#!/usr/bin/env python3
"""本地 aarch64 反汇编助手（v2）— M20 Pro 逆向工作区

支持 basic_server 与 rl_deploy 两个二进制；用 ELF 程序头做 VA→文件偏移映射。

用法:
  python disas.py <startVA_hex> <n_instructions> [--bin basic|rl]
  python disas.py <startVA_hex> --to <endVA_hex> [--bin basic|rl]
  python disas.py --find <hexbytes> [--bin basic|rl]
  python disas.py --str <text> [--bin basic|rl]        # 搜索字符串，打印地址
  python disas.py --callers <targetVA_hex> [--bin basic|rl]   # 扫描 BL/B 调用点
  python disas.py --symbols [pattern] [--bin basic|rl] # 需要 pyelftools
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

BASE = r"C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs"
BINS = {
    "basic": BASE + r"\basic_server",
    "rl": BASE + r"\rl_deploy.bin",
}


def load(which):
    with open(BINS[which], "rb") as f:
        return f.read()


def segments(data):
    """解析 ELF64 程序头，返回 [(vaddr, offset, filesz, flags), ...] (PT_LOAD)"""
    e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x36)[0]
    e_phnum = struct.unpack_from("<H", data, 0x38)[0]
    segs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        if p_type != 1:  # PT_LOAD
            continue
        p_flags = struct.unpack_from("<I", data, off + 4)[0]
        p_offset = struct.unpack_from("<Q", data, off + 8)[0]
        p_vaddr = struct.unpack_from("<Q", data, off + 16)[0]
        p_filesz = struct.unpack_from("<Q", data, off + 32)[0]
        segs.append((p_vaddr, p_offset, p_filesz, p_flags))
    return segs


def va2off(segs, va):
    for vaddr, offset, filesz, _ in segs:
        if vaddr <= va < vaddr + filesz:
            return offset + (va - vaddr)
    return None


def disas(which, start, count=None, end=None):
    data = load(which)
    segs = segments(data)
    off = va2off(segs, start)
    if off is None:
        print("!! VA 0x%x 不在任何 PT_LOAD 段内" % start)
        return
    if end is not None:
        code = data[off:off + (end - start)]
    else:
        code = data[off:off + count * 4]
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    n = 0
    for insn in md.disasm(code, start):
        print("  %x:\t%s\t%s" % (insn.address, insn.mnemonic, insn.op_str))
        n += 1
    print(";; %d instructions" % n)


def find_bytes(which, pat_hex):
    data = load(which)
    pat = bytes.fromhex(pat_hex)
    idx, hits = 0, []
    while True:
        i = data.find(pat, idx)
        if i < 0:
            break
        hits.append(i)
        idx = i + 1
    print("hits: %d" % len(hits))
    for h in hits[:80]:
        print("  off=0x%x" % h)


def find_str(which, text):
    data = load(which)
    pat = text.encode("utf-8")
    idx, hits = 0, []
    while True:
        i = data.find(pat, idx)
        if i < 0:
            break
        hits.append(i)
        idx = i + 1
    print("hits: %d" % len(hits))
    for h in hits[:80]:
        print("  va=0x%x" % h)


def callers(which, target):
    """扫描所有可执行段，找 BL/B 到 target 的地址（BL: 100101, B: 000101）"""
    data = load(which)
    segs = segments(data)
    out = []
    for vaddr, offset, filesz, flags in segs:
        if not (flags & 1):  # PF_X
            continue
        buf = data[offset:offset + filesz]
        n = len(buf) // 4
        words = struct.unpack("<%dI" % n, buf[:n * 4])
        for i, w in enumerate(words):
            if (w & 0xFC000000) == 0x94000000:  # BL
                imm = w & 0x03FFFFFF
                if imm & 0x02000000:
                    imm -= 0x04000000
                tgt = vaddr + i * 4 + imm * 4
                if tgt == target:
                    out.append(vaddr + i * 4)
    print("callers of 0x%x: %d" % (target, len(out)))
    for a in out:
        print("  0x%x" % a)


def symbols(which, pattern=None):
    from elftools.elf.elffile import ELFFile
    with open(BINS[which], "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".symtab")
        rows = []
        for s in symtab.iter_symbols():
            v = s["st_value"]
            if not v:
                continue
            name = s.name
            if pattern and pattern.lower() not in name.lower():
                continue
            t = s["st_info"]["type"]
            rows.append((v, t, name))
        rows.sort()
        for v, t, name in rows:
            print("%016x %s %s" % (v, t, name))
        print(";; %d symbols" % len(rows))


def main():
    a = sys.argv[1:]
    which = "basic"
    if "--bin" in a:
        i = a.index("--bin")
        which = a[i + 1]
        del a[i:i + 2]
    if a[0] == "--find":
        find_bytes(which, a[1])
    elif a[0] == "--str":
        find_str(which, a[1])
    elif a[0] == "--callers":
        callers(which, int(a[1], 16))
    elif a[0] == "--symbols":
        symbols(which, a[1] if len(a) > 1 else None)
    else:
        start = int(a[0], 16)
        if a[1] == "--to":
            disas(which, start, end=int(a[2], 16))
        else:
            disas(which, start, count=int(a[1]))


if __name__ == "__main__":
    main()
