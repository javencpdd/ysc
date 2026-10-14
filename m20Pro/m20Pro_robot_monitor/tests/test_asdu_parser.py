"""ASDU 解析器单测（ACL）：帧头校验 + 5 类消息字段映射（PLAN §10）。"""

import pytest

from errors import ProtocolError
from ingestion import asdu_parser as ap


def _frame(type_, command, items):
    return ap.encode_frame(type_, command, items)


def test_header_layout_is_16_bytes_with_tag():
    data = _frame(100, 100, {})
    assert data[:4] == ap.HEAD_TAG
    assert len(data) >= ap.HEADER_SIZE
    # 帧头布局：4s tag(0-3) + H dataSize(4-5) + H messageID(6-7) + B protocolType(8) + 7B 保留
    assert data[8] == ap.PROTOCOL_TYPE_JSON
    assert data[9:16] == b"\x00" * 7


def test_decode_roundtrip_all_topics():
    cases = {
        (1002, 6): {"BasicStatus": {"MotionState": 1, "Gait": 0x1001, "Version": "PRO"}},
        (1002, 4): {"MotionStatus": {"Roll": 0.1},
                    "MotorStatus": {"Joint": [0.0] * 16}},
        (1002, 5): {"BatteryList": [{"BatteryLevel": 88.0, "Voltage": 50.1}]},
        (1002, 3): {"ErrorList": [{"errorCode": 7, "component": "motor"}]},
        (1101, 7): {"Sleep": 0, "Auto": True, "Time": 10},
    }
    for (t, c), items in cases.items():
        decoded = ap.decode_frame(_frame(t, c, items))
        assert (decoded["type"], decoded["command"]) == (t, c)
        assert decoded["items"] == items


def test_reject_bad_tag():
    data = bytearray(_frame(1002, 6, {}))
    data[0] = 0x00
    with pytest.raises(ProtocolError):
        ap.decode_frame(bytes(data))


def test_reject_short_and_truncated():
    with pytest.raises(ProtocolError):
        ap.decode_frame(b"\xeb\x91\xeb\x90\x00")          # 不足 16 字节
    data = _frame(1002, 6, {"BasicStatus": {}})
    with pytest.raises(ProtocolError):
        ap.decode_frame(data[:ap.HEADER_SIZE + 3])        # 帧体截断


def test_basic_mapping_and_labels():
    parsed = ap.parse_frame(_frame(1002, 6, {"BasicStatus": {
        "MotionState": 1, "Gait": 0x1001, "Charge": 0, "HES": 0,
        "ControlUsageMode": 0, "Direction": 0, "OOA": 0,
        "PowerManagement": 0, "Sleep": 0, "Version": "PRO"}}))
    assert parsed["topic"] == "basic" and parsed["key"] == "1002/6"
    f = parsed["fields"]
    assert f["motion_state_label"] == "站立"
    assert f["gait_label"] == "基础(标准)"
    assert f["control_usage_mode_label"] == "常规"
    assert f["version"] == "PRO"


def test_motion_has_16_joints_wheeled_leg():
    """轮足：4 腿 × (hip_x, hip_y, knee, wheel) = 16 关节（PLAN §10.4 ②）。"""
    parsed = ap.parse_frame(_frame(1002, 4, {
        "MotionStatus": {"Roll": 0.1, "LinearX": 0.2},
        "MotorStatus": {"Joint": [float(i) for i in range(16)]}}))
    assert parsed["topic"] == "motion"
    joints = parsed["fields"]["joints"]
    assert len(joints) == 16 == ap.JOINT_COUNT
    assert parsed["fields"]["joint_names"][3] == "LF_wheel"   # 第 4 个是轮毂
    assert parsed["fields"]["joint_names"][-1] == "RB_wheel"
    assert parsed["fields"]["linear_x"] == 0.2


def test_motion_fallback_to_named_fields():
    """无 Joint 数组时从命名字段还原（docs/04 两种表示并存）。"""
    items = {"MotorStatus": {"LeftFrontHipX": 0.1, "LeftFrontHipY": 0.2,
                             "LeftFrontKnee": 0.3, "LeftFrontWheel": 0.4}}
    parsed = ap.parse_frame(_frame(1002, 4, items))
    assert parsed["fields"]["joints"] == [0.1, 0.2, 0.3, 0.4]


def test_device_battery_list():
    parsed = ap.parse_frame(_frame(1002, 5, {"BatteryList": [
        {"Voltage": 50.4, "BatteryLevel": 86.5, "battery_temperature": 31.0,
         "charge": False, "serial": "A"},
        {"Voltage": 49.9, "BatteryLevel": 80.0, "battery_temperature": 30.0,
         "charge": True, "serial": "B"}]}))
    f = parsed["fields"]
    assert f["battery_count"] == 2
    assert f["level"] == 86.5 and f["charging"] is False
    assert f["batteries"][1]["serial"] == "B"


def test_fault_error_list():
    parsed = ap.parse_frame(_frame(1002, 3, {"ErrorList": [
        {"errorCode": 7, "component": "motor"}]}))
    f = parsed["fields"]
    assert f["error_count"] == 1 and f["has_fault"] is True
    assert f["errors"][0]["component"] == "motor"


def test_sleep_query_response():
    parsed = ap.parse_frame(_frame(1101, 7, {"Sleep": 2, "Auto": True, "Time": 5}))
    assert parsed["topic"] == "sleep"
    assert parsed["fields"]["sleep_label"] == "进入休眠中"


def test_unknown_message_is_passthrough():
    parsed = ap.parse_frame(_frame(9999, 1, {"X": 1}))
    assert parsed["topic"] == "unknown"
    assert parsed["fields"] == {}


def test_gait_zero_means_unset():
    """真机实测：空闲状态 Gait=0（docs/04 未列该值）→ 应显示"未设置"而非"未知(0)"。"""
    parsed = ap.parse_frame(_frame(1002, 6, {"BasicStatus": {"Gait": 0}}))
    assert parsed["fields"]["gait_label"] == "未设置"


def test_confidence_report_covers_all_topics():
    report = ap.confidence_report()
    # 6 类 = docs/04 五类 + 真机实测新增的 nav（ack 也登记但无枚举字段）
    assert {"basic", "motion", "device", "fault", "sleep", "nav"} <= set(report)
    # 关节字段已确认；单位未载 → unknown（PLAN Q12）
    assert report["motion"]["joints"] == "confirmed"
    assert report["motion"]["unit_linear"] == "unknown"
