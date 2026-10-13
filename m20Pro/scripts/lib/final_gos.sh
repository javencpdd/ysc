#!/bin/bash
PW="'"
TARGET="10.21.31.104"
cat > /tmp/m20hw.sh <<'HWEOF'
echo "##### $(hostname) #####"
cat /proc/device-tree/model 2>/dev/null; echo
grep -E "model name|Hardware" /proc/cpuinfo | sort -u
echo "CPU parts: $(grep 'CPU part' /proc/cpuinfo | sort | uniq -c | tr '\n' ' ')"
echo "Mem: $(free -h | grep Mem | tr -s ' ')"
lsblk 2>/dev/null | head -4
echo "OS: $(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)  kernel $(uname -r)"
echo "GPU节点: $(ls /dev/mali0 2>/dev/null || echo 无) | DRI: $(ls /dev/dri 2>/dev/null | tr '\n' ' ')"
echo "NPU: $(ls /dev/rknpu 2>/dev/null || echo 未见) | misc: $(ls /sys/class/misc/ 2>/dev/null | grep -iE 'npu|rga|mali' | tr '\n' ' ')"
echo "modules: $(grep -iE 'npu|mali|mpp|rga|vpu|drm|cec' /proc/modules 2>/dev/null | awk '{print $1}' | tr '\n' ' ')"
ip -4 addr show | grep inet | grep -v "127.0.0.1" | awk '{print $NF, $2}'
echo "Mali容量/频率: $(cat /sys/class/misc/mali0/device/devfreq/*/cur_freq 2>/dev/null | head -2 | tr '\n' ' ')"
HWEOF
sshpass -p "$PW" ssh -F /dev/null -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o ConnectTimeout=10 -o LogLevel=ERROR "user@$TARGET" bash -s < /tmp/m20hw.sh
rm -f /tmp/m20hw.sh
