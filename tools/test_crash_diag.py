# -*- coding: utf-8 -*-
"""crash 日志诊断：crashify 块解析 + 行分类噪声过滤（回归测试）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crash import parse_crashify_blocks, classify_log_line

SAMPLE = """14:16:06.082 [Lua] INFO [BackendManager] title_request: GET /tracks/x
14:16:06.096 [Lua] <<crashify-exception>>
              \t<<system>>ConstantElementNotificationFeed<</system>>
              \t<<message>>Item type "WEAPON_MELEE" is not defined!<</message>>
              \t<<callstack>><Lua Script.Callstack>
  [1] @scripts/foundation/utilities/crashify.lua:82: in function print_exception
  [2] ./../mods/WhosNotReady/scripts/mods/WhosNotReady/WhosNotReady.lua:67
  [3] ./../mods/SpecialsTracker/scripts/mods/SpecialsTracker/SpecialsTracker.lua:651
  [4] ./../mods/dmf/scripts/mods/dmf/modules/core/hooks.lua:199
</Lua Script.Callstack>
<</callstack>>
              <</crashify-exception>>
14:16:06.178 [Lua] INFO [BackendManager] title_request done"""


def test_parse_crashify_blocks():
    diag = parse_crashify_blocks(SAMPLE)
    assert len(diag) == 1, f'期望 1 块，实际 {len(diag)}'
    d = diag[0]
    assert d['system'] == 'ConstantElementNotificationFeed', d
    assert 'WEAPON_MELEE' in d['message'], d
    # mods 按帧出现顺序（越接近抛错点越靠后出现，保持日志顺序）；断言集合一致
    assert d['mods'] == ['WhosNotReady', 'SpecialsTracker'] or sorted(d['mods']) == ['SpecialsTracker', 'WhosNotReady'], d['mods']
    # frames 逐帧解析：mod 帧带 mod 名 + 源码行号
    mod_frames = [f for f in d['frames'] if f['kind'] == 'mod']
    assert len(mod_frames) == 2, mod_frames
    st = next(f for f in mod_frames if f['mod'] == 'SpecialsTracker')
    assert st['line'] == 651, st
    wn = next(f for f in mod_frames if f['mod'] == 'WhosNotReady')
    assert wn['line'] == 67, wn
    print('  frames:', [(f['mod'], f['line']) for f in mod_frames])
    assert d['line'] == 2, d['line']
    print('test_parse_crashify_blocks OK:', d['summary'])


def test_no_false_positive_on_info():
    # 旧规则会误标红的 INFO 噪声行，现在应判 ok
    noise = [
        '[Lua] INFO [Log Internal] Exceptions will be handled as warnings',
        '[ParameterResolver] Overriding param [error_codes_crashifyreport] from backend',
        '[ErrorCodes] Crashify exception enabled from backend for error_code: "pong_timeout"',
        'error:   [Unit] Unit: has still childs attached to it, please unlink',
        '[Lua] ERROR [WorldLevelDespawnManager] Unregistering orphaned unit',
        '[Backend] "Character not found"',
    ]
    for ln in noise:
        assert classify_log_line(ln) == 'ok', f'噪声误标: {ln}'
    print('test_no_false_positive_on_info OK (%d 条噪声)' % len(noise))


def test_real_error_still_caught():
    real = [
        '[Lua] <<crashify-exception>>',
        '[Lua] ERROR attempt to index a nil value (field \'foo\')',
        'error:   [Lua] ERROR [Unit] attempt to call method',
    ]
    for ln in real:
        assert classify_log_line(ln) == 'err', f'真错误漏标: {ln}'
    print('test_real_error_still_caught OK')


def test_empty_input():
    assert parse_crashify_blocks('') == []
    assert parse_crashify_blocks('no exception here') == []
    print('test_empty_input OK')


if __name__ == '__main__':
    test_parse_crashify_blocks()
    test_no_false_positive_on_info()
    test_real_error_still_caught()
    test_empty_input()
    print('\n全部通过')
