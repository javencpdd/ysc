#!/bin/bash
D=/tmp/opt4
mkdir -p $D; rm -f $D/*
SRC="rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=100 ! rtph265depay ! h265parse"
ENC="mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"

echo "=== 可用编码器 / RGA 相关元素 ==="
gst-inspect-1.0 2>/dev/null | grep -iE 'enc:|rga|convert' | head -30
echo
echo "=== /dev/rga / rga 元素 ==="
ls -la /dev/rga 2>&1
gst-inspect-1.0 rgaconvert 2>&1 | head -3
gst-inspect-1.0 rkximageconvert 2>&1 | head -3
echo

cpu_of() { awk '{print $14+$15}' /proc/$1/stat 2>/dev/null; }
measure() {
    local name="$1"; shift
    gst-launch-1.0 -e $SRC "$@" >$D/$name.log 2>&1 &
    local pid=$!
    sleep 6; local t1; t1=$(cpu_of $pid)
    sleep 8; local t2; t2=$(cpu_of $pid)
    kill -TERM $pid 2>/dev/null; sleep 2; kill -KILL $pid 2>/dev/null
    local pct="-"; [ -n "$t1" ] && [ -n "$t2" ] && pct=$(awk -v a="$t1" -v b="$t2" 'BEGIN{printf "%.1f",(b-a)/100/8*100}')
    printf "%-30s CPU=%s%%\n" "$name" "$pct"
    grep -ciE 'critical|error|not-negotiated' $D/$name.log | sed 's/^/                               报错: /'
}

echo "=== A. 软解 H.265 + 快速 videoconvert + 硬编 H.264 ==="
measure A_swdec_conv_I420 ! queue ! avdec_h265 ! videoconvert ! video/x-raw,format=I420 ! $ENC ! h264parse ! matroskamux ! filesink location=$D/A.mkv

echo
echo "=== B. 硬解 + videoconvert I420（当前方案，对照）==="
measure B_hwdec_conv_I420 ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=I420 ! $ENC ! h264parse ! matroskamux ! filesink location=$D/B.mkv

echo
echo "=== C. 软解 H.265 + 软编 x264（全软，参照最低画质风险）==="
measure C_swdec_x264 ! queue ! avdec_h265 ! videoconvert ! video/x-raw,format=I420 ! x264enc speed-preset=ultrafast tune=zerolatency ! h264parse ! matroskamux ! filesink location=$D/C.mkv

echo
echo "=== 抽帧对比 ==="
for v in A B C; do
    [ -s $D/$v.mkv ] || { echo "$v: 无输出 ($(stat -c %s $D/$v.mkv 2>/dev/null) bytes)"; continue; }
    timeout 20 ffmpeg -y -v error -ss 3 -i $D/$v.mkv -frames:v 1 -pix_fmt rgb24 $D/${v}_f.png 2>/dev/null
    printf "%s: mkv=%s  frame=%s\n" "$v" "$(stat -c %s $D/$v.mkv)" "$(stat -c %s $D/${v}_f.png 2>/dev/null)"
done

echo
echo "=== 当前源画面（确认相机不是黑的）==="
rm -f $D/srcnow.png
timeout 20 ffmpeg -y -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video1 -frames:v 1 -pix_fmt rgb24 $D/srcnow.png 2>/dev/null
echo "源帧大小: $(stat -c %s $D/srcnow.png 2>/dev/null)"

rm -rf /home/user/frames7; mkdir -p /home/user/frames7; cp -f $D/*.png /home/user/frames7/ 2>/dev/null; chmod 644 /home/user/frames7/* 2>/dev/null
ls /home/user/frames7/
