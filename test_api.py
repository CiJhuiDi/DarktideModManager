# -*- coding: utf-8 -*-
"""测试脚本：对 mock 环境跑一遍全部 API（写操作会改 mock 文件，不会碰真实游戏）"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
MOCK_MODS = BASE / "mock" / "mods"
HTTP = "http://127.0.0.1:8317"


def call(method, path, body=None):
    path = urllib.parse.quote(path, safe="/%")  # URL 编码中文路径
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(HTTP + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"HTTP_ERROR": e.code, "body": e.read().decode()[:300]}


ok = 0
fail = 0


def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label}  {detail}")


print("== status ==")
st = call("GET", "/api/status")
check("status points to mock", "mock" in st.get("game_dir", ""), st)
check("total=4 mods", st.get("total") == 4, st)

print("== initial mods ==")
mods = call("GET", "/api/mods")["mods"]
names = {m["name"]: m for m in mods}
check("base excluded", "base" not in names)
check("4 mods found", len(mods) == 4, [m["name"] for m in mods])
check("A/B/C enabled", all(names[n]["enabled"] for n in ["TestModA", "TestModB", "TestModC"]))
check("DisabledMod disabled", not names["DisabledMod"]["enabled"])
check("versions parsed", names["TestModA"]["version"] == "1.2.0", names["TestModA"])

print("== toggle ==")
r = call("POST", "/api/mods/TestModB/toggle")
check("toggle off returns enabled=false", r.get("enabled") is False, r)
mods = call("GET", "/api/mods")["mods"]
names = {m["name"]: m for m in mods}
check("B now disabled", not names["TestModB"]["enabled"])
r = call("POST", "/api/mods/TestModB/toggle")
check("toggle on returns enabled=true", r.get("enabled") is True, r)

print("== order ==")
r = call("POST", "/api/order", {"mods": ["TestModC", "TestModA"]})
check("order ok", r.get("ok") is True, r)
mods = call("GET", "/api/mods")["mods"]
enabled = [m["name"] for m in mods if m["enabled"]]
check("enabled order = C,A", enabled == ["TestModC", "TestModA"], enabled)
check("B disabled after order", "TestModB" not in enabled)

print("== file content after order ==")
lines = open(MOCK_MODS / "mod_load_order.txt",
             encoding="utf-8").read().splitlines()
check("comment header preserved", any(l.startswith("-- 测试注释行") for l in lines))
check("disabled_by_comment preserved", any(l.startswith("--disabled_by_comment") for l in lines))
check("B commented out", "--TestModB" in lines, lines)

print("== profiles ==")
r = call("POST", "/api/profiles", {"name": "打宝流"})
check("profile saved", r.get("ok") is True, r)
r = call("GET", "/api/profiles")
check("profile listed", any(p["name"] == "打宝流" and p["count"] == 2 for p in r["profiles"]), r)
# 改一下状态再应用预设
call("POST", "/api/mods/TestModB/toggle")
call("POST", "/api/order", {"mods": ["TestModA", "TestModC", "TestModB"]})
r = call("POST", "/api/profiles/打宝流/apply")
check("profile applied", r.get("ok") is True, r)
mods = call("GET", "/api/mods")["mods"]
enabled = [m["name"] for m in mods if m["enabled"]]
check("after apply: C,A enabled", enabled == ["TestModC", "TestModA"], enabled)
check("B disabled again", "TestModB" not in enabled)
r = call("DELETE", "/api/profiles/打宝流")
check("profile deleted", r.get("ok") is True, r)

print("== toggle missing-dir mod (listed but folder gone) ==")
# 模拟：清单里有但目录里没有的 mod —— 加一个 ghost 行到 mock 清单
open(MOCK_MODS / "mod_load_order.txt", "a", encoding="utf-8").write("GhostMod\n")
mods = call("GET", "/api/mods")["mods"]
ghost = [m for m in mods if m["name"] == "GhostMod"]
check("ghost marked missing", ghost and ghost[0].get("missing") is True, ghost)
r = call("POST", "/api/mods/GhostMod/toggle")
check("ghost toggle ok", r.get("ok") is True, r)

print(f"\n===== {ok} passed, {fail} failed =====")
