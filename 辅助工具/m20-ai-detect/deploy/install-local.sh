#!/usr/bin/env bash
# ============================================================
# 就地部署 / 更新（**在目标机上执行**，不需要开发机）
#
# 场景一（推荐）：把新代码放旁路目录或压缩包，由本脚本覆盖进当前项目
#   bash deploy/install-local.sh --from ~/m20-ai-detect-new
#   bash deploy/install-local.sh --from ~/m20-ai-detect-v0.8.12.tar.gz
#
# 场景二：你已经直接把 m20-ai-detect 拖/拷覆盖到了当前目录，只想走一遍
#         备份 → 清理垃圾 → 自检 → 重启
#   bash deploy/install-local.sh
#
# 身份（ADR-017）：unit / env / helper 名由 APP_ID 派生（deploy/identity.sh）。
#   老部署（env 里没有 M20AI_APP_ID）解析结果就是 m20 ⇒ 行为与改造前完全一致。
#
# 安全约束：
#   1. 只覆盖**代码白名单**（src deploy tests docs webconsole Makefile pyproject.toml *.md），
#      绝不碰 spool/ raw/ results/ alerts/ saved/ log/ tmp/ .env .backup/.runtime；
#   2. 覆盖前先把旧代码打成 .backup/code-<TS>.tar.gz（回滚只需一条 tar xzf）；
#   3. 校验 BASE 与 systemd unit 的 WorkingDirectory 一致，不一致直接拒绝（--force 可越权跳过），
#      避免"服务能起但写 raw/ 被沙箱拦下"的隐蔽故障；
#   4. 自动清理 Windows 拷贝带来的垃圾（.playwright-cli / .pytest_cache / __pycache__）
#      与 CRLF 行尾，补回可执行位；
#   5. 自检不通过不重启（退回到"服务还跑着旧代码"，比跑坏代码安全）。
#
# 参数：
#   --from <dir|tar.gz>  源（目录或压缩包）；省略则视为"代码已在位，只做校验+重启"
#   --base <dir>         项目根（默认：本脚本所在目录的上级）
#   --app-id <id>        手动指定身份（缺省按 env 文件反查）
#   --dry-run            只打印将做什么，不落盘、不重启
#   --no-restart         自检通过也不重启（首次部署前用）
#   --force              跳过 unit 路径一致性检查（确认自己知道在干什么再用）
# ============================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${M20AI_BASE_DIR:-$(dirname "$SELF_DIR")}"
FROM=""
DRY=0
NO_RESTART=0
FORCE=0
APP_ID_OVERRIDE=""

say()  { printf "\033[36m[local]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[local][warn]\033[0m %s\n" "$*" >&2; }
die()  { printf '\033[31m[local][fail]\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [[ "$DRY" == "1" ]]; then printf "  \033[90m[dry-run] %s\033[0m\n" "$*"; else "$@"; fi; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from)       FROM="${2:-}"; shift 2 ;;
        --base)       BASE="${2:-}"; shift 2 ;;
        --app-id)     APP_ID_OVERRIDE="${2:-}"; shift 2 ;;
        --dry-run)    DRY=1; shift ;;
        --no-restart) NO_RESTART=1; shift ;;
        --force)      FORCE=1; shift ;;
        -h|--help)    sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)            die "未知参数：$1（--help 看用法）" ;;
    esac
done

# ---------- 0. 环境与身份 ----------
[[ -d "$BASE" ]] || die "项目目录不存在：$BASE"
[[ -f "$BASE/src/m20_ai_detect/__init__.py" ]] || die "$BASE 不像本项目（缺 src/m20_ai_detect/__init__.py）"

# shellcheck source=deploy/identity.sh
. "$SELF_DIR/identity.sh"
# --app-id 显式指定时优先级最高（等价于 M20AIC_APP_ID）
[[ -n "$APP_ID_OVERRIDE" ]] && export M20AIC_APP_ID="$APP_ID_OVERRIDE"
detect_identity "$BASE"

say "项目根：$BASE"
say "身份  ：APP_ID=$APP_ID  unit=$UNIT / $CONSOLE_UNIT"
say "      env=$ENV_FILE  helper=$HELPER"
if [[ "$APP_ID" != "m20" ]]; then
    say "      非缺省身份：unit/env/helper 名均已按 APP_ID 派生"
fi
UNIT_PATH="/etc/systemd/system/$UNIT"
CONSOLE_UNIT_PATH="/etc/systemd/system/$CONSOLE_UNIT"

