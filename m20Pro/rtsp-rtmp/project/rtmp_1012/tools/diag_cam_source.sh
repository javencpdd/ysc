#!/bin/bash
# diag_cam_source.sh —— 排查采集进程真实来源
TARGET=/opt/robot/scripts/board_resources/rtsp_service/push_video.sh

echo "=== 1. TARGET 文件版本 ==="
md5sum "$TARGET"; echo -n "extra-controls count: "; grep -c extra-controls "$TARGET"

echo ""
echo "=== 2. 采集进程 2068/2074 启动时间与父链 ==="
ps -o pid,ppid,lstart,etimes,comm -p 2068,2074 2>/dev/null
for pid in 2068 2074; do
  [ -d /proc/$pid ] || continue
  ppid=$(awk '{print $4}' /proc/$pid/stat 2>/dev/null)
  echo "PID $pid <- PPID $ppid : $(tr '\0' ' ' < /proc/$ppid/cmdline 2>/dev/null | cut -c1-200)"
  gppid=$(awk '{print $4}' /proc/$ppid/stat 2>/dev/null)
  [ -n "$gppid" ] && echo "   <- PPID $gppid : $(tr '\0' ' ' < /proc/$gppid/cmdline 2>/dev/null | cut -c1-200)"
done

echo ""
echo "=== 3. 系统内所有 push_video 副本 ==="
find /opt/robot /usr/local /home -name 'push_video*' 2>/dev/null

echo ""
echo "=== 4. 当前所有 gst 采集进程完整命令行 ==="
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v 'rtmp-gst' | cut -c1-400

echo ""
echo "=== 5. camera_push.log 全文尾部 ==="
tail -40 /tmp/camera_push.log 2>/dev/null

echo ""
echo "=== 6. 可能的重拉者 ==="
ps -eo pid,lstart,cmd 2>/dev/null | grep -iE 'basic_server|start_server|restart\.sh|rtsp_service' | grep -v grep | cut -c1-180

echo ""
echo "=== 7. push_video 主脚本进程树 ==="
pgrep -af 'push_video' | grep -v 'bash -c' | cut -c1-160
