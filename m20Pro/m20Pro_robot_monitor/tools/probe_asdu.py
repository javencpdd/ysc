#!/usr/bin/env python3
"""M20 Pro ASDU 独立探针（上机只读探测，对应 PLAN T2.1）。

用途：
  1. 验证 **Q1**：监控协议服务端实际监听地址（10.21.31.103 / 10.21.33.103 / 0.0.0.0）；
  2. 验证 **Q3**：机器人是否把状态推回**心跳发送方的同一个 socket**；
  3. 抓取**真实 ASDU 帧**保存为 JSONL，供 T2.4 字段核对与 T2.6 回放回归。

为什么是独立脚本：196 上是 python3.8 且没有本项目依赖，本脚本只依赖标准库，
可直接 scp 上去跑（lite3 的 tools/mock_sender.py 是同样的定位）。

用法（在 196 上）：
    python3 probe_asdu.py                      # 探测默认目标 10.21.31.103:30000，8 秒
    python3 probe_asdu.py --target 10.21.33.103 --seconds 15
    python3 probe_asdu.py --out /tmp/asdu.jsonl   # 保存抓取到的原始帧
    python3 probe_asdu.py --scan                # 依次探测多个候选地址（Q1）

⚠️ 只读：只发心跳（Type 100 / Command 100），不下发任何控制指令。
"""

import argparse
import json
import socket
import struct
import sys
import time

HEAD_TAG = b"\xeb\x91\xeb\x90"
HEADER = struct.Struct("<4sHHB7x")  # tag(4) + dataSize(2) + messageID(2) + protocolType(1) + rsv(7)

#: docs/04 §1.3 五类状态消息（供统计展示）
TOPIC_NAMES = {
    (1002, 6): "基础状态", (1002, 4): "运控状态", (1002, 5): "设备状态",
    (1002, 3): "异常状态", (1101, 7): "休眠查询响应", (1002, 1): "基础状态查询",
}


def encode(type_, command, items=None, time_str=""):
    """16 字节帧头 + JSON（PatrolDevice 信封）。"""
    env = {"PatrolDevice": {
        "Type": int(type_), "Command": int(command),
        "Time": time_str or time.strftime("%Y-%m-%d %H:%M:%S"),
        "Items": items or {},
    }}
    body = json.dumps(env, ensure_ascii=False).encode("utf-8")
    return HEADER.pack(HEAD_TAG, len(body), 0, 1) + body


def decode(data):
    """解一帧；失败返回 None（死信）。"""
    if len(data) < 16:
        return None
    tag, size, _mid, ptype = HEADER.unpack_from(data, 0)
    if tag != HEAD_TAG or ptype != 1:
        return None
    body = data[16:16 + size]
    try:
        return json.loads(body.decode("utf-8"))["PatrolDevice"]
    except Exception:
        return None


