#!/usr/bin/env python3
"""从 basic_server 反汇编里还原 (Type, Command) -> 处理函数 映射表。

在车上跑：
    objdump -d <bin> > /tmp/bs.asm
    python3 re_cmdtable.py /tmp/bs.asm

注册代码形如（AArch64，外层 map 键在栈槽 A，内层在槽 B）：

    adrp  x2, <pool>     ; .text 常量池，首 8 字节 = 处理函数指针
    add   x2, x2, #imm
    mov   wN,  #outer    ; Type
    str   wN,  [sp, #A]
    stp   x2, xzr, [sp, #...]
    bl    <unordered_map<int, unordered_map<int,function>>::operator[]>
    mov   wM,  #inner    ; Command
    str   wM,  [sp, #B]
    bl    <unordered_map<int, function>::operator[]>

以「内层 map 的 operator[] 调用」为锚点，向前取最近两个不同栈槽的 str。
"""
from __future__ import annotations

import re
import sys

RE_MOV = re.compile(r"mov\s+w(\d+), #0x([0-9a-f]+)")
RE_ADRP = re.compile(r"adrp\s+x2, ([0-9a-f]{4,}) ")
RE_ADD = re.compile(r"add\s+x2, x2, #0x([0-9a-f]+)")
RE_STR = re.compile(r"str\s+w(\w+), \[sp, #(\d+)\]")
#: 内层 map = unordered_map<int, std::function<...>> 的 operator[](int&&)
RE_INNER = re.compile(r"Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson.*ixEOi>")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: re_cmdtable.py <asm>")
        return 2
    regs = {}
    pool = None
    pending = None
    strs = []
    rows = []
    with open(sys.argv[1], "r", errors="replace") as fh:
        for line in fh:
            if "\t" not in line:
                continue
            # 行格式: "  addr:\t<机器码> \t<助记符>\t<操作数> \t// 注释"
            # ⚠️ 助记符与操作数之间**也是制表符**，必须拼接而不是只取一个字段
            parts = line.split("\t")
            insn = "\t".join(parts[2:]).strip() if len(parts) >= 3 else parts[-1].strip()
            m = RE_MOV.match(insn)
            if m:
                regs[m.group(1)] = int(m.group(2), 16)
                continue
            m = RE_ADRP.match(insn)
            if m:
                pending = int(m.group(1), 16) & ~0xFFF
                continue
            m = RE_ADD.match(insn)
            if m and pending is not None:
                pool = pending + int(m.group(1), 16)
                pending = None
                continue
            m = RE_STR.match(insn)
            if m:
                slot, reg = int(m.group(2)), m.group(1)
                val = 0 if reg == "zr" else regs.get(reg)
                if val is None:
                    continue
                strs.append((slot, val))
                if len(strs) > 6:
                    del strs[0]
                continue
            if "bl\t" in insn and RE_INNER.search(insn):
                pair = []
                for slot, val in reversed(strs):
                    if pair and slot == pair[0][0]:
                        continue
                    pair.append((slot, val))
                    if len(pair) == 2:
                        break
                if len(pair) == 2:
                    rows.append((pair[1][1], pair[0][1], pool))
                strs = []
    for outer, inner, p in rows:
        print("%d\t%d\t0x%x" % (outer, inner, p or 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
