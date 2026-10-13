#!/usr/bin/env bash
# ============================================================================
# run_all.sh —— 前台运行两路推流（供 systemd 使用）
#   手动启停请用 start.sh / stop.sh，或 m20video 命令
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

P1=""; P2=""

stop_children() {
    [ -n "$P1" ] && kill -TERM "$P1" 2>/dev/null
    [ -n "$P2" ] && kill -TERM "$P2" 2>/dev/null
    [ -n "$P1" ] && wait "$P1" 2>/dev/null
    [ -n "$P2" ] && wait "$P2" 2>/dev/null
}

on_signal() {
    echo "[run_all] 收到停止信号，正在关闭两路..."
    stop_children
    echo "[run_all] 已全部停止"
    exit 0
}
trap on_signal TERM INT

"$SCRIPT_DIR/rtmp_forward.sh" f &
P1=$!
"$SCRIPT_DIR/rtmp_forward.sh" b &
P2=$!

echo "[run_all] 已启动 forward-f(pid=$P1) 与 forward-b(pid=$P2)"

# 任一路退出 -> 收掉另一路并整体退出，由 systemd 重建（避免半死不活状态）
wait -n
RC=$?
echo "[run_all] 检测到某一路退出 (rc=$RC)，整体退出以便上层重建"
stop_children
exit "$RC"
