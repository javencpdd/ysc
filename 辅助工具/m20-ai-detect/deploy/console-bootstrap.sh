#!/usr/bin/env bash
# ============================================================
# Web 控制台首次部署引导（在目标机上以业务账户身份执行）
#
# 用法：
#   ssh <目标机>
#   cd <项目目录> && bash deploy/console-bootstrap.sh
#
# 幂等：可重复执行；不覆盖已存在的 <app_id>-ai-console.env
# 前置：代码已同步（含 webconsole/ 与 deploy/）
#
# 身份（ADR-017）：与 bootstrap.sh 用同一套解析规则（deploy/identity.sh）。
#   项目叫什么由 env 文件里的 M20AI_APP_ID（或文件名前缀）决定，缺省 m20；
#   换到 Lite3 等平台时 unit/env/helper 名自动跟着变，脚本不用改。
# ============================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SELF_DIR")"
BASE="${M20AI_BASE_DIR:-$PROJ_ROOT}"

# ---- 0. 身份解析 -----------------------------------------------------------
# shellcheck source=deploy/identity.sh
. "$SELF_DIR/identity.sh"
detect_identity "$BASE"

say()  { printf "\033[36m[console-bootstrap]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[console-bootstrap][warn]\033[0m %s\n" "$*" >&2; }
die()  { printf '\033[31m[console-bootstrap][fail]\033[0m %s\n' "$*" >&2; exit 1; }

say "身份：APP_ID=$APP_ID  unit=$CONSOLE_UNIT"
say "      env=$CONSOLE_ENV_FILE  helper=$HELPER  run_user=$RUN_USER"
say "工作空间：$BASE"

# ---- 1. 控制台 env（不覆盖已有） -------------------------------------------
if [[ ! -f "$CONSOLE_ENV_FILE" ]]; then
    cp "$BASE/deploy/m20-ai-console.env.example" "$CONSOLE_ENV_FILE"
    chmod 600 "$CONSOLE_ENV_FILE"
    say "已生成 $CONSOLE_ENV_FILE（权限 600，默认 0.0.0.0:5050，token 留空=内网开放）"
    if [[ "$APP_ID" != "m20" ]]; then
        warn "APP_ID=$APP_ID：请确认其中的 M20AIC_ENV_FILE 指向 $ENV_FILE"
    fi
else
    say "$CONSOLE_ENV_FILE 已存在，跳过"
fi

# ---- 2. 现场渲染 unit/helper/sudoers（按身份，ADR-017）------------------------
# helper 与 sudoers 也从同一份渲染结果里取：它们内部写死了 unit 名与路径，
# 必须与 unit 保持同一身份，否则白名单调不通。
say "按身份渲染 unit/helper/sudoers（APP_ID=$APP_ID）..."
UNIT_TMP="$(mktemp -d)"
# trap 里最后一条命令的返回码会成为脚本退出码：清理失败不许把成功的部署报成失败
trap 'rm -rf "$UNIT_TMP" 2>/dev/null || true' EXIT
if render_units_into "$UNIT_TMP"; then
    say "  已渲染：$CONSOLE_UNIT $UNIT $HELPER_BASENAME $SUDOERS_BASENAME"
    HELPER_SRC="$UNIT_TMP/$HELPER_BASENAME"
    SUDOERS_SRC="$UNIT_TMP/$SUDOERS_BASENAME"
    UNIT_SRC="$UNIT_TMP/$CONSOLE_UNIT"
else
    # 渲染失败（缺 render_units.py、python3 不可用等）：退回仓库提交的成品。
    # 成品只对应缺省身份 m20，非 m20 身份到这里必须停，否则名字对不上。
    warn "render_units.py 失败，退回 deploy/ 下提交的缺省成品（仅适用于 APP_ID=m20）"
    [[ "$APP_ID" == "m20" ]] || die "APP_ID=$APP_ID 但无法现场渲染，请检查 $BASE/deploy/render_units.py 与 python3"
    HELPER_SRC="$BASE/deploy/m20-ai-console-helper"
    SUDOERS_SRC="$BASE/deploy/m20-ai-console.sudoers"
    UNIT_SRC="$BASE/deploy/m20-ai-console.service"
fi

# ---- 3. root helper + sudoers 白名单 ---------------------------------------
say "安装 root helper 与 sudoers 白名单（需要 sudo）..."
printf "'\n" | sudo -S install -m 755 "$HELPER_SRC" "$HELPER"
printf "'\n" | sudo -S install -m 440 "$SUDOERS_SRC" "$SUDOERS"
printf "'\n" | sudo -S visudo -c >/dev/null || die "sudoers 语法校验失败，已装入但请立即检查 $SUDOERS"
say "helper=$HELPER；sudoers 白名单已装入并通过 visudo -c"

# ---- 4. aiDetect 终端命令 ---------------------------------------------------
say "安装 aiDetect 终端命令（/usr/local/bin/aiDetect + 别名 aidetect）..."
printf "'\n" | sudo -S install -m 755 "$BASE/deploy/aiDetect" /usr/local/bin/aiDetect
printf "'\n" | sudo -S ln -sf /usr/local/bin/aiDetect /usr/local/bin/aidetect
say "已装入。试试：aiDetect status / aiDetect help"

# ---- 5. systemd unit --------------------------------------------------------
say "安装 systemd unit..."
printf "'\n" | sudo -S install -m 644 "$UNIT_SRC" "/etc/systemd/system/$CONSOLE_UNIT"
printf "'\n" | sudo -S systemctl daemon-reload
# 开机自启默认不开启（ADR-008：重启后手动启动，aiDetect up --all）。
# 不再自动 enable，也不触碰既有状态。
en="$(systemctl is-enabled "$CONSOLE_UNIT" 2>/dev/null || true)"
say "unit 已安装。开机自启：${en:-disabled}（不再自动 enable；需要时：sudo systemctl enable $CONSOLE_UNIT）"

# ---- 6. 冒烟自检（不启动常驻，先前台验 5 秒） -------------------------------
say "冒烟自检：前台起 5 秒，验 /api/status 与静态页..."
set +e
( cd "$BASE" && set -a && . "./$CONSOLE_ENV_BASENAME" && set +a \
    && PYTHONPATH="$BASE/src:$BASE" timeout 5 python3 -m webconsole ) &
SMOKE_PID=$!
sleep 2
PORT="$(sed -n 's/^M20AIC_PORT=//p' "$CONSOLE_ENV_FILE")"
PORT="${PORT:-5050}"
code1="$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/api/status" || true)"
code2="$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/" || true)"
wait $SMOKE_PID 2>/dev/null || true
set -e
[[ "$code1" == "200" && "$code2" == "200" ]] || die "冒烟失败：api/status=$code1 index=$code2"
say "冒烟通过（api/status=200, 首页=200）"

# ---- 7. 启动常驻 ------------------------------------------------------------
say "启动 $CONSOLE_UNIT_NAME..."
printf "'\n" | sudo -S systemctl start "$CONSOLE_UNIT_NAME"
sleep 2
state="$(systemctl is-active "$CONSOLE_UNIT_NAME" || true)"
[[ "$state" == "active" ]] || die "服务未起来（state=$state），查 journalctl -u $CONSOLE_UNIT_NAME -n 30"
say "$CONSOLE_UNIT_NAME 已启动（$(systemctl show "$CONSOLE_UNIT_NAME" --property=MainPID --no-pager)）"
say "访问    ：http://127.0.0.1:$PORT （按 M20AIC_BIND 监听；内网可达即可访问）"
say "看日志  ：journalctl -u $CONSOLE_UNIT_NAME -f"
