"""解析 CmdHandle::init 反汇编，自动提取全部指令注册表：
模拟寄存器传播（mov wN,#imm → str wN,[sp,#120/#124]），
在 std::function::operator=(0xf4ac0) 调用处收割 (outer,inner,handler) 事件。
"""
import re
import bisect

ASM = r'C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\init_full.asm'
NM  = r'C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\nm_sorted.txt'

lines = open(ASM, encoding='utf-8', errors='replace').read().splitlines()
reg = {}
outer = inner = None
pend_page = None
handler = None
events = []

for ln in lines:
    m = re.search(r'\bmov\s+w(\d+),\s*#(0x[0-9a-fA-F]+|\d+)', ln)
    if m:
        reg[int(m.group(1))] = int(m.group(2), 0)
        continue
    m = re.search(r'\bstr\s+w(\d+),\s*\[sp,\s*#(\d+)\]', ln)
    if m:
        r, off = int(m.group(1)), int(m.group(2))
        if off == 120:
            outer = reg.get(r)
        elif off == 124:
            inner = reg.get(r)
        continue
    m = re.search(r'\badrp\s+x2,\s*([0-9a-fA-F]+)', ln)
    if m:
        pend_page = int(m.group(1), 16)
        continue
    m = re.search(r'\badd\s+x2,\s*x2,\s*#(0x[0-9a-fA-F]+|\d+)', ln)
    if m and pend_page is not None:
        handler = pend_page + int(m.group(1), 0)
        pend_page = None
        continue
    m = re.search(r'\bbl\s+([0-9a-fA-F]+)\s+<', ln)
    if m:
        tgt = int(m.group(1), 16)
        if tgt == 0xf4ac0:          # std::function::operator=
            events.append((outer, inner, handler))
            handler = None
        continue

# nm 符号映射
syms = []
for l in open(NM, encoding='utf-8', errors='replace'):
    p = l.split()
    if len(p) >= 3:
        try:
            a = int(p[0], 16)
        except ValueError:
            continue
        syms.append((a, p[2]))
syms.sort()
addrs = [s[0] for s in syms]

def name_of(addr):
    if not addr:
        return '?'
    i = bisect.bisect_right(addrs, addr) - 1
    if i < 0:
        return '?'
    a, n = syms[i]
    d = addr - a
    return n if d == 0 else '%s+%#x' % (n, d)

print('total events:', len(events))
for o, i, h in events:
    print('outer=%-6s inner=%-6s  handler=%#010x  %s'
          % (o, i, h if h else 0, name_of(h)))
