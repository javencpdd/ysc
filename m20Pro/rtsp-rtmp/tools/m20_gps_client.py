#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M20 直连协议客户端（TCP 30001）—— 直接向 basic_server 索取 GPS
协议（从 /home/tank/m20/server.js 逆出）:
  帧 = SYNC[EB 91 EB 90] + len(UInt16LE) + msgId(UInt16LE) + fmt(UInt8=1) + UTF-8 JSON
  心跳 = {"PatrolDevice":{"Type":100,"Command":100,"Time":"...","Items":{}}}  每 800ms
  GPS  = 响应中 {"PatrolDevice":{"Type":1002,"Command":5,"Items":{"GPS":{...}}}}
"""
import datetime
import json
import socket
import struct
import sys
import time

SYNC = bytes([235, 145, 235, 144])
HOST, PORT = "127.0.0.1", 30001


def build(t, cmd, items, seq, hdr_len):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(
        {"PatrolDevice": {"Type": t, "Command": cmd, "Time": now, "Items": items}},
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    h = bytearray(hdr_len)
    h[0:4] = SYNC
    h[4:6] = struct.pack("<H", len(payload))
    h[6:8] = struct.pack("<H", seq % 65536)
    h[8] = 1
    return bytes(h) + payload


def scan_frames(buf, hdr_len):
    """按给定头长度扫描完整帧，返回 [(json, 帧总长)]"""
    out = []
    i = 0
    while True:
        p = buf.find(SYNC, i)
        if p < 0 or len(buf) < p + hdr_len:
            break
        ln = struct.unpack_from("<H", buf, p + 4)[0]
        total = hdr_len + ln
        if len(buf) < p + total:
            break
        body = buf[p + hdr_len:p + total]
        try:
            out.append((json.loads(body.decode("utf-8")), total))
        except Exception:
            out.append((None, total))
        i = p + total
    return out


def main():
    hdr_len = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    print("连接 %s:%d  (假设 HEADER_LEN=%d, 观察 %.0fs)" % (HOST, PORT, hdr_len, dur))

    s = socket.create_connection((HOST, PORT), timeout=5)
    s.settimeout(1.0)
    seq = 1
    buf = b""
    t0 = time.time()
    next_hb = t0
    got_gps = None
    types_seen = {}

    while time.time() - t0 < dur:
        now = time.time()
        if now >= next_hb:
            s.sendall(build(100, 100, {}, seq, hdr_len))
            seq += 1
            next_hb = now + 0.8
        try:
            d = s.recv(8192)
            if d:
                buf += d
        except socket.timeout:
            pass

    s.close()
    print("共收到 %d 字节" % len(buf))
    if not buf:
        print("  对端无任何返回 —— 可能 HEADER_LEN 不对，或需要其它握手")
        print("  原始前 64 字节:", buf[:64].hex(" "))
        return

    print("  原始前 96 字节 hex:", buf[:96].hex(" "))
    frames = scan_frames(buf, hdr_len)
    print("  解析出 %d 帧" % len(frames))
    for i, (j, total) in enumerate(frames[:8]):
        if j is None:
            print("   [%d] 非 JSON（%d 字节）" % (i, total))
            continue
        pd = j.get("PatrolDevice", {})
        t, c = pd.get("Type"), pd.get("Command")
        types_seen[(t, c)] = types_seen.get((t, c), 0) + 1
        items = pd.get("Items") or {}
        keys = list(items.keys())[:8]
        print("   [%d] Type=%s Command=%s Items键=%s" % (i, t, c, keys))
        if t == 1002 and c == 5 and "GPS" in items:
            got_gps = items["GPS"]

    print()
    print("  出现过的 (Type, Command) 组合:", types_seen)
    print()
    if got_gps:
        g = got_gps
        print("  ✅ 拿到 GPS 数据（完整）:")
        print(json.dumps(g, ensure_ascii=False, indent=2))
        lat = g.get("Latitude") or 0
        lon = g.get("Longitude") or 0
        fix = g.get("fixQuality", g.get("FixQuality"))
        sats = g.get("numSatellites", g.get("NumSatellites"))
        print()
        if lat == 0 and lon == 0:
            print("  ❌ 经纬度为 0 —— 无有效定位（与 /dev/ttyS5 那路 GPS 一致）")
        else:
            print("  ✅ 有效坐标: %.6f, %.6f" % (lat, lon))
    else:
        print("  ❌ 本次未收到 Type=1002/Command=5 的 GPS 帧")


if __name__ == "__main__":
    main()
