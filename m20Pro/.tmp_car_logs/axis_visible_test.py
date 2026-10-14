#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""axis_visible_test.py — 可见速度流式轴指令实测（M20 Pro 控制台 v1）

目的
    验证"轴指令能否让车体以可见速度移动"。前序测试疑似因控制值过小（x=0.1）
    导致位移不可感知；本脚本以阶梯速度（默认 0.4 / 0.7 / 1.0）持续流式发送，
    并同步记录定位坐标（1Hz 定位）与实时速度，用数据而非肉眼判定。

关键机制（逆向结论，决定本脚本设计）
    - rl_deploy 侧 MonitorSteer 看门狗：150ms 内无新 /STEER 数据即清零速度
      → 必须 >=7Hz 连续发送；本脚本 20Hz。
    - 控制台 AxisWatchdog：feed 后 250ms 无新 feed 即 trip（零位 + 软急停）；
      axis/stop 也会 pause → trip → 软急停。
      → 本脚本 **不用** continuous 模式、**不用** axis/stop，
        改为一发一发地（continuous=False）以 20Hz 节奏发送，停止时只发零位，
        让 rl_deploy 侧 150ms 看门狗自然清零 —— 不触发软急停、不改变状态机。
    - rl_deploy HandlerSteer 在 gait 0x1001 下对 x/y 有 0.5 缩放；车侧
      cmd_vel_limit.yml vx_limit=0.40 m/s。实际速度上限受此约束，阶梯测试
      可解出"控制值 → 实际速度"的映射曲线。

用法
    python3 axis_visible_test.py                # 默认 3 轮：0.4/2.5s, 0.7/2.5s, 1.0/3.0s
    python3 axis_visible_test.py 0.5 2.0        # 单轮：x=0.5 持续 2 秒
    python3 axis_visible_test.py --dry          # 只做前置检查，不发送
    python3 axis_visible_test.py --allow-low    # 允许非站立状态运行（默认拒绝）

前置
    - 车体站立（motion_state ∈ {1, 17}）、常规模式（control_usage_mode=0）、
      未充电、无急停
    - 车周围留有 >=2m 空间，有人守候在硬件急停旁
