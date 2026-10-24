#!/usr/bin/env bash
# ============================================================================
# 安装两个"受控提权入口"到本机（任何跑 m20pro-console 的 AOS 主机）：
#
#   /usr/local/sbin/m20-ap-ctl      WiFi 热点读写（根:根 0755）
#   /usr/local/sbin/m20-video-ctl   推流服务启停（根:根 0755）
#
#   /etc/sudoers.d/m20-ap-ctl       精确 NOPASSWD 白名单（**零通配符**）
#   /etc/sudoers.d/m20-video-ctl    同上
#
# 为什么单独一个脚本：这两个 helper 装在**系统目录**，
#   · deploy/install.sh 只装"控制台本体"（backend/venv/systemd），不碰 /usr/local/sbin；
#   · deploy/_apply.sh 只同步应用目录，也不碰；
#   → 换机器时最容易漏的就是这一步，漏了表现为热点/推流面板报
#     "受控入口不存在或不可执行 —— 请先部署 deploy/m20-ap-ctl"。
#
# 用法：
#   sudo bash deploy/install_helpers.sh              # 目标用户 = sudo 调用者
#   sudo bash deploy/install_helpers.sh djw          # 显式指定目标用户
#   sudo bash deploy/install_helpers.sh --uninstall  # 卸载（控制台本体不受影响）
#
# ⚠️ sudoers 里**必须是实际运行控制台的那个用户**。模板写的是 `user`，
#    本脚本按参数替换 —— 用户名对不上时 sudo -n 会一直报
#    "a password is required"，而 helper 自己还没机会说话，很难查。
#
# 幂等：可重复执行；每次覆盖安装并重写白名单（先 visudo 校验后生效）。
# ============================================================================
set -euo pipefail

SBIN=/usr/local/sbin
SUDOERS_DIR=/etc/sudoers.d
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '\033[1;32m[helpers]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { err "请用 sudo 运行：sudo bash $0"; exit 1; }

# ---------------------------------------------------------------- 卸载分支
if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$SBIN/m20-ap-ctl" "$SBIN/m20-video-ctl" \
          "$SUDOERS_DIR/m20-ap-ctl" "$SUDOERS_DIR/m20-video-ctl"
    log "已卸载两个 helper 与两份 sudoers（控制台服务本身不受影响）"
    exit 0
fi

# ---------------------------------------------------------------- 参数与前置
TARGET_USER="${1:-${SUDO_USER:-user}}"
if [ "$TARGET_USER" = "root" ]; then
    TARGET_USER="${SUDO_USER:-user}"
fi
id -u "$TARGET_USER" >/dev/null 2>&1 || { err "目标用户不存在：$TARGET_USER"; exit 1; }

command -v visudo >/dev/null 2>&1 || { err "未找到 visudo（sudo 未安装？）"; exit 1; }

for f in m20-ap-ctl m20-video-ctl; do
    [ -f "$SRC_DIR/$f" ] || { err "缺少源文件：$SRC_DIR/$f"; exit 1; }
done

log "目标用户：$TARGET_USER   源目录：$SRC_DIR"

# ---------------------------------------------------------------- 1. 装脚本本体
# ⚠️ 先装到临时名再 mv：避免 helper 正在被调用时读到半个文件。
install_helper() {
    local name=$1 tmp
    tmp="$SBIN/.$name.new"
    install -o root -g root -m 0755 "$SRC_DIR/$name" "$tmp"
    mv -f "$tmp" "$SBIN/$name"
    log "已安装 $SBIN/$name"
}
install_helper m20-ap-ctl
install_helper m20-video-ctl

