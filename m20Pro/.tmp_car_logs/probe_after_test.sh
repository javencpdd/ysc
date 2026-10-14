#!/bin/bash
# probe_after_test.sh — 轴测试后只读取证（不改任何状态）
cat > /tmp/_ts_probe.py <<'PYEOF'
import json
import urllib.request
try:
    d = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/v1/state", timeout=3).read().decode())
except Exception as e:
    print("ERR:", e)
    raise SystemExit(0)
t = d.get("topics", {})
def ts(k):
    return (t.get(k) or {}).get("ts")
print("server_time=%.1f nav.ts=%s motion.ts=%s basic.ts=%s device.ts=%s fault.ts=%s" % (
    d.get("server_time") or 0, ts("nav"), ts("motion"), ts("basic"), ts("device"), ts("fault")))
n = (t.get("nav") or {}).get("data") or {}
print("nav: located=%s pos=(%.4f,%.4f,%.4f) conf=%.3f reloc=%s" % (
    n.get("located"), n.get("pos_x") or 0, n.get("pos_y") or 0, n.get("pos_z") or 0,
    n.get("confidence") or 0, n.get("relocation")))
m = (t.get("motion") or {}).get("data") or {}
print("motion: vx=%.4f vy=%.4f wz=%.4f H=%.4f" % (
    m.get("linear_x") or 0, m.get("linear_y") or 0, m.get("omega_z") or 0, m.get("height") or 0))
PYEOF
echo "=== [1] ts 刷新检查（间隔 2.5s 两次采样） ==="
python3 /tmp/_ts_probe.py
sleep 2.5
python3 /tmp/_ts_probe.py
echo
echo "=== [2] 日志目录（最新 6 个） ==="
ls -t /var/opt/robot/log/ | head -6
echo
echo "=== [3] 最新目录内容 ==="
D=$(ls -t /var/opt/robot/log/ | head -1)
echo "DIR=$D"
ls -lt "/var/opt/robot/log/$D/" 2>/dev/null | head -15
echo
echo "=== [4] rl_deploy 日志尾部 ==="
RL=$(ls -t /var/opt/robot/log/$D/*[Rr][Ll]* 2>/dev/null | head -1)
echo "RL_LOG=$RL"
if [ -n "$RL" ]; then tail -c 6000 "$RL" | strings | tail -45; fi
echo
echo "=== [5] Basic_server 日志尾部 ==="
BS=$(ls -t /var/opt/robot/log/$D/*[Bb]asic* 2>/dev/null | head -1)
echo "BS_LOG=$BS"
if [ -n "$BS" ]; then tail -c 6000 "$BS" | strings | tail -45; fi
echo
echo "=== [6] MotionInfo.h 结构字段 ==="
MF=/usr/local/include/dridl/dr_msgs/msg/MotionInfo.h
if [ -f "$MF" ]; then grep -nE "(float|double|int32|int64|uint32|uint64|bool) +[a-z_]+" "$MF" | grep -vE "operator|friend|return|constexpr" | head -40; fi
