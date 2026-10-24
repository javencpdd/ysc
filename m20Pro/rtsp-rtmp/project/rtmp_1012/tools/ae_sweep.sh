#!/bin/bash
# ae_sweep.sh —— 曝光时间扫描：验证"曝光时间 > 帧周期(33ms) 是否拖低帧率"
# 只动 video2 的 ctrl，video1 保持正常；结束恢复 220
set -u
D=/dev/video2
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

setexp() { $CTL -d "$D" --set-ctrl exposure_auto=1 >/dev/null 2>&1; $CTL -d "$D" --set-ctrl exposure_absolute="$1" >/dev/null 2>&1; }
getexp() { $CTL -d "$D" --get-ctrl exposure_absolute 2>/dev/null | awk '{print $2}'; }

echo "########## 曝光时间 → 帧率 扫描（video2，每档 12s） ##########"
printf "  %-12s %-10s %s\n" "曝光值" "曝光时间" "测量结果"
for v in 220 330 400 550 800 1100; do
  setexp "$v"
  sleep 1
  cur=$(getexp)
  ms=$(awk -v x="$cur" 'BEGIN{printf "%.1f", x/10}')
  printf "  %-12s %-10s " "${cur}(设定${v})" "${ms}ms"
  bash /tmp/measure_two.sh video2 12 | sed 's/^  video2//'
done

echo ""
echo "########## 恢复 220 ##########"
setexp 220
sleep 2
echo -n "  当前曝光: "; getexp
bash /tmp/measure_two.sh video2 12
