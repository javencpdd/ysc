#!/usr/bin/env python3
"""detail_state.py — 单次快照：打印 basic/motion/nav/device/fault 关键值（只读）"""
import json
import sys
import urllib.request

URL = "http://127.0.0.1:8080/api/v1/state"

try:
    with urllib.request.urlopen(URL, timeout=3) as r:
        d = json.loads(r.read().decode())
except Exception as e:
    print("ERROR: 无法获取 state:", e)
    sys.exit(1)

t = d.get("topics", {})
b = (t.get("basic") or {}).get("data") or {}
m = (t.get("motion") or {}).get("data") or {}
n = (t.get("nav") or {}).get("data") or {}
dev = (t.get("device") or {}).get("data") or {}
f = (t.get("fault") or {}).get("data") or {}

print("server_time =", d.get("server_time"))
print("connected   =", d.get("connected"))
print("--- basic ---")
for k in sorted(b.keys()):
    print("  %-28s = %s" % (k, b.get(k)))
print("--- motion (subset) ---")
for k in ("height", "linear_x", "linear_y", "omega_z", "payload", "remain_mile", "roll", "pitch", "yaw"):
    print("  %-28s = %s" % (k, m.get(k)))
print("--- nav ---")
for k in ("located", "pos_x", "pos_y", "pos_z", "confidence", "nav_value",
          "nav_status", "nav_error_code", "relocation", "loop_count"):
    print("  %-28s = %s" % (k, n.get(k)))
print("--- device (power) ---")
for k in ("charging", "level_left", "level_right", "voltage_left", "voltage_right",
          "battery_count", "temperature"):
    print("  %-28s = %s" % (k, dev.get(k)))
print("--- fault ---")
print("  has_fault =", f.get("has_fault"), " error_count =", f.get("error_count"))
for e in (f.get("errors") or [])[:10]:
    print("   -", e)
