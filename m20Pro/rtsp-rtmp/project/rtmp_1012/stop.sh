#!/usr/bin/env bash
# ============================================================================
# stop.sh —— 停止两路推流
#   向 rtmp_forward.sh 发 TERM，由它负责结束 gst 子进程并发 EOS
#     ./stop.sh         停止两路
#     ./stop.sh f       只停前视
#     ./stop.sh b       只停后视
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/run"

GRACE=10   # 等待优雅退出的秒数

stop_one() {
    local stream="$1"
    local pidfile="$PID_DIR/forward-$stream.pid"

    if [ ! -f "$pidfile" ]; then
        echo "[$stream] 未在运行 (无 PID 文件)"
        return 0
    fi
    local pid
    pid="$(cat "$pidfile" 2>/dev/null)"
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        echo "[$stream] 进程已不存在，清理 PID 文件"
        rm -f "$pidfile"
        return 0
    fi

    echo "[$stream] 正在停止 (PID=$pid) ..."
    kill -TERM "$pid" 2>/dev/null

    local w=0
    while kill -0 "$pid" 2>/dev/null && [ "$w" -lt "$GRACE" ]; do
        sleep 1
        w=$((w + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo "[$stream] 优雅退出超时，强制终止"
        kill -KILL "$pid" 2>/dev/null
        sleep 1
    fi

    # 兜底：清掉可能残留的该路 gst 进程
    local leftover
    leftover="$(pgrep -f "rtmpsink.*forward-$stream" 2>/dev/null)"
    if [ -n "$leftover" ]; then
        echo "[$stream] 清理残留 gst 进程: $leftover"
        kill -KILL $leftover 2>/dev/null
    fi

    rm -f "$pidfile"
    echo "[$stream] 已停止"
}

case "${1:-all}" in
    f) stop_one f ;;
    b) stop_one b ;;
    all) stop_one f; stop_one b ;;
    *) echo "用法: $0 [all|f|b]"; exit 2 ;;
esac

echo
"$SCRIPT_DIR/status.sh"
