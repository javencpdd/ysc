#!/bin/bash
# v1_sanity.sh —— 排除伪影：确认 video1 流是实时的，且控件是否整体失效
set -u
D=/dev/video1
URL=rtsp://127.0.0.1:8554/video1
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

frame_sig() {
  timeout 12 ffmpeg -v error -rtsp_transport tcp -i "$URL" -frames:v 1 \
    -vf scale=64:48,format=gray -f rawvideo - 2>/dev/null \
  | od -An -tu1 -v | awk '{for(i=1;i<=NF;i++){s+=$i;n++}} END{if(n>0) printf "%.1f", s/n; else printf "NA"}'
}

echo "=== 1. 流是否实时：连续 3 次采样，画面应有微小差异 ==="
for i in 1 2 3; do echo -n "  t$i 亮度="; frame_sig; echo; sleep 3; done

echo ""
echo "=== 2. 帧率是否正常（video1 RTSP 6s）==="
timeout 14 ffmpeg -v error -rtsp_transport tcp -i "$URL" -t 6 -c copy -y /tmp/_v1.mkv 2>/dev/null
N=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/_v1.mkv 2>/dev/null | wc -l)
awk -v n="$N" 'BEGIN{printf "  帧数=%d  帧率≈%.1f fps\n", n, n/6.0}'
rm -f /tmp/_v1.mkv

echo ""
echo "=== 3. video1 控件是否整体失效（gamma 在 video2 上极敏感）==="
for v in 100 200 300; do
  $CTL -d "$D" --set-ctrl gamma=$v >/dev/null 2>&1
  sleep 3
  printf "  gamma=%-4s 亮度=%s\n" "$v" "$(frame_sig)"
done
$CTL -d "$D" --set-ctrl gamma=100 >/dev/null 2>&1

echo ""
echo "=== 4. video1 控件是否整体失效（saturation 应明显改变画面）==="
for v in 0 76 100; do
  $CTL -d "$D" --set-ctrl saturation=$v >/dev/null 2>&1
  sleep 3
  printf "  saturation=%-4s 亮度=%s\n" "$v" "$(frame_sig)"
done
$CTL -d "$D" --set-ctrl saturation=76 >/dev/null 2>&1

echo ""
echo "=== 5. 谁在打开 /dev/video0 ==="
fuser -v /dev/video0 2>&1 | head -6
echo "=== 6. 当前 ctrl 值确认 ==="
$CTL -d "$D" --get-ctrl brightness,gamma,saturation,exposure_auto 2>/dev/null | sed 's/^/  /'
