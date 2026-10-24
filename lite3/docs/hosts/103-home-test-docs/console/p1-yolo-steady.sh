#!/usr/bin/env bash
# yolo 稳态验证：经 console API 启动 → 等 45s 冷启动 → 验证出帧 + RTMP 推流 → 停止
# （P1-3 补测：E3b 只证明了进程存活，未证明到达稳态）
#
# ★本脚本必须在 **103 主机上**执行（读 /home/test/yolo8 本地路径 + 本机 ffprobe）：
#   scp p1-yolo-steady.sh ysc@192.168.1.103:/tmp/ && ssh ysc@192.168.1.103 'bash /tmp/p1-yolo-steady.sh'
#   2026-10-22 教训：在本机（Windows）直接跑，token/日志/pid/ffprobe 全部落空，
#   表现为"配置文件不存在"+全链 401，一度误判为线上事故。
set -u
BASE=http://192.168.1.103:8090
TOKEN=$(python3 -c "import json;print(json.load(open('/home/test/yolo8/config/yolo8.json'))['console']['token'])")
JAR=/tmp/p1_cookies.txt
LOG=/home/test/yolo8/logs/yolo-publish.log

# 登录建会话（写接口双因子：Cookie + X-Yolo-Token；登录限流 1req/s）
rm -f $JAR
curl -s -o /dev/null -c $JAR -X POST -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\"}" $BASE/api/auth/login; sleep 1.3

# 记录启动前的日志行数，用于判定"新"推理行
BEFORE=$(wc -l < "$LOG")
echo "启动前日志行数: $BEFORE"

echo "--- 经 console 启动 yolo ---"
curl -s -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" \
  -d '{"target":"yolo"}' $BASE/api/service/start
echo ""

echo "--- 等待 45s（冷启动 ~35s：RTSP 首帧 + TRT engine 加载）---"
sleep 45

echo "--- 新增日志行（启动 banner 之后的部分）---"
tail -n +$((BEFORE + 1)) "$LOG" | head -20
echo "..."

echo "--- 进程状态 ---"
PID=$(cat /home/test/yolo8/logs/yolo.pid 2>/dev/null)
if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
  echo "yolo 进程存活 PID=$PID"
  ps -p "$PID" -o pid,etime,%cpu,rss,cmd --no-headers
  echo "CPU 亲和:"; taskset -pc "$PID" 2>/dev/null || cat /proc/$PID/status | grep Cpus_allowed_list
else
  echo "!! yolo 进程不在运行"
fi

echo "--- RTMP 推流验证（ffprobe 拉回流）---"
timeout 25 ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 \
  "rtmp://172.31.68.227:1936/live/lite3_yolo" 2>&1

echo "--- 控制台视角的状态 ---"
curl -s -b $JAR "$BASE/api/service/status?target=yolo"
echo ""

echo "--- 停止 yolo ---"
curl -s -b $JAR -X POST -H 'Content-Type: application/json' -H "X-Yolo-Token: $TOKEN" \
  -d '{"target":"yolo"}' $BASE/api/service/stop
echo ""
sleep 3
curl -s -b $JAR "$BASE/api/service/status?target=yolo"
echo ""
