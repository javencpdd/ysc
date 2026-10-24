#!/usr/bin/env bash
set -u
PCLI=$(command -v playwright-cli)
TOKEN=$(bash "$(dirname "$0")/get-token.sh")
URL=http://127.0.0.1:8090
PROBE=$(tr '\n' ' ' < probe.js)
ev() { "$PCLI" eval "$1" 2>/dev/null | sed -n '/^### Result$/,/^### Ran Playwright code$/p' | sed '1d;$d'; }

"$PCLI" open "$URL" >/dev/null 2>&1
sleep 2
"$PCLI" fill e7 "$TOKEN" >/dev/null 2>&1
"$PCLI" click e8 >/dev/null 2>&1
sleep 4
echo "login ok, app hidden = $(ev "document.getElementById('app-view').hidden")"
echo "PID before = $(ev "document.querySelector('#card-rosbridge .kv').textContent.match(/PID(\d+)/)?.[1] || 'none'")"
echo "probe install = $(ev "$PROBE")"
echo "sampler alive = $(ev "String(!!window.__sampler)")"

ev "document.querySelector('#card-rosbridge button[data-act=restart]').click()"
sleep 1
echo "modal = $(ev "String(!!document.querySelector('.modal'))")  disabled(pre) = $(ev "document.querySelector('#card-rosbridge button[data-act=restart]').disabled")"
CLICK_MS=$(ev "window.__t0 = Date.now(); 'mark'")
ev "document.querySelector('.modal button.danger').click()"
echo ">>> danger clicked, sampling 14s..."
sleep 14
ev "clearInterval(window.__sampler)"
echo "--- fetch 日志 (相对安装探针 ms) ---"
ev "JSON.stringify(window.__fetchLog)"
echo "--- 采样时间线 (ms, disabled, inflight, toast) ---"
ev "JSON.stringify(window.__tl)"
echo "PID after = $(ev "document.querySelector('#card-rosbridge .kv').textContent.match(/PID(\d+)/)?.[1] || 'none'")"
"$PCLI" close >/dev/null 2>&1
