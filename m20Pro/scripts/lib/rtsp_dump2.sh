dump_text() {
  for f in "$@"; do
    [ -f "$f" ] || continue
    if file -b "$f" 2>/dev/null | grep -qiE 'text|empty|json|script'; then
      echo "=========== FILE: $f ($(wc -l < "$f") 行) ==========="
      head -170 "$f"
      echo ""
    else
      echo "=========== (跳过二进制) $f ==========="
      ls -la "$f"
      echo ""
    fi
  done
}

echo "########## A. /home/user/rtmp_1012 顶层文本文件 ##########"
dump_text /home/user/rtmp_1012/README.md \
          /home/user/rtmp_1012/config.env \
          /home/user/rtmp_1012/rtmp_forward.sh \
          /home/user/rtmp_1012/start.sh \
          /home/user/rtmp_1012/stop.sh \
          /home/user/rtmp_1012/status.sh \
          /home/user/rtmp_1012/run_all.sh \
          /home/user/rtmp_1012/install_service.sh \
          /home/user/rtmp_1012/systemd/rtmp-forward@.service \
          /home/user/rtmp_1012/systemd/m20video.service

echo ""
echo "########## B. bin/rtmp-gst 是什么 ##########"
file /home/user/rtmp_1012/bin/rtmp-gst 2>/dev/null
ls -la /home/user/rtmp_1012/bin/
echo "--- strings 里的关键线索 ---"
strings /home/user/rtmp_1012/bin/rtmp-gst 2>/dev/null | grep -iE 'rtsp|rtmp|flv|gst|\.sh|usage|app|key|url|location' | head -30

echo ""
echo "########## C. logs 目录 ##########"
ls -la /home/user/rtmp_1012/logs/
for lg in /home/user/rtmp_1012/logs/forward-f.log /home/user/rtmp_1012/logs/forward-b.log; do
  echo "--- $lg (最后 15 行) ---"
  tail -15 "$lg" 2>/dev/null
  echo ""
done

echo ""
echo "########## D. rtmp-forward@ 实例与状态 ##########"
systemctl list-units --all --no-pager 2>/dev/null | grep -iE 'rtmp-forward|tk-mtx|m20video'
echo "--- journalctl rtmp-forward@ ---"
journalctl -u 'rtmp-forward@f' -u 'rtmp-forward@b' --no-pager -n 20 2>/dev/null | tail -25

echo ""
echo "########## E. config.env 解析出的实际目标 ##########"
grep -vE '^\s*#|^\s*$' /home/user/rtmp_1012/config.env 2>/dev/null

echo ""
echo "########## F. 当前到外部的 RTMP 连接 ##########"
ss -tnp 2>/dev/null | grep -E ':(1935|1936|8554)[[:space:]]' | head -15
