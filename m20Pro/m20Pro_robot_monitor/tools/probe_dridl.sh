#!/bin/bash
# 检查 dridl 消息定义 + 完整错误码表 dump
echo '=== 1. dridl 消息清单 ==='
ls /usr/local/include/dridl/dr_msgs/msg/ 2>/dev/null | head -80
echo
echo '=== 2. MotionStatusValue.h 字段 ==='
grep -nE 'typedef|::|private:|public:|_timeout|error|Error|imu|joint|odom' /usr/local/include/dridl/dr_msgs/msg/MotionStatusValue.h 2>/dev/null | head -60
echo
echo '=== 3. MotionStatus.h 字段 ==='
grep -nE 'typedef|private:|public:|_timeout|error|Error|imu|joint|odom' /usr/local/include/dridl/dr_msgs/msg/MotionStatus.h 2>/dev/null | head -60
echo
echo '=== 4. dridl 里搜 8017 / 0x80xx ==='
grep -rn '8017' /usr/local/include/dridl/ 2>/dev/null | head -10
grep -rln 'ErrorCode\|error_code' /usr/local/include/dridl/dr_msgs/msg/ 2>/dev/null | head -20
echo
echo '=== 5. dump 错误码表完整区域 ==='
python3 <<'PYEOF'
data = open('/opt/robot/share/basic_server/bin/basic_server','rb').read()
import struct
start = 0x24c900
chunk = data[start:start+0xC00]
# 以 8 字节 struct 解析
print('region @0x%x, %d bytes' % (start, len(chunk)))
for off in range(0, len(chunk)-7, 8):
    code, val = struct.unpack_from('<II', chunk, off)
    if 0x8000 <= code <= 0x9000:
        print('  @0x%x  0x%04X (%d) -> %d' % (start+off, code, code, val))
PYEOF
echo
echo '=== 6. rl_deploy change_log 搜 imu/超时 ==='
grep -n -iE 'imu|超时|8017|timeout' /opt/robot/share/rl_deploy/change_log.md 2>/dev/null | head -40
echo
echo '=== 7. basic_server strings 搜中文错误名 ==='
strings -a /opt/robot/share/basic_server/bin/basic_server 2>/dev/null | grep -E '编码器|姿态|电机|关节|电池|超时|断开|通信' | head -40
