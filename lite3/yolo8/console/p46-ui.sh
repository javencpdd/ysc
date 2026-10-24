#!/usr/bin/env bash
# P4.6 可用性改造 前端真机核对（playwright 单进程，PC 上跑）：
#   bash console/p46-ui.sh
# 覆盖：卡片折叠骨架 / 折叠交互 / 全部折叠·展开 / 折叠后摘要可见
#       / 占用占比条 / 开关控件 / 留存策略内联编辑 / 快速设置内联编辑
#       / 内嵌块折叠 / 折叠状态记忆（刷新后保持）/ 原有元素回归。
set -u
# 计划书 §1248：Chromium 会读 env 代理，PC 上跑必须显式清空
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
PCLI=$(command -v playwright-cli)
TOKEN=$(bash "$(dirname "$0")/get-token.sh")
URL=http://192.168.1.103:8090
PASS=0; FAIL=0

ck(){ if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1)); else echo "FAIL  $1 期望 [$2] 实际 [$3]"; FAIL=$((FAIL+1)); fi; }
# ev 只收单个表达式（多语句静默不执行）；结果带双引号，用 evs 剥
ev(){ "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d'; }
evs(){ ev "$1" | sed 's/^"//; s/"$//; s/\\"/"/g'; }

echo "===== 0. 打开并登录 ====="
"$PCLI" open "$URL" >/dev/null 2>&1
sleep 2
ev "(function(){var i=document.getElementById('token-input');i.value='$TOKEN';document.getElementById('login-btn').click();return 1})()" >/dev/null
sleep 5
ck "登录成功（主界面可见）" "false" "$(ev "document.getElementById('app-view').hidden")"

echo "===== 0.5 P4.7：首访默认折叠归一化 ====="
# P4.7 起「配置与维护」三张重卡首次访问默认折叠（首屏只留监控）。
# 本脚本后面要测"点一下就折叠"，所以先把状态归一化为全展开。
ev "(function(){['card-config','card-model','card-storage'].forEach(function(id){var c=document.getElementById(id);if(c&&c.className.indexOf('collapsed')>=0){c.className=c.className.replace(/\s*collapsed/g,'');}});return 1})()" >/dev/null
sleep 1

echo "===== 1. 卡片折叠骨架 ====="
ck "卡片总数 = 8" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card').length")"
ck "折叠头数量 = 卡片数" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card > .card-head').length")"
ck "每卡都有 card-body" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card > .card-body').length")"
ck "每卡都有折叠箭头" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card > .card-head > .card-arrow').length")"
ck "每卡都有摘要位" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card > .card-head > .card-summary').length")"

echo "===== 2. 折叠交互（点标题栏）====="
ev "(function(){document.querySelector('#card-storage > .card-head').click();return 1})()" >/dev/null
sleep 1
ck "点击后 storage 折叠" "true" "$(ev "document.getElementById('card-storage').className.indexOf('collapsed') >= 0")"
ck "折叠后 body 高度为 0" "0" "$(ev "document.querySelector('#card-storage > .card-body').offsetHeight")"
ev "(function(){document.querySelector('#card-storage > .card-head').click();return 1})()" >/dev/null
sleep 1
ck "再点可展开" "false" "$(ev "document.getElementById('card-storage').className.indexOf('collapsed') >= 0")"
ck "展开后 body 有高度" "true" "$(ev "document.querySelector('#card-storage > .card-body').offsetHeight > 0")"

echo "===== 3. 全部折叠 / 全部展开 ====="
ev "(function(){document.getElementById('toggle-all-btn').click();return 1})()" >/dev/null
sleep 1
ck "按钮文案切到 全部展开" "全部展开" "$(evs "document.getElementById('toggle-all-btn').textContent")"
ck "八张卡全部折叠" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card.collapsed').length")"
ev "(function(){document.getElementById('toggle-all-btn').click();return 1})()" >/dev/null
sleep 1
ck "按钮文案切回 全部折叠" "全部折叠" "$(evs "document.getElementById('toggle-all-btn').textContent")"
ck "八张卡全部展开" "0" "$(ev "document.querySelectorAll('#app-view .grid > .card.collapsed').length")"

echo "===== 4. 折叠后仍看得到结论（摘要）====="
ck "storage 摘要非空（含合计）" "true" "$(ev "/合计/.test(document.getElementById('sum-card-storage').textContent||'')")"
ck "yolo 摘要含运行/未运行" "true" "$(ev "/运行|未运行/.test(document.getElementById('sum-card-yolo').textContent||'')")"

echo "===== 5. 占用占比条 ====="
ck "占比条容器已显示" "false" "$(ev "document.getElementById('storage-usage').hidden")"
ck "占比行 = 5 类" "5" "$(ev "document.querySelectorAll('#storage-usage .usage-row').length")"
ck "填充块 = 5" "5" "$(ev "document.querySelectorAll('#storage-usage .usage-fill').length")"
ck "填充块有宽度" "true" "$(ev "parseFloat(document.querySelector('#storage-usage .usage-fill').style.width) > 0")"

echo "===== 6. 开关控件（替代裸 checkbox）====="
ck "switch 数量 >= 5" "true" "$(ev "document.querySelectorAll('.switch').length >= 5")"
ck "计时缓存开关仍是 checkbox 语义" "true" "$(ev "document.getElementById('st-keep-cache').checked")"
# 开关只是"选项"，不是清空范围 ⇒ 它不该影响清空按钮的可用态
ev "(function(){var u=document.getElementById('st-uploads');u.checked=true;u.dispatchEvent(new Event('change'));return 1})()" >/dev/null
sleep 1
ck "勾选一个范围后清空按钮启用" "false" "$(ev "document.getElementById('storage-purge').disabled")"
ev "(function(){var c=document.getElementById('st-keep-cache');c.checked=false;c.dispatchEvent(new Event('change'));return 1})()" >/dev/null
sleep 1
ck "切计时缓存开关不影响清空按钮" "false" "$(ev "document.getElementById('storage-purge').disabled")"
ck "开关视觉上已切到关闭" "false" "$(ev "document.getElementById('st-keep-cache').checked")"
ev "(function(){var c=document.getElementById('st-keep-cache');c.checked=true;c.dispatchEvent(new Event('change'));var u=document.getElementById('st-uploads');u.checked=false;u.dispatchEvent(new Event('change'));return 1})()" >/dev/null
sleep 1
ck "取消范围后清空按钮禁用" "true" "$(ev "document.getElementById('storage-purge').disabled")"

echo "===== 7. 留存策略内联编辑（改了不重启 yolo）====="
ck "总量上限已回填" "2048" "$(evs "document.getElementById('rt-max-mb').value")"
ck "留存天数已回填" "30" "$(evs "document.getElementById('rt-keep-days').value")"
ck "回收站天数已回填" "7" "$(evs "document.getElementById('rt-trash-days').value")"
ck "检查间隔已回填" "600" "$(evs "document.getElementById('rt-interval').value")"
ck "初始保存按钮禁用" "true" "$(ev "document.getElementById('rt-save').disabled")"
ck "初始无脏标记" "true" "$(ev "document.getElementById('rt-dirty').hidden")"
ev "(function(){var n=document.getElementById('rt-keep-days');n.value=45;n.dispatchEvent(new Event('input'));return 1})()" >/dev/null
sleep 1
ck "改值后保存按钮启用" "false" "$(ev "document.getElementById('rt-save').disabled")"
ck "脏标记显示" "false" "$(ev "document.getElementById('rt-dirty').hidden")"
ck "卡片摘要提示未保存" "true" "$(ev "/未保存/.test(document.getElementById('sum-card-storage').textContent||'')")"
ev "(function(){document.getElementById('rt-revert').click();return 1})()" >/dev/null
sleep 1
ck "还原后按钮禁用" "true" "$(ev "document.getElementById('rt-save').disabled")"
ck "还原后值恢复" "30" "$(evs "document.getElementById('rt-keep-days').value")"

echo "===== 8. 快速设置内联编辑（改了会重启 yolo）====="
ck "阈值数字框已回填" "0.4" "$(evs "document.getElementById('qc-conf-num').value")"
ck "阈值滑块已回填" "0.4" "$(evs "document.getElementById('qc-conf-range').value")"
ck "推流地址已回填" "true" "$(ev "(document.getElementById('qc-rtmp-url').value||'').indexOf('rtmp://') === 0")"
ck "抓拍开关已回填" "true" "$(ev "document.getElementById('qc-snap').checked")"
ck "初始保存禁用" "true" "$(ev "document.getElementById('qc-save').disabled")"
ev "(function(){var r=document.getElementById('qc-conf-range');r.value=0.6;r.dispatchEvent(new Event('input'));return 1})()" >/dev/null
sleep 1
ck "拖滑块 → 数字框联动" "0.6" "$(evs "document.getElementById('qc-conf-num').value")"
ck "改值后保存启用" "false" "$(ev "document.getElementById('qc-save').disabled")"
ev "(function(){document.getElementById('qc-revert').click();return 1})()" >/dev/null
sleep 1
ck "还原后禁用" "true" "$(ev "document.getElementById('qc-save').disabled")"
ck "还原后阈值回到 0.4" "0.4" "$(evs "document.getElementById('qc-conf-num').value")"

echo "===== 9. 内嵌块可折叠 ====="
ck "icfg 块 = 2" "2" "$(ev "document.querySelectorAll('.icfg').length")"
ev "(function(){document.querySelector('#retention-box .icfg-head').click();return 1})()" >/dev/null
sleep 1
ck "留存块可折叠" "true" "$(ev "document.getElementById('retention-box').className.indexOf('collapsed') >= 0")"
ev "(function(){document.querySelector('#retention-box .icfg-head').click();return 1})()" >/dev/null
sleep 1
ck "留存块可再展开" "false" "$(ev "document.getElementById('retention-box').className.indexOf('collapsed') >= 0")"

echo "===== 10. 折叠状态记忆（刷新后保持）====="
ev "(function(){document.querySelector('#card-pics > .card-head').click();return 1})()" >/dev/null
sleep 1
"$PCLI" reload >/dev/null 2>&1
sleep 6
ck "刷新后 pics 仍折叠" "true" "$(ev "document.getElementById('card-pics').className.indexOf('collapsed') >= 0")"
ev "(function(){if(document.getElementById('card-pics').className.indexOf('collapsed')>=0){document.querySelector('#card-pics > .card-head').click();}return 1})()" >/dev/null
sleep 1
ck "已还原 pics 为展开" "false" "$(ev "document.getElementById('card-pics').className.indexOf('collapsed') >= 0")"

echo "===== 11. 回归：原有关键元素仍在 ====="
ck "五类清空勾选框仍在" "5" "$(ev "document.querySelectorAll('#storage-targets input[type=checkbox]').length")"
ck "编辑配置按钮仍在" "false" "$(ev "document.getElementById('cfg-edit-btn').hidden")"
ck "抓拍时间轴仍在" "true" "$(ev "!!document.getElementById('pics-slider')")"
ck "模型导出进度条仍在" "true" "$(ev "!!document.getElementById('model-progress-bar')")"
ck "日志目标下拉仍在" "true" "$(ev "!!document.getElementById('log-target')")"

echo ""
echo "RESULT PASS=$PASS FAIL=$FAIL"
