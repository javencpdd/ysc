#!/bin/bash
# 检查源流与相机服务现状（避免命令行走势被误杀，统一用脚本文件执行）
echo "=== 源流 ==="
for p in video1 video2; do
  printf '%s: ' "$p"
  curl -s -o /dev/null -m 5 -w '%{http_code}\n' "http://127.0.0.1:8888/$p/index.m3u8"
done
echo
echo "=== 相机采集进程 ==="
pgrep -af 'gst-launch-1.0' | cut -c1-80
echo
echo "=== 相关脚本进程 ==="
pgrep -af 'rtsp_service' | cut -c1-80
echo
echo "=== basic_server 是什么 ==="
file /opt/robot/share/basic_server/bin/basic_server 2>&1 | cut -c1-160
pgrep -af basic_server | head -3
echo
echo "=== basic_server 中与脚本相关的字符串 ==="
strings -a /opt/robot/share/basic_server/bin/basic_server 2>/dev/null \
  | grep -iE 'restart\.sh|stop\.sh|start_server|rtsp_service|push_video|pkill|v4l2' | sort -u | head -20
