# -*- coding: utf-8 -*-
"""整合包"解压一次"回归：预览与导入共用暂存，不再重复解压与重复上传。

用户反馈：导入别人的整合包时触发了两次解压缩。
旧流程 = 预览解压一次（且包体 base64 上传，体积 +33%）+ 导入再解压一次。
新流程 = /api/pack/stage 上传一次、解压一次 → token 复用。

本测试用**计数**断言解压次数（不靠感觉），并覆盖过期 token、非整合包、暂存清理。
"""
import io
import shutil
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def tempfile_dir():
    """临时目录（供"解压判定"用例使用）"""
    with tempfile.TemporaryDirectory() as td:
        yield td


if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import state                      # noqa: E402
from core import mods as core_mods          # noqa: E402
from core import imports as I               # noqa: E402

MOCK = ROOT / 'mock_stage'
FAILED = []


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f"  <- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def point_to(mock: Path):
    state.GAME_DIR = mock.resolve()
    state.MODS_DIR = state.GAME_DIR / "mods"
    state.LOAD_ORDER_FILE = state.MODS_DIR / "mod_load_order.txt"
    state.CONFIG_FILE = mock.resolve() / "config_test.json"
    state.BACKUP_DIR = mock.resolve() / "backups"
    state.MY_MODS_DIR = mock.resolve() / "my_mods"
    core_mods.MY_MODS_FILE = mock.resolve() / "my_mods.json"
    core_mods._my_mods_cache = None


def setup():
    # 注意：本测试自己会造**只读文件**（第 10/11 节），清理必须用 safe_rmtree，
    # 否则 rmtree 静默失败 → 下次运行 FileExistsError（同一个只读坑，实测踩过）
    if MOCK.exists():
        state.safe_rmtree(MOCK, ignore_errors=True)
    (MOCK / "mods").mkdir(parents=True, exist_ok=True)
    (MOCK / "backups").mkdir(parents=True, exist_ok=True)
    point_to(MOCK)
    for t in list(I._PACK_STAGES):
        I._drop_stage(t)
    I._PACK_STAGES.clear()
    state.safe_rmtree(I._PACK_STAGE_ROOT, ignore_errors=True)   # 清掉上一次运行可能留下的暂存


def make_pack(names_ver: dict) -> bytes:
    buf = io.BytesIO()
    body = 'return { run = function() new_mod("X", {}) end, packages = {}, version = "%s" }'
    with zipfile.ZipFile(buf, 'w') as z:
        for n, v in names_ver.items():
            z.writestr(f"mods/{n}/{n}.mod", body % v)
            z.writestr(f"mods/{n}/scripts/{n}.lua", f"-- {n}")
        z.writestr("mods/mod_load_order.txt", "\n".join(names_ver) + "\n")
    return buf.getvalue()


def make_notpack() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr("readme.txt", "not a pack")
    return buf.getvalue()


class ExtractCounter:
    """统计 extract_archive 被调用几次（这正是用户报的"解压两次"）"""

    def __init__(self):
        self.n = 0
        self.orig = I.extract_archive

    def __enter__(self):
        def counting(data, filename, out):
            self.n += 1
            return self.orig(data, filename, out)
        I.extract_archive = counting
        return self

    def __exit__(self, *exc):
        I.extract_archive = self.orig
        return False


print("===== 1. 新流程：stage + 带 token 导入 → 只解压一次 =====")
setup()
data = make_pack({"PackA": "1.0", "PackB": "1.0"})
with ExtractCounter() as c:
    st = I.stage_pack_archive("pack.zip", data)
    check("stage 成功并返回 token", st.get("ok") is True and bool(st.get("token")), str(st)[:120])
    tok = st.get("token", "")
    check("stage 已解压一次", c.n == 1, f"解压 {c.n} 次")
    pv = st.get("preview") or {}
    check("stage 同时给出预览", pv.get("ok") is True and pv.get("added") == ["PackA", "PackB"],
          str(pv.get("added")))
    check("预览里带 staged_token", pv.get("staged_token") == tok, str(pv.get("staged_token")))
    staged_dir = I._PACK_STAGES[tok]["dir"]
    check("暂存目录已建立", staged_dir.is_dir(), str(staged_dir))
    r = I.import_pack_archive("pack.zip", b"", "replace", keep_enabled=True, staged_token=tok)
    check("带 token 导入成功", r.get("ok") is True, str(r.get("error"))[:120])
    check("导入没有再次解压（总数仍 1）", c.n == 1, f"解压 {c.n} 次")
    check("mod 已落地", (state.MODS_DIR / "PackA").is_dir() and (state.MODS_DIR / "PackB").is_dir())
check("导入后暂存已清理", not staged_dir.exists(), str(staged_dir))
check("暂存登记已移除", tok not in I._PACK_STAGES)

