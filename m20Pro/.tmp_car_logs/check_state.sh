#!/bin/bash
# check_state.sh — 只读侦察：控制台状态 + 车体状态摘要（不改任何东西）
echo "=== [1] control/status ==="
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/control/status
echo
echo "=== [2] state digest ==="
curl -s --max-time 5 http://127.0.0.1:8080/api/v1/state > /tmp/state_now.json
python3 - <<'PYEOF'
import json
try:
    d = json.load(open("/tmp/state_now.json"))
except Exception as e:
    print("state parse error:", e)
    raise SystemExit
t = d.get("topics", {})
print("top-level keys:", sorted(d.keys()))
print("topic keys:", sorted(t.keys()))
for k in ("basic", "motion", "device", "fault", "nav", "sleep"):
    node = t.get(k) or {}
    data = node.get("data") or {}
    print("--- topic %s --- ts=%s" % (k, node.get("ts")))
    if k == "motion":
        ks = sorted(data.keys())
        print("    keys:", ks)
        for f in ks:
            lf = f.lower()
            if any(s in lf for s in ("state", "gait", "vel", "linear", "speed", "height")):
                print("    %s = %s" % (f, data.get(f)))
    elif k == "nav":
        for f in ("nav_value", "nav_status", "nav_error_code", "located", "pos_x", "pos_y", "pos_z", "task_name"):
            if f in data:
                print("    %s = %s" % (f, data.get(f)))
        ks = sorted(data.keys())
        print("    all keys:", ks)
    else:
        ks = sorted(data.keys())
        print("    keys:", ks[:60])
        if k == "device":
            for f in ks:
                lf = f.lower()
                if any(s in lf for s in ("usage", "mode", "charging", "battery", "soc")):
                    print("    %s = %s" % (f, data.get(f)))
PYEOF
echo "=== [3] clock / uptime ==="
date
uptime
echo "=== [4] control service alive? ==="
pgrep -af "uvicorn|main.py|monitor" | head -5
