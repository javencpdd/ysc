"""journal 日志行的解析、级别分类与过滤（纯逻辑，可单测）。

日志来源是 ``journalctl -u m20-ai-detect -o short-iso``，行长这样：
  2026-06-21T00:05:49+0800 gos m20-ai-detect[15586]: clock offset ... (auto-measured ...)
注意：journal 的时间戳是**本机时钟**（被车队 PTP 钉在 2024），仅用于排序，
展示时应注明；权威时间以 JSONL 的 ts 为准（ADR-004）。
"""
from __future__ import annotations

import re
from typing import List, Optional

LEVELS = ("all", "alert", "fail", "boot", "ok")

_RULES = (
    ("alert", re.compile(r"ALERT|alert", re.I)),
    ("fail", re.compile(r"FAIL|fail|error|ERROR|Traceback|Exception", re.I)),
    ("boot", re.compile(r"clock offset|start cap=|spawn capture|stopped|startup", re.I)),
)


def classify(line: str) -> str:
    """把一行日志归类：alert / fail / boot / ok。"""
    for level, pattern in _RULES:
        if pattern.search(line):
            return level
    return "ok"


def split_ts(line: str) -> Optional[str]:
    """取出 short-iso 行首的时间戳（无则 None）。"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+\-]\d{4})\s", line)
    return m.group(1) if m else None


def filter_lines(lines: List[str], level: str = "all", query: str = "") -> List[str]:
    """按级别与关键字过滤。level=all 时不过滤级别；query 大小写不敏感子串匹配。"""
    q = (query or "").strip().lower()
    out = []
    for ln in lines:
        if level != "all" and classify(ln) != level:
            continue
        if q and q not in ln.lower():
            continue
        out.append(ln)
    return out
