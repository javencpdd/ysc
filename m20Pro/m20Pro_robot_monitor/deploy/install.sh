#!/usr/bin/env bash
#
# 在 **196（AOS）** 上安装 M20 Pro 控制台。
#
# 用法（默认装到 /home/djw/monitor）：
#   sudo bash deploy/install.sh
#   sudo bash deploy/install.sh /home/djw/monitor     # 显式指定
#
# 运行用户：优先用安装目录的属主（如 /home/djw → djw）；若该用户不存在，
#   则退回 sudo 调用者（如 user），避免 systemd 因 User= 不存在而启动失败。
#
# 已知坑（本脚本已逐一处理）：
#   1) 196 是 python3.8 且 **缺 ensurepip** → `python3 -m venv` 会失败 → 自动装 python3.8-venv；
#   2) 196 系统时钟被拉回 2024（上游 NTP 就是错的）→ **HTTPS/TLS 全废**
#      → pip 走 **http 镜像 + --trusted-host**，绕开证书校验；
#   3) 196 缺依赖时 apt 也可能受时钟影响 → apt 默认走 http，通常可用。
#
set -euo pipefail

# ⚠️ 日志函数必须定义在**任何调用之前**：set -e 下调用未定义函数会以
#    127（command not found）静默退出，且没有任何输出（实测踩过，极难排查）。
log()  { echo -e "\033[1;32m[install]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
err()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

INSTALL_DIR="${1:-/home/djw/monitor}"
SERVICE_NAME="m20pro-console"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 运行用户：取安装目录的属主（/home/djw/monitor → djw），不存在则退回 sudo 调用者
OWNER_FROM_PATH="$(basename "$(dirname "$INSTALL_DIR")")"
if [[ "$INSTALL_DIR" == /home/* ]] && id -u "$OWNER_FROM_PATH" >/dev/null 2>&1; then
    RUN_USER="$OWNER_FROM_PATH"
else
    RUN_USER="${SUDO_USER:-$(id -un)}"
    [[ "$OWNER_FROM_PATH" != "home" ]] && \
        warn "用户 $OWNER_FROM_PATH 不存在，服务将以 $RUN_USER 运行（如需 djw 用户请先 useradd）"
fi
PIP_INDEX="${PIP_INDEX:-http://mirrors.aliyun.com/pypi/simple/}"
PIP_TRUSTED="${PIP_TRUSTED:-mirrors.aliyun.com}"

[[ $EUID -eq 0 ]] || { err "请用 sudo 运行"; exit 1; }

log "安装目录: $INSTALL_DIR  运行用户: $RUN_USER"
log "pip 源: $PIP_INDEX（http，绕开 TLS/时钟问题）"

# ---------------------------------------------------------------- 1. 目录与文件
log "[1/7] 准备目录并复制文件"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/hls"

# ⚠️ 必须用 "src/." 的写法：直接 `cp -r src dst/`，当 dst/<name> 已存在时
#    GNU cp 会把源目录**拷进目标内部**（变成 dst/backend/backend），
#    导致服务仍跑旧代码而"改了不生效"（实测踩过）。
copy_dir() {   # copy_dir <源> <目标>
    local src="$1" dst="$2"
    mkdir -p "$dst"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete "$src/" "$dst/"
    else
        rm -rf "$dst"
        mkdir -p "$dst"
        cp -r "$src/." "$dst/"
    fi
}

copy_dir "$SRC_DIR/backend" "$INSTALL_DIR/backend"
[[ -d "$SRC_DIR/frontend/dist" ]] && copy_dir "$SRC_DIR/frontend/dist" "$INSTALL_DIR/frontend/dist" \
    || warn "未发现 frontend/dist，将只提供 API"
[[ -d "$SRC_DIR/tools" ]] && copy_dir "$SRC_DIR/tools" "$INSTALL_DIR/tools" || true
[[ -d "$SRC_DIR/note" ]] && copy_dir "$SRC_DIR/note" "$INSTALL_DIR/note" || true
# 清理历史遗留的嵌套目录（旧版 cp -r 造成的 backend/backend）
rm -rf "$INSTALL_DIR/backend/backend" 2>/dev/null || true
[[ -f "$SRC_DIR/requirements.txt" ]] && cp "$SRC_DIR/requirements.txt" "$INSTALL_DIR/" || true
[[ -f "$SRC_DIR/config.example.toml" ]] && cp "$SRC_DIR/config.example.toml" "$INSTALL_DIR/" || true

# ---------------------------------------------------------------- 2. 虚拟环境
log "[2/7] 创建虚拟环境（多层降级）"
PY_BIN="$(command -v python3 || true)"
[[ -n "$PY_BIN" ]] || { err "未找到 python3"; exit 1; }
log "python3: $PY_BIN ($("$PY_BIN" -V 2>&1))"

VENV_OK=0
if "$PY_BIN" -m venv "$INSTALL_DIR/venv" 2>/dev/null; then
    VENV_OK=1
else
    warn "venv 创建失败（多半缺 ensurepip），尝试安装 python3.8-venv ..."
    if apt-get install -y python3.8-venv python3-pip >/dev/null 2>&1; then
        "$PY_BIN" -m venv "$INSTALL_DIR/venv" && VENV_OK=1
    else
        warn "apt 安装 python3.8-venv 失败，尝试 virtualenv ..."
        "$PY_BIN" -m pip install --user virtualenv >/dev/null 2>&1 || true
        if "$PY_BIN" -m virtualenv "$INSTALL_DIR/venv" >/dev/null 2>&1; then
            VENV_OK=1
        fi
    fi
fi

if [[ $VENV_OK -eq 1 ]]; then
    PIP_CMD="$INSTALL_DIR/venv/bin/pip"
    PY_CMD="$INSTALL_DIR/venv/bin/python"
    log "虚拟环境就绪: $INSTALL_DIR/venv"
else
    warn "无法创建虚拟环境，回退到 pip3 --user（系统级安装）"
    PIP_CMD="$PY_BIN -m pip --user"
    PY_CMD="$PY_BIN"
fi

# ---------------------------------------------------------------- 3. 依赖
log "[3/7] 安装依赖（http 镜像 + --trusted-host）"
# shellcheck disable=SC2086
$PIP_CMD install --upgrade pip >/dev/null 2>&1 || warn "pip 自升级失败，继续"
# shellcheck disable=SC2086
if $PIP_CMD install -r "$INSTALL_DIR/requirements.txt" \
        -i "$PIP_INDEX" --trusted-host "$PIP_TRUSTED" >/tmp/m20_pip.log 2>&1; then
    log "依赖安装完成"
else
    warn "依赖安装可能失败，日志尾部："
    tail -5 /tmp/m20_pip.log 2>/dev/null || true
    warn "可手动重试：PIP_INDEX=$PIP_INDEX $PIP_CMD install -r $INSTALL_DIR/requirements.txt -i $PIP_INDEX --trusted-host $PIP_TRUSTED"
fi

# ---------------------------------------------------------------- 4. 权限
log "[4/7] 设置权限"
chown -R "$RUN_USER":"$RUN_USER" "$INSTALL_DIR"
chmod -R u+rwX "$INSTALL_DIR"

# ---------------------------------------------------------------- 5. systemd
log "[5/7] 安装 systemd 单元"
UNIT_SRC="$SRC_DIR/deploy/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ -f "$UNIT_SRC" ]]; then
    # 把单元里的路径替换为实际安装目录（支持装到非默认目录）
    # 兼容两种字面量：当前默认 /home/djw/monitor 与历史默认 /userdata/m20pro-console
    sed -e "s#/home/djw/monitor#$INSTALL_DIR#g" \
        -e "s#/userdata/m20pro-console#$INSTALL_DIR#g" \
        -e "s#^User=.*#User=$RUN_USER#" \
        -e "s#^Group=.*#Group=$RUN_USER#" \
        "$UNIT_SRC" > "$UNIT_DST"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
    log "已安装并启用: $UNIT_DST"
else
    err "未找到 $UNIT_SRC"
    exit 1
fi

# ---------------------------------------------------------------- 6. 启动与验证
log "[6/7] 启动服务"
systemctl restart "$SERVICE_NAME"
sleep 5
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "服务已启动 ✅"
else
    err "服务未起来，最近日志："
    journalctl -u "$SERVICE_NAME" --no-pager -n 20 2>/dev/null || true
    exit 1
fi

PORT="$(grep -E '^Environment="M20_SERVICE__PORT=' "$UNIT_DST" | sed -E 's/.*=([0-9]+).*/\1/' || echo 8080)"
echo ""
log "健康检查："
curl -s --max-time 5 "http://127.0.0.1:${PORT}/health" || true
echo ""

# ---------------------------------------------------------------- 7. m20monitor 命令
log "[7/7] 安装 m20monitor 管理命令（up/down/reset/status/log）"
if [[ -f "$SRC_DIR/deploy/install_m20monitor.sh" ]]; then
    bash "$SRC_DIR/deploy/install_m20monitor.sh" "$RUN_USER" \
        || warn "m20monitor 安装失败（可选组件；不影响控制台本体，可稍后手动重跑 deploy/install_m20monitor.sh）"
else
    warn "未找到 deploy/install_m20monitor.sh，跳过 m20monitor 安装"
fi

cat <<EOF

------------------------------------------------------------------
安装完成。访问： http://<196-IP>:${PORT}/
  · 状态快照  http://<196-IP>:${PORT}/api/v1/state
  · HLS 视频  http://<196-IP>:${PORT}/hls/live.m3u8
常用运维（推荐，已配免密白名单）：
  m20monitor status        查看状态
  m20monitor up / down     启动 / 停止
  m20monitor reset         重启
  m20monitor log f         跟踪日志
原生命令：
  sudo systemctl status  $SERVICE_NAME
  sudo journalctl -u $SERVICE_NAME -f
  sudo systemctl restart $SERVICE_NAME
排障工具：
  python3 $INSTALL_DIR/tools/probe_asdu.py --target 127.0.0.1 --seconds 8
  python3 $INSTALL_DIR/tools/probe_asdu.py --send 1101/6 --items '{"Sleep":false}'   # 唤醒（相机才通电）
------------------------------------------------------------------
EOF
