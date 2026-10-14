#!/usr/bin/env bash
# ============================================================
# m20-ai-detect 首次部署引导（在 GOS 10.21.31.104 上以 user 身份执行）
#
# 用法：
#   ssh m20pro-GOS.104
#   cd ~ && bash ~/m20-ai-detect/deploy/bootstrap.sh
#
# 幂等：可重复执行；不会覆盖已存在的 m20-ai-detect.env
# 前置：代码已由 install.sh 同步到 ~/m20-ai-detect（含 deploy/）
# ============================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SELF_DIR")"
# BASE 默认取"本脚本所在的已部署副本"（PROJ_ROOT），不用 $HOME——
# GOS 登录账户是 user（$HOME=/home/user），而工作空间按 ADR-001 放在
# /home/djw/m20-ai-detect（root 所有 + ACL 授权 user）。显式设
# M20AI_BASE_DIR 可覆盖（需与 unit/env 一致）。
BASE="${M20AI_BASE_DIR:-$PROJ_ROOT}"

say() { printf "\033[36m[bootstrap]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[bootstrap][warn]\033[0m %s\n" "$*" >&2; }
die() { printf "\033[31m[bootstrap][fail]\033[0m %s\n" "$*" >&2; exit 1; }

# ---- 0. 身份与主机自检 ----------------------------------------------------
# GOS 无 djw 账户（id djw 报 no such user），登录账户是 user；
# /home/djw 为 root 所有但已设 ACL 授权 user:user:rwx，故工作空间仍放 /home/djw 下。
[[ "$(id -un)" == "user" ]] || warn "当前用户是 $(id -un)，预期 user（GOS 唯一可用账户）；unit 写死了 User=user"
[[ "$BASE" == "$PROJ_ROOT" || "$PROJ_ROOT" == "$BASE" ]] || \
    warn "脚本位于 $PROJ_ROOT，但 BASE_DIR=$BASE；确认执行的是已部署副本"

say "工作空间：$BASE"

# ---- 1. 运行时依赖检查（缺什么装什么，装不了就明确退出） ------------------
missing=()
command -v ffmpeg  >/dev/null 2>&1 || missing+=("ffmpeg")
command -v python3 >/dev/null 2>&1 || missing+=("python3")
if [[ ${#missing[@]} -gt 0 ]]; then
    warn "缺少：${missing[*]}"
    say "尝试 apt 安装（需要 sudo，口令为半角单引号）..."
    printf "'\n" | sudo -S apt-get update -qq
    printf "'\n" | sudo -S apt-get install -y -qq "${missing[@]}" \
        || die "apt 安装失败，请手动安装：${missing[*]}"
fi
say "ffmpeg   : $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
say "python3  : $(python3 --version 2>&1)"
python3 -c 'import sys; assert sys.version_info >= (3, 6), "python3 版本过低"' \
    || die "python3 >= 3.6  required（本工程零第三方依赖，标准库即可运行）"

# ---- 2. 目录骨架（与 store.py 的六个子目录一一对应） ----------------------
mkdir -p "$BASE"/{spool,raw,results,alerts,log,tmp}
chmod 750 "$BASE"
say "目录骨架：spool/ raw/ results/ alerts/ log/ tmp/"

# ---- 3. 配置文件（不覆盖已有） -------------------------------------------
if [[ ! -f "$BASE/m20-ai-detect.env" ]]; then
    cp "$BASE/deploy/m20-ai-detect.env.example" "$BASE/m20-ai-detect.env"
    chmod 600 "$BASE/m20-ai-detect.env"
    say "已生成 m20-ai-detect.env（权限 600）；请 review 后再启动"
else
    say "m20-ai-detect.env 已存在，跳过（保留你的修改）"
fi

# ---- 4. systemd unit ------------------------------------------------------
say "安装 systemd unit（需要 sudo）..."
printf "'\n" | sudo -S cp "$BASE/deploy/m20-ai-detect.service" /etc/systemd/system/
printf "'\n" | sudo -S systemctl daemon-reload
printf "'\n" | sudo -S systemctl enable m20-ai-detect.service
say "unit 已安装并 enable（enable != start，启动见下一步）"

# ---- 5. logrotate（文件日志 + journal 双轨，防 raw/ 打爆 eMMC） -----------
cat > /tmp/m20-ai-detect.logrotate <<'EOF'
/home/djw/m20-ai-detect/log/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
printf "'\n" | sudo -S cp /tmp/m20-ai-detect.logrotate /etc/logrotate.d/m20-ai-detect
rm -f /tmp/m20-ai-detect.logrotate
say "logrotate 已安装（log/ 保留 7 天）"

# ---- 6. 首次门禁：不启动服务，先跑 doctor ---------------------------------
say "运行 doctor 门禁（V0″）..."
set +e
( cd "$BASE" && set -a && . ./m20-ai-detect.env && set +a \
    && PYTHONPATH="$BASE/src" python3 -m m20_ai_detect doctor )
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
    warn "doctor 未全绿（rc=$rc）。常见原因：AI 服务不可达 / GOS 无公网出口 / 相机源未起（时钟项为偏移量语义，见 ADR-004，未配置即 PASS）"
    warn "排查后再执行：sudo systemctl start m20-ai-detect"
    exit $rc
fi
say "doctor 全绿。启动服务：sudo systemctl start m20-ai-detect"
say "看日志：journalctl -u m20-ai-detect -f"
