#!/usr/bin/env bash
# ============================================================================
# wifi-uplink-check.sh —— M20 出口 WiFi 链路 vs 推流需求 适配性检测
#
# 背景：M20 唯一出口是 p2p0 WiFi（连 Tenda 5G）。relay 双路外推 + 本地观看端
#       （RTSP/HLS）全部共用这一条上行。2026-10-18 实测：该链路 RTT 抖动大时
#       （mdev 12.4ms）TCP 会进入重传退避（rto 54s），RTMP 播出端周期性卡顿，
#       而本地回环拉流完全正常——"本地不卡、服务器端卡"的根因。
#
# 本脚本把那次手工诊断固化为一条命令，回答两个问题：
#   1. 当前链路质量能否承载 外推+观看 的总需求？（OK / WARN / CRITICAL）
#   2. 各类终端各占多少上行、观看端有几路、代价多大？
#
# 用法：
#   ./wifi-uplink-check.sh        常规（结论 + 明细）
#   ./wifi-uplink-check.sh -v     详细（含 ping 逐包、每个连接）
#   ./wifi-uplink-check.sh -q     安静（只输出一行结论，适合 cron/看门狗）
#
# 无需 root：全部数据来自 /sys、ss、iw、ping。
# ⚠ 命令行/内容中不得出现厂商敏感字样（会被上游 pkill 误伤），本脚本已规避。
# ============================================================================
set -u

VERBOSE=0
QUIET=0
for a in "$@"; do
    case "$a" in
        -v) VERBOSE=1 ;;
        -q) QUIET=1 ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        *) echo "未知参数: $a（-v 详细 / -q 安静）" >&2; exit 2 ;;
    esac
done

# ---- 目标与默认参数 --------------------------------------------------------
RTMP_HOST_DEFAULT="172.31.68.227"
RTMP_PORT="1936"
RTSP_PORT="8554"
# 本地 HTTP 观看端口：HLS 8888 + WHEP 8889（控制台双通道，ADR-011）
HTTP_VIEW_PORTS="8888 8889"
SAMPLE_SECS=3                 # 上行吞吐采样时长
HLS_WINDOW_SECS=3             # HLS 短连接采样窗口
# 观看端看的是相机端源流码率（未转码），比 relay 外推贵一倍。
# 优先读**正在运行的相机进程**实际参数（配置文件里有多个分支，以进程为准），
# 读不到再退回配置文件，最后用经验默认值（800x600@30 ≈ 2.0 Mbps）
SRC_BPS=2000000
CAM_CFG="/opt/robot/scripts/board_resources/rtsp_service/push_video.sh"
v="$(ps -eo cmd 2>/dev/null | grep -F 'mpph264enc' | grep -v grep | grep -oE 'bps=[0-9]+' | head -1 | cut -d= -f2)"
if [ -z "${v:-}" ] && [ -r "$CAM_CFG" ]; then
    # 排除注释行（配置文件里有注释掉的示例参数，会污染取值）
    v="$(grep -vE '^\s*#' "$CAM_CFG" 2>/dev/null | grep -oE 'bps=[0-9]+' | tail -1 | cut -d= -f2)"
fi
[ -n "${v:-}" ] && SRC_BPS="$v"

# ---- 输出 helper -----------------------------------------------------------
if [ -t 1 ] && [ "$QUIET" = 0 ]; then
    C_OK=$'\e[32m'; C_WARN=$'\e[33m'; C_CRIT=$'\e[31m'; C_B=$'\e[1m'; C_0=$'\e[0m'
else
    C_OK=""; C_WARN=""; C_CRIT=""; C_B=""; C_0=""
fi
SCORE=0                      # 0=OK 1=WARN 2=CRITICAL
note()  { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }
warn()  { SCORE=$((SCORE>1?SCORE:1)); note "${C_WARN}[WARN]${C_0} $*"; }
crit()  { SCORE=2; note "${C_CRIT}[CRIT]${C_0} $*"; }
ok()    { note "${C_OK}[ OK ]${C_0} $*"; }
kv()    { [ "$QUIET" = 1 ] || printf '    %-22s %s\n' "$1" "$2"; }

