#!/bin/bash
# ============================================================
# 120主机 无线故障一键取证脚本
# 用法：故障复现后、重启之前执行 sudo bash wifi_diag_collect.sh
#       产物目录 /home/ysc/wifi_diag_<时间戳>，打包带回分析
# 注意：务必在重启前执行，否则 journal 证据会丢失
# ============================================================

OUT=/home/ysc/wifi_diag_$(date '+%Y%m%d_%H%M%S')
mkdir -p "$OUT"

{
  echo "===== 采集时间 $(date '+%F %T') ====="

  echo "--- 基础信息 ---"
  uname -a; uptime; free -h

  echo "--- 重启历史 ---"
  last -x reboot | head -20

  echo "--- iw dev ---"
  iw dev

  echo "--- wlan0 link ---"
  iw dev wlan0 link

  echo "--- p2p0 info ---"
  iw dev p2p0 info

  echo "--- power save ---"
  iw wlan0 get power_save
  iw p2p0 get power_save

  echo "--- nmcli 连接 ---"
  nmcli -t -f NAME,TYPE,DEVICE con show

  echo "--- nmcli 设备 ---"
  nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev status

  echo "--- dnsmasq 进程 ---"
  ps aux | grep -E "[d]nsmasq"

  echo "--- AP 已接入客户端 ---"
  iw dev p2p0 station dump

  echo "--- 温度 ---"
  for f in /sys/class/thermal/thermal_zone*/temp; do echo "$f $(cat $f)"; done

  echo "--- 驱动模块 ---"
  lsmod | grep -iE "8822ce|rtl88"
  modinfo 8822ce 2>/dev/null | grep -E "^version|^filename"

  echo "--- 路由 ---"
  ip route

  echo "--- 磁盘 ---"
  df -h
} > "$OUT/snapshot.txt" 2>&1

# 内核与系统日志（近 2 小时）
dmesg > "$OUT/dmesg.txt" 2>&1
journalctl -k --since "2 hours ago" --no-pager > "$OUT/journal_kern.txt" 2>&1
journalctl    --since "2 hours ago" --no-pager > "$OUT/journal_all.txt" 2>&1

# 跨重启的关键日志切片（rsyslog 留存）
zgrep -ahE "RTW|HALMAC|8822ce|wlan0|p2p0" /var/log/kern.log*  > "$OUT/kern_wifi.txt"  2>&1
zgrep -ahE "wpa_supplicant|NetworkManager|dnsmasq" /var/log/syslog* > "$OUT/syslog_net.txt" 2>&1
zgrep -ahE "CHANNEL-SWITCH|CTRL-EVENT-DISCONNECTED|OnDeAuth|AP-STA-DISCONNECTED" \
    /var/log/syslog* /var/log/kern.log* > "$OUT/disconnect_events.txt" 2>&1

# 看门狗记录（若已部署）
if [ -d /var/log/wifi_watchdog ]; then
    cp -r /var/log/wifi_watchdog "$OUT/wifi_watchdog" 2>/dev/null
fi

echo "采集完成：$OUT"
ls -lh "$OUT"
echo
echo "打包命令： tar czf ${OUT##*/}.tar.gz -C /home/ysc ${OUT##*/}"
