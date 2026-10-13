PW="'"
TARGET="10.21.31.104"
cat > /tmp/m20gpu.sh <<'HWEOF'
echo "##### $(hostname) GPU细节 #####"
echo "--- mali device目录 ---"; ls /sys/class/misc/mali0/device/ 2>/dev/null
echo "--- uevent ---"; cat /sys/class/misc/mali0/device/uevent 2>/dev/null
echo "--- devfreq频率档 ---"; cat /sys/class/misc/mali0/device/devfreq/*/available_frequencies 2>/dev/null; echo "cur: $(cat /sys/class/misc/mali0/device/devfreq/*/cur_freq 2>/dev/null)"; echo "governor: $(cat /sys/class/misc/mali0/device/devfreq/*/governor 2>/dev/null)"
echo "--- dmesg mali ---"; dmesg 2>/dev/null | grep -i mali | head -5 || echo "dmesg无权限"
echo "--- 大小核对 ---"; grep -E "processor|model name|CPU part" /proc/cpuinfo | head -12
echo "--- RK编解码VPU ---"; ls /dev/mpp_service /dev/rga /dev/dri/renderD129 2>/dev/null; ls /sys/class/misc/ | grep -iE "mpp|hevc|vpu|rga"
echo "--- docker容器 ---"; docker ps --format "{{.Names}}: {{.Image}}" 2>/dev/null | head -15 || echo "docker无权限"
echo "--- CPU隔离 ---"; cat /proc/cmdline | tr ' ' '\n' | grep -E "isolcpus|maxcpus"
HWEOF
sshpass -p "$PW" ssh -F /dev/null -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o ConnectTimeout=10 -o LogLevel=ERROR "user@$TARGET" bash -s < /tmp/m20gpu.sh
rm -f /tmp/m20gpu.sh
