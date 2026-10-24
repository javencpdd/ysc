#!/usr/bin/env bash
# P5 真机验收：存储治理（占用统计 / 按需清空 / 日志轮换）。
#
# 必须在 103 上执行：
#   bash /home/test/yolo8/console/p5-accept.sh
#
# 覆盖：占用统计 → 五类分类正确 → purge 值域校验 → 清空 uploads/exports
#       → 计时缓存默认保护 → 审计留痕 → logrotate 安装状态。
# 安全边界：**只清空 uploads/exports 两类缓存**；pic/ 与 logs/ 是真实数据，
# 只统计不清空（真要清请用控制台界面手动确认）。
set -u

APP=/home/test/yolo8
# 必须用 LAN IP：console 的 CIDR 白名单只放 192.168.1.0/24（127.0.0.1 会 403）
BASE=http://192.168.1.103:8090
JAR=$(mktemp)
OUT=$(mktemp)
trap 'rm -f "$JAR" "$OUT"' EXIT

PASS=0
FAIL=0
TOKEN=$(python3 -c "import json;print(json.load(open('$APP/config/yolo8.json'))['console']['token'])")

say()  { printf '\n== %s\n' "$1"; }
ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf 'FAIL  %s\n' "$1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1 = $2"; else bad "$1: got $2 want $3"; fi; }

code(){ local m=$1 p=$2 body=${3:-}; shift 3 || true
  if [ -n "$body" ]; then
    curl -s -o "$OUT" -w '%{http_code}' -X "$m" "$BASE$p" -b "$JAR" \
      -H "X-Yolo-Token: $TOKEN" -H 'Content-Type: application/json' \
      --data "$body" --noproxy '*' "$@"
  else
    curl -s -o "$OUT" -w '%{http_code}' -X "$m" "$BASE$p" -b "$JAR" \
      -H "X-Yolo-Token: $TOKEN" --noproxy '*' "$@"
  fi
}
jget(){ python3 -c "import json,sys;d=json.load(open('$OUT'));print(eval(sys.argv[1]))" "$1" 2>/dev/null; }

say "0. 健康检查与登录"
code GET /healthz >/dev/null
check "healthz ok" "$(jget 'd["ok"]')" "True"
curl -s -c "$JAR" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
     --data "{\"token\":\"$TOKEN\"}" --noproxy '*' >/dev/null
check "登录拿到 Cookie" "$(grep -c yolo8_s "$JAR")" "1"

say "1. 占用统计"
code GET /api/maintenance/storage >/dev/null
check "接口 ok" "$(jget 'd["ok"]')" "True"
for k in pics trash uploads exports logs; do
  n=$(jget "d[\"storage\"][\"kinds\"][\"$k\"][\"files\"]")
  if [ -n "$n" ]; then ok "$k 有统计（$n 个）"; else bad "$k 缺统计"; fi
done
check "retention 默认 pic_max_mb" "$(jget 'd["retention"]["pic_max_mb"]')" "2048"
check "retention 默认 pic_keep_days" "$(jget 'd["retention"]["pic_keep_days"]')" "30"
check "retention 默认 trash_keep_days" "$(jget 'd["retention"]["trash_keep_days"]')" "7"
check "purge_targets 五类" "$(jget 'len(d["purge_targets"])')" "5"
TOTAL=$(jget 'd["storage"]["total_bytes"]')
printf '  当前分类合计：%s 字节\n' "$TOTAL"

say "2. purge 值域校验（都不能落文件）"
sleep 11   # purge 限流 10s/次（破坏性操作），验收必须拉开间隔
c=$(code POST /api/maintenance/purge '{"targets":[]}')
check "空 targets → 400" "$c" "400"
sleep 11   # purge 限流 10s/次（破坏性操作），验收必须拉开间隔
c=$(code POST /api/maintenance/purge '{"targets":["nope"]}')
check "未知 target → 400" "$c" "400"
sleep 11   # purge 限流 10s/次（破坏性操作），验收必须拉开间隔
c=$(code POST /api/maintenance/purge '{"targets":["uploads"],"keep_timing_cache":"yes"}')
check "keep_timing_cache 非布尔 → 400" "$c" "400"

say "3. 清空 uploads（造一个测试文件）"
head -c 4096 /dev/zero > "$APP/model/uploads/p5-test.onnx"
BEFORE=$(ls -1 "$APP/model/uploads" | wc -l)
sleep 11   # purge 限流 10s/次（破坏性操作），验收必须拉开间隔
c=$(code POST /api/maintenance/purge '{"targets":["uploads"]}')
check "purge uploads → 200" "$c" "200"
AFTER=$(ls -1 "$APP/model/uploads" | wc -l)
check "uploads 已清空" "$AFTER" "0"
printf '  清理前 %s 个 → 清理后 %s 个\n' "$BEFORE" "$AFTER"

say "4. 清空 exports，计时缓存必须保住"
CACHE="$APP/model/exports/.trt-timing-cache"
[ -f "$CACHE" ] && ok "计时缓存存在（$(stat -c%s "$CACHE") 字节）" || bad "计时缓存不存在，无法验证保护逻辑"
head -c 2048 /dev/zero > "$APP/model/exports/p5-test.engine"
sleep 11   # purge 限流 10s/次（破坏性操作），验收必须拉开间隔
c=$(code POST /api/maintenance/purge '{"targets":["exports"]}')
check "purge exports → 200" "$c" "200"
[ -f "$APP/model/exports/p5-test.engine" ] && bad "测试 engine 未删" || ok "测试 engine 已删"
[ -f "$CACHE" ] && ok "计时缓存被保留（默认保护生效）" || bad "计时缓存被误删"
check "exports 只删了 1 个" "$(jget 'd["result"]["exports"]["files"]')" "1"

say "5. 审计留痕"
N=$(printf '\047\n' | sudo -S grep -c maintenance_purge "$APP/logs/console-audit.log" 2>/dev/null)
if [ "${N:-0}" -ge 1 ]; then ok "审计有 maintenance_purge 记录（$N 条）"; else bad "审计无记录"; fi

say "6. 日志治理安装状态"
if [ -f /etc/logrotate.d/lite3-yolo8 ]; then
  ok "logrotate 已安装"
else
  bad "logrotate 未安装（跑：sudo bash $APP/deploy/install-retention.sh）"
fi
if [ -f /etc/systemd/journald.conf.d/lite3-yolo8.conf ]; then
  ok "journald 限额已安装"
else
  bad "journald 限额未安装"
fi
printf '  logs/ 当前占用：%s\n' "$(du -sh "$APP/logs" 2>/dev/null | cut -f1)"

printf '\nRESULT PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
