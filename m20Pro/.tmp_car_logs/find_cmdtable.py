"""在 basic_server 二进制中定位 cmdInfo_t 分发表：
搜索各 cmdHandle_* 函数地址在数据段中的引用（8 字节小端指针），
并打印引用点上下文 hex，用于反推每条指令的 (Type, Command) 编码。
"""
import struct

P = '/opt/robot/share/basic_server/bin/basic_server'
d = open(P, 'rb').read()
print('file size:', len(d))

def find_all(va):
    needle = struct.pack('<Q', va)
    out = []
    i = d.find(needle)
    while i != -1 and len(out) < 40:
        out.append(i)
        i = d.find(needle, i + 1)
    return out

# 需要定位的 handler（nm 得到）与已知参照
targets = [
    ('EnableSDK', 0x0d8be0),
    ('RealSteer', 0x0d2a68),
    ('Steer',     0x0d2430),
    ('Motion',    0x0d30b0),
    ('Gait',      0x0d3640),
    ('HeartBeat', 0x0d20f0),
]

for name, va in targets:
    refs = find_all(va)
    print('==', name, hex(va), 'n_refs:', len(refs))
    for q in refs[:6]:
        lo = max(0, q - 96)
        hi = min(len(d), q + 96)
        print('   ctx@file+%#x:' % q, d[lo:hi].hex())
print('DONE')
