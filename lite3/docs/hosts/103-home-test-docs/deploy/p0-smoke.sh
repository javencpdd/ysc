#!/usr/bin/env bash
# P0 冒烟启动包装。
# 关键点：先把自己 PID 落盘再 exec；run-yolo-publish.sh 末尾也 exec python3，
# 因此这个 PID 一路保留到 python3 进程，便于之后按 PID 停止（避免 pkill -f 自杀，坑 11.1）。
set -u

APP_DIR=/home/test/yolo8
echo $$ > "$APP_DIR/logs/p0-smoke.pid"
exec bash "$APP_DIR/deploy/scripts/run-yolo-publish.sh"
