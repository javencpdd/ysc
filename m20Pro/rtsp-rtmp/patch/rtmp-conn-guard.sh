#!/usr/bin/env bash
# rtmp-conn-guard: 检测 RTMP 上行链路"僵尸"连接（中途 TCP 卡死），并重启中继服务实现自愈。
#
# 背景：中继脚本在"连接前探测失败"时会以 exit 3 退出，靠 drop-in(RestartSec=30) 自愈；
#       但"连接中途 TCP 卡死"（cwnd 塌缩到 1、Send-Q 冻结、retrans 累加）时进程仍存活，
#       不触发 exit 3，也不会自愈。本看门狗周期性读 `ss -tni`，发现僵尸即强杀重启。
#
# 判定（满足任一且连续 BAD_LIMIT 次采样）→ 重启：
#   - cwnd <= CWND_ZOMBIE 且 Send-Q > SENDQ_MIN（窗口塌缩 + 数据积压）
#   - retrans >= RETRANS_MAX（持续重传失败）
#   - 服务 active 但已无任何到上游的 ESTAB 连接（链路彻底丢失）
# 重启后进入 COOLDOWN 冷却，避免抖动期空转。
set -u

# 自动识别本机的中继服务（优先 m20video，其次 rtsp_stream）
DEFAULT_SVC=""
for c in m20video.service rtsp_stream.service; do
  if systemctl is-enabled "$c" >/dev/null 2>&1; then DEFAULT_SVC="$c"; break; fi
done

SERVICE="${1:-$DEFAULT_SVC}"
UPSTREAM="${2:-172.31.68.227:1936}"
LOG_FILE="${3:-/var/log/rtmp-conn-guard.log}"
STATE_DIR="${STATE_DIR:-/var/lib/rtmp-conn-guard}"

CWND_ZOMBIE="${CWND_ZOMBIE:-3}"     # cwnd <= 此值（且 Send-Q 大）视为可疑
SENDQ_MIN="${SENDQ_MIN:-65536}"     # Send-Q 超过此值(64KB)且 cwnd 低 = 积压
RETRANS_MAX="${RETRANS_MAX:-20}"    # retrans 累计超过此值 = 失败
BAD_LIMIT="${BAD_LIMIT:-3}"         # 连续可疑采样次数（×定时器间隔=判定时长）
COOLDOWN="${COOLDOWN:-300}"         # 重启后冷却秒数

[ -n "$SERVICE" ] || { echo "no relay service found on this host"; exit 0; }
mkdir -p "$STATE_DIR"
SF="$STATE_DIR/$(echo "$SERVICE" | tr '.' '_').badcount"
CF="$STATE_DIR/$(echo "$SERVICE" | tr '.' '_').cooldown"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [conn-guard] $*" >> "$LOG_FILE"; }

# 冷却期内不动作
if [ -f "$CF" ]; then
  last=$(cat "$CF" 2>/dev/null || echo 0); [ -z "$last" ] && last=0
  now=$(date +%s)
  if [ $((now - last)) -lt "$COOLDOWN" ]; then exit 0; fi
fi

# 服务没在跑：交给 systemd/drop-in 处理，看门狗不抢
if ! systemctl is-active "$SERVICE" >/dev/null 2>&1; then
  echo 0 > "$SF"; exit 0
fi

# 收集到上游的 ESTAB 记录（把缩进的续行合并进同一记录，兼容单行/多行 ss 输出）
records=$(ss -tni 2>/dev/null | awk '
  /ESTAB/ && /:1936/ { if (rec != "") print rec; rec=$0; next }
  /^[[:space:]]+/ && rec != "" { rec = rec " " $0; next }
  { if (rec != "") { print rec; rec="" } }
  END { if (rec != "") print rec }
')

bad=0
if [ -z "$records" ]; then
  bad=1   # active 但无任何到上游的 ESTAB：链路彻底丢失
else
  while IFS= read -r r; do
    [ -z "$r" ] && continue
    set -- $r                       # 位置字段：$1 状态 $2 Recv-Q $3 Send-Q ...
    sendq="${3:-0}"
    cwnd=$(echo "$r" | grep -oE 'cwnd:[0-9]+' | head -1 | cut -d: -f2)
    retrans=$(echo "$r" | grep -oE 'retrans:[0-9]+' | head -1 | cut -d: -f2)
    cwnd="${cwnd:-0}"; retrans="${retrans:-0}"
    if [ "$cwnd" -le "$CWND_ZOMBIE" ] && [ "$sendq" -gt "$SENDQ_MIN" ]; then bad=1; fi
    if [ "$retrans" -ge "$RETRANS_MAX" ]; then bad=1; fi
  done <<< "$records"
fi

if [ "$bad" -eq 1 ]; then
  cnt=$(cat "$SF" 2>/dev/null || echo 0); cnt=$((cnt + 1)); echo "$cnt" > "$SF"
  if [ "$cnt" -ge "$BAD_LIMIT" ]; then
    log "ZOMBIE detected for $SERVICE (bad=$cnt); systemctl restart"
    systemctl restart "$SERVICE" >> "$LOG_FILE" 2>&1
    date +%s > "$CF"; echo 0 > "$SF"
  else
    log "suspicious $SERVICE upstream (bad $cnt/$BAD_LIMIT)"
  fi
else
  echo 0 > "$SF"
fi
