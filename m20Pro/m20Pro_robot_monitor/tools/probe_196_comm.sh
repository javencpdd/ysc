#!/bin/bash
# 探查 196(AOS) 运控通信进程与端口 —— 用于追溯 ASDU 消息（1002/x）的发送方
echo '=== 30000/25000/26000 端口 ==='
netstat -tunlp 2>/dev/null | grep -E ':30000|:25000|:26000'
echo
echo '=== ./run 5 1 (PID 1959) ==='
ls -l /proc/1959/cwd /proc/1959/exe 2>/dev/null
tr '\0' ' ' < /proc/1959/cmdline 2>/dev/null
echo
echo '=== 全部 UDP 监听 ==='
netstat -tunlp 2>/dev/null | grep -w udp | head -40
echo
echo '=== rte_checker ==='
ls /opt/robot/share/rte_checker/ 2>/dev/null
ls /opt/robot/share/rte_checker/bin/ 2>/dev/null | head
cat /opt/robot/share/rte_checker/scripts/run.sh 2>/dev/null
