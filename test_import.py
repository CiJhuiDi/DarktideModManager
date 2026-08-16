# -*- coding: utf-8 -*-
"""造测试用 mod zip 包（标准结构/根散文件/非法/路径穿越/已存在覆盖）"""
import io
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
import json
import zipfile
from pathlib import Path

base = str(Path(__file__).resolve().parent)
mock_mods = base + r"\mock\mods"


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in entries:
            z.writestr(name, content)
    return buf.getvalue()


zips = {
    "NewMod.zip": make_zip([
        ("NewMod/NewMod.mod", 'return { run = function() new_mod("NewMod", {}) end, packages = {}, version = "1.0.0" }'),
        ("NewMod/scripts/mods/NewMod/NewMod.lua", "-- test mod"),
        ("NewMod/README.txt", "readme"),
    ]),
    "RootStyle.zip": make_zip([
        ("RootStyle.mod", 'return { run = function() new_mod("RootStyle", {}) end, packages = {}, version = "0.9" }'),
        ("scripts/mods/RootStyle/RootStyle.lua", "-- root style"),
    ]),
    "UpdateTestA.zip": make_zip([  # 覆盖已存在的 TestModA（带版本后缀目录）
        ("TestModA-2.0.0/TestModA.mod", 'return { run = function() new_mod("TestModA", {}) end, packages = {}, version = "2.0.0" }'),
        ("TestModA-2.0.0/scripts/x.lua", "-- v2"),
    ]),
    "not_a_zip.zip": b"this is not a zip file at all",
    "evil.zip": make_zip([
        ("Evil/../evil.mod", "bad"),
    ]),
}

import urllib.request

# 写 config 指向 mock（源码模式读项目根 config.json）
cfg = {"game_dir": mock_mods.replace(r"\mods", "")}
open(base + r"\config.json", "w", encoding="utf-8").write(json.dumps(cfg))

# 起服务前先确认端口 —— 服务由外部启动
import time
for _ in range(30):
    try:
        urllib.request.urlopen("http://127.0.0.1:8317/api/status", timeout=1)
        break
    except Exception:
        time.sleep(0.5)

import http.client


def upload(files: dict):
    boundary = "----dmmtest"
    body = b""
    for name, data in files.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'.encode()
        body += b"Content-Type: application/zip\r\n\r\n"
        body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    conn = http.client.HTTPConnection("127.0.0.1", 8317, timeout=30)
    conn.request("POST", "/api/mods/import", body,
                 {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    resp = conn.getresponse()
    return json.loads(resp.read().decode())


ok = fail = 0


def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label}  {detail}")


print("== import tests ==")
r = upload({k: v for k, v in zips.items() if k in ("NewMod.zip", "RootStyle.zip",
                                                   "UpdateTestA.zip", "not_a_zip.zip", "evil.zip")})
for item in r["results"]:
    print(" ", item["file"], "->", "OK" if item["ok"] else "ERR", item.get("mod") or item.get("error"))
by_file = {i["file"]: i for i in r["results"]}
check("NewMod imported", by_file["NewMod.zip"].get("ok") and by_file["NewMod.zip"]["mod"] == "NewMod")
check("RootStyle imported (root .mod)", by_file["RootStyle.zip"].get("ok") and by_file["RootStyle.zip"]["mod"] == "RootStyle")
check("TestModA updated (version-suffixed dir)", by_file["UpdateTestA.zip"].get("ok") and by_file["UpdateTestA.zip"]["mod"] == "TestModA")
check("non-zip rejected", not by_file["not_a_zip.zip"].get("ok"))
check("path traversal rejected", not by_file["evil.zip"].get("ok"))

import os
print("== filesystem checks ==")
check("NewMod dir exists", os.path.isdir(mock_mods + r"\NewMod"))
check("NewMod.mod extracted", os.path.isfile(mock_mods + r"\NewMod\NewMod.mod"))
check("scripts extracted", os.path.isfile(mock_mods + r"\NewMod\scripts\mods\NewMod\NewMod.lua"))
check("RootStyle dir exists", os.path.isdir(mock_mods + r"\RootStyle"))
check("RootStyle.mod at root extracted", os.path.isfile(mock_mods + r"\RootStyle\RootStyle.mod"))
check("TestModA v2 extracted", "version = \"2.0.0\"" in open(mock_mods + r"\TestModA\TestModA.mod", encoding="utf-8").read())
baks = [d for d in os.listdir(mock_mods) if d.startswith("TestModA.bak_")]
check("old TestModA backed up", len(baks) == 1, baks)
check("evil not extracted", not os.path.exists(mock_mods + r"\evil.mod"))

print("== load order updated ==")
lo = open(mock_mods + r"\mod_load_order.txt", encoding="utf-8").read()
check("NewMod in load order", "NewMod" in lo)
check("RootStyle in load order", "RootStyle" in lo)
check("TestModA still single entry", lo.count("TestModA") == 1, lo)

print(f"\n===== {ok} passed, {fail} failed =====")
