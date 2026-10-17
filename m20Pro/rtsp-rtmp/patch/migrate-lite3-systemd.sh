#!/usr/bin/env bash
# ============================================================================
# Lite3(120) 推流：由「用户级 systemd」迁移为「系统级 systemd」
# 目的：与 M20(196) 的技术逻辑统一（系统级 service + 系统级 guard timer），
#       自启动不再依赖 loginctl Linger，运维命令统一为 systemctl（无 --user）。
#
# 前置（在调用本脚本之前、以 ysc 身份完成）：
#   systemctl --user stop/disable rtmp-forward.service
#   systemctl --user stop/disable rtmp-conn-guard-user.timer
# 必须先停用户级再起系统级，否则两套并存会重复推流、撞流名 live/lite3。
#
# 用法：sudo bash /tmp/migrate-lite3-systemd.sh
# ============================================================================
set -eu

install -m 0644 /tmp/rtmp-forward.system.service   /etc/systemd/system/rtmp-forward.service
install -m 0644 /tmp/rtmp-conn-guard.lite3.service /etc/systemd/system/rtmp-conn-guard.service

# 双保险：让脚本的自动识别候选也能命中 rtmp-forward（主路径仍是上面的显式传参）
if [ -f /usr/local/sbin/rtmp-conn-guard.sh ]; then
  cp -n /usr/local/sbin/rtmp-conn-guard.sh /usr/local/sbin/rtmp-conn-guard.sh.bak-sysmigrate || true
  sed -i 's/for c in m20video\.service rtsp_stream\.service; do/for c in m20video.service rtmp-forward.service rtsp_stream.service; do/' \
      /usr/local/sbin/rtmp-conn-guard.sh
fi

systemctl daemon-reload
systemctl enable --now rtmp-forward.service
systemctl enable --now rtmp-conn-guard.timer

echo "--- migrate done, status ---"
systemctl is-active  rtmp-forward.service
systemctl is-enabled rtmp-forward.service
systemctl is-active  rtmp-conn-guard.timer
systemctl is-enabled rtmp-conn-guard.timer