# ---------------------------------------------------------------- 2. 生成并校验 sudoers
# 只替换**行首**的 `user `，不碰注释里出现的 "user" 字样。
install_sudoers() {
    local src=$1 dst=$2 tmp
    tmp="$(mktemp)"
    sed -e "s/^user /${TARGET_USER} /" "$SRC_DIR/$src" > "$tmp"
    # 兜底断言：**每条 NOPASSWD 授权行的首字段必须等于目标用户**。
    # ⚠️ 不能写成 `grep -q '^user '` —— 目标用户恰好就叫 `user` 时会误报
    #    "未替换"（本机就是这种，2026-10-18 踩到）。按字段比对才判得准。
    if ! awk -v u="$TARGET_USER" '
            /^[[:space:]]*#/ { next }
            /NOPASSWD/ && $1 != u { bad = 1 }
            END { exit bad ? 1 : 0 }' "$tmp"; then
        err "$src 里有授权行的用户不是 $TARGET_USER："
        grep -n 'NOPASSWD' "$tmp" >&2 || true
        rm -f "$tmp"
        return 1
    fi
    # ★ 先校验再落盘：sudoers 写坏会让 sudo 全盘失效（包括 sudo -S 自己）
    if ! visudo -c -q -f "$tmp" >/dev/null 2>&1; then
        err "$src 语法校验未过，未安装。临时文件：$tmp"
        visudo -c -f "$tmp" || true
        return 1
    fi
    install -o root -g root -m 0440 "$tmp" "$dst"
    rm -f "$tmp"
    log "已安装 $dst（授权给 $TARGET_USER）"
}
install_sudoers sudoers-m20-ap-ctl    "$SUDOERS_DIR/m20-ap-ctl"
install_sudoers sudoers-m20-video-ctl "$SUDOERS_DIR/m20-video-ctl"

# ---------------------------------------------------------------- 3. 自检
log "自检（以 $TARGET_USER 身份跑 sudo -n）："
run_as() {
    sudo -u "$TARGET_USER" -H bash -lc "$1" 2>&1 || true
}
# ⚠️ 不要 `head -3` 再 grep：`m20-ap-ctl status` **先输出 uplink.* 再输出 ap.***，
#    截断前几行会全是 uplink → 误报"不可用"（2026-10-18 踩到）。
#    改为全量输出、按**行首**匹配。
ap_out=$(run_as "sudo -n $SBIN/m20-ap-ctl status")
if printf '%s\n' "$ap_out" | grep -q '^ap\.'; then
    log "  ✅ m20-ap-ctl 可用（$(printf '%s\n' "$ap_out" | grep -m1 '^ap.state=' || true)）"
else
    warn "  ❌ m20-ap-ctl 不可用：$(printf '%s\n' "$ap_out" | head -3 | tr '\n' ' ')"
    warn "     常见原因：sudoers 授权用户不是 $TARGET_USER；或厂商热点脚本缺失"
fi

vid_out=$(run_as "sudo -n $SBIN/m20-video-ctl status")
if printf '%s\n' "$vid_out" | grep -qE '^(local|relay)\.'; then
    log "  ✅ m20-video-ctl 可用（$(printf '%s\n' "$vid_out" | grep -m1 '^local.ready=' || true)）"
else
    warn "  ❌ m20-video-ctl 不可用：$(printf '%s\n' "$vid_out" | head -3 | tr '\n' ' ')"
    warn "     若本机没有厂商推流链（/opt/robot/scripts/board_resources/rtsp_service/），"
    warn "     这条失败是**预期**的，控制台的其它功能不受影响。"
fi

# ---------------------------------------------------------------- 4. 提示依赖
if [ ! -d /opt/robot/scripts/board_resources/rtsp_service ]; then
    warn "未发现厂商推流目录 —— 「本地推流」面板会报未运行（相机画面不会有图）"
fi
if [ ! -f /opt/robot/scripts/wifi/password ]; then
    warn "未发现厂商热点配置 /opt/robot/scripts/wifi/password —— 热点面板只能读不能写"
fi

cat <<EOF

------------------------------------------------------------------
helper 安装完成。
  两个入口：$SBIN/m20-ap-ctl、$SBIN/m20-video-ctl
  两份白名单：$SUDOERS_DIR/m20-ap-ctl、$SUDOERS_DIR/m20-video-ctl（授权给 $TARGET_USER）

卸载：sudo bash deploy/install_helpers.sh --uninstall
------------------------------------------------------------------
EOF
