#!/bin/bash
# 读取 GPS 话题实际数据（Foxy 不支持 --once，用 timeout + head）
source /opt/ros/foxy/setup.bash 2>/dev/null
export ROS_DOMAIN_ID=0

echo "############ 1. NavSat 消息定义 ############"
timeout 8 ros2 interface show drdds/msg/NavSat 2>&1 | head -30
echo

echo "############ 2. /GPS 数据（10 秒）############"
timeout 12 ros2 topic echo /GPS 2>&1 | head -45
echo

echo "############ 3. /GPS_SYS_MODE ############"
timeout 10 ros2 topic echo /GPS_SYS_MODE 2>&1 | head -10
echo

echo "############ 4. /GPS_SYN_UTC ############"
timeout 10 ros2 topic echo /GPS_SYN_UTC 2>&1 | head -10
echo

echo "############ 5. /GPS_CFGSYS ############"
timeout 10 ros2 topic echo /GPS_CFGSYS 2>&1 | head -10
echo

echo "############ 6. 所有含 GPS/RTK/FIBOCOM 的话题及发布者数 ############"
for t in $(timeout 12 ros2 topic list 2>/dev/null | grep -iE 'gps|rtk|fibocom|gnss|fix'); do
    printf "  %-32s " "$t"
    timeout 6 ros2 topic info "$t" 2>/dev/null | grep -E 'Type|Publisher count|Subscription count' | tr '\n' ' | '
    echo
done
