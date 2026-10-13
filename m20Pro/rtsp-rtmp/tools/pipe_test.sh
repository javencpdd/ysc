#!/bin/bash
# 直接手动执行脚本构建的同一条管道，看看为什么不推流
GSTBIN=/home/user/rtmp_1012/bin/rtmp-gst
echo "=== 副本是否可用 ==="
ls -la "$GSTBIN"
"$GSTBIN" --version 2>&1 | head -3
echo "rc=$?"
echo
echo "=== 直接跑管道 15 秒 (不套 taskset) ==="
timeout 15 "$GSTBIN" -e \
  rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=100 \
  ! rtph265depay ! h265parse \
  ! queue \
  ! mppvideodec ! videoconvert ! video/x-raw,format=NV12 \
  ! mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr \
  ! h264parse config-interval=-1 \
  ! flvmux streamable=true \
  ! queue \
  ! rtmpsink "location=rtmp://172.31.68.227:1936/live/m20pro-f live=1" \
  2>&1 | head -30
echo "pipeline rc=${PIPESTATUS[0]}"
