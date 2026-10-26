# -*- coding: utf-8 -*-
"""用户 2026-10-10 报的"导入整合包仍然解压两次"：索引读不到的格式（rar / tar / 未知扩展名）。

路径：拖入/「＋ 导入」一个**索引读不到**的整合包 →
  ① 判定类型时解压一次（老写法在这里整包解压，随后 stage 又解压一次 = 用户看到的两次）
  ② 现在这次解压直接进暂存区并把 token 交出去，导入复用 → 全流程只解压 1 次
"""
import io
import sys
import tarfile
import zipfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import state                       # noqa: E402
from core import imports as I                # noqa: E402
from core.load_order import read_load_order, enabled_names   # noqa: E402

MOCK = ROOT / 'mock_indexless'
BODY = 'return { run = function() new_mod("X", {}) end, packages = {}, version = "1.0" }'
FAILED = []


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f"  <- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def setup():
    if MOCK.exists():
        state.safe_rmtree(MOCK, ignore_errors=True)
    (MOCK / 'mods').mkdir(parents=True)
    (MOCK / 'backups').mkdir(parents=True)
    state.GAME_DIR = MOCK
    state.MODS_DIR = MOCK / 'mods'
    state.LOAD_ORDER_FILE = state.MODS_DIR / 'mod_load_order.txt'
    state.CONFIG_FILE = MOCK / 'c.json'
    state.BACKUP_DIR = MOCK / 'backups'
    state.MY_MODS_DIR = MOCK / 'my_mods'
    I._PACK_STAGES.clear()
    I.EXTRACT_CALLS = 0


def zip_bytes(mods=('IdxA', 'IdxB'), with_list=True):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for n in mods:
            z.writestr(f'mods/{n}/{n}.mod', BODY)
        if with_list:
            z.writestr('mods/mod_load_order.txt', '\n'.join(mods) + '\n')
    return b.getvalue()


def tar_bytes(mods=('TarA', 'TarB')):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode='w') as t:
        for n in mods:
            data = BODY.encode()
            info = tarfile.TarInfo(f'mods/{n}/{n}.mod')
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        lo = ('\n'.join(mods) + '\n').encode()
        info = tarfile.TarInfo('mods/mod_load_order.txt')
        info.size = len(lo)
        t.addfile(info, io.BytesIO(lo))
    return b.getvalue()


print("===== 1. 未知扩展名的整合包（索引读不到）→ 只解压一次 =====")
setup()
data = zip_bytes()
r1 = I.import_mod_archive('MyPack.pack', data)      # 未知扩展名 → 索引读不到
check("判定为整合包", r1.get('is_pack') is True, str(r1)[:140])
check("回传 staged_token", bool(r1.get('staged_token')), str(r1.get('staged_token'))[:20])
check("同时回传预览", bool(r1.get('preview')) and r1['preview'].get('pack_count') == 2,
      str(r1.get('preview', {}).get('pack_count')))
after_classify = I.EXTRACT_CALLS
check("判定阶段解压 1 次", after_classify == 1, str(after_classify))

r2 = I.import_pack_archive('MyPack.pack', b'', 'replace', staged_token=r1['staged_token'])
check("带 token 的导入成功", r2.get('ok') is True, str(r2.get('error'))[:140])
check("全流程总共只解压 1 次（用户报的第二次没了）", I.EXTRACT_CALLS == 1, str(I.EXTRACT_CALLS))
check("包内 mod 已落盘", (state.MODS_DIR / 'IdxA').is_dir() and (state.MODS_DIR / 'IdxB').is_dir())
check("清单已按作者条目写入", enabled_names(read_load_order()) == ['IdxA', 'IdxB'],
      str(enabled_names(read_load_order())))
check("暂存已释放（导入后不留临时目录）", not I._PACK_STAGES, str(list(I._PACK_STAGES)))

print("\n===== 2. tar 包现在能只读索引（0 次解压判定）=====")
setup()
r3 = I.import_mod_archive('MyPack.tar', tar_bytes())
check("tar 判定为整合包", r3.get('is_pack') is True, str(r3)[:140])
check("tar 判定阶段 0 次解压（索引里就能看出来）", I.EXTRACT_CALLS == 0, str(I.EXTRACT_CALLS))
r4 = I.import_pack_archive('MyPack.tar', tar_bytes(), 'replace')
check("tar 导入成功且只解压 1 次", r4.get('ok') is True and I.EXTRACT_CALLS == 1, str(I.EXTRACT_CALLS))

print("\n===== 3. 未知扩展名的**单个 mod**：解压一次后直接导入，不留暂存 =====")
setup()
b = io.BytesIO()
with zipfile.ZipFile(b, 'w') as z:
    z.writestr('SoloMod/SoloMod.mod', BODY)
r5 = I.import_mod_archive('SoloMod.mystery', b.getvalue())
check("单个 mod 导入成功", r5.get('ok') is True, str(r5)[:160])
check("只解压 1 次", I.EXTRACT_CALLS == 1, str(I.EXTRACT_CALLS))
check("单 mod 不留暂存", not I._PACK_STAGES, str(list(I._PACK_STAGES)))
# mod 目录名取自 .mod 内容里的 new_mod("X")，不是压缩包里的文件夹名
installed = r5.get('mod') or 'X'
check("mod 已落盘", (state.MODS_DIR / installed).is_dir(), f"{installed} -> {sorted(p.name for p in state.MODS_DIR.iterdir())}")

print("\n===== 4. zip 走索引快路：判定 0 次解压，导入 1 次 =====")
setup()
r6 = I.import_mod_archive('MyPack.zip', zip_bytes())
check("zip 判定为整合包且 0 次解压", r6.get('is_pack') is True and I.EXTRACT_CALLS == 0, str(I.EXTRACT_CALLS))
r7 = I.import_pack_archive('MyPack.zip', zip_bytes(), 'replace')
check("zip 导入共 1 次解压", r7.get('ok') is True and I.EXTRACT_CALLS == 1, str(I.EXTRACT_CALLS))

print("\n===== 5. 失效 token 仍然报错（不会偷偷重新解压整包）=====")
setup()
r8 = I.import_pack_archive('MyPack.pack', b'', 'replace', staged_token='deadbeef')
check("失效 token 明确报错", r8.get('ok') is False and '暂存已过期' in (r8.get('error') or ''), str(r8)[:120])
check("失效 token 时没有解压", I.EXTRACT_CALLS == 0, str(I.EXTRACT_CALLS))

state.safe_rmtree(MOCK, ignore_errors=True)
print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    raise SystemExit(1)
print("全部通过 通过")
