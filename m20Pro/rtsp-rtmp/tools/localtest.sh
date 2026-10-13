#!/bin/bash
# 本地对照实验：同一管线推本机 mediamtx，用于排除外网因素
# 输出: /tmp/localtest.log   PID: /tmp/localtest.pid
PIPE_TARGET="${1:-rtmp://127.0.0.1:1935/localtest}"
LOG=/tmp/localtest.log
: > "$LOG"
setsid taskset -c 0,1 gst-launch-1.0 -e \
  rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=200 drop-on-latency=true \
  ! rtph265depay ! h265parse \
  ! queue max-size-buffers=8 leaky=downstream \
  ! mppvideodec ! videoconvert ! video/x-raw,format=NV12 \
  ! mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr \
  ! h264parse config-interval=-1 \
  ! flvmux streamable=true \
  ! queue max-size-buffers=8 leaky=downstream \
  ! rtmpsink "location=$PIPE_TARGET live=1" \
  > "$LOG" 2>&1 < /dev/null &
echo $! > /tmp/localtest.pid
sleep 2
echo "started pid=$(cat /tmp/localtest.pid) target=$PIPE_TARGET"
