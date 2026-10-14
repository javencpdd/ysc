#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prep_stand.py — 起立预备：enable + lease + stand_up + 等待站起到位（只发运动状态指令，不发轴值）"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8080/api/v1"


def post(path, payload=None, timeout=3.0):
    data = json.dumps(payload).encode() if payload is not None else b"{}"
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "error": str(e)}


def get(path, timeout=3.0):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def state():
    d = get("/state")
    t = d.get("topics", {})
    b = (t.get("basic") or {}).get("data") or {}
    m = (t.get("motion") or {}).get("data") or {}
    n = (t.get("nav") or {}).get("data") or {}
    return {"ms": b.get("motion_state"), "h": m.get("height"),
            "mode": b.get("control_usage_mode"),
            "pos": (n.get("pos_x"), n.get("pos_y"))}


cs = get("/control/status")
c = cs.get("control", {})
print("[控制台] enabled=%s estop=%s lease_active=%s" % (
    c.get("enabled"), c.get("estop"), c.get("lease_active")))

s = state()
print("[当前  ] ms=%s H=%.3f mode=%s pos=(%s, %s)" % (
    s.get("ms"), s.get("h") or 0, s.get("mode"),
    s.get("pos", (None, None))[0], s.get("pos", (None, None))[1]))

if s.get("ms") == 17 and (s.get("h") or 0) > 0.5:
    print("[INFO] 车已站立，无需起立。")
    raise SystemExit(0)

print("[enable ]", post("/control/enable", {"enable": True, "confirmed": True}))
print("[lease  ]", post("/control/lease"))
print("[stand  ]", post("/control/command", {"name": "stand_up", "params": {}}))

ok = False
for i in range(20):
    time.sleep(1.0)
    s = state()
    print("  t=%2ds  ms=%-3s H=%.3f" % (i + 1, s.get("ms"), s.get("h") or 0))
    if s.get("ms") == 17 and (s.get("h") or 0) > 0.5:
        ok = True
        break

if ok:
    print("[OK] 已站起（ms=17, H=%.3f），可以开始标定测试" % (s.get("h") or 0))
else:
    print("[WARN] 20 秒内未到位：ms=%s H=%s —— 请检查车况后再决定" % (s.get("ms"), s.get("h")))
