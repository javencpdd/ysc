#!/usr/bin/env bash
# ============================================================================
# 从**外部主机**（PC）一条命令把控制台装到 M20 —— 远程首次安装。
#
# ★ 目标一律用 **user@ip** 形式（不依赖 ~/.ssh/config 里的主机别名）：
#    · 别名看不出"到底连的哪台"，换机器还要先去改 SSH 配置；
#    · user@ip 一眼看得出身份与地址，报错时也好定位。
#
# 与另外几个脚本的分工：
#   · install_remote.sh  ← 本脚本：PC 驱动，**首次安装**（预检 → 上传 → install.sh → 验收）
#   · deploy_196.sh      ← PC 驱动，**日常迭代**（增量 rsync，要求已装过）
#   · deploy_196_tar.sh  ← PC 驱动，日常迭代的 tar 降级版（无 rsync 时用）
#   · _apply.sh          ← **M20 本地**执行：应用一个 tarball（迭代与首次都可）
#   · install.sh         ← **M20 本地**执行：真正安装（venv/依赖/systemd/helper）
#
# 也就是：**安装动作永远在 M20 上跑**，本脚本把"上传 + 预检 + 调用 + 验收"串成一条命令。
#
# 用法：
#   bash deploy/install_remote.sh --check user@192.168.0.196        # 只测连通性，不装
#   bash deploy/install_remote.sh user@192.168.0.196                # 装到 /home/user/m20monitor
#   bash deploy/install_remote.sh user@192.168.0.196 /opt/m20monitor
#
# 环境变量：
#   M20_SUDO_PASS   远端 sudo 口令（默认 半角单引号 '）
#   M20_USER        参数没写 user@ 时补的用户名（默认 user）
#
# 选项：
#   --check            只做连通性与就绪检查，然后退出（推荐先跑这个）
#   --skip-preflight   跳过远程预检（**不推荐**：预检会挡掉版本/路径问题）
#   --skip-build       不自动构建前端（默认 dist 缺失时尝试 npm run build）
#   --force            目标已装过也继续（默认遇到已有安装会停手，提示用 _apply.sh）
#   -h|--help          帮助
#
# 前置：本机能 ssh 到目标机（免密或已接纳主机指纹），且该机 sudo 可用。
# ============================================================================
set -euo pipefail

# ---------------------------------------------------------------- 参数解析
M20_USER_DEFAULT="${M20_USER:-user}"
HOST_RAW=""
INSTALL_DIR=""
DO_CHECK=0
DO_PREFLIGHT=1
DO_BUILD=1
FORCE=0
POS=()

for a in "$@"; do
    case "$a" in
        --check)          DO_CHECK=1 ;;
        --skip-preflight) DO_PREFLIGHT=0 ;;
        --skip-build)     DO_BUILD=0 ;;
        --force)          FORCE=1 ;;
        -h|--help)
            sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*)
            printf '\033[1;31m[error]\033[0m 未知选项：%s\n' "$a" >&2
            exit 2 ;;
        *) POS+=("$a") ;;
    esac
done

HOST_RAW="${POS[0]:-}"
INSTALL_DIR="${POS[1]:-/home/user/m20monitor}"

if [[ -z "$HOST_RAW" ]]; then
    printf '\033[1;31m[error]\033[0m 缺少目标机。用法：bash deploy/install_remote.sh --check user@192.168.0.196\n' >&2
    exit 2
fi

# ---- 规范化成 user@host：没写 @ 就补默认用户名，并**明确告诉你补了什么**
case "$HOST_RAW" in
    *@*) HOST="$HOST_RAW" ;;
    *)   HOST="${M20_USER_DEFAULT}@${HOST_RAW}"
         printf '\033[1;33m[warn]\033[0m 参数没写 "user@"，已按 %s 处理\n' "$HOST" >&2
         printf '        若不是这个用户，请显式写：%s@%s（或用 M20_USER=xxx 覆盖）\n' "$M20_USER_DEFAULT" "$HOST_RAW" >&2 ;;
esac

SSH_USER="${HOST%@*}"
SSH_ADDR="${HOST#*@}"

