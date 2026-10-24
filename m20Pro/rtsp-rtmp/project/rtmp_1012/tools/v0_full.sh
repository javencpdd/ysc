#!/bin/bash
# v0_full.sh —— 前相机（采集节点 /dev/video0）完整控件有效性测试
# ⚠️ 教训：UVC 每颗相机有两个节点，偶数=采集(video0/video2)，奇数=metadata(video1/video3)
#          设控件必须打在采集节点上，打在 metadata 节点上不会影响画面。
set -u
D=/dev/video0
URL=rtsp://127.0.0.1:8554/video1
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

stat_lum() {
  timeout 12 ffmpeg -v error -rtsp_transport tcp -i "$URL" -frames:v 1 \
    -vf scale=64:48,format=gray -f rawvideo - 2>/dev/null \
  | od -An -tu1 -v | awk '{for(i=1;i<=NF;i++){v=$i; s+=v; n++; if(v>=250) hi++; if(v<=5) lo++}}
      END{if(n>0) printf "亮度=%5.1f 饱和=%4.1f%% 全黑=%4.1f%%", s/n, hi*100/n, lo*100/n; else printf "NA"}'
}

echo "=== 前相机 /dev/video0（采集节点）控件有效性 ==="
echo -n "  基线: "; stat_lum; echo

echo ""
echo "--- A. exposure_absolute 是否有效（若有效，过曝有救） ---"
$CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
for v in 3 100 220 600 1200 2047; do
  $CTL -d "$D" --set-ctrl exposure_absolute=$v >/dev/null 2>&1
  sleep 3
  rb=$($CTL -d "$D" --get-ctrl exposure_absolute 2>/dev/null | awk '{print $2}')
  printf "  exposure=%-5s(读回%-5s) %s\n" "$v" "$rb" "$(stat_lum)"
done
$CTL -d "$D" --set-ctrl exposure_absolute=220 >/dev/null 2>&1

echo ""
echo "--- B. brightness 负向（压缩过曝） ---"
for v in 0 -20 -40 -64; do
  $CTL -d "$D" --set-ctrl brightness=$v >/dev/null 2>&1
  sleep 3
  printf "  brightness=%-4s %s\n" "$v" "$(stat_lum)"
done
$CTL -d "$D" --set-ctrl brightness=0 >/dev/null 2>&1

echo ""
echo "--- C. backlight_compensation（背光补偿，专治白墙过曝） ---"
for v in 0 1; do
  $CTL -d "$D" --set-ctrl backlight_compensation=$v >/dev/null 2>&1
  sleep 4
  printf "  bl_comp=%s  %s\n" "$v" "$(stat_lum)"
done
$CTL -d "$D" --set-ctrl backlight_compensation=0 >/dev/null 2>&1

echo ""
echo "--- D. contrast 降低（拉开高光） ---"
for v in 40 20 0; do
  $CTL -d "$D" --set-ctrl contrast=$v >/dev/null 2>&1
  sleep 3
  printf "  contrast=%-4s %s\n" "$v" "$(stat_lum)"
done
$CTL -d "$D" --set-ctrl contrast=40 >/dev/null 2>&1

echo ""
echo "=== 恢复默认 ==="
$CTL -d "$D" --set-ctrl brightness=0 contrast=40 backlight_compensation=0 >/dev/null 2>&1
$CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
$CTL -d "$D" --set-ctrl exposure_absolute=220 >/dev/null 2>&1
sleep 3
$CTL -d "$D" --get-ctrl brightness,contrast,backlight_compensation,exposure_auto,exposure_absolute 2>/dev/null | sed 's/^/  /'
echo -n "  恢复后: "; stat_lum; echo
