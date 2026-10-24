#!/usr/bin/env bash
# P4 重载钩子快检（不需要 TRT 构建）：把现有 arm.engine 复制成 exports/arm-copy.engine，
# 切过去让 worker 真重建一次（reload_count+1），再切回原 engine。
# 用途：构建耗时长时单独验证 §5.6.4 的 worker 帧边界重载链路。
# 用法：bash console/p4-reload-check.sh
set -u
APP=/home/test/yolo8
BASE=http://192.168.1.103:8090      # 必须 LAN IP（白名单只放 192.168.1.0/24）
JAR=$(mktemp); OUT=$(mktemp)
trap 'rm -f "$JAR" "$OUT"' EXIT
PASS=0; FAIL=0
TOKEN=$(python3 -c "import json;print(json.load(open('$APP/config/yolo8.json'))['console']['token'])")
WST="$APP/logs/worker_state.json"

ok(){ PASS=$((PASS+1)); echo "PASS  $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL  $1"; }
ck(){ if [ "$2" = "$3" ]; then ok "$1 = $3"; else bad "$1 期望 $2 实际 $3"; fi; }
jget(){ python3 -c "import json,sys;d=json.load(open('$OUT'));print(eval(sys.argv[1]))" "$1" 2>/dev/null; }

curl -s -c "$JAR" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  --data "{\"token\":\"$TOKEN\"}" --noproxy '*' >/dev/null

mkdir -p "$APP/model/exports"
cp -f "$APP/model/yolov8n_arm.engine" "$APP/model/exports/arm-copy.engine"
ok "已复制 arm.engine → exports/arm-copy.engine（$(stat -c%s "$APP/model/exports/arm-copy.engine") 字节）"

BEFORE=$(python3 -c "import json;print((json.load(open('$WST')).get('model') or {}).get('reload_count',0))" 2>/dev/null)
echo "重载前 reload_count=$BEFORE"

sleep 2.2
C=$(curl -s -o "$OUT" -w '%{http_code}' -X POST "$BASE/api/model/reload" -b "$JAR" \
    -H "X-Yolo-Token: $TOKEN" -H 'Content-Type: application/json' \
    --data '{"engine":"exports/arm-copy.engine"}' --noproxy '*')
ck "重载受理" "$C" "200"

GOT=""
for i in $(seq 1 30); do
  sleep 2
  GOT=$(python3 -c "
import json
d = json.load(open('$WST')).get('model') or {}
print('%s|%s|%s' % (d.get('engine'), d.get('pending_reload'), d.get('reload_count')))
" 2>/dev/null)
  echo "  ... $GOT"
  case "$GOT" in
    "arm-copy.engine|False|"*) break ;;
  esac
done
case "$GOT" in
  "arm-copy.engine|False|"*) ok "worker 已切到 arm-copy.engine 且 pending 清零" ;;
  *) bad "worker 未切到 arm-copy.engine（$GOT）" ;;
esac
AFTER=$(echo "$GOT" | cut -d'|' -f3)
if [ "${AFTER:-0}" -gt "${BEFORE:-0}" ] 2>/dev/null; then
  ok "reload_count $BEFORE → $AFTER（确为重建，非「相同路径跳过」）"
else
  bad "reload_count 未增长（$BEFORE → $AFTER）"
fi

sleep 2.2
C=$(curl -s -o "$OUT" -w '%{http_code}' -X POST "$BASE/api/model/reload" -b "$JAR" \
    -H "X-Yolo-Token: $TOKEN" -H 'Content-Type: application/json' \
    --data '{"engine":"yolov8n_arm.engine"}' --noproxy '*')
ck "还原受理" "$C" "200"
BACK=""
for i in $(seq 1 20); do
  sleep 2
  BACK=$(python3 -c "
import json
d = json.load(open('$WST')).get('model') or {}
print('%s|%s' % (d.get('engine'), d.get('pending_reload')))
" 2>/dev/null)
  [ "$BACK" = "yolov8n_arm.engine|False" ] && break
done
ck "已还原 arm.engine" "$BACK" "yolov8n_arm.engine|False"
FPS=$(python3 -c "import json;print(json.load(open('$WST'))['worker']['fps'])" 2>/dev/null)
awk -v f="$FPS" 'BEGIN{exit !(f > 3)}' && ok "重载后 fps=$FPS" || bad "fps 异常：$FPS"

printf '\nRESULT PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
