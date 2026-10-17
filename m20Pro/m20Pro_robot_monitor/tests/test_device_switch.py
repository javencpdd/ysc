"""设备供电开关（1101/3）单测 —— 2026-10-17 抓包 + 真机探测取证后的落地。

取证结论见 ``patrol_codec.DEVICE_SWITCH_SPEC``：
  - 1101/3 的 Items 键名决定目标设备，**只认白名单内的键**
  - 该指令只认厂商 App 的帧头 magic ``EB 90 EB 90``，否则
    basic_server 回 ``ErrorCode 57351 / "No operation permission"``
  - ``EB 90 EB 90`` 对其余指令（心跳/运动/查询）与默认 magic 完全等价，
    所以只在 DeviceControl 类指令上切换，**绝不全局替换**
"""

import json

import pytest

from control import patrol_codec
from control.control_gateway import ControlGateway, RecordingSink
from control.command_log import CommandLog
from ingestion import asdu_parser


# ---------------------------------------------------------------- 编解码
def test_device_switch_encodes_1101_3_with_authorized_magic():
    frame = patrol_codec.encode("device_switch", {"items": {
        "Video": {"Front": 1, "Back": 0}}})
    # 帧头：授权 magic + protocolType=1
    assert frame[:4] == asdu_parser.HEAD_TAG_AUTHORIZED == b"\xeb\x90\xeb\x90"
    assert frame[4:6] == b"\x8e\x00" or frame[4:6] == (len(frame) - 16).to_bytes(2, "little")
    body = json.loads(frame[16:].decode("utf-8"))
    assert body["PatrolDevice"]["Type"] == 1101
    assert body["PatrolDevice"]["Command"] == 3
    assert body["PatrolDevice"]["Items"] == {"Video": {"Front": 1, "Back": 0}}


def test_other_commands_keep_default_magic():
    """其余指令一律用默认 magic —— 心跳/运动链路已验证，不许被顺手改掉。"""
    for name, params in (("heartbeat", {}), ("stand_up", {}), ("gait", {"param": 0x3002}),
                         ("usage_mode", {"mode": 0}), ("sleep_query", {})):
        frame = patrol_codec.encode(name, params)
        assert frame[:4] == asdu_parser.HEAD_TAG == b"\xeb\x91\xeb\x90", name


def test_device_switch_rejects_unknown_keys():
    """绝不透传任意 Items —— 键名猜错等于盲目操作硬件。"""
    with pytest.raises(ValueError) as exc:
        patrol_codec.encode("device_switch", {"items": {"JOINTS_POWER": 0}})
    assert "不支持的键" in str(exc.value)


def test_device_switch_rejects_bad_values():
    for bad in ({"GPS": 2}, {"FanSpeed": 200}, {"FanSpeed": -1},
                {"GPSMode": 2 ** 33}, {"Lidar": {"Front": 1}},        # 缺 Back
                {"Lidar": {"Front": 9, "Back": 0}}, {"Video": 1}):
        with pytest.raises(ValueError):
            patrol_codec.encode("device_switch", {"items": bad})


def test_device_switch_requires_at_least_one_key():
    with pytest.raises(ValueError):
        patrol_codec.encode("device_switch", {"items": {}})


def test_device_switch_accepts_every_whitelisted_key():
    """白名单里每个键都要能编过去（含语义未公开的 GPSMode，仅取证用）。"""
    items = {
        "Video": {"Front": 1, "Back": 1}, "Lidar": {"Front": 0, "Back": 0},
        "GPS": 1, "LedHost": 1, "LedExt": 0, "LoadPower": 1, "FP": 0,
        "FanSpeed": 60, "GPSMode": 69905,
    }
    msg = patrol_codec.build("device_switch", {"items": items})
    assert msg["type"] == 1101 and msg["command"] == 3
    assert msg["items"] == items


def test_turns_off_detection():
    off = patrol_codec.device_switch_turns_off
    assert off({"Video": {"Front": 1, "Back": 0}}) is True
    assert off({"Lidar": {"Front": 0, "Back": 0}}) is True
    assert off({"GPS": 0}) is True
    assert off({"FanSpeed": 0}) is True
    assert off({"Video": {"Front": 1, "Back": 1}}) is False
    assert off({"GPS": 1, "FanSpeed": 80}) is False
    assert off({}) is False
    assert off(None) is False


def test_lidar_report_value_two_is_not_off():
    """真机实测：DevEnable.Lidar 开启后上报 **2**（运行中），不是 1。

    车侧日志 `mLIDAR_POWER_.front 2` = 运行中，1 = 已供电/启动中，0 = 关。
    因此"是否关闭"只能按 ==0 判，==1 会把运行中的雷达误判成已关闭。
    """
    assert patrol_codec.device_switch_turns_off({"Lidar": {"Front": 2, "Back": 2}}) is False
    assert patrol_codec.device_switch_is_off("Lidar", {"Front": 2, "Back": 2}) is False
    assert patrol_codec.device_switch_is_off("Lidar", {"Front": 1, "Back": 2}) is False
    assert patrol_codec.device_switch_is_off("Lidar", {"Front": 0, "Back": 2}) is True


