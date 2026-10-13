#!/bin/bash

if [ -f /opt/robot/os_type ]; then
    os_type=$(cat /opt/robot/os_type)
    if [ "$os_type" = "CA9B_VOS" ]; then
        echo "os_type=$os_type, 脚本直接退出"
        exit 1
    fi
    if [ "$os_type" = "CA9B_GOS" ]; then
        echo "os_type=$os_type, 脚本直接退出"
        exit 1
    fi
    if [ "$os_type" = "CA9B_NOS" ]; then
        echo "os_type=$os_type, 脚本直接退出"
        exit 1
    fi
fi

cd /opt/robot/scripts/board_resources/rtsp_service
sudo ./mediamtx &
sleep 5
/opt/robot/scripts/board_resources/rtsp_service/push_video.sh
