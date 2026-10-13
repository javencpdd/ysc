#!/bin/bash
# 只读：用完整路径调用 pm2，导出应用的精确启动参数，供复原使用
export PM2_HOME=/root/.pm2
PM2=/root/.nvm/versions/node/v20.20.2/lib/node_modules/pm2/bin/pm2
NODE_BIN=/root/.nvm/versions/node/v20.20.2/bin

export PATH="$NODE_BIN:$PATH"

echo "=== PM2 版本与列表 ==="
$PM2 --version 2>&1
$PM2 list 2>&1 | head -20
echo

echo "=== 应用详情（完整）==="
$PM2 describe camera-rtsp-backend 2>&1 | head -45
echo

echo "=== 是否还有其它 PM2 应用 ==="
$PM2 jlist 2>/dev/null | tr ',' '\n' | grep -o '"name":"[^"]*"' | sort -u
echo

echo "=== dump.pm2 备份 ==="
cp -f /root/.pm2/dump.pm2 /root/.pm2/dump.pm2.bak-$(date +%Y%m%d-%H%M%S)
cp -f /root/.pm2/dump.pm2 /home/user/rtmp_1012/patch/dump.pm2.orig 2>/dev/null
ls -la /root/.pm2/dump.pm2*
echo

echo "=== dump 中的应用条目（原始 JSON 片段）==="
python3 - <<'PY'
import json
try:
    data = json.load(open('/root/.pm2/dump.pm2'))
    for app in data:
        keep = {k: app.get(k) for k in ('name','script','args','cwd','interpreter','exec_mode','instances','env','node_args','max_memory_restart')}
        print(json.dumps(keep, ensure_ascii=False, indent=2)[:1500])
        print('---')
except Exception as e:
    print('解析失败:', e)
PY