"""
from __future__ import print_function

import json
import math
import sys
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:8080/api/v1"
CTL = BASE + "/control"

HZ = 20.0
INTERVAL = 1.0 / HZ

DEFAULT_ROUNDS = [(0.4, 2.5), (0.7, 2.5), (1.0, 3.0)]
SNAP_EVERY = 5          # 每 5 帧记一次快照
LEASE_INTERVAL = 1.5    # 续约周期（TTL 5s）
PAUSE_BETWEEN = 1.5     # 轮间停顿时长


# ---------------------------------------------------------------- HTTP 工具
def _post(path, payload=None, timeout=2.0):
    data = json.dumps(payload).encode() if payload is not None else b"{}"
    req = urllib.request.Request(CTL + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"ok": None, "error": str(e)}


def _get_state(timeout=2.5):
    try:
        with urllib.request.urlopen(BASE + "/state", timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return {}


def extract(state):
    t = state.get("topics", {})
    n = (t.get("nav") or {}).get("data") or {}
    m = (t.get("motion") or {}).get("data") or {}
    b = (t.get("basic") or {}).get("data") or {}
    dev = (t.get("device") or {}).get("data") or {}
    return {
        "loc": n.get("located"), "x": n.get("pos_x"), "y": n.get("pos_y"), "z": n.get("pos_z"),
        "vx": m.get("linear_x"), "vy": m.get("linear_y"), "wz": m.get("omega_z"),
        "h": m.get("height"),
        "ms": b.get("motion_state"), "gait": b.get("gait"), "mode": b.get("control_usage_mode"),
        "charging": dev.get("charging"),
    }


def _fmt(s):
    return ("pos=(%.3f,%.3f,%.3f) v=(%.3f,%.3f,%.3f) H=%.3f | loc=%s ms=%s gait=%s mode=%s chg=%s"
            % (s["x"] or 0, s["y"] or 0, s["z"] or 0,
               s["vx"] or 0, s["vy"] or 0, s["wz"] or 0, s["h"] or 0,
               s["loc"], s["ms"], s["gait"], s["mode"], s["charging"]))


def _dist(a, b):
    if None in (a.get("x"), a.get("y"), b.get("x"), b.get("y")):
        return None
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


# ---------------------------------------------------------------- 主流程
def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    allow_low = "--allow-low" in args
    args = [a for a in args if not a.startswith("--")]

    rounds = []
    while len(args) >= 2:
        rounds.append((float(args[0]), float(args[1])))
        args = args[2:]
    if not rounds:
        rounds = list(DEFAULT_ROUNDS)
    rounds = [(max(0.0, min(1.0, x)), max(0.5, min(5.0, d))) for x, d in rounds]

    print("=" * 74)
    print("M20 轴指令可见速度实测 | 轮次: %s" % (["x=%.2f/%.1fs" % r for r in rounds],))
    print("=" * 74)

    # ---- 前置检查
    s0 = extract(_get_state())
    print("[前置] 当前:", _fmt(s0))
    problems = []
    if s0["ms"] not in (1, 17) and not allow_low:
        problems.append("motion_state=%s 不在 (1=站立, 17=RL)" % s0["ms"])
    if s0["mode"] not in (None, 0):
        problems.append("control_usage_mode=%s != 0（常规模式）" % s0["mode"])
    if s0["charging"]:
        problems.append("charging=True（充电中禁止）")
    if problems:
        print("[前置] !! 不满足：")
        for p in problems:
            print("        -", p)
        print("       先让车回到站立态（可用控制台指令 stand_up），或 --allow-low 强制继续")
        sys.exit(2)
    print("[前置] OK 检查通过。提醒：车前方请留 >=2m 空间，人守在硬件急停旁")
    if dry:
        print("[dry] 仅检查，不发送。退出。")
        return 0

    # ---- 使能 + 租约
    print("[准备] enable:", _post("/enable", {"enable": True, "confirmed": True}))
    print("[准备] lease :", _post("/lease"))

    stop_evt = threading.Event()

    def lease_loop():
        while not stop_evt.is_set():
            _post("/lease")
            stop_evt.wait(LEASE_INTERVAL)

    threading.Thread(target=lease_loop, daemon=True).start()

    csv_path = "/tmp/axis_visible_%s.csv" % time.strftime("%H%M%S")
    csv = open(csv_path, "w")
    csv.write("phase,rel_t,pos_x,pos_y,pos_z,vx,vy,wz,h,loc,ms,gait,mode,ok,reason\n")
    t_start = time.time()

    def snap(phase, ok=None, reason=""):
        s = extract(_get_state())
        csv.write("%s,%.2f,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" % (
            phase, time.time() - t_start,
            s["x"], s["y"], s["z"], s["vx"], s["vy"], s["wz"], s["h"],
            s["loc"], s["ms"], s["gait"], s["mode"],
            ok if ok is not None else "", reason))
        csv.flush()
        return s

    def send_axis(xv):
        return _post("/axis", {"x": xv, "y": 0.0, "z": 0.0,
                               "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                               "continuous": False})

    ok_cnt = 0
    rej_cnt = 0
    last_reason = ""

    try:
        print("[基线] 静止快照:")
        b0 = snap("base0"); print("        ", _fmt(b0))
        time.sleep(0.6)
        b0 = snap("base1"); print("        ", _fmt(b0))

        for ri, (xv, dur) in enumerate(rounds, 1):
            tag = "r%d_x%.2f" % (ri, xv)
            print("-" * 74)
            print("[轮 %d] x=%.2f 持续 %.1fs @%.0fHz" % (ri, xv, dur, HZ))
            r_start = snap(tag + "_start")
            n = int(dur * HZ)
            next_t = time.monotonic()
            for i in range(n):
                r = send_axis(xv)
                if isinstance(r, dict) and r.get("ok"):
                    ok_cnt += 1
                else:
                    rej_cnt += 1
                    last_reason = (r or {}).get("reason") or (r or {}).get("error") or "?"
                if i % SNAP_EVERY == 0:
                    s = snap(tag, r.get("ok") if isinstance(r, dict) else None, last_reason)
                    print("   t=%5.1fs %s | ok=%d rej=%d"
                          % (time.time() - t_start, _fmt(s), ok_cnt, rej_cnt))
                next_t += INTERVAL
                d = next_t - time.monotonic()
                if d > 0:
                    time.sleep(d)
            send_axis(0.0)   # 轮末零位（不发 axis/stop，避免软急停）
            time.sleep(PAUSE_BETWEEN)
            r_end = snap(tag + "_end")
            dist = _dist(r_start, r_end)
            print("   [轮 %d 结果] %s" % (ri, _fmt(r_end)))
            print("   [轮 %d 位移] %s m" % (ri, ("%.4f" % dist) if dist is not None else "n/a"))
            print("   [轮 %d 速度] vx=%s vy=%s" % (ri, r_end["vx"], r_end["vy"]))

        print("-" * 74)
        print("[收尾] 发送零位 + 关闭控制")
        send_axis(0.0)
        time.sleep(0.6)
        s_end = snap("final")
        print("        ", _fmt(s_end))
        print("        disable:", _post("/enable", {"enable": False, "confirmed": True}))
        td = _dist(b0, s_end)
        print("        [总位移] %s m（基线 → 最终）" % (("%.4f" % td) if td is not None else "n/a"))
    finally:
        stop_evt.set()
        csv.close()
        print("=" * 74)
        print("统计: ok=%d rej=%d last_reason=%s" % (ok_cnt, rej_cnt, last_reason))
        print("CSV : %s" % csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
