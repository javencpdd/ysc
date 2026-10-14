import struct
import sys

path = sys.argv[1] if len(sys.argv) > 1 else \
    r'C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\rl_deploy.bin'
data = open(path, 'rb').read()
print('file size', len(data))
e_phoff = struct.unpack_from('<Q', data, 0x20)[0]
e_phentsize = struct.unpack_from('<H', data, 0x36)[0]
e_phnum = struct.unpack_from('<H', data, 0x38)[0]
for i in range(e_phnum):
    off = e_phoff + i * e_phentsize
    p_type = struct.unpack_from('<I', data, off)[0]
    if p_type == 1:
        fl = struct.unpack_from('<I', data, off + 4)[0]
        po = struct.unpack_from('<Q', data, off + 8)[0]
        pv = struct.unpack_from('<Q', data, off + 16)[0]
        fs = struct.unpack_from('<Q', data, off + 32)[0]
        print('PT_LOAD vaddr=0x%x offset=0x%x filesz=0x%x flags=%d' % (pv, po, fs, fl))
