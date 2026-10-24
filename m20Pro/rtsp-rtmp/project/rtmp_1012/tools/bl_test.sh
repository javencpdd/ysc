#!/bin/bash
# bl_test.sh —— 抢救前相机过曝：backlight_compensation 与 brightness 的实测效果
set -u
D=/dev/video1
URL=rtsp://127.0.0.1:8554/video1
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

stat_lum() {
  timeout 12 ffmpeg -v error -rtsp_transport tcp -i "$URL" -frames:v 1 \
    -vf scale=64:48,format=gray -f rawvideo - 2>/dev/null \
  | od -An -tu1 -v | awk '{for(i=1;i<=NF;i++){v=$i; s+=v; n++; if(v>=250) hi++; if(v<=5) lo++}}
      END{if(n>0) printf "亮度=%5.1f  饱和=%4.1f%%  全黑=%4.1f%%", s/n, hi*100/n, lo*100/n; else printf "NA"}'
}

echo "=== 前相机 video1 过曝抢救实验（基线：亮度~202, 饱和~21.5%）==="

echo ""
echo "--- A. backlight_compensation 开/关（让 AE 照顾暗部） ---"
for v in 0 1; do
  $CTL -d "$D" --set-ctrl backlight_compensation=$v >/dev/null 2>&1
  sleep 4
  printf "  bl_comp=%s  %s\n" "$v" "$(stat_lum)"
done
$CTL -d "$D" --set-ctrl backlight_compensation=0 >/dev/null 2>&1

echo ""
echo "--- B. brightness 负向补偿 ---"
for v in 0 -20 -40 -60; do
  $CTL -d "$D" --set-ctrl brightness=$v >/dev/null 2>&1
  sleep 3
  printf "  brightness=%-4s %s\n" "$v" "$(stat_lum)"
done

echo ""
echo "--- C. 组合：bl_comp=1 + brightness 微调 ---"
$CTL -d "$D" --set-ctrl backlight_compensation=1 >/dev/null 2>&1
for v in 0 -20 -40; do
  $CTL -d "$D" --set-ctrl brightness=$v >/dev/null 2>&1
  sleep 3
  printf "  bl=1 brightness=%-4s %s\n" "$v" "$(stat_lum)"
done

echo ""
echo "=== 恢复默认 (bl=0, brightness=0) ==="
$CTL -d "$D" --set-ctrl backlight_compensation=0 >/dev/null 2>&1
$CTL -d "$D" --set-ctrl brightness=0 >/dev/null 2>&1
sleep 3
$CTL -d "$D" --get-ctrl brightness,backlight_compensation 2>/dev/null | sed 's/^/  /'
echo -n "  恢复后: "; stat_lum; echo
