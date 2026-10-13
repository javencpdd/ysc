#!/bin/bash
# 量 120 主机上"纯 remux"中继链路的真实开销
W=15
HZ=100
NCPU=$(nproc --all)
echo "120 主机: $(hostname)  核数=$NCPU"

jif() { awk '{print $14+$15}' /proc/$1/stat 2>/dev/null; }

# 找出中继相关进程：rtmp_forward.sh 及其 gst 子进程
RELAY=$(pgrep -f 'rtmp_forwar[d]' | tr '\n' ' ')
GST=$(pgrep -f 'rtmpsin[k]' | tr '\n' ' ')
CAM=$(pgrep -f 'rtspclientsin[k]' | tr '\n' ' ')
MTX=$(pgrep -x mediamtx | tr '\n' ' ')

echo "  中继脚本 PID: ${RELAY:-无}"
echo "  中继gst  PID: ${GST:-无}"
echo "  相机gst  PID: ${CAM:-无}"
echo "  mediamtx PID: ${MTX:-无}"
echo

sum() { local t=0 v; for p in $1; do v=$(jif $p); [ -n "$v" ] && t=$((t+v)); done; echo $t; }
rss() { local t=0 v; for p in $1; do v=$(awk '/^VmRSS:/{print $2}' /proc/$p/status 2>/dev/null); [ -n "$v" ] && t=$((t+v)); done; echo $t; }

measure() {
    local name="$1" pids="$2"
    [ -z "$pids" ] && { echo "  $name: 进程不存在"; return; }
    local a b r
    a=$(sum "$pids"); sleep "$W"; b=$(sum "$pids"); r=$(rss "$pids")
    awk -v n="$name" -v a="$a" -v b="$b" -v r="$r" -v h="$HZ" -v w="$W" -v nc="$NCPU" \
      'BEGIN{printf "  %-24s CPU=%6.1f%%单核 (整机%5.1f%%, %.2f核)  内存=%6.1fMB\n", n, (b-a)/h/w*100, (b-a)/h/w*100/nc, (b-a)/h/w, r/1024}'
}

measure "RTSP→RTMP 中继(纯remux)" "$RELAY $GST"
measure "相机采集+编码" "$CAM"
measure "mediamtx" "$MTX"

echo
echo "  参考: 两条链路做的活儿不同——"
echo "    120: 相机已编 H.264 → 中继只做拆包/封 FLV（零转码）"
echo "    196: 相机编 H.265 → 中继必须 解码+重编 H.264（含 95%/路的 NV12→I420 转换）"
