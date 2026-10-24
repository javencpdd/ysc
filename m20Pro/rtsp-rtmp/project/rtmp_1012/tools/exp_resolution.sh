#!/bin/bash
# exp_resolution.sh —— 相机标准模式帧率实验（2026-10-19）
# 依次测 640x480 / 848x480 / 1280x720，最后恢复 800x600
PW="'"
TARGET=/opt/robot/scripts/board_resources/rtsp_service/push_video.sh

set_res() {
  sed -i "s/DEV_WIDTH=[0-9]*/DEV_WIDTH=$1/; s/DEV_HEIGHT=[0-9]*/DEV_HEIGHT=$2/" "$TARGET"
  grep -E '^DEV_WIDTH=|^DEV_HEIGHT=' "$TARGET" | tr '\n' ' '
  echo ""
}

measure() {
  local w=$1 h=$2
  echo "===== ${w}x${h} ====="
  set_res "$w" "$h"
  printf "%s\n" "$PW" | sudo -S bash /home/user/rtmp_1012/patch/restart_camera.sh >/dev/null 2>&1
  sleep 5
  for v in video1 video2; do
    timeout -s INT 14 ffmpeg -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/$v -c copy -t 10 -y /tmp/e_$v.mp4 2>/dev/null
    if [ -s /tmp/e_$v.mp4 ]; then
      local n=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/e_$v.mp4 2>/dev/null | wc -l)
      local sz=$(ls -la /tmp/e_$v.mp4 | awk '{print $5}')
      echo "  $v: 帧数=$n/10s  码率=$((sz/10/1024))KB/s"
      echo "  间隔分布 top5:"
      ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/e_$v.mp4 | awk 'NR>1{printf "%.4f\n", $1-p} {p=$1}' | sort -n | uniq -c | sort -rn | head -5 | sed 's/^/    /'
    else
      echo "  $v: 起流失败"
    fi
    rm -f /tmp/e_$v.mp4
  done
  echo ""
}

measure 640 480
measure 848 480
measure 1280 720

echo "===== 恢复 800x600 ====="
set_res 800 600
printf "%s\n" "$PW" | sudo -S bash /home/user/rtmp_1012/patch/restart_camera.sh 2>&1 | grep -E 'HLS|采集进程数'
