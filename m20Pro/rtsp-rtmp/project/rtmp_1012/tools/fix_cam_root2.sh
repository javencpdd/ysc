#!/bin/bash
# fix_cam_root2.sh —— 诊断权限 + 清旧 log + root 重启相机
PW="'"

echo "=== 1. 设备节点权限 ==="
ls -la /dev/video0 /dev/video2 2>/dev/null

echo ""
echo "=== 2. 旧 log 属主与 root 写 /tmp 测试 ==="
ls -la /tmp/camera_push.log 2>/dev/null
printf "%s\n" "$PW" | sudo -S sh -c 'echo ok > /tmp/root_write_test 2>&1 && echo "root write /tmp: OK" && rm -f /tmp/root_write_test' 2>&1 | grep -v '^\[sudo\]'

echo ""
echo "=== 3. 删除 user 旧 log ==="
rm -f /tmp/camera_push.log && echo "  removed" || echo "  rm failed"

echo ""
echo "=== 4. sudo restart_camera（root） ==="
printf "%s\n" "$PW" | sudo -S bash /home/user/rtmp_1012/patch/restart_camera.sh 2>&1 | grep -vE '^\[sudo\]' | tail -12

echo ""
echo "=== 5. 采集进程（期望含 extra-controls） ==="
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | cut -c1-400 || echo "  (无)"

echo ""
echo "=== 6. 曝光控制值（期望 exposure_auto=1） ==="
printf "%s\n" "$PW" | sudo -S v4l2-ctl -d /dev/video0 -L 2>/dev/null | grep -A4 'exposure_auto' | head -6
