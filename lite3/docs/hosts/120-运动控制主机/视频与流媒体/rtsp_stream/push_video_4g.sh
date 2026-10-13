#!/bin/bash
# ============================================================================
# 4G/5G 公网图传推流脚本  (RK3588 / Rockchip MPP 硬件编码)
#
# 用法:
#   ./push_video_4g.sh probe   检查 GStreamer 插件是否齐全（先跑这个）
#   ./push_video_4g.sh srt     推荐：SRT 回传，抗丢包，延迟 200-500ms
#   ./push_video_4g.sh rtmp    备选：RTMP 回传，兼容好，弱网延迟不可控
#
# 可通过环境变量覆盖:
#   SERVER_IP   服务器公网 IP 或域名     例: SERVER_IP=1.2.3.4
#   STREAM_ID   流标识，建议用机器人编号  例: STREAM_ID=robot01
#   BITRATE     目标码率 bps             例: BITRATE=800000
#
# 与局域网版 push_video.sh 并存，互不干扰。
# ============================================================================

set -u

SERVER_IP="${SERVER_IP:-203.0.113.10}"
STREAM_ID="${STREAM_ID:-robot01}"
MODE="${1:-srt}"

# ---------- 采集 ----------
V4L2_DEV="${V4L2_DEV:-/dev/video0}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"

# ---------- 编码（4G 弱网优化） ----------
# 4G 上行实测常只有 2-8 Mbps 且抖动大，码率务必给链路留 40% 余量。
# gop=30 意味着每秒一个 I 帧，弱网丢包后能在 1 秒内恢复画面。
BITRATE="${BITRATE:-1500000}"
GOP="${GOP:-30}"

# ---------- SRT ----------
SRT_PORT="${SRT_PORT:-8890}"
# latency 是 SRT 的核心旋钮：太小则频繁重传，太大则延迟高。
# 4G 建议 300；信号好可降到 150；专网/专线的场合可试 100。
SRT_LATENCY="${SRT_LATENCY:-300}"

# ---------- RTMP ----------
RTMP_PORT="${RTMP_PORT:-1935}"
RTMP_APP="${RTMP_APP:-live}"

# ---------- 管道片段 ----------
SRC="v4l2src device=${V4L2_DEV} ! image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1 ! jpegdec ! videoconvert ! video/x-raw,format=NV12"

# config-interval=1 -> 每个 IDR 前都插入 SPS/PPS，接收端可随时中途加入
#
# AVCC capsfilter 是 RTMP 推流的必需环节（SRT 不需要，但对 SRT 也无害）：
#   mpph264enc 输出 Annex-B（00 00 00 01 起始码），
#   FLV/RTMP 要求 AVCC（4 字节大端长度前缀）。
#   不做这步转换，SRS 会直接丢弃或解不出画面。
#   alignment=au 保证每个 buffer 恰好一个完整访问单元，flvmux 才能正确打 tag。
ENC="mpph264enc bps=${BITRATE} gop=${GOP} \
     ! h264parse config-interval=1 \
     ! video/x-h264,stream-format=avc,alignment=au"

# ---------------------------------------------------------------------------
probe() {
    echo "=== GStreamer 插件自检 ==="
    local missing=0
    for p in v4l2src jpegdec videoconvert mpph264enc h264parse; do
        if gst-inspect-1.0 "$p" >/dev/null 2>&1; then
            echo "  [OK]      $p"
        else
            echo "  [MISSING] $p"
            missing=1
        fi
    done

    if gst-inspect-1.0 srtsink >/dev/null 2>&1; then
        echo "  [OK]      srtsink     (SRT 可用)"
    else
        echo "  [MISSING] srtsink     -> sudo apt install gstreamer1.0-plugins-bad"
    fi

    if gst-inspect-1.0 rtmpsink >/dev/null 2>&1; then
        echo "  [OK]      rtmpsink    (RTMP 可用)"
    else
        echo "  [MISSING] rtmpsink    -> sudo apt install gstreamer1.0-plugins-bad"
    fi

    if gst-inspect-1.0 mpegtsmux >/dev/null 2>&1; then
        echo "  [OK]      mpegtsmux"
    else
        echo "  [MISSING] mpegtsmux   -> sudo apt install gstreamer1.0-plugins-bad"
    fi

    echo
    echo "=== 采集设备 ==="
    if [ -e "${V4L2_DEV}" ]; then
        echo "  [OK]      ${V4L2_DEV} 存在"
    else
        echo "  [MISSING] ${V4L2_DEV} 不存在"
        missing=1
    fi

    echo
    echo "=== 编码器属性速查 ==="
    echo "  运行: gst-inspect-1.0 mpph264enc"
    echo "  重点关注 bps / bps-max / bps-min / gop / rc-mode / profile / level"

    if [ "$missing" -eq 0 ]; then
        echo
        echo "全部必需组件就绪。"
    else
        echo
        echo "有组件缺失，请先安装后再推流。"
    fi
}

