#!/bin/bash
# verify_fps.sh —— 曝光修复后帧率/GOP/码率验证
echo "=== 1. video1 帧间隔分布（10s） ==="
timeout -s INT 14 ffmpeg -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video1 -c copy -t 10 -y /tmp/v1.mp4 2>/dev/null
echo -n "  总帧数: "; ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v1.mp4 2>/dev/null | wc -l
echo "  间隔分布 top8:"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v1.mp4 | awk 'NR>1{printf "%.4f\n", $1-p} {p=$1}' | sort -n | uniq -c | sort -rn | head -8 | sed 's/^/    /'
echo "  关键帧时间戳（GOP 间隔）:"
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,flags -of csv=p=0 /tmp/v1.mp4 | grep K | head -6 | sed 's/^/    /'
echo -n "  文件大小: "; ls -la /tmp/v1.mp4 | awk '{print $5, "bytes ->", $5/10/1024, "KB/s"}'
rm -f /tmp/v1.mp4

echo ""
echo "=== 2. video2 帧间隔分布（10s） ==="
timeout -s INT 14 ffmpeg -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video2 -c copy -t 10 -y /tmp/v2.mp4 2>/dev/null
echo -n "  总帧数: "; ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v2.mp4 2>/dev/null | wc -l
ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/v2.mp4 | awk 'NR>1{printf "%.4f\n", $1-p} {p=$1}' | sort -n | uniq -c | sort -rn | head -5 | sed 's/^/    /'
rm -f /tmp/v2.mp4

echo ""
echo "=== 3. relay 与外推 ==="
m20-video-ctl status 2>/dev/null | head -8
pgrep -af rtmp-gst | grep -v 'bash -c' | wc -l | sed 's/^/  relay 进程数: /'
ss -tn state established '( dport = :1936 )' 2>/dev/null | tail -n +2 | wc -l | sed 's/^/  1936 ESTAB: /'
