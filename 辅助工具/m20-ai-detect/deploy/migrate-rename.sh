#!/usr/bin/env bash
# ============================================================
# 老部署改名迁移（ADR-017）
#
# 场景：一台按老身份（m20-ai-detect / m20-ai-console）跑起来的机器，要改名成
#       lite3 / ugv_1-a / ipc-x …… 而不重装、不丢用户改过的 env 配置。
#
# 改名的影响面（换一个名字要动的东西，一个都不能漏）：
#   · 运行时 env 文件名        <old>-ai-detect.env   → <new>-ai-detect.env
#   · 控制台 env 里的身份派生键 M20AIC_ENV_FILE / M20AIC_HELPER / M20AIC_APP_ID
#   · systemd unit 两个          + 旧 unit 让位
#   · root helper（/usr/local/sbin）与 sudoers 白名单（/etc/sudoers.d）
#   · logrotate conf（/etc/logrotate.d）
#   · 开机自启状态（尊重旧 unit 的 enabled/disabled）
#
# 安全模型：
#   · 缺省 **dry-run**：只打印计划，一个字节都不碰系统；
#   · --apply          ：安装新身份四件套 + 迁移 env + daemon-reload（**不切换**，
#                        新旧服务并存，旧服务继续跑，可反复试）；
#   · --switch         ：连带切换（先 enable 新的再 stop 旧 start 新，几秒空档）；
#   · --purge-legacy   ：切换成功后清理旧身份残留（unit/helper/sudoers/logrotate；
#                        **不删旧 env 文件**，那是你的配置与历史）。
#
# 限制：只改身份、不改目录。连目录一起搬迁请先把代码同步到新目录，再用
#       M20AI_BASE_DIR 指向新目录执行 bootstrap.sh（全新部署，不是迁移）。
#
# 用法：
#   bash deploy/migrate-rename.sh --to lite3                  # dry-run 看计划
#   bash deploy/migrate-rename.sh --to lite3 --apply          # 装入新身份
#   bash deploy/migrate-rename.sh --to lite3 --apply --switch # 装入并切换
#   ... --purge-legacy                                        # 清理旧残留
#
# 身份来源与 identity.sh 一致（env 内 M20AI_APP_ID > env 文件名前缀 > 缺省 m20）。
# ============================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(dirname "$SELF_DIR")"
# shellcheck source=deploy/identity.sh
. "$SELF_DIR/identity.sh"

say()  { printf '\033[36m[migrate]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[migrate][warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[migrate][fail]\033[0m %s\n' "$*" >&2; exit 1; }

# ---- 参数 -------------------------------------------------------------------
TO=""
APPLY=0
SWITCH=0
PURGE=0
usage() { sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --to)             [[ $# -ge 2 ]] || die "--to 缺值"; TO="$2"; shift 2 ;;
        --apply)          APPLY=1; shift ;;
        --switch)         SWITCH=1; shift ;;
        --purge-legacy)   PURGE=1; shift ;;
        -h|--help)        usage; exit 0 ;;
        *)                die "未知参数：$1（--help 看用法）" ;;
    esac
done
[[ -n "$TO" ]] || { usage; die "缺少 --to <新身份>"; }
# --switch/--purge-legacy 都隐含 --apply（不能 dry-run 切换服务）
if [[ $SWITCH -eq 1 || $PURGE -eq 1 ]]; then APPLY=1; fi

# ---- 旧身份（老部署反查） -----------------------------------------------------
BASE="${M20AI_BASE_DIR:-$PROJ_ROOT}"
[[ -f "$BASE/deploy/identity.sh" ]] || die "找不到 $BASE/deploy/identity.sh；请先同步代码（M20AI_BASE_DIR 可显式指定项目根）"
detect_identity "$BASE"

OLD_APP_ID="$APP_ID"
OLD_UNIT="$UNIT";                   OLD_CONSOLE_UNIT="$CONSOLE_UNIT"
OLD_UNIT_NAME="$UNIT_NAME";         OLD_CONSOLE_UNIT_NAME="$CONSOLE_UNIT_NAME"
OLD_ENV_FILE="$ENV_FILE";           OLD_CONSOLE_ENV_FILE="$CONSOLE_ENV_FILE"
OLD_HELPER="$HELPER";               OLD_SUDOERS="$SUDOERS"
OLD_LOGROTATE_CONF="$LOGROTATE_CONF"

