"""机器人设置页（补光灯 / 首启回零 / 休眠）API 契约测试（2026-10-18 加）。

守住四条底线（都是真机实测出来的，不是设计时想当然）：

1. **车侧静默夹取，后端必须先拒** —— ``1101/6`` 的 ``Time`` 超出 5~30 时车侧
   **不回错误码**，直接把值夹到边界（实测 60→30、3→5），``Auto`` 照常生效。
   用户填 60 却静默变成 30 是最难排查的一类 bug，所以在后端就挡住。
2. **危险操作必须二次确认** —— 整车休眠（会趴下并依次断 LED/风扇/视频/关节）
   与"关闭首启回零"都需 ``confirmed=true``；反向操作（唤醒/开回零）不拦。
3. **确认闸拦下时一条报文都不能发** —— 只返回 ``CONFIRM_REQUIRED``。
4. **只读查询不开控制也能问** —— ``1101/11`` / ``1101/7`` 不改车上任何东西，
   把它们锁在"先开 L1"后面纯属自找麻烦。
"""

import json

import pytest
from fastapi.testclient import TestClient

import main
from control import patrol_codec
from config import Settings


def _svc():
    """mock 数据源的 MonitorService + 它的 RecordingSink（不发真包，只记录）。"""
    svc = main.MonitorService(Settings(data_source="mock"))
    sink = svc.control._sink          # mock 场景由 MonitorService 自建，这里取引用
    svc.control.enable()
    svc.control.renew_lease()
    return svc, sink


def _post(path, svc, body=None):
    prev = main.service
    main.service = svc
    try:
        return TestClient(main.app).post(path, json=body or {})
    finally:
        main.service = prev


def _get(path, svc):
    prev = main.service
    main.service = svc
    try:
        return TestClient(main.app).get(path)
    finally:
        main.service = prev


def _frame(sink, index=0):
    frame = sink.sent[index]
    return json.loads(frame[16:].decode("utf-8"))["PatrolDevice"]


# ------------------------------------------------ 休眠时长：车侧夹取 → 后端先拒
@pytest.mark.parametrize("minutes", [60, 31, 4, 0, -5])
def test_sleep_minutes_out_of_range_rejected_without_frame(minutes):
    """越界时长必须一条报文都不发（车侧会静默夹到边界，见模块 docstring）。"""
    svc, sink = _svc()
    res = _post("/api/v1/robot/sleep", svc, {"sleep": False, "auto": True,
                                            "minutes": minutes})
    body = res.json()
    assert body["ok"] is False
    assert body["reason"] == "MINUTES_OUT_OF_RANGE"
    assert sink.sent == []


@pytest.mark.parametrize("minutes", [5, 10, 30])
def test_sleep_minutes_boundaries_are_accepted(minutes):
    """5 与 30 是车侧接受的边界值，必须放行。"""
    svc, sink = _svc()
    res = _post("/api/v1/robot/sleep", svc, {"sleep": False, "auto": True,
                                            "minutes": minutes})
    assert res.json()["ok"] is True
    body = _frame(sink)
    assert body["Type"] == 1101 and body["Command"] == 6
    assert body["Items"]["Time"] == minutes


def test_sleep_config_does_not_need_confirmation():
    """只改自动休眠策略（sleep=false）不会让车趴下 → 不拦。"""
    svc, sink = _svc()
    res = _post("/api/v1/robot/sleep", svc, {"sleep": False, "auto": True,
                                            "minutes": 20})
    assert res.json()["ok"] is True


def test_sleep_now_requires_confirmation():
    """整车休眠 = 趴下 + 依次断电，未确认必须拦下且不发报文。"""
    svc, sink = _svc()
    res = _post("/api/v1/robot/sleep", svc, {"sleep": True, "auto": False,
                                            "minutes": 10})
    body = res.json()
    assert body["ok"] is False and body["reason"] == "CONFIRM_REQUIRED"
    assert sink.sent == []


