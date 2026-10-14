#!/bin/bash
BS=/var/opt/robot/log/2026_1015/Basic_server.2026_1015.log
RL=/var/opt/robot/log/2026_1015/rl_deploy.2026_1015.log
echo '=== 1. Basic_server 日志文件信息 ==='
ls -la $BS; wc -l $BS
echo
echo '=== 2. 搜"恢复/正常/清除"类打印 ==='
grep -nE '恢复|正常|clear|清除|解除' $BS | head -30
echo
echo '=== 3. rl_deploy 今天所有安全状态/恢复相关 ==='
grep -nE '安全状态变更|恢复正常|恢复变化|安全异常恢复' $RL | tail -40
echo
echo '=== 4. rl_deploy 日志文件信息 ==='
ls -la $RL; wc -l $RL
echo
echo '=== 5. 最后 10 行 Basic_server（再确认一次尾部） ==='
tail -10 $BS
