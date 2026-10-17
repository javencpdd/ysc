#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报文记录真机端到端验证：发出 → 机器人响应 → 面板标记是否正确。

只走 HTTP API（与浏览器点按钮同一条路），验证四件事：
  1. 报文原文被留下（hex 可反解、magic 正确）
  2. **有响应的指令被标成 ok**（这一条最关键 —— 证明响应关联真的通）
  3. 被拒的指令标成 rejected 且没有报文
  4. 一条执行了但不回帧的指令 → 超时后标 no_response（语义正确，不是失败）

⚠️ 只动幂等/低危操作，结束恢复原状。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8080"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    return json.load(urllib.request.urlopen(req, timeout=10))


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=10))


def cmd(name, params=None, confirmed=False):
    post("/api/v1/control/lease", {})
    return post("/api/v1/control/command",
                {"name": name, "params": params or {}, "confirmed": confirmed})


def packets():
    return get("/api/v1/control/packets?limit=20")["items"]


def newest(name=None):
    its = packets()
    return next((i for i in its if name is None or i["name"] == name), None)


def wait_status(item, want, timeout=6.0):
    """轮询直到该 seq 的记录变成 want（或超时返回当前）。"""
    deadline = time.time() + timeout
    cur = item
    while time.time() < deadline:
        cur = next((i for i in packets() if i["seq"] == item["seq"]), cur)
        if cur["resp"]["status"] != "pending":
            return cur
        time.sleep(0.25)
    return cur


def main() -> int:
    print("== 准备：开 L1 + 续约 ==")
    print("  ", post("/api/v1/control/enable", {"enable": True, "confirmed": True}))

    # ---------- 1. 有响应的指令（休眠查询 1101/7 —— 真机实测会回 Sleep/Auto/Time）
    print("\n== 1) 休眠查询：应留下报文并收到 ok ==")
    r = cmd("sleep_query")
    assert r["ok"], r
    it = newest("sleep_query")
    assert it is not None, "报文没被记录"
    print("   frame_hex =", it["frame_hex"][:64], "...")
    print("   magic =", it["frame_hex"][:8], "(eb90eb90 = 授权，说明 DeviceControl 类走对通道)")
    it = wait_status(it, "ok")
    resp = it["resp"]
    print("   resp.status =", resp["status"], "| latency =", resp.get("latency_ms"), "ms")
    print("   resp.items  =", json.dumps(resp.get("items"), ensure_ascii=False)[:160])
    assert resp["status"] == "ok", resp
    # 反解验证报文原文
    body = bytes.fromhex(it["frame_hex"])[16:].decode()
    dec = json.loads(body)["PatrolDevice"]
    assert dec["Type"] == 1101 and dec["Command"] == 7, dec
    print("   反解 OK：Type=%s Command=%s" % (dec["Type"], dec["Command"]))

    # ---------- 2. 被拒的指令：有记录、无报文
    print("\n== 2) 未确认关闭 GPS：应标 rejected 且无报文 ==")
    r = cmd("device_switch", {"items": {"GPS": 0}})
    assert r["ok"] is False and r["reason"] == "CONFIRM_REQUIRED"
    it = newest("device_switch")
    print("   frame_hex =", it["frame_hex"], "| resp =", it["resp"]["status"],
          it["resp"].get("reason"))
    assert it["frame_hex"] is None and it["resp"]["status"] == "rejected"

    # ---------- 3. 执行了但（大概率）不回帧的指令 → no_response
    print("\n== 3) 步态查询类无响应指令：超时后应标 no_response ==")
    r = cmd("usage_mode", {"mode": 0})          # 1101/5，幂等（当前就是 0）
    assert r["ok"], r
    it = newest("usage_mode")
    print("   刚发出：", it["resp"]["status"])
    it2 = wait_status(it, "no_response", timeout=8.0)
    print("   等待后：", it2["resp"]["status"], "| latency =", it2["resp"].get("latency_ms"), "ms")
    # 不断言一定是 no_response —— 若厂商其实回帧，那标 ok 也是正确行为。
    # 这里只验证"状态机能从 pending 走到某个终态"，不会永远挂起。
    assert it2["resp"]["status"] in ("ok", "error", "no_response"), it2["resp"]
    if it2["resp"]["status"] == "no_response":
        print("   → 标为 no_response（**不代表车没执行**，只是这一条没有应答帧）")

    # ---------- 4. 统计与最新角标
    print("\n== 4) 统计 ==")
    d = get("/api/v1/control/packets?limit=5")
    print("   stats =", json.dumps(d["stats"], ensure_ascii=False))
    print("   pending =", d["pending"], "| timeout_s =", d["timeout_s"])

    print("\n✅ 报文记录端到端验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
