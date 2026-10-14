#!/bin/bash
echo '=== 1. msg 目录完整清单（后半段） ==='
ls /usr/local/include/dridl/dr_msgs/msg/ 2>/dev/null | grep -v CdrAux | grep -v PubSubTypes | tail -70
echo
echo '=== 2. InputStatusValue.h 字段 ==='
grep -oE 'eProsima_user_DllExport (void|uint32_t|float|double|[a-zA-Z_]+) [a-z_0-9]+\(\)' /usr/local/include/dridl/dr_msgs/msg/InputStatusValue.h 2>/dev/null | sed 's/eProsima_user_DllExport //' | sort -u | head -40
echo
echo '=== 3. 哪些消息定义里有 timeout 字段 ==='
grep -rln 'timeout' /usr/local/include/dridl/dr_msgs/msg/*.h 2>/dev/null | grep -v CdrAux | grep -v PubSub
grep -rn -i 'timeout' /usr/local/include/dridl/dr_msgs/msg/InputStatusValue.h 2>/dev/null | head -20
echo
echo '=== 4. basic_server 中 imu_timeout 字符串的上下文 ==='
strings -a -t x /opt/robot/share/basic_server/bin/basic_server 2>/dev/null | grep -B6 -A6 'imu_timeout'
echo
echo '=== 5. rl_deploy 二进制搜 imu/timeout ==='
strings -a /opt/robot/share/rl_deploy/bin/rl_deploy 2>/dev/null | grep -iE 'imu.*timeout|timeout.*imu|imu_timeout' | head -20
echo
echo '=== 6. rl_deploy conf/config ==='
ls /opt/robot/share/rl_deploy/conf/ /opt/robot/share/rl_deploy/config/ 2>/dev/null
echo
echo '=== 7. rl_deploy change_log 头部 ==='
head -30 /opt/robot/share/rl_deploy/change_log.md 2>/dev/null
