#!/bin/bash
# ae_verify.sh —— 验证曝光值是否真的作用到画面：测亮度 + 相邻帧差异
# 亮度：scale→gray→rawvideo 后求均值（无依赖）
# 重复帧：连续 3 帧的 md5 是否相同（相同=相机在吐重复帧）
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

frames3() {
  rm -f /tmp/_fr*.png
  timeout 15 ffmpeg -v error -rtsp_transport tcp -i "$URL" -frames:v 3 \
    -vsync 0 -y /tmp/_fr%d.png 2>/dev/null
  local a b c
  a=$(md5sum /tmp/_fr1.png 2>/dev/null | cut -c1-8)
  b=$(md5sum /tmp/_fr2.png 2>/dev/null | cut -c1-8)
  c=$(md5sum /tmp/_fr3.png 2>/dev/null | cut -c1-8)
  local dup=0
  [ -n "$a" ] && [ "$a" = "$b" ] && dup=$((dup+1))
  [ -n "$b" ] && [ "$b" = "$c" ] && dup=$((dup+1))
  echo "$a/$b/$c dup=${dup}/2"
}

echo "########## 曝光值 → 画面亮度 / 重复帧 ##########"
printf "  %-8s %-10s %-12s %s\n" "曝光值" "理论时间" "平均亮度" "连续3帧指纹(dup=完全重复)"
for v in 100 166 220 400 800 1400; do
  $CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1
  $CTL -d "$D" --set-ctrl exposure_absolute="$v" >/dev/null 2>&1
  sleep 2
  L=$(lum)
  F=$(frames3)
  ms=$(awk -v x="$v" 'BEGIN{printf "%.1fms", x/10}')
  printf "  %-8s %-10s %-12s %s\n" "$v" "$ms" "$L" "$F"
done

echo ""
echo "########## 恢复 220 ##########"
$CTL -d "$D" --set-ctrl exposure_absolute=220 >/dev/null 2>&1
sleep 2
printf "  220 亮度=%s\n" "$(lum)"
rm -f /tmp/_fr*.png