# ---------- 1. unit 路径一致性（最常见的翻车点） ----------
if [[ -f "$UNIT_PATH" ]] && grep -q "^WorkingDirectory=" "$UNIT_PATH"; then
    UNIT_DIR="$(sed -n 's/^WorkingDirectory=//p' "$UNIT_PATH" | head -1)"
    if [[ "$UNIT_DIR" != "$BASE" ]]; then
        warn "路径不一致：unit WorkingDirectory=$UNIT_DIR，本脚本 BASE=$BASE"
        if [[ "$FORCE" == "1" ]]; then
            warn "--force 已指定，继续（写文件可能被 systemd 沙箱拦截）"
        else
            cat >&2 <<EOF
修法（三处必须一致，否则表现为"采集无数据 + permission denied"）：
  sudo sed -i 's#$UNIT_DIR#$BASE#g' $UNIT_PATH $CONSOLE_UNIT_PATH
  sudo systemctl daemon-reload
  sed -i 's#^M20AI_BASE_DIR=.*#M20AI_BASE_DIR=$BASE#' $ENV_FILE
EOF
            die "请先统一路径，或加 --force 跳过本检查"
        fi
    else
        say "unit 路径一致：$UNIT_DIR"
    fi
else
    warn "未找到 $UNIT_PATH（首次部署请先跑 deploy/bootstrap.sh）；本次跳过路径检查"
fi

# ---------- 2. 备份（覆盖之前） ----------
TS="$(date +%Y%m%d-%H%M%S)"
BK="$BASE/.backup"
say "备份旧代码 -> $BK/code-$TS.tar.gz"
run mkdir -p "$BK"
if [[ "$DRY" == "1" ]]; then
    printf "  \033[90m[dry-run] tar czf %s/code-%s.tar.gz -C %s src deploy tests docs webconsole Makefile pyproject.toml README.md USAGE.md .env.example\033[0m\n" \
        "$BK" "$TS" "$BASE"
else
    tar czf "$BK/code-$TS.tar.gz" -C "$BASE" \
        src deploy tests docs webconsole Makefile pyproject.toml \
        README.md USAGE.md .env.example 2>/dev/null || true
    [[ -f "$ENV_FILE" ]] && cp -a "$ENV_FILE" "$BK/env-$TS"
    ls -1t "$BK" | head -4 | sed 's/^/  /'
fi

