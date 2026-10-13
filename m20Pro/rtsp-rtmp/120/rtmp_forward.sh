#!/usr/bin/env bash
# Relay the existing local H.264 RTSP stream to the external RTMP endpoint.
# The camera remains owned by rtsp_stream.service; this process never opens /dev/video0.
#
# 网络不可达保护：
#   每轮推流前先探测到 RTMP 服务器的 TCP 连通性；连续 MAX_CONNECT_FAILURES 次失败后，
#   写出诊断日志并以退出码 3 退出。配合单元里的 RestartPreventExitStatus=3 /
#   SuccessExitStatus=3，systemd 不再重启该服务，即“自动关闭推流”。
set -u

source_url="${SOURCE_URL:-rtsp://127.0.0.1:8554/test}"
target_url="${RTMP_TARGET_URL:-rtmp://172.31.68.227:1936/live/lite3}"
retry_seconds="${RETRY_SECONDS:-5}"
max_connect_failures="${MAX_CONNECT_FAILURES:-3}"
probe_timeout="${PROBE_TIMEOUT:-5}"
log_file="${RTMP_FORWARD_LOG:-/home/ysc/rtsp_stream/logs/rtmp_forward.log}"
give_up_exit_code=3

mkdir -p "$(dirname "$log_file")" 2>/dev/null

log() {
    printf "%s %s\n" "$(date --iso-8601=seconds)" "$*" >> "$log_file" 2>/dev/null
    printf "%s %s\n" "$(date --iso-8601=seconds)" "$*"
}

# 从 rtmp://host:port/app/key 解析出 host 与 port
parse_host_port() {
    local url="$1" rest host port
    rest="${url#*://}"
    rest="${rest%%/*}"
    host="${rest%%:*}"
    if [ "$host" = "$rest" ]; then port="1935"; else port="${rest##*:}"; fi
    if [ -z "$port" ]; then port="1935"; fi
    printf "%s %s\n" "$host" "$port"
}

read -r rtmp_host rtmp_port <<<"$(parse_host_port "$target_url")"
if [ -z "${rtmp_host:-}" ]; then
    log "无法从 target_url 解析主机: $target_url"
    exit 4
fi

# TCP 连通性探测：能连上返回 0，否则非 0
probe_tcp() {
    timeout "$probe_timeout" python3 - "$1" "$2" <<'PY' 2>/dev/null
import socket, sys
try:
    s = socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=3)
    s.close()
except Exception:
    sys.exit(1)
PY
}

dump_diagnostics() {
    {
        echo "=============== 推流自动关闭诊断 ==============="
        echo "时间: $(date --iso-8601=seconds)"
        echo "主机: $(hostname)  用户: $(whoami)"
        echo "目标: $target_url  (TCP $rtmp_host:$rtmp_port)"
        echo "源流: $source_url"
        echo "原因: 连续 $consecutive_failures 次无法建立到 $rtmp_host:$rtmp_port 的 TCP 连接"
        echo "阈值: MAX_CONNECT_FAILURES=$max_connect_failures  PROBE_TIMEOUT=$probe_timeout"
        echo "最近一次转发进程退出码: ${last_exit_code:-未运行}"
        echo "--- ip route get $rtmp_host ---"
        ip route get "$rtmp_host" 2>&1 | head -3
        echo "--- 网卡地址 ---"
        ip -brief addr 2>/dev/null | head -6 || hostname -I
        echo "--- 到目标的 TCP 会话 ---"
        ss -tnp 2>/dev/null | grep "$rtmp_host:$rtmp_port" || echo "(无已建立连接)"
        echo "--- 源流自检(HLS) ---"
        curl -s -o /dev/null -w "HLS=%{http_code}\n" http://127.0.0.1:8888/test/index.m3u8 2>&1
        echo "==============================================="
    } >> "$log_file" 2>&1
}

consecutive_failures=0
last_exit_code=""

log "转发服务启动: $source_url -> $target_url (RTMP 目标 TCP $rtmp_host:$rtmp_port)"

while true; do
    if ! probe_tcp "$rtmp_host" "$rtmp_port"; then
        consecutive_failures=$((consecutive_failures + 1))
        log "连接失败 $consecutive_failures/$max_connect_failures: 无法建立到 $rtmp_host:$rtmp_port 的 TCP 连接"
        if [ "$consecutive_failures" -ge "$max_connect_failures" ]; then
            log "达到连续失败上限，自动关闭推流服务（退出码 $give_up_exit_code，systemd 不再重启）"
            dump_diagnostics
            exit "$give_up_exit_code"
        fi
        sleep "$retry_seconds"
        continue
    fi

    consecutive_failures=0
    log "启动转发: $source_url -> $target_url"

    /usr/bin/gst-launch-1.0 -e \
        rtspsrc location="$source_url" protocols=tcp latency=200 ! \
        rtph264depay ! \
        h264parse config-interval=-1 ! \
        flvmux streamable=true ! \
        rtmpsink location="$target_url live=1"
    exit_code=$?
    last_exit_code="$exit_code"

    log "转发进程退出，状态码 $exit_code；${retry_seconds} 秒后重试"
    sleep "$retry_seconds"
done