def test_report_value_two_is_normalized_when_sending():
    """前端回填另一路当前值（可能是 2）时必须归一成 1 —— 2 不是合法下发值。"""
    with pytest.raises(ValueError):
        patrol_codec.encode("device_switch", {"items": {"Lidar": {"Front": 2, "Back": 1}}})


# ---------------------------------------------------------------- 安全闸
def _gw(state=None, enabled=True):
    sink = RecordingSink()
    gw = ControlGateway(sink, enabled=enabled, lease_seconds=5.0,
                        state_provider=(lambda: state) if state is not None else None)
    gw.renew_lease()
    if enabled:
        gw.enable()          # L0 场景必须保持未启用，否则测不到分层闸
    return gw, sink


def test_turning_off_requires_confirmation():
    gw, sink = _gw()
    res = gw.execute("device_switch", {"items": {"GPS": 0}})
    assert res["ok"] is False and res["reason"] == "CONFIRM_REQUIRED"
    assert sink.sent == []                     # 一条都没发
    # 二次确认后放行
    assert gw.execute("device_switch", {"items": {"GPS": 0}}, confirmed=True)["ok"] is True
    assert len(sink.sent) == 1


def test_turning_on_does_not_need_confirmation():
    gw, sink = _gw()
    assert gw.execute("device_switch", {"items": {"GPS": 1}})["ok"] is True
    assert len(sink.sent) == 1


