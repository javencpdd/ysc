#!/usr/bin/env bash
# ============================================================
# 部署脚本共用的"身份解析"（ADR-017）。
#
# 被 source，不直接执行：
#   . "$(dirname "${BASH_SOURCE[0]}")/identity.sh"
#   detect_identity "$BASE"
#   # 之后：$APP_ID / $UNIT / $CONSOLE_UNIT / $ENV_FILE / $CONSOLE_ENV_FILE
#   #       $HELPER / $SUDOERS / $LOGROTATE_CONF / $RUN_USER
#
# 为什么 shell 里也要一份：unit/env/helper 的名字由 app_id 派生，而 bootstrap 与
# install-local 都是在**目标机**上跑的 bash。解析规则与 Python 侧
# ``identity.discover_app_id`` 逐条对齐（含鸡生蛋问题的解法）：
#
#   1. 环境变量 M20AIC_APP_ID > M20AI_APP_ID（最高优先，用于手动指定）
#   2. 扫 <base>/*-ai-detect.env：文件内显式 M20AI_APP_ID > 文件名前缀
#   3. 都没有 → 缺省 m20
#
# 向后兼容的关键：**老部署（env 里没有 M20AI_APP_ID）解析结果就是 m20**，
# 于是 unit 名 / env 名 / helper 路径与改造前逐字相同，脚本一行都不用改。
# ============================================================

#: app_id 字符集与 src/m20_ai_detect/identity.py 的 APP_ID_RE 保持一致。
#: 注意：放在**变量**里的正则按 POSIX ERE 解释，{} 区间不能加反斜杠（会失配）。
IDENT_RE='^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$'

#: 缺省身份 = 原 M20 部署
IDENT_DEFAULT_APP_ID=m20

# identity_msg <level> <text>：统一前缀的提示（say/warn 由调用方定义时优先用它们的）
_ident_say()  { printf '\033[36m[identity]\033[0m %s\n' "$*"; }
# 注意：fmt 必须是**第一个**参数，后面的才是替换值（不能把值和文本拼成一个参数）
_ident_warn() {
    local fmt="$1"; shift
    printf "\033[33m[identity][warn]\033[0m $fmt\n" "$@" >&2
}

# identity_valid <app_id>：字符集校验，非法返回 1
identity_valid() {
    [[ "${1:-}" =~ $IDENT_RE ]]
}

# identity_check_or_default <app_id>：非法则告警并退回缺省值（不 die：
# 身份解析失败不该让整个部署脚本退出，退回 m20 至少还能按老路径跑）
identity_check_or_default() {
    local raw="${1:-}"
    if [[ -z "$raw" ]]; then
        printf '%s' "$IDENT_DEFAULT_APP_ID"
        return 0
    fi
    if identity_valid "$raw"; then
        printf '%s' "$raw"
        return 0
    fi
    _ident_warn "app_id=%s 非法（只能含字母/数字/下划线/连字符，≤32 位，字母或数字开头），退回 %s" \
        "$raw" "$IDENT_DEFAULT_APP_ID"
    printf '%s' "$IDENT_DEFAULT_APP_ID"
}

