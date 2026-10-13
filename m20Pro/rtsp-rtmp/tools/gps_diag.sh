#!/bin/bash
# 诊断为何 ros2 topic echo 无输出
source /opt/ros/foxy/setup.bash 2>/dev/null
export ROS_DOMAIN_ID=0

echo "############ 1. 用标准类型话题验证整条链路 (/GPS_SYN_UTC: std_msgs/String) ############"
timeout 15 ros2 topic echo /GPS_SYN_UTC 2>&1 | head -12
echo "[退出码 $?]"
echo

echo "############ 2. 频率测量（各 12 秒）############"
for t in /GPS /GPS_SYS_MODE /GPS_SYN_UTC; do
    echo "--- $t ---"
    timeout 14 ros2 topic hz "$t" 2>&1 | head -4
done
echo

echo "############ 3. drdds 消息是否对 Python 可见 ############"
python3 -c "import drdds; print('drdds 包路径:', drdds.__file__)" 2>&1 | head -3
python3 -c "from drdds.msg import NavSat; print('NavSat OK:', NavSat)" 2>&1 | head -5
echo "--- 找 drdds 消息定义 ---"
find / -name 'NavSat*.msg' -o -name 'drdds' -type d 2>/dev/null | grep -v proc | head -8
echo "--- rosidl 类型支持库 ---"
find / -name '*drdds*' -name '*.so' 2>/dev/null | head -8
ls /opt/robot/share/gs2dds/bin/ 2>/dev/null
echo

echo "############ 4. 直接向 /GPS 订阅（ros2 topic echo 完整 stderr）############"
timeout 15 ros2 topic echo /GPS --qos-reliability reliable 2>&1 | head -25
echo "[退出码 $?]"
echo

echo "############ 5. GPS 串口 /dev/ttyS5 谁能读 ############"
fuser -v /dev/ttyS5 2>&1 | head -5
echo "--- gps_node 是否持有串口 ---"
PID=$(pgrep -x gps_node | head -1)
echo "gps_node PID=$PID"
[ -n "$PID" ] && ls -l /proc/$PID/fd 2>/dev/null | grep -i tty
echo

echo "############ 6. basic_server 的 GPS 输出（30002 端口）############"
timeout 8 python3 - <<'PY'
import socket
for port in (30002, 30001):
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=4)
        s.settimeout(4)
        buf = b''
        try:
            while len(buf) < 256:
                d = s.recv(256)
                if not d: break
                buf += d
        except socket.timeout:
            pass
        print(f'  port {port}: 收到 {len(buf)} 字节', buf[:48].hex(' ') if buf else '')
        s.close()
    except Exception as e:
        print(f'  port {port}: {type(e).__name__} {e}')
PY
