#!/bin/bash
# 扩大错误码表 dump + MotionStatusValue 完整字段 + IMU 消息定义
echo '=== 1. 扩大 dump：0x24c000-0x24d800 ==='
python3 <<'PYEOF'
data = open('/opt/robot/share/basic_server/bin/basic_server','rb').read()
import struct
start, end = 0x24c000, 0x24d800
print('region @0x%x-0x%x' % (start, end))
prev = None
for off in range(start, end-7, 8):
    code, val = struct.unpack_from('<II', data, off)
    if 0x8000 <= code <= 0x9999:
        print('  @0x%x  0x%04X (%5d) -> %d' % (off, code, code, val))
PYEOF
echo
echo '=== 2. MotionStatusValue.h 全部成员字段 ==='
grep -oE 'eProsima_user_DllExport (void|uint32_t|float|double|[a-zA-Z_]+) [a-z_0-9]+\(\)' /usr/local/include/dridl/dr_msgs/msg/MotionStatusValue.h 2>/dev/null | sed 's/eProsima_user_DllExport //' | sort -u | head -60
echo
echo '=== 3. MotionStatus.h 全部成员字段 ==='
grep -oE 'eProsima_user_DllExport (void|uint32_t|float|double|[a-zA-Z_]+) [a-z_0-9]+\(\)' /usr/local/include/dridl/dr_msgs/msg/MotionStatus.h 2>/dev/null | sed 's/eProsima_user_DllExport //' | sort -u | head -60
echo
echo '=== 4. ImuData.h 字段 ==='
grep -oE 'eProsima_user_DllExport (void|uint32_t|float|double|[a-zA-Z_]+) [a-z_0-9]+\(\)' /usr/local/include/dridl/dr_msgs/msg/ImuData.h 2>/dev/null | sed 's/eProsima_user_DllExport //' | sort -u | head -40
echo
echo '=== 5. 搜 0x8016 的 u32-le 出现 ==='
python3 <<'PYEOF'
data = open('/opt/robot/share/basic_server/bin/basic_server','rb').read()
import re
hits = [m.start() for m in re.finditer(re.escape(b'\x16\x80\x00\x00'), data)]
print('0x8016 u32le hits:', len(hits))
for h in hits[:15]:
    print('  @0x%x: %s' % (h, repr(data[max(0,h-48):h+48])))
PYEOF
