#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 m20cap.pcap 中提取「厂商 App -> basic_server:30000」的非心跳指令包。

用法： python3 cap2.py [pcap路径]
"""
import re
import sys
import json
import collections

PCAP = sys.argv[1] if len(sys.argv) > 1 else "/tmp/m20cap.pcap"
FILTER = "udp and src host 10.21.33.11 and dst port 30000"

proc = subprocess_run = None
import subprocess

r = subprocess.run(
    ["tcpdump", "-r", PCAP, "-nn", "-A", FILTER],
    capture_output=True,
    text=True,
)
if not r.stdout:
    sys.stderr.write("tcpdump empty: rc=%s err=%s\n" % (r.returncode, r.stderr[:400]))
    sys.exit(1)

HDR = re.compile(
    r"^(\d\d:\d\d:\d\d\.\d+)\s+IP\s+(\S+)\s+>\s+(\S+):\s+UDP,\s+length\s+(\d+)$"
)

pkts = []
cur = None
for line in r.stdout.splitlines():
    m = HDR.match(line.rstrip())
    if m:
        if cur:
            pkts.append(cur)
        cur = {"t": m.group(1), "n": int(m.group(4)), "body": ""}
    elif cur is not None:
        cur["body"] += line
if cur:
    pkts.append(cur)

sys.stdout.write("total packets from App: %d\n" % len(pkts))
sys.stdout.write(
    "length dist: %s\n\n" % collections.Counter(p["n"] for p in pkts).most_common()
)

sys.stdout.write("=== 非心跳指令包 (length != 99) ===\n")
for p in pkts:
    if p["n"] == 99:
        continue
    b = p["body"]
    i = b.find("{")
    j = b.rfind("}")
    payload = b[i : j + 1] if (i >= 0 and j > i) else b
    sys.stdout.write("%s  len=%d\n    %s\n" % (p["t"], p["n"], payload[:500]))
