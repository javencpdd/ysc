#!/usr/bin/env bash
# ============================================================================
# rtmp_forward.sh —— 单路 RTSP -> RTMP 推流器
#
# 用法:  ./rtmp_forward.sh f        # 前视  video1 -> m20pro-f
#        ./rtmp_forward.sh b        # 后视  video2 -> m20pro-b
#
# 设计要点（参考 120 主机方案，并针对本机 H.265 源与实测故障做了加固）:
#
#   1. 每路一个独立进程，进程内自带重连循环
#   2. 推流前先探测目标 TCP 连通性；连续失败达上限则以退出码 3 退出
#      （配合 systemd RestartPreventExitStatus=3 实现"网络长期不可用则停推"）
#   3. 推流前先探测源流是否在线，源断时不空转 gst，避免无谓的报错刷屏
#   4. 看门狗：gst 进程活着但目标连接已死（CLOSE-WAIT/FIN）或发送队列长期积压
#      时，判定推流失效并重启管道
#      —— 这是实测踩到的坑：rtmpsink 在远端断开后不会让 gst 退出，
#         进程看着还活着，其实早就不推了
#   5. ⚠ 管道中禁止使用 drop-on-latency / queue leaky
#      —— 实测：源流中断时这两个设置会让管线陷入 CRITICAL 报错风暴
#         （96 万条/2 分钟）并把 CPU 打到 73%。转码中继不能丢帧，
#         丢了就破坏 H.265 解码链，必须保持完整有序。
#   6. gst-launch 加 -e，收到 TERM 时发 EOS，让 RTMP 端干净断流
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.env
source "$SCRIPT_DIR/config.env"

GIVE_UP_EXIT=3

# 用重命名后的副本调用 gst-launch，避免被上游 restart.sh 的
# `pgrep -f "gst-launch"` 无差别杀掉（见 config.env 第 8 节）
# 注意：必须同时校验"非空 + 可执行"——0 字节文件同样满足 -x，
# 会让 gst 启动即静默退出（实测踩过这个坑）。
if [ -n "${GST_BIN:-}" ] && [ -s "${GST_BIN}" ] && [ -x "${GST_BIN}" ]; then
    GST="$GST_BIN"
else
    GST="${GST_FALLBACK:-/usr/bin/gst-launch-1.0}"
fi

# ---------------------------------------------------------------------------
# 参数解析：f / b
# ---------------------------------------------------------------------------
STREAM="${1:-}"
case "$STREAM" in
    f) SRC="$STREAM_F_SRC"; DST="$STREAM_F_DST"; CPUSET="$CPU_F"; LABEL="m20pro-f (前视 video1)" ;;
    b) SRC="$STREAM_B_SRC"; DST="$STREAM_B_DST"; CPUSET="$CPU_B"; LABEL="m20pro-b (后视 video2)" ;;
    *)
        echo "用法: $0 <f|b>" >&2
        exit 2
        ;;
esac

LOG_DIR="$SCRIPT_DIR/logs"
PID_DIR="$SCRIPT_DIR/run"
LOG_FILE="$LOG_DIR/forward-$STREAM.log"
PID_FILE="$PID_DIR/forward-$STREAM.pid"
mkdir -p "$LOG_DIR" "$PID_DIR"

