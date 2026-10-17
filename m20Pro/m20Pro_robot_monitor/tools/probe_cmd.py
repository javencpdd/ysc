#!/usr/bin/env python3
"""M20 basic_server 指令探测器（只读取证优先）。

用法（在 AOS 上跑，或任意能到 30000/UDP 的机器）：

    python3 probe_cmd.py <type> <command> [json_items] [--auth] [--wait 秒]

例：
    python3 probe_cmd.py 1101 11            # GetAutoResetJointsZero
    python3 probe_cmd.py 1101 7             # GetSleepConfig
    python3 probe_cmd.py 1101 2 '{"Front":1,"Back":1}' --auth

输出：收发的原始帧 hex + 解析后的应答。
"""
from __future__ import annotations

import json
import socket
import struct
import sys
import time

HEAD = b"\xeb\x91\xeb\x90"
AUTH = b"\xeb\x90\xeb\x90"
HDR = struct.Struct("<4sHHB7x")


def frame(t, c, items, tag=HEAD, mid=0):
    body = json.dumps(
        {"PatrolDevice": {"Type": t, "Command": c,
                          "Time": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "Items": items}},
        separators=(",", ":"),
    ).encode("utf-8")
    return HDR.pack(tag, len(body), mid, 0x01) + body


def decode(data):
    for tag in (HEAD, AUTH):
        if data[:4] != tag:
            continue
        size = HDR.unpack(data[:16])[1]
        try:
            obj = json.loads(data[16:16 + size].decode("utf-8", "replace"))
        except Exception:
            return tag.hex(), None
        return tag.hex(), obj
    return data[:4].hex(), None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    auth = "--auth" in sys.argv
    wait = 3.0
    if "--wait" in sys.argv:
        wait = float(sys.argv[sys.argv.index("--wait") + 1])
    if len(args) < 2:
        print(__doc__)
        return 2
    if args and args[0] == "listen":
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", 0))
        s.settimeout(wait)
        s.sendto(frame(100, 100, {}, HEAD), ("127.0.0.1", 30000))
        end = time.time() + wait
        while time.time() < end:
            try:
                data, _ = s.recvfrom(65535)
            except socket.timeout:
                break
            _, obj = decode(data)
            if obj is None:
                continue
            inner = obj.get("PatrolDevice", obj)
            if (inner.get("Type"), inner.get("Command")) != (1002, 5):
                continue
            led = inner.get("Items", {}).get("Led", {})
            dev = inner.get("Items", {}).get("DevEnable", {})
            print("Led=%s  DevEnable=%s" % (json.dumps(led, ensure_ascii=False),
                                            json.dumps(dev, ensure_ascii=False)))
            break
        return 0
    typ, cmd = int(args[0]), int(args[1])
    items = json.loads(args[2]) if len(args) > 2 else {}
    tag = AUTH if auth else HEAD

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 0))
    s.settimeout(wait)
    # 先注册（心跳），否则 basic_server 不知道往哪儿回
    s.sendto(frame(100, 100, {}, tag), ("127.0.0.1", 30000))
    time.sleep(0.2)
    payload = frame(typ, cmd, items, tag)
    print("SEND %d/%d tag=%s len=%d\n  %s" % (typ, cmd, tag.hex(), len(payload), payload.hex()))
    s.sendto(payload, ("127.0.0.1", 30000))
    end = time.time() + wait
    got = 0
    while time.time() < end:
        try:
            data, _ = s.recvfrom(65535)
        except socket.timeout:
            break
        t, obj = decode(data)
        if obj is None:
            continue
        inner = obj.get("PatrolDevice", obj)
        if inner.get("Type") == 100 and inner.get("Command") == 100:
            continue  # 心跳应答，忽略
        if inner.get("Type") == 1002:
            continue  # 状态上报（10Hz 会淹没应答）
        got += 1
        print("RECV tag=%s\n  %s" % (t, json.dumps(obj, ensure_ascii=False)))
        if got >= 3:
            break
    if not got:
        print("RECV (none, %ds timeout)" % wait)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
