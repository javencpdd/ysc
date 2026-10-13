#!/bin/bash
# 在"画面正确"的前提下找最省 CPU 的转码路径
D=/tmp/opt
mkdir -p $D; rm -f $D/*
SRC="rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=100 ! rtph265depay ! h265parse"
ENC="mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"

echo "=== mppvideodec 全部属性（找 afbc / 输出格式控制）==="
gst-inspect-1.0 mppvideodec 2>/dev/null | sed -n '/Element Properties/,$p' | grep -E '^\s{2}[a-z-]+ +:' | head -20
echo

run_case() {
    local name="$1"; shift
    echo "--- $name ---"
    timeout 22 gst-launch-1.0 -e $SRC "$@" ! $ENC ! h264parse ! matroskamux ! filesink location=$D/$name.mkv >$D/$name.log 2>&1 &
    local pid=$!
    sleep 14
    local cpu=$(ps -o %cpu= -p $pid 2>/dev/null | tr -d ' ')
    echo "  CPU=${cpu:-?}%"
    wait $pid 2>/dev/null
    # 抽帧
    timeout 20 ffmpeg -y -v error -i $D/$name.mkv -frames:v 1 -pix_fmt rgb24 $D/${name}.png 2>/dev/null
    echo "  帧大小: $(stat -c %s $D/${name}.png 2>/dev/null)"
    grep -ciE 'critical|error' $D/$name.log | sed 's/^/  报错数: /'
}

run_case "P1_dec2I420_novidconv"  ! queue ! mppvideodec ! video/x-raw,format=I420
run_case "P2_afbc_nv12"           ! queue ! mppvideodec ! video/x-raw,format=NV12
run_case "P3_conv_I420"           ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=I420

echo
echo "=== P2 需要单独加 arm-afbc=true 重跑 ==="
timeout 22 gst-launch-1.0 -e $SRC ! queue ! mppvideodec ! video/x-raw,format=NV12 \
    ! mpph264enc arm-afbc=true rc-mode=1 bps=2000000 gop=30 header-mode=each-idr \
    ! h264parse ! matroskamux ! filesink location=$D/P2afbc.mkv >$D/P2afbc.log 2>&1 &
P=$!; sleep 14; echo "  P2afbc CPU=$(ps -o %cpu= -p $P 2>/dev/null | tr -d ' ')%"; wait $P 2>/dev/null
timeout 20 ffmpeg -y -v error -i $D/P2afbc.mkv -frames:v 1 -pix_fmt rgb24 $D/P2afbc.png 2>/dev/null
echo "  帧大小: $(stat -c %s $D/P2afbc.png 2>/dev/null)"

echo
echo "=== 汇总 ==="
ls -la $D/*.png 2>/dev/null
# 转到用户目录便于拉取
rm -rf /home/user/frames4; mkdir -p /home/user/frames4
cp -f $D/*.png /home/user/frames4/ 2>/dev/null; chmod 644 /home/user/frames4/* 2>/dev/null
ls /home/user/frames4/
