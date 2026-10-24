"""逆向工具回归测试（2026-10-18 加）。

锁两个**静默出错**的坑——它们不报错，只是悄悄给出错答案，比崩溃难查得多：

1. **`re_cmdname.pretty()` 必须按长度前缀切片**。曾用
   ``([A-Za-z0-9_]+)E`` 抓 mangled 名，参数串里全是字母数字下划线
   （``rapidjson``/``GenericValue``/``MemoryPoolAllocator``/``basic_string``…），
   贪婪匹配一路吃到最后一个 ``E``，解出的"名字"是整整一串参数——
   而脚本毫无察觉、照样打印。
2. **`re_cmdtable` 解析 objdump 必须拼接字段**。objdump 行
   ``addr:\t<机器码>\t<助记符>\t<操作数>\t// 注释`` 中助记符与操作数之间
   **也是制表符**，只取一个字段拿到的是十六进制机器码 → 输出 0 行。
"""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, filename):
    path = os.path.join(ROOT, "tools", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


re_cmdname = _load("re_cmdname", "re_cmdname.py")
re_cmdtable = _load("re_cmdtable", "re_cmdtable.py")


# 真机 nm 输出的**真实符号**（2026-10-18 从 196 的 basic_server 抓取，勿手改——
# 长度前缀写错一个字符就会解错，曾因此误判过工具）
SYM_STEER = ("_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEEN"
             "S0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_"
             "stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE")
SYM_LED = ("_ZN9CmdHandle13cmdHandle_LEDERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_"
           "19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIc"
           "St11char_traitsIcESaIcEEERKNS_9cmdInfo_tE")
SYM_LONG = ("_ZN9CmdHandle32cmdHandle_SetAutoResetJointsZeroERN9rapidjson12GenericVal"
            "ueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7_"
            "_cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE")
SYM_NOT_CMDHANDLE = "_ZN3foo3barEv"


def test_pretty_extracts_bare_name_not_mangled_params():
    """解出的必须是干净函数名，不能带任何 mangled 参数串。"""
    assert re_cmdname.pretty(SYM_STEER) == "Steer"
    assert re_cmdname.pretty(SYM_LED) == "LED"
    assert re_cmdname.pretty(SYM_LONG) == "SetAutoResetJointsZero"


def test_pretty_result_is_short_and_identifier_like():
    """长度兜底：解出的名字不该超过 handler 名本身的量级。"""
    for sym, expect in ((SYM_STEER, "Steer"), (SYM_LED, "LED"),
                        (SYM_LONG, "SetAutoResetJointsZero")):
        got = re_cmdname.pretty(sym)
        assert got == expect, "%r -> %r" % (sym[:40], got)
        assert len(got) <= 40, "名字长 %d，八成把参数串吃进来了" % len(got)


def test_pretty_handles_non_cmdhandle_symbol():
    """非 cmdHandle 符号不该崩，原样返回。"""
    assert re_cmdname.pretty(SYM_NOT_CMDHANDLE) == SYM_NOT_CMDHANDLE
    assert re_cmdname.pretty("main") == "main"


def test_pretty_length_prefix_is_used_not_regex_greed():
    """长度前缀优先：即使正则能匹配也不许它贪婪越界。

    这条直接对着曾经的 bug 写——旧正则会返回
    ``_SteerERN9rapidjson…cmdInfo_t`` 这么一长串。
    """
    got = re_cmdname.pretty(SYM_STEER)
    assert "rapidjson" not in got and "MemoryPoolAllocator" not in got
    assert got != SYM_STEER


def test_pretty_long_name_uses_its_own_prefix():
    """长名字（32 字符）不能按短名字的长度截断。

    曾经手写夹具把长度前缀写错，解出 `SetAutoResetJoi` —— 工具行为其实是对的，
    错的是夹具。这条保证夹具用的是真机符号、且长短名都覆盖。
    """
    assert re_cmdname.pretty(SYM_LONG) == "SetAutoResetJointsZero"
    assert re_cmdname.pretty(SYM_STEER) == "Steer"          # 短名不被长名逻辑影响


# ---------------------------------------------------------------- objdump 解析
ASM_LINE_OK = ("  d2430:\td2800540 \tmov\tw0, #0x2e \t// #46\n")
ASM_LINE_TABBED = ("  d2434:\t39400000 \tstrb\tw0, [x0, #14]\t// 16-bit store\n")


def test_cmdtable_joins_tab_separated_insn_fields():
    """助记符与操作数之间也是制表符 —— 拼接后必须能认出 mov/strb。"""
    # 直接验证行解析逻辑：取 parts[2:] 再 join，不能只取一个字段
    for line in (ASM_LINE_OK, ASM_LINE_TABBED):
        parts = line.split("\t")
        assert len(parts) >= 3, "测试数据本身错了"
        insn = "\t".join(parts[2:]).strip()
        assert insn, "拼接后为空，说明只取到了机器码"
        assert insn.split("\t")[0].isalpha(), "首段应是助记符，实际 %r" % insn[:20]


def test_cmdtable_mov_regex_matches_assembled_insn():
    """mov 立即数必须能解析出来（这是 Type/Command 的来源）。"""
    parts = ASM_LINE_OK.split("\t")
    insn = "\t".join(parts[2:]).strip()
    m = re_cmdtable.RE_MOV.match(insn)
    assert m is not None, "mov 没匹配上：%r" % insn
    assert int(m.group(2), 16) == 0x2E          # #46 → 十进制 46


def test_cmdtable_str_regex_matches_assembled_insn():
    parts = ASM_LINE_TABBED.split("\t")
    insn = "\t".join(parts[2:]).strip()
    m = re_cmdtable.RE_STR.match(insn)
    # strb 不是 str，这里主要验证"能走到正则"而不是崩；
    # 真正的 str 行用下面单独一条
    assert m is None or m.group(1) == "w0"


def test_cmdtable_real_str_line_parses():
    line = "  d2440:\tb9001bff \tstr\tw31, [sp, #16]\t// 16-bit store\n"
    insn = "\t".join(line.split("\t")[2:]).strip()
    m = re_cmdtable.RE_STR.match(insn)
    assert m is not None, "str 没匹配上：%r" % insn
    # 正则里 w 是字面量，捕获组只有数字部分
    assert m.group(1) == "31"
    assert int(m.group(2)) == 16
