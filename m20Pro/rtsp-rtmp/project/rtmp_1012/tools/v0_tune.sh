#!/bin/bash
# v0_tune.sh —— 为前相机找最佳曝光：消除 21.6% 过曝，同时保住暗部
set -u
D=/dev/video0
URL=rtsp://127.0.0.1:8554/video1
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

stat_lum() {
  timeout 12 ffmpeg -v error -rtsp_transport tcp -i "$URL" -frames:v 1 \
    -vf scale=64:48,format=gray -f rawvideo - 2>/dev/null \
  | od -An -tu1 -v | awk '{for(i=1;i<=NF;i++){v=$i; s+=v; n++; if(v>=250) hi++; if(v<=20) lo++}}
      END{if(n>0) printf "亮度=%5.1f 饱和=%4.1f%% 暗部(<=20)=%4.1f%%", s/n, hi*100/n, lo*100/n; else printf "NA"}'
}

echo "=== 前相机曝光细调（目标：饱和<2%，亮度 130~170，暗部<8%）==="
$CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
printf "  %-10s %s\n" "exposure" "指标"
for v in 90 110 130 150 170 200; do
  $CTL -d "$D" --set-ctrl exposure_absolute=$v >/dev/null 2>&1
  sleep 3
  printf "  %-10s %s\n" "$v" "$(stat_lum)"
done

echo ""
echo "=== 对照：前相机改用自动曝光（与后相机工作模式一致）==="
$CTL -d "$D" --set-ctrl exposure_auto=3 >/dev/null 2>&1
for i in 1 2 3; do
  sleep 4
  printf "  auto=3 t+%ds  %s\n" $((i*4)) "$(stat_lum)"
done

echo ""
echo "=== 恢复当前生产配置（auto=1, 220）==="
$CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
$CTL -d "$D" --set-ctrl exposure_absolute=220 >/dev/null 2>&1
sleep 3
$CTL -d "$D" --get-ctrl exposure_auto,exposure_absolute 2>/dev/null | sed 's/^/  /'
echo -n "  "; stat_lum; echo
