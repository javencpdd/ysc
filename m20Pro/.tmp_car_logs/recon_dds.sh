#!/bin/bash
# 只读侦察脚本（2026-10-15 会话）：DDS 拓扑 / SDK 服务 / rl_deploy 线索
# 不改动任何状态；只读命令 + grep

echo "===== [0] 时间与 uptime ====="
date
uptime

echo "===== [1] 控制台 control status ====="
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/control/status
echo
echo "===== [2] 控制台 state ====="
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/state | head -c 2500
echo
echo "===== [3] 控制台 status ====="
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/status | head -c 2500
echo

echo "===== [4] ROS 环境探测 ====="
source /opt/ros/foxy/setup.bash 2>/dev/null
command -v ros2 && echo "ros2 found" || echo "ros2 NOT in PATH"

echo "===== [5] ROS 节点列表 ====="
timeout 12 ros2 node list 2>&1 | head -40

echo "===== [6] /STEER topic info -v ====="
timeout 12 ros2 topic info -v /STEER 2>&1 | head -90

echo "===== [7] /REAL_STEER topic info -v ====="
timeout 12 ros2 topic info -v /REAL_STEER 2>&1 | head -90

echo "===== [8] /HANDLE_STEER topic info -v ====="
timeout 12 ros2 topic info -v /HANDLE_STEER 2>&1 | head -90

echo "===== [9] /MOTION_INFO topic info -v ====="
timeout 12 ros2 topic info -v /MOTION_INFO 2>&1 | head -60

echo "===== [10] SDK/LIO 服务 ====="
timeout 12 ros2 service list -t 2>&1 | grep -iE "sdk|lio" 

echo "===== [11] rl_deploy strings (SDK) ====="
RL=/opt/robot/share/rl_deploy/bin/rl_deploy
ls -la "$RL" 2>/dev/null
strings -n 6 "$RL" 2>/dev/null | grep -i "sdk" | sort -u | head -50

echo "===== [12] rl_deploy strings (STEER 话题) ====="
strings -n 5 "$RL" 2>/dev/null | grep -E "STEER" | sort -u | head -30

echo "===== [13] basic_server 30000 监听 ====="
ss -ulnp 2>/dev/null | grep 30000

echo "===== [14] 日志目录 ====="
ls -lt /var/opt/robot/log/ 2>/dev/null | head -12
ls -t /var/opt/robot/log/*/Basic_server*.log 2>/dev/null | head -3

echo "===== [15] 当前 /MOTION_INFO 采样（6s） ====="
timeout 6 ros2 topic echo /MOTION_INFO 2>&1 | head -50

echo "===== done ====="
