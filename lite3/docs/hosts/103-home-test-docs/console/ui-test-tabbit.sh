#!/usr/bin/env bash
# P1-3 浏览器级 UI 验收 — tabbit-cli 版（2026-10-22 起主用，37 项）
# 相对 playwright-cli 版（ui-test.sh，已 37/37 通过）的三个决定性优势：
#   1. 单次调用墙钟 ~0.3s（pw-cli 实测 2~9s）——时序断言不再被 CLI 开销吞掉窗口
#      （pw-cli 版 U27b/U30 四个 FAIL 全是此因，被迫把时序段塞进单次 eval）
#   2. 任务/页面跨 Bash 调用持久保持（pw-cli 浏览器会话会被回收，逼着单脚本跑完）
#   3. 多行程序 + top-level await/return（pw-cli 把表达式包成 () => (EXPR)，
#      多语句直接语法错误——ui-forensic 探针连装三次才定位到）
# tabbit 特有坑（2026-10-22 实踩，均已在本脚本内规避）：
#   A. nodejs 程序跑在常驻控制器进程里，**不继承调用方 shell 的 env**
#      （process.env.YOLO8_TOKEN 读到 undefined，page.fill 直接报错）→ 动态值
#      （token/PID）一律写临时文件、程序内 require("fs") 读取。
#   B. CLI 对重复 request-id **静默返回缓存 receipt、不重跑**；计数器放 $(...) 子
#      shell 里不持久会导致父子调用交错碰撞（整轮 29 个假 FAIL）→ rid 用纳秒+
#      随机数，val 内校验回执 id 一致性。
#   C. python - <<EOF 会让 heredoc 占掉 stdin，管道里的 CLI 输出永远读不到
#      （整轮 __PARSE_FAIL__）→ val 必须用 -c 传程序。
#   D. 等待类操作一律 try/catch 包裹让程序返回状态而非失败（失败程序的副作用
#      不可控，且 receipt 里没有 value 可供断言）。
set -u
TC="/c/Users/19046/AppData/Local/Tabbit/LocalAgent/bin/tabbit-cli.exe"
PY="/c/Users/19046/.workbuddy/binaries/python/versions/3.13.12/python.exe"
TASK="yolo8-console-p1"
TMPW="C:/Users/19046/AppData/Local/Temp"   # 控制器可见的 Windows 风格临时目录
PASS=0; FAIL=0
ck() { # $1 名称  $2 期望  $3 实际
  if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1));
  else echo "FAIL  $1  期望 $2 实际 $3"; FAIL=$((FAIL+1)); fi
}
tj() { # $1 = nodejs 程序全文；stdin 传给 CLI
  RID="r$(date +%s%N)$RANDOM"
  printf '%s' "$RID" > "${TMPDIR:-/tmp}/.tj_rid.$$"
  printf '%s\n' "$1" | "$TC" nodejs --task "$TASK" --request-id "$RID"
}
val() { # 提取 result.value：标量原样打印，对象打印 JSON；校验回执 id 防静默串味
  "$PY" -c '
import json,sys
want=sys.argv[1] if len(sys.argv)>1 else ""
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    print("__PARSE_FAIL__"); raise SystemExit
r=d.get("result") or {}
got=r.get("requestId") or d.get("requestId") or ""
if want and got and got!=want:
    print("__RID_MISMATCH__:%s!=%s"%(got,want)); raise SystemExit
if d.get("status")!="succeeded" or "value" not in r:
    print("__ERR__:"+str(r.get("error") or d.get("error") or "unknown")[:160]); raise SystemExit
v=r["value"]
print(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False))
' "$(cat "${TMPDIR:-/tmp}/.tj_rid.$$" 2>/dev/null || echo '')"
}
jget() { "$PY" -c 'import json,sys; print(json.loads(sys.stdin.read())["'"$1"'"])'; }
where() { # 页面状态诊断：URL + 关键 id 是否存在 + taskId
  tj 'return {url: page.url(), dom: await page.evaluate(() => ["token-input","app-view","badges","yolo-kv","card-rosbridge"].map(i => i + "=" + !!document.getElementById(i)))};' | val
}

echo "===== 0. 环境预检（diagnose） ====="
if "$TC" diagnose >/dev/null 2>&1; then
  echo "PASS  D1 tabbit 控制器在线"; PASS=$((PASS+1))
else
  echo "FAIL  D1 tabbit 控制器不在线"; FAIL=$((FAIL+1)); echo "汇总: PASS=$PASS FAIL=$FAIL"; exit 1
fi

