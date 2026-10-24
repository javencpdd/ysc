#!/bin/bash
# fix_cam_root.sh —— root 身份重启相机服务（新版 push_video.sh）
PW="'"

echo "=== 1. camera_push.log 尾部（确认 user 树在等什么） ==="
tail -4 /tmp/camera_push.log 2>/dev/null

echo ""
echo "=== 2. sudo 跑 restart_camera.sh（root 身份） ==="
printf "%s\n" "$PW" | sudo -S bash /home/user/rtmp_1012/patch/restart_camera.sh 2>&1 | grep -vE '^\[sudo\]' | tail -14

echo ""
echo "=== 3. 采集进程（期望含 extra-controls） ==="
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | cut -c1-400 || echo "  (无)"

echo ""
echo "=== 4. 曝光控制值（期望 exposure_auto=1） ==="
printf "%s\n" "$PW" | sudo -S v4l2-ctl -d /dev/video0 -L 2>/dev/null | grep -A4 'exposure_auto' | head -6