# ---------- 3. 覆盖（仅 --from） ----------
if [[ -n "$FROM" ]]; then
    [[ -e "$FROM" ]] || die "源不存在：$FROM"
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    if [[ -d "$FROM" ]]; then
        SRC="$FROM"
    else
        say "解压 $FROM"
        run tar xzf "$FROM" -C "$TMP"
        # 压缩包可能自带一层目录
        SRC="$TMP/$(ls -1 "$TMP" | head -1)"
        [[ -d "$SRC/src" ]] || SRC="$TMP"
    fi
    [[ -d "$SRC/src/m20_ai_detect" ]] || die "源里没有 src/m20_ai_detect：$SRC"
    say "覆盖代码（白名单，不删数据/配置）<- $SRC"
    declare -a ITEMS=()
    for it in src deploy tests docs webconsole Makefile pyproject.toml README.md USAGE.md; do
        [[ -e "$SRC/$it" ]] && ITEMS+=("$it")
    done
    [[ ${#ITEMS[@]} -gt 0 ]] || die "源里没有可覆盖的代码项"
    say "  将覆盖：${ITEMS[*]}"
    # 用 tar 管道覆盖：同名文件替换，不在白名单的旧文件保留（不删），数据目录天然不受影响
    if [[ "$DRY" == "1" ]]; then
        printf "  \033[90m[dry-run] tar cf - -C %s %s | tar xf - -C %s\033[0m\n" "$SRC" "${ITEMS[*]}" "$BASE"
    else
        tar cf - -C "$SRC" "${ITEMS[@]}" | tar xf - -C "$BASE"
    fi
fi

# ---------- 4. 清理本地/Windows 垃圾 ----------
say "清理本地产物（.playwright-cli / .pytest_cache / __pycache__ / *.pyc）"
for junk in .playwright-cli .pytest_cache .runtime; do
    [[ -e "$BASE/$junk" ]] && run rm -rf "$BASE/$junk"
done
run find "$BASE" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
run find "$BASE" -name '*.pyc' -type f -delete 2>/dev/null || true

# ---------- 5. 行尾与执行位 ----------
say "修正行尾（CRLF -> LF）与可执行位"
if grep -lq $'\r' "$BASE"/deploy/*.sh "$BASE"/deploy/aiDetect 2>/dev/null; then
    warn "检测到 CRLF，自动转换"
    for f in "$BASE"/deploy/*.sh "$BASE"/deploy/aiDetect; do
        [[ -f "$f" ]] || continue
        run sed -i 's/\r$//' "$f"
    done
fi
run chmod +x "$BASE"/deploy/*.sh "$BASE"/deploy/aiDetect 2>/dev/null || true
run mkdir -p "$BASE"/{spool,raw,results,alerts,log,tmp}

# ---------- 5b. unit 同步（模板改了/身份变了要重装） ----------
# 只在 unit 缺失、或 WorkingDirectory 与 BASE 不一致时重装（不动 enable 状态）。
say "检查 systemd unit 是否需要重装"
# 注意 pipefail：unit 不存在时 sed 非零退出会连带整条管道失败，必须显式 || true
UNIT_WD="$(sed -n 's/^WorkingDirectory=//p' "$UNIT_PATH" 2>/dev/null | head -1 || true)"
if [[ ! -f "$UNIT_PATH" ]] || [[ "$UNIT_WD" != "$BASE" ]]; then
    if [[ "$DRY" == "1" ]]; then
        printf "  \033[90m[dry-run] 按 APP_ID=%s 渲染并安装 %s / %s\033[0m\n" \
            "$APP_ID" "$UNIT" "$CONSOLE_UNIT"
    else
        UNIT_TMP="$(mktemp -d)"
        trap 'rm -rf "$UNIT_TMP"' EXIT
        if render_units_into "$UNIT_TMP"; then
            printf "'\n" | sudo -S install -m 644 "$UNIT_TMP/$UNIT" "$UNIT_PATH"
            printf "'\n" | sudo -S install -m 644 "$UNIT_TMP/$CONSOLE_UNIT" "$CONSOLE_UNIT_PATH"
            printf "'\n" | sudo -S systemctl daemon-reload
            say "  已按 APP_ID=$APP_ID 重装 unit（不改变开机自启状态）"
        else
            warn "  render_units.py 失败，保留现有 unit（APP_ID=m20 的既有部署不受影响）"
        fi
    fi
else
    say "  unit 与 BASE 一致，跳过（要强制重装：先 sudo rm $UNIT_PATH 再跑本脚本）"
fi

# ---------- 6. 自检（不通过不重启） ----------
say "自检：compileall + import"
if [[ "$DRY" == "1" ]]; then
    printf "  \033[90m[dry-run] python3 -m compileall -q src webconsole && import 自检\033[0m\n"
else
    ( cd "$BASE" && python3 -m compileall -q src webconsole ) || die "编译失败，未重启（旧代码仍在跑）"
    ( cd "$BASE" && PYTHONPATH=src:. python3 - <<'PY'
import sys
import m20_ai_detect, webconsole
print("import ok, sampler v%s, console v%s" % (m20_ai_detect.__version__, webconsole.__version__))
sys.exit(0)
PY
    ) || die "import 自检失败，未重启（旧代码仍在跑）"
fi

# ---------- 7. 重启 ----------
if [[ "$NO_RESTART" == "1" ]]; then
    say "--no-restart：跳过重启。手动：sudo systemctl restart $UNIT_NAME $CONSOLE_UNIT_NAME"
elif [[ "$DRY" == "1" ]]; then
    printf "  \033[90m[dry-run] 重启 %s / %s\033[0m\n" "$UNIT_NAME" "$CONSOLE_UNIT_NAME"
else
    say "重启服务"
    if sudo -n "$HELPER" svc-restart 2>/dev/null; then
        say "  采样器：$(systemctl is-active "$UNIT_NAME" || true)"
    elif sudo -n systemctl restart "$UNIT_NAME" 2>/dev/null; then
        say "  采样器：$(systemctl is-active "$UNIT_NAME" || true)"
    else
        warn "  采样器未重启（helper 未装或需口令）：printf \"'\\n\" | sudo -S systemctl restart $UNIT_NAME"
    fi
    if sudo -n "$HELPER" console-restart 2>/dev/null; then
        say "  控制台：$(systemctl is-active "$CONSOLE_UNIT_NAME" || true)"
    else
        warn "  控制台未重启：printf \"'\\n\" | sudo -S systemctl restart $CONSOLE_UNIT_NAME"
    fi
fi

say "完成。回滚：tar xzf $BK/code-$TS.tar.gz -C $BASE && sudo systemctl restart $UNIT_NAME"