# ---- A. 出口网卡 -----------------------------------------------------------
RTMP_HOST="${RTMP_HOST:-$RTMP_HOST_DEFAULT}"
IFACE="$(ip route get "$RTMP_HOST" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1)"
[ -z "$IFACE" ] && IFACE="$(ip route show default 2>/dev/null | awk '{print $5; exit}')"
if [ -z "$IFACE" ]; then
    crit "找不到出口网卡（路由表异常？）"
    [ "$QUIET" = 1 ] && echo "CRITICAL no-route"
    exit 2
fi

# ---- B. WiFi 物理层 --------------------------------------------------------
SIGNAL=""; BITRATE=""
if command -v iw >/dev/null 2>&1; then
    L="$(iw dev "$IFACE" link 2>/dev/null)"
    SIGNAL="$(printf '%s' "$L" | grep -oE 'signal: -?[0-9]+ dBm' | grep -oE '\-?[0-9]+')"
    BITRATE="$(printf '%s' "$L" | grep -oE 'tx bitrate: [0-9.]+' | grep -oE '[0-9.]+')"
fi
# -60dBm 是本次卡顿实测值；-50 以上为良
if [ -n "$SIGNAL" ]; then
    if   [ "$SIGNAL" -ge -50 ]; then ok   "信号 ${SIGNAL} dBm（良）"
    elif [ "$SIGNAL" -ge -65 ]; then warn "信号 ${SIGNAL} dBm（中等，改善空间大；卡顿时实测 -60）"
    else crit "信号 ${SIGNAL} dBm（弱，链路随时可能损伤）"; fi
fi

# ---- C. RTT 抖动（链路质量核心指标）---------------------------------------
# 参考基线：同位置 PC（-28dBm）ping 同目标 mdev≈1-2ms；
#           卡顿中的 M20（-60dBm）mdev=12.4ms。
PING_OUT="$(ping -i 0.3 -c 15 "$RTMP_HOST" 2>/dev/null)"
MDEV="$(printf '%s' "$PING_OUT" | sed -n 's#.*= \([0-9.]*\)/\([0-9.]*\)/\([0-9.]*\)/\([0-9.]*\) ms.*#\4#p' | tail -1)"
LOSS="$(printf '%s' "$PING_OUT" | sed -n 's#.*, \([0-9.]*\)% packet loss.*#\1#p' | tail -1)"
[ -z "$LOSS" ] && LOSS="?"
if [ -z "$MDEV" ]; then
    warn "ping $RTMP_HOST 无响应（服务器不可达或 ICMP 被禁）——链路质量无法评估"
else
    mdev_int="${MDEV%%.*}"
    if   [ "${mdev_int:-99}" -lt 5 ];  then ok   "RTT 抖动 mdev=${MDEV}ms（健康，对照 PC≈1-2ms）"
    elif [ "${mdev_int:-99}" -le 15 ]; then warn "RTT 抖动 mdev=${MDEV}ms（偏大；卡顿时实测 12.4ms）"
    else crit "RTT 抖动 mdev=${MDEV}ms（链路正在损伤，播放端会周期性卡）"; fi
    # 丢包率可能是小数（如 13.3333），取整数部分比较
    loss_int="${LOSS%%.*}"
    if [ "$loss_int" != "?" ] && [ "${loss_int:-0}" -gt 0 ]; then
        if [ "${loss_int:-0}" -ge 5 ]; then
            crit "ping 丢包 ${LOSS}%（≥5%：链路正在损伤，TCP 会反复重传退避）"
        else
            warn "ping 丢包 ${LOSS}%（轻微，持续观察）"
        fi
    fi
fi
[ "$VERBOSE" = 1 ] && [ -n "$PING_OUT" ] && printf '%s\n' "$PING_OUT" | sed 's/^/    /'

# ---- D. TCP 传输层健康（relay 外推连接）-----------------------------------
# 注意：本机 ss -tni 为**单行格式**（socket 头与 cwnd/rto 在同一行），
# 但有些版本是两行格式——先按单行匹配，匹配行缺 cwnd 时再走两行配对。
ESTAB_N=0; RTO_MAX=0; RETRANS_TOTAL=0; CWND_MIN=999999
SOCK_LINES="$(ss -tni 2>/dev/null | grep ESTAB | grep -F ":$RTMP_PORT" || true)"
if [ -n "$SOCK_LINES" ] && ! printf '%s\n' "$SOCK_LINES" | grep -q cwnd; then
    # 两行格式：头行(ESTAB+端口) → 下一行(cwnd/rto)
    SOCK_LINES="$(ss -tni 2>/dev/null | awk -v p=":$RTMP_PORT" '/ESTAB/ && index($0,p){want=1;next} want && /cwnd/{print;want=0}')"
