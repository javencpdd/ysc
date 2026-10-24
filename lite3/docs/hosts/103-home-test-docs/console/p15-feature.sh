#!/usr/bin/env bash
# P1.5 新功能 curl 验收（计划书 §18：话题订阅 + 配置在线编辑 + 连通预检）
#
# 覆盖：
#   T1 /api/topics        ws 连接串 + 话题清单 + rosbridge 运行态
#   T2 /api/source/probe  ffprobe 探视频源（结构化返回，不抛异常）
#   T3 /api/stream/probe  RTMP 目标 TCP 预检
#   T4 配置写拒绝路径      非法 URL / console 节 / live/lite3 互踢 / 空体（均 400 且不落盘）
#   T5 配置写正常路径      yolo 未运行 → 保存+跳过重启；yolo 运行中 → 保存+自动重启+PID 变更
#   T6 幂等写              值与现值相同 → needs_restart 为空、不重启
#   T7 审计                config_write / source_probe / stream_probe 事件留痕
#
# 约束（同 p1-accept）：登录限流 1req/s，每请求间隔 ≥0.3s；跑在 103 上（来源 ∈ 白名单）。
set -u
BASE=http://192.168.1.103:8090
TOKEN=$(python3 -c "import json;print(json.load(open('/home/test/yolo8/config/yolo8.json'))['console']['token'])")
JAR=/tmp/p15_cookies.txt
CFG=/home/test/yolo8/config/yolo8.json
PASS=0; FAIL=0

check() { # $1 名称  $2 期望  $3 实际
  if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1));
  else echo "FAIL  $1  期望 $2 实际 $3"; FAIL=$((FAIL+1)); fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; sleep 0.3; }
jget() { curl -s -b "$JAR" "$@"; sleep 0.3; }
jpost(){ # $1 URL  $2 body  $3 输出文件（可选；注意 jpost 早先版本只收 $1/$2，会把 -o 吞掉）
  local out=""
  if [ -n "${3:-}" ]; then out="-o $3"; fi
  # shellcheck disable=SC2086
  curl -s -b "$JAR" --max-time 150 -X POST -H 'Content-Type: application/json' \
    -H "X-Yolo-Token: $TOKEN" -d "$2" "$1" $out; sleep 0.3;
}
ypid(){ # 单目标 status 的 services 直接是状态对象（不是按 target 键的字典）
  python3 -c "import json;d=json.load(open('$1'));s=d.get('services',d);print((s.get('yolo',s) if isinstance(s,dict) else {}).get('pid'))"
}

echo "========== 登录 =========="
rm -f $JAR
curl -s -o /dev/null -c $JAR -X POST -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\"}" $BASE/api/auth/login; sleep 1.3

