#!/bin/bash
# exp_layout_c.sh —— 布局 C 验证：video1=6-7(大核独占) / video2=0-3 / irq122=4-5(专职中断)
set -u
V1=$(pgrep -f 'dev/video0' | head -1)
V2=$(pgrep -f 'dev/video2' | head -1)
rebind() { for t in /proc/$1/task/*; do taskset -pc "$2" "$(basename "$t")" >/dev/null 2>&1; done; }

echo "=== 布局 C 实验 (V1=$V1 V2=$V2) ==="
echo "--- 改前 ---"
grep Cpus_allowed_list /proc/$V1/status | sed 's/^/  v1 /'
grep Cpus_allowed_list /proc/$V2/status | sed 's/^/  v2 /'
echo -n "  irq122="; cat /proc/irq/122/effective_affinity_list

rebind "$V1" 6-7
echo "5" > /proc/irq/122/smp_affinity_list 2>/dev/null
echo "--- 改后 ---"
grep Cpus_allowed_list /proc/$V1/status | sed 's/^/  v1 /'
grep Cpus_allowed_list /proc/$V2/status | sed 's/^/  v2 /'
echo -n "  irq122="; cat /proc/irq/122/effective_affinity_list
sleep 4
echo "--- 测量 ---"
bash /tmp/measure_two.sh both 25

echo "--- 恢复：v1=4-5, irq122=6 ---"
rebind "$V1" 4-5
echo "6" > /proc/irq/122/smp_affinity_list 2>/dev/null
grep Cpus_allowed_list /proc/$V1/status | sed 's/^/  v1 /'
echo -n "  irq122="; cat /proc/irq/122/effective_affinity_list
