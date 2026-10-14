"""真机抓包回归测试（PLAN T2.6）：用 196 上抓到的**真实 ASDU 帧**验证解析层。

抓包文件由 ``tools/probe_asdu.py --out`` 生成（2026-10-14 于 196 上抓取，
目标 127.0.0.1:30000，10 秒 226 帧）。文件不存在时跳过，保证 M1 无真机也能跑。
"""

import json
import os

import pytest

from ingestion import asdu_parser
from state.state_store import StateStore

CAPTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tools", "capture", "asdu_loopback_20261015.jsonl")

pytestmark = pytest.mark.skipif(not os.path.isfile(CAPTURE),
                                reason="真机抓包文件不存在（无真机时跳过）")


def _rows():
    with open(CAPTURE, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_every_real_frame_parses_without_error():
    """真机 226 帧必须零死信——这是解析层最强的回归。"""
    rows = _rows()
    assert len(rows) > 100
    errors = []
    for row in rows:
        try:
            asdu_parser.parse_frame(bytes.fromhex(row["hex"]))
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    assert errors == []


def test_real_topics_cover_documented_and_discovered():
    rows = _rows()
    seen = {}
    for row in rows:
        parsed = asdu_parser.parse_frame(bytes.fromhex(row["hex"]))
        seen.setdefault(parsed["topic"], 0)
        seen[parsed["topic"]] += 1
    # docs/04 五类 + 实测新增（心跳应答 ack、导航定位 nav）
    for topic in ("basic", "motion", "device", "fault", "ack", "nav"):
        assert topic in seen, "真机抓包中未出现 %s" % topic
    # 运控 10Hz 应占多数
    assert seen["motion"] > seen["basic"]


def test_real_motion_has_16_joints():
    """轮足 16 关节 —— 由真机数据最终确认（不再是推断）。"""
    for row in _rows():
        parsed = asdu_parser.parse_frame(bytes.fromhex(row["hex"]))
        if parsed["topic"] == "motion":
            assert len(parsed["fields"]["joints"]) == 16
            assert parsed["fields"]["joint_names"][3] == "LF_wheel"
            return
    pytest.fail("抓包中没有运控帧")


def test_real_device_reports_two_batteries():
    """实测双电池（BatteryList 2 项 + BatteryStatus 左右）。"""
    for row in _rows():
        parsed = asdu_parser.parse_frame(bytes.fromhex(row["hex"]))
        if parsed["topic"] == "device":
            fields = parsed["fields"]
            assert fields["battery_count"] == 2
            assert "level_left" in fields and "level_right" in fields
            assert len(fields["motor_temperatures"]) == 16   # 16 个电机温度
            return
    pytest.fail("抓包中没有设备帧")


def test_real_nav_provides_position():
    """实测新增：导航 + 定位位姿（PosX/Y/Z + RPY + 置信度）。"""
    for row in _rows():
        parsed = asdu_parser.parse_frame(bytes.fromhex(row["hex"]))
        if parsed["topic"] == "nav":
            f = parsed["fields"]
            for key in ("pos_x", "pos_y", "pos_z", "roll", "pitch", "yaw", "confidence"):
                assert f[key] is not None, key
            return
    pytest.fail("抓包中没有导航帧")


def test_replay_capture_into_state_store():
    """把真机抓包灌进 StateStore，快照必须可用（端到端回归）。"""
    store = StateStore(stale_threshold=30.0, link_timeout=30.0)
    for row in _rows():
        store.update(asdu_parser.parse_frame(bytes.fromhex(row["hex"])),
                     bytes.fromhex(row["hex"]))
    snap = store.snapshot()
    assert snap["connected"] is True
    assert store.counters()["errors"] == 0
    assert "motion" in snap["topics"] and "nav" in snap["topics"]
