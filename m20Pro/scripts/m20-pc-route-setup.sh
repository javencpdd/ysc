#!/bin/bash
# m20-pc-route-setup.sh
# ----------------------------------------------------------------------------
# 在 M20 Pro 的 NOS / GOS 主机上，持久化「PC 直连」所需的静态路由：
#   192.168.0.0/24  via  10.21.31.103  (AOS 内网口)
# 配套前提：AOS(196) 已配置 masquerade + FORWARD 放行，并由 netfilter-persistent 固化。
# 做法：写入独立 systemd oneshot 单元 m20-pc-route.service，开机后幂等补路由
#       （ip route replace + 6 次重试等接口就绪），不改动 netplan / NetworkManager
#       配置，避免连接重激活掉线。
#
# 用法（需 root 或 sudo 权限；AOS/NOS/GOS 的 sudo 口令为半角单引号 '）：
#   交互式：  m20ssh nos                    # 进入交互 shell（user）
#            sudo ./m20-pc-route-setup.sh
#   非交互：  口令经环境变量传入（不写本脚本）：
#            本地：  SUDO_PW='<' sudo -S bash m20-pc-route-setup.sh
#            跳板：  m20ssh nos "cat /path/m20-pc-route-setup.sh | SUDO_PW='<' sudo -S bash -s"
# ----------------------------------------------------------------------------
set -euo pipefail

# 兼容交互(plain sudo)与非交互(SUDO_PW 环境变量 -> sudo -S)
run_sudo() {
  if [ -n "${SUDO_PW:-}" ]; then
    printf '%s\n' "$SUDO_PW" | sudo -S "$@"
  else
    sudo "$@"
  fi
}

UNIT_PATH=/etc/systemd/system/m20-pc-route.service
TMP_UNIT=$(mktemp /tmp/m20pr.XXXXXX)

cat > "$TMP_UNIT" <<'UNITEOF'
[Unit]
Description=Persist static route 192.168.0.0/24 via AOS 10.21.31.103 (PC direct access)
After=NetworkManager.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for i in 1 2 3 4 5 6; do ip route replace 192.168.0.0/24 via 10.21.31.103 && exit 0; sleep 2; done; exit 1'

[Install]
WantedBy=multi-user.target
UNITEOF

run_sudo cp "$TMP_UNIT" "$UNIT_PATH"
run_sudo chmod 0644 "$UNIT_PATH"
run_sudo systemctl daemon-reload
run_sudo systemctl enable m20-pc-route.service
run_sudo ip route replace 192.168.0.0/24 via 10.21.31.103
rm -f "$TMP_UNIT"

echo "=== INSTALLED UNIT ==="
run_sudo cat "$UNIT_PATH"
echo "=== IS-ENABLED ==="
systemctl is-enabled m20-pc-route.service
echo "=== ROUTE GET ==="
ip route get 192.168.0.200
