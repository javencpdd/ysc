#!/bin/bash
# experiment_affinity.sh —— video2 绑核 × USB 中断亲和性 对照实验
# 只迁移运行态亲和性，不改脚本、不改设备；结束自动恢复原布局
set -u
find_v2() { pgrep -f 'dev/video2' | head -1; }
rebind() {  # $1=pid $2=cpus
  for t in /proc/$1/task/*; do taskset -pc "$2" "$(basename "$t")" >/dev/null 2>&1; done
}
set_irq() {  # $1=cpus
  echo "$1" > /proc/irq/122/smp_affinity_list 2>/dev/null \
    && echo "  irq122 -> cpu[$1] (effective=$(cat /proc/irq/122/effective_affinity_list))" \
    || echo "  irq122 设置失败"
}
m() { bash /tmp/measure_two.sh video2 "$1"; }

V2=$(find_v2)
echo "=== 目标进程: video2 gst PID=$V2 ==="
[ -z "$V2" ] && { echo "找不到 video2 采集进程"; exit 1; }

echo ""
echo "--- [1] 基线：gst=cpu6-7, irq122=cpu6 ---"
grep Cpus_allowed_list /proc/$V2/status | sed 's/^/  /'
echo -n "  irq122 effective="; cat /proc/irq/122/effective_affinity_list
m 15

echo ""
echo "--- [2] gst 迁至 cpu4-5（与 video1 同核组，避开 irq122） ---"
rebind "$V2" 4-5
sleep 3
m 15

echo ""
echo "--- [3] gst 迁至 cpu0-3（小核组，大核全留给另一路） ---"
rebind "$V2" 0-3
sleep 3
m 15

echo ""
echo "--- [4] gst 回 cpu6-7，irq122 改到 cpu0-2（中断/编码彻底分核） ---"
rebind "$V2" 6-7
set_irq 0-2
sleep 3
m 15

echo ""
echo "--- [5] 恢复：irq122=cpu6, gst=cpu6-7 ---"
set_irq 6
rebind "$V2" 6-7
sleep 2
echo "  已恢复。"
