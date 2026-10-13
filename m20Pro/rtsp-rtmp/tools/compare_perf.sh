#!/bin/bash
# 对比 m20video 与 3000 端口(node/PM2) 两套服务的资源占用
# 方法：/proc/PID/stat 的 utime+stime 增量 + VmRSS + 系统总 CPU

WINDOW="${1:-20}"          # 每个阶段的采样窗口(秒)
HZ=100

jif() { awk '{print $14+$15}' /proc/$1/stat 2>/dev/null; }

sum_jif() {   # 对一组 PID 求和
    local t=0
    for p in $1; do
        local v; v=$(jif $p)
        [ -n "$v" ] && t=$((t + v))
    done
    echo $t
}

sum_rss_kb() {
    local t=0
    for p in $1; do
        local v; v=$(awk '/^VmRSS:/{print $2}' /proc/$p/status 2>/dev/null)
        [ -n "$v" ] && t=$((t + v))
    done
    echo $t
}

cpu_busy_pct() {    # 系统总 CPU 利用率（两秒快照）
    local a b
    a=$(awk '/^cpu /{idle=$5+$6; tot=0; for(i=2;i<=9;i++) tot+=$i; print idle, tot}' /proc/stat)
    sleep 2
    b=$(awk '/^cpu /{idle=$5+$6; tot=0; for(i=2;i<=9;i++) tot+=$i; print idle, tot}' /proc/stat)
    echo "$a $b" | awk '{di=$3-$1; dt=$4-$2; printf "%.1f", (dt-di)/dt*100}'
}

port3000_pids() {
    local npid
    npid=$(ss -tlnp 2>/dev/null | grep ':3000' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u)
    local ppid_=$(ps -o ppid= -p "$npid" 2>/dev/null | tr -d ' ')
    echo "$npid $ppid_" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u | tr '\n' ' '
}

m20_pids() {
    local cg
    cg=$(systemctl show -p ControlGroup --value m20video.service 2>/dev/null)
    [ -n "$cg" ] && cat "/sys/fs/cgroup${cg}/cgroup.procs" 2>/dev/null | sort -u | tr '\n' ' '
}

measure() {
    local label="$1"
    local pids="$2"
    echo "──── $label ────"
    echo "  进程列表: $(echo $pids | tr ' ' ',')"
    local t1 t2
    t1=$(sum_jif "$pids")
    local rss=$(sum_rss_kb "$pids")
    local busy=$(cpu_busy_pct)
    t2=$(sum_jif "$pids")
    local ncpu=$(nproc --all)
    echo "  窗口: ${WINDOW}s   系统总CPU占用: ${busy}%"
    awk -v a="$t1" -v b="$t2" -v hz=$HZ -v w=$WINDOW -v n=$ncpu -v m="$rss" \
        'BEGIN{
            c=(b-a)/hz;
            printf "  该组CPU: %.1f%% 单核  (占整机 %.1f%%  / 约 %.2f 个核)\n", c/w*100, c/w*100/n, c/w;
            printf "  该组内存(RSS): %.1f MB\n", m/1024;
        }'
    echo "  进程数: $(echo $pids | wc -w)   线程数: $(ps -o nlwp= -p $(echo $pids | tr ' ' ',') 2>/dev/null | awk '{s+=$1} END{print s+0}')"
    echo
    sleep "$WINDOW"
}

echo "############ 阶段 1：只有 3000 端口服务在跑（m20video 停止）############"
systemctl stop m20video.service 2>/dev/null
sleep 5
P3=$(port3000_pids)
measure "3000端口服务 (node /home/tank/m20/server.js + PM2)" "$P3"

echo "############ 阶段 2：m20video 也启动 ############"
systemctl start m20video.service
sleep 25
P3=$(port3000_pids); PM=$(m20_pids)
measure "3000端口服务" "$P3"
measure "m20video 推流服务" "$PM"

echo "############ 收尾：恢复默认关闭 ############"
systemctl stop m20video.service
sleep 3
echo -n "m20video 状态: "; systemctl is-active m20video.service
echo -n "开机自启: "; systemctl is-enabled m20video.service
echo -n "到目标连接: "; ss -tn 2>/dev/null | grep -c 172.31.68.227