# ---------------------------------------------------------------------------
push_srt() {
    echo "SRT 推流 -> srt://${SERVER_IP}:${SRT_PORT}  stream=${STREAM_ID}  latency=${SRT_LATENCY}ms"
    echo "码率 ${BITRATE} bps / GOP ${GOP}"
    echo

    # mode=caller 是关键：由机器人主动向外连接服务器，
    # 这样才能穿过 4G/5G 的运营商 NAT，服务器无需为机器人做端口映射。
    # 断线后 GStreamer 会退出，依赖外部守护（systemd Restart=always）自动重连。
    exec gst-launch-1.0 -v \
        ${SRC} \
        ! ${ENC} \
        ! mpegtsmux alignment=7 \
        ! srtsink uri="srt://${SERVER_IP}:${SRT_PORT}" \
                  mode=caller \
                  latency=${SRT_LATENCY} \
                  streamid="publish:/${STREAM_ID}" \
                  sync=false
}

# ---------------------------------------------------------------------------
push_rtmp() {
    echo "RTMP 推流 -> rtmp://${SERVER_IP}:${RTMP_PORT}/${RTMP_APP}/${STREAM_ID}"
    echo "码率 ${BITRATE} bps / GOP ${GOP}"
    echo
    echo "警告: RTMP 基于 TCP，4G 丢包时会因队头阻塞导致延迟飙升到 10s 以上。"
    echo "      仅在 SRT 不可用、或必须对接只认 RTMP 的下游时使用。"
    echo

    # live=1 关闭 rtmpsink 的发送缓冲，能压掉约 1 秒延迟，但弱网下更容易卡顿
    # streamable=true 生成流式 FLV（不写 duration 字段），直播必须
    exec gst-launch-1.0 -v \
        ${SRC} \
        ! ${ENC} \
        ! flvmux streamable=true \
        ! rtmpsink location="rtmp://${SERVER_IP}:${RTMP_PORT}/${RTMP_APP}/${STREAM_ID} live=1" \
                   sync=false
}

# ---------------------------------------------------------------------------
usage() {
    echo "用法: $0 {probe|srt|rtmp}"
    echo
    echo "  probe  检查 GStreamer 插件与采集设备（首次使用请先执行）"
    echo "  srt    SRT 回传（4G/5G 公网推荐）"
    echo "  rtmp   RTMP 回传（兼容性优先时使用）"
    echo
    echo "环境变量: SERVER_IP  STREAM_ID  BITRATE  WIDTH  HEIGHT  FPS"
    echo "          SRT_PORT  SRT_LATENCY  RTMP_PORT  RTMP_APP  V4L2_DEV"
    echo
    echo "示例:"
    echo "  SERVER_IP=1.2.3.4 STREAM_ID=robot01 $0 srt"
    echo "  BITRATE=800000 WIDTH=640 HEIGHT=480 FPS=25 $0 srt"
}

# ---------------------------------------------------------------------------
if [ "${SERVER_IP}" = "203.0.113.10" ] && [ "${MODE}" != "probe" ]; then
    echo "错误: 请先设置服务器地址。"
    echo "  例: SERVER_IP=1.2.3.4 $0 ${MODE}"
    echo "  或直接编辑本脚本顶部的 SERVER_IP 默认值。"
    exit 1
fi

case "${MODE}" in
    probe) probe ;;
    srt)   push_srt ;;
    rtmp)  push_rtmp ;;
    *)     usage; exit 1 ;;
esac
