#!/usr/bin/env bash
# P4 真机验收（L4 模型上传 / L5 engine 兼容性 + 重载闭环）。
#
# 必须在 103 上执行（读 /home/test 本地路径、调本机 python3/TRT）：
#   bash /home/test/yolo8/console/p4-accept.sh
#
# 覆盖：认证双因子 → 好 onnx 上传（classes=80）→ 三类坏文件拒绝 →
#       导出（TRT，1~6 min）→ L5 头/5 key/names → 重载 → worker 状态闭环 →
#       非法 engine 路径拒绝 → 还原原 engine。
set -u

APP=/home/test/yolo8
# 必须用 LAN IP 而不是 127.0.0.1：console 的 CIDR 白名单只放 192.168.1.0/24，
# 从 localhost 访问时来源 IP 是 127.0.0.1 → 403（P4 首跑实测）。
BASE=http://192.168.1.103:8090
JAR=$(mktemp)
OUT=$(mktemp)
trap 'rm -f "$JAR" "$OUT"' EXIT

PASS=0
FAIL=0
TOKEN=$(python3 -c "import json;print(json.load(open('$APP/config/yolo8.json'))['console']['token'])")
COOKIE=""

say()  { printf '\n== %s\n' "$1"; }
ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf 'FAIL  %s\n' "$1"; }
check(){ if [ "$2" = "$3" ]; then ok "$1 = $2"; else bad "$1: got $2 want $3"; fi; }

# code METHOD PATH [json|file] [extra curl args...]
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

say "0. 健康检查与版本"
code GET /healthz >/dev/null
check "healthz ok" "$(jget 'd["ok"]')" "True"
check "版本" "$(jget 'd["version"]')" "2.1.0-p4"

say "1. 认证（L7 子集）"
c=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/model/info" --noproxy '*')
check "无 Cookie → 401" "$c" "401"
LOGIN=$(curl -s -c "$JAR" -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
        --data "{\"token\":\"$TOKEN\"}" --noproxy '*')
COOKIE=$(grep -c yolo8_s "$JAR")
check "登录拿到 Cookie" "$COOKIE" "1"
c=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/model/reload" -b "$JAR" \
    -H 'Content-Type: application/json' --data '{}' --noproxy '*')
check "写接口缺 X-Yolo-Token → 401" "$c" "401"

say "2. 好 onnx 上传（L4）"
# multipart 单独走：不能带 JSON Content-Type（会破坏 boundary 解析）
c=$(curl -s -o "$OUT" -w '%{http_code}' -X POST "$BASE/api/model/upload" -b "$JAR" \
    -H "X-Yolo-Token: $TOKEN" -F "onnx=@$APP/model/yolov8n.onnx;filename=yolov8n.onnx" --noproxy '*')
check "上传 HTTP" "$c" "200"
UPLOAD_ID=$(jget 'd["upload_id"]')
check "类别数" "$(jget 'd["classes"]')" "80"
check "imgsz" "$(jget 'd["imgsz"]')" "[640, 640]"
check "names 来源" "$(jget 'd["names_source"]')" "onnx_metadata"
check "names 数量" "$(jget 'len(d["names"])')" "80"
check "person 在 0 号位" "$(jget 'd["names"]["0"]')" "person"
[ -n "$UPLOAD_ID" ] && ok "upload_id=$UPLOAD_ID" || bad "upload_id 为空"

say "3. 三类坏文件（L4）"
# 注意长度 >64 字节：否则会先命中"文件过小"，测不到文本魔数那一道（P4 首跑踩过）
python3 -c "open('/tmp/p4-fake.onnx','w').write('hello, i am a txt file renamed to onnx\n' * 5)"
sleep 2.2
c=$(curl -s -o "$OUT" -w '%{http_code}' -X POST "$BASE/api/model/upload" -b "$JAR" \
    -H "X-Yolo-Token: $TOKEN" -F "onnx=@/tmp/p4-fake.onnx;filename=fake.onnx" --noproxy '*')
