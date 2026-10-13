#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
m20_dog_query.py —— M20 机器狗直连协议查询工具（TCP 30001）

协议（从 /home/tank/m20/server.js 逆向得出，已实测打通）：

  帧结构 (HEADER_LEN = 16):
    [0:4]   同步头 SYNC = EB 91 EB 90
    [4:6]   ASDU 长度      UInt16 LE   (JSON 载荷字节数)
    [6:8]   消息序号        UInt16 LE
    [8]     载荷格式        1 = JSON
    [9:16]  保留（填 0）
    [16:]   UTF-8 JSON: {"PatrolDevice":{"Type":T,"Command":C,"Time":"YYYY-MM-DD HH:MM:SS","Items":{...}}}

  心跳: Type=100, Command=100, Items={}   建议 800ms 一次
  上行遥测(设备主动周期上报):
    (1002, 3)  ErrorList
    (1002, 4)  MotionStatus, MotorStatus
    (1002, 5)  BatteryList, BatteryStatus, DeviceTemperature, Led, GPS, DevEnable, CPU
    (1002, 6)  BasicStatus
    (1002, 7)  NavStatus, LocationStatus

用法:
  python3 m20_dog_query.py gps          # 只取 GPS（一次）
  python3 m20_dog_query.py gps --json   # JSON 输出
  python3 m20_dog_query.py watch        # 持续打印 GPS
  python3 m20_dog_query.py dump         # 打印各类遥测的键
  python3 m20_dog_query.py raw [秒]     # 原始帧转储
"""
import argparse
import datetime
import json
import socket
import struct
import sys
import time

SYNC = bytes([235, 145, 235, 144])
HEADER_LEN = 16
HOST = "127.0.0.1"
PORT = 30001
GPS_TYPE, GPS_CMD = 1002, 5
HEARTBEAT = (100, 100)


def build_frame(t, cmd, items, seq):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(
        {"PatrolDevice": {"Type": t, "Command": cmd, "Time": now, "Items": items}},
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    h = bytearray(HEADER_LEN)
    h[0:4] = SYNC
    h[4:6] = struct.pack("<H", len(payload))
    h[6:8] = struct.pack("<H", seq % 65536)
    h[8] = 1
    return bytes(h) + payload


def iter_frames(buf, state):
    """增量解析缓冲里的完整帧；state 用于跨调用保留未消费的残余"""
    buf = state["buf"]
    while True:
        p = buf.find(SYNC)
        if p < 0:
            # 无同步头：保留末尾 3 字节，防止半个同步头被丢掉
            buf = buf[-3:] if len(buf) > 3 else buf
            break
        if len(buf) < p + HEADER_LEN:
            buf = buf[p:]
            break
        ln = struct.unpack_from("<H", buf, p + 4)[0]
        total = HEADER_LEN + ln
        if len(buf) < p + total:
            buf = buf[p:]
            break
        body = buf[p + HEADER_LEN:p + total]
        buf = buf[p + total:]
        try:
            yield json.loads(body.decode("utf-8"))
        except Exception:
            yield None
    state["buf"] = buf


def collect(seconds=6.0, want_types=None, hb_interval=0.8):
    """连接 → 发心跳 → 收集指定类型的最新一帧"""
    out = {}
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.settimeout(0.5)
    st = {"buf": b""}
    seq = 1
    t0 = time.time()
    nxt = t0
    try:
        while time.time() - t0 < seconds:
            now = time.time()
            if now >= nxt:
                s.sendall(build_frame(HEARTBEAT[0], HEARTBEAT[1], {}, seq))
                seq += 1
                nxt = now + hb_interval
            try:
                d = s.recv(16384)
                if d:
                    st["buf"] += d
            except socket.timeout:
                pass
            for j in iter_frames(None, st):
                if not j:
                    continue
                pd = j.get("PatrolDevice") or {}
                key = (pd.get("Type"), pd.get("Command"))
                if want_types is None or key in want_types:
                    out[key] = pd.get("Items") or {}
    finally:
        s.close()
    return out


def cmd_gps(args):
    if args.watch:
        while True:
            r = collect(2.5, {(GPS_TYPE, GPS_CMD)})
            g = r.get((GPS_TYPE, GPS_CMD), {}).get("GPS", {})
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            if g:
                lat, lon = g.get("Latitude", 0), g.get("Longitude", 0)
                ok = "定位有效" if (lat or lon) else "无定位"
                print("[%s] lat=%.6f lon=%.6f alt=%.1f fix=%s sats=%s/%s  %s" % (
                    ts, lat, lon, g.get("Altitude", 0), g.get("FixQuality"),
                    g.get("NumSatellites"), g.get("VisibleSatellites"), ok))
            else:
                print("[%s] 未收到 GPS 帧" % ts)
            time.sleep(1)
    r = collect(args.seconds, {(GPS_TYPE, GPS_CMD)})
    g = r.get((GPS_TYPE, GPS_CMD), {}).get("GPS", {})
    if not g:
        print("未收到 GPS 帧", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
    else:
        print("M20 狗端 GPS:")
        for k, v in g.items():
            print("  %-20s = %s" % (k, v))
        lat, lon = g.get("Latitude", 0), g.get("Longitude", 0)
        print()
        print("  %s" % ("✅ 有效坐标 %.6f, %.6f" % (lat, lon) if (lat or lon)
                        else "❌ 经纬度为 0 —— 无有效定位（FixQuality=%s）" % g.get("FixQuality")))
    return 0


def cmd_dump(args):
    r = collect(6.0, None)
    print("收到的遥测类型（Type, Command）→ Items 键：")
    for k in sorted(r.keys(), key=lambda x: (x[0] or 0, x[1] or 0)):
        print("  (%s, %s)  %s" % (k[0], k[1], list(r[k].keys())))
    print()
    print("完整内容（前 2 类）：")
    for k in sorted(r.keys(), key=lambda x: (x[0] or 0, x[1] or 0))[:2]:
        print("--- (%s, %s) ---" % k)
        print(json.dumps(r[k], ensure_ascii=False, indent=2)[:1500])
    return 0


def cmd_raw(args):
    dur = float(args.seconds)
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.settimeout(0.5)
    st = {"buf": b""}
    seq = 1
    t0 = time.time()
    nxt = t0
    n = 0
    while time.time() - t0 < dur:
        now = time.time()
        if now >= nxt:
            blob = build_frame(*HEARTBEAT, {}, seq)
            s.sendall(blob)
            seq += 1
            nxt = now + 0.8
            print(">>> 发送心跳 (%d 字节): %s" % (len(blob), blob[:24].hex(" ")))
        try:
            d = s.recv(16384)
            if d:
                st["buf"] += d
        except socket.timeout:
            pass
        for j in iter_frames(None, st):
            n += 1
            print("<<< 帧 %d: %s" % (n, json.dumps(j, ensure_ascii=False)[:180] if j else "(非JSON)"))
            if n >= 12:
                s.close()
                return 0
    s.close()
    return 0


def main():
    ap = argparse.ArgumentParser(description="M20 机器狗直连协议查询")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("gps", help="查询 GPS")
    p.add_argument("--json", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--seconds", type=float, default=6.0)
    p.set_defaults(func=cmd_gps)

    p = sub.add_parser("dump", help="转储各类遥测键")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("raw", help="原始帧转储")
    p.add_argument("seconds", nargs="?", default="6")
    p.set_defaults(func=cmd_raw)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
