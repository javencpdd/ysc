#!/bin/bash
# kill_root_cam_tree.sh —— 清除 root 旧采集树，让 user 新树（新版管线）接管
echo "=== 1. 属主确认 ==="
ps -o user:14,pid,lstart,cmd -p 1918,2008,2011,2066,2071,2068,2074,1094,194716 2>/dev/null | cut -c1-130

echo ""
echo "=== 2. sudo 杀 root 旧采集树（push_video 脚本树 + gst 采集） ==="
for pid in 1918 2008 2011 2066 2071 2068 2074; do
  if [ -d /proc/$pid ]; then
    sudo kill -9 "$pid" 2>/dev/null && echo "  killed $pid" || echo "  FAILED $pid"
  else
    echo "  gone $pid"
  fi
done
sleep 3

echo ""
echo "=== 3. 残留检查 ==="
pgrep -af 'push_video' | grep -v 'bash -c' | cut -c1-120
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | cut -c1-120 || echo "  (无残留 gst 采集)"

echo ""
echo "=== 4. 等待 user 新树接管起流（25s） ==="
sleep 25
echo "--- 当前采集进程（应含 extra-controls） ---"
pgrep -af 'gst-launch' | grep -v 'bash -c' | grep -v rtmp-gst | cut -c1-400

echo ""
echo "=== 5. HLS ==="
for p in video1 video2; do
  printf "  %-8s HLS=%s\n" "$p" "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8888/$p/index.m3u8)"
done
