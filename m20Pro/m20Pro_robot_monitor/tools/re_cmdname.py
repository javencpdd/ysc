#!/usr/bin/env python3
"""把 re_cmdtable.py 输出的处理函数地址解析成名字（demangle 简化）。

    python3 re_cmdname.py tools/tbl.txt tools/syms.txt

符号形如 ``_ZN9CmdHandle15cmdHandle_SteerE<参数...>``，其中 ``15`` 是
``cmdHandle_Steer`` 的**长度前缀**（Itanium ABI 的命名规则）。

⚠️ 曾经用 ``([A-Za-z0-9_]+)E`` 抓名字，**贪婪匹配会一路吃到最后一个 E** ——
参数串里全是字母数字下划线（rapidjson/GenericValue/MemoryPoolAllocator/...），
结果解出的"名字"是整整一串 mangled 参数，而脚本毫无察觉。
改为**按长度前缀切片**，这是唯一可靠的判据（2026-10-18 修）。
"""
from __future__ import annotations

import re
import sys

#: 只用来定位长度前缀；名字长度由前缀决定，不靠正则猜
RE = re.compile(r"_ZN9CmdHandle(\d+)")
_PREFIX = "cmdHandle_"


def load_syms(path):
    m = {}
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                m[int(parts[0], 16)] = parts[2]
            except ValueError:
                pass
    return m


def pretty(sym):
    m = RE.search(sym)
    if m:
        # 长度前缀指的是**含 cmdHandle_ 的整段**，取完再剥前缀
        n = int(m.group(1))
        name = sym[m.end():m.end() + n]
        if name.startswith(_PREFIX):
            name = name[len(_PREFIX):]
        return name
    if sym.startswith("_ZN"):
        return sym
    return sym


def main():
    syms = load_syms(sys.argv[2])
    rows = []
    with open(sys.argv[1], "r", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            outer, inner, addr = int(parts[0]), int(parts[1]), int(parts[2], 16)
            rows.append((outer, inner, pretty(syms.get(addr, "<0x%x>" % addr))))
    for outer, inner, name in sorted(rows):
        print("%-6d %-6d %s" % (outer, inner, name))


if __name__ == "__main__":
    main()
