"""用已知 (type,command) 的指令校准数据表 tag 编码，然后解出 EnableSDK 的 Type。

已知参照（官方文档）：
  Motion           = 2/22      Gait      = 2/23      Charge    = 2/24
  HeartBeat        = 100/100   SetSleep  = 1101/6    GetSleepConfig = 1101/7
  ControlUsage     = 1101/5
"""
import struct

P = '/opt/robot/share/basic_server/bin/basic_server'
d = open(P, 'rb').read()

handlers = [
    ('Motion',         0x0d30b0, '2/22'),
    ('Gait',           0x0d3640, '2/23'),
    ('Charge',         0x0d39d8, '2/24'),
    ('HeartBeat',      0x0d20f0, '100/100'),
    ('ControlUsage',   0x0d4418, '1101/5'),
    ('SetSleep',       0x0db538, '1101/6'),
    ('GetSleepConfig', 0x0d0e38, '1101/7'),
    ('Steer',          0x0d2430, 'old?'),
    ('RealSteer',      0x0d2a68, 'new=2/21?'),
    ('EnableSDK',      0x0d8be0, '???'),
]

for name, va, known in handlers:
    needle = struct.pack('<Q', va)
    pos = []
    i = d.find(needle)
    while i != -1 and len(pos) < 5:
        pos.append(i)
        i = d.find(needle, i + 1)
    if not pos:
        print('%-14s NOT FOUND' % name)
        continue
    for i in pos:
        tag, ptr, val = struct.unpack_from('<QQQ', d, i - 8)
        hi, lo = tag >> 32, tag & 0xffffffff
        print('%-14s @%#x  tag=%#018x  hi=%#010x  lo=%#010x  val=%#x   [known: %s]'
              % (name, i, tag, hi, lo, val, known))
