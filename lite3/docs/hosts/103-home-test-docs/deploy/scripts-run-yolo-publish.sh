#!/usr/bin/env bash
# ============================================================
# YOLO 发布本体：唯一的启动执行体
# ============================================================
# systemd unit（ExecStart）与 lite3-publish-ctl.sh（手工模式）共用本脚本，
# 保证两种拉起方式行为完全一致。
#
# 职责：加载 ros2 环境 → 读 env（**只剩启动期静态键**）→ exec 成主进程。
# 注意用 exec：让 python 直接接管本进程 PID，便于 systemd/PID 文件管理。
#
# P2 起（计划书 §5.11）：运行期配置唯一来源 = config/yolo8.json。
#   · YOLO8_PUBLISH_MODE 及其推导出的开关**已弃用**（会与 config 双写）；
#   · 已迁移键（YOLO8_RTMP_URL / BITRATE / CONF / ROS2_EVERY）在 env 中已注释，
#     仅保留"缺失 config 时的回退"能力（worker 侧 config_loader 仍读 env 兜底）。
# ============================================================
set -euo pipefail

APP_DIR=/home/test/yolo8
ENV_FILE=$APP_DIR/deploy/yolo-publish.env

# ROS2 Foxy 环境（systemd/非交互这里必须显式 source，不能依赖 ~/.bashrc）
# 注意：setup.bash 内部会读未定义变量（AMENT_TRACE_SETUP_FILES），
# 在 set -u 下会直接中断 → 临时关掉 nounset 再 source。
set +u
# shellcheck disable=SC1091
source /opt/ros/foxy/setup.bash
set -u

# 载入配置（重复注入无害：systemd 已注入时这里只是再读一遍）
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# 弃用提示（不 exit：旧部署脚本可能仍带着 MODE 变量，不该因此起不来）
if [ -n "${YOLO8_PUBLISH_MODE:-}" ]; then
  echo "[run-yolo-publish] 提示：YOLO8_PUBLISH_MODE 已弃用，请改 config/yolo8.json 的 stream.rtmp / stream.ros2_image" >&2
fi

echo "[run-yolo-publish] 配置以 config/yolo8.json 为准（rtmp/ros2/阈值/源均可热改，无需重启）"

mkdir -p "$APP_DIR/logs"
cd "$APP_DIR/src"
exec python3 -u run_tracker_publish.py