print("\n===== 2. 旧调用（无 token）仍可用，但确实是两次解压 =====")
setup()
data = make_pack({"PackA": "1.0"})
with ExtractCounter() as c:
    pv = I.preview_pack_archive("pack.zip", data)
    check("旧预览可用", pv.get("ok") is True, str(pv)[:100])
    r = I.import_pack_archive("pack.zip", data, "replace")
    check("旧导入可用", r.get("ok") is True, str(r.get("error"))[:100])
    check("旧流程解压两次（对照，说明这次优化修的是什么）", c.n == 2, f"解压 {c.n} 次")

print("\n===== 3. token 过期/非法 → 明确报错且不解压 =====")
setup()
with ExtractCounter() as c:
    r = I.import_pack_archive("pack.zip", b"", "replace", staged_token="deadbeef")
    check("拒绝并提示重新选择", r.get("ok") is False and "暂存已过期" in (r.get("error") or ""),
          str(r.get("error")))
    check("非法 token 不会触发解压", c.n == 0, f"解压 {c.n} 次")

print("\n===== 4. 不是整合包 → stage 失败且不留暂存 =====")
setup()
before = set(I._PACK_STAGES)
dirs_before = {d.name for d in I._PACK_STAGE_ROOT.iterdir()} if I._PACK_STAGE_ROOT.is_dir() else set()
r = I.stage_pack_archive("x.zip", make_notpack())
check("stage 拒绝非整合包", r.get("ok") is False and "不是暗潮整合包" in (r.get("error") or ""),
      str(r.get("error"))[:120])
check("失败后没有残留暂存登记", set(I._PACK_STAGES) == before, str(I._PACK_STAGES))
dirs_after = {d.name for d in I._PACK_STAGE_ROOT.iterdir()} if I._PACK_STAGE_ROOT.is_dir() else set()
check("失败后没有新增暂存目录", dirs_after == dirs_before, f"新增 {dirs_after - dirs_before}")

print("\n===== 5. 过期暂存会被清理 =====")
setup()
st = I.stage_pack_archive("pack.zip", make_pack({"PackA": "1.0"}))
tok2 = st["token"]
d2 = I._PACK_STAGES[tok2]["dir"]
I._PACK_STAGES[tok2]["ts"] = time.time() - (I._PACK_STAGE_TTL + 10)   # 伪造成过期
I._prune_stages()
check("过期暂存登记被清", tok2 not in I._PACK_STAGES)
check("过期暂存目录被删", not d2.exists(), str(d2))

print("\n===== 6. 带 token 且同时上传其他文件：都能导入 =====")
setup()
st = I.stage_pack_archive("first.zip", make_pack({"First": "1.0"}))
tok3 = st["token"]
r1 = I.import_pack_archive("first.zip", b"", "merge", staged_token=tok3)
r2 = I.import_pack_archive("second.zip", make_pack({"Second": "1.0"}), "merge")
check("暂存的那个导入成功", r1.get("ok") is True, str(r1.get("error"))[:100])
check("后上传的那个也成功", r2.get("ok") is True, str(r2.get("error"))[:100])
check("两个 mod 都在", (state.MODS_DIR / "First").is_dir() and (state.MODS_DIR / "Second").is_dir())

print("\n===== 7. 用户取消导入 → 立刻释放暂存（不等 TTL） =====")
setup()
st = I.stage_pack_archive("pack.zip", make_pack({"PackA": "1.0"}))
tok4 = st["token"]
d4 = I._PACK_STAGES[tok4]["dir"]
I._drop_stage(tok4)          # 对应 /api/pack/stage/discard 的内核
check("取消后暂存登记清空", tok4 not in I._PACK_STAGES)
check("取消后暂存目录删除", not d4.exists(), str(d4))

print("\n===== 8. 不解压判定 vs 解压判定：结论必须一致 =====")
setup()
body = 'return { run = function() new_mod("X", {}) end, packages = {}, version = "1.0" }'


