#!/bin/bash
# probe2_after_test.sh — 第二轮只读取证：rl_deploy 日志 + VelControl 配置溯源
echo "=== [1] rl_deploy 日志大小与测试时段摘录（01:32-01:35） ==="
RL=/var/opt/robot/log/2026_1015/rl_deploy.2026_1015.log
wc -c "$RL"
grep -nE "01:3[2-5]" "$RL" | head -80
echo
echo "=== [2] rl_deploy 关键词扫描 ==="
grep -niE "steer|sdk|gait|motion state|state=" "$RL" | tail -60
echo
echo "=== [3] Basic_server 日志 01:23-01:36 全摘 ==="
BS=/var/opt/robot/log/2026_1015/Basic_server.2026_1015.log
grep -nE "01:2[3-9]|01:3[0-6]" "$BS" | head -120
echo
echo "=== [4] 控制台 audit 最近 40 条 ==="
curl -s "http://127.0.0.1:8080/api/v1/control/audit?limit=40" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for it in (d.get('items') or [])[-40:]:
    print(it)
"
echo
echo "=== [5] MotionInfo 消息定义 ==="
find /usr/local/include -name "MotionInfo.h" 2>/dev/null
MF=$(find /usr/local/include -name "MotionInfo.h" 2>/dev/null | head -1)
if [ -n "$MF" ]; then grep -nE "(float|double|int32|uint32|int64|uint64|bool) [a-z_0-9]+_" "$MF" | head -40; fi
echo
echo "=== [6] VelControl / 速度相关配置文件搜索 ==="
ls -l /opt/robot/share/basic_server/conf/ 2>/dev/null
find /userdata /opt/robot /home/djw /etc -maxdepth 4 \( -iname "*veloc*" -o -iname "*steer*" -o -iname "*speed*" \) 2>/dev/null | head -20
echo
echo "=== [7] 最新保存的 TOML（按修改时间） ==="
find /userdata /opt/robot -name "*.toml" -newermt "2024-06-20" 2>/dev/null | head -20
echo
echo "=== [8] basic_server 配置内容抽查 ==="
cat /opt/robot/share/basic_server/conf/basic_server.toml 2>/dev/null | head -60
