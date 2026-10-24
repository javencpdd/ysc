#!/usr/bin/env bash
# ============================================================
# m20-ai-detect 部署脚本（在开发机上执行，不在 104 上执行）
#
# 用法（推荐直接写 user@IP，不依赖 ~/.ssh/config 别名）：
#   ./deploy/install.sh user@192.168.0.196             # 部署到该主机
#   ./deploy/install.sh user@192.168.0.196 --check      # 只测连通性+远端环境，不动任何文件
#   ./deploy/install.sh user@192.168.0.196 --no-restart # 只同步代码不重启（首次部署前）
#   cp deploy/site.env.example deploy/site.env          # 可选：部署前统一填目标机/相机/端口（docs §3.5）
#   ./deploy/install.sh --with-env                      # 用 deploy/site.env 覆盖远端 env（先备份）
#   HOST=user@192.168.0.196 ./deploy/install.sh         # 环境变量写法同样支持
#   HOST=m20pro-GOS.104 ./deploy/install.sh             # 也支持 ssh 别名（需先配 ~/.ssh/config）
#   ./deploy/install.sh --app-id lite3                  # 换部署身份（ADR-017；等价 site.env 的 APP_ID）
#   SKIP_TESTS=1 ./deploy/install.sh ...                # 跳过本地测试（调试期用）
#
# 设计原则：
#   1. 部署前必过测试（除非显式跳过）——坏代码不进主机
#   2. 远端先备份再覆盖——.env 与旧代码可一键回滚
#   3. 同步后远端先 import 自检再重启——语法错误不会打爆服务
#   4. 全程 rsync --delete，保证远端 == 本地（.env 与 spool/ 等运行数据除外）
#   5. 身份（ADR-017）：APP_ID 来自 site.env，决定远端 env 文件名与被重启的 unit 名；
#      缺省 m20 ⇒ 与改造前逐字一致。改名的完整流程见 deploy/migrate-rename.sh
# ============================================================
set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_ROOT"

HOST_GIVEN="${HOST:-}"
DIR_GIVEN="${REMOTE_DIR:-}"
HOST="${HOST:-m20pro-GOS.104}"
REMOTE_DIR="${REMOTE_DIR:-/home/djw/m20-ai-detect}"
SITE_ENV="${SITE_ENV:-deploy/site.env}"
PYTHON="${PYTHON:-python3}"
SKIP_TESTS="${SKIP_TESTS:-0}"
NO_RESTART="${NO_RESTART:-0}"
WITH_ENV=0
CHECK_ONLY=0
#: 缺省身份 = 原 M20 部署（保证老 site.env 渲染/路径一字不变）
APP_ID="${APP_ID:-m20}"

# 部署前统一配置：site.env 里的 DEPLOY_HOST / DEPLOY_DIR / APP_ID 作为默认值
#（显式传入的不覆盖）
if [[ -f "$SITE_ENV" ]]; then
    if [[ -z "$HOST_GIVEN" ]]; then
        _h="$(sed -n 's/^DEPLOY_HOST=//p' "$SITE_ENV" | head -1)"
        [[ -n "$_h" ]] && HOST="$_h"
    fi
    if [[ -z "$DIR_GIVEN" ]]; then
        _d="$(sed -n 's/^DEPLOY_DIR=//p' "$SITE_ENV" | head -1)"
        [[ -n "$_d" ]] && REMOTE_DIR="$_d"
    fi
    if [[ -z "${APP_ID_GIVEN:-}" ]]; then
        _a="$(sed -n 's/^APP_ID=//p' "$SITE_ENV" | head -1)"
        [[ -n "$_a" ]] && APP_ID="$_a"
    fi
fi

say()  { printf "\033[36m[deploy]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[deploy][warn]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[31m[deploy][fail]\033[0m %s\n" "$*" >&2; exit 1; }

usage() { sed -n '3,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)       CHECK_ONLY=1; shift ;;
        --no-restart)  NO_RESTART=1; shift ;;
        --skip-tests)  SKIP_TESTS=1; shift ;;
        --with-env)    WITH_ENV=1; shift ;;
        --app-id)      APP_ID="${2:-}"; APP_ID_GIVEN=1; shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        -*)            die "未知参数：$1（--help 看用法）" ;;
        *)             HOST="$1"; shift ;;
    esac
done

