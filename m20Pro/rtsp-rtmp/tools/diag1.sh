#!/bin/bash
# 排查：谁在调用 restart.sh / stop.sh / start_push_video.sh
echo "=== 搜索引用这些脚本的文件 ==="
grep -rl 'restart\.sh' /opt/robot /etc /lib/systemd /usr/lib/systemd 2>/dev/null | head -20
echo "--- 具体行 ---"
grep -rn 'rtsp_service/restart\.sh\|rtsp_service/stop\.sh\|start_push_video' /opt/robot /etc /lib/systemd /usr/lib/systemd 2>/dev/null | head -20
echo
echo "=== /opt/robot/scripts 下的所有文件 ==="
find /opt/robot/scripts -maxdepth 2 -type f | sort | head -40
echo
echo "=== 是否有 watchdog / monitor 类进程 ==="
ps -eo pid,ppid,etime,cmd | grep -iE 'watch|monitor|supervis|guard' | grep -v grep | head
echo
echo "=== 当前进程全景 (前 30) ==="
ps -eo pid,ppid,etime,cmd --sort=start_time | tail -30
