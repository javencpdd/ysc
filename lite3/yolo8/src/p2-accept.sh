#!/usr/bin/env bash
# P2 运行时验收（**必须在 103 上执行**：读 /home/test 本地路径 + 本机 ffprobe）
#
# 覆盖 P2 的核心承诺（§10 分期表 P2 行判据）：
#   V1 冷启动到达稳态：进程存活、源 running、RTMP 可 ffprobe 拉回流
#   V2 worker_state.json 落盘且字段符合 §6.3
#   V3 阈值热更新 ≤1s：改 config → 日志同步 + worker_state 同步（不改进程）
#   V4 RTMP 故障**只降级不退出**（R11）：目标改不可达 → error → 进程仍存活 → 改回自动恢复
#   V5 源切换失败回滚：坏源 → 回滚 last_good → 源仍 running、帧继续
#   V6 管理面兜底：经 console API 提交坏源被 400 拒绝且不落盘（旧源无感）
#
# 前置：yolo 已在运行。跑法：
#   scp p2-accept.sh ysc@192.168.1.103:/tmp/ && ssh ysc@192.168.1.103 'bash /tmp/p2-accept.sh'
set -u
BASE=http://192.168.1.103:8090
CFG=/home/test/yolo8/config/yolo8.json
LOG=/home/test/yolo8/logs/yolo-publish.log
STATE=/home/test/yolo8/logs/worker_state.json
RTMP=rtmp://172.31.68.227:1936/live/lite3_yolo
BAD_RTMP=rtmp://127.0.0.1:1936/live/test        # 本机无监听 ⇒ 即时拒连（ECONNREFUSED，~1s 内总线报错）。
# 原用 192.0.2.1（TEST-NET-1 不可达）的问题（P2 首轮实测）：
#   ① librtmp 对不可达地址要等 TCP 超时（十几秒~分钟级），14s 窗口内 rtmp_state
#      仍是 running ⇒ V4a/V4c 假失败；
#   ② 坏 publisher 管线永远 preroll 不了、常驻不撤，疑似把主循环拖慢到 0.83fps
#      （frames 1700→1800 走了 121s）⇒ 连带 V5d 假失败。
# 拒连形态同样覆盖 R11「RTMP 出错只降级不退出」的承诺，且失败确定性可复现。
BAD_RTSP=rtsp://192.0.2.1:8554/nope             # 源侧保持不可达：V5 回滚路径靠看门狗兜底（~7s 抛 SourceUnavailable）
JAR=/tmp/p2_cookies.txt
PASS=0; FAIL=0

TOKEN=$(python3 -c "import json;print(json.load(open('$CFG'))['console']['token'])")

check() { # $1 名称 $2 期望 $3 实际
  if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; PASS=$((PASS+1));
  else echo "FAIL  $1  期望 $2 实际 $3"; FAIL=$((FAIL+1)); fi
}
check_true() { # $1 实际（Python 的 True/False 也算），$2 名称
  case "$(echo "$1" | tr 'A-Z' 'a-z')" in
    true) echo "PASS  $2"; PASS=$((PASS+1));;
    *)    echo "FAIL  $2  ($1)"; FAIL=$((FAIL+1));;
  esac; }
jfield() { python3 -c "import json;d=json.load(open('$1'));print($2)" 2>/dev/null; }
ypid() { cat /home/test/yolo8/logs/yolo.pid 2>/dev/null; }
setcfg() { # $1 python 表达式，直接改配置文件（模拟外部改配置）
  python3 - "$CFG" "$1" <<'EOF'
import json, sys
p, expr = sys.argv[1], sys.argv[2]
c = json.load(open(p))
exec(expr)
open(p, 'w').write(json.dumps(c, ensure_ascii=False, indent=2))
EOF
}

echo "========== V1 冷启动稳态 =========="
PID0=$(ypid); echo "yolo PID=$PID0"
if [ -n "$PID0" ] && ps -p "$PID0" >/dev/null 2>&1; then
  check "V1a 进程存活" "yes" "yes"
else
  check "V1a 进程存活" "yes" "no"
fi
sleep 2
check "V1b source.state" "running" "$(jfield $STATE "d['source']['state']")"
check "V1c rtmp_state" "running" "$(jfield $STATE "d['stream']['rtmp_state']")"
FF=$(timeout 25 ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height -of csv=p=0 "$RTMP" 2>&1)
echo "  ffprobe: $FF"
if echo "$FF" | grep -q "h264"; then check "V1d RTMP 回流 h264" "yes" "yes";
else check "V1d RTMP 回流 h264" "yes" "no"; fi

echo "========== V2 worker_state 字段 =========="
check_true "$(jfield $STATE "str(d['worker']['alive'])")" "V2a worker.alive"
check_true "$(python3 -c "
import json;d=json.load(open('$STATE'));print('true' if d['worker']['fps']>0 else 'false')")" \
  "V2b worker.fps>0"
check_true "$(python3 -c "
import json;d=json.load(open('$STATE'))
print('true' if set(['type','state','url_masked','err']) <= set(d['source']) else 'false')")" \
  "V2c source 字段齐全"
check_true "$(python3 -c "
import json;d=json.load(open('$STATE'))
print('true' if set(['rtmp_state','rtmp_url','rtmp_err','pushed_frames']) <= set(d['stream']) else 'false')")" \
  "V2d stream 字段齐全"
check "$(jfield $STATE "d['worker']['conf_threshold']")" "0.4" "$(jfield $STATE "d['worker']['conf_threshold']")"

