#!/bin/bash
# rl_deploy 深挖（只读）：符号表 / SDK 字符串 / 日志历史 / 配置文件
RL=/opt/robot/share/rl_deploy/bin/rl_deploy

echo "===== [1] rl_deploy 符号: sdk 相关 ====="
nm "$RL" 2>/dev/null | grep -iE "sdk" | head -80
echo "(symbol count: $(nm "$RL" 2>/dev/null | wc -l))"

echo "===== [2] rl_deploy 符号: steer/State 相关 ====="
nm "$RL" 2>/dev/null | grep -iE "steer" | head -40
nm "$RL" 2>/dev/null | grep -iE "State" | grep -iE "Control|Sdk|Steer|Normal|Idle|Joint" | head -40

echo "===== [3] rl_deploy strings: 话题名 ====="
strings -n 5 "$RL" 2>/dev/null | grep -E "^/(REAL_STEER|STEER|HANDLE_STEER|SDK|JOINTS|joints|MOTION)" | sort -u | head -40

echo "===== [4] rl_deploy strings: SDK 业务串（滤掉模板噪声） ====="
strings -n 6 "$RL" 2>/dev/null | grep -iE "sdk" | grep -vE "std::|__|allocator|template|_Bind|_Head_base|_M_|allocated|make_shared|make_unique|destroy<|construct<|enable_shared|_Function|_invoke|_Mu<|_S_|forward<|move<|get<|tuple|conditional|_Weak|_Sp_" | sort -u | head -80

echo "===== [5] rl_deploy conf 目录 ====="
ls -la /opt/robot/share/rl_deploy/conf/ 2>/dev/null
echo "--- SDK_authority_code.toml 前 30 行 ---"
head -30 /opt/robot/share/rl_deploy/conf/SDK_authority_code.toml 2>/dev/null
echo "--- cmd_vel_limit.yml ---"
cat /opt/robot/share/rl_deploy/conf/cmd_vel_limit.yml 2>/dev/null

echo "===== [6] rl_deploy 日志: Sdk/Steer 历史（全部日志目录） ====="
grep -rhiE "sdk|steer" /var/opt/robot/log/ 2>/dev/null | grep -iE "rl_deploy|sdk|steer" | sort -u | tail -50

echo "===== [7] rl_deploy change_log 全文 ====="
cat /opt/robot/share/rl_deploy/change_log.md 2>/dev/null | head -100

echo "===== [8] basic_server authority_code.toml ====="
head -20 /opt/robot/share/basic_server/conf/authority_code.toml 2>/dev/null

echo "===== [9] rl_deploy 顶层目录 ====="
ls -la /opt/robot/share/rl_deploy/ 2>/dev/null

echo "===== done ====="
