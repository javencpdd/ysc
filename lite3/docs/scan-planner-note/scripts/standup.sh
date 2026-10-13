#!/usr/bin/env bash
# ============================================================
# 本体起立（带状态门禁）
#
# 为什么不能直接发"起立"：
#   0x21010202 是「起立 / 趴下」**轮流切换**（toggle）。
#   狗站着的时候发它 -> 直接趴下；只有狗趴着时发它才会起立。发反了要出事。
#   所以本脚本先用按需探针读 robot_basic_state，只在确认是「趴下(0)」时才发。
#
# robot_basic_state 取值（厂商协议表）：
#   0 趴下   1 准备起立   2 正在起立   3 力控（站立就绪，可运动）
#   4 正在趴下   5 失控保护   6 姿态调整   7 翻身   8 AI状态   9 回零
#
# 用法：
#   bash scripts/standup.sh            # 检查 + 必要时起立，结束后再确认一次
#   bash scripts/standup.sh --check    # 只读状态，不发起立指令
#
# 探针用 AF_PACKET 旁路抓包，需要 root（脚本内部自带 sudo 输入）。
# ============================================================

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="$HERE/robot_state_probe.py"
IFACE="${IFACE:-eth0}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# ⚠️ source 之前必须 set +u：ROS 的 setup.bash 在 set -u 下会静默终止 shell
set +u
# shellcheck disable=SC1090
source "$HERE/env.sh" >/dev/null 2>&1
TRANSFER_WS=/home/ysc/lite_cog/transfer
[ -f "$TRANSFER_WS/devel/setup.bash" ] && source "$TRANSFER_WS/devel/setup.bash"
set -u

K_STAND_LIE=553714178   # 0x21010202 起立/趴下 toggle

name_of() {
  case "${1:-}" in
    0) echo "趴下" ;;
    1) echo "准备起立" ;;
    2) echo "正在起立" ;;
    3) echo "力控状态（站立就绪）" ;;
    4) echo "正在趴下" ;;
    5) echo "失控保护" ;;
    6) echo "姿态调整" ;;
    7) echo "执行翻身" ;;
    8) echo "AI状态" ;;
    9) echo "回零" ;;
    *) echo "未知($1)" ;;
  esac
}

# 读一次 basic_state（按需探针，跑完即退，不常驻）
read_state() {
  local out
  out=$(printf "\047\n" | sudo -S python3 "$PROBE" "$IFACE" 4 2>/dev/null)
  printf '%s\n' "$out" | grep "基本状态" | sed 's/.*:[[:space:]]*\([0-9]\+\).*/\1/' | head -1
}

S="$(read_state)"
echo "[standup] 当前 robot_basic_state = ${S:-?} （$(name_of "${S:-?}")）"

if [ -z "${S:-}" ]; then
  echo "[standup] ❌ 读不到状态：检查网卡名（IFACE=$IFACE，用 ip -o link 确认）、本体是否上电" >&2
  exit 1
fi

case "$S" in
  3)
    echo "[standup] ✅ 已是站立就绪（力控），可以走了"
    exit 0
    ;;
  1|2)
    echo "[standup] 起立进行中（$(name_of "$S")），等待 6 秒后再看"
    sleep 6
    S2="$(read_state)"
    echo "[standup] 现在 = ${S2:-?}（$(name_of "${S2:-?}")）"
    [ "${S2:-}" = "3" ] && echo "[standup] ✅ 站立完成" || echo "[standup] ⚠️  仍未站立，建议用手柄起立后重试"
    exit 0
    ;;
  0)
    if [ "$CHECK_ONLY" -eq 1 ]; then
      echo "[standup] --check：狗趴着，未发起立指令"
      exit 0
    fi
    echo "[standup] 狗趴着 -> 发起立 toggle（0x21010202）"
    timeout 12 rostopic pub -1 /simple_cmd message_transformer/SimpleCMD \
      "{cmd_code: $K_STAND_LIE, cmd_value: 0, type: 0}" 2>&1 | tail -1
    sleep 8
    S3="$(read_state)"
    echo "[standup] 起立后 = ${S3:-?}（$(name_of "${S3:-?}")）"
    if [ "${S3:-}" = "3" ]; then
      echo "[standup] ✅ 已站立，可以走"
    else
      echo "[standup] ⚠️  起立后不是力控态，别发速度指令；建议手柄起立后重跑本脚本确认"
    fi
    exit 0
    ;;
  *)
    echo "[standup] ⚠️  状态 $(name_of "$S") 不适合自动起立，请用手柄处理" >&2
    exit 1
    ;;
esac
