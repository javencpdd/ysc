#!/usr/bin/env bash
# ============================================================
# auto_mode.py 的环境包装：先建 ROS1 环境（清 foxy + 加载 noetic），
# 再额外加载 message_transformer 所在的 transfer 工作空间，然后跑 Python。
#
# 不能直接 `python3 auto_mode.py`：
#   1) 103 的 ~/.bashrc 默认 source foxy，不隔离会 import 不到 rospy(noetic)；
#   2) message_transformer 的 msg 在 /home/ysc/lite_cog/transfer/devel 下，
#      scan_planner 的 env.sh 并不加载它。
# ============================================================
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ⚠️ source 之前必须 set +u：ROS 的 setup.bash 里有未绑定变量引用，
#    在 set -u 下会直接终止整个 shell（脚本表现为"无任何输出、exit 1"）。
set +u
# shellcheck disable=SC1090
source "$HERE/env.sh" >/dev/null 2>&1

TRANSFER_WS=/home/ysc/lite_cog/transfer
if [ -f "$TRANSFER_WS/devel/setup.bash" ]; then
  # shellcheck disable=SC1090
  source "$TRANSFER_WS/devel/setup.bash"
else
  echo "[auto_mode] 找不到 $TRANSFER_WS/devel/setup.bash，message_transformer 消息可能导入失败" >&2
fi
set -u

exec python3 "$HERE/auto_mode.py" "$@"
