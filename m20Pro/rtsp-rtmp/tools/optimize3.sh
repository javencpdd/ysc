#!/bin/bash
D=/tmp/opt3
mkdir -p $D; rm -f $D/*
SRC="rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=100 ! rtph265depay ! h265parse"

echo "=== videoconvert 是否有 n-threads 属性 ==="
gst-inspect-1.0 videoconvert 2>/dev/null | grep -iE 'n-threads|threads' | head -5
echo

cpu_of() { awk '{print $14+$15}' /proc/$1/stat 2>/dev/null; }

measure() {
    local name="$1"; shift
    gst-launch-1.0 -e $SRC "$@" >$D/$name.log 2>&1 &
    local pid=$!
    sleep 6
    local t1; t1=$(cpu_of $pid)
    sleep 8
    local t2; t2=$(cpu_of $pid)
    kill -TERM $pid 2>/dev/null; sleep 2; kill -KILL $pid 2>/dev/null
    local pct="-"
    [ -n "$t1" ] && [ -n "$t2" ] && pct=$(awk -v a="$t1" -v b="$t2" 'BEGIN{printf "%.1f",(b-a)/100/8*100}')
    printf "%-34s CPU=%s%%\n" "$name" "$pct"
    grep -ciE 'critical|error|not-negotiated' $D/$name.log | sed 's/^/                                   报错: /'
}

ENC="mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"

echo "=== 隔离 videoconvert 的开销 ==="
measure C1_dec_conv_I420_fake   ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=I420 ! fakesink sync=false
measure C2_dec_nv12_fake        ! queue ! mppvideodec ! video/x-raw,format=NV12 ! fakesink sync=false

echo
echo "=== 多线程 videoconvert 完整链路 ==="
measure C3_conv4_I420   ! queue ! mppvideodec ! videoconvert n-threads=4 ! video/x-raw,format=I420 ! $ENC ! h264parse ! matroskamux ! filesink location=$D/C3.mkv
measure C4_conv2_I420   ! queue ! mppvideodec ! videoconvert n-threads=2 ! video/x-raw,format=I420 ! $ENC ! h264parse ! matroskamux ! filesink location=$D/C4.mkv
measure C5_conv1_I420   ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=I420 ! $ENC ! h264parse ! matroskamux ! filesink location=$D/C5.mkv

echo
echo "=== 抽帧验证 C3/C4/C5 ==="
for v in C3 C4 C5; do
    [ -s $D/$v.mkv ] || { echo "$v: 无输出"; continue; }
    timeout 20 ffmpeg -y -v error -sseof -2 -i $D/$v.mkv -frames:v 1 -pix_fmt rgb24 $D/$v.png 2>/dev/null
    echo "$v: mkv=$(stat -c %s $D/$v.mkv) png=$(stat -c %s $D/$v.png 2>/dev/null)"
    timeout 15 ffprobe -v error -show_entries stream=nb_frames,avg_frame_rate,bit_rate -of csv=p=0 $D/$v.mkv 2>/dev/null | head -1
done
rm -rf /home/user/frames6; mkdir -p /home/user/frames6; cp -f $D/*.png /home/user/frames6/ 2>/dev/null; chmod 644 /home/user/frames6/* 2>/dev/null
