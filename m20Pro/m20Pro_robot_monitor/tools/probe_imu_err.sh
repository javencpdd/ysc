#!/bin/bash
# 精读 change_log 相关段落 + 搜索 IMU 超时错误码具体值
BS=/opt/robot/share/basic_server
echo '=== change_log.md 行 370-445（IMU 超时错误码上下文，含版本号） ==='
sed -n '370,445p' $BS/change_log.md
echo
echo '=== authority_code.toml ==='
cat $BS/conf/authority_code.toml 2>/dev/null | head -60
echo
echo '=== strings 搜 timeout / 超时 ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -iE 'timeout' | head -40
echo
echo '=== strings 搜中文 超时 ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -E '超时' | head -40
echo
echo '=== strings 搜 IMU 相关日志格式串 ==='
strings -a $BS/bin/basic_server 2>/dev/null | grep -E 'IMU|imu' | grep -vE '^_Z|^N[0-9]|PubSub|SubListener|PubListener|DDS' | head -40
