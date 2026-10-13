#!/bin/bash
# 精确测 CPU + 中段抽帧，找出"画面正确且最省 CPU"的路径
D=/tmp/opt2
mkdir -p $D; rm -f $D/*
SRC="rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=100 ! rtph265depay ! h265parse"
ENC="mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"

# 用 /proc/PID/stat 的 utime+stime 增量算 CPU（单位: jiffies, HZ=100）
cpu_of() {
    awk '{print $14+$15}' /proc/$1/stat 2>/dev/null
}

measure() {
    local name="$1"; shift
    local out=$D/$name.mkv
    gst-launch-1.0 -e $SRC "$@" ! $ENC ! h264parse ! matroskamux ! filesink location=$out >$D/$name.log 2>&1 &
    local pid=$!
    sleep 6
    local t1; t1=$(cpu_of $pid)
    sleep 8
    local t2; t2=$(cpu_of $pid)
    kill -TERM $pid 2>/dev/null; sleep 2; kill -KILL $pid 2>/dev/null
    local pct="-"
    if [ -n "$t1" ] && [ -n "$t2" ]; then
        pct=$(awk -v a="$t1" -v b="$t2" 'BEGIN{printf "%.1f", (b-a)/100/8*100}')
    fi
    # 抽中段帧
    timeout 20 ffmpeg -y -v error -sseof -2 -i "$out" -frames:v 1 -pix_fmt rgb24 $D/$name.png 2>/dev/null
    local png=$(stat -c %s $D/$name.png 2>/dev/null || echo 0)
    printf "%-28s CPU=%-7s 帧=%s bytes\n" "$name" "$pct%" "$png"
}

echo "=== 各路径 CPU 与出帧对比 ==="
measure V1_conv_I420      ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=I420
measure V2_dec_I420       ! queue ! mppvideodec ! video/x-raw,format=I420
measure V3_nv12           ! queue ! mppvideodec
measure V4_afbc           ! queue ! mppvideodec arm-afbc=true ! video/x-raw,format=NV12
measure V5_conv_YV12      ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=YV12

echo
echo "=== 抽帧汇总 ==="
ls -la $D/*.png 2>/dev/null
rm -rf /home/user/frames5; mkdir -p /home/user/frames5
cp -f $D/*.png /home/user/frames5/ 2>/dev/null; chmod 644 /home/user/frames5/* 2>/dev/null
echo "已导出到 /home/user/frames5/"
