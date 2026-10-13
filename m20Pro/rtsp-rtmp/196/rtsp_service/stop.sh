#!/bin/bash
# 关闭所有进程名包含 v4l2 的进程
pkill -f v4l2
pkill -f push_video

# 检查 pkill 命令是否成功执行
if [ $? -eq 0 ]; then
    echo "所有包含 v4l2 的进程已成功关闭。"
else
    echo "未找到包含 v4l2 的进程或关闭失败。"
fi
