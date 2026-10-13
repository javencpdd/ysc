#!/bin/bash
# 抓原始 NMEA（短暂共享串口，gps_node 仍持有，影响可忽略）
echo "############ 原始 NMEA 采样（3 秒）############"
timeout 8 python3 - <<'PY'
import os, select, time
fd = os.open('/dev/ttyS5', os.O_RDONLY | os.O_NONBLOCK)
buf = b''
t0 = time.time()
while time.time() - t0 < 3:
    r, _, _ = select.select([fd], [], [], 0.5)
    if r:
        try:
            d = os.read(fd, 8192)
            if d: buf += d
        except OSError:
            break
os.close(fd)
print('  共读取 %d 字节' % len(buf))
txt = buf.decode('ascii', 'replace')
lines = [l.strip() for l in txt.split('\n') if l.strip().startswith('$')]
print('  完整 NMEA 语句 %d 条，去重后示例：' % len(lines))
seen = set()
for l in lines:
    key = l.split(',')[0]
    if key in seen: continue
    seen.add(key)
    print('   ', l[:110])
print()
print('  —— 关键判读 ——')
for l in lines:
    if l.startswith('$GNRMC') or l.startswith('$GNGGA'):
        f = l.split(',')
        if l.startswith('$GNRMC'):
            print('  RMC 状态字段(第2个): %r  <- V=无效定位, A=有效' % (f[2] if len(f)>2 else '?'))
        else:
            print('  GGA 定位质量(第6个): %r  <- 0=无定位, 1=单点, 2=差分, 4=RTK固定' % (f[6] if len(f)>6 else '?'))
        break
PY
echo
echo "############ M20 直连协议里 GPS 相关（server.js）############"
grep -oE '.{50}(gps|GPS).{120}' /home/tank/m20/server.js 2>/dev/null | head -10
echo
echo "############ gps_node 是否在发 DDS（看它连的 UDP 端口/IP）############"
PID=$(pgrep -x gps_node | head -1)
ss -unp 2>/dev/null | grep "pid=$PID," | head -6
