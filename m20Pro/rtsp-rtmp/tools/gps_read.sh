#!/bin/bash
# 读取 GPS 话题的实际内容
source /opt/ros/foxy/setup.bash 2>/dev/null
export ROS_DOMAIN_ID=0

echo "############ 0. gps.yaml 配置 ############"
cat /opt/robot/share/node_driver/config/gps.yaml 2>/dev/null | head -40
echo

echo "############ 1. 话题类型 ############"
for t in /GPS /GPS_SYS_MODE /GPS_SYN_UTC /GPS_CFGSYS /FIBOCOM/net_rtk/gngga /FIBOCOM/net_rtk/heading; do
    echo "--- $t ---"
    timeout 8 ros2 topic info -v "$t" 2>&1 | head -12
done
echo

echo "############ 2. 频率 ############"
for t in /GPS /FIBOCOM/net_rtk/gngga; do
    echo -n "  $t: "
    timeout 12 ros2 topic hz "$t" 2>&1 | head -2 | tr '\n' ' '
    echo
done
echo

echo "############ 3. /GPS 实际内容（取一条）############"
timeout 15 ros2 topic echo /GPS --once 2>&1 | head -40
echo

echo "############ 4. /FIBOCOM/net_rtk/gngga 实际内容 ############"
timeout 15 ros2 topic echo /FIBOCOM/net_rtk/gngga --once 2>&1 | head -20
echo

echo "############ 5. /FIBOCOM/net_rtk/heading 实际内容 ############"
timeout 15 ros2 topic echo /FIBOCOM/net_rtk/heading --once 2>&1 | head -20
echo

echo "############ 6. /GPS_SYS_MODE ############"
timeout 12 ros2 topic echo /GPS_SYS_MODE --once 2>&1 | head -10
