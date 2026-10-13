#!/bin/bash
# 只读：定位 GPS 的对外接口（ROS 2 话题 / M20 直连协议）
echo "############ 1. gps_run.sh 内容 ############"
cat /opt/robot/share/node_driver/scripts/gps_run.sh 2>&1
echo
echo "--- node_driver 目录 ---"
ls -la /opt/robot/share/node_driver/ 2>&1 | head -15
ls -la /opt/robot/share/node_driver/scripts/ 2>&1 | head -15
echo

echo "############ 2. gps_node 二进制里的 ROS 话题名 ############"
BIN=$(ls /opt/robot/share/node_driver/gps_node /opt/robot/share/node_driver/bin/gps_node 2>/dev/null | head -1)
echo "二进制: ${BIN:-未找到}"
[ -n "$BIN" ] && strings -a "$BIN" 2>/dev/null | grep -E '^/[a-zA-Z_][a-zA-Z0-9_/]*$' | sort -u | head -25
echo "--- 含 gps/gnss/fix 的字符串 ---"
[ -n "$BIN" ] && strings -a "$BIN" 2>/dev/null | grep -iE 'gps|gnss|fix|nmea|navsat' | sort -u | head -25
echo

echo "############ 3. gs2dds 模块 ############"
ls -la /opt/robot/share/gs2dds/ 2>&1 | head -10
ls -la /opt/robot/share/gs2dds/scripts/ 2>&1 | head -10
for f in /opt/robot/share/gs2dds/scripts/*.sh; do echo "--- $f ---"; cat "$f" 2>/dev/null | head -20; done
echo

echo "############ 4. ROS 2 话题（source 环境后）############"
source /opt/ros/foxy/setup.bash 2>/dev/null
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
echo "ROS_DISTRO=$ROS_DISTRO  ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
timeout 15 ros2 topic list 2>&1 | head -40
echo

echo "############ 5. 直接探测 M20 直连协议 TCP 30001 ############"
timeout 10 python3 - <<'PY'
import socket
try:
    s = socket.create_connection(('127.0.0.1', 30001), timeout=5)
    s.settimeout(6)
    buf = b''
    try:
        while len(buf) < 512:
            d = s.recv(512)
            if not d: break
            buf += d
    except socket.timeout:
        pass
    print('  收到 %d 字节' % len(buf))
    if buf:
        print('  前 96 字节 hex:', buf[:96].hex(' '))
        # 试着找可读字符串
        import re
        txt = re.findall(rb'[\x20-\x7e]{4,}', buf)
        print('  可读片段:', [t.decode() for t in txt[:12]])
    s.close()
except Exception as e:
    print('  连接失败:', type(e).__name__, e)
PY