# ------------------------------------------------ 首启回零：关要确认，开不要
def test_auto_reset_off_requires_confirmation():
    """关回零 = 下次开机直接站立，关节位置未经标定 → 需确认。"""
    svc, sink = _svc()
    res = _post("/api/v1/robot/auto_reset", svc, {"enable": False})
    body = res.json()
    assert body["ok"] is False and body["reason"] == "CONFIRM_REQUIRED"
    assert sink.sent == []


def test_auto_reset_on_does_not_need_confirmation():
    svc, sink = _svc()
    res = _post("/api/v1/robot/auto_reset", svc, {"enable": True})
    assert res.json()["ok"] is True


def test_auto_reset_write_encodes_1101_10():
    svc, sink = _svc()
    res = _post("/api/v1/robot/auto_reset", svc, {"enable": False, "confirmed": True})
    assert res.json()["ok"] is True
    # 车侧对 1101/10 不回帧 → 成功也要提示回读，不能让前端误以为已验证
    assert "verify_hint" in res.json()
    body = _frame(sink)
    assert body["Type"] == 1101 and body["Command"] == 10
    assert body["Items"] == {"Enable": False}


# ------------------------------------------------ 补光灯
def test_fill_light_encodes_1101_2():
    svc, sink = _svc()
    res = _post("/api/v1/robot/light", svc, {"front": True, "back": False})
    assert res.json()["ok"] is True
    body = _frame(sink)
    assert body["Type"] == 1101 and body["Command"] == 2
    assert body["Items"] == {"Front": 1, "Back": 0}


# ------------------------------------------------ 只读查询：不开控制也能问
def test_queries_are_allowed_without_l1():
    svc = main.MonitorService(Settings(data_source="mock"))
    sink = svc.control._sink
    assert svc.control.enabled is False        # L1 默认关闭
    res = _post("/api/v1/robot/config/refresh", svc, {})
    assert res.json()["ok"] is True
    kinds = sorted(_frame(sink, i)["Command"]
                   for i in range(len(sink.sent)))
    assert kinds == [7, 11]                    # GetSleepConfig + GetAutoResetJointsZero


def test_robot_config_shape():
    """三段结构必须齐：补光灯 / 首启回零 / 休眠，且"没问过"要显式 known=False。"""
    svc, sink = _svc()
    body = _get("/api/v1/robot/config", svc).json()
    assert body["ok"] is True
    assert set(body) >= {"fill_light", "auto_reset", "sleep"}
    assert body["fill_light"]["known"] is False       # 没有设备帧时就是未知
    assert body["auto_reset"]["known"] is False
    assert body["sleep"]["known"] is False
    # ★ known=False 时必须让前端显示"未知"，不能显示成"关闭"——那是凭空断言


def test_command_log_caches_query_answers():
    """查询应答要进缓存并带 age_s，前端才能区分"没问过/问过没答"。"""
    from control.command_log import CommandLog

    log = CommandLog(size=10, timeout_s=1.0)
    assert log.query(1101, 7) is None                   # 没问过
    log.on_response(1101, 7, {"Sleep": 0, "Auto": False, "Time": 10})
    cached = log.query(1101, 7)
    assert cached is not None
    assert cached["items"]["Time"] == 10
    assert "age_s" in cached and cached["age_s"] >= 0.0


def test_needs_confirm_only_for_dangerous_direction():
    """确认闸只看方向：休眠要确认、唤醒不要；关回零要确认、开不要。"""
    assert patrol_codec.needs_confirm("sleep", {"enable": True}) is True
    assert patrol_codec.needs_confirm("sleep", {"enable": False}) is False
    assert patrol_codec.needs_confirm("auto_reset_set", {"enable": False}) is True
    assert patrol_codec.needs_confirm("auto_reset_set", {"enable": True}) is False
    # 未知指令名不能炸，也不能默认放行危险操作
    assert patrol_codec.needs_confirm("no_such_command", {"enable": True}) is False
