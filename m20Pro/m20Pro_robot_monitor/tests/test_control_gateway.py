"""控制安全闸单测：四道闸逐条验证（ADR-004 / PLAN §9）。"""

import pytest

from control import patrol_codec
from control.control_gateway import ControlGateway, RecordingSink
from errors import (ControlBlacklistError, ControlDisabledError, ControlError,
                    ControlLeaseError, ControlPreconditionError)


def _gateway(state=None, enabled=False):
    sink = RecordingSink()
    gw = ControlGateway(sink, enabled=enabled, lease_seconds=5.0,
                        state_provider=(lambda: state) if state is not None else None)
    return gw, sink


def test_l0_rejects_everything_except_estop():
    gw, sink = _gateway(enabled=False)
    res = gw.execute("stand_up")
    assert res["ok"] is False and res["reason"] == "CONTROL_DISABLED"
    assert sink.sent == []                       # 一条都没发出去

    # 软急停：安全手段优先于开关（ADR-004）
    res = gw.execute("soft_estop")
    assert res["ok"] is True
    assert len(sink.sent) == 1
    assert gw.estop is True


def test_estop_lock_blocks_further_commands():
    gw, _ = _gateway(enabled=True)
    gw.execute("soft_estop")
    res = gw.execute("stand_up")
    assert res["ok"] is False and res["reason"] == "CONTROL_DISABLED"
    gw.clear_estop()
    gw.renew_lease()
    assert gw.execute("stand_up")["ok"] is True


def test_l1_requires_lease():
    gw, _ = _gateway(enabled=True)
    res = gw.execute("stand_up")
    assert res["ok"] is False and res["reason"] == "LEASE_EXPIRED"
    gw.renew_lease()
    assert gw.lease_active() is True
    assert gw.execute("stand_up")["ok"] is True


def test_charge_reset_is_blacklisted_in_any_config():
    """Charge=2 黑名单：即使 enabled + 已续约也拒绝（无"除非"）。"""
    gw, sink = _gateway(enabled=True)
    gw.renew_lease()
    gw.enable()
    res = gw.execute("charge", {"action": patrol_codec.CHARGE_RESET})
    assert res["ok"] is False and res["reason"] == "BLACKLISTED"
    assert sink.sent == []
    # 其他充电动作正常放行
    assert gw.execute("charge", {"action": patrol_codec.CHARGE_START})["ok"] is True


def test_axis_precondition_requires_standing_and_normal_mode():
    gw, _ = _gateway(state={"motion_state": 0, "control_usage_mode": 0}, enabled=True)
    gw.renew_lease()
    res = gw.execute("axis", {"x": 0.5})
    assert res["ok"] is False and res["reason"] == "PRECONDITION_FAILED"

    gw2, sink = _gateway(state={"motion_state": 1, "control_usage_mode": 0}, enabled=True)
    gw2.renew_lease()
    assert gw2.execute("axis", {"x": 0.5})["ok"] is True
    assert len(sink.sent) == 1

    # 非常规模式（导航）下拒绝 —— docs/04 §1.2.5 原文约束
    gw3, _ = _gateway(state={"motion_state": 1, "control_usage_mode": 1}, enabled=True)
    gw3.renew_lease()
    assert gw3.execute("axis", {"x": 0.1})["reason"] == "PRECONDITION_FAILED"

    # RL 控制状态允许
    gw4, _ = _gateway(state={"motion_state": 17, "control_usage_mode": 0}, enabled=True)
    gw4.renew_lease()
    assert gw4.execute("axis", {"y": 0.1})["ok"] is True


def test_axis_values_are_clamped_server_side():
    """浏览器不是可信边界：服务端二次截断（安全上限 ±0.40，2026-10-15 实测）。"""
    gw, sink = _gateway(state={"motion_state": 1, "control_usage_mode": 0}, enabled=True)
    gw.renew_lease()
    res = gw.execute("axis", {"x": 5.0, "y": -9.9, "z": 0.333})
    assert res["ok"] is True
    assert res["params"]["x"] == 0.4
    assert res["params"]["y"] == -0.4
    assert res["params"]["z"] == 0.33            # 2 位小数


