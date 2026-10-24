#!/usr/bin/env bash
# ============================================================
# 首次部署引导（在目标机上以业务账户身份执行）
#
# 用法：
#   ssh <目标机>
#   cd ~/<项目目录> && bash deploy/bootstrap.sh
#
# 幂等：可重复执行；不会覆盖已存在的 <app_id>-ai-detect.env
# 前置：代码已同步到目标机（含 deploy/）
#
# 身份（ADR-017）：本项目叫什么由 env 文件里的 M20AI_APP_ID（或文件名前缀）决定，
#   缺省 m20。换到 Lite3 等平台时所有 unit/env/helper 名自动跟着变。
#   · 手动指定：M20AIC_APP_ID=lite3 bash deploy/bootstrap.sh
#   · 运行账户：M20AI_RUN_USER=ysc bash deploy/bootstrap.sh（缺省取当前登录用户）
# ============================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SELF_DIR")"
# BASE 默认取"本脚本所在的已部署副本"（PROJ_ROOT），不用 $HOME——
# GOS 登录账户是 user（$HOME=/home/user），而工作空间按 ADR-001 放在
# /home/djw/m20-ai-detect（root 所有 + ACL 授权 user）。显式设
# M20AI_BASE_DIR 可覆盖（需与 unit/env 一致）。
BASE="${M20AI_BASE_DIR:-$PROJ_ROOT}"

# ---- 0. 身份解析（unit/env/helper 名全部由 APP_ID 派生，见 identity.sh）----
# shellcheck source=deploy/identity.sh
. "$SELF_DIR/identity.sh"
detect_identity "$BASE"
say_id() { printf "\033[36m[bootstrap]\033[0m %s\n" "$*"; }

say_id "身份：APP_ID=$APP_ID  unit=$UNIT / $CONSOLE_UNIT"
say_id "      env=$ENV_FILE / $CONSOLE_ENV_FILE"
say_id "      helper=$HELPER  run_user=$RUN_USER"

say() { printf "\033[36m[bootstrap]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[bootstrap][warn]\033[0m %s\n" "$*" >&2; }
die() { printf "\033[31m[bootstrap][fail]\033[0m %s\n" "$*" >&2; exit 1; }

# ---- 0b. 主机自检 -----------------------------------------------------------
# 参考部署（GOS 10.21.31.104）无 djw 账户，登录账户是 user；换平台不强制，
# 只提示"unit 将以 $RUN_USER 运行"。
say "当前用户：$(id -un)；unit 将以 User=$RUN_USER 运行"
[[ "$BASE" == "$PROJ_ROOT" || "$PROJ_ROOT" == "$BASE" ]] || \
    warn "脚本位于 $PROJ_ROOT，但 BASE_DIR=$BASE；确认执行的是已部署副本"

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
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$BASE/deploy/m20-ai-detect.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    say "已生成 $ENV_FILE（权限 600）；请 review 后再启动"
    # 新平台不要用这份"参考部署"默认值硬跑：按平台挑一个 profile 追加进去
    # （同名键后者覆盖前者），至少改掉 M20AI_SOURCES 的相机地址。
    avail_profiles=()
    for p in "$BASE"/deploy/profiles/*.env; do
        [[ -f "$p" ]] && avail_profiles+=("$(basename "$p")")
    done
    if [[ ${#avail_profiles[@]} -gt 0 ]]; then
        say "  可用平台 profile：${avail_profiles[*]}"
        say "  追加示例：cat deploy/profiles/lite3-single.env >> $ENV_FILE"
    fi
    # 提示：这是从模板拷出来的，身份键没写（缺省 m20 靠文件名前缀兜底反查）。
    if [[ "$APP_ID" != "m20" ]]; then
        warn "APP_ID=$APP_ID 但新 env 未写 M20AI_APP_ID；建议补一行：M20AI_APP_ID=$APP_ID"
    fi
else
    say "$ENV_FILE 已存在，跳过（保留你的修改）"
fi

# ---- 4. systemd unit ------------------------------------------------------
# unit 由模板按身份渲染（ADR-017），渲染不出来才退回仓库里提交的缺省成品。
say "安装 systemd unit（需要 sudo）..."
UNIT_TMP="$(mktemp -d)"
trap 'rm -rf "$UNIT_TMP"' EXIT
if render_units_into "$UNIT_TMP"; then
    say "  已按 APP_ID=$APP_ID 渲染 unit（WorkingDirectory=$BASE, User=$RUN_USER）"
else
    warn "render_units.py 失败，退回 deploy/ 下提交的缺省 unit（仅适用于 APP_ID=m20）"
    cp "$BASE/deploy/m20-ai-detect.service" "$UNIT_TMP/$UNIT"
    cp "$BASE/deploy/m20-ai-console.service" "$UNIT_TMP/$CONSOLE_UNIT"
fi
printf "'\n" | sudo -S install -m 644 "$UNIT_TMP/$UNIT" "/etc/systemd/system/$UNIT"
printf "'\n" | sudo -S systemctl daemon-reload
# 开机自启默认不开启（ADR-008：用户要求重启后手动启动，aiDetect up --all）。
# 本脚本不再自动 enable，也不触碰既有状态——曾 enable 过的保留 enabled。
en="$(systemctl is-enabled "$UNIT" 2>/dev/null || true)"
say "unit 已安装。开机自启：${en:-disabled}（不再自动 enable；需要时：sudo systemctl enable $UNIT）"

# ---- 5. logrotate（文件日志 + journal 双轨，防 raw/ 打爆 eMMC） -----------
cat > /tmp/"$APP_ID"-ai-detect.logrotate <<EOF
$BASE/log/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
printf "'\n" | sudo -S install -m 644 /tmp/"$APP_ID"-ai-detect.logrotate "$LOGROTATE_CONF"
rm -f /tmp/"$APP_ID"-ai-detect.logrotate
say "logrotate 已安装（$LOGROTATE_CONF，log/ 保留 7 天）"

# ---- 6. 首次门禁：不启动服务，先跑 doctor ---------------------------------
say "运行 doctor 门禁（V0″）..."
set +e
( cd "$BASE" && set -a && . "./$ENV_BASENAME" && set +a \
    && PYTHONPATH="$BASE/src" python3 -m m20_ai_detect doctor )
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
    warn "doctor 未全绿（rc=$rc）。常见原因：AI 服务不可达 / 无公网出口 / 相机源未起（时钟项为偏移量语义，见 ADR-004，未配置即 PASS）"
    warn "排查后再执行：sudo systemctl start $UNIT"
    exit $rc
fi
say "doctor 全绿。启动服务：sudo systemctl start $UNIT"
say "看日志：journalctl -u $UNIT_NAME -f"
