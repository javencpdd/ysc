echo "########## 1. /home/user/rtmp_1012 目录树 ##########"
find /home/user/rtmp_1012 -maxdepth 3 2>/dev/null | head -60
echo ""
for f in $(find /home/user/rtmp_1012 -maxdepth 3 -type f 2>/dev/null | head -30); do
  echo "=========== FILE: $f ($(wc -l < "$f") 行) ==========="
  head -150 "$f"
  echo ""
done

echo ""
echo "########## 2. rtsp_service 目录 ##########"
ls -la /opt/robot/scripts/board_resources/rtsp_service/ 2>/dev/null
echo ""
for f in /opt/robot/scripts/board_resources/rtsp_service/*.sh /opt/robot/scripts/board_resources/rtsp_service/*.yml; do
  [ -f "$f" ] || continue
  echo "=========== FILE: $f ($(wc -l < "$f") 行) ==========="
  head -120 "$f"
  echo ""
done

echo ""
echo "########## 3. board_resources 上层结构 ##########"
find /opt/robot/scripts/board_resources -maxdepth 2 2>/dev/null | head -40

echo ""
echo "########## 4. 视频相关 systemd 单元 ##########"
echo "--- m20video.service ---"
cat /etc/systemd/system/m20video.service 2>/dev/null || echo "(无)"
echo "--- tk-mtx.service ---"
systemctl cat tk-mtx.service --no-pager 2>/dev/null || echo "(无)"
echo "--- tk-mtx 状态 ---"
systemctl status tk-mtx.service --no-pager 2>/dev/null | head -15

echo ""
echo "########## 5. rtmp_1012 日志 ##########"
for lg in $(find /home/user/rtmp_1012 -name '*.log' 2>/dev/null | head -3); do
  echo "--- $lg ($(wc -l < "$lg") 行) ---"
  tail -25 "$lg"
done

echo ""
echo "########## 6. 当前 RTMP/RTSP 对外连接 ##########"
ss -tnp 2>/dev/null | grep -E ':(1935|1936|8554|554)[[:space:]]' | head -20

echo ""
echo "########## 7. rtmp-forward@ 实例状态 ##########"
systemctl list-units --all --no-pager 2>/dev/null | grep -iE 'rtmp|mtx|m20' 
echo "--- 日志 ---"
journalctl -u 'rtmp-forward@*' --no-pager -n 30 2>/dev/null | tail -35
