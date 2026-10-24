#!/usr/bin/env bash
# P5 前端真机核对（playwright 单进程，PC 上跑）：
#   bash console/p5-ui.sh
# 覆盖：存储清理卡渲染 / 五类占用 + 合计 / 留存策略显示 / 清空按钮初态
#       / 勾选后才可用 / 计时缓存保护默认勾选 / 提示文案。
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
ev "(function(){var i=document.getElementById('token-input');i.value='$TOKEN';document.getElementById('login-btn').click();return 1})()" >/dev/null
sleep 5
ck "登录成功（主界面可见）" "false" "$(ev "document.getElementById('app-view').hidden")"

echo "===== 1. 存储清理卡渲染 ====="
ck "卡片存在且可见" "false" "$(ev "document.getElementById('card-storage').hidden")"
ROWS=$(ev "document.getElementById('storage-list').querySelectorAll('.kv').length")
ck "占用行 = 5 类 + 合计" "6" "$ROWS"
ck "含抓拍图片行" "true" \
  "$(ev "document.getElementById('storage-list').textContent.indexOf('抓拍图片')>=0")"
ck "含回收站行" "true" \
  "$(ev "document.getElementById('storage-list').textContent.indexOf('回收站')>=0")"
ck "含合计行" "true" \
  "$(ev "document.getElementById('storage-list').textContent.indexOf('合计')>=0")"

echo "===== 2. 留存策略显示 ====="
ck "pic_keep_days 显示 30" "30" "$(evs "document.getElementById('st-conf-days').textContent")"
ck "pic_max_mb 显示 2048" "2048" "$(evs "document.getElementById('st-conf-mb').textContent")"
ck "trash_keep_days 显示 7" "7" "$(evs "document.getElementById('st-conf-trash').textContent")"
ck "prune_interval_s 显示 600" "600" "$(evs "document.getElementById('st-conf-interval').textContent")"

echo "===== 3. 清空交互初态 ====="
ck "清空按钮初始禁用" "true" "$(ev "document.getElementById('storage-purge').disabled")"
ck "计时缓存保护默认勾选" "true" "$(ev "document.getElementById('st-keep-cache').checked")"
ck "五个范围勾选框都在" "5" "$(ev "document.querySelectorAll('#storage-targets input[type=checkbox]').length")"
# 勾一个 → 按钮应启用（单表达式：勾选 + 派发 change + 读结果）
ck "勾选后按钮启用" "false" \
  "$(ev "(function(){var e=document.getElementById('st-uploads');e.checked=true;e.dispatchEvent(new Event('change'));return document.getElementById('storage-purge').disabled})()")"
# 取消勾选 → 回到禁用
ck "取消勾选后按钮禁用" "true" \
  "$(ev "(function(){var e=document.getElementById('st-uploads');e.checked=false;e.dispatchEvent(new Event('change'));return document.getElementById('storage-purge').disabled})()")"

echo "===== 4. 提示文案 ====="
ck "提示提到计时缓存" "true" \
  "$(ev "document.getElementById('storage-hint').hidden===false && document.getElementById('storage-hint').textContent.indexOf('计时缓存')>=0")"

echo "===== 5. 截图存档 ====="
"$PCLI" screenshot >/dev/null 2>&1 && echo "PASS  截图已保存" && PASS=$((PASS+1)) || echo "SKIP  截图（命令不可用）"

printf '\nRESULT PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
