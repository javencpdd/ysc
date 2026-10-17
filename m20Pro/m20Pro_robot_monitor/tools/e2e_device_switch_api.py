#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""走 HTTP API 的设备开关端到端验证（完全复现前端行为）。

不 import 任何后端模块 —— 只打 `POST /api/v1/control/command`，
与浏览器里点按钮走的是同一条路（含 L1 开关 / 租约 / 四道闸 + 新增第五道闸）。

⚠️ 结束时会恢复原状。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.load(r)


def dev() -> dict:
    return get("/api/v1/state")["topics"]["device"]["data"]


def show(tag: str) -> None:
    d = dev()
    print("    [%-9s] GPS=%s Lidar=%s/%s Video=%s/%s LedHost=%s LedExt=%s Load=%s Fan=%s FP=%s"
          % (tag, d.get("gps_enable"), d.get("lidar_front"), d.get("lidar_back"),
             d.get("video_front"), d.get("video_back"), d.get("led_host"),
             d.get("led_ext"), d.get("load_power"), d.get("fan_speed"), d.get("fp")))


def cmd(name, params, confirmed=False):
    # 前端靠 WS 保活定期续约（默认租约 5s）；脚本没有 WS，必须手动续，
    # 否则第二步之后就会 LEASE_EXPIRED —— 这不是缺陷，是设计使然。
    post("/api/v1/control/lease", {})
    return post("/api/v1/control/command",
                {"name": name, "params": params, "confirmed": confirmed})


def main() -> int:
    before = dev()
    print("== 执行前 =="); show("before")

    print("\n== 开 L1（需确认）+ 续约 ==")
    print("   ", post("/api/v1/control/enable", {"enable": True, "confirmed": True}))
    print("   ", post("/api/v1/control/lease", {}))

    print("\n== 1) 开启不需要确认 ==")
    r = cmd("device_switch", {"items": {"Lidar": {"Front": 1, "Back": 1}}})
    print("   ", r.get("ok"), r.get("result"), r.get("detail", ""))
    assert r["ok"], r
    time.sleep(3.0); show("lidar-on")

    print("\n== 2) 关闭必须二次确认（confirmed=false 应被拒）==")
    r = cmd("device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}})
    print("   ", r.get("ok"), r.get("reason"), "|", r.get("detail"))
    assert r["ok"] is False and r["reason"] == "CONFIRM_REQUIRED"
    show("unchanged")

    print("\n== 3) 确认后关闭（趴下态允许）==")
    r = cmd("device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}}, confirmed=True)
    print("   ", r.get("ok"), r.get("result"))
    assert r["ok"], r
    time.sleep(2.5); show("lidar-off")

    print("\n== 4) GPS 关 / 开 ==")
    r = cmd("device_switch", {"items": {"GPS": 0}}, confirmed=True)
    print("    关:", r.get("ok")); time.sleep(2.0); show("gps-off")
    r = cmd("device_switch", {"items": {"GPS": 1}})
    print("    开:", r.get("ok")); time.sleep(2.0); show("gps-on")

    print("\n== 5) 非法参数被服务端拦下（BAD_PARAMS，不发报文）==")
    r = cmd("device_switch", {"items": {"JOINTS_POWER": 0}}, confirmed=True)
    print("   ", r.get("ok"), r.get("reason"), "|", r.get("detail"))
    assert r["ok"] is False and r["reason"] == "BAD_PARAMS"

    print("\n== 6) 审计可查 ==")
    audit = get("/api/v1/control/audit").get("items") or []
    for a in audit[:6]:
        print("    %s %-14s %-8s %s" % (
            time.strftime("%H:%M:%S", time.localtime(a["ts"])),
            a["command"], a["result"], a.get("reason") or ""))

    after = dev()
    keys = ("gps_enable", "lidar_front", "lidar_back", "video_front", "video_back",
            "led_host", "led_ext", "load_power", "fan_speed")
    same = all(before.get(k) == after.get(k) for k in keys)
    print("\n原状恢复：", "是" if same else "否 -> %s" % {k: (before.get(k), after.get(k))
                                                     for k in keys if before.get(k) != after.get(k)})
    print("\n" + ("✅ HTTP 端到端全部通过" if same else "⚠️ 状态有差异，请检查"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
