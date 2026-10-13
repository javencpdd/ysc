#!/bin/bash
# ============================================================
# 120主机 无线状态巡检 & 断连自动抓证 看门狗
# 用途：每分钟采样一次 AP(p2p0) 与 STA(wlan0) 状态；
#       一旦检测到热点消失或上联 WiFi 断连，立即抓取前后证据存档。
# 配套：systemd timer（见排查文档 4.6.2）
#
# ---------- 日志体积控制策略（三重保险）----------
#   1) 主日志 wifi_watch.log 达 10MB 触发轮转并 gzip
#   2) 归档 .gz 超过 RETENTION_DAYS 天自动删除
#   3) 整个日志目录超过 MAX_DIR_MB 时，从最旧的 incident 开始删
#   4) 持续故障期间抓证节流：每 INCIDENT_COOLDOWN 秒才做一次完整抓证，
#      其余只往现有档案追加一行（避免每分钟生成一个大文件）
# ------------------------------------------------------------

LOGDIR=/var/log/wifi_watchdog
mkdir -p "$LOGDIR"
LOG="$LOGDIR/wifi_watch.log"
TS=$(date '+%F %T')
NOW=$(date +%s)

# ---------- 可调参数 ----------
RETENTION_DAYS=7          # 轮转归档(.gz)保留天数
INCIDENT_COOLDOWN=300     # 同一故障的完整抓证间隔（秒），默认 5 分钟
MAX_DIR_MB=50             # 日志目录体积上限（MB），超限删最旧 incident
LOG_ROTATE_BYTES=10485760 # 主日志轮转阈值（字节），默认 10MB

AP_IF=p2p0
STA_IF=wlan0
AP_CON=myap50G
STA_CON=Tenda_FCFA20

# ---------- 状态采集 ----------
ap_state=$(iw dev "$AP_IF" info 2>/dev/null | awk '/type AP/{print "AP_UP"}')
ap_chan=$(iw dev "$AP_IF" info 2>/dev/null | grep -oE 'channel [0-9]+' | head -1)
sta_link=$(iw dev "$STA_IF" link 2>/dev/null | grep -c 'Connected to')
ap_sta_num=$(iw dev "$AP_IF" station dump 2>/dev/null | grep -c '^Station')

echo "$TS ap=${ap_state:-AP_DOWN} ${ap_chan} ap_clients=$ap_sta_num sta_connected=$sta_link \
mem_avail=$(awk '/MemAvailable/{printf "%dMiB",$2/1024}' /proc/meminfo) \
load=$(cut -d' ' -f1 /proc/loadavg) \
temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)" >> "$LOG"

# ---------- 异常判定：AP 消失 或 STA 断连 ----------
if [ -z "$ap_state" ] || [ "$sta_link" -eq 0 ]; then

    # 抓证节流：判断距最近一次完整抓证是否已超过冷却时间
    LAST_INC=$(ls -1t "$LOGDIR"/incident_*.log 2>/dev/null | head -1)
    if [ -n "$LAST_INC" ] && [ -f "$LAST_INC" ]; then
        LAST_AGE=$(( NOW - $(stat -c %Y "$LAST_INC") ))
    else
        LAST_AGE=$INCIDENT_COOLDOWN
    fi

    if [ "$LAST_AGE" -ge "$INCIDENT_COOLDOWN" ]; then
        # ---- 完整抓证：新建事件档案 ----
        INC="$LOGDIR/incident_$(date '+%Y%m%d_%H%M%S').log"
        {
            echo "===== 无线异常事件 $TS ====="
            echo "ap_state=${ap_state:-AP_DOWN} sta_connected=$sta_link"
            echo "--- iw dev ---";        iw dev
            echo "--- iw link ---";       iw dev "$STA_IF" link
            echo "--- nmcli dev ---";     nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev status
            echo "--- 近10分钟内核日志 ---"
            journalctl -k --since "10 min ago" --no-pager 2>/dev/null \
                | grep -iE "RTW|HALMAC|8822ce|wlan0|p2p0|pcie|AER" | tail -40
            echo "--- 近10分钟系统日志 ---"
            journalctl --since "10 min ago" --no-pager 2>/dev/null \
                | grep -iE "wpa_supplicant|NetworkManager|dnsmasq" | tail -40
            echo "--- 资源 ---";           free -h; uptime
            echo "--- dnsmasq ---";        ps aux | grep -E "[d]nsmasq"
            echo "--- 温度 ---"
            for f in /sys/class/thermal/thermal_zone*/temp; do echo "$f $(cat $f)"; done
        } >> "$INC" 2>&1
        logger -t wifi_watchdog "WIFI_INCIDENT captured: $INC"
        TARGET="$INC"
    else
        # ---- 节流中：只往现有档案追加状态行，不新建大文件 ----
        TARGET="$LAST_INC"
        echo "$TS [持续异常 ${LAST_AGE}s] ap=${ap_state:-AP_DOWN} ${ap_chan} \
sta_connected=$sta_link (抓证节流中，每 ${INCIDENT_COOLDOWN}s 一次)" >> "$TARGET"
    fi

    # ---------- 软件层自愈尝试 ----------
    nmcli con up "$AP_CON"  >/dev/null 2>&1
    nmcli con up "$STA_CON" >/dev/null 2>&1
    sleep 15

    if [ -z "$(iw dev "$AP_IF" info 2>/dev/null | grep 'type AP')" ] \
       || [ "$(iw dev "$STA_IF" link 2>/dev/null | grep -c 'Connected to')" -eq 0 ]; then
        echo "$TS SOFT_RECOVERY_FAILED 软件层自愈无效，需人工重启" >> "$TARGET"
        # 仅在完整抓证周期写 syslog，避免持续故障时刷屏
        [ "$LAST_AGE" -ge "$INCIDENT_COOLDOWN" ] && \
            logger -t wifi_watchdog "SOFT_RECOVERY_FAILED: 软件层自愈无效，需人工重启"
    else
        echo "$TS SOFT_RECOVERY_OK" >> "$TARGET"
        logger -t wifi_watchdog "SOFT_RECOVERY_OK"
    fi
fi

# ---------- 体积保护 1：主日志按大小轮转 ----------
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG" 2>/dev/null)" -gt "$LOG_ROTATE_BYTES" ]; then
    STAMP=$(date '+%Y%m%d_%H%M%S')
    mv "$LOG" "$LOG.$STAMP"
    gzip -f "$LOG.$STAMP" 2>/dev/null
fi

# ---------- 体积保护 2：清理过期归档 ----------
find "$LOGDIR" -type f -name '*.gz' -mtime +"$RETENTION_DAYS" -delete 2>/dev/null

# ---------- 体积保护 3：目录总大小上限，超限删最旧的 incident ----------
DIR_KB=$(du -sk "$LOGDIR" 2>/dev/null | awk '{print $1}')
MAX_KB=$(( MAX_DIR_MB * 1024 ))
if [ "${DIR_KB:-0}" -gt "$MAX_KB" ]; then
    for f in $(ls -1tr "$LOGDIR"/incident_* 2>/dev/null); do
        [ -f "$f" ] || continue
        rm -f "$f"
        DIR_KB=$(du -sk "$LOGDIR" 2>/dev/null | awk '{print $1}')
        [ "${DIR_KB:-0}" -le "$MAX_KB" ] && break
    done
    logger -t wifi_watchdog "LOGDIR 超过 ${MAX_DIR_MB}MB，已清理最旧 incident 归档"
fi
