#!/bin/bash
# 在 basic_server（ASDU 通信服务）中搜索错误码定义
BS=/opt/robot/share/basic_server
echo '=== basic_server 目录结构 ==='
ls -la $BS/ 2>/dev/null
echo
echo '=== bin ==='
ls -la $BS/bin/ 2>/dev/null
echo
echo '=== scripts ==='
ls $BS/scripts/ 2>/dev/null
cat $BS/scripts/run.sh 2>/dev/null
echo
echo '=== strings: 搜 8017 ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -iE '0x8017|8017' | head -20
echo
echo '=== strings: 搜 ErrorList/errorCode ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -iE 'ErrorList|errorCode|component' | head -30
echo
echo '=== strings: 搜 imu ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -i 'imu' | head -20
echo
echo '=== strings: 搜 encoder ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -i 'encoder' | head -20
echo
echo '=== 搜其他文件里的 8017（限文本） ==='
grep -rn '8017' /opt/robot/share/basic_server/ 2>/dev/null | head
grep -rln '8017' /opt/robot/include /opt/robot/lib 2>/dev/null | head
