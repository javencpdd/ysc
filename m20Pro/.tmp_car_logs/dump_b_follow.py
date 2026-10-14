"""dump 表条目中 B 指针指向的内容（字符串或函数），以及各条目 24B 全量解析。"""
import struct

P = '/opt/robot/share/basic_server/bin/basic_server'
d = open(P, 'rb').read()

# B 列指针（从 dump_cmdinfo 输出挑出的样本 + EnableSDK 邻域）
targets = [0x228378, 0x244b40, 0x1a25e8, 0x233ef8, 0x2d61d0, 0x2d61f0,
           0x2c7868, 0x241b28, 0x196b48, 0x174f48, 0x1e4120, 0x170a98,
           0x170ef8, 0x12d550, 0x1adfc0, 0x165f00, 0x121d28, 0x1d8020]
for va in targets:
    chunk = d[va:va + 72]
    printable = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
    print('%#x: %s' % (va, printable))

print('=== raw 24B entries around EnableSDK (0x3147e8..0x314900) ===')
for off in range(0x3147e8, 0x314908, 24):
    tag, ptr, val = struct.unpack_from('<QQQ', d, off)
    ptr_desc = ''
    if 0x0c0000 <= ptr <= 0x0e8000:
        ptr_desc = 'code:0x%x' % ptr
    elif ptr != 0:
        ptr_desc = 'data:0x%x' % ptr
    print('%#x  tag=%#018x  ptr=%s  val=%#x (%d)' % (off, tag, ptr_desc, val, val))
