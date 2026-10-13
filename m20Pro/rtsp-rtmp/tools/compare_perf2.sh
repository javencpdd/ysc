#!/bin/bash
# 对比 m20video vs 3000端口服务 的资源占用（修正版：用 cgroup v1 cpuacct 计账）
WINDOW="${1:-20}"
HZ=100
NCPU=$(nproc --all)

# --- m20video 走 cgroup 计账（内核累加，最准）---
m20_cpu_ns()  { cat /sys/fs/cgroup/cpu,cpuacct/system.slice/m20video.service/cpuacct.usage 2>/dev/null; }
m20_mem()     { cat /sys/fs/cgroup/memory/system.slice/m20video.service/memory.usage_in_bytes 2>/dev/null; }
m20_npids()   { cat /sys/fs/cgroup/cpu,cpuacct/system.slice/m20video.service/cgroup.procs 2>/dev/null | wc -l; }
m20_ntasks()  { cat /sys/fs/cgroup/cpu,cpuacct/system.slice/m20video.service/tasks 2>/dev/null | wc -l; }

# --- 3000 端口服务走 /proc ---
p3000_pids() {
    local npid pp
    npid=$(ss -tlnp 2>/dev/null | grep ':3000' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u)
    pp=$(ps -o ppid= -p "$npid" 2>/dev/null | tr -d ' ')
    echo "$npid $pp" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u | tr '\n' ' '
}
jif()  { awk '{print $14+$15}' /proc/$1/stat 2>/dev/null; }
sum_jif() { local t=0 v; for p in $1; do v=$(jif $p); [ -n "$v" ] && t=$((t+v)); done; echo $t; }
sum_rss() { local t=0 v; for p in $1; do v=$(awk '/^VmRSS:/{print $2}' /proc/$p/status 2>/dev/null); [ -n "$v" ] && t=$((t+v)); done; echo $t; }
sum_thr() { ps -o nlwp= -p $(echo $1 | tr ' ' ',') 2>/dev/null | awk '{s+=$1} END{print s+0}'; }

sys_cpu_busy() {
    local a b
    a=$(awk '/^cpu /{i=$5+$6; t=0; for(k=2;k<=9;k++) t+=$k; print i,t}' /proc/stat)
    sleep "$WINDOW"
    b=$(awk '/^cpu /{i=$5+$6; t=0; for(k=2;k<=9;k++) t+=$k; print i,t}' /proc/stat)
    echo "$a $b" | awk '{printf "%.1f", (($4-$2)-($3-$1))/($4-$2)*100}'
}

report() {  # $1=名称 $2=CPU秒 $3=内存MB $4=进程数 $5=线程数 $6=系统CPU%
    awk -v n="$1" -v c="$2" -v m="$3" -v p="$4" -v th="$5" -v s="$6" -v nc="$NCPU" -v w="$WINDOW" \
      'BEGIN{
        printf "  %-26s CPU=%6.1f%%单核 (整机%5.1f%%, %.2f核)  内存=%7.1fMB  进程=%d 线程=%d  系统总线CPU=%s%%\n",
          n, c/w*100, c/w*100/nc, c/w, m, p, th, s;
      }'
}

echo "############ 阶段 1：仅 3000 端口服务 ############"
systemctl stop m20video.service 2>/dev/null; sleep 5
P3=$(p3000_pids)
t1=$(sum_jif "$P3"); r=$(sum_rss "$P3"); th=$(sum_thr "$P3"); sys=$(sys_cpu_busy); t2=$(sum_jif "$P3")
report "3000端口 (node+PM2)" "$(awk -v a=$t1 -v b=$t2 -v h=$HZ 'BEGIN{print (b-a)/h}')" \
       "$(awk -v r=$r 'BEGIN{print r/1024}')" "$(echo $P3|wc -w)" "$th" "$sys"

echo
echo "############ 阶段 2：m20video 启动 ############"
systemctl start m20video.service
sleep 30
u1=$(m20_cpu_ns); m1=$(m20_mem)
P3=$(p3000_pids); a=$(sum_jif "$P3"); r=$(sum_rss "$P3"); th=$(sum_thr "$P3")
sys=$(sys_cpu_busy)
u2=$(m20_cpu_ns); m2=$(m20_mem)
b=$(sum_jif "$P3")

report "3000端口 (node+PM2)" "$(awk -v a=$a -v b=$b -v h=$HZ 'BEGIN{print (b-a)/h}')" \
       "$(awk -v r=$r 'BEGIN{print r/1024}')" "$(echo $P3|wc -w)" "$th" "$sys"
report "m20video (两路推流)" "$(awk -v a=$u1 -v b=$u2 'BEGIN{print (b-a)/1000000000}')" \
       "$(awk -v m=$m2 'BEGIN{print m/1048576}')" "$(m20_npids)" "$(m20_ntasks)" "$sys"

echo
echo "############ 收尾：恢复默认关闭 ############"
systemctl stop m20video.service; sleep 3
echo -n "状态: "; systemctl is-active m20video.service
echo -n "自启: "; systemctl is-enabled m20video.service
echo -n "到目标连接: "; ss -tn 2>/dev/null | grep -c 172.31.68.227
