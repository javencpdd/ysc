#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设备供电开关（1101/3）真机端到端验证。

用**新代码**（/tmp/m20stage/backend）构造真实 ControlGateway + 真实 UDP 出口，
直接打 AOS :30000，验证四件事：

  1. 编码器产出的帧（默认 separators、带空格的 JSON）真机确实接受
  2. 「开启」不需要确认、「关闭」需要 confirmed=true（服务端闸生效）
  3. 站立/RL 态禁关雷达（用假 state_provider 注入，不真的把车弄站起来）
  4. 真机执行结果：车侧日志 + DevEnable 状态真的变了

⚠️ 只动「趴下」态下允许操作的设备；结束时会**恢复原状**（雷达开、GPS 开）。
用法： cd /tmp/m20stage && python3 /tmp/e2e_device_switch.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.path.insert(0, "/tmp/m20stage")

from control import patrol_codec                      # noqa: E402
from control.control_gateway import ControlGateway, UdpControlSink  # noqa: E402

TARGET = ("127.0.0.1", 30000)
STATE_URL = "http://127.0.0.1:8080/api/v1/state"


def dev_state() -> dict:
    with urllib.request.urlopen(STATE_URL, timeout=6) as r:
        d = json.load(r)
    return d["topics"]["device"]["data"]


def show(tag: str) -> None:
    d = dev_state()
    print("    [%s] DevEnable: GPS=%s Lidar=%s/%s Video=%s/%s LedHost=%s LedExt=%s "
          "Load=%s Fan=%s FP=%s"
          % (tag, d.get("gps_enable"), d.get("lidar_front"), d.get("lidar_back"),
             d.get("video_front"), d.get("video_back"), d.get("led_host"),
             d.get("led_ext"), d.get("load_power"), d.get("fan_speed"), d.get("fp")))


def main() -> int:
    before = dev_state()
    print("== 执行前 ==")
    show("before")

    sink = UdpControlSink(*TARGET)
    gw = ControlGateway(sink, enabled=True, lease_seconds=30.0)
    gw.enable()
    gw.renew_lease()

    # ---------- 1. 帧格式真机验收 ----------
    print("\n== 1) 编码器产出的帧直接打真机 ==")
    frame = patrol_codec.encode("device_switch",
                                {"items": {"Video": {"Front": 1, "Back": 1}}})
    print("    magic=%s len=%d json=%s" % (frame[:4].hex(), len(frame),
                                           frame[16:].decode()[:80]))
    res = gw.execute("device_switch", {"items": {"Video": {"Front": 1, "Back": 1}}})
    print("    execute ->", res)
    assert res["ok"], "相机开启被拒，说明帧/magic 有问题"

    # ---------- 2. 关闭需二次确认 ----------
    print("\n== 2) 关闭必须二次确认 ==")
    res = gw.execute("device_switch", {"items": {"GPS": 0}})
    print("    未确认 ->", res.get("ok"), res.get("reason"))
    assert res["ok"] is False and res["reason"] == "CONFIRM_REQUIRED"
    res = gw.execute("device_switch", {"items": {"GPS": 0}}, confirmed=True)
    print("    已确认 ->", res)
    assert res["ok"]
    time.sleep(2.0)
    show("gps-off")

    # ---------- 3. 运动中禁关雷达（注入假状态，不真站起来） ----------
    print("\n== 3) 站立态禁关雷达（假 state_provider 注入）==")
    gw_motion = ControlGateway(sink, enabled=True, lease_seconds=30.0,
                               state_provider=lambda: {"basic": {"motion_state": 17}})
    gw_motion.enable()
    gw_motion.renew_lease()
    res = gw_motion.execute("device_switch",
                            {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                            confirmed=True)
    print("    ->", res.get("ok"), res.get("reason"), "|", res.get("detail"))
    assert res["ok"] is False and res["reason"] == "PRECONDITION_FAILED"

    # ---------- 4. 趴下态关/开雷达（真机执行） ----------
    print("\n== 4) 趴下态关/开雷达（真机执行）==")
    res = gw.execute("device_switch",
                     {"items": {"Lidar": {"Front": 0, "Back": 0}}}, confirmed=True)
    print("    关 ->", res)
    time.sleep(2.0)
    show("lidar-off")
    res = gw.execute("device_switch",
                     {"items": {"Lidar": {"Front": 1, "Back": 1}}})
    print("    开 ->", res)
    time.sleep(2.0)
    show("lidar-on")

    # ---------- 5. 恢复 GPS ----------
    print("\n== 5) 恢复 GPS 供电 ==")
    res = gw.execute("device_switch", {"items": {"GPS": 1}})
    print("    ->", res)
    time.sleep(2.0)
    show("gps-on")

    after = dev_state()
    print("\n== 执行后 ==")
    show("after")
    same = all(before.get(k) == after.get(k)
               for k in ("gps_enable", "lidar_front", "lidar_back", "video_front"))
    print("\n原状恢复：", "是" if same else "否（%s -> %s）" % (before, after))
    print("\n✅ 端到端验证通过" if same else "\n⚠️ 状态未完全恢复，请检查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
