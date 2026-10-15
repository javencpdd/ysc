#!/usr/bin/env bash
#
# enable-internet-via-aos.sh
# 让本机(NOS/GOS)经由 AOS(10.21.31.103) 出公网, 并把配置固化到 netplan(重启仍生效).
#
# 背景 / 原理:
#   M20 Pro 三主机里只有 AOS 有公网出口 —— AOS 的 p2p0(192.168.0.196) 连腾达路由器,
#   且 AOS 上已配置好:
#     iptables -t nat -A POSTROUTING -s 10.21.31.0/24 -o p2p0 -j MASQUERADE
#     iptables FORWARD  eth2<->p2p0 放行
#   所以把 NOS/GOS 的默认网关指向 AOS(10.21.31.103), 即可借 AOS 的 NAT 上公网.
#
#   NOS 出厂 netplan 把 eth1 网关写死成内网总关 10.21.31.99(该网关实际不可达,
#   且 DNS 配的 8.8.8.8 经死网关也不可达) -> 无公网 / 域名解析失败.
#   GOS 默认网关早已指向 AOS, 本脚本在其上幂等跳过.
#
# 用法:
#   sudo ./enable-internet-via-aos.sh          检测并固化(改 netplan + apply)
#   ./enable-internet-via-aos.sh --check       仅报告将要做的改动, 不改动
#   sudo ./enable-internet-via-aos.sh --rollback  用最新备份还原 netplan 并 apply
#
set -euo pipefail

AOS_GW="${AOS_GW:-10.21.31.103}"   # AOS 内网地址 = 本机出公网下一跳
DNS1="${DNS1:-192.168.0.1}"        # 腾达 DNS(AOS 同款, 可达)
NETPLAN_YAML="/etc/netplan/config.yaml"
BAK="/etc/netplan/config.yaml.bak-$(date +%Y%m%d%H%M%S)"

# --check 只读, 无需 root; 其余(apply/rollback)需要 root, 非 root 时自动 sudo 重新执行
if [ "${1:-}" != "--check" ] && [ "$(id -u)" -ne 0 ]; then
  echo "[*] 需要 root, 以 sudo 重新执行..." >&2
  exec sudo "$0" "$@"
fi

DEF_DEV="$(ip route show default 2>/dev/null | awk '/dev/ {print $5; exit}')"
CUR_GW="$(ip route show default 2>/dev/null | awk '/via/ {print $3; exit}')"

echo "== 本机: $(hostname) =="
echo "默认路由接口 : ${DEF_DEV:-<无>}"
echo "当前默认网关 : ${CUR_GW:-<无>}"
echo "目标网关     : $AOS_GW (AOS)"
echo "目标 DNS     : $DNS1"

if [ -z "$DEF_DEV" ]; then
  echo "[!] 未找到默认路由接口, 退出." >&2
  exit 1
fi

case "${1:-}" in
  --rollback)
    LATEST="$(ls -1t /etc/netplan/config.yaml.bak-* 2>/dev/null | head -1)"
    if [ -z "$LATEST" ]; then echo "[!] 没有找到时间戳备份." >&2; exit 1; fi
    echo "[*] 还原: $LATEST -> $NETPLAN_YAML"
    cp "$LATEST" "$NETPLAN_YAML"
    netplan apply
    echo "[*] 已还原并 apply. 当前默认路由:"; ip route show default
    exit 0
    ;;
  --check)
    if [ "$CUR_GW" = "$AOS_GW" ]; then
      echo "[check] 默认网关已是 $AOS_GW, 无需改动(幂等)."
    else
      echo "[check] 将改 netplan: ethernets.$DEF_DEV.gateway4=$AOS_GW ; nameservers.addresses=[$DNS1]"
    fi
    exit 0
    ;;
esac

if [ "$CUR_GW" = "$AOS_GW" ]; then
  echo "[*] 默认网关已是 $AOS_GW, 出口已正常, 无需改 netplan."
  echo "[*] 顺手确认运行时 DNS:"
  resolvectl dns "$DEF_DEV" "$DNS1" 2>/dev/null || true
  echo "完成(无改动)."
  exit 0
fi

echo "[1/4] 备份 netplan: $BAK"
cp "$NETPLAN_YAML" "$BAK"

echo "[2/4] netplan set: ethernets.$DEF_DEV.gateway4=$AOS_GW"
netplan set "ethernets.$DEF_DEV.gateway4=$AOS_GW"

echo "[3/4] netplan set: ethernets.$DEF_DEV.nameservers.addresses=[$DNS1]"
netplan set "ethernets.$DEF_DEV.nameservers.addresses=[$DNS1]"

echo "[4/4] netplan apply"
netplan apply

echo "== 验证 =="
echo "默认路由:"; ip route show default
echo "DNS:"; resolvectl dns "$DEF_DEV" 2>/dev/null
echo "解析测试:"; ping -c1 -W3 bilibili.com 2>&1 | tail -3 || echo "(ping 失败, 见上方输出)"
echo "完成. 备份在 $BAK ; 如需回退: sudo $0 --rollback"
