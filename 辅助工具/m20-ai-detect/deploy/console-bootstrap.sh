#!/usr/bin/env bash
# ============================================================
# m20-ai-console 首次部署引导（在 GOS 10.21.31.104 上以 user 身份执行）
#
# 用法：
#   ssh m20pro-GOS.104
#   cd /home/djw/m20-ai-detect && bash deploy/console-bootstrap.sh
#
# 幂等：可重复执行；不覆盖已存在的 m20-ai-console.env
# 前置：代码已由 install.sh 同步（含 webconsole/ 与 deploy/）
# ============================================================
set -euo pipefail

BASE="${M20AI_BASE_DIR:-/home/djw/m20-ai-detect}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SELF_DIR")"

say()  { printf "\033[36m[console-bootstrap]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[console-bootstrap][warn]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[31m[console-bootstrap][fail]\033[0m %s\n" "$*" >&2; exit 1; }

[[ "$(id -un)" == "user" ]] || warn "当前用户是 $(id -un)，预期 user（GOS 唯一可用账户）"

say "工作空间：$BASE"

# ---- 1. 控制台 env（不覆盖已有） -------------------------------------------
if [[ ! -f "$BASE/m20-ai-console.env" ]]; then
    cp "$BASE/deploy/m20-ai-console.env.example" "$BASE/m20-ai-console.env"
    chmod 600 "$BASE/m20-ai-console.env"
    say "已生成 m20-ai-console.env（权限 600，默认 0.0.0.0:5050，token 留空=内网开放）"
else
    say "m20-ai-console.env 已存在，跳过"
fi

# ---- 2. root helper + sudoers 白名单 ---------------------------------------
say "安装 root helper 与 sudoers 白名单（需要 sudo）..."
printf "'\n" | sudo -S install -m 755 "$BASE/deploy/m20-ai-console-helper" /usr/local/sbin/m20-ai-console-helper
printf "'\n" | sudo -S install -m 440 "$BASE/deploy/m20-ai-console.sudoers" /etc/sudoers.d/m20-ai-console
printf "'\n" | sudo -S visudo -c >/dev/null || die "sudoers 语法校验失败，已装入但请立即检查 /etc/sudoers.d/m20-ai-console"
say "helper=/usr/local/sbin/m20-ai-console-helper；sudoers 白名单已装入并通过 visudo -c"

# ---- 3. aiDetect 终端命令 ---------------------------------------------------
say "安装 aiDetect 终端命令（/usr/local/bin/aiDetect + 别名 aidetect）..."
printf "'\n" | sudo -S install -m 755 "$BASE/deploy/aiDetect" /usr/local/bin/aiDetect
printf "'\n" | sudo -S ln -sf /usr/local/bin/aiDetect /usr/local/bin/aidetect
say "已装入。试试：aiDetect status / aiDetect help"

# ---- 4. systemd unit --------------------------------------------------------
say "安装 systemd unit..."
printf "'\n" | sudo -S install -m 644 "$BASE/deploy/m20-ai-console.service" /etc/systemd/system/m20-ai-console.service
printf "'\n" | sudo -S systemctl daemon-reload
# 开机自启默认不开启（ADR-008：重启后手动启动，aiDetect up --all）。
# 不再自动 enable，也不触碰既有状态。
en="$(systemctl is-enabled m20-ai-console.service 2>/dev/null || true)"
say "unit 已安装。开机自启：${en:-disabled}（不再自动 enable；需要时：sudo systemctl enable m20-ai-console）"

# ---- 5. 冒烟自检（不启动常驻，先前台验 5 秒） -------------------------------
say "冒烟自检：前台起 5 秒，验 /api/status 与静态页..."
set +e
( cd "$BASE" && set -a && . ./m20-ai-console.env && set +a \
    && PYTHONPATH="$BASE/src:$BASE" timeout 5 python3 -m webconsole ) &
SMOKE_PID=$!
sleep 2
PORT="$(sed -n 's/^M20AIC_PORT=//p' "$BASE/m20-ai-console.env")"
PORT="${PORT:-5050}"
code1="$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/api/status" || true)"
code2="$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/" || true)"
wait $SMOKE_PID 2>/dev/null || true
set -e
[[ "$code1" == "200" && "$code2" == "200" ]] || die "冒烟失败：api/status=$code1 index=$code2"
say "冒烟通过（api/status=200, 首页=200）"

# ---- 6. 启动常驻 ------------------------------------------------------------
say "启动 m20-ai-console..."
printf "'\n" | sudo -S systemctl start m20-ai-console
sleep 2
state="$(systemctl is-active m20-ai-console || true)"
[[ "$state" == "active" ]] || die "服务未起来（state=$state），查 journalctl -u m20-ai-console -n 30"
say "m20-ai-console 已启动（$(systemctl show m20-ai-console --property=MainPID --no-pager)）"
say "访问    ：http://10.21.31.104:$PORT （机器人内网；外网无 DNAT 到不了）"
say "看日志  ：journalctl -u m20-ai-console -f"
