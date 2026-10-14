#!/usr/bin/env bash
#
# 把本地修改后的后端 + 前端 dist 增量同步到 196 并重启服务（日常迭代用）。
#
# 前置：
#   1. 本机已配置到 196 的 SSH 免密（ssh-copy-id / known_hosts）；
#   2. 196 上已完成 install.sh 首次安装；
#   3. 前端改动需先本地构建：cd frontend && npm run build
#
# 用法：
#   bash deploy/deploy_196.sh                      # 默认 m20pro-f20-0-196:/home/djw/monitor
#   M20_HOST=user@192.168.0.196 M20_REMOTE=/home/djw/monitor bash deploy/deploy_196.sh
#   bash deploy/deploy_196.sh --no-restart         # 只同步不重启
#
set -euo pipefail

HOST="${M20_HOST:-m20pro-f20-0-196}"     # 走 ~/.ssh/config 别名，或改成 user@IP
REMOTE_DIR="${M20_REMOTE:-/home/djw/monitor}"
SERVICE_NAME="m20pro-console"
RESTART=1
[[ "${1:-}" == "--no-restart" ]] && RESTART=0

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 目标: $HOST:$REMOTE_DIR"
echo "==> 本地: $LOCAL_DIR"

echo "==> [1/3] 同步后端（排除 venv / __pycache__）"
rsync -avz --delete \
  --exclude 'venv' --exclude '__pycache__' --exclude '*.pyc' --exclude 'hls' \
  "$LOCAL_DIR/backend/" "$HOST:$REMOTE_DIR/backend/"

if [[ -d "$LOCAL_DIR/frontend/dist" ]]; then
    echo "==> [2/3] 同步前端静态资源 dist"
    rsync -avz --delete "$LOCAL_DIR/frontend/dist/" "$HOST:$REMOTE_DIR/frontend/dist/"
else
    echo "==> [2/3] 跳过：未发现 frontend/dist（先 npm run build）"
fi

if [[ $RESTART -eq 1 ]]; then
    echo "==> [3/3] 重启服务"
    ssh "$HOST" "sudo systemctl restart $SERVICE_NAME && sleep 3 && systemctl is-active $SERVICE_NAME && curl -s --max-time 5 http://127.0.0.1:8080/health"
else
    echo "==> [3/3] 跳过重启（--no-restart）"
fi
echo "==> 完成。控制台： http://192.168.0.196:8080/"
