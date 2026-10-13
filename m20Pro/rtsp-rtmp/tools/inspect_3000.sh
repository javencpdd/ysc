#!/bin/bash
# 只读勘察：3000 端口服务（node /home/tank/m20/server.js）的托管与自启机制
export PM2_HOME=/root/.pm2

echo "=== 1. PM2 进程列表 ==="
pm2 list 2>&1 | head -20
echo

echo "=== 2. PM2 详情 ==="
pm2 describe 0 2>&1 | head -30
echo

echo "=== 3. PM2 自启单元 (systemd) ==="
systemctl list-unit-files 2>/dev/null | grep -i pm2 || echo "  (无 pm2 相关 unit)"
echo "--- pm2-root.service 状态 ---"
systemctl status pm2-root.service --no-pager 2>&1 | head -12
echo
echo "--- 是否有 enable 软链 ---"
ls -la /etc/systemd/system/multi-user.target.wants/ 2>/dev/null | grep -i pm2 || echo "  (multi-user.target.wants 下无 pm2)"
echo

echo "=== 4. PM2 dump（开机恢复用的进程清单）==="
ls -la /root/.pm2/dump.pm2 2>&1
echo "--- 内容摘要 ---"
grep -o '"name":"[^"]*"\|"script":"[^"]*"\|"cwd":"[^"]*"' /root/.pm2/dump.pm2 2>/dev/null | head -10
echo

echo "=== 5. 进程与端口 ==="
ss -tlnp 2>/dev/null | grep ':3000'
ps -eo pid,ppid,etime,cmd | grep -E 'PM2|server\.js' | grep -v grep
echo

echo "=== 6. 其它可能自启的途径 ==="
echo "--- /etc/rc.local ---"; [ -f /etc/rc.local ] && cat /etc/rc.local || echo "  (无)"
echo "--- root crontab ---"; crontab -l 2>&1 | head -5
echo "--- /etc/cron.d ---"; ls /etc/cron.d/ 2>&1
echo "--- 用户 user 的 crontab ---"; su - user -c "crontab -l 2>&1 | head -5" 2>/dev/null
echo

echo "=== 7. 服务文件与实际入口 ==="
cat /home/tank/m20/package.json 2>&1 | head -20
echo "--- config.json ---"
cat /home/tank/m20/config.json 2>&1
