#!/bin/bash
# 步骤1：备份相机推流脚本并定位需要修改的确切内容
SRC=/opt/robot/scripts/board_resources/rtsp_service/push_video.sh
BK=/home/user/rtmp_1012/patch
mkdir -p "$BK"

echo "=== 原始文件信息 ==="
ls -la "$SRC"
md5sum "$SRC"
echo

echo "=== 备份 ==="
cp -f "$SRC" "$BK/push_video.sh.orig"
cp -f "$SRC" "$BK/push_video.sh.orig.$(date +%Y%m%d-%H%M%S)"
chmod 644 "$BK"/push_video.sh.orig*
md5sum "$BK"/push_video.sh.orig*
echo

echo "=== 所有含编解码器关键字的行 ==="
grep -n 'mpph265enc\|mpph264enc\|h265parse\|h264parse\|DEV_ENCODER_PARAMS\|videoconvert' "$SRC"
echo

echo "=== build_pipeline 函数原文 ==="
sed -n '/^build_pipeline()/,/^}/p' "$SRC"
echo

echo "=== SM_USB_107X profile 原文 ==="
sed -n '/^        SM_USB_107X)/,/^            ;;/p' "$SRC"
echo

echo "=== 默认 profile 原文 ==="
sed -n '/^        \*)/,/^            ;;/p' "$SRC"