def test_axis_speed_cap_blocks_dangerous_values():
    """实测危险速度（≥0.7 ≈1.1m/s）在服务端被强制截断到 0.40 上限。"""
    gw, sink = _gateway(state={"motion_state": 17, "control_usage_mode": 0}, enabled=True)
    gw.renew_lease()
    res = gw.execute("axis", {"x": 0.7})
    assert res["ok"] is True
    assert res["params"]["x"] == 0.4             # 0.7 被截为 0.4
    res = gw.execute("axis", {"x": 0.25})
    assert res["params"]["x"] == 0.25            # 舒适档原样通过


def test_nan_axis_value_becomes_zero():
    gw, _ = _gateway(state={"motion_state": 1, "control_usage_mode": 0}, enabled=True)
    gw.renew_lease()
    res = gw.execute("axis", {"x": float("nan")})
    assert res["params"]["x"] == 0.0


def test_audit_records_every_attempt():
    gw, _ = _gateway(enabled=False)
    gw.execute("stand_up")            # 被拒
    gw.renew_lease()
    gw.execute("charge", {"action": 2})   # 被黑名单拒
    audit = gw.audit(limit=10)
    assert len(audit) == 2
    assert all(item["result"] == "rejected" for item in audit)
    assert audit[0]["command"] == "charge"      # 倒序：最新在前


def test_disable_sends_zero_before_closing():
    gw, sink = _gateway(enabled=True)
    gw.enable()
    gw.renew_lease()
    gw.disable()
    assert gw.enabled is False
    assert len(sink.sent) == 1                   # 补发零位
    assert patrol_codec.zero_axis()["items"]["X"] == 0.0


def test_gait_field_name_is_gaitparam():
    """协议事实修正：字段名是 GaitParam，不是 Gait。"""
    msg = patrol_codec.gait(patrol_codec.GAIT_STAIR_AGILE)
    assert msg == {"type": 2, "command": 23, "items": {"GaitParam": 0x3003}}


def test_unknown_command_raises_keyerror():
    with pytest.raises(KeyError):
        patrol_codec.build("fly_to_moon")


# ---------------------------------------------------------------- 实时通道（2/25，2026-10-16）
def test_axis_real_encodes_command_25_with_same_fields():
    """实时通道与主通道字段完全同构，仅 command=25（帧头解码验证）。"""
    from ingestion import asdu_parser

    gw, sink = _gateway(state={"motion_state": 1, "control_usage_mode": 0}, enabled=True)
    gw.renew_lease()
    res = gw.execute("axis_real", {"x": 0.1, "y": -0.3})
    assert res["ok"] is True
    decoded = asdu_parser.decode_frame(sink.sent[-1])
    assert decoded["type"] == 2 and decoded["command"] == 25
    assert decoded["items"]["Y"] == -0.3
    assert decoded["items"]["X"] == 0.1


def test_axis_real_gets_same_gates_and_clamp():
    """值域钳制 / 前置校验对两条通道一视同仁。"""
    gw, _ = _gateway(state={"motion_state": 4, "control_usage_mode": 0}, enabled=True)
    gw.renew_lease()
    assert gw.execute("axis_real", {"y": 0.3})["reason"] == "PRECONDITION_FAILED"

    gw2, _ = _gateway(state={"motion_state": 1, "control_usage_mode": 0}, enabled=True)
    gw2.renew_lease()
    res = gw2.execute("axis_real", {"y": -9.9})
    assert res["ok"] is True and res["params"]["y"] == -0.4


def test_channel_mapping_and_fallback():
    """通道键映射：非法值回退主通道（绝不因拼错而静默换通道）。"""
    assert patrol_codec.channel_command("steer") == "axis"
    assert patrol_codec.channel_command("real") == "axis_real"
    assert patrol_codec.channel_command(None) == "axis"
    assert patrol_codec.channel_command("REAL") == "axis"      # 大小写敏感，防呆
    assert patrol_codec.channel_key("real") == "real"


