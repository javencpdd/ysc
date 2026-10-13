#!/usr/bin/env bash
# ============================================================================
# install_service.sh —— 安装 systemd 服务 + m20video 命令
#
#     sudo ./install_service.sh                安装（默认不自启、不启动，避免占用 CPU）
#     sudo ./install_service.sh --autostart    安装并设为开机自启
#     sudo ./install_service.sh start          安装后立即启动一次
#     sudo ./install_service.sh uninstall      卸载
#
#   说明：本服务跑的是 H.265 -> H.264 硬件转码，实测约占 1 个 CPU 核/路，
#         因此默认「装好但不启动」。需要时用 `sudo m20video up` 拉起。
# ============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="$SCRIPT_DIR/systemd/m20video.service"
UNIT_DST="/etc/systemd/system/m20video.service"
CLI_SRC="$SCRIPT_DIR/m20video"
CLI_DST="/usr/local/bin/m20video"

AUTOSTART=0
STARTNOW=0
ACTION="install"
for a in "$@"; do
    case "$a" in
        --autostart) AUTOSTART=1 ;;
        start)       STARTNOW=1 ;;
        uninstall)   ACTION="uninstall" ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 sudo 运行"; exit 1
fi

if [ "$ACTION" = "uninstall" ]; then
    systemctl disable --now m20video.service 2>/dev/null
    rm -f "$UNIT_DST"
    systemctl daemon-reload
    rm -f "$CLI_DST"
    echo "已卸载 m20video.service 与 m20video 命令"
    echo "（项目文件仍在 $SCRIPT_DIR，可用 ./stop.sh 手动停止）"
    exit 0
fi

# 避免 systemd 与手动 start.sh 同时管理
if [ -d "$SCRIPT_DIR/run" ] && ls "$SCRIPT_DIR"/run/forward-*.pid >/dev/null 2>&1; then
    echo "检测到手动启动的实例，先停止..."
    "$SCRIPT_DIR/stop.sh" >/dev/null 2>&1 || true
    sleep 2
fi

chmod +x "$SCRIPT_DIR"/*.sh "$CLI_SRC"

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
install -m 0755 "$CLI_SRC"  "$CLI_DST"
systemctl daemon-reload

if [ "$AUTOSTART" -eq 1 ]; then
    systemctl enable m20video.service
    echo "已设置开机自启（注意：会常驻占用约 2 个 CPU 核）"
else
    systemctl disable m20video.service 2>/dev/null
    echo "已安装，但未设置开机自启（默认关闭，避免 CPU 消耗）"
fi

if [ "$STARTNOW" -eq 1 ]; then
    systemctl start m20video.service
    sleep 4
    systemctl --no-pager --quiet is-active m20video.service >/dev/null 2>&1 \
        && echo "已启动" || echo "启动失败，查看: journalctl -u m20video.service -n 50"
fi

echo
echo "安装完成。当前状态:"
printf "  开机自启: %s\n" "$(systemctl is-enabled m20video.service 2>&1)"
printf "  运行状态: %s\n" "$(systemctl is-active m20video.service 2>&1)"
echo
echo "日常使用:"
echo "  sudo m20video up | down | reset | status | doctor"
echo "  sudo m20video log f              # 跟踪前视日志"
echo "  sudo m20video enable | disable   # 开机自启开关"
