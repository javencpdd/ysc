echo "##### $(hostname) #####"
cat /proc/device-tree/model 2>/dev/null; echo
grep -E "model name|Hardware" /proc/cpuinfo | sort -u
echo "CPU parts: $(grep 'CPU part' /proc/cpuinfo | sort | uniq -c | tr '\n' ' ')"
echo "Mem: $(free -h | grep Mem | tr -s ' ')"
lsblk 2>/dev/null | head -4
echo "OS: $(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)  kernel $(uname -r)"
echo "GPU节点: $(ls /dev/mali0 2>/dev/null || echo 无) | DRI: $(ls /dev/dri 2>/dev/null | tr '\n' ' ')"
echo "NPU: $(ls /dev/rknpu 2>/dev/null || ls /sys/class/misc/ 2>/dev/null | grep -i npu || echo 未见) | RGA: $(ls /sys/class/misc/ 2>/dev/null | grep -i rga || echo 无)"
ip -4 addr show | grep inet | grep -v "127.0.0.1" | awk '{print $NF, $2}'
echo
