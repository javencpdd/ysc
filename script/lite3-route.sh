#!/usr/bin/env bash
# lite3-route.sh —— 让主机 A 能 SSH 到 Lite3(192.168.1.103)
#
# 拓扑：A 用 wls6 上校园网，enp7s0(10.42.0.1) 共享给路由器 WAN(10.42.0.116)，
#       路由器 LAN 是 192.168.1.0/24，Lite3 直连在上面(eth0 = 192.168.1.103)。
#       默认 A 没有到 LAN 网段的路由，包会走 default 从 wls6 出去被丢。
#
# 用法：
#   sudo bash lite3-route.sh            # 临时加路由（重启失效）
#   sudo bash lite3-route.sh persist    # 额外写入 NetworkManager，永久生效
#
set -u

IFACE="enp7s0"
VIA="10.42.0.116"
NET="192.168.1.0/24"
TARGET="192.168.1.103"
SSH_USER="ysc"

say() { printf '\n=== %s ===\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "请用 sudo 运行：sudo bash $0"
    exit 1
fi

say "1. 加静态路由 $NET via $VIA dev $IFACE"
if ip route show "$NET" | grep -q "$NET"; then
    echo "路由已存在，跳过"
else
    ip route add "$NET" via "$VIA" dev "$IFACE" && echo "已添加" || { echo "添加失败"; exit 1; }
fi

say "2. 确认路由走向"
ip route get "$TARGET"

say "3. 连通性测试"
if ping -c 3 -W 2 "$TARGET" >/dev/null 2>&1; then
    echo "ping 通 —— 路由器允许 WAN→LAN，可以直接 SSH"
else
    echo "ping 不通"
    echo "可能原因：路由器丢弃了 WAN→LAN 新建连接（家用路由默认行为）"
    echo "解决办法二选一："
    echo "  a) 路由器后台关掉 SPI 防火墙 / WAN 入站过滤"
    echo "  b) 路由器后台加端口转发：外部 2222 -> $TARGET:22 (TCP)"
    echo "     连法变成： ssh -p 2222 $SSH_USER@$VIA"
fi

say "4. SSH 端口探测"
if command -v nc >/dev/null 2>&1; then
    if nc -z -w 3 "$TARGET" 22 2>/dev/null; then
        echo "22 端口开放，现在可以：ssh $SSH_USER@$TARGET"
    else
        echo "22 端口不通（若上面 ping 已通，检查 Lite3 上的 sshd 是否在跑）"
    fi
else
    echo "未装 nc，跳过"
fi

if [ "${1:-}" = "persist" ]; then
    say "5. 写入 NetworkManager 永久路由"
    CONN="$(nmcli -g NAME,DEVICE connection show --active 2>/dev/null | awk -F: -v d="$IFACE" '$2==d {print $1; exit}')"
    if [ -z "$CONN" ]; then
        echo "没找到 $IFACE 对应的连接名，请手动执行："
        echo "  nmcli connection show"
        echo "  sudo nmcli connection modify \"<连接名>\" +ipv4.routes \"$NET $VIA\""
    else
        echo "连接名：$CONN"
        nmcli connection modify "$CONN" +ipv4.routes "$NET $VIA" && echo "已写入，重启后依然有效"
    fi
else
    say "提示"
    echo "这条路由重启会失效。要永久生效请重跑：sudo bash $0 persist"
fi
