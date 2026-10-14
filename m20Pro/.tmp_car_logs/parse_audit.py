# -*- coding: utf-8 -*-
"""解析控制台审计拉取文件：还原 02:12-02:13 会话的指令序列。"""
import json
import sys

P = r"C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\audit_pull_20261015.txt"
raw = open(P, encoding="utf-8").read()

i1 = raw.index("===STATUS===")
i2 = raw.index("===STATE===")
audit = json.loads(raw[:i1].strip())
items = audit["items"]

print("总条目数:", len(items))
print("\n--- 样本条目（结构） ---")
for it in items[:2]:
    print(json.dumps(it, ensure_ascii=False))

print("\n--- 命令统计 ---")
from collections import Counter
c = Counter((it.get("cmd"), it.get("result")) for it in items)
for k, v in sorted(c.items()):
    print(k, v)

print("\n--- 非 axis 条目（全量） ---")
for it in items:
    if it.get("cmd") != "axis":
        print(json.dumps(it, ensure_ascii=False))

print("\n--- 时间范围 ---")
print("first ts:", items[0]["ts"], " last ts:", items[-1]["ts"])

# ts 基准：1718907176.17 = 02:12:56.17
BASE = 1718907136.0  # 02:12:16
def rel(ts):
    return ts - BASE

print("\n--- 最近会话时间线（ts>=02:12:16）---")
last = None
for it in items:
    if it["ts"] < BASE:
        continue
    p = it.get("params") or {}
    val = "x={:.3f} y={:.3f} yaw={:.3f} z={:.3f}".format(
        p.get("x", 0), p.get("y", 0), p.get("yaw", 0), p.get("z", 0))
    extra = ""
    if it.get("forced"):
        extra += " FORCED reason=%s" % it.get("reason")
    if it.get("actor") and it["actor"] != "api":
        extra += " actor=%s" % it["actor"]
    line = "+%7.2fs %-11s %-45s %s%s" % (rel(it["ts"]), it.get("cmd"), val, it.get("result"), extra)
    # 相同值连续行折叠
    if line.split(" ", 1)[1].split(" ", 1)[0] == "axis" and last is not None:
        # 折叠连续相同 axis 值
        same = (last.get("cmd") == "axis" and last.get("params") == it.get("params")
                and last.get("result") == it.get("result")
                and (last["ts"] > BASE))
        if same:
            last = it
            continue
    print(line)
    last = it

print("\n--- y / yaw 使用统计（全量） ---")
ys = [abs((it.get("params") or {}).get("y", 0)) for it in items if it.get("cmd") == "axis"]
yaws = [abs((it.get("params") or {}).get("yaw", 0)) for it in items if it.get("cmd") == "axis"]
nz_y = [v for v in ys if v > 0.001]
nz_yaw = [v for v in yaws if v > 0.001]
print("axis 总数:", len(ys))
print("|y|>0 条数:", len(nz_y), " max|y|:", max(nz_y) if nz_y else 0)
print("|yaw|>0 条数:", len(nz_yaw), " max|yaw|:", max(nz_yaw) if nz_yaw else 0)

print("\n--- STATUS ---")
print(raw[i1:i2].strip())
print("\n--- STATE ---")
print(raw[i2:][:1500].strip())