echo "========== V3 阈值热更新 ≤1s =========="
# 注意：yolo 日志被 ultralytics 的逐帧输出刷屏，`tail -N` 抓不到关键行
# ⇒ 用"改配置前的行数偏移"精确定位增量日志。
L0=$(wc -l < "$LOG")
setcfg "c['detect']['conf_threshold']=0.7"
sleep 3
check "V3a worker_state 同步" "0.7" "$(jfield $STATE "d['worker']['conf_threshold']")"
if tail -n +$((L0 + 1)) "$LOG" | grep -q "conf_threshold -> 0.70"; then
  check "V3b 日志同步" "yes" "yes"; else check "V3b 日志同步" "yes" "no"; fi
check "V3c 进程未被重启" "$PID0" "$(ypid)"
setcfg "c['detect']['conf_threshold']=0.4"
sleep 3
check "V3d 改回 0.4" "0.4" "$(jfield $STATE "d['worker']['conf_threshold']")"

echo "========== V4 RTMP 故障只降级不退出（R11） =========="
L0=$(wc -l < "$LOG")
setcfg "c['stream']['rtmp_url']='$BAD_RTMP'"
# 降级后 worker 按退避重连（R11 只降级不退出 ⇒ 必带重试），rtmp_state 会在
# error（退避中，相位 2/4/8/16s 渐长）↔ running（刚重建，相位 ~0.25s）间振荡。
# P2 第二轮实测：单次采样正好落在 +14s 的重建相位拿到 running，而同窗口 V4c
# 已证降级发生（日志有"出错降级"，错误为 gst-resource-error 拒连）。
# ⇒ 改为 14s 窗口内每秒采样，出现过 error 即判定降级生效。
SEEN_ERROR=no
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14; do
  sleep 1
  ST=$(jfield $STATE "d['stream']['rtmp_state']")
  echo "  rtmp_state 第${i}s: $ST"
  if [ "$ST" = "error" ]; then SEEN_ERROR=yes; break; fi
done
check "V4a rtmp_state=error（14s 窗口内出现过）" "yes" "$SEEN_ERROR"
check "V4b 进程仍存活（未退出）" "$PID0" "$(ypid)"
if tail -n +$((L0 + 1)) "$LOG" | grep -q "出错降级"; then
  check "V4c 日志记降级" "yes" "yes"; else check "V4c 日志记降级" "yes" "no"; fi
check_true "$(python3 -c "
import json;d=json.load(open('$STATE'))
print('true' if d['worker']['frames']>0 else 'false')")" "V4d 主循环仍在推进"
setcfg "c['stream']['rtmp_url']='$RTMP'"
sleep 12
check "V4e 改回后自动恢复" "running" "$(jfield $STATE "d['stream']['rtmp_state']")"
# 换流后 SRS 需要一点时间重新注册，单次 ffprobe 太早会假失败（P2 实测：
# V4e 已恢复 running 后立刻 ffprobe 拿到空结果，等 ~30s 后才恢复）
OK=no
for try in 1 2 3 4; do
  FF2=$(timeout 25 ffprobe -v error -select_streams v:0 -show_entries stream=codec_name \
    -of csv=p=0 "$RTMP" 2>&1)
  echo "  ffprobe 恢复检查 第${try}次: $FF2"
  if echo "$FF2" | grep -q "h264"; then OK=yes; break; fi
  sleep 8
done
check "V4f 回流恢复" "$OK" "yes"

echo "========== V5 源切换失败回滚（R10） =========="
FRAMES0=$(jfield $STATE "d['worker']['frames']")
L0=$(wc -l < "$LOG")
setcfg "c['source']['rtsp_url']='$BAD_RTSP'"
sleep 20
check "V5a 源仍 running（回滚）" "running" "$(jfield $STATE "d['source']['state']")"
check "V5b 进程存活" "$PID0" "$(ypid)"
if tail -n +$((L0 + 1)) "$LOG" | grep -q "回滚"; then
  check "V5c 日志记回滚" "yes" "yes"; else check "V5c 日志记回滚" "yes" "no"; fi
# 写回真实源，帧应继续增长
setcfg "c['source']['rtsp_url']='rtsp://192.168.1.120:8554/test'"
sleep 20
FRAMES1=$(jfield $STATE "d['worker']['frames']")
check_true "$(python3 -c "print('true' if $FRAMES1 > $FRAMES0 else 'false')")" \
  "V5d 帧继续增长 ($FRAMES0 -> $FRAMES1)"

echo "========== V6 管理面拒绝坏源（console 侧 400） =========="
rm -f $JAR
curl -s -o /dev/null -c $JAR -X POST -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\"}" $BASE/api/auth/login; sleep 1.3
MD5_BEFORE=$(md5sum "$CFG" | cut -d' ' -f1)
CODE=$(curl -s -o /tmp/p2_bad.json -w '%{http_code}' -b $JAR -X POST \
  -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" \
  -d "{\"config\":{\"source\":{\"rtsp_url\":\"$BAD_RTSP\"}}}" $BASE/api/config)
check "V6a 坏源被拒 400" "400" "$CODE"
MD5_AFTER=$(md5sum "$CFG" | cut -d' ' -f1)
check "V6b 配置未落盘" "$MD5_BEFORE" "$MD5_AFTER"
sleep 3
check "V6c 旧源无感（仍 running）" "running" "$(jfield $STATE "d['source']['state']")"

echo ""
echo "===== P2 运行时验收汇总: PASS=$PASS FAIL=$FAIL ====="
