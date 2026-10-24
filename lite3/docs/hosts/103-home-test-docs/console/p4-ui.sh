#!/usr/bin/env bash
# P4 前端真机核对（playwright 单进程，PC 上跑）：
#   bash console/p4-ui.sh
# 覆盖：模型卡渲染 / 当前 engine 信息 / 导出历史（含"当前"标记）/ 徽标墙
#       / 上传与启用按钮初态 / 类别清单区默认隐藏。
set -u
# 计划书 §1248：Chromium 会读 env 代理，PC 上跑必须显式清空
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
PCLI=$(command -v playwright-cli)
TOKEN=$(bash "$(dirname "$0")/get-token.sh")
URL=http://192.168.1.103:8090
PASS=0; FAIL=0

ck(){ if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1)); else echo "FAIL  $1 期望 $2 实际 $3"; FAIL=$((FAIL+1)); fi; }
# ev 只收单个表达式（多语句静默不执行）；结果带双引号，用 evs 剥
ev(){ "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d'; }
evs(){ ev "$1" | sed 's/^"//; s/"$//; s/\\"/"/g'; }

echo "===== 0. 打开并登录 ====="
"$PCLI" open "$URL" >/dev/null 2>&1
sleep 2
# 单表达式：填 token 并点登录（避免依赖 eNN 引用编号）
ev "(function(){var i=document.getElementById('token-input');i.value='$TOKEN';document.getElementById('login-btn').click();return 1})()" >/dev/null
sleep 5
ck "登录成功（主界面可见）" "false" "$(ev "document.getElementById('app-view').hidden")"

echo "===== 1. 模型卡渲染 ====="
ck "卡片存在且可见" "false" "$(ev "document.getElementById('card-model').hidden")"
ck "kv 为 4 组键值" "4" "$(ev "document.getElementById('model-kv').children.length/2")"
ck "当前 engine 显示 arm.engine" "true" \
  "$(ev "document.getElementById('model-kv').textContent.indexOf('yolov8n_arm.engine')>=0")"
ck "tag 显示类别数" "true" \
  "$(ev "/[0-9]+ 类/.test(document.getElementById('model-tag').textContent)")"
ck "kv 含 worker 行" "true" \
  "$(ev "document.getElementById('model-kv').textContent.indexOf('worker')>=0")"

echo "===== 2. 导出历史 ====="
ROWS=$(ev "document.querySelectorAll('#model-exports .model-row').length")
if [ "${ROWS:-0}" -gt 0 ] 2>/dev/null; then
  echo "PASS  导出记录 $ROWS 条"; PASS=$((PASS+1))
  ck "行内显示 engine 文件名" "true" \
    "$(ev "/\\.engine/.test(document.getElementById('model-exports').textContent)")"
  ck "每行有启用按钮" "$ROWS" "$(ev "document.querySelectorAll('#model-exports .model-row button').length")"
else
  # 不是回归：exports 可能被「存储清理」清空（P5 的 purge 或手工清理），
  # 导出历史本来就该允许为空。断言只约束"有记录时的行格式"。
  echo "SKIP  导出记录为空（exports 已被清空，非回归；有记录时才会校验行格式）"
fi

echo "===== 3. 徽标墙 / 按钮初态 ====="
ck "徽标墙含 engine" "true" "$(ev "document.getElementById('badges').textContent.indexOf('engine')>=0")"
ck "上传按钮初始禁用" "true" "$(ev "document.getElementById('model-upload').disabled")"
ck "启用按钮可用" "false" "$(ev "document.getElementById('model-reload').disabled")"
ck "类别清单区默认隐藏" "true" "$(ev "document.getElementById('model-names-box').hidden")"
ck "进度区默认隐藏" "true" "$(ev "document.getElementById('model-progress-box').hidden")"
ck "workspace 默认 1024" "1024" "$(evs "document.getElementById('model-ws').value")"

echo "===== 4. 截图存档 ====="
"$PCLI" screenshot >/dev/null 2>&1 && echo "PASS  截图已保存" && PASS=$((PASS+1)) || echo "SKIP  截图（命令不可用）"

printf '\nRESULT PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
