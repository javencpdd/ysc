#!/usr/bin/env bash
# ============================================================
# m20-ai-detect 部署脚本（在开发机上执行，不在 104 上执行）
#
# 用法：
#   ./deploy/install.sh                    # 默认部署到 m20pro-GOS.104:/home/djw/m20-ai-detect
#   HOST=m20pro-NOS.106 ./deploy/install.sh # 换主机（会顺带换 src 里的默认配置注释）
#   SKIP_TESTS=1 ./deploy/install.sh        # 跳过本地测试（调试期用）
#   NO_RESTART=1 ./deploy/install.sh        # 只同步代码不重启（首次部署先跑这个 + bootstrap.sh）
#
# 设计原则：
#   1. 部署前必过测试（除非显式跳过）——坏代码不进主机
#   2. 远端先备份再覆盖——.env 与旧代码可一键回滚
#   3. 同步后远端先 import 自检再重启——语法错误不会打爆服务
#   4. 全程 rsync --delete，保证远端 == 本地（.env 与 spool/ 等运行数据除外）
# ============================================================
set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_ROOT"

HOST="${HOST:-m20pro-GOS.104}"
REMOTE_DIR="${REMOTE_DIR:-/home/djw/m20-ai-detect}"
PYTHON="${PYTHON:-python3}"
SKIP_TESTS="${SKIP_TESTS:-0}"
NO_RESTART="${NO_RESTART:-0}"

say()  { printf "\033[36m[deploy]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[deploy][warn]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[31m[deploy][fail]\033[0m %s\n" "$*" >&2; exit 1; }

# ---- 1. 本地预检 ----------------------------------------------------------
say "1/6 本地预检"
if [[ "$SKIP_TESTS" != "1" ]]; then
    say "  跑测试（PYTHONPATH=src unittest，应全绿）..."
    PYTHONPATH=src "$PYTHON" -m unittest discover -s tests 2>&1 | tail -3 \
        || die "测试未过，终止部署"
else
    warn "  SKIP_TESTS=1，跳过测试"
fi

