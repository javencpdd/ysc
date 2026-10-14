#!/usr/bin/env bash
#
# 在**开发机（PC）**上生成精简部署包。
#
# 为什么需要它：项目里 frontend/node_modules 与 .venv 有几百 MB，
# 整个目录往 196 传既慢又没必要 —— 196 只需要后端源码 + 已构建好的前端产物。
#
# 用法（Git Bash / WSL / Linux）：
#   bash deploy/pack.sh                       # 生成 m20pro-console-deploy.tar.gz
#   bash deploy/pack.sh /tmp/m20.tgz          # 指定输出路径
#
set -euo pipefail

OUT="${1:-m20pro-console-deploy.tar.gz}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
PKG="$TMP_DIR/m20pro_console"

mkdir -p "$PKG"
echo "[pack] 收集文件 ..."
cp -r "$SRC_DIR/backend" "$PKG/"
cp -r "$SRC_DIR/deploy"  "$PKG/"
[[ -f "$SRC_DIR/requirements.txt" ]] && cp "$SRC_DIR/requirements.txt" "$PKG/" || true
[[ -f "$SRC_DIR/config.example.toml" ]] && cp "$SRC_DIR/config.example.toml" "$PKG/" || true

# tools/ 里的探针与抓包分析在 196 上排障很实用，一并带上
[[ -d "$SRC_DIR/tools" ]] && cp -r "$SRC_DIR/tools" "$PKG/" || true
# 计划书：196 上排障主要靠它（体积很小）
[[ -d "$SRC_DIR/note" ]] && cp -r "$SRC_DIR/note" "$PKG/" || true

if [[ -d "$SRC_DIR/frontend/dist" ]]; then
    mkdir -p "$PKG/frontend"
    cp -r "$SRC_DIR/frontend/dist" "$PKG/frontend/"
    echo "[pack] 已包含前端构建产物 frontend/dist"
else
    echo "[pack] 警告：未发现 frontend/dist（196 上将只提供 API）"
    echo "        建议先执行：cd frontend && npm run build"
fi

# 清理本地缓存与虚拟环境，减小体积
find "$PKG" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -type d -name ".venv" -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -type d -name "venv" -prune -exec rm -rf {} + 2>/dev/null || true
# 抓包文件较大，部署包不带（需要时单独 scp）
[[ -d "$PKG/tools/capture" ]] && rm -rf "$PKG/tools/capture" || true

tar -czf "$OUT" -C "$TMP_DIR" m20pro_console
rm -rf "$TMP_DIR"

SIZE="$(du -h "$OUT" 2>/dev/null | awk '{print $1}')"
cat <<EOF

$(echo -e '\033[1;32m')打包完成$(echo -e '\033[0m')  $OUT  ($SIZE)

上传到 196：
  scp "$OUT" m20pro-f20-0-196:/tmp/

在 196 上部署（注意用 http 镜像绕开时钟/TLS 问题）：
  ssh m20pro-f20-0-196
  cd /tmp && tar xzf $(basename "$OUT")
  sudo bash m20pro_console/deploy/install.sh /home/djw/monitor
EOF