def zip_of(entries: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for k, v in entries.items():
            z.writestr(k, v)
    return b.getvalue()


CASES = {
    "整合包_多mod带清单": ({"mods/A/A.mod": body, "mods/B/B.mod": body,
                            "mods/mod_load_order.txt": "A\nB\n"}, "pack"),
    "整合包_带系统组件base": ({"mods/A/A.mod": body, "mods/base/init.lua": "--", }, "pack"),
    "整合包_带加载器": ({"binaries/mod_loader": "x", "mods/A/A.mod": body}, "pack"),
    "整合包_套一层目录": ({"DarktidePack/mods/A/A.mod": body, "DarktidePack/mods/B/B.mod": body,
                            "DarktidePack/mods/mod_load_order.txt": "A\nB\n"}, "pack"),
    "单mod_根目录mod文件": ({"MyMod.mod": body, "scripts/mods/MyMod/x.lua": "--"}, "mod"),
    "单mod_包裹_mo墙s一个无清单": ({"mods/OnlyOne/OnlyOne.mod": body}, "ambiguous"),
}
for label, (entries, expect) in CASES.items():
    data_c = zip_of(entries)
    idx = I.classify_archive_index(data_c, "t.zip")
    with tempfile_dir() as td:
        out = Path(td) / "out"
        out.mkdir()
        I.extract_archive(data_c, "t.zip", out)
        ext = I.classify_archive(out)
    check(f"索引判定 == 解压判定（{label}）", idx == ext, f"索引={idx} 解压={ext}")
    check(f"判定结果符合预期（{label}）", idx == expect, f"得到 {idx}，期望 {expect}")

check("rar 等读不到索引时返回 None（交给解压判定）",
      I.classify_archive_index(b"not an archive", "x.rar") is None,
      str(I.classify_archive_index(b"not an archive", "x.rar")))

print("\n===== 9. 「＋ 导入」整条路径（分类 → 预览 → 导入）只解压一次 =====")
setup()
data = make_pack({"PackA": "1.0", "PackB": "1.0"})
with ExtractCounter() as c:
    r0 = I.import_mod_archive("pack.zip", data)          # 分类：以前会整个解压一遍
    check("分类阶段认出是整合包", r0.get("is_pack") is True, str(r0)[:100])
    check("分类阶段解压 0 次", c.n == 0, f"解压 {c.n} 次")
    st = I.stage_pack_archive("pack.zip", data)          # 预览：解压一次
    tok9 = st["token"]
    r1 = I.import_pack_archive("pack.zip", b"", "replace", keep_enabled=True, staged_token=tok9)
    check("导入成功", r1.get("ok") is True, str(r1.get("error"))[:100])
    check("整条路径合计只解压 1 次", c.n == 1, f"解压 {c.n} 次")
check("导入结果正确落地", (state.MODS_DIR / "PackA").is_dir() and (state.MODS_DIR / "PackB").is_dir())

print("\n===== 10. 只读文件也要能删干净（导入后不留垃圾） =====")
# 用户的整合包里带 git 检出（.git/objects/* 是只读的），实测 shutil.rmtree(ignore_errors=True)
# 会静默失败——暂存目录整份留在 %TEMP%。这里就把"只读文件"造出来验证。
setup()
ro_pack = SHOT_PACK = None
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('mods/RoMod/RoMod.mod', body)
    z.writestr('mods/RoMod/.git/objects/ab/cdef0123456789', 'x' * 64)
    z.writestr('mods/RoMod/scripts/readonly.lua', '-- 只读文件')
    z.writestr('mods/mod_load_order.txt', 'RoMod\n')
ro_data = buf.getvalue()

st10 = I.stage_pack_archive("ro.zip", ro_data)
check("含只读文件的包也能暂存成功", st10.get("ok") is True, str(st10)[:120])
tok10 = st10["token"]
sd = I._PACK_STAGES[tok10]["dir"]
# 把解压出来的文件设成只读（模拟从 git 检出的包）
import os as _os
import stat as _stat
ro_files = 0
for p in sd.rglob('*'):
    if p.is_file():
        _os.chmod(p, _stat.S_IREAD)
        ro_files += 1
check("已把解压出的文件设为只读", ro_files > 0, f"{ro_files} 个文件")
r10 = I.import_pack_archive("ro.zip", b"", "replace", staged_token=tok10)
check("带 token 导入成功", r10.get("ok") is True, str(r10.get("error"))[:120])
check("导入后暂存目录被彻底删除（只读文件不再是障碍）", not sd.exists(), str(sd))
check("mod 已落地", (state.MODS_DIR / "RoMod").is_dir())

# 顺带验证 state.safe_rmtree 本体
d_ro = MOCK / "ro_only"
(d_ro / "sub").mkdir(parents=True)
f_ro = d_ro / "sub" / "readonly.bin"
f_ro.write_bytes(b"x")
_os.chmod(f_ro, _stat.S_IREAD)
ok_rm = state.safe_rmtree(d_ro)
check("state.safe_rmtree 能删掉含只读文件的目录", ok_rm and not d_ro.exists(), f"返回 {ok_rm} 剩余 {d_ro.exists()}")

print("\n===== 11. TTL 清理也要能清掉只读残留 =====")
d_old = I._PACK_STAGE_ROOT / "stale_readonly"
(d_old / "deep").mkdir(parents=True, exist_ok=True)
f_old = d_old / "deep" / "ro.bin"
f_old.write_bytes(b"y")
_os.chmod(f_old, _stat.S_IREAD)
old_t = time.time() - (I._PACK_STAGE_TTL + 60)
_os.utime(d_old, (old_t, old_t))
I._prune_stages()
check("TTL 清理清掉了含只读文件的残留目录", not d_old.exists(), str(d_old))

# 收尾：清暂存 + mock
for t in list(I._PACK_STAGES):
    I._drop_stage(t)
state.safe_rmtree(MOCK, ignore_errors=True)
state.safe_rmtree(I._PACK_STAGE_ROOT, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
