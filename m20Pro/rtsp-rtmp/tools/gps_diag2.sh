#!/bin/bash
# 1) 查是否有有效定位  2) 提取 M20 直连协议（TCP 30001）的报文格式
source /opt/ros/foxy/setup.bash 2>/dev/null
export ROS_DOMAIN_ID=0

echo "############ 1. gps_node 日志 ############"
ls -la /var/opt/robot/log/ 2>/dev/null | head -15
find /var/opt/robot/log -iname '*gps*' 2>/dev/null | head -5
for f in $(find /var/opt/robot/log -iname '*gps*' 2>/dev/null | head -2); do
    echo "--- $f (尾部) ---"; tail -25 "$f"
done
echo

echo "############ 2. gps_node 进程状态与串口 ############"
ps -o pid=,etime=,pcpu=,cmd= -p $(pgrep -x gps_node | head -1) 2>/dev/null
echo "--- 串口参数 ---"
stty -F /dev/ttyS5 -a 2>&1 | head -5
echo

echo "############ 3. 串口是否有数据（被动观察 3 秒，只读不抢）############"
timeout 5 python3 - <<'PY'
import select, os
try:
    fd = os.open('/dev/ttyS5', os.O_RDONLY | os.O_NONBLOCK)
    buf = b''
    import time
    t0 = time.time()
    while time.time() - t0 < 3:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            d = os.read(fd, 4096)
            if d: buf += d
    os.close(fd)
    print('  读到 %d 字节' % len(buf))
    if buf:
        txt = buf.decode('ascii', 'replace')
        print('  前 500 字符:')
        print('  ' + txt[:500].replace('\n', '\n  '))
    else:
        print('  (3 秒内无数据)')
except Exception as e:
    print('  打开失败:', type(e).__name__, e)
PY
echo

echo "############ 4. 从 server.js 提取 M20 直连协议 ############"
echo "--- 含 GPS/协议关键字的位置 ---"
grep -oE '.{60}(gps|GPS)\b.{100}' /home/tank/m20/server.js | head -12
echo
echo "--- 帧头/命令字相关常量 ---"
grep -oE '(0x[0-9a-fA-F]{2},){3,}' /home/tank/m20/server.js | head -12
echo
echo "--- 缓冲区解析相关 ---"
grep -oE '.{80}(recvBuffer|_recvBuffer|parseFrame|parsePacket|_parseBuffer).{140}' /home/tank/m20/server.js | head -8