check "改扩展名 txt → 400" "$c" "400"
grep -q "文本" "$OUT" && ok "拒绝理由提到文本" || bad "拒绝理由不明确：$(cat "$OUT")"

: > /tmp/p4-empty.onnx
sleep 2.2
c=$(curl -s -o "$OUT" -w '%{http_code}' -X POST "$BASE/api/model/upload" -b "$JAR" \
    -H "X-Yolo-Token: $TOKEN" -F "onnx=@/tmp/p4-empty.onnx;filename=empty.onnx" --noproxy '*')
check "空文件 → 400" "$c" "400"

dd if=/dev/zero of=/tmp/p4-big.onnx bs=1M count=51 status=none
sleep 2.2
c=$(curl -s -o "$OUT" -w '%{http_code}' -X POST "$BASE/api/model/upload" -b "$JAR" \
    -H "X-Yolo-Token: $TOKEN" -F "onnx=@/tmp/p4-big.onnx;filename=big.onnx" --noproxy '*')
check "51 MB 超限 → 413" "$c" "413"
ls "$APP/model/uploads" | grep -c "p4-fake\|p4-empty\|p4-big" >/dev/null && bad "坏文件留下了残文件" || ok "坏文件无残留"
rm -f /tmp/p4-fake.onnx /tmp/p4-empty.onnx /tmp/p4-big.onnx

say "4. 类别清单校验（负数用例）"
sleep 2.2                       # 限流：写接口 1 req/s（upload 桶 0.5/s）
c=$(code POST /api/model/export "{\"upload_id\":\"$UPLOAD_ID\",\"names\":[\"a\",\"b\"]}")
check "names 数量不符 → 400" "$c" "400"

say "5. 导出 engine（TRT，最长 30 min）"
if [ -n "${REUSE_ENGINE:-}" ] && [ -f "$APP/model/$REUSE_ENGINE" ]; then
  TARGET="$REUSE_ENGINE"
  ok "复用已有 engine：$TARGET（跳过构建，REUSE_ENGINE 生效）"
else
NAMES=$(python3 - "$UPLOAD_ID" <<'PY'
import json, sys, os
p = "/home/test/yolo8/model/yolov8n.onnx"
sys.path.insert(0, "/home/test/yolo8/src")
import export_engine as ee
names = ee.inspect_onnx(p)["names"]
print(json.dumps(names, ensure_ascii=False))
PY
)
BODY=$(python3 -c "import json,sys;print(json.dumps({'upload_id':sys.argv[1],'names':json.loads(sys.argv[2]),'workspace_mb':1024,'half':True}))" "$UPLOAD_ID" "$NAMES")
sleep 2.2                       # 限流
c=$(code POST /api/model/export "$BODY")
check "导出受理 → 202" "$c" "202"
TARGET=$(jget 'd["target"]')
[ -n "$TARGET" ] && ok "目标 $TARGET" || bad "无 target"

STATE=exporting
for i in $(seq 1 540); do           # 540×5s = 45 min，与 server.py EXPORT_TIMEOUT_S 对齐
  sleep 5
  code GET /api/model/export/status >/dev/null
  STATE=$(jget 'd["task"]["state"]')
  PROG=$(jget 'd["task"]["progress"]')
  LAST=$(jget '(d["task"].get("log") or [""])[-1][:80]')
  printf '  ... %ss state=%s progress=%s | %s\n' "$((i*5))" "$STATE" "$PROG" "$LAST"
  [ "$STATE" = "exported" ] && break
  [ "$STATE" = "failed" ] && break
done
check "导出最终状态" "$STATE" "exported"
if [ "$STATE" != "exported" ]; then
  printf '导出日志尾部：\n'; python3 -c "import json;d=json.load(open('$OUT'));print('\n'.join(d['task']['log'][-12:]))"
fi
fi   # REUSE_ENGINE

