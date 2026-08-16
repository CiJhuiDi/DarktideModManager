# -*- coding: utf-8 -*-
"""多格式导入测试：zip / 7z / tar.gz / rar / 未知扩展名"""
import io
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
import json
import os
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

import py7zr
import zipfile

base = str(Path(__file__).resolve().parent)
mock_mods = base + r"\mock\mods"

WINRAR = r"C:\Program Files\WinRAR\WinRAR.exe"
HAVE_WINRAR = os.path.isfile(WINRAR)

MOD_BODY = 'return { run = function() new_mod("%s", {}) end, packages = {}, version = "1.0.0" }'

# 造各种格式的测试包（内容都是标准结构：ModDir/ModDir.mod + scripts）
def build_7z(name):
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        z.writestr(MOD_BODY % name, f"{name}/{name}.mod")  # 注意 py7zr 参数顺序是 (data, arcname)
        z.writestr("-- 7z test", f"{name}/scripts/mods/{name}/{name}.lua")
    return buf.getvalue()

def build_targz(name):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        def add(p, content):
            ti = tarfile.TarInfo(p)
            data = content.encode()
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
        add(f"{name}/{name}.mod", MOD_BODY % name)
        add(f"{name}/scripts/mods/{name}/{name}.lua", "-- tar test")
    return buf.getvalue()

def build_rar(name):
    # 用系统 WinRAR 创建（无 WinRAR 时跳过 rar 用例）
    work = base + r"\mock\rarwork"
    os.makedirs(work + f"\\{name}", exist_ok=True)
    with open(work + f"\\{name}\\{name}.mod", "w", encoding="utf-8") as f:
        f.write(MOD_BODY % name)
    os.makedirs(work + f"\\{name}\\scripts", exist_ok=True)
    rar_path = work + f"\\{name}.rar"
    subprocess.run([WINRAR, "a", "-ep1", "-y", rar_path, work + f"\\{name}"],
                   capture_output=True, timeout=60)
    with open(rar_path, "rb") as f:
        return f.read()

# config 指向 mock
cfg = {"game_dir": mock_mods.replace(r"\mods", "")}
open(base + r"\config.json", "w", encoding="utf-8").write(json.dumps(cfg))

# 等服务就绪
for _ in range(40):
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
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    conn = http.client.HTTPConnection("127.0.0.1", 8317, timeout=60)
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


files = {
    "ModZip.zip": build_rar("ModZip"),  # 占位，下面覆盖
}
# 正式构造
z = io.BytesIO()
with zipfile.ZipFile(z, "w") as zf:
    zf.writestr("ModZip/ModZip.mod", MOD_BODY % "ModZip")
    zf.writestr("ModZip/scripts/mods/ModZip/ModZip.lua", "-- zip test")
files["ModZip.zip"] = z.getvalue()
files["ModSeven.7z"] = build_7z("ModSeven")
files["ModTar.tar.gz"] = build_targz("ModTar")
if HAVE_WINRAR:
    files["ModRar.rar"] = build_rar("ModRar")
files["weird.abc"] = z.getvalue()  # 未知扩展名但内容为 zip

r = upload(files)
for item in r["results"]:
    print(" ", item["file"], "->", "OK" if item["ok"] else "ERR", item.get("mod") or item.get("error"))
by_file = {i["file"]: i for i in r["results"]}
check("zip ok", by_file["ModZip.zip"].get("ok") and by_file["ModZip.zip"]["mod"] == "ModZip")
check("7z ok", by_file["ModSeven.7z"].get("ok") and by_file["ModSeven.7z"]["mod"] == "ModSeven")
check("tar.gz ok", by_file["ModTar.tar.gz"].get("ok") and by_file["ModTar.tar.gz"]["mod"] == "ModTar")
if HAVE_WINRAR:
    check("rar ok (via WinRAR)", by_file["ModRar.rar"].get("ok") and by_file["ModRar.rar"]["mod"] == "ModRar", by_file["ModRar.rar"])
else:
    print("  SKIP  rar 用例（系统未安装 WinRAR）")
check("unknown ext fallback ok", by_file["weird.abc"].get("ok") and by_file["weird.abc"]["mod"] == "ModZip", by_file["weird.abc"])

print("== filesystem ==")
for name in ("ModZip", "ModSeven", "ModTar"):
    check(f"{name} dir + .mod", os.path.isfile(mock_mods + f"\\{name}\\{name}.mod"))
if HAVE_WINRAR:
    check("ModRar dir + .mod", os.path.isfile(mock_mods + r"\ModRar\ModRar.mod"))

print("== load order ==")
lo = open(mock_mods + r"\mod_load_order.txt", encoding="utf-8").read()
for name in ("ModZip", "ModSeven", "ModTar"):
    check(f"{name} in load order", name in lo)
if HAVE_WINRAR:
    check("ModRar in load order", "ModRar" in lo)

# 清理 rar 工作目录
import shutil
shutil.rmtree(base + r"\mock\rarwork", ignore_errors=True)
print(f"\n===== {ok} passed, {fail} failed =====")
