#!/bin/bash
# usbmon_probe.sh — 抓 Bus002(video1) 的 USB 总线数据 22s，同时拉 20s 流用于时间轴对齐
# 目的：看帧洞期间 USB 总线上到底发生了什么（空包 / 完全静默 / 控制传输）
cd /tmp
rm -f usb2.log v1_probe.ts
P="'"

printf "$P\n" | sudo -S timeout 22 cat /sys/kernel/debug/usb/usbmon/2u > /tmp/usb2.log 2>/dev/null &
CAP=$!
sleep 1
ffmpeg -v error -y -i http://127.0.0.1:8888/video1/index.m3u8 -c copy -t 20 /tmp/v1_probe.ts 2>/dev/null
wait $CAP

echo "=== sizes ==="
ls -la /tmp/usb2.log /tmp/v1_probe.ts
echo "=== usbmon line count / types ==="
grep -c " C " /tmp/usb2.log
awk '{print $3}' /tmp/usb2.log | sort | uniq -c | head
echo "=== urb direction types (complete only) ==="
grep " C " /tmp/usb2.log | awk '{print $4}' | cut -d: -f1 | sort | uniq -c
