#!/bin/bash
# 分别从"源 RTSP"和"我的 RTMP 输出"抓帧，用于对比定位画质问题
OUT=/tmp/frames
mkdir -p $OUT
rm -f $OUT/*.png

echo "=== 1. 源流 video1 (rtsp://127.0.0.1:8554/video1) 抓帧 ==="
timeout 25 ffmpeg -y -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video1 \
    -frames:v 1 -pix_fmt rgb24 $OUT/src_video1.png 2>&1 | tail -3
ls -la $OUT/src_video1.png 2>&1

echo
echo "=== 2. 源流 video2 抓帧 ==="
timeout 25 ffmpeg -y -v error -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video2 \
    -frames:v 1 -pix_fmt rgb24 $OUT/src_video2.png 2>&1 | tail -3
ls -la $OUT/src_video2.png 2>&1

echo
echo "=== 3. 我的输出 m20pro-f 抓帧 ==="
timeout 25 ffmpeg -y -v error -i rtmp://172.31.68.227:1936/live/m20pro-f \
    -frames:v 1 -pix_fmt rgb24 $OUT/out_f.png 2>&1 | tail -3
ls -la $OUT/out_f.png 2>&1

echo
echo "=== 4. 源流的像素格式与尺寸 ==="
timeout 20 ffprobe -v error -rtsp_transport tcp -select_streams v:0 \
    -show_entries stream=codec_name,width,height,pix_fmt,profile -of default=noprint_wrappers=1 \
    rtsp://127.0.0.1:8554/video1 2>&1 | head -8