# identity_scan_base <base>：扫目录反查 app_id（模仿 identity.scan_app_id）
identity_scan_base() {
    local base="${1:-}"
    local f val app
    [[ -d "$base" ]] || { printf '%s' "$IDENT_DEFAULT_APP_ID"; return 0; }
    # glob 天然按字典序展开，与 Python 侧 list_app_ids 的 sorted() 一致
    for f in "$base"/*-ai-detect.env; do
        [[ -f "$f" ]] || continue          # 无匹配时 glob 原样返回，跳过
        val="$(sed -n 's/^M20AI_APP_ID=//p' "$f" 2>/dev/null | head -1 | tr -d "'\"\r")"
        if [[ -n "$val" ]]; then
            printf '%s' "$val"
            return 0
        fi
        app="$(basename "$f")"
        app="${app%-ai-detect.env}"
        printf '%s' "$app"
        return 0
    done
    printf '%s' "$IDENT_DEFAULT_APP_ID"
}

# detect_identity [base]：解析身份并导出全部派生名字。
# 用法：BASE=/x/y; detect_identity "$BASE"; echo "$APP_ID $ENV_FILE"
detect_identity() {
    local base="${1:-${BASE:-}}"
    local raw="${M20AIC_APP_ID:-${M20AI_APP_ID:-}}"
    [[ -n "$raw" ]] || raw="$(identity_scan_base "$base")"

    APP_ID="$(identity_check_or_default "$raw")"
    BASE="${base}"

    # ---- 由 app_id 派生的全部对外名字（与 identity.Identity 逐条对应）----
    UNIT="$APP_ID-ai-detect.service"
    CONSOLE_UNIT="$APP_ID-ai-console.service"
    UNIT_NAME="$APP_ID-ai-detect"
    CONSOLE_UNIT_NAME="$APP_ID-ai-console"
    ENV_BASENAME="$APP_ID-ai-detect.env"
    CONSOLE_ENV_BASENAME="$APP_ID-ai-console.env"
    SUDOERS_NAME="$APP_ID-ai-console"
    # 渲染产物名（与 deploy/render_units.py DEFAULTS 的 out="%s-..." 对应）。
    # 与"目标安装名"区分：HELPER/SUDOERS 装到 /usr/local/sbin 与
    # /etc/sudoers.d，文件名另有一套（SUDOERS_NAME）。
    HELPER_BASENAME="$APP_ID-ai-console-helper"
    SUDOERS_BASENAME="$APP_ID-ai-console.sudoers"

    # 带 BASE 的完整路径（BASE 为空时退化成文件名，供拼命令用）
    if [[ -n "$BASE" ]]; then
        ENV_FILE="$BASE/$ENV_BASENAME"
        CONSOLE_ENV_FILE="$BASE/$CONSOLE_ENV_BASENAME"
        LOGROTATE_CONF="/etc/logrotate.d/$APP_ID-ai-detect"
    else
        ENV_FILE="$ENV_BASENAME"
        CONSOLE_ENV_FILE="$CONSOLE_ENV_BASENAME"
        LOGROTATE_CONF="/etc/logrotate.d/$APP_ID-ai-detect"
    fi

    # helper 路径**不由 BASE 决定**（装到 /usr/local/sbin，systemd 沙箱外）
    HELPER="/usr/local/sbin/$APP_ID-ai-console-helper"
    SUDOERS="/etc/sudoers.d/$SUDOERS_NAME"

    # 运行账户：显式 M20AI_RUN_USER > 当前登录用户。
    # 老 GOS 部署当前用户就是 user ⇒ 与 unit 里写死的 User=user 一致；
    # 换到 ysc 等账户的机器（Lite3）时不用再手改 unit。
    RUN_USER="${M20AI_RUN_USER:-$(id -un 2>/dev/null || echo user)}"
    RUN_GROUP="${M20AI_RUN_GROUP:-$RUN_USER}"

    export APP_ID BASE UNIT CONSOLE_UNIT UNIT_NAME CONSOLE_UNIT_NAME
    export ENV_BASENAME CONSOLE_ENV_BASENAME ENV_FILE CONSOLE_ENV_FILE
    export HELPER SUDOERS SUDOERS_NAME LOGROTATE_CONF RUN_USER RUN_GROUP
    export HELPER_BASENAME SUDOERS_BASENAME
}

# render_units_into <out_dir> [deploy_dir]：在现场用 deploy/render_units.py 渲染 unit。
# 渲染失败（老主机缺 src/、python 版本不符等）时返回 1，由调用方决定是否
# 退回用仓库里提交的 m20-ai-*.service。stdout 保留（"写入 <path>" 对现场有用）。
#
# Windows/Git Bash 开发机上两个坑一起治（目标机 Linux 均无此行为）：
#   ① MSYS 隐式参数改写会把 **值** 里形如 /usr/local/sbin/... 的字符串
#      污染成 C:/Program Files/Git/usr/local/sbin/...（静默写错配置）；
#   ② 但关掉改写后，Windows 的 python.exe 又不认 /c/Users/... 形式的
#      脚本/文件路径（会解释成 C:\c\Users\...）。
# 解法：MSYS_NO_PATHCONV=1 关隐式改写 + _ident_win() 把真实文件路径显式
# 转成 Windows 形式；Linux 上 _ident_win 原样返回。
_ident_win() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1" 2>/dev/null || printf '%s' "$1"
    else
        printf '%s' "$1"
    fi
}
render_units_into() {
    local out_dir="${1:?render_units_into 需要 out_dir}"
    local deploy_dir="${2:-$BASE/deploy}"
    [[ -f "$deploy_dir/render_units.py" ]] || return 1
    mkdir -p "$out_dir"
    MSYS_NO_PATHCONV=1 python3 "$(_ident_win "$deploy_dir/render_units.py")" \
        --unit all \
        --app-id "$APP_ID" \
        --base-dir "$(_ident_win "$BASE")" \
        --run-user "$RUN_USER" \
        --run-group "$RUN_GROUP" \
        --out-dir "$(_ident_win "$out_dir")"
}
