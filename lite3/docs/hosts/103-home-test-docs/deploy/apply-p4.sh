#!/usr/bin/env bash
# P4 部署：备份 → scp → 双侧 md5 比对 → 真机 py3.8 编译检查。
# 用法：bash deploy/apply-p4.sh [目标主机，默认 lite3-f20-1-103]
set -euo pipefail

HOST="${1:-lite3-f20-1-103}"
APP=/home/test/yolo8
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TS=$(date +%Y%m%d-%H%M%S)
BK="$APP/deploy/backup-p4-$TS"

# 相对 lite3/docs/hosts/103-home-test-docs/ 的路径 → 远端同路径
FILES=(
  src/export_engine.py
  src/run_tracker_publish.py
  src/RobotController/RobotController.py
  src/RobotController/YoloWrapper/YoloWrapper.py
  src/p4-unit.py
  console/server.py
  console/static/index.html
  console/p4-unit.py
  console/p5-unit.py
  console/p5-accept.sh
  console/p4-accept.sh
  deploy/install-retention.sh
  deploy/lite3-yolo8.logrotate
  deploy/lite3-yolo8-journald.conf
)

echo "== 备份到 $BK"
ssh "$HOST" "mkdir -p '$BK/src/RobotController/YoloWrapper' '$BK/console/static' '$BK/deploy'"
for f in "${FILES[@]}"; do
  ssh "$HOST" "if [ -f '$APP/$f' ]; then cp -p '$APP/$f' '$BK/$f'; fi"
done
ssh "$HOST" "cp -p '$APP/config/yolo8.json' '$BK/yolo8.json' 2>/dev/null || true"

echo "== 上传"
for f in "${FILES[@]}"; do
  scp -q "$HERE/$f" "$HOST:$APP/$f"
done

echo "== md5 比对（本地 vs 远端）"
fail=0
for f in "${FILES[@]}"; do
  a=$(md5sum "$HERE/$f" | cut -d' ' -f1)
  b=$(ssh "$HOST" "md5sum '$APP/$f' | cut -d' ' -f1")
  if [ "$a" = "$b" ]; then
    printf '  OK   %-46s %s\n' "$f" "$a"
  else
    printf '  BAD  %-46s local=%s remote=%s\n' "$f" "$a" "$b"
    fail=1
  fi
done
[ "$fail" -eq 0 ] || { echo "md5 不一致，中止"; exit 1; }

echo "== 远端 py3.8 编译"
ssh "$HOST" "cd '$APP' && python3 -m py_compile src/export_engine.py src/run_tracker_publish.py src/RobotController/RobotController.py src/RobotController/YoloWrapper/YoloWrapper.py src/p4-unit.py console/server.py console/p4-unit.py && echo '  py_compile OK'"

echo "== 去 CR（幂等）"
for f in "${FILES[@]}"; do
  ssh "$HOST" "sed -i 's/\r\$//' '$APP/$f'"
done

echo "完成。备份：$BK"
echo "提示：改 .py 需重启 console；worker 已改 → 需 ctl restart yolo 才生效。"
