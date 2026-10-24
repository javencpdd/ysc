#!/bin/bash
# bright_test.sh —— 验证 brightness/contrast/gamma 是否真正生效（区别于已被证伪的 exposure_absolute）
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

echo "=== brightness 扫描（baseline 应约 137）==="
for v in -64 -30 0 30 64; do
  $CTL -d "$D" --set-ctrl brightness=$v >/dev/null 2>&1
  sleep 2
  rb=$($CTL -d "$D" --get-ctrl brightness 2>/dev/null | awk '{print $2}')
  printf "  brightness=%-4s 读回 %-4s 亮度=%s\n" "$v" "$rb" "$(lum)"
done
$CTL -d "$D" --set-ctrl brightness=0 >/dev/null 2>&1

echo ""
echo "=== contrast 扫描 ==="
for v in 0 40 95; do
  $CTL -d "$D" --set-ctrl contrast=$v >/dev/null 2>&1
  sleep 2
  printf "  contrast=%-4s 亮度=%s\n" "$v" "$(lum)"
done
$CTL -d "$D" --set-ctrl contrast=40 >/dev/null 2>&1

echo ""
echo "=== gamma 扫描 ==="
for v in 100 200 300; do
  $CTL -d "$D" --set-ctrl gamma=$v >/dev/null 2>&1
  sleep 2
  printf "  gamma=%-4s 亮度=%s\n" "$v" "$(lum)"
done
$CTL -d "$D" --set-ctrl gamma=100 >/dev/null 2>&1

echo ""
echo "=== 恢复默认并复核 ==="
sleep 2
$CTL -d "$D" --get-ctrl brightness,contrast,gamma 2>/dev/null | sed 's/^/  /'
echo -n "  亮度="; lum; echo
