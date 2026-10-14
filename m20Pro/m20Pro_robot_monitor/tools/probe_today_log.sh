#!/bin/bash
echo '=== 1. 今天日志目录 2026_1015 ==='
ls -la /var/opt/robot/log/2026_1015/ 2>/dev/null
echo
echo '=== 2. 搜今天的 IMU 相关日志 ==='
for f in /var/opt/robot/log/2026_1015/*.log; do
  echo "--- $f ---"
  grep -in 'imu' "$f" 2>/dev/null | tail -25
done
echo
echo '=== 3. 搜今天的 8017 / 32791 / 超时 ==='
grep -rn -E '8017|32791' /var/opt/robot/log/2026_1015/ 2>/dev/null | tail -30
echo '---timeout---'
grep -rn -iE 'timeout|超时' /var/opt/robot/log/2026_1015/ 2>/dev/null | tail -40
echo
echo '=== 4. rl_deploy 今天日志的头部与 IMU 检测打印 ==='
ls /var/opt/robot/log/2026_1015/ | grep -i rl_deploy
grep -inE 'IsImu|imu.*flag|imu.*timeout|timeout.*imu' /var/opt/robot/log/2026_1015/rl_deploy* 2>/dev/null | tail -30
