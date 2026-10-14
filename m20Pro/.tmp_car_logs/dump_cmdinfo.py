"""解码 EnableSDK cmdInfo 对象周边 4KB：按 8 字节小端逐项打印，
标注 <CODE-PTR>（落入 cmdHandle 代码区）与小整数，寻找 type/command 字段规律。"""
import struct

P = '/opt/robot/share/basic_server/bin/basic_server'
d = open(P, 'rb').read()

ref = 0x314898           # EnableSDK 指针出现处（file offset）
base = ref - 0x800
end = ref + 0x800
for off in range(base, end, 8):
    v = struct.unpack_from('<Q', d, off)[0]
    tag = ''
    if 0x0c0000 <= v <= 0x0e8000:
        tag = '<CODE-PTR>'
    elif v < 0x10000:
        tag = 'small'
    print('%#x  %#018x  %s' % (off, v, tag))
