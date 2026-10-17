#!/usr/bin/env python3
"""把 re_cmdtable.py 输出的处理函数地址解析成名字（demangle 简化）。

    python3 re_cmdname.py tools/tbl.txt tools/syms.txt
"""
from __future__ import annotations

import re
import sys

RE = re.compile(r"_ZN9CmdHandle(\d+)(cmdHandle|)([A-Za-z0-9_]+)E")


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
        return m.group(3)
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
