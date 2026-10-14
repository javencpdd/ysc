#!/usr/bin/env python3
"""解析 rl_deploy 中 PLT 桩 → 导入符号名。

用法: python pltsym.py 0x9f210 0x9e1a0 ...
对每个地址：反汇编前几条，若为 PLT 跳转桩（adrp x16 + ldr x17 + br x17），
通过 .rela.plt 反查 GOT 地址 → 符号名；否则打印该地址处反汇编。
"""
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from elftools.elf.elffile import ELFFile

BIN = r"C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\rl_deploy.bin"

md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)


def load_relocs():
    f = open(BIN, "rb")
    elf = ELFFile(f)
    relocs = {}
    for secname in (".rela.plt", ".rela.dyn"):
        sec = elf.get_section_by_name(secname)
        if sec is None:
            continue
        symtab = elf.get_section(sec["sh_link"])
        for r in sec.iter_relocations():
            s = symtab.get_symbol(r["r_info_sym"])
            relocs[r["r_offset"]] = s.name or ("<sym%d>" % r["r_info_sym"])
    return relocs


def near_symbols():
    """把 .symtab 全部载入，便于找最近前向符号"""
    import bisect
    global NEAR_KEYS, NEAR_VALS
    with open(BIN, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".symtab")
        rows = []
        for s in symtab.iter_symbols():
            if s["st_value"]:
                rows.append((s["st_value"], s.name))
    rows.sort()
    NEAR_KEYS = [r[0] for r in rows]
    NEAR_VALS = [r[1] for r in rows]


def near(addr):
    import bisect
    i = bisect.bisect_right(NEAR_KEYS, addr) - 1
    if i < 0:
        return None
    return NEAR_VALS[i], addr - NEAR_KEYS[i]


def main():
    relocs = load_relocs()
    near_symbols()
    data = open(BIN, "rb").read()
    for arg in sys.argv[1:]:
        addr = int(arg, 16)
        print("== %s ==" % arg)
        # 先按 PLT 解析
        code = data[addr:addr + 32]
        insns = list(md.disasm(code, addr))
        # PLT 模式: adrp x16, page; ldr x17, [x16, #off]; ...; br x17
        got = None
        have_br = False
        page = None
        for insn in insns[:6]:
            if insn.mnemonic == "adrp" and "x16" in insn.op_str:
                page = int(insn.op_str.split(",")[1].strip().lstrip("#"), 16)
            if insn.mnemonic == "ldr" and "x17, [x16" in insn.op_str:
                off = insn.op_str.split("#")[-1].rstrip("]")
                got = page + int(off, 16)
            if insn.mnemonic == "br" and "x17" in insn.op_str:
                have_br = True
        if got is not None and got in relocs:
            print("   -> PLT import: %s" % relocs[got])
            continue
        # 否则尝试最近符号
        ns = near(addr)
        if ns and ns[1] < 0x800:
            print("   -> near symbol: %s (+0x%x)" % ns)
        else:
            print("   -> (no PLT reloc) 反汇编:")
            for insn in insns[:6]:
                print("      %x:\t%s\t%s" % (insn.address, insn.mnemonic, insn.op_str))


if __name__ == "__main__":
    main()
