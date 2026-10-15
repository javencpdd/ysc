#!/usr/bin/env python3
"""轴指令"车侧反馈"采集探针（2026-10-16 加，横移排查用）。

在 **196** 上运行（本机回环访问控制台 API），以 5Hz 同时采样三处：

    - topics.motion : linear_x / linear_y / omega_z / roll / pitch / yaw / height
    - topics.basic  : motion_state / gait / control_usage_mode
    - watchdog      : timed_active / timed_remaining / channel / sent_frames

用法（196 上，控制台已启动）：
    python3 tools/probe_motion.py 240            # 采 240 秒，逐行打到 stdout
    python3 tools/probe_motion.py 240 > /tmp/x.log

读法（先看基线，再看响应）：
    · **基线**（未发指令，站立）：linear_x/y 有 ±0.0x 的噪声底——判断"有没有真动"
      必须减掉这个底再看抬升；
    · 发 y 令后 **vy 明显抬升 / roll 有偏移** = 策略层在执行（姿态/速度响应）；
    · vy 抬升但机身不挪 = 侧滑 / 摩擦受限；
    · vy 恒在噪声底 = 动力层没执行（换通道 / 换步态再验）。
"""

import json
import sys
import time
import urllib.request

STATE = "http://127.0.0.1:8080/api/v1/state"
CTRL = "http://127.0.0.1:8080/api/v1/control/status"


def get(url):
    with urllib.request.urlopen(url, timeout=3) as resp:
        return json.load(resp)


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def main():
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
    t0 = time.time()
    n = 0
    print("# t_off    ms   gait   vx       vy       wz      roll   pitch   yaw     height  timed rem  ch    sent",
          flush=True)
    while time.time() - t0 < duration:
        try:
            st = get(STATE)
            m = ((st.get("topics") or {}).get("motion") or {}).get("data") or {}
            b = ((st.get("topics") or {}).get("basic") or {}).get("data") or {}
            w = (get(CTRL) or {}).get("watchdog") or {}
            print("%8.2f  %-4s %-5s  %8.4f %8.4f %7.4f  %6.2f %6.2f %7.2f  %5.3f  %-5s %4.1f %-5s %s" % (
                time.time() - t0, b.get("motion_state"), b.get("gait"),
                fnum(m.get("linear_x")), fnum(m.get("linear_y")), fnum(m.get("omega_z")),
                fnum(m.get("roll")), fnum(m.get("pitch")), fnum(m.get("yaw")), fnum(m.get("height")),
                w.get("timed_active"), fnum(w.get("timed_remaining")), w.get("channel"),
                w.get("sent_frames")), flush=True)
        except Exception as exc:  # noqa: BLE001 - 探针不能因单次失败中断
            print("ERR %s" % exc, flush=True)
        n += 1
        time.sleep(0.2)
    print("# PROBE_DONE samples=%d" % n, flush=True)


if __name__ == "__main__":
    main()
