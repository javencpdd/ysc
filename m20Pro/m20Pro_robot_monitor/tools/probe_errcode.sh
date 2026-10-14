#!/bin/bash
# 在 basic_server 变更日志与全盘中搜索错误码起源
BS=/opt/robot/share/basic_server
echo '=== change_log.md 中 imu/error/8017 相关行 ==='
grep -n -iE 'imu|error|8017|错误|异常' $BS/change_log.md | head -80
echo
echo '=== change_log.md 开头 60 行 ==='
head -60 $BS/change_log.md
echo
echo '=== conf 目录 ==='
find $BS/conf/ -type f 2>/dev/null | head -30
echo
echo '=== 全盘搜中文错误码关键词（可能命中错误码表所在文件） ==='
grep -rln '编码器无值' /opt/robot/ 2>/dev/null | head -10
echo '---'
grep -rln '电机温度预警' /opt/robot/ 2>/dev/null | head -10
echo '---'
grep -rln '低电量预警' /opt/robot/ 2>/dev/null | head -10
echo
echo '=== 搜 0x8016 文本出现 ==='
grep -rn '0x8016' /opt/robot/ 2>/dev/null | head -10
echo
echo '=== IDL / hpp 候选 ==='
find /opt/robot -name '*.idl' 2>/dev/null | head -20
find /opt/robot -name '*.hpp' 2>/dev/null | head -30
