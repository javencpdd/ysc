#!/bin/bash
# 从 server.js 提取 M20 直连协议（TCP 30001）的报文格式与命令字
S=/home/tank/m20/server.js
echo "############ 1. 报文/帧结构相关 ############"
grep -oE '.{70}(Items|Command|HEADER|header|magic|MAGIC|0x[0-9a-fA-F]{4}).{130}' "$S" | head -20
echo
echo "############ 2. send/request 构造 ############"
grep -oE '.{60}(_send|sendCmd|writeFrame|_write|buildMsg|_build|JSON\.stringify).{160}' "$S" | head -14
echo
echo "############ 3. GPS 提取逻辑 ############"
grep -oE '.{140}extractGpsFromMessage.{260}' "$S" | head -4
echo
echo "############ 4. 命令码常量（成组数字）############"
grep -oE 'Command[:=][^,;}]{1,40}' "$S" | sort -u | head -20
echo
echo "############ 5. RobotClient 建连与心跳 ############"
grep -oE '.{60}(_heartbeatTimer|heartbeat|createConnection).{200}' "$S" | head -6
echo
echo "############ 6. 消息中的 GPS 字段名 ############"
grep -oE 'Items\.GPS[^;]{0,300}' "$S" | head -3
echo
echo "############ 7. 是否有中文协议说明字符串 ############"
strings -a "$S" 2>/dev/null | grep -E '纬度|经度|海拔|航向|定位|卫星' | head -12