echo "===== 1. 打开登录页 ====="
bash "$(dirname "$0")/get-token.sh" > "${TMPDIR:-/tmp}/yolo8-ui-token"   # 供程序内 fs 读取
TOKLEN=$(tr -d '\n' < "${TMPDIR:-/tmp}/yolo8-ui-token" | wc -c | tr -d ' ')
echo "goto 结果: $(tj 'await page.goto("http://127.0.0.1:8090/", {waitUntil: "domcontentloaded"}); return {url: page.url(), title: await page.title()};' | val)"
ck "U1 登录表单渲染"     "true" "$(tj 'return await page.evaluate(() => !!document.getElementById("token-input"));' | val)"
ck "U2 主界面初始隐藏"   "true"  "$(tj 'return await page.evaluate(() => document.getElementById("app-view").hidden);' | val)"

echo "===== 2. 填 token 登录 ====="
echo "登录结果: $(tj 'const fs = require("fs");
const token = fs.readFileSync("'"$TMPW"'/yolo8-ui-token", "utf8").trim();
await page.fill("#token-input", token);
await page.click("#login-btn");
var logged = true;
try { await page.waitForFunction(() => !document.getElementById("app-view").hidden, null, {timeout: 10000}); } catch (e) { logged = false; }
return {logged: logged, err: await page.evaluate(() => document.getElementById("login-err").textContent)};' | val)"
ck "U3 登录后主界面显示"  "false" "$(tj 'return await page.evaluate(() => document.getElementById("app-view").hidden);' | val)"
ck "U4 登录页已隐藏"      "true"  "$(tj 'return await page.evaluate(() => document.getElementById("login-view").hidden);' | val)"
ck "U5 token 存入 sessionStorage" "$TOKLEN" "$(tj 'return await page.evaluate(() => (sessionStorage.getItem("yolo8_console_token")||"").length);' | val)"

echo "===== 3. 徽标墙渲染 ====="
echo "徽标等待: $(tj 'var ok = true;
try { await page.waitForFunction(() => document.querySelectorAll("#badges .badge").length >= 8, null, {timeout: 10000}); } catch (e) { ok = false; }
return {ok: ok, n: await page.evaluate(() => document.querySelectorAll("#badges .badge").length)};' | val)"
N6=$(tj 'return await page.evaluate(() => document.querySelectorAll("#badges .badge").length);' | val)
if [ "$N6" -ge 8 ] 2>/dev/null; then echo "PASS  U6 徽标墙 >=8 个（实际 $N6）"; PASS=$((PASS+1)); else echo "FAIL  U6 徽标墙数量（实际 $N6）"; FAIL=$((FAIL+1)); fi
ck "U7 徽标含 yolo 项"   "true" "$(tj 'return await page.evaluate(() => [...document.querySelectorAll("#badges .badge .k")].some(e => e.textContent === "yolo"));' | val)"
ck "U8 徽标含白名单"     "true" "$(tj 'return await page.evaluate(() => [...document.querySelectorAll("#badges .badge .k")].some(e => e.textContent === "白名单"));' | val)"
ck "U9 徽标含 console 版本" "true" "$(tj 'return await page.evaluate(() => [...document.querySelectorAll("#badges .badge .v")].some(e => e.textContent.includes("2.1.0-p1")));' | val)"
ck "U10 负载徽标非占位"  "true" "$(tj 'return await page.evaluate(() => [...document.querySelectorAll("#badges .badge .v")].some(e => /^[0-9]/.test(e.textContent)));' | val)"
echo "--- 徽标墙文本 ---"
tj 'return await page.evaluate(() => document.getElementById("badges").textContent.replace(/\s+/g, " ").trim());' | val

echo "===== 4. 服务卡片渲染 ====="
ck "U11 yolo 卡片 kv 有 4+ 行" "true" "$(tj 'return await page.evaluate(() => document.querySelectorAll("#yolo-kv .k").length >= 4);' | val)"
ck "U12 yolo 托管模式=已安装未启用" "true" "$(tj 'return await page.evaluate(() => document.getElementById("yolo-kv").textContent.includes("已安装未启用"));' | val)"
ck "U13 yolo 日志尾非空"    "true" "$(tj 'return await page.evaluate(() => !document.getElementById("yolo-logtail").textContent.includes("（无日志）"));' | val)"
ck "U14 rosbridge 卡片有按钮 x3" "3" "$(tj 'return await page.evaluate(() => document.querySelectorAll("#card-rosbridge button[data-act]").length);' | val)"
ck "U15 按钮未被禁用（未在飞行）" "false" "$(tj 'return await page.evaluate(() => document.querySelector("#card-rosbridge button[data-act=restart]").disabled);' | val)"
echo "页面状态: $(where)"

