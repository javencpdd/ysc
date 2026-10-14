# -*- coding: utf-8 -*-
"""审计复盘：时间线写入本地文件。"""
import json

P = r"C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\audit_pull_20261015.txt"
OUT = r"C:\Users\19046\Desktop\特种机器人\云深处\m20Pro\.tmp_car_logs\audit_timeline.txt"
raw = open(P, encoding="utf-8").read()
i1 = raw.index("===STATUS===")
i2 = raw.index("===STATE===")
items = json.loads(raw[:i1].strip())["items"]
items = list(reversed(items))  # 时间正序

BASE = 1718907136.0  # 02:12:16 附近

def rel(ts):
    return ts - BASE

lines = []
lines.append("总条目数: %d" % len(items))
lines.append("时间范围: +%.1fs ~ +%.1fs (相对 02:12:16)" % (rel(items[0]["ts"]), rel(items[-1]["ts"])))
lines.append("")

# 全量：非 axis 或有特殊字段的条目
lines.append("=== 全量非 axis / 特殊条目 ===")
for it in items:
    if it.get("command") != "axis" or it.get("forced") or it.get("result") != "ok":
        lines.append(json.dumps(it, ensure_ascii=False))

lines.append("")
lines.append("=== 时间线（全部条目，连续相同 axis 值折叠为 xN） ===")
prev = None
count = 0
for it in items:
    p = it.get("params") or {}
    key = (it.get("command"), p.get("x"), p.get("y"), p.get("z"), p.get("yaw"), p.get("roll"), p.get("pitch"),
           it.get("result"), it.get("actor"), it.get("reason"))
    if prev is not None and key == prev:
        count += 1
        continue
    if count > 0:
        lines.append("        ... 上一行重复 x%d" % count)
        count = 0
    p = it.get("params") or {}
    lines.append("+%7.3fs %-10s x=%6.3f y=%6.3f yaw=%6.3f z=%6.3f | %-8s actor=%-8s %s%s" % (
        rel(it["ts"]), it.get("command"),
        p.get("x", 0), p.get("y", 0), p.get("yaw", 0), p.get("z", 0),
        it.get("result"), it.get("actor") or "-",
        ("reason=%s" % it.get("reason")) if it.get("reason") else "",
        (" FORCED" if it.get("forced") else "")))
    prev = key
if count > 0:
    lines.append("        ... 上一行重复 x%d" % count)

# y/yaw 统计
ys = [abs((it.get("params") or {}).get("y", 0)) for it in items if it.get("command") == "axis"]
yaws = [abs((it.get("params") or {}).get("yaw", 0)) for it in items if it.get("command") == "axis"]
xs = [abs((it.get("params") or {}).get("x", 0)) for it in items if it.get("command") == "axis"]
lines.append("")
lines.append("=== 统计 ===")
lines.append("axis 条目: %d  |x|>0: %d max=%.3f |y|>0: %d max=%.3f |yaw|>0: %d max=%.3f" % (
    len(xs), len([v for v in xs if v > 0.001]), max(xs) if xs else 0,
    len([v for v in ys if v > 0.001]), max(ys) if ys else 0,
    len([v for v in yaws if v > 0.001]), max(yaws) if yaws else 0))

lines.append("")
lines.append("=== STATUS ===")
lines.append(raw[i1:i2].strip())
lines.append("")
lines.append("=== STATE ===")
lines.append(raw[i2:][:1200].strip())

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("written", OUT)
