#!/bin/bash
#sudo bash /home/ysc/rtsp_service/usb_ctl.sh enable
sleep 3

# 定义推流函数
push_video() {
    local core=$1
    local config_file=$2
    local video_device=$(jq -r '.video_device // 0' "$config_file" 2>/dev/null || echo 0)
    
    echo "启动推流: taskset -c $core /opt/robot/scripts/board_resources/rtsp_service/push_video $config_file"
    
    while true; do
        # 检查视频设备是否存在
        if [ -e "/dev/video$video_device" ]; then
            taskset -c $core /opt/robot/scripts/board_resources/rtsp_service/push_video "$config_file"
            echo "推流进程退出，可能设备已断开，将在3秒后重试..."
			/opt/robot/scripts/board_resources/rtsp_service/restart.sh
        else
            echo "视频设备 /dev/video$video_device 不存在，将在3秒后重试..."
        fi
        sleep 3
    done
}

if lsusb | grep -q "SM_USB_107X"; then
	if [ -e /dev/video0 ]; then
 		push_video "4,5" "/opt/robot/scripts/board_resources/rtsp_service/SM_USB_107X_0.json" &
	        push_video "6,7" "/opt/robot/scripts/board_resources/rtsp_service/SM_USB_107X_2.json" &
	else
	    push_video "4,5" "/opt/robot/scripts/board_resources/rtsp_service/SM_USB_107X_1.json" &
	        push_video "6,7" "/opt/robot/scripts/board_resources/rtsp_service/SM_USB_107X_3.json" &
	fi
else
	# 对于非SM_USB_107X设备，使用默认GStreamer推流
	taskset -c 4,5 sudo gst-launch-1.0 v4l2src device=/dev/video0 ! image/jpeg, width=1280, height=720, framerate=30/1 ! jpegdec ! videoconvert ! mpph265enc rc-mode=0 bps=1800000 bps-max=2000000 qp-min=12 qp-max=45 ! rtspclientsink location=rtsp://10.21.31.155:8554/video1 latency=10 &
	taskset -c 6,7 sudo gst-launch-1.0 v4l2src device=/dev/video2 ! image/jpeg, width=1280, height=720, framerate=30/1 ! jpegdec ! videoconvert ! mpph265enc rc-mode=0 bps=1800000 bps-max=2000000 qp-min=12 qp-max=45 ! rtspclientsink location=rtsp://10.21.31.155:8554/video2 latency=10 &
fi