# APP_ID 字符集校验（与 src/m20_ai_detect/identity.py 的 APP_ID_RE 一致）：
# 非法值会让 systemd unit 名/env 文件名跟着坏掉，必须在本地就拦下
if ! printf '%s' "$APP_ID" | grep -qE '^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$'; then
    die "APP_ID=$APP_ID 非法：只能含字母/数字/下划线/连字符，最长 32 位，且以字母或数字开头"
fi
say "部署身份：APP_ID=$APP_ID（unit=$APP_ID-ai-detect / $APP_ID-ai-console，env=$APP_ID-ai-detect.env）"

# 目标规范化提示：不带 @ 时用的是 ssh 默认用户（常与本机登录用户同名），最容易「以为连的是 user」
if [[ "$HOST" != *@* ]]; then
    warn "HOST=$HOST 未含用户名，将使用 ssh 默认用户（本机是 $(id -un)）。"
    warn "建议写成 user@<IP> 形式，例如：./deploy/install.sh user@192.168.0.196"
fi

# ---- 1. 本地预检（--check 只测连通性，跳过）--------------------------------
if [[ "$CHECK_ONLY" == "1" ]]; then
    say "0/6 --check 模式：跳过本地预检，只测连通性与远端环境"
else
say "1/6 本地预检"
if [[ "$SKIP_TESTS" != "1" ]]; then
    say "  跑测试（PYTHONPATH=src unittest，应全绿）..."
    PYTHONPATH=src "$PYTHON" -m unittest discover -s tests 2>&1 | tail -3 \
        || die "测试未过，终止部署"
else
    warn "  SKIP_TESTS=1，跳过测试"
fi

say "  检查上游 pkill 关键词（push_video/v4l2/gst-launch，排除注释行）..."
# 只扫**会进 argv 的面**：unit/模板/profile/env 示例。src 不扫——ADR-016 起 device://
# 适配器在 sources.py 内部按白名单构造 -f v4l2（受 allow_local_device 闸门，属既定设计），
# env 侧另有 Config.validate 的 FORBIDDEN_TOKENS 运行时兜底。
# 只查**非注释行**——profile 的注释里会解释"为什么不能用 -f v4l2"，那是文档不是命令行。
PKILL_BAD="$(grep -rnIE "push_video|v4l2|gst-launch" --exclude-dir=__pycache__ \
    deploy/*.service deploy/units/*.tmpl deploy/profiles/*.env deploy/*.env.example 2>/dev/null \
    | grep -vE ':[0-9]+:[[:space:]]*#' || true)"
if [[ -n "$PKILL_BAD" ]]; then
    printf '%s\n' "$PKILL_BAD" >&2
    die "unit/模板/profile/env 含禁用关键词（非注释行），会被机器人侧 restart.sh 的 pkill 误杀"
fi
say "  ok"

say "  检查 LF 行尾（CRLF 会在 Linux 上报 bad interpreter / syntax error）..."
LFSET="src/m20_ai_detect/*.py deploy/*.sh deploy/*.service deploy/*.py deploy/identity.sh deploy/units/*.tmpl deploy/profiles/*.env deploy/m20-ai-console-helper deploy/m20-ai-console.sudoers deploy/aiDetect webconsole/*.py webconsole/static/*.html"
# 用 Python 按字节检测：Windows 的 `file` 与 MSYS 的 `grep $'\r'` 都会漏检，
# 必须读原始字节（2026-10-18 实测：Write 落盘的 .sh 带 CRLF，上机后 bash 直接语法错误）。
CRLF_BAD="$("$PYTHON" - $LFSET <<'PYEOF'
import glob, sys
bad = []
for pat in sys.argv[1:]:
    for f in glob.glob(pat):
        try:
            with open(f, "rb") as fh:
                if b"\r\n" in fh.read():
                    bad.append(f)
        except OSError:
            pass
print(" ".join(bad))
PYEOF
)"
if [[ -n "${CRLF_BAD// /}" ]]; then
    die "存在 CRLF 文件：$CRLF_BAD
修法（任选）：
  python3 - <<'EOF2'
import glob
for f in glob.glob('deploy/*.sh')+glob.glob('src/**/*.py', recursive=True):
    d=open(f,'rb').read()
    if b'\r\n' in d: open(f,'wb').write(d.replace(b'\r\n', b'\n'))
EOF2
  # 或：dos2unix $CRLF_BAD"
fi
say "  ok"

