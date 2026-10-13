#!/usr/bin/env bash
# ============================================================================
# apply_h264.sh —— 把相机侧 push_video.sh 从 H.265 改为 H.264
#
#   目的：让 196 本机 RTSP 流变成 H.264，从而使 rtmp_1012 中继退化为
#         「纯 remux」（零转码），CPU 从约 2 核降到约 0.3 核。
#
#   改动点（仅 3 处，全部在 push_video.sh 内）：
#     1) 第 320 行 build_pipeline:  mpph265enc -> mpph264enc
#     2) 第 320 行 build_pipeline:  h265parse  -> h264parse
#     3) 第 320 行 build_pipeline:  在 videoconvert 后强制 I420
#        （必须！mpph264enc 在 NV12 输入下会花屏，实测确认）
#     4) 第 115 行 SM_USB_107X profile: 补上码率参数
#        （原来只有 gop=2 header-mode=each-idr，无码率控制；
#          且 gop=2 会显著抬升码率，改为 gop=30）
#
#   幂等：已打过补丁则跳过；文件被外部改动过则中止并提示。
#   还原：执行同目录的 revert_h265.sh
# ============================================================================
set -u

TARGET=/opt/robot/scripts/board_resources/rtsp_service/push_video.sh
PATCH_DIR=/home/user/rtmp_1012/patch
BACKUP="$PATCH_DIR/push_video.sh.orig"
RESTART="$PATCH_DIR/restart_camera.sh"

echo "==================== 应用 H.264 补丁 ===================="

[ -f "$TARGET"  ] || { echo "错误: 目标不存在 $TARGET"; exit 1; }
[ -f "$BACKUP"  ] || { echo "错误: 备份不存在 $BACKUP（请先运行 patch_step1）"; exit 1; }

echo "--- 备份校验 ---"
ORIG_MD5=$(md5sum "$BACKUP" | awk '{print $1}')
echo "  备份 md5: $ORIG_MD5"

if grep -q 'mpph265enc' "$TARGET"; then
    echo "--- 状态: 未打补丁，开始应用 ---"
elif grep -q 'mpph264enc' "$TARGET" && ! grep -q 'mpph265enc' "$TARGET"; then
    echo "--- 状态: 已经是 H.264（已打过补丁），无需重复应用 ---"
    echo "  若想还原: $PATCH_DIR/revert_h265.sh"
    exit 0
else
    echo "--- 错误: 文件内容既非原版也非预期补丁版，可能被外部修改过 ---"
    echo "  当前 md5: $(md5sum "$TARGET" | awk '{print $1}')"
    echo "  原始 md5: $ORIG_MD5"
    echo "  请人工确认后再操作。已中止。"
    exit 2
fi

# 先备份当前实际内容（万一备份与现状不一致）
cp -f "$TARGET" "$PATCH_DIR/push_video.sh.before-apply.$(date +%Y%m%d-%H%M%S)"

# ---- 改动 1~3：重写 build_pipeline 里的管道行 ----
sed -i \
  -e 's#! videoconvert ! mpph265enc \$DEV_ENCODER_PARAMS ! h265parse config-interval=-1 !#! videoconvert ! video/x-raw,format=I420 ! mpph264enc $DEV_ENCODER_PARAMS ! h264parse config-interval=-1 !#' \
  "$TARGET"

# ---- 改动 4：SM_USB_107X 的编码参数 ----
sed -i \
  -e 's#DEV_ENCODER_PARAMS="gop=2 header-mode=each-idr"#DEV_ENCODER_PARAMS="rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"#' \
  "$TARGET"

echo
echo "--- 改动后校验 ---"
echo -n "  仍含 mpph265enc : "; grep -c 'mpph265enc' "$TARGET"
echo -n "  仍含 h265parse  : "; grep -c 'h265parse' "$TARGET"
echo -n "  含 mpph264enc   : "; grep -c 'mpph264enc' "$TARGET"
echo -n "  含 h264parse    : "; grep -c 'h264parse' "$TARGET"
echo -n "  含 I420 强制    : "; grep -c 'format=I420' "$TARGET"
echo
echo "  新的 build_pipeline:"
sed -n '/^build_pipeline()/,/^}/p' "$TARGET" | grep -o 'taskset.*latency=10' | head -1
echo
echo "  新的 SM_USB_107X 参数:"
grep -n 'DEV_ENCODER_PARAMS=' "$TARGET" | head -3

echo
echo "--- 重启相机服务使改动生效 ---"
bash "$RESTART"

echo
echo "======================================================="
echo "补丁应用完成。下一步请把 rtmp_1012 的 config.env 改成 SOURCE_CODEC=\"h264\" 并重启推流。"
echo "还原方法: $PATCH_DIR/revert_h265.sh"
