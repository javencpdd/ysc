#!/bin/bash
# deploy_196_tar.sh — Windows 无 rsync 时的 196 降级部署（tar over scp）
#
# 本地用法（在项目根目录）：
#   cd frontend && npm run build && cd ..
#   bash deploy/deploy_196_tar.sh
#
# 流程：本地打包 backend/dist → scp 到 /tmp → 远端本脚本解包覆盖 → 重启 → 验证
# 与 deploy_196.sh 的差异：不做 rsync --delete（tar 覆盖式；dist 先删后解包保证干净）
set -euo pipefail

HOST="${M20_HOST:-m20pro-f20-0-196}"
REMOTE_DIR="${M20_REMOTE:-/home/djw/monitor}"
SERVICE_NAME="m20pro-console"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [1/5] 本地打包"
rm -f /tmp/m20_backend_update.tgz /tmp/m20_dist_update.tgz
tar czf /tmp/m20_backend_update.tgz \
  --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='hls' \
  -C "$LOCAL_DIR" backend/
tar czf /tmp/m20_dist_update.tgz -C "$LOCAL_DIR/frontend" dist/
ls -la /tmp/m20_backend_update.tgz /tmp/m20_dist_update.tgz

echo "==> [2/5] 上传到 $HOST:/tmp"
scp /tmp/m20_backend_update.tgz /tmp/m20_dist_update.tgz "$HOST:/tmp/"

echo "==> [3/5] 远端解包（备份旧 backend）"
ssh "$HOST" "bash -s" <<REMOTE
set -e
TS=\$(date +%m%d%H%M%S)
cd "$REMOTE_DIR"
cp -r backend /tmp/m20_backend_bak_\$TS
tar xzf /tmp/m20_backend_update.tgz -C "$REMOTE_DIR/"
find backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf frontend/dist
tar xzf /tmp/m20_dist_update.tgz -C frontend/
echo "backup: /tmp/m20_backend_bak_\$TS"
REMOTE

echo "==> [4/5] 重启服务"
ssh "$HOST" "printf \"'\n\" | sudo -S systemctl restart $SERVICE_NAME && sleep 3 && systemctl is-active $SERVICE_NAME"

echo "==> [5/5] 验证"
ssh "$HOST" "curl -s --max-time 5 http://127.0.0.1:8080/health; echo; curl -s --max-time 5 http://127.0.0.1:8080/api/v1/control/status | head -c 420; echo; echo '--- index bundle ---'; grep -o 'assets/index-[^\"]*\.js' $REMOTE_DIR/frontend/dist/index.html"
echo "==> 完成。控制台： http://192.168.0.196:8080/"
