#!/usr/bin/env bash
# 在 196 上定点替换前端构建产物（只换 frontend/dist，不动后端 / 配置 / 服务单元）。
# 用法（PC 侧）：
#   scp apply-dist.sh m20pro-f20-0-196:/tmp/
#   ssh m20pro-f20-0-196 "printf \"'\n\" | sudo -S bash /tmp/apply-dist.sh"
set -euo pipefail

DST=/home/djw/monitor/frontend
[[ -f /tmp/m20-dist.tgz ]] || { echo "找不到 /tmp/m20-dist.tgz" >&2; exit 1; }

cd "$DST"
TS=$(date +%Y%m%d-%H%M%S)

echo "[1/4] 备份当前 dist -> dist.bak-$TS"
rm -rf "dist.bak-$TS"
if [[ -d dist ]]; then mv dist "dist.bak-$TS"; fi

echo "[2/4] 解压新 dist"
tar xzf /tmp/m20-dist.tgz -C "$DST"
[[ -f dist/index.html ]] || { echo "解压异常：缺 dist/index.html" >&2; exit 1; }

echo "[3/4] 修正属主"
chown -R user:user dist

echo "[4/4] 重启 m20pro-console"
systemctl restart m20pro-console
sleep 2
systemctl is-active m20pro-console
echo "BACKUP=dist.bak-$TS"
ls -la dist/assets/
