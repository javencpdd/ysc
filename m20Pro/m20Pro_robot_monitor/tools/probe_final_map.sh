#!/bin/bash
echo '=== 1. basic_server 字符串池完整区域（0x24c400-0x24c620） ==='
python3 <<'PYEOF'
data = open('/opt/robot/share/basic_server/bin/basic_server','rb').read()
chunk = data[0x24c380:0x24c680]
# 提取可打印字符串及其偏移
import re
for m in re.finditer(rb'[\x20-\x7e]{4,}', chunk):
    print('  0x%x: %s' % (0x24c380+m.start(), m.group().decode()))
PYEOF
echo
echo '=== 2. rl_deploy SafeController 方法 / imu 符号 ==='
strings -a /opt/robot/share/rl_deploy/bin/rl_deploy 2>/dev/null | grep -E 'SafeController|IsImu|IsJoint|Timeout|timeout' | sort -u | head -50
echo
echo '=== 3. rl_deploy 二进制搜 0x8017 / 0x8016 u32-le ==='
python3 <<'PYEOF'
data = open('/opt/robot/share/rl_deploy/bin/rl_deploy','rb').read()
import re
for pat, name in [(b'\x17\x80\x00\x00','0x8017'), (b'\x16\x80\x00\x00','0x8016'), (b'\x29\x80\x00\x00','0x8029')]:
    hits = [m.start() for m in re.finditer(re.escape(pat), data)]
    print('%s u32le hits: %d' % (name, len(hits)))
    for h in hits[:10]:
        print('  @0x%x: %s' % (h, repr(data[max(0,h-40):h+40])))
PYEOF
echo
echo '=== 4. 日志目录 ==='
ls -lt /var/opt/robot/log/ 2>/dev/null | head -15
find /var/opt/robot/log /opt/robot/log /home/user/log -maxdepth 3 -name '*.log' 2>/dev/null | head -20
echo
echo '=== 5. basic_server 日志配置 ==='
cat /opt/robot/share/basic_server/conf/log/log.properties 2>/dev/null | head -30
