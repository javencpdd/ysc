#!/bin/bash
# install_ae_fix.sh —— 安装曝光修复版 push_video.sh（2026-10-19）
# 相机服务会瞬断 20-30s，relay 有源探测+重连会自动恢复
SVC=/opt/robot/scripts/board_resources/rtsp_service
TARGET=$SVC/push_video.sh
BAK=/home/user/rtmp_1012/patch/push_video.sh.bak-ae-off-$(date +%Y%m%d-%H%M%S)
NEW=/tmp/push_video.sh.new

echo "=== 1. 备份当前版本 ==="
cp -p "$TARGET" "$BAK" && echo "  备份 -> $BAK"
md5sum "$TARGET"

echo "=== 2. 安装新版本 ==="
cp "$NEW" "$TARGET" && chmod +x "$TARGET"

echo "=== 3. 校验改动存在 ==="
grep -c 'extra-controls' "$TARGET"
grep -n 'extra-controls' "$TARGET" | head -2 | cut -c1-160

echo "=== 4. 语法检查 ==="
bash -n "$TARGET" && echo "  bash -n OK"

echo "=== 5. 重启相机服务（瞬断 20-30s） ==="
bash /home/user/rtmp_1012/patch/restart_camera.sh || echo "  (restart 脚本返回非零，继续验证)"
