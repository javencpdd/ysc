"""dump cmdHandle_RealSteer 引用的 6 个 JSON 字段名 + EnableSDK 再次确认。"""
P = '/opt/robot/share/basic_server/bin/basic_server'
d = open(P, 'rb').read()

def cstr(va, maxlen=64):
    chunk = d[va:va + maxlen]
    return chunk.split(b'\x00')[0].decode('utf-8', errors='replace')

print('--- cmdHandle_RealSteer 字段（6 个 double）---')
for va in [0x24d8e8, 0x24db18, 0x243be8, 0x22eb50, 0x22eb58, 0x22eb60]:
    print('%#x  %r' % (va, cstr(va)))

print('--- cmdHandle_EnableSDK 字段（复查）---')
for va in [0x232a58, 0x232ac8, 0x232a60, 0x232a72]:
    print('%#x  %r' % (va, cstr(va)))

print('--- cmdHandle_Steer(2/21) 对照：找它引用的字符串 ---')
# 从 objdump 已知 Steer 从 0xd2430 起，先给个占位：仅验证 SDKMode 附近
for va in [0x232a50, 0x232a90]:
    print('%#x  %r' % (va, cstr(va)))