echo "===== 5. 配置树渲染（只读） ====="
echo "配置等待: $(tj 'var ok = true;
try { await page.waitForFunction(() => document.querySelectorAll("#cfgtree .row").length >= 30, null, {timeout: 10000}); } catch (e) { ok = false; }
return {ok: ok, n: await page.evaluate(() => document.querySelectorAll("#cfgtree .row").length)};' | val)"
R=$(tj 'return await page.evaluate(() => document.querySelectorAll("#cfgtree .row").length);' | val)
if [ "$R" -ge 30 ] 2>/dev/null; then echo "PASS  U16 配置树 >=30 行（实际 $R）"; PASS=$((PASS+1)); else echo "FAIL  U16 配置树行数（实际 $R）"; FAIL=$((FAIL+1)); fi
ck "U17 配置含 stream.rtmp_url" "true" "$(tj 'return await page.evaluate(() => document.getElementById("cfgtree").textContent.includes("rtmp://172.31.68.227"));' | val)"
ck "U18 配置含 console.port"   "true" "$(tj 'return await page.evaluate(() => document.getElementById("cfgtree").textContent.includes("8090"));' | val)"
ck "U19 配置来源标注"          "true" "$(tj 'return await page.evaluate(() => document.getElementById("cfg-src").textContent.includes("config/yolo8.json"));' | val)"
ck "U20 配置无编辑输入框（P1 只读）" "0" "$(tj 'return await page.evaluate(() => document.querySelectorAll("#cfgtree input").length);' | val)"

echo "===== 6. 日志渲染 ====="
echo "日志等待: $(tj 'var ok = true;
try { await page.waitForFunction(() => document.querySelectorAll("#logbox .ln").length >= 5, null, {timeout: 10000}); } catch (e) { ok = false; }
return {ok: ok, n: await page.evaluate(() => document.querySelectorAll("#logbox .ln").length)};' | val)"
L=$(tj 'return await page.evaluate(() => document.querySelectorAll("#logbox .ln").length);' | val)
if [ "$L" -ge 5 ] 2>/dev/null; then echo "PASS  U21 日志行 >=5（实际 $L）"; PASS=$((PASS+1)); else echo "FAIL  U21 日志行数（实际 $L）"; FAIL=$((FAIL+1)); fi
ck "U22 日志无 HTML 注入（纯文本）" "true" "$(tj 'return await page.evaluate(() => document.getElementById("logbox").children.length === document.getElementById("logbox").querySelectorAll(".ln").length);' | val)"
ck "U23 日志目标默认为 yolo"      "yolo" "$(tj 'return await page.evaluate(() => document.getElementById("log-target").value);' | val)"

