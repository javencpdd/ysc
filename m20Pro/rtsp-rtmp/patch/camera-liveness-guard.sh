#!/bin/bash
# ============================================================================
# camera-liveness-guard —— 相机推流"假死管道"守护
#
# 背景（2026-10-15 故障复盘）：
#   push_video.sh 的监控函数 _is_stream_alive() 只判断「进程是否活着」
#   （kill -0 + pgrep -P <pid> gst-launch + cmdline 含 gst-launch），
#   完全没有「是否真的在发布」的判据。于是出现如下真实故障：
#     · gst-launch 进程存活、持有 /dev/videoN 与 /dev/mpp_service
#     · 但 mpph264enc 每帧报错（~60 条/s 刷 /dev/log），从不向 rtspclientsink 交付数据
#     · sink 从未 ANNOUNCE → MediaMTX 报 "no one is publishing to path 'videoN'"
#     · 中继源探测拿到 404，拒绝起 rtmp-gst → 推流中断且永不自愈
#   该故障 2026-10-15 一天内复现 3 次。
#
# 本守护的思路（刻意"最小侵入"）：
#   不改 push_video.sh 一行代码。push_video.sh 的外层 `while true` 在
#   _is_stream_alive 返回假时会重新拉起管道 —— 所以只要有人把「假死的管道」
#   杀掉，它自己就会重生。本脚本就是那个"杀"的人。
#
# 判据（保守，避免误杀正常流）：
#   1) mediamtx 必须在监听 8554（否则源全断是中继侧问题，杀相机无意义）
#   2) gst-launch 进程已运行超过 GRACE_SEC（新管道需要时间完成 publish）
#   3) 该进程 cmdline 里解析出的 rtspclientsink 目标路径，其 HLS 连续 FAIL_THRESHOLD
#      次非 200 → 判定假死，杀掉该进程（先 TERM 后 KILL）
#
# 用法：
#   camera-liveness-guard.sh --dry-run    # 只报告不动作（首次部署务必先跑这个）
#   camera-liveness-guard.sh              # 实际执行（供 systemd timer 调用）
#
# 退出码：0 = 正常；1 = 参数错误
# ============================================================================

set -u

# ------------------------------- 可调参数 -----------------------------------
HLS_BASE="${HLS_BASE:-http://127.0.0.1:8888}"   # MediaMTX HLS 地址
RTSP_PORT="${RTSP_PORT:-8554}"                  # 用于校验 mediamtx 存活
GRACE_SEC="${GRACE_SEC:-90}"                    # 管道启动后多少秒内不判定（给 publish 留时间）
FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"           # 连续 N 次探测失败才动手
PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}"             # 单次 HLS 探测超时(秒)
STATE_DIR="${STATE_DIR:-/var/lib/cam-guard}"    # 连续失败计数持久化目录
LOG_FILE="${LOG_FILE:-/var/log/cam-guard.log}"  # 动作日志

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "未知参数: $arg" >&2; exit 1 ;;
    esac
done

mkdir -p "$STATE_DIR" 2>/dev/null

log() {
    local msg="$(date '+%F %T') [cam-guard] $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null
}

# --------------------------- 前置：mediamtx 是否在 --------------------------
mediamtx_alive() {
    # 只要 8554 上有监听就算活（不去猜进程名，避免误判）
    (exec 3<>"/dev/tcp/127.0.0.1/${RTSP_PORT}") 2>/dev/null && exec 3<&- && return 0
    return 1
}

# --------------------- 从进程 cmdline 解析出发布路径 -------------------------
# 期望形如：... ! rtspclientsink location=rtsp://127.0.0.1:8554/video1 latency=50
extract_path() {
    local pid="$1"
    tr '\0' '\n' < "/proc/$pid/cmdline" 2>/dev/null \
        | grep -oE 'rtsp://[^/]+/[A-Za-z0-9_.-]+' \
        | head -1 \
        | sed -E 's#.*/([^/]+)$#\1#'
}

# ------------------------------ 进程已运行秒数 ------------------------------
proc_age_sec() {
    local pid="$1"
    local st
    st=$(awk '{print $22}' "/proc/$pid/stat" 2>/dev/null)
    [ -n "$st" ] || { echo 0; return; }
    local up
    up=$(awk '{printf "%d", $1}' /proc/uptime)
    echo $(( up - st / 100 ))
}

# ---------------------------------- 主逻辑 ----------------------------------
main() {
    if ! mediamtx_alive; then
        log "SKIP: mediamtx 未在 :${RTSP_PORT} 监听 —— 源全断属中继侧问题，本守护不动作（避免误杀）"
        exit 0
    fi

    local found=0
    for pid in $(pgrep -x gst-launch-1.0 2>/dev/null); do
        found=1
        local path age
        path=$(extract_path "$pid")
        age=$(proc_age_sec "$pid")

        if [ -z "$path" ]; then
            log "pid=$pid 未能从 cmdline 解析出发布路径，跳过"
            continue
        fi

        if [ "$age" -lt "$GRACE_SEC" ]; then
            log "pid=$pid path=$path 运行 ${age}s < ${GRACE_SEC}s 宽限期，本轮不判定"
            continue
        fi

        local code
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$PROBE_TIMEOUT" \
               "${HLS_BASE}/${path}/index.m3u8" 2>/dev/null)

        local sf="$STATE_DIR/${path}.fails"
        local fails=0
        [ -f "$sf" ] && fails=$(cat "$sf" 2>/dev/null || echo 0)

        if [ "$code" = "200" ]; then
            [ "$fails" -ne 0 ] && log "pid=$pid path=$path HLS=200 已恢复，失败计数清零（原 $fails）"
            echo 0 > "$sf"
            continue
        fi

        fails=$(( fails + 1 ))
        echo "$fails" > "$sf"
        log "pid=$pid path=$path HLS=${code} 连续失败 ${fails}/${FAIL_THRESHOLD}（运行 ${age}s）"

        if [ "$fails" -lt "$FAIL_THRESHOLD" ]; then
            continue
        fi

        # ---- 判定假死 ----
        if [ "$DRY_RUN" -eq 1 ]; then
            log "DRY-RUN: 本应杀掉假死管道 pid=$pid path=$path（HLS 连续 ${fails} 次非 200）"
            continue
        fi

        log "ACTION: 判定假死，终止 pid=$pid path=$path —— push_video.sh 会自动重建该路"
        kill -TERM "$pid" 2>/dev/null
        local w=0
        while kill -0 "$pid" 2>/dev/null && [ "$w" -lt 5 ]; do
            sleep 1; w=$(( w + 1 ))
        done
        if kill -0 "$pid" 2>/dev/null; then
            log "ACTION: TERM 未退出，改用 KILL pid=$pid"
            kill -9 "$pid" 2>/dev/null
        fi
        echo 0 > "$sf"
    done

    if [ "$found" -eq 0 ]; then
        # 一路 gst-launch 都没有：说明 push_video.sh 正在等设备或自身没起来。
        # 本守护不负责拉起 push_video.sh（那属 R19 的上游守护范畴），只告警。
        log "WARN: 未发现任何 gst-launch-1.0 进程（push_video.sh 可能未运行或在等设备）"
    fi
}

main
