#!/bin/bash
BS=/var/opt/robot/log/2026_1015/Basic_server.2026_1015.log
RL=/var/opt/robot/log/2026_1015/rl_deploy.2026_1015.log
echo '=== 1. Basic_server 日志尾部 50 行 ==='
tail -50 $BS
echo
echo '=== 2. rl_deploy 日志尾部 40 行 ==='
tail -40 $RL
echo
echo '=== 3. IMU 超时 出现次数统计（Basic_server） ==='
grep -c 'IMU 超时' $BS
echo '--- rl_deploy IMU超时统计 ---'
grep -c 'IMU数据更新超时' $RL
echo
echo '=== 4. ExceptionHandle 前后完整上下文（首次出现的 20 行） ==='
grep -n -B3 -A6 'ExceptionHandle' $BS | head -80
echo
echo '=== 5. Basic_server 日志中所有非 IMU 的错误/上报 ==='
grep -nE '\[ERROR|\[WARN' $BS | grep -v 'IMU 超时' | head -30
