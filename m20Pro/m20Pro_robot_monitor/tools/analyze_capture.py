#!/usr/bin/env python3
"""ASDU 抓包分析（PLAN T2.4：真机字段核对）。

输入：``probe_asdu.py --out`` 抓到的 JSONL（每行 {"t","from","key","hex","length"}）
输出：按消息类型统计 + Items 结构 + 与本工程映射表的差异，作为《ASDU 字段核对报告》的数据源。

用法（在 PC 上，需本项目 venv）：
    python tools/analyze_capture.py tools/capture/asdu_loopback_20261015.jsonl
    python tools/analyze_capture.py <file> --sample 2     # 每类打印 2 条样本
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from ingestion import asdu_parser  # noqa: E402


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize_obj(obj, depth=0, max_items=6):
    """把 dict/list 压成一行摘要。"""
    pad = "  " * depth
    if isinstance(obj, dict):
        keys = list(obj.keys())
        shown = keys[:max_items]
        parts = []
        for k in shown:
            v = obj[k]
            if isinstance(v, (dict, list)):
                parts.append("%s: %s" % (k, type(v).__name__ + ("(%d)" % len(v))))
            else:
                parts.append("%s: %r" % (k, v))
        more = " … +%d 项" % (len(keys) - max_items) if len(keys) > max_items else ""
        return pad + "{" + ", ".join(parts) + more + "}"
    if isinstance(obj, list):
        head = obj[:3]
        return pad + "[%d 项] 例: %s" % (len(obj), ", ".join(repr(h) for h in head))
    return pad + repr(obj)


def main():
    ap = argparse.ArgumentParser(description="分析 ASDU 抓包")
    ap.add_argument("path")
    ap.add_argument("--sample", type=int, default=1, help="每类打印样本条数")
    args = ap.parse_args()

    rows = load(args.path)
    print("抓包文件: %s" % args.path)
    print("总帧数: %d\n" % len(rows))

    counter = Counter()
    errors = Counter()
    by_key = {}

    for row in rows:
        data = bytes.fromhex(row["hex"])
        try:
            parsed = asdu_parser.parse_frame(data)
        except Exception as exc:  # noqa: BLE001
            errors[str(exc)] += 1
            continue
        key = (parsed["type"], parsed["command"])
        counter[key] += 1
        by_key.setdefault(key, []).append((row, parsed))

    print("=" * 78)
    print("消息类型统计（docs/04 §1.3 对照）")
    print("=" * 78)
    for (t, c), n in counter.most_common():
        topic = asdu_parser.TOPIC_BY_KEY.get((t, c), "❗未登记")
        known = "✅" if (t, c) in asdu_parser.TOPIC_BY_KEY else "❗文档未载/未登记"
        print("%-9s %-14s × %-4d  %s" % ("%d/%d" % (t, c), topic, n, known))

    if errors:
        print("\n解析失败（死信）:")
        for msg, n in errors.most_common():
            print("  %s × %d" % (msg, n))

    print("\n" + "=" * 78)
    print("各类消息结构（Items 顶层键 + 样本）")
    print("=" * 78)
    for (t, c), items in sorted(by_key.items(), key=lambda kv: kv[0]):
        topic = asdu_parser.TOPIC_BY_KEY.get((t, c), "未登记")
        row, parsed = items[0]
        print("\n--- %d/%d  %s  (n=%d) ---" % (t, c, topic, len(items)))
        print(" Items 顶层键: %s" % list(parsed["items"].keys()))
        print(" 结构: %s" % summarize_obj(parsed["items"]).strip())
        print(" 映射字段: %s" % ", ".join(sorted(parsed["fields"].keys())))
        for extra in range(min(args.sample, len(items))):
            r, p = items[extra]
            if extra:
                print("  样本#%d: %s" % (extra, summarize_obj(p["items"]).strip()[:200]))
            # 关节/电池/错误列表单独确认
            f = p["fields"]
            if "joints" in f:
                print("  关节数: %d（期望 16）" % len(f["joints"]))
            if "battery_count" in f:
                print("  电池块数: %d" % f["battery_count"])
            if "error_count" in f:
                print("  异常条数: %d" % f["error_count"])

    # 未登记类型提醒
    unknown = [k for k in counter if k not in asdu_parser.TOPIC_BY_KEY]
    if unknown:
        print("\n" + "!" * 78)
        print("发现未在 TOPIC_BY_KEY 登记的消息类型（需补进 asdu_parser + 计划书 §10.4）：")
        for t, c in unknown:
            print("  %d/%d × %d" % (t, c, counter[(t, c)]))
            row, parsed = by_key[(t, c)][0]
            print("    Items: %s" % json.dumps(parsed["items"], ensure_ascii=False)[:300])
        print("!" * 78)


if __name__ == "__main__":
    main()
