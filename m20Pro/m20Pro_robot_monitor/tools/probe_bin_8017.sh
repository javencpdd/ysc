#!/bin/bash
# 二进制级搜索 0x8017 + 查找 drdds 消息定义
echo '=== 1. basic_server 二进制中搜 0x8017 字节序列 ==='
python3 <<'PYEOF'
data = open('/opt/robot/share/basic_server/bin/basic_server','rb').read()
print('binary size:', len(data))
import re
for pat, name in [(b'\x17\x80\x00\x00', 'u32-le'), (b'\x00\x00\x80\x17', 'u32-be')]:
    hits = [m.start() for m in re.finditer(re.escape(pat), data)]
    print('%s pattern %s: %d hits' % (name, pat.hex(), len(hits)))
    for h in hits[:30]:
        print('  @0x%x: %s' % (h, repr(data[max(0,h-56):h+56])))
PYEOF
echo
echo '=== 2. 全盘 find drdds / MotionStatus 定义 ==='
find /opt/robot /usr/include /usr/local -iname '*drdds*' 2>/dev/null | head -20
find /opt/robot /usr/include /usr/local -iname '*MotionStatus*' 2>/dev/null | head -20
find /opt/robot /usr/include /usr/local -iname '*InputStatus*' 2>/dev/null | head -10
echo
echo '=== 3. rl_deploy 目录与日志 ==='
ls /opt/robot/share/rl_deploy/ /opt/robot/share/rl_deploy/bin/ 2>/dev/null
[ -f /opt/robot/share/rl_deploy/change_log.md ] && grep -n -iE 'imu|error' /opt/robot/share/rl_deploy/change_log.md | head -30
echo
echo '=== 4. 搜 lib 中的 drdds 库 ==='
ls /opt/robot/lib/ 2>/dev/null | head -30
