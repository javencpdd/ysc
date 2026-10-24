#!/bin/bash
# verify_ae_fix.sh —— 曝光修复效果验证
echo "=== 1. 相机采集进程（应含 extra-controls） ==="
pgrep -af 'gst' | grep -v 'bash -c' | grep -v 'rtmp-gst' | cut -c1-300

echo ""
echo "=== 2. 当前曝光控制值 ==="
v4l2-ctl -d /dev/video0 -L 2>/dev/null | grep -A4 'exposure'

echo ""
echo "=== 3. 源流帧间隔分布（10s，期望集中 0.032） ==="
timeout -s INT 14 ffmpeg -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video1 -c copy -t 10 -y /tmp/v1.mp4 2>/dev/null
echo -n "  总帧数: "; ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v1.mp4 2>/dev/null | wc -l
echo "  间隔分布 top8:"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v1.mp4 | awk 'NR>1{printf "%.4f\n", $1-p} {p=$1}' | sort -n | uniq -c | sort -rn | head -8 | sed 's/^/    /'
echo "  关键帧时间戳:"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 /tmp/v1.mp4 | grep K | head -6 | sed 's/^/    /'
rm -f /tmp/v1.mp4

echo ""
echo "=== 4. relay 状态 ==="
m20-video-ctl status 2>/dev/null | head -8

echo ""
echo "=== 5. HLS ==="
for p in video1 video2; do
  printf "  %-8s HLS=%s\n" "$p" "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8888/$p/index.m3u8)"
done
