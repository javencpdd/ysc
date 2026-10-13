#!/usr/bin/env bash
# ============================================================================
# revert_h265.sh —— 把相机侧 push_video.sh 还原回 H.265 原版
#
#   还原策略（两条，按可靠性排序）：
#     1) 优先用备份文件 push_video.sh.orig 整文件覆盖（最可靠）
#     2) 备份丢失时，用反向 sed 把 mpph264enc/h264parse/I420 改回 H.265
#
#   同时把 rtmp_1012 的 config.env 改回 SOURCE_CODEC="h265"
#   并重启相机服务 + 推流服务。
# ============================================================================
set -u

TARGET=/opt/robot/scripts/board_resources/rtsp_service/push_video.sh
PATCH_DIR=/home/user/rtmp_1012/patch
BACKUP="$PATCH_DIR/push_video.sh.orig"
RESTART="$PATCH_DIR/restart_camera.sh"
CONFIG=/home/user/rtmp_1012/config.env

echo "==================== 还原相机脚本为 H.265 ===================="

[ -f "$TARGET" ] || { echo "错误: 目标不存在 $TARGET"; exit 1; }

cp -f "$TARGET" "$PATCH_DIR/push_video.sh.before-revert.$(date +%Y%m%d-%H%M%S)"

if [ -f "$BACKUP" ] && [ -s "$BACKUP" ]; then
    echo "--- 方式1: 用备份整文件还原 ---"
    cp -f "$BACKUP" "$TARGET"
    chmod 0777 "$TARGET"
    NEW_MD5=$(md5sum "$TARGET" | awk '{print $1}')
    BAK_MD5=$(md5sum "$BACKUP" | awk '{print $1}')
    echo "  还原后 md5: $NEW_MD5"
    echo "  备份   md5: $BAK_MD5"
    if [ "$NEW_MD5" = "$BAK_MD5" ]; then
        echo "  ✅ 校验一致"
    else
        echo "  ❌ 校验不一致，请人工检查"
        exit 3
    fi
else
    echo "--- 方式2: 备份丢失，用反向 sed 还原 ---"
    sed -i \
      -e 's#! videoconvert ! video/x-raw,format=I420 ! mpph264enc \$DEV_ENCODER_PARAMS ! h264parse config-interval=-1 !#! videoconvert ! mpph265enc $DEV_ENCODER_PARAMS ! h265parse config-interval=-1 !#' \
      "$TARGET"
    sed -i \
      -e 's#DEV_ENCODER_PARAMS="rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"#DEV_ENCODER_PARAMS="gop=2 header-mode=each-idr"#' \
      "$TARGET"
    echo "  还原后 md5: $(md5sum "$TARGET" | awk '{print $1}')"
    echo "  （原始 md5 应为 128191f3fecc7f4b1017ae57fc075c77）"
fi

echo
echo "--- 还原 config.env 的 SOURCE_CODEC ---"
if [ -f "$CONFIG" ]; then
    sed -i 's/^SOURCE_CODEC="h264"/SOURCE_CODEC="h265"/' "$CONFIG"
    grep -n '^SOURCE_CODEC=' "$CONFIG"
else
    echo "  未找到 $CONFIG，跳过"
fi

echo
echo "--- 重启相机服务 ---"
bash "$RESTART"

echo
echo "--- 重启推流服务 ---"
if systemctl list-unit-files 2>/dev/null | grep -q '^m20video.service'; then
    systemctl restart m20video.service 2>/dev/null && \
        { sleep 6; echo -n "  m20video 状态: "; systemctl is-active m20video.service; } || \
        echo "  m20video 未启用（如需推流请执行: sudo m20video up）"
else
    echo "  m20video 服务未安装，跳过"
fi

echo
echo "==========================================================="
echo "已还原为 H.265。相机侧 RTSP 流恢复为 H.265，中继重新走硬转码。"