say "  检查上游 pkill 关键词（push_video/v4l2/gst-launch，排除 config.py 的守卫定义）..."
if grep -rnIE "push_video|v4l2|gst-launch" --exclude-dir=__pycache__ src deploy/*.service 2>/dev/null | grep -v "FORBIDDEN_TOKENS = "; then
    die "源码或 unit 含禁用关键词，会被机器人侧 restart.sh 的 pkill 误杀"
fi
say "  ok"

say "  检查 LF 行尾（CRLF 会在 Linux 上报 bad interpreter）..."
LFSET="src/m20_ai_detect/*.py deploy/*.sh deploy/*.service deploy/m20-ai-console-helper deploy/aiDetect"
if command -v file >/dev/null 2>&1; then
    if file $LFSET 2>/dev/null | grep -i crlf; then
        die "存在 CRLF 文件，先执行：dos2unix $LFSET"
    fi
else
    # Git Bash 等无 file 命令的环境：grep 直接找 \r
    if grep -lq $'\r' $LFSET 2>/dev/null; then
        die "存在 CRLF 文件（grep 检出），请转为 LF 后重试：$LFSET"
    fi
fi
say "  ok"

say "  检查 shell 脚本语法（bash -n）..."
for f in deploy/*.sh deploy/m20-ai-console-helper deploy/aiDetect; do
    "${BASH:-bash}" -n "$f" || die "$f 语法错误"
done
say "  ok"

# ---- 2. 远端连通性 --------------------------------------------------------
say "2/6 远端连通性：$HOST"
ssh -o ConnectTimeout=8 -o BatchMode=yes "$HOST" "echo ok" \
    || die "ssh $HOST 失败。先投递公钥：cat ~/.ssh/id_rsa.pub | ssh $HOST 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys'"

# ---- 3. 远端备份（代码 + env，回滚用） -------------------------------------
say "3/6 远端备份"
TS="$(date +%Y%m%d-%H%M%S)"
ssh "$HOST" "set -e
  mkdir -p $REMOTE_DIR/.backup
  if [[ -d $REMOTE_DIR/src ]]; then
    tar czf $REMOTE_DIR/.backup/code-$TS.tar.gz -C $REMOTE_DIR src deploy Makefile pyproject.toml 2>/dev/null || true
  fi
  if [[ -f $REMOTE_DIR/m20-ai-detect.env ]]; then
    cp -a $REMOTE_DIR/m20-ai-detect.env $REMOTE_DIR/.backup/env-$TS
  fi
  ls -1t $REMOTE_DIR/.backup/ | head -8
"
say "  备份位于远端 $REMOTE_DIR/.backup/（保留策略：手动清理，建议每月一次）"

# ---- 4. 同步代码 ----------------------------------------------------------
say "4/6 同步 -> $HOST:$REMOTE_DIR"
if command -v rsync >/dev/null 2>&1; then
    rsync -az --delete \
        --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
        --exclude '.runtime' --exclude 'spool' --exclude 'raw' \
        --exclude 'results' --exclude 'alerts' --exclude 'saved' \
        --exclude 'log' --exclude 'tmp' \
        --exclude 'm20-ai-detect.env' --exclude '.backup' \
        ./ "$HOST:$REMOTE_DIR/"
else
    # 开发机无 rsync（Windows Git Bash 常见）：tar over ssh 降级。
    # --delete 语义靠"先删远端代码侧路径"模拟——只删代码，数据目录一律不碰。
    warn "本机无 rsync，退化为 tar over ssh"
    ssh "$HOST" "cd $REMOTE_DIR 2>/dev/null && rm -rf src deploy tests docs Makefile pyproject.toml README.md USAGE.md .env.example || true"
    tar czf - \
        --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.runtime' --exclude='spool' --exclude='raw' \
        --exclude='results' --exclude='alerts' --exclude='saved' \
        --exclude='log' --exclude='tmp' \
        --exclude='m20-ai-detect.env' --exclude='.backup' \
        . | ssh "$HOST" "mkdir -p $REMOTE_DIR && tar xzf - -C $REMOTE_DIR"
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
    ok_sampler=0
    ok_console=0
    if ssh "$HOST" "sudo -n /usr/local/sbin/m20-ai-console-helper svc-restart" 2>/dev/null; then
        ok_sampler=1
    elif ssh "$HOST" "sudo -n systemctl restart m20-ai-detect" 2>/dev/null; then
        ok_sampler=1
    fi
    if ssh "$HOST" "sudo -n /usr/local/sbin/m20-ai-console-helper console-restart" 2>/dev/null; then
        ok_console=1
    fi
    if [[ "$ok_sampler" == "1" ]]; then
        say "  采样器已重启（$(ssh "$HOST" "systemctl is-active m20-ai-detect" 2>/dev/null)）"
    else
        warn "  采样器未能自动重启（helper 未装或 sudo 需口令）。手动执行："
        warn "    ssh $HOST \"printf \\\"'\\n\\\" | sudo -S systemctl restart m20-ai-detect\""
    fi
    if [[ "$ok_console" == "1" ]]; then
        say "  控制台已重启"
    else
        warn "  控制台未自动重启（首次部署时属正常：先跑 console-bootstrap.sh 装入 helper/sudoers）"
    fi
    ssh "$HOST" "journalctl -u m20-ai-detect -n 5 --no-pager | tail -5" || true
else
    warn "  NO_RESTART=1，未重启。首次部署请在 104 上先跑 deploy/bootstrap.sh"
fi

# ---- 6. 结果确认 ----------------------------------------------------------
say "6/6 完成"
say "  远端日志 : ssh $HOST 'journalctl -u m20-ai-detect -f'"
say "  远端统计 : ssh $HOST 'cd $REMOTE_DIR && PYTHONPATH=src python3 -m m20_ai_detect stats'"
say "  终端命令 : ssh $HOST 'aiDetect status'（升级后先在 104 跑 bash deploy/console-bootstrap.sh 重装 helper/sudoers/aiDetect）"
say "  回滚     : ssh $HOST 'cd $REMOTE_DIR && tar xzf .backup/code-$TS.tar.gz && sudo systemctl restart m20-ai-detect'"
say "部署完成：$TS"
