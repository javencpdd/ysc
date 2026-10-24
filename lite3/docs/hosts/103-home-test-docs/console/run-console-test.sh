#!/usr/bin/env bash
# P1-3 试运行启动器：setsid 脱离 SSH 会话，自身 echo $$ 落 PID 再 exec，
# 保证 PID 文件里是 python3 的真实 PID（$! 会是 setsid 的 PID，坑见 2026-10-22 日志）。
set -u
cd /home/test/yolo8/console
echo $$ > /home/test/yolo8/logs/console-test.pid
exec /usr/bin/python3 -u server.py
