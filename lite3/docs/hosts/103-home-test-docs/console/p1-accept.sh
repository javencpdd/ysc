#!/usr/bin/env bash
# P1-3 curl 验收 v2（修正 v1 的测试脚本缺陷：登录限流 1req/s 未留间隔、令牌桶被密集 curl 打空）
#
# v1 教训（2026-10-22）：22 个 FAIL 里 20 个是脚本自身问题——
#   · 登录接口限流 1 req/s 是**设计行为**，B1/B2 间隔 <1s 导致 B2 被 429，
#     会话始终建不起来，后续 C/D/E 全部 401（连锁）
#   · 令牌桶 10 突发被无间隔 curl 打空，零星 429
#   · A12 断言写法错误
#   · A10 未登录访问未知 /api 返回 401 而非 404 是**正确的防端点枚举**，改预期
# 本版：每请求间隔 0.25s；登录前后显式 sleep 1.3s；遍历测试加 --path-as-is。
set -u
BASE_LAN=http://192.168.1.103:8090      # 来源=192.168.1.103 ∈ 白名单
BASE_LO=http://127.0.0.1:8090           # 来源=127.0.0.1 ∉ 白名单 → 403
TOKEN=$(python3 -c "import json;print(json.load(open('/home/test/yolo8/config/yolo8.json'))['console']['token'])")
JAR=/tmp/p1_cookies.txt
PASS=0; FAIL=0
OUT=/tmp/p1_out
mkdir -p $OUT

# G 段是全文件计数 ⇒ 开跑前必须轮转审计日志。
# 历史坑（2026-10-22 P1.5 回归实测）：审计日志在 /home/test/yolo8/logs/ 下，
# 不在 console/logs/ 下；在 console/ 目录里相对路径轮转会静默失败（mv 报错被
# 2>/dev/null 吞掉），旧账累计导致 G1/G2/G3/G4 全翻倍。故此处用绝对路径并打印结果。
AUD=/home/test/yolo8/logs/console-audit.log
if [ -f "$AUD" ]; then
  ROT="$AUD.rot-$(date +%Y%m%d-%H%M%S)"
  if mv "$AUD" "$ROT"; then echo "审计日志已轮转 → $ROT"; else echo "轮转失败：$AUD"; fi
else
  echo "审计日志不存在（首次运行？）：$AUD"
fi

check() { # $1 名称  $2 期望  $3 实际
  if [ "$2" = "$3" ]; then
    echo "PASS  $1 = $3"; PASS=$((PASS+1))
  else
    echo "FAIL  $1  期望 $2 实际 $3"; FAIL=$((FAIL+1))
  fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; sleep 0.25; }
jget() { curl -s -b "$JAR" "$@"; sleep 0.25; }        # 带会话 GET
jpost(){ curl -s -b "$JAR" -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d "$2" "$1"; sleep 0.25; }

echo "========== A. 免认证与拒绝路径 =========="
check "A1 /healthz 免认证"            200 "$(code $BASE_LAN/healthz)"
check "A2 非白名单(127.0.0.1) 403"    403 "$(code $BASE_LO/api/state)"
check "A3 未登录 /api/state 401"      401 "$(code $BASE_LAN/api/state)"
check "A4 未登录 /api/config 401"     401 "$(code $BASE_LAN/api/config)"
check "A5 未登录 /api/service/status" 401 "$(code "$BASE_LAN/api/service/status?target=all")"
check "A6 未登录 POST 停止 401"       401 "$(code -X POST -H 'Content-Type: application/json' -d '{"target":"yolo"}' $BASE_LAN/api/service/stop)"
check "A7 登录页 / 可达"              200 "$(code $BASE_LAN/)"
check "A8 /static/index.html 可达"    200 "$(code $BASE_LAN/static/index.html)"
check "A9 OPTIONS 预检 403(CSRF)"     403 "$(code -X OPTIONS $BASE_LAN/api/state)"
check "A10 未知 /api 未登录 401(防枚举)" 401 "$(code $BASE_LAN/api/nope)"
check "A11 目录穿越(--path-as-is) 404" 404 "$(code --path-as-is "$BASE_LAN/static/../server.py")"
check "A12 编码穿越 %2e%2e 404"        404 "$(code --path-as-is "$BASE_LAN/static/%2e%2e/server.py")"
# 登录页 HTML 不得包含 token 明文
HPAGE=$(curl -s $BASE_LAN/)
if echo "$HPAGE" | grep -q "$TOKEN"; then check "A13 登录页不泄 token" "不含" "含"; else check "A13 登录页不泄 token" "不含" "不含"; fi
# 登录页 HTML 必须含关键元素
for kw in "login-form" "token-input" "badges" "card-yolo" "cfgtree" "logbox"; do
  if echo "$HPAGE" | grep -q "$kw"; then check "A14 登录页含 $kw" "有" "有"; else check "A14 登录页含 $kw" "有" "无"; fi
