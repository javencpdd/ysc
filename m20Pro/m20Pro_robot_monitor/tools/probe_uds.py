#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测 /tmp/basic_server.cmd.socket 的 CLI 语法（需 root）。

已知：
- 送裸 JSON 对象 → "Error: Invalid JSON - Invalid value. (offset: 0)"
- 送 JSON 对象   → "Error: Input is not a JSON array"
⇒ 它要的是 **JSON 数组**。本脚本批量试几种数组形态，只发无害内容。

用法： sudo -E env PYTHONPATH=backend python3 /tmp/probe_uds.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time

UDS = "/tmp/basic_server.cmd.socket"

CANDIDATES = [
    "help",
    "?",
    "[]",
    '[{"PatrolDevice":{"Type":1101,"Command":3,"Time":"2026-10-17 02:33:00","Items":{"Video":{"Front":1,"Back":1}}}}]',
    '["PatrolDevice",1101,3,{"Video":{"Front":1,"Back":1}}]',
    '[1101,3,{"Video":{"Front":1,"Back":1}}]',
    '[{"Type":1101,"Command":3,"Items":{"Video":{"Front":1,"Back":1}}}]',
    '[{"cmd":"help"}]',
    '[{"cmd":"list"}]',
]


def send(payload: str) -> str:
    if not os.path.exists(UDS):
        return "<socket not found>"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.5)
    try:
        s.connect(UDS)
    except OSError as exc:
        return "<connect %s>" % exc
    try:
        s.sendall(payload.encode("utf-8"))
        chunks = []
        while True:
            try:
                d = s.recv(65535)
            except socket.timeout:
                break
            if not d:
                break
            chunks.append(d)
        return b"".join(chunks).decode("utf-8", "replace")[:400]
    except OSError as exc:
        return "<OSError %s>" % exc
    finally:
        s.close()


def main() -> int:
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            sys.stdout.write(">>> %s\n    %s\n" % (p[:120], send(p)))
        return 0
    for p in CANDIDATES:
        sys.stdout.write(">>> %s\n    %s\n" % (p[:120], send(p)))
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
