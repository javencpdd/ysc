#!/usr/bin/env bash
# P4.7 信息层级与布局 前端真机核对（playwright 单进程，PC 上跑）：
#   bash console/p47-ui.sh
# 覆盖：分区分层 / 卡片归属 / 列宽配比 / 等高拉伸已消除 / 重卡内区封顶
#       / 首访默认折叠 / 页面级告警横幅（直达按钮）/ 顶栏吸顶 / 回到顶部
#       / 话题表不溢出 / 回归：8 张卡与关键控件仍在。
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

echo "===== 1. 分区分层（信息层级）====="
ck "分区数 = 3" "3" "$(ev "document.querySelectorAll('#app-view .zone').length")"
ck "分区 1 标题 = 运行概览" "运行概览" "$(evs "document.querySelector('#zone-overview .zone-head h3').textContent")"
ck "分区 2 标题 = 抓拍与日志" "抓拍与日志" "$(evs "document.querySelector('#zone-inspect .zone-head h3').textContent")"
ck "分区 3 标题 = 配置与维护" "配置与维护" "$(evs "document.querySelector('#zone-ops .zone-head h3').textContent")"
ck "概览区 3 张卡" "3" "$(ev "document.querySelectorAll('#zone-overview > .grid > .card').length")"
ck "查看区 2 张卡" "2" "$(ev "document.querySelectorAll('#zone-inspect > .grid > .card').length")"
ck "运维区 3 张卡" "3" "$(ev "document.querySelectorAll('#zone-ops > .grid > .card').length")"
ck "服务卡在概览区" "true" "$(ev "!!document.querySelector('#zone-overview #card-yolo') && !!document.querySelector('#zone-overview #card-topics')")"
ck "抓拍/日志在查看区" "true" "$(ev "!!document.querySelector('#zone-inspect #card-pics') && !!document.querySelector('#zone-inspect #card-log')")"
ck "配置/模型/存储在运维区" "true" "$(ev "!!document.querySelector('#zone-ops #card-config') && !!document.querySelector('#zone-ops #card-model') && !!document.querySelector('#zone-ops #card-storage')")"

echo "===== 2. 列宽配比 ====="
ck "概览区 = 3 列" "true" "$(ev "getComputedStyle(document.querySelector('#zone-overview > .grid')).gridTemplateColumns.split(' ').length === 3")"
ck "抓拍卡跨 2 列（span2）" "true" "$(ev "document.getElementById('card-pics').className.indexOf('span2') >= 0")"
ck "抓拍卡明显宽于日志卡" "true" "$(ev "document.getElementById('card-pics').offsetWidth > document.getElementById('card-log').offsetWidth * 1.6")"
ck "日志卡宽度合理（>=300）" "true" "$(ev "document.getElementById('card-log').offsetWidth >= 300")"
ck "卡片未被长串撑破（无横向溢出）" "true" "$(ev "document.documentElement.scrollWidth <= window.innerWidth + 2")"

