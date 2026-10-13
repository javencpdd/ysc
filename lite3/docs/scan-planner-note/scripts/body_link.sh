#!/usr/bin/env bash
# ============================================================
# 把 SCAN-Planner 的速度输出接到 Lite3 本体
#
#   /scan_planner/cmd_vel
#        └─(topic_tools relay，本脚本)─→ /cmd_vel
#                └─(ros2qnx)─→ UDP 192.168.1.120:43893 ─→ 机器人本体
#
# ⚠️ 开 relay 之前必须确认三件事：
#    1) 狗已站立，且处于自主模式并有心跳：
#         bash scripts/auto_mode.sh auto      （另开一个终端，一直挂在后台发心跳）
#    2) 周围空旷；手里握着遥控器（手柄可强制夺回控制权）
#    3) 首次联调建议把狗架空（四腿离地），只验证指令链路，不落地行走
#
# 用法：
#    bash scripts/body_link.sh start
#    bash scripts/body_link.sh status
#    bash scripts/body_link.sh stop
# ============================================================
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(dirname "$HERE")"
# ⚠️ source 之前必须 set +u：ROS 的 setup.bash 里有未绑定变量引用，
#    在 set -u 下会直接把整个 shell 终止（脚本表现为"无任何输出、exit 1"）。
set +u
# shellcheck disable=SC1090
source "$HERE/env.sh" >/dev/null 2>&1
set -u
LOG="$WS/logs/body_link.log"
mkdir -p "$WS/logs" 2>/dev/null

# 判定"本体速度 relay"是否活着。
# ⚠️ 陷阱一：lio_relay.launch 也会起 3 个 topic_tools/relay（/Odometry -> /LIO/*），
#    光看进程名 relay 会误判成"本体链路已接通"。
# ⚠️ 陷阱二：不能用 pgrep -f "<完整命令行>"，远程 ssh 的 bash -c 命令行含同样字符串，
#    会把自己和 SSH 会话一起杀掉（输出全空 + exit 255）。
# 正确做法：先用 -x 取进程名为 relay 的 PID，再逐个读 /proc/<pid>/cmdline 过滤话题名。
relay_pids() {
  local p
  for p in $(pgrep -x relay 2>/dev/null); do
    if tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q "/scan_planner/cmd_vel"; then
      echo "$p"
    fi
  done
}

ros2qnx_alive() { pgrep -x ros2qnx >/dev/null 2>&1; }

has_pub() {  # $1=话题；打印 Publishers 到结尾（Subscribers 是最后一节，不能用区间截取）
  timeout 6 rostopic info "$1" 2>/dev/null | sed -n '/Publishers:/,$p' | grep -q "http://"
}

ACTION="${1:-status}"

case "$ACTION" in
  start)
    if [ -n "$(relay_pids)" ]; then
      echo "[body_link] relay 已在跑（PID: $(relay_pids | tr '\n' ' ')），无需重复启动"
      exit 0
    fi
    if ! ros2qnx_alive; then
      echo "[body_link] ❌ ros2qnx 不在跑，/cmd_vel 没人转发给本体" >&2
      echo "            先启动本体链路：bash /home/ysc/lite_cog/system/scripts/transfer/start_transfer.sh" >&2
      exit 1
    fi
    if ! has_pub /scan_planner/cmd_vel; then
      echo "[body_link] ⚠️  /scan_planner/cmd_vel 暂无发布者（规划器还没起 / 还没发目标点）"
      echo "            仍会启动 relay，收到目标点后自动生效"
    fi
    echo "==================== 安 全 确 认 ===================="
    echo " 1) 狗已站立 + 自主模式 + 心跳在发 (scripts/auto_mode.sh auto)"
    echo " 2) 周围空旷，手握遥控器可随时接管"
    echo " 3) 首次联调建议架空（四腿离地）"
    echo "===================================================="
    for i in 3 2 1; do
      printf "   %d 秒后接通速度指令（Ctrl+C 中止）...\n" "$i"
      sleep 1
    done
    setsid nohup rosrun topic_tools relay /scan_planner/cmd_vel /cmd_vel \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 2
    if has_pub /cmd_vel; then
      echo "[body_link] ✅ 已接通：/scan_planner/cmd_vel -> /cmd_vel -> ros2qnx -> 192.168.1.120:43893"
      echo "            relay PID: $(relay_pids | tr '\n' ' ')；日志 $LOG"
    else
      echo "[body_link] ❌ 未检测到 /cmd_vel 的发布者，看日志：$LOG" >&2
      exit 1
    fi
    ;;

  stop)
    PIDS="$(relay_pids)"
    if [ -z "$PIDS" ]; then
      echo "[body_link] relay 本来就没在跑"
    else
      # shellcheck disable=SC2086
      kill $PIDS 2>/dev/null
      sleep 1
      LEFT="$(relay_pids)"
      if [ -n "$LEFT" ]; then
        # shellcheck disable=SC2086
        kill -9 $LEFT 2>/dev/null
        sleep 1
      fi
      echo "[body_link] 已断开 relay（原 PID: $(echo $PIDS | tr '\n' ' ')）"
    fi
    echo "[body_link] 提示：如需让狗立刻停住，再发一次零速度：bash scripts/auto_mode.sh zero"
    ;;

  status)
    echo "--- relay（把规划速度接到 /cmd_vel）---"
    PIDS="$(relay_pids)"
    if [ -n "$PIDS" ]; then
      echo "  ✅ 在跑，PID: $(echo $PIDS | tr '\n' ' ')"
    else
      echo "  ⭕ 未启动（规划器发速度也不会传给本体）"
    fi
    echo "--- ros2qnx（/cmd_vel -> 本体 43893）---"
    if ros2qnx_alive; then
      echo "  ✅ 在跑，PID: $(pgrep -x ros2qnx | tr '\n' ' ')"
      timeout 6 rostopic info /cmd_vel 2>/dev/null | sed -n '/Subscribers:/,$p' | sed 's/^/  /'
    else
      echo "  ❌ 不在跑"
    fi
    echo "--- /scan_planner/cmd_vel 当前值 ---"
    timeout 5 rostopic echo -n1 /scan_planner/cmd_vel 2>/dev/null | sed 's/^/  /' \
      || echo "  （无数据：规划器未起或尚未发目标点）"
    ;;

  *)
    echo "用法：bash scripts/body_link.sh {start|stop|status}"
    exit 1
    ;;
esac