def test_precheck_rejects_without_sending():
    """precheck：只过闸不发送；被拒进审计、不发包。"""
    gw, sink = _gateway(enabled=False)
    rej = gw.precheck("axis")
    assert rej is not None and rej["reason"] == "CONTROL_DISABLED"
    assert sink.sent == []
    assert gw.audit(1)[0]["result"] == "rejected"

    gw2, _ = _gateway(state={"motion_state": 1, "control_usage_mode": 0}, enabled=True)
    gw2.renew_lease()
    assert gw2.precheck("axis") is None            # 全闸通过
    assert gw2.precheck("axis_real") is None       # 实时通道同样可起步


# ------------------------------------- 遥测暂停闸（2026-10-16，"蒙眼不开车"）


def _gateway_blind(enabled=True, state=None):
    """telemetry_provider 恒 True = 心跳已停发、看不见车。"""
    sink = RecordingSink()
    gw = ControlGateway(sink, enabled=enabled, lease_seconds=999.0,
                        state_provider=lambda: (state or {"motion_state": 1,
                                                           "control_usage_mode": 0}),
                        telemetry_provider=lambda: True)
    return gw, sink


def test_telemetry_paused_blocks_motion_commands():
    """遥测暂停 → 轴指令（含实时通道）一律拒绝，且一帧都不发。"""
    gw, sink = _gateway_blind()
    gw.renew_lease(999.0)
    for name in ("axis", "axis_real"):
        res = gw.execute(name, {"y": -0.3})
        assert res["ok"] is False, name
        assert res["reason"] == "TELEMETRY_PAUSED", name
        assert res["status"] == 409, name
    assert sink.sent == []                     # 蒙眼不开车：一帧未发
    assert gw.audit(1)[0]["reason"] == "TELEMETRY_PAUSED"


def test_telemetry_paused_allows_estop_and_resume_path():
    """软急停豁免（安全手段优先）；heartbeat 指令也不被遥测闸拦
    （否则"停心跳→想恢复"会被自己的闸锁死）。"""
    gw, sink = _gateway_blind()
    gw.renew_lease(999.0)
    assert gw.execute("soft_estop")["ok"] is True      # 急停永远可达
    assert gw.estop is True
    gw.clear_estop()                                   # 解除锁存（网关方法，非指令）
    assert gw.estop is False
    assert gw.execute("heartbeat")["ok"] is True       # 恢复遥测的路径本身
    assert len(sink.sent) >= 2                         # 上述帧确实发出去了


def test_telemetry_paused_blocks_precheck_too():
    """precheck 与 execute 同构：定时移动入口同样先验后行。"""
    gw, sink = _gateway_blind()
    gw.renew_lease(999.0)
    rej = gw.precheck("axis")
    assert rej is not None and rej["reason"] == "TELEMETRY_PAUSED"
    assert sink.sent == []


def test_telemetry_provider_exception_does_not_block():
    """探针异常不能拖死指令链路（宁可放行也不能因监控自身故障锁死控制）。"""
    def _boom():
        raise RuntimeError("probe down")

    gw = ControlGateway(RecordingSink(), enabled=True, lease_seconds=999.0,
                        state_provider=lambda: {"motion_state": 1,
                                                "control_usage_mode": 0},
                        telemetry_provider=_boom)
    gw.renew_lease(999.0)
    assert gw.execute("axis", {"x": 0.2})["ok"] is True


def test_no_telemetry_provider_means_no_gate():
    """不传 telemetry_provider（旧构造方式 / mock 场景）→ 没有这道闸。"""
    gw, _ = _gateway(enabled=True, state={"motion_state": 1, "control_usage_mode": 0})
    gw.renew_lease(999.0)
    assert gw.execute("axis", {"x": 0.2})["ok"] is True
