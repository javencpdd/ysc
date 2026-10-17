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


# ---------------------------------------------------------------------------
# 2026-10-17 取证新增：关节回零 + 分设备供电使能
# ---------------------------------------------------------------------------
def test_basic_exposes_reset_joints_zero_and_status_code():
    """BasicStatus 真机实测带 `ResetJointsZero` / `StatusCode`（docs/04 未收录）。

    车侧 basic_server.toml 默认 autoResetJointsZero=true → 首次站立会先回零。
    """
    parsed = ap.parse_frame(_frame(1002, 6, {"BasicStatus": {
        "MotionState": 1, "StatusCode": 0, "ResetJointsZero": 0}}))
    f = parsed["fields"]
    assert f["reset_joints_zero"] == 0
    assert f["status_code"] == 0
    assert f["reset_joints_zero_label"] == "无需回零"


def test_reset_joints_zero_unknown_value_is_not_fabricated():
    """值域未见官方文档 → 非 0 只能透传数值，绝不臆造标签。"""
    parsed = ap.parse_frame(_frame(1002, 6, {"BasicStatus": {"ResetJointsZero": 7}}))
    assert parsed["fields"]["reset_joints_zero"] == 7
    assert "7" in parsed["fields"]["reset_joints_zero_label"]


def test_device_dev_enable_is_split_per_sensor():
    """DevEnable 真机结构：Video/Lidar 各含 Front/Back，另有 GPS/GPSMode/Led/Fan。

    前端按标签页分区展示依赖这些细粒度字段（相机页 / 运动控制页 / GPS 页）。
    """
    dev_enable = {
        "FanSpeed": 100, "LoadPower": 1, "LedHost": 1, "LedExt": 1, "FP": 1,
        "Lidar": {"Front": 0, "Back": 0},
        "GPS": 1, "GPSMode": 69905,
        "Video": {"Front": 1, "Back": 1},
    }
    parsed = ap.parse_frame(_frame(1002, 5, {"DevEnable": dev_enable}))
    f = parsed["fields"]
    assert f["video_front"] == 1 and f["video_back"] == 1
    assert f["lidar_front"] == 0 and f["lidar_back"] == 0
    assert f["gps_enable"] == 1 and f["gps_mode"] == 69905
    assert f["led_host"] == 1 and f["led_ext"] == 1
    assert f["load_power"] == 1 and f["fan_speed"] == 100
    # 原始结构仍保留（向后兼容）
    assert f["dev_enable"] == dev_enable


def test_device_dev_enable_missing_yields_none():
    """无 DevEnable 时细粒度字段应为 None，不能抛异常或返回 0（0 会被误读成"已关"）。"""
    parsed = ap.parse_frame(_frame(1002, 5, {"BatteryList": []}))
    f = parsed["fields"]
    assert f["video_front"] is None and f["lidar_front"] is None
    assert f["gps_enable"] is None


def test_device_gps_is_split_for_gps_tab():
    """GPS 标签页依赖的细粒度字段；原始 `gps` 结构同时保留（排查解析错误时用）。"""
    gps = {
        "Latitude": 30.123456, "Longitude": 120.654321, "Speed": 1.5, "Course": 88.0,
        "FixQuality": 1, "NumSatellites": 12, "Altitude": 45.6,
        "HDOP": 0.8, "VDOP": 1.1, "PDOP": 1.4, "VisibleSatellites": 18,
    }
    parsed = ap.parse_frame(_frame(1002, 5, {"GPS": gps}))
    f = parsed["fields"]
    assert f["gps_latitude"] == 30.123456 and f["gps_longitude"] == 120.654321
    assert f["gps_altitude"] == 45.6 and f["gps_speed"] == 1.5 and f["gps_course"] == 88.0
    assert f["gps_fix_quality"] == 1 and f["gps_num_satellites"] == 12
    assert f["gps_visible_satellites"] == 18
    assert f["gps_hdop"] == 0.8 and f["gps_vdop"] == 1.1 and f["gps_pdop"] == 1.4
    assert f["gps"] == gps


