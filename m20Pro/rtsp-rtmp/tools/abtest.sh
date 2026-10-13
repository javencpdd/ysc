#!/bin/bash
# 三变体对照实验：找出 CRITICAL 洪水的根因
# A 基线(mppvideodec+videoconvert+NV12, drop-on-latency, leaky queue)
# B 去掉 drop-on-latency 与 leaky
# C 去掉 videoconvert (mppvideodec 直接输出 NV12 给 mpph264enc)
ROOT=/tmp/abtest
mkdir -p "$ROOT"
rm -f "$ROOT"/*.log "$ROOT"/*.pid

launch() {
    local name="$1" core="$2"; shift 2
    setsid taskset -c "$core" gst-launch-1.0 -e "$@" \
        > "$ROOT/$name.log" 2>&1 < /dev/null &
    echo $! > "$ROOT/$name.pid"
}

COMMON_SRC=(rtspsrc location=rtsp://127.0.0.1:8554/video1 protocols=tcp latency=200)
ENC=(! mpph264enc rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr)
TAIL=(! h264parse config-interval=-1 ! flvmux streamable=true ! rtmpsink)

# A 基线
launch A 0,1 "${COMMON_SRC[@]}" drop-on-latency=true \
    ! rtph265depay ! h265parse \
    ! queue max-size-buffers=8 leaky=downstream \
    ! mppvideodec ! videoconvert ! video/x-raw,format=NV12 \
    "${ENC[@]}" "${TAIL[@]}" "location=rtmp://127.0.0.1:1935/abA live=1"

# B 无 drop-on-latency / 无 leaky
launch B 2,3 "${COMMON_SRC[@]}" \
    ! rtph265depay ! h265parse \
    ! mppvideodec ! videoconvert ! video/x-raw,format=NV12 \
    "${ENC[@]}" "${TAIL[@]}" "location=rtmp://127.0.0.1:1935/abB live=1"

# C 无 videoconvert
launch C 0,1 "${COMMON_SRC[@]}" drop-on-latency=true \
    ! rtph265depay ! h265parse \
    ! queue max-size-buffers=8 leaky=downstream \
    ! mppvideodec ! video/x-raw,format=NV12 \
    "${ENC[@]}" "${TAIL[@]}" "location=rtmp://127.0.0.1:1935/abC live=1"

echo "A=$(cat $ROOT/A.pid) B=$(cat $ROOT/B.pid) C=$(cat $ROOT/C.pid)"
echo "已启动 A/B/C 三个变体，推本机 mediamtx (abA/abB/abC)"