fi
while read -r line; do
    [ -z "$line" ] && continue
    ESTAB_N=$((ESTAB_N+1))
    r="$(printf '%s' "$line" | grep -oE 'rto:[0-9.]+' | cut -d: -f2)"
    t="$(printf '%s' "$line" | grep -oE 'retrans:[0-9]+/[0-9]+' | cut -d: -f2 | cut -d/ -f1)"
    w="$(printf '%s' "$line" | grep -oE 'cwnd:[0-9]+' | cut -d: -f2)"
    [ -n "${r:-}" ] && awk -v a="$r" -v b="$RTO_MAX" 'BEGIN{exit !(a+0>b+0)}' && RTO_MAX="$r"
    [ -n "${t:-}" ] && RETRANS_TOTAL=$((RETRANS_TOTAL+t))
    [ -n "${w:-}" ] && [ "$w" -lt "$CWND_MIN" ] && CWND_MIN="$w"
done <<<"$SOCK_LINES"

if [ "$ESTAB_N" = 0 ]; then
    warn "无到 $RTMP_HOST:$RTMP_PORT 的 ESTAB 连接——relay 未运行或已断"
else
    rto_bad="$(awk -v a="$RTO_MAX" 'BEGIN{print (a+0>1)?1:0}')"
    if [ "$rto_bad" = 1 ]; then
        crit "外推连接 TCP 重传退避中：rto=${RTO_MAX}s（卡顿时实测 54s；>1s 即链路已损伤）"
    elif [ "$RETRANS_TOTAL" -gt 0 ]; then
        warn "外推连接有重传累计 retrans=${RETRANS_TOTAL}（关注是否继续增长）"
    elif [ "$CWND_MIN" -lt 30 ]; then
        warn "外推连接 cwnd 仅 ${CWND_MIN}（健康时 78-216；被压低通常是链路丢包的征兆）"
    else
        ok "外推连接 TCP 健康（$ESTAB_N 路，cwnd≥${CWND_MIN}，无重传）"
    fi
    kv "外推 ESTAB / cwnd最小" "$ESTAB_N / $CWND_MIN"
fi

# ---- E. 上行吞吐（3s 采样）-------------------------------------------------
tx1="$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)"
sleep "$SAMPLE_SECS"
tx2="$(cat /sys/class/net/$IFACE/statistics/tx_bytes 2>/dev/null || echo 0)"
TX_KBPS=$(( (tx2-tx1)/1024/SAMPLE_SECS ))

# ---- F. 观看端清点 ---------------------------------------------------------
# RTSP：ESTAB 长连接，快照即可（对端非回环即外部观看端；
#       relay 自身经 127.0.0.1 拉流，必须排除，不能算成观看端）
RTSP_VIEWERS="$(ss -tn state established 2>/dev/null | awk -v p=":$RTSP_PORT" 'index($4,p){print $5}' | grep -v '^127.0.0.1' | sort -u)"
RTSP_N="$(printf '%s' "$RTSP_VIEWERS" | grep -c . || true)"
# 本地 HTTP 观看（HLS 8888 + WHEP 8889，控制台双通道）：短连接，
# 3s 窗口多次采样取并集；只采 established（TIME-WAIT 会把刚离开的终端算成活跃）。
HTTP_VIEWERS=""
end=$((SECONDS+HLS_WINDOW_SECS))
while [ "$SECONDS" -lt "$end" ]; do
    for hp in $HTTP_VIEW_PORTS; do
        HTTP_VIEWERS+="$(ss -tn state established 2>/dev/null | awk -v p=":$hp" 'index($4,p){print $5}' | grep -v '^127.0.0.1' | sort -u)"
        HTTP_VIEWERS+=$'\n'
    done
    sleep 0.25
