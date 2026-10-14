"""M1 全链路集成测试：MockSource → 解析 → StateStore → 快照（PLAN §14.2）。

无真机、零依赖 —— MockSource 发射的是**真实字节帧**，因此解析这一段也被真实跑通。
"""

import time

from control.control_gateway import RecordingSink
from ingestion import asdu_parser
from ingestion.mock_source import MockSource
from state.models import RobotSnapshot
from state.state_store import StateStore


def _run_pipeline(store=None, topic=None):
    """跑一遍 mock → 解析 → 入库，返回 (store, source)。"""
    store = store or StateStore(stale_threshold=0.5, link_timeout=3.0)
    src = MockSource()

    def on_frame(frame):
        raw = frame["data"]
        try:
            store.update(asdu_parser.parse_frame(raw, frame.get("addr")), raw)
        except Exception:  # noqa: BLE001 - 解析失败不应中断采集
            store.record_error(raw, "parse failed")

    src.on_frame(on_frame)
    src.emit_once(topic)
    return store, src


def test_all_mock_topics_reach_snapshot():
    """Mock 覆盖 6 类（5 类 docs + 真机实测新增的 nav）。"""
    store, src = _run_pipeline()
    snap = store.snapshot()
    assert set(snap["topics"]) == {"basic", "motion", "device", "fault", "sleep", "nav"}
    assert snap["connected"] is True
    assert src.emitted == 6
    counters = store.counters()
    assert counters["received"] == 6 and counters["errors"] == 0


def test_motion_topic_has_16_joints():
    store, _ = _run_pipeline(topic="motion")
    data = store.snapshot()["topics"]["motion"]["data"]
    assert len(data["joints"]) == 16
    assert data["joint_names"][3] == "LF_wheel"


def test_device_topic_reports_battery():
    store, _ = _run_pipeline(topic="device")
    data = store.snapshot()["topics"]["device"]["data"]
    assert data["battery_count"] >= 1
    assert data["level"] == 86.5


def test_snapshot_validates_as_contract_model():
    store, _ = _run_pipeline()
    model = store.build_snapshot_model(control={"enabled": False, "estop": False})
    assert isinstance(model, RobotSnapshot)
    # MockSource 首帧 seq=0 → MotionState=0（空闲，开机初始态最贴近真机）
    assert model.topics["basic"].data["motion_state_label"] == "空闲"


def test_stale_degradation_after_source_stops():
    """停更 → stale 标记 + connected 转 False（前端据此置灰 + 红条）。"""
    store = StateStore(stale_threshold=0.05, link_timeout=0.2)
    _run_pipeline(store=store)
    assert store.snapshot()["connected"] is True
    time.sleep(0.35)
    snap = store.snapshot()
    assert snap["connected"] is False
    assert all(t["stale"] for t in snap["topics"].values())
    # 旧值仍在（不许假数据，但也不清空）
    assert snap["topics"]["basic"]["data"]["motion_state"] is not None


def test_replay_mode_emits_recorded_frames():
    import json
    import os
    import tempfile

    src = MockSource()
    frame = src.build_bytes("basic", 0)
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        fh.write(json.dumps({"t": 0.0, "hex": frame.hex()}) + "\n")
        path = fh.name
    try:
        replay = MockSource(replay_file=path)
        assert len(replay._replay) == 1
        store = StateStore(stale_threshold=5.0)
        replay.on_frame(lambda f: store.update(
            asdu_parser.parse_frame(f["data"]), f["data"]))
        assert replay.replay_all() == 1
        assert store.snapshot()["topics"]["basic"]["data"]["version"] == "PRO"
    finally:
        os.unlink(path)


def test_control_snapshot_is_included():
    from control.control_gateway import ControlGateway

    store, _ = _run_pipeline()
    gw = ControlGateway(RecordingSink(), enabled=False)
    snap = store.build_snapshot_model(control=gw.status()).model_dump()
    assert snap["control"]["enabled"] is False
    assert snap["control"]["estop"] is False
