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

is_time_synced() {
    local year

    if command -v timedatectl >/dev/null 2>&1; then
        if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q "^yes$"; then
            return 0
        fi
        if timedatectl status 2>/dev/null | grep -q "System clock synchronized: yes"; then
            return 0
        fi
    fi

    year=$(date +%Y 2>/dev/null || echo 0)
    if [ "$year" -ge "${PTP_MIN_YEAR:-2025}" ] 2>/dev/null; then
        return 0
    fi

    return 1
}

wait_time_sync() {
    local max_wait=${PTP_SYNC_TIMEOUT:-60}
    local count=0

    while ! is_time_synced; do
        if [ "$count" -ge "$max_wait" ]; then
            echo "警告: 等待 ${max_wait}s 后仍未完成 PTP 同步, 继续启动推流"
            return 1
        fi

        if [ $((count % 5)) -eq 0 ]; then
            echo "等待 PTP 同步... (${count}/${max_wait})"
        fi

        sleep 1
        count=$((count + 1))
    done

    echo "PTP 同步完成"
    return 0
}

wait_time_sync
/opt/robot/scripts/board_resources/rtsp_service/push_video.sh