done
HTTP_VIEWERS="$(printf '%s' "$HTTP_VIEWERS" | grep -v '^$' | sort -u)"
HTTP_N="$(printf '%s' "$HTTP_VIEWERS" | grep -c . || true)"

# ---- G. 需求核算与结论 -----------------------------------------------------
# relay 外推需求：用实测反推（tx 总量 ≈ 外推 + 观看 + 其他），取保守值：
# 需求(外推) ≈ 实测 tx - 观看端贡献；这里简化为 实测 tx 即总需求，
# 观看端贡献单列，避免双重计入口径混乱。
VIEWER_BPS=$(( (RTSP_N+HTTP_N) * SRC_BPS / 1000000 ))
TOTAL_MBPS="$(awk -v k="$TX_KBPS" 'BEGIN{printf "%.2f", k*8/1024}')"
RELAY_MBPS="$(awk -v t="$TOTAL_MBPS" -v v="$VIEWER_BPS" 'BEGIN{s=t-v; if(s<0)s=0; printf "%.2f", s}')"

note ""
if [ "$QUIET" = 0 ]; then
    printf '%s=== 出口 %s（WiFi）===%s\n' "$C_B" "$IFACE" "$C_0"
    kv "信号 / PHY 速率" "${SIGNAL:-?} dBm / ${BITRATE:-?} Mbps"
    kv "RTT mdev / 丢包" "${MDEV:-?} ms / ${LOSS:-?}%"
    kv "上行实测(3s)" "${TX_KBPS} KB/s ≈ ${TOTAL_MBPS} Mbps"
    kv "relay 外推 ESTAB" "$ESTAB_N 路"
    kv "本地观看端" "RTSP ${RTSP_N} 路 + HLS/WHEP ${HTTP_N} 路"
    kv "观看端带宽代价" "≈ ${VIEWER_BPS} Mbps（看的是源流 ${SRC_BPS}/1000000 Mbps/路，比外推贵一倍）"
    [ "$VERBOSE" = 1 ] && [ -n "$RTSP_VIEWERS" ] && printf '%s\n' "$RTSP_VIEWERS" | sed 's/^/      RTSP     /'
    [ "$VERBOSE" = 1 ] && [ -n "$HTTP_VIEWERS" ] && printf '%s\n' "$HTTP_VIEWERS" | sed 's/^/      HLS/WHEP /'
    printf '%s=== 判定 ===%s\n' "$C_B" "$C_0"
fi

# 判定汇总：质量指标（mdev/rto/retrans）优先于需求量级
if [ "$SCORE" = 2 ]; then
    note "${C_CRIT}${C_B}结论: CRITICAL —— 链路正在损伤，外推质量已受影响${C_0}"
    note "  建议（按见效速度）："
    note "   1. 关掉不必要的本地观看端（每路 ≈ ${SRC_BPS}/1000000 Mbps，比外推贵一倍）"
    note "   2. 降 relay 外推码率：config.env RELAY_BPS/RELAY_FPS → m20-video-ctl restart relay"
    note "   3. 改善 M20 的 WiFi 信号/位置（当前 ${SIGNAL:-?} dBm）或有线上联"
elif [ "$SCORE" = 1 ]; then
    note "${C_WARN}${C_B}结论: WARN —— 有隐患，暂未损伤但余量不足${C_0}"
    note "  建议：减少观看端、盯紧本脚本输出；若接 WARN 后仍卡，按 CRITICAL 三条处理"
else
    note "${C_OK}${C_B}结论: OK —— 链路健康、余量充足（外推 ${RELAY_MBPS} + 观看 ${VIEWER_BPS} ≈ ${TOTAL_MBPS} Mbps）${C_0}"
fi

[ "$QUIET" = 1 ] && case "$SCORE" in
    2) echo "CRITICAL iface=$IFACE mdev=${MDEV:-?} tx=${TX_KBPS}KB/s viewers=$((RTSP_N+HTTP_N))" ;;
    1) echo "WARN iface=$IFACE mdev=${MDEV:-?} tx=${TX_KBPS}KB/s viewers=$((RTSP_N+HTTP_N))" ;;
    0) echo "OK iface=$IFACE mdev=${MDEV:-?} tx=${TX_KBPS}KB/s viewers=$((RTSP_N+HTTP_N))" ;;
esac
exit "$SCORE"
