#!/usr/bin/env bash
# 打印当前访问令牌（测试脚本的唯一取令牌入口）。
#
# 令牌来源：103 主机的 config/yolo8.json → console.token。
# 双平台：本机就是 103 时直接读文件（历史上曾无条件 ssh 回自己，
# 103 无自身公钥时报 Permission denied，2026-10-22 修复）；在 PC 上
# 跑则 ssh 过去读（静态路由直连 ysc@192.168.1.103）。
set -u
CFG=/home/test/yolo8/config/yolo8.json
if [ -r "$CFG" ]; then
  python3 -c "import json;print(json.load(open('$CFG'))['console']['token'])"
else
  exec ssh -o ConnectTimeout=8 ysc@192.168.1.103 \
    "python3 -c \"import json;print(json.load(open('/home/test/yolo8/config/yolo8.json'))['console']['token'])\""
fi
