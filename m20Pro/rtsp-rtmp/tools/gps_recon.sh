#!/bin/bash
# 只读勘察：M20 机器狗的 GPS 信号来源与获取方式
echo "############ 1. 已知线索（config.json 里的 GPS 段）############"
sed -n '/"gps"/,/},/p' /home/tank/m20/config.json
echo

echo "############ 2. TCP 30001 / UDP 30000 是谁在提供 ############"
ss -tlnp 2>/dev/null | grep -E ':3000[12]|:30001|:30000'
ss -ulnp 2>/dev/null | grep -E ':30000|:30001'
echo
echo "--- basic_server 相关字符串 ---"
strings -a /opt/robot/share/basic_server/bin/basic_server 2>/dev/null \
  | grep -iE 'gps|gnss|nmea|rtcm|30001|30000|lat|lon|longitude' | sort -u | head -25
echo

echo "############ 3. ROS 2 侧是否有 GPS 话题 ############"
ls /opt/robot/share/ 2>/dev/null | head -30
echo "--- ROS 环境 ---"
ls /opt/ros/ 2>/dev/null
echo

echo "############ 4. 系统里的 GPS / 串口设备 ############"
ls -la /dev/ttyUSB* /dev/ttyACM* /dev/ttyS[0-9]* 2>/dev/null | head -12
echo "--- gpsd ---"; which gpsd cgps gpsmon 2>&1 | head -3
systemctl is-active gpsd 2>&1
echo "--- 其他 GPS 相关进程 ---"
ps -eo pid,cmd | grep -iE 'gps|gnss|nmea' | grep -v grep | head
echo

echo "############ 5. /opt/robot/share 下的驱动模块 ############"
find /opt/robot/share -maxdepth 1 -type d 2>/dev/null | head -30
