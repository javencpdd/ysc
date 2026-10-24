#!/bin/bash
# ae_test.sh —— 自动曝光(AE)对推流的影响：在线切换 exposure_auto 做 A/B 对照
# 只改相机 ctrl 与拉流测量，不动推流进程；结束恢复固定曝光
set -u
V2=""; V1=""
for d in /dev/video0 /dev/video2; do
  case "$d" in
    */video0) V1=$d ;;
    */video2) V2=$d ;;
  esac
done
CTL=$(command -v v4l2-ctl || echo /usr/bin/v4l2-ctl)

get() { $CTL -d "$1" --get-ctrl exposure_auto,exposure_absolute 2>/dev/null | tr '\n' ' '; }
setc() { $CTL -d "$1" --set-ctrl "$2" >/dev/null 2>&1; }

echo "############ 阶段 1：固定曝光（auto=1, 220）基线 ############"
echo -n "  video0: "; get "$V1"; echo
echo -n "  video2: "; get "$V2"; echo
bash /tmp/measure_two.sh both 20

echo ""
echo "############ 阶段 2：切自动曝光 exposure_auto=3 ############"
setc "$V1" exposure_auto=3
setc "$V2" exposure_auto=3
echo "  已切换，观察 12 秒内曝光值漂移："
for i in 1 2 3 4 5 6; do
  sleep 2
  echo -n "    t+$((i*2))s  video0: "; get "$V1"; echo -n "  |  video2: "; get "$V2"; echo
done
echo ""
echo "  === AE 开启下的帧率 ==="
bash /tmp/measure_two.sh both 20

echo ""
echo "############ 阶段 3：恢复固定曝光 220 ############"
setc "$V1" exposure_auto=1; setc "$V1" exposure_absolute=220
setc "$V2" exposure_auto=1; setc "$V2" exposure_absolute=220
sleep 2
echo -n "  video0: "; get "$V1"; echo
echo -n "  video2: "; get "$V2"; echo
bash /tmp/measure_two.sh both 15
