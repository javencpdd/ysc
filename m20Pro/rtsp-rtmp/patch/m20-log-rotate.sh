#!/bin/bash
# ============================================================================
# m20-log-rotate —— 日志轮转巡检守护
#
# 为什么需要它（而不是只靠写入方自己检查）：
#   rtmp_forward.sh 里 gst-launch 是这样写日志的（L331/333）：
#       taskset -c "$CPUSET" "${PIPE[@]}" >>"$LOG_FILE" 2>&1 &
#   它由内核直接追加，不经过 shell 的 log() 函数，所以「写入方自己检查大小」
#   这条路径完全盖不住它。GStreamer 在异常时会疯狂刷 WARNING/ERROR
#   （实测 mpph264enc 报错可到 ~60 条/秒），日志增长极快。
#   因此必须有一个独立的、按固定周期巡检的轮转者。
#
# 由 m20-log-rotate.timer 每 60 秒触发一次；也可以手动执行。
#   m20-log-rotate.sh            # 扫描并轮转
#   m20-log-rotate.sh --dry-run  # 只报告哪些文件超限，不动作
#
# 依赖：m20-log.sh（默认从 /home/user/rtmp_1012/lib/ 加载）
# ============================================================================

set -u

CONF_DIR="${CONF_DIR:-/home/user/rtmp_1012}"
CONF_FILE="${CONF_FILE:-$CONF_DIR/config.env}"
LIB_FILE="${LIB_FILE:-$CONF_DIR/lib/m20-log.sh}"

# 载入用户配置（其中可覆盖 M20LOG_* 与 M20LOG_SCAN_DIR）
# shellcheck disable=SC1090
if [ -r "$CONF_FILE" ]; then
    . "$CONF_FILE" 2>/dev/null || true
fi

if [ ! -r "$LIB_FILE" ]; then
    echo "m20-log-rotate: 找不到日志库 $LIB_FILE" >&2
    exit 1
fi
# shellcheck disable=SC1090
. "$LIB_FILE"

# 兼容旧配置项 LOG_MAX_BYTES（若未显式设置 M20LOG_MAX_BYTES）
: "${M20LOG_MAX_BYTES:=${LOG_MAX_BYTES:-10485760}}"
export M20LOG_MAX_BYTES

SCAN_DIR="${M20LOG_SCAN_DIR:-$CONF_DIR/logs}"
SCAN_GLOB="${M20LOG_SCAN_GLOB:-*.log}"

DRY_RUN=0
for a in "$@"; do
    case "$a" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
        *) echo "未知参数: $a" >&2; exit 2 ;;
    esac
done

[ -d "$SCAN_DIR" ] || exit 0

rc=0
for f in "$SCAN_DIR"/$SCAN_GLOB; do
    [ -f "$f" ] || continue
    size=$(stat -c %s "$f" 2>/dev/null || echo 0)
    if [ "$size" -lt "$M20LOG_MAX_BYTES" ]; then
        continue
    fi
    if [ "$DRY_RUN" = "1" ]; then
        printf 'DRY-RUN: %s 大小 %s 字节 >= 上限 %s，本应轮转\n' \
            "$f" "$size" "$M20LOG_MAX_BYTES"
        continue
    fi
    M20LOG_VERBOSE=1 m20log_rotate "$f" || rc=1
done

exit "$rc"
