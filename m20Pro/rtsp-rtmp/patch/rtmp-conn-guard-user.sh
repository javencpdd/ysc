#!/usr/bin/env bash
# rtmp-conn-guard-user: 用户级版本，看护 Lite3(120) 的用户级推流服务 rtmp-forward.service
#
# 背景：120 的外推由用户级单元 ~/.config/systemd/user/rtmp-forward.service 托管
#       （ExecStart=/home/ysc/rtsp_stream/rtmp_forward.sh，enabled + Linger=yes 开机自启）。
#       系统级 /usr/local/sbin/rtmp-conn-guard.sh 的 DEFAULT_SVC 只会选中系统级服务，
#       在 120 上误选 rtsp_stream.service（它不产生 :1936 连接），因此对外推无效、
#       且僵尸时会重启错的服务。本脚本即为用户级正确版本。
#
# 检测"僵尸"连接（TCP 卡死：进程存活、不退出、不推数据），systemctl --user restart 自愈。
#
# 判定（满足任一且连续 BAD_LIMIT 次采样）→ 重启：
#   - cwnd <= CWND_ZOMBIE 且 Send-Q > SENDQ_MIN（窗口塌缩 + 数据积压）
#   - retrans >= RETRANS_MAX（持续重传失败）
#   - 服务 active 但已无任何到上游的 ESTAB 连接（链路彻底丢失）
# 重启后进入 COOLDOWN 冷却，避免抖动期空转。
set -u

SERVICE="${1:-rtmp-forward.service}"
UPSTREAM="${2:-172.31.68.227:1936}"
LOG_FILE="${3:-/home/ysc/rtsp_stream/logs/rtmp-conn-guard-user.log}"
STATE_DIR="${STATE_DIR:-/home/ysc/.local/state/rtmp-conn-guard-user}"

CWND_ZOMBIE="${CWND_ZOMBIE:-3}"     # cwnd <= 此值（且 Send-Q 大）视为可疑
SENDQ_MIN="${SENDQ_MIN:-65536}"     # Send-Q 超过此值(64KB)且 cwnd 低 = 积压
RETRANS_MAX="${RETRANS_MAX:-20}"    # retrans 累计超过此值 = 失败
BAD_LIMIT="${BAD_LIMIT:-3}"         # 连续可疑采样次数（×定时器间隔=判定时长）
COOLDOWN="${COOLDOWN:-300}"         # 重启后冷却秒数

# 用户级 systemd 需要 XDG_RUNTIME_DIR；Linger=yes 保证开机即存在该会话
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

mkdir -p "$STATE_DIR" "$(dirname "$LOG_FILE")"
SF="$STATE_DIR/$(echo "$SERVICE" | tr '.' '_').badcount"
CF="$STATE_DIR/$(echo "$SERVICE" | tr '.' '_').cooldown"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [conn-guard-user] $*" >> "$LOG_FILE"; }

# 冷却期内不动作
if [ -f "$CF" ]; then
  last=$(cat "$CF" 2>/dev/null || echo 0); [ -z "$last" ] && last=0
  now=$(date +%s)
  if [ $((now - last)) -lt "$COOLDOWN" ]; then exit 0; fi
fi

# 服务没在跑：交给 systemd(Restart=always) 处理，看门狗不抢
if ! systemctl --user is-active "$SERVICE" >/dev/null 2>&1; then
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
    log "ZOMBIE detected for $SERVICE (bad=$cnt); systemctl --user restart"
    systemctl --user restart "$SERVICE" >> "$LOG_FILE" 2>&1
    date +%s > "$CF"; echo 0 > "$SF"
  else
    log "suspicious $SERVICE upstream (bad $cnt/$BAD_LIMIT)"
  fi
else
  echo 0 > "$SF"
fi
