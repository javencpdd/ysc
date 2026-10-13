echo "=== HOST/OS ==="; hostname; cat /etc/os-release 2>/dev/null | head -4; cat /proc/version
echo; echo "=== CPU ==="; lscpu 2>/dev/null
echo "--- cpuinfo关键字段 ---"; grep -m2 -E "model name|Hardware|CPU part|CPU implementer" /proc/cpuinfo
echo; echo "=== MEM ==="; free -h
echo; echo "=== DISK ==="; lsblk 2>/dev/null; df -h 2>/dev/null | grep -vE "tmpfs|udev" | head -8
echo; echo "=== GPU/DRI ==="; ls -l /dev/dri 2>/dev/null || echo "no /dev/dri"; ls /sys/class/drm/ 2>/dev/null
ls -l /dev/mali0 2>/dev/null || echo "no /dev/mali0"; ls /sys/class/misc/ 2>/dev/null | head -25
echo; echo "=== 关键驱动模块 ==="; lsmod 2>/dev/null | grep -iE "mali|npu|mpp|rga|vpu|drm|gpu" || echo "lsmod无匹配或无权限"
echo; echo "=== NPU ==="; ls /sys/kernel/debug/rknpu 2>/dev/null || echo "no rknpu debugfs"; ls -d /dev/rknpu 2>/dev/null || echo "no /dev/rknpu"
echo; echo "=== NET ==="; ip -4 addr show | grep -E "inet"; echo "--- routes ---"; ip route | head -12
echo; echo "=== 板型信息 ==="; cat /proc/device-tree/model 2>/dev/null; echo; cat /proc/cmdline 2>/dev/null
