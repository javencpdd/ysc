#!/usr/bin/env bash
# ============================================================================
# start.sh —— 启动两路 RTSP -> RTMP 推流
#   PID 文件由 rtmp_forward.sh 自己维护 (run/forward-{f,b}.pid)
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# shellcheck source=config.env
source "$SCRIPT_DIR/config.env"

PID_DIR="$SCRIPT_DIR/run"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

if [ ! -x /usr/bin/gst-launch-1.0 ]; then
    echo "错误: 未找到 /usr/bin/gst-launch-1.0"
    exit 1
fi

# 准备重命名后的 gst 副本（规避上游 restart.sh 的无差别 pkill，见 config.env 第 8 节）
# 必须校验非空且真的能跑：0 字节文件也是"可执行"的，会导致静默不推流
prepare_gst() {
    local src="${GST_FALLBACK:-/usr/bin/gst-launch-1.0}"
    [ -n "${GST_BIN:-}" ] || return 0

    if [ -s "$GST_BIN" ] && [ -x "$GST_BIN" ] && "$GST_BIN" --version >/dev/null 2>&1; then
        return 0
    fi

    rm -f "$GST_BIN"
    mkdir -p "$(dirname "$GST_BIN")"
    cp -f "$src" "$GST_BIN" 2>/dev/null && chmod 0755 "$GST_BIN" 2>/dev/null

    if [ -s "$GST_BIN" ] && "$GST_BIN" --version >/dev/null 2>&1; then
        echo "已创建隔离副本: $GST_BIN ($(stat -c '%s' "$GST_BIN") bytes)"
    else
        echo "警告: 隔离副本不可用，将回退使用 $src"
        echo "      (该进程可能在相机服务重启时被误杀)"
    fi
}
prepare_gst

# MPP 硬解硬编需要访问 /dev/mpp_service (root:root 600)
if [ "$(id -u)" -ne 0 ] && [ ! -r /dev/mpp_service ]; then
    if [ "$SOURCE_CODEC" = "h265" ]; then
        echo "警告: 当前非 root 且无权限访问 /dev/mpp_service。"
        echo "      H.265 转码会失败，建议使用: sudo $0"
    fi
fi

start_one() {
    local stream="$1" label="$2"
    local pidfile="$PID_DIR/forward-$stream.pid"
    local logfile="$LOG_DIR/forward-$stream.log"

    if [ -f "$pidfile" ]; then
        local old
        old="$(cat "$pidfile" 2>/dev/null)"
        if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
            echo "[$stream] 已在运行 (PID=$old)，跳过"
            return 0
        fi
        rm -f "$pidfile"
    fi

    echo "[$stream] 启动 $label ..."
    # 日志由 rtmp_forward.sh 独占（它把自身日志与 gst 输出都写进同一个文件），
    # 这里只把无关的 stdout/stderr 丢掉，避免重复行与轮转时 fd 追不上。
    setsid "$SCRIPT_DIR/rtmp_forward.sh" "$stream" >/dev/null 2>&1 < /dev/null &
    disown 2>/dev/null || true

    # 等待转发器写出自己的 PID 文件
    local i=0
    while [ "$i" -lt 20 ]; do
        if [ -s "$pidfile" ]; then break; fi
        sleep 0.3
        i=$((i + 1))
    done

    if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "[$stream] 已启动 (PID=$(cat "$pidfile"))  日志: $logfile"
    else
        echo "[$stream] 启动失败或秒退，请查看 $logfile"
        tail -n 15 "$logfile" 2>/dev/null | sed 's/^/    /'
        return 1
    fi
}

rc=0
start_one f "m20pro-f (前视 video1)" || rc=1
start_one b "m20pro-b (后视 video2)" || rc=1

echo
"$SCRIPT_DIR/status.sh"
exit $rc