# ---------------------------------------------------------------------------
# 日志
#   正常运行时由 start.sh / systemd 负责把 stdout 重定向进日志文件；
#   这里只写文件，避免与调用方的重定向叠加造成重复行。
#   CONSOLE_LOG=1 时同时打到终端，便于手动调试。
# ---------------------------------------------------------------------------
rotate_log() {
    [ -f "$LOG_FILE" ] || return 0
    local size
    size=$(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -ge "${LOG_MAX_BYTES:-5242880}" ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null
    fi
}
rotate_log

log() {
    local line
    line="$(date '+%Y-%m-%d %H:%M:%S') [forward-$STREAM] $*"
    printf '%s\n' "$line" >>"$LOG_FILE" 2>/dev/null
    [ "${CONSOLE_LOG:-0}" = "1" ] && printf '%s\n' "$line"
    return 0
}

# ---------------------------------------------------------------------------
# 解析 rtmp://host:port/app/key -> host port
# ---------------------------------------------------------------------------
parse_host_port() {
    local url="$1" rest host port
    rest="${url#*://}"
    rest="${rest%%/*}"
    host="${rest%%:*}"
    if [ "$host" = "$rest" ]; then port="1935"; else port="${rest##*:}"; fi
    [ -n "$port" ] || port="1935"
    printf '%s %s\n' "$host" "$port"
}

read -r RTMP_HOST RTMP_PORT <<<"$(parse_host_port "$DST")"
if [ -z "${RTMP_HOST:-}" ]; then
    log "FATAL 无法从目标地址解析主机: $DST"
    exit 4
fi

SRC_PATH="$(basename "${SRC%%\?*}")"

# ---------------------------------------------------------------------------
# TCP 连通性探测（bash 内建 /dev/tcp + timeout，无需 nc / python）
# ---------------------------------------------------------------------------
probe_tcp() {
    timeout "${PROBE_TIMEOUT:-5}" bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null
}

# ---------------------------------------------------------------------------
# 源流健康探测：源由本机 mediamtx 提供，用它的 HLS 端点判断推流端是否还在
#   —— 只看 RTSP 端口没意义：mediamtx 一直在线，是"推流端(publisher)"会消失
# ---------------------------------------------------------------------------
source_health_url() {
    printf '%s/%s/index.m3u8' "${SOURCE_HEALTH_BASE:-http://127.0.0.1:8888}" "$SRC_PATH"
}

probe_source() {
    [ "${CHECK_SOURCE:-true}" = "true" ] || return 0
    local code
    code="$(curl -s -o /dev/null -m "${SOURCE_PROBE_TIMEOUT:-4}" -w '%{http_code}' \
        "$(source_health_url)" 2>/dev/null)"
    [ "$code" = "200" ]
}

# ---------------------------------------------------------------------------
# 网络/源长期不可用时的诊断快照
# ---------------------------------------------------------------------------
dump_diagnostics() {
    {
        echo "================= 推流自动停止诊断 ================="
        echo "时间        : $(date --iso-8601=seconds 2>/dev/null || date)"
        echo "主机/用户   : $(hostname) / $(whoami)"
        echo "通道        : $LABEL"
        echo "源          : $SRC"
        echo "目标        : $DST  (TCP $RTMP_HOST:$RTMP_PORT)"
        echo "原因        : 连续 $consecutive_failures 次无法建立到 $RTMP_HOST:$RTMP_PORT 的 TCP 连接"
        echo "阈值        : MAX_CONNECT_FAILURES=$MAX_CONNECT_FAILURES  PROBE_TIMEOUT=$PROBE_TIMEOUT"
        echo "编码模式    : SOURCE_CODEC=$SOURCE_CODEC"
        echo "上次 gst 退出码: ${last_exit_code:-未运行}"
        echo "--- ip route get $RTMP_HOST ---"
        ip route get "$RTMP_HOST" 2>&1 | head -3
        echo "--- 本机地址 ---"
        ip -brief addr 2>/dev/null | head -8 || hostname -I
        echo "--- 到目标的 TCP 会话 ---"
        ss -tnp 2>/dev/null | grep "$RTMP_HOST:$RTMP_PORT" || echo "(无已建立连接)"
        echo "--- 源流自检 ---"
        curl -s -o /dev/null -m 5 -w "源HLS=%{http_code}\n" "$(source_health_url)" 2>&1
        echo "===================================================="
    } >>"$LOG_FILE" 2>&1
}

# ---------------------------------------------------------------------------
# 构建 GStreamer 管道（数组形式传给 gst-launch，避免 eval 与引号问题）
# ---------------------------------------------------------------------------
build_pipeline() {
    PIPE=(
        "$GST" -e
        rtspsrc "location=$SRC" protocols=tcp "latency=${LATENCY:-100}"
    )
    # 注意：这里刻意不加 drop-on-latency —— 见文件头第 5 条

    if [ "$SOURCE_CODEC" = "h264" ]; then
        # ---------------- 纯 remux（零转码，同 120 主机方案）----------------
        PIPE+=(
            ! rtph264depay
            ! h264parse config-interval=-1
            ! flvmux streamable=true
            ! rtmpsink "location=$DST live=1"
        )
    else
        # ---------------- H.265 -> H.264 硬件转码 ----------------
        # 源是 loopback，无网络抖动，不需要丢帧；queue 用默认（不设 leaky）
        #
        # ⚠ 色度格式必须用 I420，不能用 NV12！
        #   实测（抓帧对比）：mpph264enc 喂 NV12 会输出严重花屏
        #   （绿紫横向条纹，行步长错位），无论 NV12 来自 videoconvert
        #   还是直接来自 mppvideodec。换成 I420 画面完全正常。
        #   而 mppvideodec 的硬解输出本身是好的（解码后转 RGB 出图正常）。
        PIPE+=(
            ! rtph265depay
            ! h265parse
            ! queue
            ! mppvideodec
            ! videoconvert
            ! "video/x-raw,format=${PIX_FMT:-I420}"
            ! mpph264enc
            "rc-mode=${RC_MODE:-1}"
            "bps=${BPS:-2000000}"
            "bps-max=${BPS_MAX:-2500000}"
            "gop=${GOP:-30}"
            "qp-min=${QP_MIN:-12}"
            "qp-max=${QP_MAX:-45}"
            "header-mode=each-idr"
            ! h264parse config-interval=-1
            ! flvmux streamable=true
            ! queue
            ! rtmpsink "location=$DST live=1"
        )
    fi
}

# ---------------------------------------------------------------------------
# 看门狗：gst 进程活着，但推流其实已经死了 —— 检测出来就重启管道
#   判据：到目标的连接不是 ESTAB，或发送队列长期积压
# ---------------------------------------------------------------------------
watchdog() {
    local pid="$1"
    local waited=0 strikes=0
    local info st sq

    while kill -0 "$pid" 2>/dev/null; do
        sleep "${WATCHDOG_INTERVAL:-5}"
        waited=$((waited + ${WATCHDOG_INTERVAL:-5}))

        info="$(ss -tnp 2>/dev/null | grep "$RTMP_HOST:$RTMP_PORT" \
            | grep "pid=$pid," | awk '{print $1, $3}' | head -1)"
        st="$(printf '%s' "$info" | awk '{print $1}')"
        sq="$(printf '%s' "$info" | awk '{print $2}')"

        if [ -z "$st" ]; then
            # 启动初期连接还没建立，宽限期内不计数
            [ "$waited" -le "${WATCHDOG_GRACE:-25}" ] && continue
            strikes=$((strikes + 1))
            log "看门狗: 未检测到与 $RTMP_HOST:$RTMP_PORT 的连接 ($strikes/${WATCHDOG_STRIKES:-2})"
        elif [ "$st" != "ESTAB" ]; then
            strikes=$((strikes + 1))
            log "看门狗: 目标连接状态异常 [$st] ($strikes/${WATCHDOG_STRIKES:-2})"
        elif [ -n "$sq" ] && [ "$sq" -gt "${STALL_SENDQ:-1000000}" ] 2>/dev/null; then
            strikes=$((strikes + 1))
            log "看门狗: 目标发送队列积压 ${sq}B ($strikes/${WATCHDOG_STRIKES:-2})"
        else
            strikes=0
        fi

        if [ "$strikes" -ge "${WATCHDOG_STRIKES:-2}" ]; then
            log "看门狗: 判定推流已失效，重启管道"
            kill -TERM "$pid" 2>/dev/null
            local w=0
            while kill -0 "$pid" 2>/dev/null && [ "$w" -lt 6 ]; do
                sleep 0.5; w=$((w + 1))
            done
            kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
            return 1
        fi
    done
    return 0
}

# ---------------------------------------------------------------------------
# 清理
# ---------------------------------------------------------------------------
GST_PID=""
WD_PID=""
cleanup() {
    log "收到退出信号，正在关闭推流..."
    [ -n "$WD_PID" ] && kill "$WD_PID" 2>/dev/null
    if [ -n "$GST_PID" ] && kill -0 "$GST_PID" 2>/dev/null; then
        kill -TERM "$GST_PID" 2>/dev/null
        local w=0
        while kill -0 "$GST_PID" 2>/dev/null && [ "$w" -lt 10 ]; do
            sleep 0.5; w=$((w + 1))
        done
        kill -0 "$GST_PID" 2>/dev/null && kill -KILL "$GST_PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
    log "已停止"
    exit 0
}
trap cleanup TERM INT

# ---------------------------------------------------------------------------
# 看门狗可用性判断（需要 root 才能从 ss 读出 socket 归属进程）
# ---------------------------------------------------------------------------
WATCHDOG_ON=true
if [ "$(id -u)" -ne 0 ]; then
    WATCHDOG_ON=false
fi

# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
consecutive_failures=0
source_failures=0
last_exit_code=""

echo "$$" >"$PID_FILE"
log "======================================================"
log "启动推流  通道: $LABEL"
log "源: $SRC"
log "目标: $DST"
log "编码模式: $SOURCE_CODEC    CPU 亲和: $CPUSET"
log "参数: LATENCY=${LATENCY} RETRY=${RETRY_SECONDS}s MAX_FAIL=${MAX_CONNECT_FAILURES} 看门狗=$WATCHDOG_ON"
log "======================================================"

while true; do
    # 1) 目标网络探测（失败累计到上限 => 退出码 3，交给 systemd 决定不再重启）
    if ! probe_tcp "$RTMP_HOST" "$RTMP_PORT"; then
        consecutive_failures=$((consecutive_failures + 1))
        log "目标网络探测失败 $consecutive_failures/$MAX_CONNECT_FAILURES: 无法连接 $RTMP_HOST:$RTMP_PORT"
        if [ "$consecutive_failures" -ge "$MAX_CONNECT_FAILURES" ]; then
            log "达到连续失败上限，自动停止推流（退出码 $GIVE_UP_EXIT）"
            dump_diagnostics
            rm -f "$PID_FILE"
            exit "$GIVE_UP_EXIT"
        fi
        d=$((RETRY_SECONDS * consecutive_failures))
        [ "$d" -gt "${NETWORK_BACKOFF_MAX:-60}" ] && d="${NETWORK_BACKOFF_MAX:-60}"
        sleep "$d"
        continue
    fi
    consecutive_failures=0

    # 2) 源流探测：源没在线就不空转 gst（本机问题，不计入目标失败次数）
    if ! probe_source; then
        source_failures=$((source_failures + 1))
        if [ $((source_failures % 6)) -eq 1 ]; then
            log "源流不在线 ($source_failures 次): $SRC  → 等待上游 mediamtx 推流端恢复"
        fi
        sleep "$RETRY_SECONDS"
        continue
    fi
    source_failures=0

    # 3) 启动管道
    build_pipeline
    if command -v taskset >/dev/null 2>&1 && [ -n "$CPUSET" ]; then
        taskset -c "$CPUSET" "${PIPE[@]}" >>"$LOG_FILE" 2>&1 &
    else
        "${PIPE[@]}" >>"$LOG_FILE" 2>&1 &
    fi
    GST_PID=$!
    log "推流已启动 (gst PID=$GST_PID)"

    # 4) 看门狗
    WD_PID=""
    if [ "$WATCHDOG_ON" = true ]; then
        watchdog "$GST_PID" &
        WD_PID=$!
    fi

    wait "$GST_PID"
    last_exit_code=$?
    [ -n "$WD_PID" ] && kill "$WD_PID" 2>/dev/null
    GST_PID=""
    WD_PID=""
    log "推流进程退出 (rc=$last_exit_code)，${RETRY_SECONDS}s 后重连"

    sleep "$RETRY_SECONDS"
done