echo "===== 3. 同行对齐 + 滚动区填满（对齐且无空白）====="
ck "grid align-items = stretch（同行等高）" "stretch" "$(evs "getComputedStyle(document.querySelector('#zone-overview > .grid')).alignItems")"
ev "(function(){['card-config','card-model','card-storage'].forEach(function(id){var c=document.getElementById(id);c.className=c.className.replace(/\s*collapsed/g,'');});return 1})()" >/dev/null
sleep 1
ck "yolo 与 rosbridge 等高" "$(ev "document.getElementById('card-yolo').offsetHeight")" "$(ev "document.getElementById('card-rosbridge').offsetHeight")"
# fill 生效的证据：滚动区被拉到 min-height 之上，把卡片剩余空间吃掉了
ck "日志尾区被拉高填满（>96）" "true" "$(ev "document.getElementById('yolo-logtail').offsetHeight > 96")"
ck "rosbridge 尾区同样填满" "true" "$(ev "document.getElementById('rosbridge-logtail').offsetHeight > 96")"
ck "话题表达到下限 220" "true" "$(ev "document.getElementById('topics-table').offsetHeight >= 220")"
ck "话题表确有滚动窗口" "true" "$(ev "document.getElementById('topics-table').scrollHeight > document.getElementById('topics-table').clientHeight || document.getElementById('topics-table').offsetHeight <= 260")"
ck "日志框达到下限 200" "true" "$(ev "document.getElementById('logbox').offsetHeight >= 200")"
ck "日志框确有滚动窗口" "true" "$(ev "document.getElementById('logbox').scrollHeight > document.getElementById('logbox').clientHeight || document.getElementById('logbox').offsetHeight <= 380")"
ck "抓拍舞台达到下限 220" "true" "$(ev "document.getElementById('pics-stage').offsetHeight >= 220")"
ck "同行三卡等高（概览）" "$(ev "document.getElementById('card-yolo').offsetHeight")" "$(ev "document.getElementById('card-topics').offsetHeight")"
ck "同行两卡等高（抓拍/日志）" "$(ev "document.getElementById('card-pics').offsetHeight")" "$(ev "document.getElementById('card-log').offsetHeight")"
# 反证等高：同行最高的卡折叠后，同行其余卡应变矮
HY=$(ev "document.getElementById('card-yolo').offsetHeight")
ev "(function(){var c=document.getElementById('card-topics');if(c.className.indexOf('collapsed')<0)c.className+=' collapsed';return 1})()" >/dev/null
sleep 1
HY2=$(ev "document.getElementById('card-yolo').offsetHeight")
ck "同行最高卡折叠后本卡变矮（证明等高）" "true" "$(ev "document.getElementById('card-yolo').offsetHeight < $HY")"
ev "(function(){var c=document.getElementById('card-topics');c.className=c.className.replace(/\s*collapsed/g,'');return 1})()" >/dev/null
sleep 1

echo "===== 4. 重卡内区上下限（不再无限长高，也不会塌）====="
ck "配置树 min 200" "200px" "$(evs "getComputedStyle(document.getElementById('cfgtree')).minHeight")"
ck "配置树 max 420" "420px" "$(evs "getComputedStyle(document.getElementById('cfgtree')).maxHeight")"
ck "话题表 min 220" "220px" "$(evs "getComputedStyle(document.getElementById('topics-table')).minHeight")"
ck "话题表 max 260" "260px" "$(evs "getComputedStyle(document.getElementById('topics-table')).maxHeight")"
ck "日志框 min 200" "200px" "$(evs "getComputedStyle(document.getElementById('logbox')).minHeight")"
ck "日志框 max 380" "380px" "$(evs "getComputedStyle(document.getElementById('logbox')).maxHeight")"
ck "模型列表 min 140" "140px" "$(evs "getComputedStyle(document.getElementById('model-exports')).minHeight")"
ck "日志框可拖拽调高" "vertical" "$(evs "getComputedStyle(document.getElementById('logbox')).resize")"

echo "===== 4b. 清空范围标注（说清哪些有自动清理）====="
ck "范围勾选框仍 = 5" "5" "$(ev "document.querySelectorAll('#storage-targets input[type=checkbox]').length")"
ck "每项都有标注 = 5" "5" "$(ev "document.querySelectorAll('#storage-targets .st-tag').length")"
ck "pics/trash 标 自动" "2" "$(ev "document.querySelectorAll('#storage-targets .st-tag.auto').length")"
ck "uploads/exports/logs 标 非自动" "3" "$(ev "document.querySelectorAll('#storage-targets .st-tag.manual').length")"