def test_device_gps_missing_yields_none():
    parsed = ap.parse_frame(_frame(1002, 5, {"BatteryList": []}))
    assert parsed["fields"]["gps_latitude"] is None
    assert parsed["fields"]["gps_num_satellites"] is None


def test_confidence_report_covers_all_topics():
    report = ap.confidence_report()
    # 6 类 = docs/04 五类 + 真机实测新增的 nav（ack 也登记但无枚举字段）
    assert {"basic", "motion", "device", "fault", "sleep", "nav"} <= set(report)
    # 关节字段已确认；单位未载 → unknown（PLAN Q12）
    assert report["motion"]["joints"] == "confirmed"
    assert report["motion"]["unit_linear"] == "unknown"


# ---------------------------------------------------------------- GPS 卫星系统掩码
def test_gps_mode_presets_match_vendor_config():
    """位定义必须与车侧 gps.yaml 的 sysMask 注释**逐位一致**。

    来源：/opt/robot/share/node_driver/config/gps.yaml（2026-10-17 取证）
      bit0-GPS L1CA, bit4-BDS B1I, bit8-GLONASS L1, bit12-GALILEO E1, bit16-QZSS
      presets: gps_only 0x00001 / bds_only 0x00010 / glo_only 0x00100
               / gal_only 0x01000 / qzss_only 0x10000 / all_systems 0x11111
    """
    assert dict(ap.GPS_SYSTEM_BITS) == {
        0x00001: "GPS", 0x00010: "BDS", 0x00100: "GLONASS",
        0x01000: "Galileo", 0x10000: "QZSS",
    }
    assert ap.GPS_SYSTEM_MASK_ALL == 0x11111
    assert ap.gps_mode_systems(0x11111) == ["GPS", "BDS", "GLONASS", "Galileo", "QZSS"]


def test_gps_mode_label_speaks_human_not_code():
    """用户诉求：不要用 69905 这种代号，要真名。"""
    assert ap.gps_mode_label(0x11111) == "全系统（GN 模式）"
    assert ap.gps_mode_label(0x00001) == "仅 GPS"
    assert ap.gps_mode_label(0x00010) == "仅 北斗（BDS）"
    assert ap.gps_mode_label(0x01000) == "仅 Galileo"
    # 组合（非预设）→ 列出星座
    assert ap.gps_mode_label(0x00011) == "GPS + BDS"
    # 0 = 全关
    assert ap.gps_mode_label(0) == "全部关闭（无定位）"
    assert ap.gps_mode_label(None) is None
    # 含未知位必须显式标注，绝不假装看懂
    assert "0x20000" in ap.gps_mode_label(0x20001)
    assert ap.gps_mode_label(0x20000) == "未启用任何已知星座（含未知位 0x20000）"


def test_device_exposes_gps_mode_in_human_readable_form():
    frame = _frame(1002, 5, {"DevEnable": {"GPSMode": 0x11111, "GPS": 1}})
    d = ap.parse_frame(frame)["fields"]
    assert d["gps_mode"] == 69905                       # 原始值仍在（排查用）
    assert d["gps_mode_hex"] == "0x11111"               # 与 gps.yaml 同写法
    assert d["gps_mode_label"] == "全系统（GN 模式）"     # 给人看的
    assert d["gps_systems"] == ["GPS", "BDS", "GLONASS", "Galileo", "QZSS"]


def test_gps_mode_missing_yields_none():
    frame = _frame(1002, 5, {"DevEnable": {"GPS": 1}})
    d = ap.parse_frame(frame)["fields"]
    assert d["gps_mode"] is None
    assert d["gps_mode_label"] is None
    assert d["gps_mode_hex"] is None
    assert d["gps_systems"] == []
