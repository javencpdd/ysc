#!/bin/bash
echo "=== 停止推流服务 ==="

# 1. 先通知push_video脚本退出（会触发trap清理）
pkill -f push_video
sleep 2

# 2. 强制杀死残留的gst-launch进程
pids=$(pgrep -f "gst-launch" 2>/dev/null)
if [ -n "$pids" ]; then
    echo "强制停止残留gst-launch进程: $pids"
    kill -9 $pids 2>/dev/null
    sleep 1
fi

# 3. 再次检查确保清理干净
pids=$(pgrep -f "gst-launch\|push_video" 2>/dev/null)
if [ -n "$pids" ]; then
    echo "警告: 仍有残留进程: $pids"
    kill -9 $pids 2>/dev/null
    sleep 1
fi

echo "推流服务已停止"

# 4. 启动服务
startFile=/opt/robot/scripts/board_resources/rtsp_service/start_server.sh
if [ -x "$startFile" ]; then
    echo "=== 启动推流服务 ==="
    "$startFile"
    if [ $? -eq 0 ]; then
        echo "start_server.sh 启动成功"
    else
        echo "start_server.sh 启动失败"
    fi
else
    echo "start_server.sh 不存在或没有执行权限"
fi
