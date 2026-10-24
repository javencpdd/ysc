#!/bin/bash
# exp_extreme.sh —— 曝光控件有效性终判：设极小/极大值看画面亮度是否变化
set -u
D=/dev/video2
URL=rtsp://127.0.0.1:8554/video2
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

lum() {
  timeout 12 ffmpeg -v error -rtsp_transport tcp -i "$URL" -frames:v 1 \
    -vf scale=64:48,format=gray -f rawvideo - 2>/dev/null \
  | od -An -tu1 -v | awk '{for(i=1;i<=NF;i++){s+=$i;n++}} END{if(n>0) printf "%.1f", s/n; else printf "NA"}'
}

echo "=== 曝光控件有效性终判（video2）==="
echo -n "  当前值: "; $CTL -d "$D" --get-ctrl exposure_auto,exposure_absolute 2>/dev/null | tr '\n' ' '; echo

for v in 3 50 300 1000 2047; do
  $CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
  $CTL -d "$D" --set-ctrl exposure_absolute=$v >/dev/null 2>&1
  sleep 2
  rb=$($CTL -d "$D" --get-ctrl exposure_absolute 2>/dev/null | awk '{print $2}')
  printf "  设定 %-5s 读回 %-5s 亮度=%s\n" "$v" "$rb" "$(lum)"
done

echo ""
echo "=== 再试自动曝光，并观察是否有任何响应 ==="
$CTL -d "$D" --set-ctrl exposure_auto=3 >/dev/null 2>&1
for i in 1 2 3; do sleep 3; printf "  auto=3 t+%ds 亮度=%s\n" $((i*3)) "$(lum)"; done

echo ""
echo "=== 恢复 ==="
$CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
$CTL -d "$D" --set-ctrl exposure_absolute=220 >/dev/null 2>&1
sleep 2
echo -n "  已恢复: "; $CTL -d "$D" --get-ctrl exposure_auto,exposure_absolute 2>/dev/null | tr '\n' ' '; echo