say "  检查 shell 脚本语法（bash -n）..."
for f in deploy/*.sh deploy/m20-ai-console-helper deploy/aiDetect; do
    [[ -f "$f" ]] || continue
    "${BASH:-bash}" -n "$f" || die "$f 语法错误"
done
say "  ok"

# ---- 2. 远端连通性 --------------------------------------------------------
fi   # end of 本地预检（非 --check）

say "2/6 远端连通性：$HOST"
# 用 2>&1 捕获，不落临时文件（Windows Git Bash 的 rm 钩子会拒绝 mktemp 路径）
if ! OUT="$(ssh -q -o LogLevel=ERROR -o ConnectTimeout=8 -o BatchMode=yes "$HOST" "echo ok" 2>&1)"; then
    E="$OUT"
    case "$E" in
        *"Could not resolve hostname"*)
            die "主机名/别名解析失败：$HOST
  · 想用 IP：./deploy/install.sh user@192.168.0.196
  · 想用别名：先在 ~/.ssh/config 配好 Host 段，并确认 ssh $HOST 能通" ;;
        *"Connection refused"*)
            die "连接被拒绝：$HOST 的 22 端口未监听/被防火墙拦（先在目标机 systemctl status ssh）" ;;
        *"timed out"*|*"Connection timed out"*)
            die "连接超时：$HOST 不可达（同网段吗？IP 对吗？Wi-Fi/网关通吗？先 ping 一下）" ;;
        *"No route to host"*)
            die "不可达（No route to host）：$HOST 与当前网络不同网段，或设备未上电/未连上 Wi-Fi" ;;
        *"Permission denied"*|*"no supported authentication"*)
            die "认证失败：公钥未投递。执行：
  cat ~/.ssh/id_rsa.pub | ssh $HOST 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys'" ;;
        *"Host key verification failed"*)
            die "主机指纹未知/已变：先手工 ssh $HOST 接受指纹（或 ssh-keygen -R $HOST 清旧记录）" ;;
        *)  CLEAN="$(printf '%s\n' "$E" | grep -vE 'WARNING|post-quantum|store now|upgraded|^\*\*' | tr '\n' ' ')"
            die "ssh $HOST 失败：${CLEAN:-$E}" ;;
    esac
fi

# --check：只读体检（不进本地测试/同步，不改远端任何文件）
if [[ "$CHECK_ONLY" == "1" ]]; then
    say "只读体检（--check）：不改动任何文件"
    # 用 sed 把身份相关的占位符替换掉：heredoc 必须加引号（不展开 $()），
    # 否则 $() 会在开发机上执行而不是目标机上执行
    if sed -e "s|__UNIT_DETECT__|$APP_ID-ai-detect|g" \
           -e "s|__UNIT_CONSOLE__|$APP_ID-ai-console|g" \
           -e "s|__REMOTE_DIR__|$REMOTE_DIR|g" <<'PROBE' \
        | ssh -q -o LogLevel=ERROR -o BatchMode=yes "$HOST" 'bash -s' 2>/dev/null
echo "  host    : $(hostname 2>/dev/null)"
echo "  user    : $(id -un) (uid=$(id -u))"
echo "  os      : $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")  $(uname -m)"
echo "  python  : $(python3 -V 2>&1)"
echo "  ffmpeg  : $(ffmpeg -version 2>/dev/null | head -1)"
echo "  disk    : $(df -h /home 2>/dev/null | awk 'NR==2{print $4" free on "$6}')"
echo "  memory  : $(awk '/MemAvailable/{printf "%d MB available", $2/1024}' /proc/meminfo 2>/dev/null)"
echo "  services: detect=$(systemctl show -p ActiveState --value __UNIT_DETECT__ 2>/dev/null || echo n/a)  console=$(systemctl show -p ActiveState --value __UNIT_CONSOLE__ 2>/dev/null || echo n/a)"
echo "  project : $(ls -d __REMOTE_DIR__ 2>/dev/null || echo '(未安装)')"
echo "  env     : $(ls -1 __REMOTE_DIR__/*-ai-detect.env 2>/dev/null | tr '\n' ' ')"
echo "  port    : 5050 监听数=$(ss -ltn 2>/dev/null | grep -c ':5050')"
PROBE
    then
        :
    else
        warn "远端体检命令未成功执行（ssh 能连上但命令失败），请手工 ssh $HOST 检查"
    fi
    EXTRA=""; [[ "$NO_RESTART" == "1" ]] && EXTRA=" --no-restart"
    say "  → 环境 OK 就正式部署：./deploy/install.sh $HOST$EXTRA"
    exit 0
fi

# ---- 3. 远端备份（代码 + env，回滚用） -------------------------------------
say "3/6 远端备份"
TS="$(date +%Y%m%d-%H%M%S)"
ssh "$HOST" "set -e
  mkdir -p $REMOTE_DIR/.backup
  if [[ -d $REMOTE_DIR/src ]]; then
    tar czf $REMOTE_DIR/.backup/code-$TS.tar.gz -C $REMOTE_DIR src deploy Makefile pyproject.toml 2>/dev/null || true
  fi
  for e in $REMOTE_DIR/*-ai-detect.env $REMOTE_DIR/*-ai-console.env; do
    [[ -f \"\$e\" ]] && cp -a \"\$e\" \"\$e.bak-\$(date +%Y%m%d-%H%M%S)\" 2>/dev/null || true
  done
  ls -1t $REMOTE_DIR/.backup/ | head -8
"
say "  备份位于远端 $REMOTE_DIR/.backup/（保留策略：手动清理，建议每月一次）"

# ---- 4. 同步代码 ----------------------------------------------------------
say "4/6 同步 -> $HOST:$REMOTE_DIR"
if command -v rsync >/dev/null 2>&1; then
    rsync -az --delete \
        --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude '.playwright-cli' --exclude '.pytest_cache' \
        --exclude '.venv' --exclude 'venv' --exclude 'node_modules' \
        --exclude '.runtime' --exclude 'spool' --exclude 'raw' \
        --exclude 'results' --exclude 'alerts' --exclude 'saved' \
        --exclude 'log' --exclude 'tmp' \
        --exclude '*-ai-detect.env' --exclude '*-ai-console.env' --exclude '.backup' \
        ./ "$HOST:$REMOTE_DIR/"
else
    # 开发机无 rsync（Windows Git Bash 常见）：tar over ssh 降级。
    # --delete 语义靠"先删远端代码侧路径"模拟——只删代码，数据目录一律不碰。
    warn "本机无 rsync，退化为 tar over ssh"
    ssh "$HOST" "cd $REMOTE_DIR 2>/dev/null && rm -rf src deploy tests docs Makefile pyproject.toml README.md USAGE.md .env.example || true"
    tar czf - \
        --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.playwright-cli' --exclude='.pytest_cache' \
        --exclude='.venv' --exclude='venv' --exclude='node_modules' \
        --exclude='.runtime' --exclude='spool' --exclude='raw' \
        --exclude='results' --exclude='alerts' --exclude='saved' \
        --exclude='log' --exclude='tmp' \
        --exclude='*-ai-detect.env' --exclude='*-ai-console.env' --exclude='.backup' \
        . | ssh "$HOST" "mkdir -p $REMOTE_DIR && tar xzf - -C $REMOTE_DIR"
fi

# ---- 4b. 远端配置：site.env 渲染成远端 env（首次自动写；已有则需 --with-env）----
# 目标文件名由 APP_ID 决定（ADR-017）；缺省 m20 时与改造前逐字相同。
say "4b/6 远端配置（APP_ID=$APP_ID）"
if [[ -f "$SITE_ENV" ]]; then
    mkdir -p .runtime
    # 目标目录以 site 文件为准（Windows Git Bash 会改写命令行/环境变量里的 /home/...）
    RENDER_SITE="$SITE_ENV"
    { cat "$SITE_ENV"; printf 'DEPLOY_DIR=%s\n' "$REMOTE_DIR"; } > .runtime/site-render.env
    RENDER_SITE=".runtime/site-render.env"
    "$PYTHON" deploy/render_env.py --kind detect  --site "$RENDER_SITE" --app-id "$APP_ID" \
        --out .runtime/render-detect.env \
        || die "渲染 detect env 失败（检查 $SITE_ENV）"
    "$PYTHON" deploy/render_env.py --kind console --site "$RENDER_SITE" --app-id "$APP_ID" \
        --out .runtime/render-console.env \
        || die "渲染 console env 失败（检查 $SITE_ENV）"
    for kind in detect console; do
        rf="$REMOTE_DIR/$APP_ID-ai-$kind.env"
        if ssh -q "$HOST" "test -f $rf" 2>/dev/null; then
            if [[ "$WITH_ENV" == "1" ]]; then
                ssh -q "$HOST" "cp -a $rf $rf.bak-\$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
                ssh -q "$HOST" "cat > $rf && chmod 600 $rf" < ".runtime/render-$kind.env"
                say "  已按 site.env 覆盖 $kind env（旧文件已备份为 *.bak-时间戳）"
            else
                say "  保留远端 $kind env（如需用 site.env 覆盖：--with-env）"
            fi
        else
            ssh -q "$HOST" "cat > $rf && chmod 600 $rf" < ".runtime/render-$kind.env"
            say "  首次写入 $kind env（来自 site.env）"
        fi
    done
else
    say "  未找到 $SITE_ENV —— 首次部署将由 bootstrap.sh 用模板生成默认 env"
fi

# ---- 5. 远端自检（语法 + import + doctor 快跑） ----------------------------
say "5/6 远端自检"
ssh "$HOST" "set -e
  cd $REMOTE_DIR
  mkdir -p spool raw results alerts saved log tmp
  python3 -m compileall -q src webconsole
  PYTHONPATH=src:. python3 -c 'import m20_ai_detect, webconsole; print(\"import ok, sampler v\" + m20_ai_detect.__version__ + \", console v\" + webconsole.__version__)'
"
if [[ "$NO_RESTART" != "1" ]]; then
    say "  重启服务（优先经 sudoers 白名单 helper，免密）"
    UNIT_NAME="$APP_ID-ai-detect"
    CONSOLE_UNIT_NAME="$APP_ID-ai-console"
    HELPER="/usr/local/sbin/$APP_ID-ai-console-helper"
    ok_sampler=0
    ok_console=0
    if ssh "$HOST" "sudo -n $HELPER svc-restart" 2>/dev/null; then
        ok_sampler=1
    elif ssh "$HOST" "sudo -n systemctl restart $UNIT_NAME" 2>/dev/null; then
        ok_sampler=1
    fi
    if ssh "$HOST" "sudo -n $HELPER console-restart" 2>/dev/null; then
        ok_console=1
    fi
    if [[ "$ok_sampler" == "1" ]]; then
        say "  采样器已重启（$(ssh "$HOST" "systemctl is-active $UNIT_NAME" 2>/dev/null)）"
    else
        warn "  采样器未能自动重启（helper 未装或 sudo 需口令）。手动执行："
        warn "    ssh $HOST \"printf \\\"'\\n\\\" | sudo -S systemctl restart $UNIT_NAME\""
    fi
    if [[ "$ok_console" == "1" ]]; then
        say "  控制台已重启"
    else
        warn "  控制台未自动重启（首次部署时属正常：先跑 console-bootstrap.sh 装入 helper/sudoers）"
    fi
    # 改过 APP_ID 时 unit 还没装到新名字，这里提醒一句（完整流程见 migrate-rename.sh）
    if [[ "$APP_ID" != "m20" ]]; then
        if ! ssh "$HOST" "systemctl cat $UNIT_NAME >/dev/null 2>&1"; then
            warn "远端还没有 $UNIT_NAME.service —— 新身份的 unit 未安装。"
            warn "  在目标机执行：bash deploy/bootstrap.sh && bash deploy/console-bootstrap.sh"
            warn "  （老 m20-* 服务不会被本脚本触碰，确认新身份正常后再手动停掉）"
        fi
    fi
    ssh "$HOST" "journalctl -u $UNIT_NAME -n 5 --no-pager | tail -5" || true
else
    warn "  NO_RESTART=1，未重启。首次部署请在目标机先跑 deploy/bootstrap.sh"
fi

# ---- 6. 结果确认 ----------------------------------------------------------
say "6/6 完成"
say "  远端日志 : ssh $HOST 'journalctl -u $APP_ID-ai-detect -f'"
say "  远端统计 : ssh $HOST 'cd $REMOTE_DIR && PYTHONPATH=src python3 -m m20_ai_detect stats'"
say "  终端命令 : ssh $HOST 'aiDetect status'（升级后先在目标机跑 bash deploy/console-bootstrap.sh 重装 helper/sudoers/aiDetect）"
say "  回滚     : ssh $HOST 'cd $REMOTE_DIR && tar xzf .backup/code-$TS.tar.gz && sudo systemctl restart $APP_ID-ai-detect'"
say "部署完成：$TS"
