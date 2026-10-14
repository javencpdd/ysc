#!/usr/bin/env bash
# ============================================================================
# 安装 m20monitor 到本机（196/AOS 等运行 m20pro-console 的主机）：
#   1) /usr/local/bin/m20monitor            命令本体（0755）
#   2) /etc/sudoers.d/m20-monitor           精确 NOPASSWD 白名单：
#      仅允许目标用户对 m20pro-console.service 做 start/stop/restart/enable/
#      disable —— 免密但不放权（最小提权面），status/log 只读不需要 root。
#
# 用法：
#   sudo bash deploy/install_m20monitor.sh              # 目标用户 = sudo 调用者
#   sudo bash deploy/install_m20monitor.sh user         # 显式指定目标用户
#   sudo bash deploy/install_m20monitor.sh --uninstall  # 卸载命令与白名单
#
# 幂等：可重复执行；每次覆盖安装并重写白名单（先校验后生效）。
# ============================================================================
set -euo pipefail

BIN=/usr/local/bin/m20monitor
SUDOERS=/etc/sudoers.d/m20-monitor
UNIT=m20pro-console.service
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '\033[1;32m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { err "请用 sudo 运行：sudo bash $0"; exit 1; }

# ---------------------------------------------------------------- 卸载分支
if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$BIN" "$SUDOERS"
    log "已卸载：$BIN 与 $SUDOERS（控制台服务本身不受影响）"
    exit 0
fi

# ---------------------------------------------------------------- 参数与前置
TARGET_USER="${1:-${SUDO_USER:-user}}"
if [ "$TARGET_USER" = "root" ]; then
    TARGET_USER="${SUDO_USER:-user}"
fi
id -u "$TARGET_USER" >/dev/null 2>&1 || { err "目标用户不存在：$TARGET_USER"; exit 1; }

SYSTEMCTL="$(command -v systemctl || true)"
[ -n "$SYSTEMCTL" ] || { err "未找到 systemctl"; exit 1; }

[ -f "$SRC_DIR/m20monitor" ] || { err "找不到命令本体 $SRC_DIR/m20monitor（请在项目 deploy/ 目录内运行本脚本）"; exit 1; }

# ---------------------------------------------------------------- 1. 命令本体
install -m 0755 "$SRC_DIR/m20monitor" "$BIN"
log "已安装命令：$BIN"

# ---------------------------------------------------------------- 2. sudoers 白名单
cat > "$SUDOERS" <<EOF
# m20monitor 提权白名单（由 deploy/install_m20monitor.sh 生成，勿手工修改）
# 仅授权用户 $TARGET_USER 对 $UNIT 执行下列管理动作（免密、最小权限）
$TARGET_USER ALL=(root) NOPASSWD: $SYSTEMCTL start $UNIT
$TARGET_USER ALL=(root) NOPASSWD: $SYSTEMCTL stop $UNIT
$TARGET_USER ALL=(root) NOPASSWD: $SYSTEMCTL restart $UNIT
$TARGET_USER ALL=(root) NOPASSWD: $SYSTEMCTL enable $UNIT
$TARGET_USER ALL=(root) NOPASSWD: $SYSTEMCTL disable $UNIT
EOF
chown root:root "$SUDOERS"
chmod 0440 "$SUDOERS"

# 先语法校验再放行：校验失败立即删除，绝不让坏文件影响 sudo 全局
if ! visudo -cf "$SUDOERS" >/dev/null 2>&1; then
    err "sudoers 语法校验失败，已删除 $SUDOERS（不影响系统 sudo）"
    exit 1
fi
log "已写入 sudoers 白名单：$SUDOERS（用户 $TARGET_USER）"

# ---------------------------------------------------------------- 3. 验证（无副作用）
if sudo -u "$TARGET_USER" sudo -n -l 2>/dev/null | grep -q "$UNIT"; then
    log "免密白名单验证通过（sudo -l 已列出 $UNIT 条目）"
else
    warn "白名单验证未通过，请手动检查：sudo -u $TARGET_USER sudo -n -l"
fi

if [ -x "$BIN" ] && "$BIN" status >/dev/null 2>&1; then
    log "命令自检通过（$BIN status 可执行）"
else
    warn "命令自检异常，请手动运行：$BIN status"
fi

cat <<'EOF'

安装完成。常用：
  m20monitor status     查看服务状态（默认命令）
  m20monitor up         启动
  m20monitor down       停止
  m20monitor reset      重启
  m20monitor log f      跟踪日志

远程一步到位（在开发机上，SSH 别名以本机 ssh config 为准）：
  ssh <本机别名> "m20monitor status"
EOF