# ---- 校验新身份 ---------------------------------------------------------------
identity_valid "$TO" || die "新身份 '%s' 非法：只能含字母/数字/下划线/连字符，≤32 位，字母或数字开头" "$TO"
[[ "$TO" != "$OLD_APP_ID" ]] || die "新身份与当前身份相同（$TO），无需迁移"
[[ -f "$OLD_ENV_FILE" ]] || die "找不到 $OLD_ENV_FILE：不像已部署的实例，或 BASE 指错了"

# ---- 切到新身份：重跑 detect_identity（raw 优先取 M20AIC_APP_ID） --------------
M20AIC_APP_ID="$TO"
export M20AIC_APP_ID
detect_identity "$BASE"

# ---- 计划 ---------------------------------------------------------------------
if [[ $APPLY -eq 0 ]]; then
    MODE="dry-run（不执行）"
elif [[ $SWITCH -eq 1 ]]; then
    MODE="apply + switch（装入并切换服务）"
else
    MODE="apply（装入新身份，不切换服务）"
fi
say "模式        ：$MODE"
say "旧身份      ：$OLD_APP_ID"
say "新身份      ：$APP_ID"
say "项目根 BASE ：$BASE（不变；只改身份）"
say "运行账户    ：$RUN_USER"
echo
say "将发生（顺序）："
n=0
step() { n=$((n+1)); printf '  %2d. %s\n' "$n" "$*"; }
step "拷贝 $OLD_ENV_FILE → $ENV_FILE，并写入 M20AI_APP_ID=$APP_ID（权限 600）"
step "拷贝 $OLD_CONSOLE_ENV_FILE → $CONSOLE_ENV_FILE，改写身份派生键："
step "      M20AIC_APP_ID / M20AIC_ENV_FILE=$ENV_FILE / M20AIC_HELPER=$HELPER"
step "渲染并安装 unit ×2：$UNIT / $CONSOLE_UNIT（WorkingDirectory=$BASE, User=$RUN_USER）"
step "渲染并安装 helper：$HELPER（755）"
step "渲染并安装 sudoers 白名单：$SUDOERS（440，visudo -c 校验）"
step "安装 logrotate：$LOGROTATE_CONF"
step "systemctl daemon-reload"
if [[ $SWITCH -eq 1 ]]; then
    step "尊重旧 unit 的开机自启状态（旧 enabled → 新 enable）"
    step "停旧起新：$OLD_UNIT_NAME/$OLD_CONSOLE_UNIT_NAME → $UNIT_NAME/$CONSOLE_UNIT_NAME（采集有数秒空档）"
    step "验证：systemctl is-active 新 unit；curl 控制台 /api/status"
fi
if [[ $PURGE -eq 1 ]]; then
    step "清理旧残留：stop+disable 旧 unit，删除 /etc/systemd/system/$OLD_UNIT"
    step "            /etc/systemd/system/$OLD_CONSOLE_UNIT"
    step "            $OLD_HELPER / $OLD_SUDOERS / $OLD_LOGROTATE_CONF"
    step "            （旧 env 文件 $OLD_ENV_FILE / $OLD_CONSOLE_ENV_FILE **保留**，请自行归档）"
    step "systemctl daemon-reload"
fi
echo
if [[ $APPLY -eq 0 ]]; then
    say "以上均未执行。加 --apply 装入；--apply --switch 装入并切换；--purge-legacy 清理旧残留。"
    exit 0
fi

# ---- 执行 ---------------------------------------------------------------------
say "开始执行（mode=$MODE）..."

