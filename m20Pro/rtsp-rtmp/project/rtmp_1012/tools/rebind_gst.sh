#!/bin/bash
# rebind_gst.sh —— 在线迁移 gst 进程全部线程的 CPU 亲和性（不改脚本、可逆）
# 用法: rebind_gst.sh <PID> <cpu_list>
PID="$1"; CPUS="$2"
[ -z "$PID" ] || [ -z "$CPUS" ] && { echo "用法: $0 <PID> <cpu_list>"; exit 1; }
n=$(ls -d /proc/$PID/task/* 2>/dev/null | wc -l)
for t in /proc/$PID/task/*; do
  taskset -pc "$CPUS" "$(basename "$t")" >/dev/null 2>&1
done
echo "PID $PID: $n 个线程已迁至 cpu[$CPUS]"
grep Cpus_allowed_list /proc/$PID/status
