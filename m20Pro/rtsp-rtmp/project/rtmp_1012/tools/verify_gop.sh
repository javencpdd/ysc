#!/bin/bash
# verify_gop.sh —— GOP 优化效果验证
for v in video1 video2; do
  echo "===== $v ====="
  timeout -s INT 14 ffmpeg -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/$v -c copy -t 12 -y /tmp/g_$v.mp4 2>/dev/null
  echo -n "  帧数: "; ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/g_$v.mp4 2>/dev/null | wc -l
  echo "  关键帧时间戳（期望间隔 ~1.0s）:"
  ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 /tmp/g_$v.mp4 | grep K | head -6 | sed 's/^/    /'
  echo -n "  码率: "; ls -la /tmp/g_$v.mp4 | awk '{print $5/12/1024, "KB/s"}'
  rm -f /tmp/g_$v.mp4
done
echo "===== relay 与外推 ====="
m20-video-ctl status 2>/dev/null | head -8
ss -tn state established '( dport = :1936 )' 2>/dev/null | tail -n +2 | wc -l | sed 's/^/  1936 ESTAB: /'
