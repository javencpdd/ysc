#!/usr/bin/env bash
# 在 196 上以 root 应用部署包。
#
# 用法（PC 侧）：
#   bash deploy/pack.sh /tmp/m20console.tgz
#   scp /tmp/m20console.tgz m20pro-f20-0-196:/tmp/
#   scp deploy/_apply.sh   m20pro-f20-0-196:/tmp/
#   ssh m20pro-f20-0-196 "printf \"'\n\" | sudo -S bash /tmp/_apply.sh /tmp/m20console.tgz [安装目录]"
#
# 安装目录默认 /home/djw/monitor；**换机器务必显式传**（不同 AOS 镜像的
# 家目录 / 用户名可能不同）。
#
# ⚠️ 本脚本**自己解压 tarball**。曾经的坑：只 scp 新包却复用上一次解压的目录，
#    结果改动的代码没上车、页面还是旧的，而日志显示"部署成功"——最难查的一类。
#
# ⚠️ 本脚本**不装系统级 helper**（/usr/local/sbin/m20-ap-ctl 等）。
#    新机器首次部署请先跑 deploy/install.sh；只换应用目录时补跑
#    deploy/install_helpers.sh。末尾会做一次可用性自检并提示。
set -euo pipefail

TGZ="${1:-/tmp/m20console.tgz}"
DST="${2:-/home/djw/monitor}"
SRC=/tmp/m20pro_console

[[ -f "$TGZ" ]] || { echo "找不到部署包：$TGZ" >&2; exit 1; }
[[ -d "$DST" ]] || { echo "安装目录不存在：$DST（首次部署请用 deploy/install.sh）" >&2; exit 1; }

echo "[0/5] 解压 $TGZ ..."
rm -rf "$SRC"
tar xzf "$TGZ" -C /tmp
[[ -f "$SRC/backend/main.py" ]] || { echo "解压结果异常：缺 $SRC/backend/main.py" >&2; exit 1; }
# 打上时间戳：日志里能直接看出这次用的是哪一包
echo "      包时间 $(date -r "$TGZ" '+%F %T')  md5 $(md5sum "$TGZ" | awk '{print $1}')"

echo "[1/5] 覆盖后端源码 ..."
cp -r "$SRC/backend/." "$DST/backend/"

echo "[2/5] 替换前端构建产物（旧目录先改名，成功后才删） ..."
rm -rf "$DST/frontend/dist.old"
if [[ -d "$DST/frontend/dist" ]]; then
    mv "$DST/frontend/dist" "$DST/frontend/dist.old"
fi
cp -r "$SRC/frontend/dist" "$DST/frontend/dist"
rm -rf "$DST/frontend/dist.old"

echo "[3/5] 同步 tools/note/deploy ..."
cp -r "$SRC/tools/." "$DST/tools/" 2>/dev/null || true
cp -r "$SRC/note/."  "$DST/note/"  2>/dev/null || true
mkdir -p "$DST/deploy"
cp -r "$SRC/deploy/." "$DST/deploy/" 2>/dev/null || true

echo "[4/5] 清理 __pycache__ 并修正属主 ..."
find "$DST/backend" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$DST/tools"   -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
chown -R user:user "$DST"

echo "[5/5] 重启控制台服务 ..."
systemctl restart m20pro-console
sleep 2
systemctl is-active m20pro-console

# ---- 收尾自检：系统级 helper 是**独立安装**的，别假设它一定在
echo "[自检] 受控提权 helper ..."
for h in m20-ap-ctl m20-video-ctl; do
    if [[ -x "/usr/local/sbin/$h" ]]; then
        echo "       $h 已安装"
    else
        echo "  ⚠️  $h 缺失 —— 热点/推流面板将不可写。"
        echo "      补装：sudo bash $DST/deploy/install_helpers.sh \$(stat -c %U "$DST")"
    fi
done
if ! ls /etc/sudoers.d/m20-ap-ctl /etc/sudoers.d/m20-video-ctl >/dev/null 2>&1; then
    echo "  ⚠️  sudoers 白名单缺失 —— 同上，跑 install_helpers.sh"
fi

echo "APPLY_OK"
