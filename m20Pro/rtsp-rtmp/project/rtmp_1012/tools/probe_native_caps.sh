#!/bin/bash
# probe_native_caps.sh — 只读探测 M20 两颗相机声明的全部分辨率x帧率组合
# 用途：为「不被迫降分辨率」方向找拐点——相机原生支持哪些组合、标称帧率多少
# 注意：查询类 ioctl 不需要独占设备，不影响正在运行的采集流
LOG=/home/user/caps_probe.log
{
echo "=== probe time: $(date '+%F %T') ==="
for dev in /dev/video0 /dev/video2; do
    echo ""
    echo "=== $dev formats-ext ==="
    printf "'\n" | sudo -S v4l2-ctl -d "$dev" --list-formats-ext 2>&1
    echo ""
    echo "=== $dev controls (exposure/fps related) ==="
    printf "'\n" | sudo -S v4l2-ctl -d "$dev" --list-ctrls 2>&1 | grep -iE 'exposure|frame_rate|gain|bright|auto' | head -15
done
} | tee "$LOG"
echo ""
echo "=== saved to $LOG ==="