done

echo "========== B. 登录 =========="
sleep 1.3
check "B1 错误 token 401"             401 "$(code -X POST -H 'Content-Type: application/json' -d '{"token":"0123456789abcdef0123456789abcdef"}' $BASE_LAN/api/auth/login)"
sleep 1.3
rm -f $JAR
LOGIN_CODE=$(curl -s -o $OUT/login.json -w '%{http_code}' -c $JAR -X POST \
  -H 'Content-Type: application/json' -d "{\"token\":\"$TOKEN\"}" $BASE_LAN/api/auth/login)
check "B2 正确 token 登录 200"         200 "$LOGIN_CODE"
check "B3 登录置 Set-Cookie"           1   "$(grep -c 'yolo8_s' $JAR)"
check "B4 登录响应 ok=true"            1   "$(grep -c '"ok": *true' $OUT/login.json)"
check "B5 Cookie 带 HttpOnly"          1   "$(grep -c 'HttpOnly' $JAR)"
check "B6 带会话 /api/state 200"       200 "$(code -b $JAR $BASE_LAN/api/state)"
check "B7 错误会话 401"                401 "$(code -H 'Cookie: yolo8_s=deadbeefdeadbeefdeadbeefdeadbeef' $BASE_LAN/api/state)"

echo "========== C. 读接口 =========="
jget "$BASE_LAN/api/state"  -o $OUT/state.json
jget "$BASE_LAN/api/config" -o $OUT/config.json
jget "$BASE_LAN/api/service/status?target=all" -o $OUT/status.json
jget "$BASE_LAN/api/logs?target=yolo&lines=5"   -o $OUT/logs.json
check "C1 /api/state 200"              200 "$(code -b $JAR $BASE_LAN/api/state)"
check "C2 /api/config 200"             200 "$(code -b $JAR $BASE_LAN/api/config)"
check "C3 /api/service/status 200"     200 "$(code -b $JAR "$BASE_LAN/api/service/status?target=all")"
check "C4 /api/logs 200"               200 "$(code -b $JAR "$BASE_LAN/api/logs?target=yolo&lines=5")"
check "C5 status 越界 target 400"      400 "$(code -b $JAR "$BASE_LAN/api/service/status?target=bogus")"
check "C6 带会话未知 /api 404"         404 "$(code -b $JAR $BASE_LAN/api/nope)"

echo "========== D. 写接口双因子 =========="
check "D1 缺 X-Yolo-Token 401"         401 "$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' -d '{"target":"rosbridge"}' $BASE_LAN/api/service/stop)"
sleep 0.25
check "D2 错 X-Yolo-Token 401"         401 "$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: 0123456789abcdef0123456789abcdef" -d '{"target":"rosbridge"}' $BASE_LAN/api/service/stop)"
sleep 0.25
check "D3 越界 target 400"             400 "$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"target":"bogus"}' $BASE_LAN/api/service/start)"
sleep 0.25
check "D4 非 JSON 体 400"              400 "$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d 'not-json' $BASE_LAN/api/service/start)"
sleep 0.25
check "D5 不带会话只带 token 401"      401 "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"target":"rosbridge"}' $BASE_LAN/api/service/stop)"
sleep 0.25

echo "========== E. 服务动作（真实调用 ctl） =========="
ZB=$(ps -eo stat= | grep -c '^Z' || true)
echo "动作前僵尸数: $ZB"
FAILN=0
for i in $(seq 1 10); do
  C=$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' \
      -H "X-Yolo-Token: $TOKEN" -d '{"target":"rosbridge"}' $BASE_LAN/api/service/restart)
  if [ "$C" != "200" ]; then FAILN=$((FAILN+1)); echo "  第 $i 次 restart exit=$C"; fi
  sleep 0.3
done
check "E1 rosbridge restart x10 全 200" 0 "$FAILN"
sleep 1
jget "$BASE_LAN/api/service/status?target=rosbridge" -o $OUT/rb_after.json
check "E2 重启后 rosbridge running" '"running": true' "$(grep -o '"running": *true' $OUT/rb_after.json | head -1)"