echo "========== T1 /api/topics =========="
jget "$BASE/api/topics" -o /tmp/p15_topics.json
python3 - <<'EOF'
import json, sys
d = json.load(open('/tmp/p15_topics.json'))
ok = d.get('ok') is True
names = [t['name'] for t in d.get('topics') or []]
ws = d.get('ws_url') or ''
fails = []
if not ok: fails.append('ok!=true')
if ':9090' not in ws: fails.append('ws_url 缺 9090: %r' % ws)
if '/parameter_events' not in names: fails.append('话题清单缺 /parameter_events: %r' % names)
if not isinstance(d.get('rosbridge_running'), bool): fails.append('rosbridge_running 非布尔')
print('TOPICS-CHECK', 'PASS' if not fails else 'FAIL ' + '; '.join(fails))
sys.exit(1 if fails else 0)
EOF
if [ $? -eq 0 ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
echo "  ws_url=$(python3 -c "import json;print(json.load(open('/tmp/p15_topics.json'))['ws_url'])")"
echo "  话题数=$(python3 -c "import json;print(len(json.load(open('/tmp/p15_topics.json'))['topics']))")"

echo "========== T2 /api/source/probe =========="
RTSP_URL=$(python3 -c "import json;print(json.load(open('$CFG'))['source']['rtsp_url'])")
jpost "$BASE/api/source/probe" "{\"url\":\"$RTSP_URL\",\"transport\":\"udp\"}" /tmp/p15_sprobe.json
python3 - <<'EOF'
import json, sys
d = json.load(open('/tmp/p15_sprobe.json'))
ok = d.get('ok') is True and isinstance(d.get('reachable'), bool)
print('SOURCE-PROBE-CHECK', 'PASS' if ok else 'FAIL %r' % d)
print('  reachable=%s codec=%s %sx%s@%s err=%s' % (
    d.get('reachable'), d.get('codec'), d.get('width'), d.get('height'),
    d.get('fps'), d.get('error')))
sys.exit(0 if ok else 1)
EOF
if [ $? -eq 0 ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi

echo "========== T3 /api/stream/probe =========="
RTMP_URL=$(python3 -c "import json;print(json.load(open('$CFG'))['stream']['rtmp_url'])")
jpost "$BASE/api/stream/probe" "{\"url\":\"$RTMP_URL\"}" /tmp/p15_tprobe.json
check "T3 stream probe reachable" "True" "$(python3 -c "import json;print(json.load(open('/tmp/p15_tprobe.json')).get('reachable'))")"

echo "========== T4 配置写拒绝路径（均不得落盘） =========="
MD5_BEFORE=$(md5sum $CFG | cut -d' ' -f1)
check "T4a 非法 rtsp_url 400"  400 "$(code -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"config":{"source":{"rtsp_url":"not-a-url"}}}' $BASE/api/config)"
check "T4b console 节不可写 400" 400 "$(code -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"config":{"console":{"token":"hack"}}}' $BASE/api/config)"
check "T4c live/lite3 互踢 400" 400 "$(code -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"config":{"stream":{"rtmp_url":"rtmp://172.31.68.227:1936/live/lite3"}}}' $BASE/api/config)"
check "T4d 空 patch 400"        400 "$(code -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"config":{}}' $BASE/api/config)"
check "T4e 越界阈值 400"        400 "$(code -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" -d '{"config":{"detect":{"conf_threshold":9}}}' $BASE/api/config)"
MD5_AFTER=$(md5sum $CFG | cut -d' ' -f1)
check "T4f 拒绝路径未改盘"      "$MD5_BEFORE" "$MD5_AFTER"

echo "========== T5 配置写正常路径 =========="
# 先停 yolo：保证第一个写走「保存+跳过重启」分支（运行中则会自动重启，见下一段）
curl -s -o /dev/null -b $JAR --max-time 60 -X POST -H 'Content-Type: application/json' \
  -H "X-Yolo-Token: $TOKEN" -d '{"target":"yolo"}' $BASE/api/service/stop; sleep 1.3
CONF_OLD=$(python3 -c "import json;print(json.load(open('$CFG'))['detect']['conf_threshold'])")
CONF_NEW=$(python3 -c "print(0.45 if float('$CONF_OLD')!=0.45 else 0.46)")
# yolo 当前应未运行（p1-accept E 段会停掉）→ 走「保存+跳过重启」分支
jpost "$BASE/api/config" "{\"config\":{\"detect\":{\"conf_threshold\":$CONF_NEW}}}" /tmp/p15_w1.json
check "T5a 写接口返回 ok"        "True"    "$(python3 -c "import json;print(json.load(open('/tmp/p15_w1.json')).get('ok'))")"
check "T5b needs_restart=[yolo]"  "['yolo']" "$(python3 -c "import json;print(json.load(open('/tmp/p15_w1.json')).get('needs_restart'))")"
check "T5c 重启被跳过"            "True"    "$(python3 -c "import json;d=json.load(open('/tmp/p15_w1.json'));print(bool(d.get('restart',{}).get('skipped')))")"
check "T5d 备份文件已生成"        "yes"     "$(ls $CFG.bak-* >/dev/null 2>&1 && echo yes || echo no)"
check "T5e 盘上阈值已更新"        "$CONF_NEW" "$(python3 -c "import json;print(json.load(open('$CFG'))['detect']['conf_threshold'])")"
check "T5f 回显接口已热更"        "$CONF_NEW" "$(jget $BASE/api/config -o /tmp/p15_cfg.json; python3 -c "import json;print(json.load(open('/tmp/p15_cfg.json'))['config']['detect']['conf_threshold'])")"

echo "--- 启动 yolo 后验证自动重启分支 ---"
curl -s -o /dev/null -b $JAR --max-time 90 -X POST -H 'Content-Type: application/json' \
  -H "X-Yolo-Token: $TOKEN" -d '{"target":"yolo"}' $BASE/api/service/start; sleep 1.3
jget "$BASE/api/service/status?target=yolo" -o /tmp/p15_ystat.json
PID_BEFORE=$(ypid /tmp/p15_ystat.json)
echo "  yolo PID before: $PID_BEFORE"
jpost "$BASE/api/config" "{\"config\":{\"detect\":{\"conf_threshold\":$CONF_OLD}}}" /tmp/p15_w2.json
check "T5g 运行中写触发自动重启"  "True" "$(python3 -c "import json;d=json.load(open('/tmp/p15_w2.json'));print(bool(d.get('restart',{}).get('ok')))")"
jget "$BASE/api/service/status?target=yolo" -o /tmp/p15_ystat2.json
PID_AFTER=$(ypid /tmp/p15_ystat2.json)
echo "  yolo PID after: $PID_AFTER"
if [ "$PID_BEFORE" != "$PID_AFTER" ] && [ "$PID_AFTER" != "None" ]; then
  echo "PASS  T5h yolo PID 已变更（$PID_BEFORE -> $PID_AFTER）"; PASS=$((PASS+1))
else echo "FAIL  T5h yolo PID 未变更（$PID_BEFORE -> $PID_AFTER）"; FAIL=$((FAIL+1)); fi
check "T5i 盘上阈值已还原"        "$CONF_OLD" "$(python3 -c "import json;print(json.load(open('$CFG'))['detect']['conf_threshold'])")"

echo "========== T6 幂等写（值不变 → 不重启） =========="
jpost "$BASE/api/config" "{\"config\":{\"detect\":{\"conf_threshold\":$CONF_OLD}}}" /tmp/p15_w3.json
check "T6a 幂等写 needs_restart=[]" "[]" "$(python3 -c "import json;print(json.load(open('/tmp/p15_w3.json')).get('needs_restart'))")"
check "T6b 幂等写无 restart 字段"   "None" "$(python3 -c "import json;print(json.load(open('/tmp/p15_w3.json')).get('restart'))")"

echo "========== T7 审计留痕 =========="
AUD=/home/test/yolo8/logs/console-audit.log
check "T7a config_write 已记录"  "yes" "$(grep -q '"event": "config_write"' $AUD && echo yes || echo no)"
check "T7b source_probe 已记录"  "yes" "$(grep -q '"event": "source_probe"' $AUD && echo yes || echo no)"
check "T7c stream_probe 已记录"  "yes" "$(grep -q '"event": "stream_probe"' $AUD && echo yes || echo no)"

echo ""
echo "========== P1.5 新功能验收汇总: PASS=$PASS FAIL=$FAIL =========="
[ "$FAIL" -eq 0 ] && echo "新功能验收全部通过" || echo "存在失败项，需排查"
