#!/usr/bin/env bash
# P1-3 浏览器级 UI 验收（计划书 §7：必须 playwright 真机核对）
# 全部步骤在单进程内完成：playwright-cli 的浏览器会话跨 Bash 调用会被回收。
# token 从 103 的 config/yolo8.json 读取（配置驱动，2026-10-22 起），不出现在命令行明文里。
set -u
PCLI=$(command -v playwright-cli)
TOKEN=$(bash "$(dirname "$0")/get-token.sh")
# 2026-10-22 P1.5：srcbind-relay 后台任务已被用户取消，127.0.0.1:8090 中继不再可用。
# 改直连 192.168.1.103:8090：PC 经静态路由 → 120 SNAT，console 视角来源 IP 恒为
# 192.168.1.120 ∈ 白名单（实测 healthz 200）。附带好处：accept 的 H 段锁的是
# 192.168.1.103，与本路径的来源 IP 不同，浏览器登录不受锁影响。
URL=http://192.168.1.103:8090
PASS=0; FAIL=0
ck() { # $1 名称  $2 期望  $3 实际
  if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1));
  else echo "FAIL  $1  期望 $2 实际 $3"; FAIL=$((FAIL+1)); fi
}
ev() { "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d'; }
evs() { # 字符串结果：再去掉 playwright-cli 输出的外层引号
  "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d' | sed 's/^"//; s/"$//; s/\\"/"/g'
}

echo "===== 1. 打开登录页 ====="
"$PCLI" open "$URL" >/dev/null 2>&1
sleep 2
ck "U1 登录表单渲染"     "true" "$(ev "!!document.getElementById('token-input')")"
ck "U2 主界面初始隐藏"   "true"  "$(ev "document.getElementById('app-view').hidden")"

echo "===== 2. 填 token 登录 ====="
"$PCLI" fill e7 "$TOKEN" >/dev/null 2>&1
"$PCLI" click e8 >/dev/null 2>&1
sleep 4
ck "U3 登录后主界面显示"  "false" "$(ev "document.getElementById('app-view').hidden")"
ck "U4 登录页已隐藏"      "true"  "$(ev "document.getElementById('login-view').hidden")"
ck "U5 token 存入 sessionStorage" "${#TOKEN}" "$(ev "(sessionStorage.getItem('yolo8_console_token')||'').length")"

echo "===== 3. 徽标墙渲染 ====="
sleep 2
N=$(ev "document.querySelectorAll('#badges .badge').length")
if [ "$N" -ge 8 ] 2>/dev/null; then echo "PASS  U6 徽标墙 >=8 个（实际 $N）"; PASS=$((PASS+1)); else echo "FAIL  U6 徽标墙数量（实际 $N）"; FAIL=$((FAIL+1)); fi
ck "U7 徽标含 yolo 项"   "true" "$(ev "[...document.querySelectorAll('#badges .badge .k')].some(e=>e.textContent==='yolo')")"
ck "U8 徽标含白名单"     "true" "$(ev "[...document.querySelectorAll('#badges .badge .k')].some(e=>e.textContent==='白名单')")"
ck "U9 徽标含 console 版本" "true" "$(ev "[...document.querySelectorAll('#badges .badge .v')].some(e=>e.textContent.includes('2.1.0-p3'))")"
ck "U10 负载徽标非占位"  "true" "$(ev "[...document.querySelectorAll('#badges .badge .v')].some(e=>/^[0-9]/.test(e.textContent))")"
echo "--- 徽标墙文本 ---"
ev "document.getElementById('badges').textContent.replace(/\s+/g,' ').trim()"

echo "===== 4. 服务卡片渲染 ====="
ck "U11 yolo 卡片 kv 有 4+ 行" "true" "$(ev "document.querySelectorAll('#yolo-kv .k').length>=4")"
ck "U12 yolo 托管模式=已安装未启用" "true" "$(ev "document.getElementById('yolo-kv').textContent.includes('已安装未启用')")"
ck "U13 yolo 日志尾非空"    "true" "$(ev "!document.getElementById('yolo-logtail').textContent.includes('（无日志）')")"
ck "U14 rosbridge 卡片有按钮 x3" "3" "$(ev "document.querySelectorAll('#card-rosbridge button[data-act]').length")"
ck "U15 按钮未被禁用（未在飞行）" "false" "$(ev "document.querySelector('#card-rosbridge button[data-act=restart]').disabled")"

echo "===== 5. 配置树渲染（只读） ====="
sleep 2
R=$(ev "document.querySelectorAll('#cfgtree .row').length")
if [ "$R" -ge 30 ] 2>/dev/null; then echo "PASS  U16 配置树 >=30 行（实际 $R）"; PASS=$((PASS+1)); else echo "FAIL  U16 配置树行数（实际 $R）"; FAIL=$((FAIL+1)); fi
ck "U17 配置含 stream.rtmp_url" "true" "$(ev "document.getElementById('cfgtree').textContent.includes('rtmp://172.31.68.227')")"
ck "U18 配置含 console.port"   "true" "$(ev "document.getElementById('cfgtree').textContent.includes('8090')")"
ck "U19 配置来源标注"          "true" "$(ev "document.getElementById('cfg-src').textContent.includes('config/yolo8.json')")"
ck "U20 配置无编辑输入框（P1 只读）" "0" "$(ev "document.querySelectorAll('#cfgtree input').length")"

echo "===== 6. 日志渲染 ====="
L=$(ev "document.querySelectorAll('#logbox .ln').length")
if [ "$L" -ge 5 ] 2>/dev/null; then echo "PASS  U21 日志行 >=5（实际 $L）"; PASS=$((PASS+1)); else echo "FAIL  U21 日志行数（实际 $L）"; FAIL=$((FAIL+1)); fi
ck "U22 日志无 HTML 注入（纯文本）" "true" "$(ev "document.getElementById('logbox').children.length===document.getElementById('logbox').querySelectorAll('.ln').length")"
ck "U23 日志目标默认为 yolo"      '"yolo"' "$(ev "document.getElementById('log-target').value")"

echo "===== 7. 危险操作二次确认 + 重启 rosbridge ====="
# 前置：rosbridge 必须原本在运行，否则 U36「PID 已变更」无从验证
# （2026-10-22 P3 回归实测：停机状态下进第 7 节，U36 必 FAIL——是测试前提不成立，
# 不是产品缺陷。start 无危险确认，直接点。）
if [ "$(ev "document.querySelector('#card-rosbridge .kv').textContent.includes('运行中')")" != "true" ]; then
  echo "rosbridge 未运行，先 start（确保重启验证前提）"
  ev "document.querySelector('#card-rosbridge button[data-act=start]').click()" >/dev/null
  ev "new Promise(function(res){ var t0 = Date.now(); (function poll(){ if (document.querySelector('#card-rosbridge .kv').textContent.includes('运行中') || Date.now()-t0>20000) return res(1); setTimeout(poll, 300); })(); })" >/dev/null
fi
PID_BEFORE=$(ev "document.querySelector('#card-rosbridge .kv').textContent.match(/PID(\\d+)/)?.[1] || 'none'")
echo "重启前 rosbridge PID: $PID_BEFORE"
ev "document.querySelector('#card-rosbridge button[data-act=restart]').click()"
sleep 1
ck "U24 点击重启弹出确认框"  "true" "$(ev "!!document.querySelector('.modal')")"
ck "U25 确认框标题含服务名"  "true" "$(ev "document.querySelector('.modal h3').textContent.includes('rosbridge')")"
ck "U26 确认框警告冷启动"    "true" "$(ev "document.querySelector('.modal p').textContent.includes('35s')")"
# 确认前不应禁用（动作尚未开始）
ck "U27 确认前按钮未禁用"    "false" "$(ev "document.querySelector('#card-rosbridge button[data-act=restart]').disabled")"
# ★关键时序段必须整体在浏览器内完成：实测 playwright-cli 单次调用墙钟开销 2~9s（本机
# 负载高时更差，见 ui-forensic 实验 D：相邻两次调用间隔 9064ms / 5853ms），而 restart
# POST 往返约 4s、toast 只活 3.2s——任何"点完→shell sleep→再 eval"的拆步，测量点都
# 整体落在窗口之后（v3/v4 共四个 FAIL 均此因；产品行为经 100ms 探针取证完全正确：
# 禁用窗口=整个 POST 期间，toast 准时出现并存活 3.2s）。
# 单次 eval 内完成：装 toast 观察器 → 点确认 → 600ms 读飞行禁用 → 9s 内收 toast → 收尾读恢复态。
PID_BEFORE=${PID_BEFORE//\"/}
RESTART_RET=$(evs "new Promise(function(res){ var out = {}, seen = 'no'; var mo = new MutationObserver(function(){ if (document.getElementById('toast').textContent.indexOf('完成') >= 0) seen = 'yes'; }); mo.observe(document.getElementById('toast'), {childList: true, characterData: true, subtree: true}); var t0 = Date.now(); document.querySelector('.modal button.danger').click(); setTimeout(function(){ out.disabledAt600 = String(document.querySelector('#card-rosbridge button[data-act=restart]').disabled); out.inflightAt600 = String(window.inflight.rosbridge); }, 600); setTimeout(function(){ mo.disconnect(); out.toast = seen; out.disabledAtEnd = String(document.querySelector('#card-rosbridge button[data-act=restart]').disabled); out.elapsed = Date.now() - t0; res(JSON.stringify(out)); }, 9000); })")
echo "重启时序采样（单次 eval 内）: $RESTART_RET"
ck "U27b 确认后按钮进入飞行禁用" "true"  "$(echo "$RESTART_RET" | sed -n 's/.*"disabledAt600":"\([a-z]*\)".*/\1/p')"
ck "U30 toast 提示完成"      "yes"   "$(echo "$RESTART_RET" | sed -n 's/.*"toast":"\([a-z]*\)".*/\1/p')"
ck "U28 重启后按钮恢复可用"  "false" "$(echo "$RESTART_RET" | sed -n 's/.*"disabledAtEnd":"\([a-z]*\)".*/\1/p')"
ck "U29 rosbridge 变为运行中" "true" "$(ev "document.querySelector('#card-rosbridge .kv').textContent.includes('运行中')")"
# PID 变更同样浏览器内轮询等刷新（kv 由 1s tick 刷新，CLI 拆步会读到旧值）
PID_AFTER=$(evs "new Promise(function(res){ var before = '$PID_BEFORE'; var t0 = Date.now(); (function poll(){ var kv = document.querySelector('#card-rosbridge .kv').textContent; var m = kv.match(/PID(\\d+)/); if (kv.indexOf('运行中') >= 0 && m && m[1] !== before) return res(m[1]); if (Date.now() - t0 > 15000) return res(m ? m[1] : 'none'); setTimeout(poll, 200); })(); })")
echo "重启后 rosbridge PID: $PID_AFTER"
if [ "$PID_BEFORE" != "none" ] && [ "$PID_AFTER" != "none" ] && [ "$PID_BEFORE" != "$PID_AFTER" ]; then
  echo "PASS  U36 PID 已变更（$PID_BEFORE -> $PID_AFTER，确认真重启）"; PASS=$((PASS+1))
else
  echo "FAIL  U36 PID 未变更（$PID_BEFORE -> $PID_AFTER）"; FAIL=$((FAIL+1))
fi
echo "--- rosbridge 卡片状态 ---"
ev "document.querySelector('#card-rosbridge .kv').textContent.replace(/\s+/g,' ').trim()"

echo "===== 8. 取消路径（不应执行动作） ====="
ev "document.querySelector('#card-rosbridge button[data-act=stop]').click()"
sleep 1
ev "document.querySelector('.modal .actions button:not(.danger)').click()"
sleep 2
ck "U31 取消后服务仍运行"    "true" "$(ev "document.querySelector('#card-rosbridge .kv').textContent.includes('运行中')")"
ck "U32 弹层已关闭"          "false" "$(ev "!!document.querySelector('.modal')")"

echo "===== 9. 退出登录 ====="
ev "document.getElementById('logout-btn').click()"
sleep 2
ck "U33 退出后回到登录页"    "false" "$(ev "document.getElementById('login-view').hidden")"
ck "U34 退出后主界面隐藏"    "true"  "$(ev "document.getElementById('app-view').hidden")"
ck "U35 sessionStorage 已清" "0" "$(ev "(sessionStorage.getItem('yolo8_console_token')||'').length")"

echo "===== 10. 截图留档 ====="
"$PCLI" open "$URL" >/dev/null 2>&1; sleep 1
"$PCLI" screenshot --filename=p1-console-login.png >/dev/null 2>&1
echo "截图: p1-console-login.png"
"$PCLI" close >/dev/null 2>&1

echo ""
echo "===== UI 验收汇总: PASS=$PASS FAIL=$FAIL ====="
[ "$FAIL" -eq 0 ] && echo "浏览器级 UI 验收全部通过" || echo "UI 验收存在失败项"
