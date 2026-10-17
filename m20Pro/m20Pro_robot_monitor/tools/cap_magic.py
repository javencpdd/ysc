#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查 basic_server **应答帧**用的帧头 magic —— 决定我们的解码器认不认。

背景：请求用授权 magic（EB90EB90）发出去时，若应答也沿用 EB90EB90，
而 `asdu_parser.decode_frame` 只认 EB91EB90，就会解析失败 →
报文记录永远 no_response（2026-10-17 实际踩到）。

用法： python3 cap_magic.py [pcap] [过滤表达式]
"""
from __future__ import annotations

import re
import subprocess
import sys

PCAP = sys.argv[1] if len(sys.argv) > 1 else "/tmp/m20cap.pcap"
FILTER = sys.argv[2] if len(sys.argv) > 2 else "udp and src host 10.21.33.103"

out = subprocess.run(["tcpdump", "-r", PCAP, "-nn", "-X", FILTER],
                     capture_output=True, text=True).stdout

HDR = re.compile(r"^(\d\d:\d\d:\d\d\.\d+) IP (\S+) > (\S+): UDP, length (\d+)$")
HEXL = re.compile(r"^\s+0x([0-9a-f]{4}):\s+((?:[0-9a-f]{2,4}\s+){1,8})\s+(.*)$")

pkts = []
cur = None
for line in out.splitlines():
    m = HDR.match(line.strip())
    if m:
        if cur:
            pkts.append(cur)
        cur = {"t": m.group(1), "src": m.group(2), "dst": m.group(3),
               "n": int(m.group(4)), "bytes": "", "ascii": ""}
        continue
    if cur is None:
        continue
    m = HEXL.match(line)
    if m:
        cur["bytes"] += m.group(2).replace(" ", "")
        cur["ascii"] += m.group(3)

print("packets: %d" % len(pkts))

# 统计"带 Type/Command 的应答帧"的 magic（UDP 头 8 字节之后才是我们的帧头）
import collections
magic_dist = collections.Counter()
samples = []
for p in pkts:
    raw = bytes.fromhex(p["bytes"][:len(p["bytes"]) // 2 * 2])
    if len(raw) < 24:
        continue
    # 跳过 IP 头(20，0x45 → IHL=5) + UDP 头(8) = 28 字节，才是我们的 16 字节帧头
    ihl = (raw[0] & 0x0F) * 4 if raw else 20
    payload = raw[ihl + 8:]
    magic = payload[:4].hex()
    magic_dist[magic] += 1
    # 只看含 Command 的（应答/上报都带），并单独挑 Type 1101
    if b'"Command":3' in payload or b'"Command": 3' in payload:
        samples.append((p["t"], p["n"], magic, payload[16:80]))

print("\n=== magic 分布（src=%s）===" % FILTER)
for k, v in magic_dist.most_common():
    tag = {b"\xeb\x91\xeb\x90".hex(): "EB91EB90(我们默认)",
           b"\xeb\x90\xeb\x90".hex(): "EB90EB90(授权)"}.get(k, "未知")
    print("  %s  x%d  %s" % (k, v, tag))

print("\n=== Command:3 的帧（最多 6 条）===")
for t, n, magic, head in samples[:6]:
    print("  %s len=%d magic=%s" % (t, n, magic))
    print("      %s" % head.decode("utf-8", "replace")[:120])