def test_lidar_off_blocked_while_standing():
    """站立/RL 态禁关雷达（平衡参考输入）—— 开启不受限。"""
    gw, sink = _gw(state={"basic": {"motion_state": patrol_codec.MOTION_RL}})
    res = gw.execute("device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                     confirmed=True)
    assert res["ok"] is False and res["reason"] == "PRECONDITION_FAILED"
    assert "禁止关闭" in res["detail"] and "雷达" in res["detail"]
    assert sink.sent == []
    # 开启雷达在站立态照常放行
    assert gw.execute("device_switch",
                      {"items": {"Lidar": {"Front": 1, "Back": 1}}})["ok"] is True


def test_lidar_off_allowed_when_lying_down():
    gw, sink = _gw(state={"basic": {"motion_state": patrol_codec.MOTION_LIE_DOWN}})
    res = gw.execute("device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                     confirmed=True)
    assert res["ok"] is True
    assert len(sink.sent) == 1


def test_camera_off_allowed_while_standing_but_still_confirms():
    """相机断电不影响平衡参考，故不做运动闸；但二次确认仍然要。"""
    gw, sink = _gw(state={"basic": {"motion_state": patrol_codec.MOTION_STAND}})
    assert gw.execute("device_switch",
                      {"items": {"Video": {"Front": 0, "Back": 0}}})["ok"] is False
    res = gw.execute("device_switch",
                     {"items": {"Video": {"Front": 0, "Back": 0}}}, confirmed=True)
    assert res["ok"] is True and len(sink.sent) == 1


def test_bad_device_params_are_rejected_without_sending():
    gw, sink = _gw()
    res = gw.execute("device_switch", {"items": {"Nope": 1}}, confirmed=True)
    assert res["ok"] is False and res["reason"] == "BAD_PARAMS"
    assert sink.sent == []


def test_device_switch_gated_by_l1_and_lease_like_others():
    """L0 下设备开关同样不可用（安全手段优先级不受影响）。"""
    gw, sink = _gw(enabled=False)
    assert gw.execute("device_switch", {"items": {"GPS": 1}})["ok"] is False
    gw, sink = _gw(enabled=True)
    gw._lease_until = 0.0                     # 手动弄过期约
    assert gw.execute("device_switch", {"items": {"GPS": 1}})["ok"] is False


def test_precheck_catches_unconfirmed_shutdown():
    gw, _ = _gw()
    res = gw.precheck("device_switch", {"items": {"GPS": 0}})
    assert res is not None and res["reason"] == "CONFIRM_REQUIRED"
    assert gw.precheck("device_switch", {"items": {"GPS": 0}}, confirmed=True) is None


def test_gps_mode_mask_is_accepted_and_never_looks_like_power_off():
    """GPSMode 走 1101/3 —— 是"切星座"不是"断供电"，不该被当成关闭要确认。

    唯一例外：掩码 0 = 所有星座全关，那确实是"关"，要求确认是对的。
    """
    on = {"GPSMode": 0x11111}
    assert patrol_codec.device_switch_turns_off(on) is False
    assert patrol_codec.device_switch_turns_off({"GPSMode": 0x00001}) is False
    msg = patrol_codec.build("device_switch", {"items": on})
    assert msg["items"] == {"GPSMode": 0x11111}
    # 掩码 0 → 判为关闭语义
    assert patrol_codec.device_switch_turns_off({"GPSMode": 0}) is True


def test_gps_mode_switch_does_not_need_confirm_at_api_level():
    gw, sink = _gw(state={"basic": {"motion_state": patrol_codec.MOTION_LIE_DOWN}})
    res = gw.execute("device_switch", {"items": {"GPSMode": 0x00001}})   # 未带确认
    assert res["ok"] is True
    assert len(sink.sent) == 1
    frame = sink.sent[0]
    assert frame[:4] == asdu_parser.HEAD_TAG_AUTHORIZED       # 走授权通道
    body = json.loads(frame[16:].decode("utf-8"))["PatrolDevice"]
    assert body["Type"] == 1101 and body["Command"] == 3
    assert body["Items"] == {"GPSMode": 1}


def test_gps_mode_out_of_range_rejected_without_frame():
    gw, sink = _gw()
    res = gw.execute("device_switch", {"items": {"GPSMode": -1}}, confirmed=True)
    assert res["ok"] is False and res["reason"] == "BAD_PARAMS"
    assert sink.sent == []


# ------------------------------------------------ 关闭判定必须对比当前状态
def _gw3(state=None, dev_enable=None):
    """带 device_provider 的网关（生产装配形态）。"""
    sink = RecordingSink()
    gw = ControlGateway(
        sink, enabled=True, lease_seconds=30.0,
        state_provider=(lambda: state) if state is not None else None,
        device_provider=(lambda: {"dev_enable": dev_enable}) if dev_enable is not None else None,
        command_log=CommandLog(size=50))
    gw.enable()
    gw.renew_lease()
    return gw, sink


def test_opening_one_side_is_not_treated_as_shutdown():
    """★回归（2026-10-17 真踩）：开一路时另一路的 0 只是"保持关闭"，不是关闭操作。

    Items 是整键覆写，开前相机必然带上 ``{"Back":0}``。旧实现只看目标值，
    见到 0 就判成"关闭" → 要求二次确认 → 前端点「开」根本不弹框 →
    用户看到 ``CONFIRM_REQUIRED``，表现为"点开启没反应"。
    """
    cur = {"Video": {"Front": 0, "Back": 0}}
    gw, sink = _gw3(state={"basic": {"motion_state": patrol_codec.MOTION_LIE_DOWN}},
                    dev_enable=cur)
    res = gw.execute("device_switch", {"items": {"Video": {"Front": 1, "Back": 0}}})
    assert res["ok"] is True, res          # 不该要确认
    assert len(sink.sent) == 1
    body = json.loads(sink.sent[0][16:].decode("utf-8"))["PatrolDevice"]
    assert body["Items"] == {"Video": {"Front": 1, "Back": 0}}


def test_real_shutdown_still_needs_confirmation():
    """真关（当前开着 → 目标 0）仍然必须二次确认 —— 修 bug 不能把安全闸修没了。"""
    gw, sink = _gw3(state={"basic": {"motion_state": patrol_codec.MOTION_LIE_DOWN}},
                    dev_enable={"GPS": 1, "Video": {"Front": 1, "Back": 1}})
    r1 = gw.execute("device_switch", {"items": {"GPS": 0}})
    assert r1["ok"] is False and r1["reason"] == "CONFIRM_REQUIRED"
    r2 = gw.execute("device_switch", {"items": {"Video": {"Front": 0, "Back": 1}}})
    assert r2["ok"] is False and r2["reason"] == "CONFIRM_REQUIRED"
    assert sink.sent == []
    # 确认后放行
    assert gw.execute("device_switch", {"items": {"GPS": 0}}, confirmed=True)["ok"] is True


def test_no_current_state_falls_back_to_conservative_rule():
    """读不到当前 DevEnable 时回退到保守判定（有 0 就要求确认）—— 宁严勿松。"""
    gw, sink = _gw3(state={"basic": {"motion_state": patrol_codec.MOTION_LIE_DOWN}})
    res = gw.execute("device_switch", {"items": {"Video": {"Front": 1, "Back": 0}}})
    assert res["ok"] is False and res["reason"] == "CONFIRM_REQUIRED"
    assert sink.sent == []


def test_motion_lock_only_fires_for_running_lidar():
    """运动锁也按"当前是否开着"判定：关一个本来就关着的雷达不算危险动作。"""
    standing = {"basic": {"motion_state": patrol_codec.MOTION_STAND}}
    # 雷达当前 0/0（已关）→ 再下发 0 不需要被运动锁拦
    gw, _ = _gw3(state=standing, dev_enable={"Lidar": {"Front": 0, "Back": 0}})
    assert gw.execute("device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                      confirmed=True)["ok"] is True
    # 雷达当前 2/2（运行中）→ 关它必须被拦
    gw2, sink2 = _gw3(state=standing, dev_enable={"Lidar": {"Front": 2, "Back": 2}})
    res = gw2.execute("device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                      confirmed=True)
    assert res["ok"] is False and res["reason"] == "PRECONDITION_FAILED"
    assert sink2.sent == []


def test_gps_mode_switch_needs_no_confirmation():
    """切星座掩码不是"关供电"，任何当前状态下都不该要确认。"""
    gw, sink = _gw3(state={"basic": {"motion_state": patrol_codec.MOTION_STAND}},
                    dev_enable={"GPSMode": 0x11111, "GPS": 1})
    assert gw.execute("device_switch", {"items": {"GPSMode": 0x00001}})["ok"] is True
    assert len(sink.sent) == 1