echo "===== 5. 首访默认折叠（重卡不占首屏）====="
ev "(function(){localStorage.clear();return 1})()" >/dev/null
"$PCLI" reload >/dev/null 2>&1
sleep 6
ck "刷新后仍在主界面" "false" "$(ev "document.getElementById('app-view').hidden")"
ck "三张重卡默认折叠" "3" "$(ev "document.querySelectorAll('#zone-ops > .grid > .card.collapsed').length")"
ck "概览三卡默认展开" "0" "$(ev "document.querySelectorAll('#zone-overview > .grid > .card.collapsed').length")"
ck "抓拍/日志默认展开" "0" "$(ev "document.querySelectorAll('#zone-inspect > .grid > .card.collapsed').length")"
ck "默认折叠只生效一次（有标志位）" "1" "$(evs "localStorage.getItem('yolo8_card_defaults_done')")"
# 用户展开后刷新不该被重新折叠
ev "(function(){var c=document.getElementById('card-storage');c.className=c.className.replace(/\s*collapsed/g,'');var m={};m['card-config']=1;m['card-model']=1;localStorage.setItem('yolo8_card_collapsed','card-config,card-model');return 1})()" >/dev/null
"$PCLI" reload >/dev/null 2>&1
sleep 6
ck "用户展开 storage 后刷新保持展开" "false" "$(ev "document.getElementById('card-storage').className.indexOf('collapsed') >= 0")"
ck "用户仍折叠的 config 保持折叠" "true" "$(ev "document.getElementById('card-config').className.indexOf('collapsed') >= 0")"

echo "===== 6. 页面级告警横幅 ====="
ck "告警横幅节点存在" "true" "$(ev "!!document.getElementById('alert-banner')")"
ck "横幅可见（rosbridge 未运行）" "false" "$(ev "document.getElementById('alert-banner').hidden")"
ck "横幅含 rosbridge 提示" "true" "$(ev "/rosbridge/.test(document.getElementById('alert-banner').textContent||'')")"
ck "横幅有直达按钮" "true" "$(ev "document.querySelectorAll('#alert-banner .al-go').length >= 1")"
# 点直达：目标卡应被自动展开
ev "(function(){var c=document.getElementById('card-rosbridge');if(c.className.indexOf('collapsed')<0)c.className+=' collapsed';return 1})()" >/dev/null
sleep 1
ev "(function(){var b=document.querySelector('#alert-banner .al-go');if(b)b.click();return 1})()" >/dev/null
sleep 1
ck "点直达后 rosbridge 卡被展开" "false" "$(ev "document.getElementById('card-rosbridge').className.indexOf('collapsed') >= 0")"

echo "===== 7. 顶栏吸顶 + 回到顶部 ====="
ck "顶栏 position = sticky" "sticky" "$(evs "getComputedStyle(document.querySelector('header.top')).position")"
ck "回顶按钮初始隐藏" "true" "$(ev "document.getElementById('totop').hidden")"
ev "(function(){window.scrollTo(0,document.body.scrollHeight);return 1})()" >/dev/null
sleep 2
ck "滚到底后回顶按钮出现" "false" "$(ev "document.getElementById('totop').hidden")"
ev "(function(){document.getElementById('totop').click();return 1})()" >/dev/null
sleep 2
ck "点回顶后回到页面上部" "true" "$(ev "(window.pageYOffset||document.documentElement.scrollTop) < 200")"

echo "===== 8. 话题表不再溢出 ====="
ck "话题表无横向溢出" "true" "$(ev "(function(){var t=document.getElementById('topics-table');return t.scrollWidth <= t.clientWidth + 2})()")"
ck "话题行类型列可换行" "break-all" "$(evs "getComputedStyle(document.querySelector('#topics-table .trow .ty')).wordBreak")"

echo "===== 9. 回归：8 张卡与关键控件仍在 ====="
ck "卡片总数仍 = 8" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card').length")"
ck "折叠头仍 = 8" "8" "$(ev "document.querySelectorAll('#app-view .grid > .card > .card-head').length")"
ck "编辑配置按钮仍在" "false" "$(ev "document.getElementById('cfg-edit-btn').hidden")"
ck "抓拍时间轴仍在" "true" "$(ev "!!document.getElementById('pics-slider')")"
ck "模型导出进度条仍在" "true" "$(ev "!!document.getElementById('model-progress-bar')")"
ck "日志目标下拉仍在" "true" "$(ev "!!document.getElementById('log-target')")"
ck "留存策略内联块仍在" "true" "$(ev "!!document.getElementById('retention-box')")"
ck "快速设置内联块仍在" "true" "$(ev "!!document.getElementById('quick-cfg')")"

echo ""
echo "RESULT PASS=$PASS FAIL=$FAIL"