SUDO_PASS="${M20_SUDO_PASS:-}"
[ -z "$SUDO_PASS" ] && SUDO_PASS="'"

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TGZ="/tmp/m20console_remote.tgz"
STAGE="/tmp/m20stage.$$"          # 时间戳化：避免上次 root 解包留下的目录删不掉

log()  { printf '\033[1;32m[remote]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m  %s\n' "$*"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

log "目标: $HOST:$INSTALL_DIR"
log "身份: ssh 用户=$SSH_USER  地址=$SSH_ADDR"
[[ -n "${POS[1]:-}" ]] || log "安装目录: 未指定，用默认 $INSTALL_DIR"

# ---------------------------------------------------------------- 连通性
# 先测裸 TCP/SSH，再测"能不能真跑命令"，最后测 sudo —— 三层分开报，便于定位。
conn_check() {
    local ok=0
    log "① SSH 可连接性"
    if ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST" 'true' 2>/dev/null; then
        log "   ✅ 免密可达（BatchMode 成功）"
    elif ssh -o ConnectTimeout=8 "$HOST" 'true' 2>/dev/null; then
        warn "   ⚠️  可达，但需要口令 → 本脚本会多次连接，建议先 ssh-copy-id"
    else
        err "   ❌ 连不上 $HOST"
        err "      排查：① ping $SSH_ADDR   ② nc -vz $SSH_ADDR 22   ③ ssh $HOST 手动试一次"
        err "            ④ 确认用户名对不对（不是写 $SSH_ADDR 而是 $HOST？）"
        return 1
    fi

    log "② 远端身份与系统"
    ssh "$HOST" 'printf "   hostname=%s\n   user=%s\n   kernel=%s\n   uptime=%s\n" \
        "$(hostname)" "$(id -un)" "$(uname -r)" "$(uptime -p 2>/dev/null || uptime)"' || ok=1

    log "③ sudo 可用性（用 M20_SUDO_PASS）"
    if printf '%s\n' "$SUDO_PASS" | ssh "$HOST" "sudo -S -p '' id -un" 2>/dev/null | grep -q '^root$'; then
        log "   ✅ sudo 通过"
    else
        err "   ❌ sudo 失败 —— 口令不对（当前默认是半角单引号 '），或该用户不在 sudoers"
        err "      覆盖口令：M20_SUDO_PASS='你的口令' bash $0 ..."
        ok=1
    fi

    log "④ 关键前置（速览，完整检查跑 tools/preflight_new_host.sh）"
    ssh "$HOST" '
        command -v python3 >/dev/null && echo "   ✅ python3: $(python3 -V 2>&1)" || echo "   ❌ 无 python3"
        command -v systemctl >/dev/null && echo "   ✅ systemd 在" || echo "   ❌ 无 systemd"
        if ss -lun 2>/dev/null | grep -q ":30000"; then echo "   ✅ basic_server 30000/udp 在听"; else echo "   ❌ 30000/udp 没在听"; fi
        if [ -f /opt/robot/share/basic_server/bin/basic_server ]; then echo "   ✅ basic_server 二进制在"; else echo "   ❌ 找不到 basic_server（可能不是 M20 Pro）"; fi
        if [ -e '"$INSTALL_DIR"' ]; then echo "   ⚠️  安装目录已存在：'"$INSTALL_DIR"'"; else echo "   ✅ 安装目录尚未存在：'"$INSTALL_DIR"'"; fi
    ' || true

    return $ok
}

log "[0/6] 连通性检查"
if ! conn_check; then
    err "连通性/前置不满足，已停止（未做任何更改）"
    exit 1
fi
if [[ "$DO_CHECK" == "1" ]]; then
    echo
    log "--check 模式：检查完毕，未做任何更改。"
    log "去掉 --check 即可开始安装。"
    exit 0
fi

# ---------------------------------------------------------------- 1. 前端
if [[ "$DO_BUILD" == "1" && ! -d "$LOCAL_DIR/frontend/dist" ]]; then
    if command -v npm >/dev/null 2>&1; then
        log "[1/6] 未发现 frontend/dist，尝试本地构建"
        ( cd "$LOCAL_DIR/frontend" && npm run build ) || { err "前端构建失败"; exit 1; }
    else
        err "未发现 frontend/dist 且本机无 npm —— 请在能构建的机器上 npm run build 后重试"
        exit 1
    fi
else
    log "[1/6] 前端产物已就绪"
fi

# ---------------------------------------------------------------- 2. 打包
log "[2/6] 打包"
bash "$LOCAL_DIR/deploy/pack.sh" "$TGZ" >/dev/null
[[ -s "$TGZ" ]] || { err "打包失败"; exit 1; }
log "      $TGZ  $(du -h "$TGZ" | awk '{print $1}')"

# ---------------------------------------------------------------- 3. 上传
log "[3/6] 上传（预检脚本 + 部署包）"
scp -q "$LOCAL_DIR/tools/preflight_new_host.sh" "$HOST:/tmp/m20preflight.sh"
scp -q "$TGZ" "$HOST:/tmp/m20console_remote.tgz"
log "      已上传"

# ---------------------------------------------------------------- 4. 预检
if [[ "$DO_PREFLIGHT" == "1" ]]; then
    log "[4/6] 远程预检（环境 + 安装路径）"
    set +e
    printf '%s\n' "$SUDO_PASS" | ssh "$HOST" \
        "sudo -S -p '' bash /tmp/m20preflight.sh '$INSTALL_DIR'" 2>&1 | tail -30
    rc=${PIPESTATUS[1]:-1}
    set -e
    if [[ "$rc" != "0" ]]; then
        err "预检未通过（退出码 $rc）——先按上面 ❌ 项修好，或用 --skip-preflight 强装（不建议）"
        exit 1
    fi
    log "      预检通过"
else
    warn "[4/6] 已按要求跳过预检"
fi

# ---------------------------------------------------------------- 5. 已有安装检查
log "[5/6] 检查是否已安装"
if ssh "$HOST" "test -f '$INSTALL_DIR/backend/main.py'" 2>/dev/null; then
    if [[ "$FORCE" != "1" ]]; then
        err "目标已有控制台：$INSTALL_DIR"
        err "  日常迭代请用： bash deploy/_apply.sh 路径（见文档）"
        err "  确实要重装请加 --force（会重建 venv、重装依赖，较慢）"
        exit 1
    fi
    warn "目标已存在，--force 指定：重装（会重建 venv 并重装依赖）"
fi

# ---------------------------------------------------------------- 6. 安装
log "[6/6] 远程安装（解包到 $STAGE 后执行 install.sh）"
# ⚠️ 以**普通用户**解包（不要用 sudo 解），否则这个目录下次删不掉
ssh "$HOST" "rm -rf '$STAGE' && mkdir -p '$STAGE' && tar xzf /tmp/m20console_remote.tgz -C '$STAGE'" \
    || { err "解包失败"; exit 1; }

printf '%s\n' "$SUDO_PASS" | ssh "$HOST" \
    "sudo -S -p '' bash '$STAGE/m20pro_console/deploy/install.sh' '$INSTALL_DIR'" 2>&1 \
    | grep -vE '^\[sudo\]' | tail -40

# ---------------------------------------------------------------- 验收
log "验收"
ssh "$HOST" "curl -s -m 8 http://127.0.0.1:8080/health" || true
echo
USER_NOW=$(ssh "$HOST" "systemctl show m20pro-console -p User --value" 2>/dev/null || echo '?')
ACTIVE=$(ssh "$HOST" "systemctl is-active m20pro-console" 2>/dev/null || echo '?')
echo
log "服务: $ACTIVE   运行用户: $USER_NOW"
if [[ "$USER_NOW" == "root" ]]; then
    warn "运行用户是 root！请用普通用户执行（别以 root 直接跑），或改单元 User= 后重载"
fi
log "访问: http://${SSH_ADDR}:8080/"

echo
log "清理远端中转文件"
ssh "$HOST" "rm -rf '$STAGE' /tmp/m20console_remote.tgz /tmp/m20preflight.sh" 2>/dev/null || true
log "完成"