# 1) env 迁移：拷贝 + 键级 upsert（只动身份派生键，用户调过的键一律不碰）
#    语义与 deploy/render_env.py 的 _upsert 一致；实现是可单测的 env_upsert.py。
#    MSYS_NO_PATHCONV=1 + _ident_win()：见 identity.sh 的同名注释——
#    Windows/Git Bash 上关掉 MSYS 隐式改写，防 M20AIC_HELPER=/usr/local/sbin/...
#    被污染；真实文件路径用 _ident_win 显式转成 Windows python.exe 认识的形式。
say "[1/5] 迁移 env（原文件保留，新文件是副本+身份键）..."
cp "$OLD_ENV_FILE" "$ENV_FILE";        chmod 600 "$ENV_FILE"
cp "$OLD_CONSOLE_ENV_FILE" "$CONSOLE_ENV_FILE"; chmod 600 "$CONSOLE_ENV_FILE"

HDR="身份迁移（deploy/migrate-rename.sh → APP_ID=$APP_ID）"
MSYS_NO_PATHCONV=1 python3 "$(_ident_win "$SELF_DIR/env_upsert.py")" --header "$HDR" \
    "$(_ident_win "$ENV_FILE")" "M20AI_APP_ID=$APP_ID"
MSYS_NO_PATHCONV=1 python3 "$(_ident_win "$SELF_DIR/env_upsert.py")" --header "$HDR" \
    "$(_ident_win "$CONSOLE_ENV_FILE")" "M20AIC_APP_ID=$APP_ID" \
                         "M20AIC_ENV_FILE=$ENV_FILE" \
                         "M20AIC_HELPER=$HELPER"
say "  $ENV_FILE（+M20AI_APP_ID）"
say "  $CONSOLE_ENV_FILE（+M20AIC_APP_ID/ENV_FILE/HELPER）"

# 2) 渲染四件套（按新身份）
say "[2/5] 按新身份渲染 unit/helper/sudoers..."
RENDER_TMP="$(mktemp -d)"
# trap 里最后一条命令的返回码会成为脚本退出码：清理失败（只读目录、沙箱
# 拦截等）不许把一次成功的迁移报成失败。
trap 'rm -rf "$RENDER_TMP" 2>/dev/null || true' EXIT
if ! render_units_into "$RENDER_TMP"; then
    die "render_units.py 失败；检查 $BASE/deploy/render_units.py 与 python3"
fi

# 3) 安装（sudo 口令为半角单引号，与其它 deploy 脚本一致）
say "[3/5] 安装 unit/helper/sudoers/logrotate（需要 sudo）..."
printf "'\n" | sudo -S install -m 644 "$RENDER_TMP/$UNIT"           "/etc/systemd/system/$UNIT"
printf "'\n" | sudo -S install -m 644 "$RENDER_TMP/$CONSOLE_UNIT"   "/etc/systemd/system/$CONSOLE_UNIT"
printf "'\n" | sudo -S install -m 755 "$RENDER_TMP/$HELPER_BASENAME" "$HELPER"
printf "'\n" | sudo -S install -m 440 "$RENDER_TMP/$SUDOERS_BASENAME" "$SUDOERS"
printf "'\n" | sudo -S visudo -c >/dev/null || die "sudoers 语法校验失败：$SUDOERS"
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

# 4) daemon-reload
say "[4/5] daemon-reload..."
printf "'\n" | sudo -S systemctl daemon-reload

# 5) 切换 / 清理
say "[5/5] 切换与清理..."
take_over() {  # 旧 unit 让位给新 unit：先尊重 enable 状态，再 stop 旧 start 新
    local old_unit="$1" new_unit="$2" old_name="$3" new_name="$4"
    local was
    was="$(systemctl is-enabled "$old_unit" 2>/dev/null || true)"
    if [[ "$was" == "enabled" ]]; then
        printf "'\n" | sudo -S systemctl enable "$new_name"
        say "  $new_name 已 enable（跟随旧 unit 的开机自启状态）"
    else
        say "  $new_name 不 enable（旧 unit 状态：${was:-disabled}）"
    fi
    printf "'\n" | sudo -S systemctl stop "$old_name"
    printf "'\n" | sudo -S systemctl start "$new_name"
}

