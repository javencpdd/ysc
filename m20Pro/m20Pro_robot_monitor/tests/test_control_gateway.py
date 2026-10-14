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