echo "===== 7. 危险操作二次确认 + 重启 rosbridge（时序段单程序内完成） ====="
PID_BEFORE=$(tj 'return await page.evaluate(() => { var m = document.querySelector("#card-rosbridge .kv").textContent.match(/PID(\d+)/); return m ? m[1] : "none"; });' | val)
printf '%s' "$PID_BEFORE" > "${TMPDIR:-/tmp}/yolo8-ui-pid"   # 供程序内 fs 读取
echo "重启前 rosbridge PID: $PID_BEFORE"
tj 'await page.evaluate(() => document.querySelector("#card-rosbridge button[data-act=restart]").click()); return "clicked";' >/dev/null
tj 'var ok = true;
try { await page.waitForSelector(".modal", {timeout: 5000}); } catch (e) { ok = false; }
return ok;' >/dev/null
ck "U24 点击重启弹出确认框"  "true" "$(tj 'return await page.evaluate(() => !!document.querySelector(".modal"));' | val)"
ck "U25 确认框标题含服务名"  "true" "$(tj 'return await page.evaluate(() => document.querySelector(".modal h3").textContent.includes("rosbridge"));' | val)"
ck "U26 确认框警告冷启动"    "true" "$(tj 'return await page.evaluate(() => document.querySelector(".modal p").textContent.includes("35s"));' | val)"
ck "U27 确认前按钮未禁用"    "false" "$(tj 'return await page.evaluate(() => document.querySelector("#card-rosbridge button[data-act=restart]").disabled);' | val)"
# 单程序：装 toast 观察器 → 点确认 → 600ms 读飞行禁用 → 8.4s 后收 toast 与恢复态
# （restart POST 往返约 4s、toast 活 3.2s；全程无 CLI 往返，测量点不被开销推移）
RESTART_RET=$(tj 'return await page.evaluate(() => new Promise(res => {
  window.__seen = "no";
  var mo = new MutationObserver(function(){ if (document.getElementById("toast").textContent.indexOf("完成") >= 0) window.__seen = "yes"; });
  mo.observe(document.getElementById("toast"), {childList: true, characterData: true, subtree: true});
  var t0 = Date.now();
  document.querySelector(".modal button.danger").click();
  setTimeout(function(){
    var d600 = document.querySelector("#card-rosbridge button[data-act=restart]").disabled;
    var i600 = window.inflight.rosbridge;
    setTimeout(function(){
      mo.disconnect();
      res({d600: String(d600), i600: String(i600), seen: window.__seen,
           dEnd: String(document.querySelector("#card-rosbridge button[data-act=restart]").disabled),
           elapsed: Date.now() - t0});
    }, 8400);
  }, 600);
}));' | val)
echo "重启时序采样: $RESTART_RET"
ck "U27b 确认后按钮进入飞行禁用" "true"  "$(echo "$RESTART_RET" | jget d600)"
ck "U30 toast 提示完成"      "yes"   "$(echo "$RESTART_RET" | jget seen)"
ck "U28 重启后按钮恢复可用"  "false" "$(echo "$RESTART_RET" | jget dEnd)"
# PID 变更：浏览器内轮询等 kv 刷新（1s tick），带 15s 超时兜底
PID_AFTER=$(tj 'var before = require("fs").readFileSync("'"$TMPW"'/yolo8-ui-pid", "utf8").trim();
return await page.evaluate(b => new Promise(res => {
  var t0 = Date.now();
  (function poll(){
    var kv = document.querySelector("#card-rosbridge .kv").textContent;
    var m = kv.match(/PID(\d+)/);
    if (kv.indexOf("运行中") >= 0 && m && m[1] !== b) return res(m[1]);
    if (Date.now() - t0 > 15000) return res(m ? m[1] : "none");
    setTimeout(poll, 200);
  })();
}), before);' | val)
ck "U29 rosbridge 变为运行中" "true" "$(tj 'return await page.evaluate(() => document.querySelector("#card-rosbridge .kv").textContent.includes("运行中"));' | val)"
echo "重启后 rosbridge PID: $PID_AFTER"
if [ "$PID_BEFORE" != "none" ] && [ "$PID_AFTER" != "none" ] && [ "$PID_BEFORE" != "$PID_AFTER" ]; then
  echo "PASS  U36 PID 已变更（$PID_BEFORE -> $PID_AFTER，确认真重启）"; PASS=$((PASS+1))
else
  echo "FAIL  U36 PID 未变更（$PID_BEFORE -> $PID_AFTER）"; FAIL=$((FAIL+1))
fi
echo "--- rosbridge 卡片状态 ---"
tj 'return await page.evaluate(() => document.querySelector("#card-rosbridge .kv").textContent.replace(/\s+/g, " ").trim());' | val

echo "===== 8. 取消路径（不应执行动作） ====="
tj 'await page.evaluate(() => document.querySelector("#card-rosbridge button[data-act=stop]").click()); return "clicked";' >/dev/null
tj 'var ok = true;
try { await page.waitForSelector(".modal", {timeout: 5000}); } catch (e) { ok = false; }
return ok;' >/dev/null
tj 'await page.evaluate(() => document.querySelector(".modal .actions button:not(.danger)").click()); return "cancelled";' >/dev/null
tj 'var ok = true;
try { await page.waitForFunction(() => !document.querySelector(".modal"), null, {timeout: 5000}); } catch (e) { ok = false; }
return ok;' >/dev/null
ck "U31 取消后服务仍运行"    "true" "$(tj 'return await page.evaluate(() => document.querySelector("#card-rosbridge .kv").textContent.includes("运行中"));' | val)"
ck "U32 弹层已关闭"          "false" "$(tj 'return await page.evaluate(() => !!document.querySelector(".modal"));' | val)"

echo "===== 9. 退出登录 ====="
tj 'await page.evaluate(() => document.getElementById("logout-btn").click()); return "clicked";' >/dev/null
tj 'var ok = true;
try { await page.waitForFunction(() => !document.getElementById("login-view").hidden, null, {timeout: 5000}); } catch (e) { ok = false; }
return ok;' >/dev/null
ck "U33 退出后回到登录页"  "false" "$(tj 'return await page.evaluate(() => document.getElementById("login-view").hidden);' | val)"
ck "U34 退出后主界面隐藏"  "true"  "$(tj 'return await page.evaluate(() => document.getElementById("app-view").hidden);' | val)"
ck "U35 sessionStorage 已清" "0" "$(tj 'return await page.evaluate(() => (sessionStorage.getItem("yolo8_console_token")||"").length);' | val)"

echo "===== 10. 截图留档 + 收尾 ====="
tj 'await page.screenshot({path: "p1-console-login-tabbit.png", fullPage: false}); return "shot";' | val
ls -la p1-console-login-tabbit.png 2>/dev/null || echo "（截图未落 cwd，查 tabbit artifact 目录）"
"$TC" finish --task "$TASK" >/dev/null 2>&1 || true
rm -f "${TMPDIR:-/tmp}/yolo8-ui-token" "${TMPDIR:-/tmp}/yolo8-ui-pid"

echo ""
echo "===== UI 验收汇总: PASS=$PASS FAIL=$FAIL ====="
[ "$FAIL" -eq 0 ] && echo "浏览器级 UI 验收全部通过" || echo "UI 验收存在失败项"
