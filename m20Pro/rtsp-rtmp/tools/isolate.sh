#!/bin/bash
# 逐级抓帧，定位画质损坏发生在哪个元素
D=/tmp/iso
mkdir -p $D; rm -f $D/*.png $D/*.mkv

SRC="rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=100 ! rtph265depay ! h265parse"

echo "=== A. mppvideodec 解码后直接出 PNG（检查硬解输出）==="
timeout 18 gst-launch-1.0 -e $SRC ! mppvideodec ! videoconvert ! video/x-raw,format=RGB \
    ! pngenc ! multifilesink max-files=2 location=$D/A_%02d.png >$D/A.log 2>&1
echo "A rc=$?; 文件: $(ls $D/A_*.png 2>/dev/null | tail -1)"

echo
echo "=== B. avdec_h265(软解) 出 PNG（参照）==="
timeout 18 gst-launch-1.0 -e $SRC ! avdec_h265 ! videoconvert ! video/x-raw,format=RGB \
    ! pngenc ! multifilesink max-files=2 location=$D/B_%02d.png >$D/B.log 2>&1
echo "B rc=$?; 文件: $(ls $D/B_*.png 2>/dev/null | tail -1)"

echo
echo "=== C. mppvideodec -> videoconvert -> NV12 -> mpph264enc 存 mkv ==="
timeout 18 gst-launch-1.0 -e $SRC \
    ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=NV12 \
    ! mpph264enc rc-mode=1 bps=2000000 gop=30 header-mode=each-idr \
    ! h264parse ! matroskamux ! filesink location=$D/C.mkv >$D/C.log 2>&1
echo "C rc=$?; 大小: $(stat -c %s $D/C.mkv 2>/dev/null)"

echo
echo "=== D. mppvideodec -> videoconvert -> I420 -> mpph264enc 存 mkv（改色度格式）==="
timeout 18 gst-launch-1.0 -e $SRC \
    ! queue ! mppvideodec ! videoconvert ! video/x-raw,format=I420 \
    ! mpph264enc rc-mode=1 bps=2000000 gop=30 header-mode=each-idr \
    ! h264parse ! matroskamux ! filesink location=$D/D.mkv >$D/D.log 2>&1
echo "D rc=$?; 大小: $(stat -c %s $D/D.mkv 2>/dev/null)"

echo
echo "=== E. mppvideodec -> mpph264enc（不插 videoconvert）存 mkv ==="
timeout 18 gst-launch-1.0 -e $SRC \
    ! queue ! mppvideodec ! mpph264enc rc-mode=1 bps=2000000 gop=30 header-mode=each-idr \
    ! h264parse ! matroskamux ! filesink location=$D/E.mkv >$D/E.log 2>&1
echo "E rc=$?; 大小: $(stat -c %s $D/E.mkv 2>/dev/null)"

echo
echo "=== 从 C/D/E 各抽一帧 ==="
for v in C D E; do
    [ -f "$D/$v.mkv" ] || { echo "$v: 无文件"; continue; }
    timeout 20 ffmpeg -y -v error -i "$D/$v.mkv" -frames:v 1 -pix_fmt rgb24 "$D/${v}_frame.png" 2>&1 | tail -2
    echo "$v 抽帧: $(stat -c %s $D/${v}_frame.png 2>/dev/null)"
done

echo
echo "=== 结果清单 ==="
ls -la $D/*.png 2>/dev/null
echo
echo "=== C/D/E 日志中的告警 ==="
for v in C D E; do echo "--- $v ---"; grep -iE 'error|warn|critical' $D/$v.log 2>/dev/null | head -3; done