if [[ $SWITCH -eq 1 ]]; then
    state_before="$(systemctl is-active "$OLD_UNIT_NAME" 2>/dev/null || true)"
    if [[ "$state_before" == "active" ]]; then
        warn "采样器正在运行：切换到 $UNIT_NAME 会有数秒采集空档"
    fi
    take_over "$OLD_CONSOLE_UNIT" "$CONSOLE_UNIT" \
              "$OLD_CONSOLE_UNIT_NAME" "$CONSOLE_UNIT_NAME"
    take_over "$OLD_UNIT" "$UNIT" \
              "$OLD_UNIT_NAME" "$UNIT_NAME"
    say "  切换完成：$CONSOLE_UNIT_NAME=$(systemctl is-active "$CONSOLE_UNIT_NAME" 2>/dev/null || true)" \
        "  $UNIT_NAME=$(systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"

    # 验证：控制台 /api/status（端口从新 console env 读）
    PORT="$(sed -n 's/^M20AIC_PORT=//p' "$CONSOLE_ENV_FILE" | head -1)"
    PORT="${PORT:-5050}"
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:$PORT/api/status" || true)"
    if [[ "$code" == "200" ]]; then
        say "  控制台自检通过：http://127.0.0.1:$PORT/api/status → 200"
    else
        warn "控制台 /api/status 返回 $code（端口 $PORT）；排查：journalctl -u $CONSOLE_UNIT_NAME -n 30"
    fi
fi

if [[ $PURGE -eq 1 ]]; then
    printf '\033[31m[migrate][warn]\033[0m 即将删除旧身份残留：%s\n' \
        "/etc/systemd/system/$OLD_UNIT /etc/systemd/system/$OLD_CONSOLE_UNIT $OLD_HELPER $OLD_SUDOERS $OLD_LOGROTATE_CONF"
    printf '旧 env 文件（%s / %s）会保留。确认删除旧系统组件？[y/N] ' \
        "$OLD_ENV_FILE" "$OLD_CONSOLE_ENV_FILE"
    read -r ans
    if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
        say "已取消清理（新身份不受影响）。稍后可手动执行："
        say "  sudo systemctl disable --now $OLD_UNIT_NAME $OLD_CONSOLE_UNIT_NAME"
        say "  sudo rm -f /etc/systemd/system/$OLD_UNIT /etc/systemd/system/$OLD_CONSOLE_UNIT \\"
        say "            $OLD_HELPER $OLD_SUDOERS $OLD_LOGROTATE_CONF"
        say "  sudo systemctl daemon-reload"
    else
        printf "'\n" | sudo -S systemctl stop "$OLD_UNIT_NAME" "$OLD_CONSOLE_UNIT_NAME" || true
        printf "'\n" | sudo -S systemctl disable "$OLD_UNIT_NAME" "$OLD_CONSOLE_UNIT_NAME" || true
        # 注意：$OLD_UNIT/$OLD_CONSOLE_UNIT 只是**文件名**（detect_identity 不拼前缀），
        # 删系统 unit 必须自己拼 /etc/systemd/system/（写成裸文件名会去 cwd 删）。
        printf "'\n" | sudo -S rm -f "/etc/systemd/system/$OLD_UNIT" \
            "/etc/systemd/system/$OLD_CONSOLE_UNIT" \
            "$OLD_HELPER" "$OLD_SUDOERS" "$OLD_LOGROTATE_CONF"
        printf "'\n" | sudo -S systemctl daemon-reload
        say "旧身份残留已清理。旧 env 文件保留在：$OLD_ENV_FILE / $OLD_CONSOLE_ENV_FILE"
    fi
fi

echo
say "完成。新身份 $APP_ID 的使用方式："
say "  aiDetect status                      # 终端命令已按新身份反查（$BASE/deploy/identity.sh）"
say "  控制台网页                            # 端口见 $CONSOLE_ENV_FILE 的 M20AIC_PORT"
say "  journalctl -u $UNIT_NAME -f          # 采样器日志"
say "  journalctl -u $CONSOLE_UNIT_NAME -f  # 控制台日志"
if [[ $PURGE -eq 0 ]]; then
    say "提示：旧身份（$OLD_APP_ID）的 unit/helper/sudoers/logrotate 仍并存/生效；"
    say "      确认新身份稳定运行后，追加 --purge-legacy 清理（旧 env 会保留）。"
fi