def probe(target, port=30000, seconds=8.0, hz=5.0, out=None, verbose=True,
          query=None, send=None, items="{}"):
    """发心跳并接收推送，返回统计与抓取记录。

    query: (type, command) 元组 —— 在 1 秒时额外发一条**查询类**指令（如 1101/7 查休眠），
           收到的同类型响应会单独打印。查询是只读的，不改变机器人状态。
    send:  "type/command" 字符串 —— 在 2 秒时发一条**控制指令**（如 1101/6 唤醒）。
           ⚠️ 会改变机器人状态，使用前确认现场安全；配合 items 传 Items JSON。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    local = sock.getsockname()
    if verbose:
        print("[probe] 目标 %s:%s  本地 socket %s" % (target, port, local))

    start = time.time()
    sent = 0
    records = []
    stats = {}
    next_hb = 0.0
    query_sent = False
    query_responses = []
    send_done = False

    while time.time() - start < seconds:
        now = time.time() - start
        if query and not query_sent and now >= 1.0:
            sock.sendto(encode(query[0], query[1], {}), (target, port))
            query_sent = True
            if verbose:
                print("[probe] 已发送查询 %d/%d" % (query[0], query[1]))
        if send and not send_done and now >= 2.0:
            t, c = send.split("/")
            try:
                payload_items = json.loads(items)
            except ValueError:
                payload_items = {}
            sock.sendto(encode(int(t), int(c), payload_items), (target, port))
            send_done = True
            print("[probe] ⚠️ 已发送控制指令 %s  items=%s" % (send, json.dumps(payload_items)))
        if now >= next_hb:
            sock.sendto(encode(100, 100, {}), (target, port))
            sent += 1
            next_hb = now + 1.0 / max(1.0, hz)
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        msg = decode(data)
        key = None
        if msg:
            key = (msg.get("Type"), msg.get("Command"))
            stats[key] = stats.get(key, 0) + 1
            if query and key == tuple(query):
                query_responses.append(msg)
        records.append({
            "t": round(time.time() - start, 3),
            "from": "%s:%s" % addr,
            "key": "%s/%s" % key if key else None,
            "hex": data.hex(),
            "length": len(data),
        })

    sock.close()
    if verbose and query:
        if query_responses:
            print("[probe] 查询 %d/%d 响应：%s"
                  % (query[0], query[1],
                     json.dumps(query_responses[0].get("Items"), ensure_ascii=False)))
        else:
            print("[probe] 查询 %d/%d 无响应（可能不支持或需其它前置）"
                  % (query[0], query[1]))
    if verbose:
        print("[probe] 心跳发出 %d 条，收到 %d 帧" % (sent, len(records)))
        if len(records):
            print("[probe] ✅ 推送回到了同一个 socket（Q3 成立）")
            for key, count in sorted(stats.items(), key=lambda kv: -kv[1]):
                name = TOPIC_NAMES.get(key, "未知")
                print("        %s/%s  %-8s × %d" % (key[0], key[1], name, count))
        else:
            print("[probe] ❌ 未收到任何推送 —— 检查目标地址/心跳是否被接受（Q1）")

    if out and records:
        with open(out, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("[probe] 已保存 %d 帧到 %s" % (len(records), out))
    return {"sent": sent, "received": len(records), "stats": stats, "records": records}


def scan(port, seconds):
    """依次探测候选地址（Q1）。"""
    candidates = ["10.21.31.103", "10.21.33.103", "10.21.32.103", "127.0.0.1"]
    for host in candidates:
        print("\n===== 探测 %s =====" % host)
        try:
            res = probe(host, port=port, seconds=seconds)
        except OSError as exc:
            print("[probe] 失败: %s" % exc)
            continue
        if res["received"]:
            print(">>> %s 有效（收到 %d 帧）" % (host, res["received"]))
            return host
    print("\n所有候选地址均未收到推送")
    return None


def main():
    ap = argparse.ArgumentParser(description="M20 Pro ASDU 只读探针")
    ap.add_argument("--target", default="10.21.31.103")
    ap.add_argument("--port", type=int, default=30000)
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--hz", type=float, default=5.0)
    ap.add_argument("--out", default="", help="保存抓取帧的 JSONL 路径")
    ap.add_argument("--scan", action="store_true", help="依次探测候选地址")
    ap.add_argument("--query", default="",
                    help="额外发一条查询指令，格式 type/command，如 1101/7（查休眠状态）")
    ap.add_argument("--send", default="",
                    help="**控制**指令，格式 type/command，如 1101/6（休眠/唤醒设置）")
    ap.add_argument("--items", default="{}",
                    help="配合 --send 的 Items JSON，如 '{\"Sleep\": false}'")
    args = ap.parse_args()

    query = None
    if args.query:
        t, c = args.query.split("/")
        query = (int(t), int(c))

    if args.scan:
        scan(args.port, args.seconds)
    else:
        probe(args.target, args.port, args.seconds, args.hz, args.out or None,
              query=query, send=args.send or None, items=args.items)


if __name__ == "__main__":
    main()
