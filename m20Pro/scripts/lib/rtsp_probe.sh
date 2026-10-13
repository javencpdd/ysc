echo "########## 主机信息 ##########"
hostname; date
ip -brief addr show 2>/dev/null | grep -v '^lo'

echo ""
echo "########## 媒体相关端口监听 ##########"
ss -tlnp 2>/dev/null | grep -E ':(8554|8555|1935|1936|8888|8889|554|5540|8080|30000|30001|8000)[[:space:]]' || echo "(无相关监听)"

echo ""
echo "########## 媒体相关进程 ##########"
ps aux 2>/dev/null | grep -iE 'rtsp|rtmp|mediamtx|srs|ffmpeg|gst|zlmedia|nginx|rtspd' | grep -v grep || echo "(无)"

echo ""
echo "########## 按名字搜 rtsp/rtmp/mediamtx/srs 文件 ##########"
find /home /opt /etc /usr/local /data /root -maxdepth 4 \
  \( -iname '*rtsp*' -o -iname '*rtmp*' -o -iname '*mediamtx*' -o -iname '*srs*' -o -iname '*push*stream*' \) 2>/dev/null | head -40

echo ""
echo "########## systemd 相关服务 ##########"
systemctl list-units --type=service --all --no-pager 2>/dev/null | grep -iE 'rtsp|rtmp|video|stream|media|live' || echo "(无相关服务)"
echo "--- /etc/systemd/system ---"
ls /etc/systemd/system/ 2>/dev/null | head -40
echo "--- 用户级 ---"
ls ~/.config/systemd/user/ 2>/dev/null || echo "(无)"

echo ""
echo "########## 日志目录里的推流日志 ##########"
find /home /opt /var/log -maxdepth 3 \( -iname '*rtmp*log*' -o -iname '*rtsp*log*' -o -iname '*stream*log*' -o -iname '*push*log*' \) 2>/dev/null | head -20
