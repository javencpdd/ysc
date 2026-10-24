#!/usr/bin/env bash
# U27b/U30 失败项取证：浏览器内 100ms 采样 + fetch 包裹，重放 rosbridge 重启
set -u
PCLI=$(command -v playwright-cli)
TOKEN=$(bash "$(dirname "$0")/get-token.sh")
URL=http://127.0.0.1:8090
ev() { "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d'; }

echo "===== 打开并登录 ====="
"$PCLI" open "$URL" >/dev/null 2>&1
sleep 2
"$PCLI" fill e7 "$TOKEN" >/dev/null 2>&1
"$PCLI" click e8 >/dev/null 2>&1
sleep 4
echo "app-view hidden = $(ev "document.getElementById('app-view').hidden")"
echo "PID before = $(ev "document.querySelector('#card-rosbridge .kv').textContent.match(/PID(\d+)/)?.[1] || 'none'")"

echo "===== 安装探针（fetch 包裹 + 100ms 采样器） ====="
ev '
window.__fetchLog = [];
var of = window.fetch;
window.fetch = function(){
  var u = String(arguments[0]), t0 = Date.now();
  window.__fetchLog.push([t0, "START", u.slice(0, 60)]);
  return of.apply(this, arguments).then(function(r){
    window.__fetchLog.push([Date.now(), "END", u.slice(0, 60), r.status]);
    return r;
  }, function(e){
    window.__fetchLog.push([Date.now(), "ERR", u.slice(0, 60), String(e)]);
    throw e;
  });
};
window.__tl = [];
window.__t0 = Date.now();
window.__sampler = setInterval(function(){
  var b = document.querySelector("#card-rosbridge button[data-act=restart]");
  window.__tl.push([
    Date.now() - window.__t0,
    b ? String(b.disabled) : "NOBTN",
    (window.inflight && typeof window.inflight === "object") ? String(window.inflight["rosbridge"]) : "NOINFLIGHT",
    document.getElementById("toast").textContent.slice(0, 36)
  ]);
}, 100);
"probe installed"'
echo "probe = $(ev "String(!!window.__sampler)")"

echo "===== 点击重启 → 等确认框 ====="
ev "document.querySelector('#card-rosbridge button[data-act=restart]').click()"
sleep 1
echo "modal present = $(ev "String(!!document.querySelector('.modal'))")"
echo "disabled(pre-confirm) = $(ev "document.querySelector('#card-rosbridge button[data-act=restart]').disabled")"

echo "===== 点击确认（danger） ====="
CLICK_MS=$(ev "Date.now() - window.__t0")
ev "document.querySelector('.modal button.danger').click()"
echo "danger clicked at t0+${CLICK_MS}ms"

sleep 12

echo "===== 停止采样并读取 ====="
ev "clearInterval(window.__sampler); 'stopped'"
echo "--- fetch 日志（相对 t0，ms） ---"
ev "JSON.stringify(window.__fetchLog.map(function(x){return [x[0]-window.__t0, x[1], x[2], x[3]]}))"
echo "--- 按钮/飞行锁/toast 时间线（相对 t0，ms） ---"
ev "JSON.stringify(window.__tl)"
echo "--- 关键节点前后各 8 条采样 ---"
ev "JSON.stringify(window.__tl.filter(function(x){return Math.abs(x[0]-$CLICK_MS)<2500}))"
echo "PID after = $(ev "document.querySelector('#card-rosbridge .kv').textContent.match(/PID(\d+)/)?.[1] || 'none'")"
echo "kv now = $(ev "document.querySelector('#card-rosbridge .kv').textContent.replace(/\s+/g,' ').trim()")"

"$PCLI" close >/dev/null 2>&1
echo "===== 取证结束 ====="
