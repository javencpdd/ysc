"""前后端契约冻结测试（PLAN §5.4 / T1.7）。

契约破坏即红 —— 前端只依赖 ``GET /api/v1/schema``，后端换数据源时 schema 不得变。
"""

from state.models import (SCHEMA_VERSION, RobotSnapshot, ServiceSnapshot,
                          snapshot_json_schema)
from state.state_store import StateStore

#: 冻结的顶层字段集合：新增字段需同步升级 SCHEMA_VERSION 并更新此处
EXPECTED_TOP_LEVEL = {
    "schema_version", "type", "server_time", "connected",
    "since_last_update_ms", "topics", "control", "service",
}
EXPECTED_SERVICE_FIELDS = {
    "uptime_seconds", "push_hz", "data_source", "ws_clients",
    "packets_received", "packets_parsed", "packets_error",
    "packets_dropped", "degraded", "degraded_reason",
}


def _store_with_basic():
    store = StateStore(stale_threshold=1.0)
    store.update({"topic": "basic", "fields": {"motion_state": 1},
                  "recv_monotonic": 0.0, "recv_wall": 0.0})
    return store


def test_schema_version_is_pinned():
    assert SCHEMA_VERSION == "1.0"


def test_json_schema_exposes_frozen_fields():
    schema = snapshot_json_schema()
    assert set(schema["properties"]) == EXPECTED_TOP_LEVEL
    assert schema["x_schema_version"] == SCHEMA_VERSION
    # 每个 topic 快照必须带新鲜度语义（前端永不猜新鲜度）
    topic_props = schema["$defs"]["TopicSnapshot"]["properties"]
    assert {"ts", "age_ms", "stale", "data"} <= set(topic_props)


def test_service_snapshot_fields_frozen():
    assert set(ServiceSnapshot.model_fields) == EXPECTED_SERVICE_FIELDS


def test_snapshot_validates_against_model():
    store = _store_with_basic()
    model = store.build_snapshot_model(control={"enabled": False, "estop": False})
    assert isinstance(model, RobotSnapshot)
    dumped = model.model_dump()
    assert set(dumped) == EXPECTED_TOP_LEVEL
    assert dumped["topics"]["basic"]["data"]["motion_state"] == 1
    assert dumped["control"]["enabled"] is False


def test_snapshot_is_json_serializable():
    import json

    store = _store_with_basic()
    payload = store.build_snapshot_model(control={}).model_dump()
    text = json.dumps(payload, ensure_ascii=False)
    assert "motion_state" in text


def test_topic_data_contract_for_each_topic():
    """每个 topic 的字段集合冻结（防协议映射改动悄悄破坏前端）。"""
    expected = {
        "basic": {"motion_state", "motion_state_label", "gait", "charge", "hes",
                  "control_usage_mode", "direction", "ooa", "power_management",
                  "sleep", "version"},
        "motion": {"roll", "pitch", "yaw", "omega_z", "linear_x", "linear_y",
                   "height", "payload", "remain_mile", "joints", "joint_count"},
        "device": {"batteries", "battery_count", "level", "voltage",
                   "temperature", "charging", "level_left", "level_right",
                   "motor_temperatures", "gps", "cpu"},
        "fault": {"errors", "error_count", "has_fault"},
        "sleep": {"sleep", "auto", "time"},
        "nav": {"nav_value", "located", "pos_x", "pos_y", "pos_z",
                "roll", "pitch", "yaw", "confidence"},
    }
    from ingestion.mock_source import MockSource
    from ingestion import asdu_parser

    store = StateStore(stale_threshold=5.0)
    src = MockSource()
    for topic in ("basic", "motion", "device", "fault", "sleep", "nav"):
        data = src.build_bytes(topic, 0)
        store.update(asdu_parser.parse_frame(data))
    snap = store.snapshot()
    assert set(snap["topics"]) == set(expected)
    for topic, keys in expected.items():
        assert keys <= set(snap["topics"][topic]["data"]), topic
