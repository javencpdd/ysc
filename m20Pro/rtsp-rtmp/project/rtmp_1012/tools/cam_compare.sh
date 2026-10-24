#!/bin/bash
# cam_compare.sh —— 前后相机（video0 / video2）三层配置对比
# 只读：lsusb 身份、v4l2 全部控件当前值、实际格式与帧率
set -u
CTL=/usr/bin/v4l2-ctl
[ -x "$CTL" ] || CTL=$(command -v v4l2-ctl)

ident() {
  local dev=$1 node=$2
  echo "  [$node]"
  echo -n "    name: "; cat /sys/class/video4linux/$node/name 2>/dev/null || echo NA
  local lnk; lnk=$(readlink -f /sys/class/video4linux/$node 2>/dev/null)
  echo "    sysfs: $lnk"
  local usbpath; usbpath=$(echo "$lnk" | sed -n 's|.*/\([0-9]\+-[0-9.]\+\(:[0-9.]\+\)\?\)/video4linux/.*|\1|p')
  echo "    usb_path: ${usbpath:-NA}"
  if [ -n "${usbpath:-}" ]; then
    local base="/sys/bus/usb/devices/${usbpath%%:*}"
    for f in idVendor idProduct manufacturer product serial bcdDevice speed version; do
      [ -f "$base/$f" ] && echo "    $f: $(cat "$base/$f" 2>/dev/null)"
    done
  fi
}

echo "########## 1. 硬件身份 ##########"
ident /dev/video0 video0
ident /dev/video2 video2

echo ""
echo "########## 2. 当前格式 / 帧率 ##########"
for d in /dev/video0 /dev/video2; do
  echo "  [$d]"
  $CTL -d "$d" --get-fmt-video 2>/dev/null | sed 's/^/    /'
  $CTL -d "$d" --get-parm 2>/dev/null | sed 's/^/    /'
done

echo ""
echo "########## 3. 全部控件当前值（diff 看差异） ##########"
$CTL -d /dev/video0 --list-ctrls 2>/dev/null | sed 's/[[:space:]]\+/ /g' > /tmp/_c0.txt
$CTL -d /dev/video2 --list-ctrls 2>/dev/null | sed 's/[[:space:]]\+/ /g' > /tmp/_c2.txt
echo "  --- video0 (前) ---"
cat /tmp/_c0.txt | sed 's/^/    /'
echo "  --- video2 (后) ---"
cat /tmp/_c2.txt | sed 's/^/    /'
echo "  --- 差异 (< 前 / > 后) ---"
diff /tmp/_c0.txt /tmp/_c2.txt | sed 's/^/    /' || true

echo ""
echo "########## 4. 推流侧参数（从 RTSP 实拉核对） ##########"
for s in video1 video2; do
  echo -n "  $s: "
  timeout 12 ffprobe -v error -rtsp_transport tcp -select_streams v:0 \
    -show_entries stream=width,height,r_frame_rate,avg_frame_rate,codec_name,profile,level \
    -of default=nw=1 "rtsp://127.0.0.1:8554/$s" 2>/dev/null | tr '\n' ' '
  echo
  echo -n "        码率/GOP: "
  timeout 14 ffmpeg -v error -rtsp_transport tcp -i "rtsp://127.0.0.1:8554/$s" -t 6 -c copy -y /tmp/_p_$s.mkv 2>/dev/null
  SZ=$(stat -c %s /tmp/_p_$s.mkv 2>/dev/null || echo 0)
  K=$(ffprobe -v error -select_streams v:0 -show_entries packet=flags -of csv=p=0 /tmp/_p_$s.mkv 2>/dev/null | grep -c K)
  N=$(ffprobe -v error -select_streams v:0 -show_entries packet=pts_time -of csv=p=0 /tmp/_p_$s.mkv 2>/dev/null | wc -l)
  awk -v s="$SZ" -v k="$K" -v n="$N" 'BEGIN{if(n>0) printf "%.0f kbps, 6s内 %d 帧(%d 个I帧, GOP≈%.1f)\n", s*8/6/1000, n, k, (k>0)?n/k:0; else print "NA"}'
  rm -f /tmp/_p_$s.mkv
done
rm -f /tmp/_c0.txt /tmp/_c2.txt