say "6. L5 engine 兼容性"
ENGINE_ABS="$APP/model/$TARGET"
[ -f "$ENGINE_ABS" ] && ok "engine 文件存在（$(stat -c%s "$ENGINE_ABS") 字节）" || bad "engine 文件不存在"
VERIFY=$(cd "$APP/src" && python3 export_engine.py --verify "$ENGINE_ABS" 2>/dev/null | grep '^RESULT ' | cut -c8-)
check "头解析 ok" "$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['ok'])" "$VERIFY")" "True"
check "5 个必需 key 齐全（parse_engine_header 校验）" \
  "$(python3 -c "import json,sys;print(json.loads(sys.argv[1]).get('required_keys_ok'))" "$VERIFY")" "True"
check "names 数量" "$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['names_count'])" "$VERIFY")" "80"
# 端到端加载（ultralytics AutoBackend）在 worker 占着 GPU 时会挂住（P4 实测 90s 无输出），
# 故这里只验证 plan 可反序列化；真正的端到端加载由第 8 节（重载后 worker 继续出帧）证明。
DES=$(cd "$APP/src" && timeout 120 python3 -c "
import tensorrt as trt
p='$ENGINE_ABS'
ml=int.from_bytes(open(p,'rb').read(4),'little',signed=True)
f=open(p,'rb'); f.seek(4+ml); plan=f.read()
rt=trt.Runtime(trt.Logger(trt.Logger.ERROR))
print('DES', bool(rt.deserialize_cuda_engine(plan)))
" 2>/dev/null | grep -E '^DES ' | tail -1)
check "TRT 反序列化 plan 可用" "$DES" "DES True"

say "7. 非法 engine 路径"
sleep 2.2
c=$(code POST /api/model/reload '{"engine":"../../etc/passwd"}')
check "路径穿越 → 400" "$c" "400"
sleep 1.2
c=$(code POST /api/model/reload '{"engine":"exports/nope.engine"}')
check "不存在 → 404" "$c" "404"

say "8. 重载闭环（worker 帧边界重建）"
sleep 2.2
c=$(code POST /api/model/reload "{\"engine\":\"$TARGET\"}")
check "重载受理 → 200" "$c" "200"
check "pending_reload" "$(jget 'd["pending_reload"]')" "True"
WST="$APP/logs/worker_state.json"
GOT=""
for i in $(seq 1 24); do
  sleep 2
  GOT=$(python3 -c "
import json
d = json.load(open('$WST')).get('model') or {}
print('%s|%s|%s|%s' % (d.get('engine'), d.get('pending_reload'), d.get('reload_count'), d.get('classes_total')))
" 2>/dev/null)
  printf '  ... worker model=%s\n' "$GOT"
  case "$GOT" in
    "$(basename "$TARGET")|False|"*) break ;;
  esac
done
case "$GOT" in
  "$(basename "$TARGET")|False|"*) ok "worker 已切到新 engine 且 pending 清零（$GOT）" ;;
  *) bad "worker 未完成重载（$GOT）" ;;
esac
FPS=$(python3 -c "import json;print(json.load(open('$WST'))['worker']['fps'])" 2>/dev/null)
awk -v f="$FPS" 'BEGIN{exit !(f > 3)}' && ok "重载后 fps=$FPS" || bad "fps 异常：$FPS"

say "9. 还原原 engine"
sleep 2.2
c=$(code POST /api/model/reload '{"engine":"yolov8n_arm.engine"}')
check "还原受理 → 200" "$c" "200"
OKR=""
for i in $(seq 1 20); do
  sleep 2
  OKR=$(python3 -c "
import json
d = json.load(open('$WST')).get('model') or {}
print('%s|%s' % (d.get('engine'), d.get('pending_reload')))
" 2>/dev/null)
  printf '  ... %s\n' "$OKR"
  [ "$OKR" = "yolov8n_arm.engine|False" ] && break
done
check "已回到 arm.engine" "$OKR" "yolov8n_arm.engine|False"
python3 -c "
import json
cfg = json.load(open('$APP/config/yolo8.json'))
print('config model =', json.dumps(cfg['model'], ensure_ascii=False))
" | tail -1

printf '\nRESULT PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
