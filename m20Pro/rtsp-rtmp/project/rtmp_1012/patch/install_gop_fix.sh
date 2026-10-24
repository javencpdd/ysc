#!/bin/bash
# install_gop_fix.sh —— 安装 GOP 优化版 push_video.sh（曝光版 + gop=20）
PW="'"
SVC=/opt/robot/scripts/board_resources/rtsp_service
TARGET=$SVC/push_video.sh
BAK=/home/user/push_video.sh.bak-gop30-$(date +%Y%m%d-%H%M%S)
NEW=/tmp/push_video.sh.new

echo "=== 1. 备份当前版本（曝光版 gop=30） ==="
printf "%s\n" "$PW" | sudo -S cp -p "$TARGET" "$BAK" 2>/dev/null && echo "  备份 -> $BAK" || echo "  备份失败(权限?)"
printf "%s\n" "$PW" | sudo -S md5sum "$TARGET" 2>/dev/null | grep -v '^\[sudo\]'

echo "=== 2. 安装新版本 ==="
printf "%s\n" "$PW" | sudo -S cp "$NEW" "$TARGET" 2>/dev/null && echo "  installed" || echo "  install FAILED"

echo "=== 3. 校验 ==="
printf "%s\n" "$PW" | sudo -S sh -c "grep -c extra-controls '$TARGET'; grep -o 'gop=[0-9]*' '$TARGET' | head -2" 2>/dev/null | grep -v '^\[sudo\]'
printf "%s\n" "$PW" | sudo -S bash -n "$TARGET" 2>/dev/null && echo "  bash -n OK" || echo "  bash -n FAILED"

echo "=== 4. root 重启相机 ==="
printf "%s\n" "$PW" | sudo -S bash /home/user/rtmp_1012/patch/restart_camera.sh 2>&1 | grep -vE '^\[sudo\]' | tail -8

echo "=== 5. 采集进程（期望 gop=20 + extra-controls） ==="
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | grep -o 'mpph264enc[^!]*' | head -2