echo "--- yolo 一轮真实启停 ---"
Y1=$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' \
    -H "X-Yolo-Token: $TOKEN" -d '{"target":"yolo"}' $BASE_LAN/api/service/start)
check "E3 yolo start 200" 200 "$Y1"
sleep 8
jget "$BASE_LAN/api/service/status?target=yolo" -o $OUT/yolo_status.json
check "E3b yolo 启动后 running" '"running": true' "$(grep -o '"running": *true' $OUT/yolo_status.json | head -1)"
Y2=$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -X POST -H 'Content-Type: application/json' \
    -H "X-Yolo-Token: $TOKEN" -d '{"target":"yolo"}' $BASE_LAN/api/service/stop)
check "E4 yolo stop 200" 200 "$Y2"
sleep 3
jget "$BASE_LAN/api/service/status?target=yolo" -o $OUT/yolo_status_after.json
check "E5 停止后 running=false" '"running": false' "$(grep -o '"running": *false' $OUT/yolo_status_after.json | head -1)"

echo "========== F. 僵尸与残留 =========="
sleep 1
ZA=$(ps -eo stat= | grep -c '^Z' || true)
echo "动作后僵尸数: $ZA"
check "F1 无新增僵尸" "$ZB" "$ZA"
LEFT=$(ps -eo pid,cmd | grep -c '[r]un-rosbridge.sh' || true)
check "F2 rosbridge 无残留进程" 0 "$LEFT"
LEFTY=$(ps -eo pid,cmd | grep -c '[r]un-yolo-publish.sh' || true)
check "F3 yolo 无残留进程" 0 "$LEFTY"

echo "========== G. 审计日志 =========="
# 聚合式审计语义（RejectThrottle）：窗口内首条立即记（无 suppressed 字段），
# 其余只计数，由后台线程每 30s 补一条带 suppressed 的汇总行。
AUD=/home/test/yolo8/logs/console-audit.log
immediate() { grep "\"event\": \"$1\"" $AUD | grep -vc '"suppressed"' || true; }
summary()   { grep "\"event\": \"$1\"" $AUD | grep -c '"suppressed"' || true; }

A1=$(grep -c '"event": "service_restart"' $AUD || true)
check "G1 审计含 10 条 service_restart" 10 "$A1"
# D1 缺头 + D2 错头 → 同 IP 同窗口 → 1 条立即 + 1 次被抑制
check "G2 token_reject 首条立即记"      1 "$(immediate token_reject)"
# A3/A4/A5/A6 + B7 + D5 共 6 次无会话 401 → 1 条立即
check "G3 auth_reject 首条立即记"       1 "$(immediate auth_reject)"
# A2/A11/A12 共 3 次白名单外 → 1 条立即
check "G4 cidr_reject 首条立即记"       1 "$(immediate cidr_reject)"
T3=$(grep -c '"event": "login"' $AUD || true)
echo "审计 login 条数: $T3 (期望 >=2: B1 失败 + B2 成功；登录失败不降频)"
if [ "$T3" -ge 2 ]; then echo "PASS  G5 login 计数"; PASS=$((PASS+1)); else echo "FAIL  G5 login 计数"; FAIL=$((FAIL+1)); fi
# 汇总线程已在 30s 倍数时刻 tick 过，应存在带 suppressed 的汇总行
T4=$(grep -c '"suppressed"' $AUD || true)
echo "审计汇总行(suppressed)条数: $T4 (期望 >=1)"
if [ "$T4" -ge 1 ]; then echo "PASS  G6 汇总线程已补条"; PASS=$((PASS+1)); else echo "FAIL  G6 汇总线程已补条"; FAIL=$((FAIL+1)); fi

echo "========== H. 登录锁定（放最后：会锁 192.168.1.103 300s） =========="
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -X POST -H 'Content-Type: application/json' \
    -d '{"token":"ffffffffffffffffffffffffffffffff"}' $BASE_LAN/api/auth/login
  sleep 1.3
done
check "H1 第 6 次登录 429 锁定" 429 "$(code -X POST -H 'Content-Type: application/json' -d "{\"token\":\"$TOKEN\"}" $BASE_LAN/api/auth/login)"

echo ""
echo "========== 汇总: PASS=$PASS FAIL=$FAIL =========="
[ "$FAIL" -eq 0 ] && echo "P1-3 验收全部通过" || echo "P1-3 存在失败项，需排查"
