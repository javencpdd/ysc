#!/bin/bash
# kill_root_cam_tree2.sh —— 带密码的 sudo 清除 root 旧采集树
PW="'"
sukill() { printf "%s\n" "$PW" | sudo -S kill -9 "$1" 2>/dev/null; }

echo "=== 1. sudo 杀 root 旧采集树 ==="
for pid in 1918 2008 2011 2066 2071 2068 2074; do
  if [ -d /proc/$pid ]; then
    if sukill "$pid"; then echo "  killed $pid"; else echo "  FAILED $pid"; fi
  else
    echo "  gone $pid"
  fi
done
sleep 3

echo ""
echo "=== 2. 残留 gst 采集检查 ==="
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | cut -c1-100 || echo "  (无)"

echo ""
echo "=== 3. 等待 user 新树接管起流（25s） ==="
sleep 25
echo "--- 当前采集进程（期望含 extra-controls） ---"
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | cut -c1-400 || echo "  (暂无采集进程)"

echo ""
echo "=== 4. HLS ==="
for p in video1 video2; do
  printf "  %-8s HLS=%s\n" "$p" "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8888/$p/index.m3u8)"
done

echo ""
echo "=== 5. 曝光控制值（期望 auto=1） ==="
v4l2-ctl -d /dev/video0 -L 2>/dev/null | grep -A4 'exposure_auto' | head -6
