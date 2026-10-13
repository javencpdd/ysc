#!/usr/bin/env bash
# ============================================================================
# status.sh —— 查看两路推流状态
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.env
source "$SCRIPT_DIR/config.env"

PID_DIR="$SCRIPT_DIR/run"
LOG_DIR="$SCRIPT_DIR/logs"

show_one() {
    local stream="$1" label="$2" src="$3" dst="$4"
    local pidfile="$PID_DIR/forward-$stream.pid"
    local logfile="$LOG_DIR/forward-$stream.log"

    printf '%-28s ' "$label"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile" 2>/dev/null)" 2>/dev/null; then
        local pid gstpid aff
        pid="$(cat "$pidfile")"
        gstpid="$(pgrep -P "$pid" -f rtspsrc 2>/dev/null | head -1)"
        printf '运行中  PID=%s\n' "$pid"

        if [ -n "$gstpid" ]; then
            local cpu
            cpu="$(ps -o %cpu= -p "$gstpid" 2>/dev/null | tr -d ' ')"
            aff="$(taskset -cp "$gstpid" 2>/dev/null | sed 's/.*: //')"
            printf '%-28s   └─ gst PID=%s  亲和=%s  CPU=%s%%\n' "" "$gstpid" "${aff:-?}" "${cpu:-?}"
        else
            printf '%-28s   └─ (gst 子进程未就绪：源未上线或正在重试)\n' ""
        fi
    else
        printf '未运行\n'
    fi
    printf '%-28s   源: %s\n' "" "$src"
    printf '%-28s   目标: %s\n' "" "$dst"
    if [ -f "$logfile" ]; then
        printf '%-28s   最近日志: %s\n' "" "$(tail -n 1 "$logfile" 2>/dev/null | tr -d '\000')"
    fi
}

echo "==================== rtmp_1012 推流状态 ===================="
show_one f "m20pro-f (前视 video1)" "$STREAM_F_SRC" "$STREAM_F_DST"
echo
show_one b "m20pro-b (后视 video2)" "$STREAM_B_SRC" "$STREAM_B_DST"
echo "==========================================================="
echo "源编码模式: $SOURCE_CODEC    目标基址: $RTMP_BASE"
