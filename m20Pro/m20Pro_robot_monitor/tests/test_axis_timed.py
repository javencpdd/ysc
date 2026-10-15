"""定时移动 API（``/api/v1/control/axis/timed``）契约测试（2026-10-16 加）。

守住三条底线：

1. **计时在后端** —— 浏览器定时器会被节流（切后台/省电）；到点必须自动
   "零位一帧 + 停发"（只停不趴，绝不软急停）；
2. **通道可选** —— steer(2/21) / real(2/25) 同构两条通道，可做"同一轴值换
   通道"的对照排查（帧头解码验证 command 号）；
3. **先验后行** —— 控制未开启 / 未站立等情况**立即返回被拒原因**（一帧都不发），
   而不是让用户看着倒计时空转。

时间推进全部用假时钟手动 tick，不依赖真实 sleep。
"""

from fastapi.testclient import TestClient

import main
from control.axis_watchdog import AxisWatchdog
from control.control_gateway import ControlGateway, RecordingSink
from ingestion import asdu_parser


class FakeClock:
    """可控时钟：让 1.5s 的定时任务不需要真的等 1.5s。"""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class _FakeService:
    """最小替身：真网关（记录型出口）+ 真看门狗（假时钟、不起线程）。"""

    def __init__(self, enabled=True, state=None):
        self.sink = RecordingSink()
        self.clock = FakeClock()
        self._state = state or {"motion_state": 1, "control_usage_mode": 0}
        self.control = ControlGateway(
            self.sink, enabled=enabled, lease_seconds=999.0,
            state_provider=lambda: self._state)
        if enabled:
            self.control.enable()
            self.control.renew_lease(999.0)
        self.watchdog = AxisWatchdog(self.control, hz=20, clock=self.clock,
                                     sleeper=lambda _s: None)
        self.watchdog.start = lambda: None      # 不起真实线程：单测只手动 tick

    def _basic_fields(self):
        """横移步态警示用（与 MonitorService._basic_fields 同语义）。"""
        return self._state


def _post(path, svc, body=None):
    """装上假服务请求一次，用完立即还原全局 service（避免污染其他用例）。"""
    prev = main.service
    main.service = svc
    try:
        resp = TestClient(main.app).post(path, json=body or {})
    finally:
        main.service = prev
    return resp


def test_timed_endpoint_starts_and_auto_stops():
    svc = _FakeService()
    resp = _post("/api/v1/control/axis/timed", svc,
                 {"y": -0.3, "duration_s": 1.5, "channel": "real"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["timed"]["timed_active"] is True
    assert body["timed"]["timed_remaining"] == 1.5
    assert body["timed"]["channel"] == "real"

    # 未到点：持续发送（走 real 通道 = command 25）
    assert svc.watchdog.tick() == "axis_timed"
    decoded = asdu_parser.decode_frame(svc.sink.sent[-1])
    assert decoded["type"] == 2 and decoded["command"] == 25
    assert decoded["items"]["Y"] == -0.3

    # 越过 deadline：自动零位停发（不软急停）
    svc.clock.advance(2.0)
    n = len(svc.sink.sent)
    assert svc.watchdog.tick() == "timed_done"
    assert len(svc.sink.sent) == n + 1
    assert asdu_parser.decode_frame(svc.sink.sent[-1])["items"]["Y"] == 0.0
    assert svc.watchdog.status()["timed_active"] is False
    assert svc.control.estop is False
    assert svc.watchdog.tick() is None            # 到点后彻底停发


def test_timed_endpoint_rejects_when_control_disabled():
    svc = _FakeService(enabled=False)
    resp = _post("/api/v1/control/axis/timed", svc, {"x": 0.2, "duration_s": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["reason"] == "CONTROL_DISABLED"
    assert svc.sink.sent == []                     # 先验后行：一帧都没发
    assert svc.watchdog.status()["timed_active"] is False


def test_timed_endpoint_rejects_when_not_standing():
    """未站立（趴下）→ 前置校验拒绝，且不发任何帧。"""
    svc = _FakeService(state={"motion_state": 4, "control_usage_mode": 0})
    resp = _post("/api/v1/control/axis/timed", svc, {"y": 0.3, "duration_s": 3})
    body = resp.json()
    assert body["ok"] is False and body["reason"] == "PRECONDITION_FAILED"
    assert svc.sink.sent == []


def test_timed_endpoint_duration_bounds_are_validated():
    """0.5 ~ 30s 之外直接 422（前端也钳制，双保险）。"""
    svc = _FakeService()
    for bad in ({"x": 0.1, "duration_s": 0.2}, {"x": 0.1, "duration_s": 99}):
        resp = _post("/api/v1/control/axis/timed", svc, bad)
        assert resp.status_code == 422, resp.text


def test_axis_stop_aborts_timed():
    """中止 = 走 /axis/stop（与松手同路径）：零位停发，不软急停。"""
    svc = _FakeService()
    _post("/api/v1/control/axis/timed", svc, {"x": 0.2, "duration_s": 10})
    assert svc.watchdog.status()["timed_active"] is True

    resp = _post("/api/v1/control/axis/stop", svc)
    assert resp.status_code == 200
    assert resp.json()["watchdog"]["timed_active"] is False
    assert svc.control.estop is False
    svc.clock.advance(60.0)                        # 原 deadline 早过：也不得再发
    assert svc.watchdog.tick() is None


def test_axis_continuous_accepts_channel():
    """摇杆持续控制也支持通道选择（默认 steer，保持旧行为）。"""
    svc = _FakeService()
    resp = _post("/api/v1/control/axis", svc,
                 {"y": -0.4, "continuous": True, "channel": "real"})
    assert resp.json()["ok"] is True
    assert resp.json()["watchdog"]["channel"] == "real"
    assert svc.watchdog.tick() == "axis"
    assert asdu_parser.decode_frame(svc.sink.sent[-1])["command"] == 25

    # 缺省 channel → 主通道（command 21），与旧行为一致
    svc2 = _FakeService()
    _post("/api/v1/control/axis", svc2, {"y": -0.4, "continuous": True})
    svc2.watchdog.tick()
    assert asdu_parser.decode_frame(svc2.sink.sent[-1])["command"] == 21


# ------------------------------------------------- 横移步态警示（2026-10-16 结论）


def _state(gait, motion=1):
    return {"motion_state": motion, "control_usage_mode": 0, "gait": gait}


def test_lateral_warning_on_basic_gait():
    """基础（标准）步态 + Y 指令 → 带警示（只提示、不拦截，照发不误）。"""
    svc = _FakeService(state=_state(0x1001))
    resp = _post("/api/v1/control/axis/timed", svc, {"y": -0.3, "duration_s": 5})
    body = resp.json()
    assert body["ok"] is True                        # 警示不拦截
    assert "warning" in body
    assert "0x3002" in body["warning"]
    assert svc.watchdog.status()["timed_active"] is True   # 帧照常发
    assert svc.watchdog.tick() == "axis_timed"


def test_lateral_warning_absent_on_agile_gaits():
    """敏捷系步态（0x3002 / 0x3003）→ 无警示（含未装机步态也不误报）。"""
    for gait in (0x3002, 0x3003):
        svc = _FakeService(state=_state(gait))
        body = _post("/api/v1/control/axis/timed", svc,
                     {"y": 0.3, "duration_s": 2}).json()
        assert body["ok"] is True and "warning" not in body, gait


def test_lateral_warning_only_applies_to_y():
    """警示只针对横移：纯 X / Yaw 指令在基础步态下不带警示。"""
    svc = _FakeService(state=_state(0x1001))
    for payload in ({"x": 0.2, "duration_s": 2}, {"yaw": 0.4, "duration_s": 2}):
        body = _post("/api/v1/control/axis/timed", svc, payload).json()
        assert body["ok"] is True and "warning" not in body, payload


def test_lateral_warning_absent_without_basic_data():
    """basic 尚未上报（启动瞬间，gait=None）→ 不误报。"""
    svc = _FakeService()                             # 默认 state 无 gait 字段
    body = _post("/api/v1/control/axis/timed", svc, {"y": 0.3, "duration_s": 2}).json()
    assert body["ok"] is True and "warning" not in body


def test_lateral_warning_on_stair_standard_gait():
    """楼梯（标准）0x1003 与基础同系 → 也提示（横移未实测）。"""
    svc = _FakeService(state=_state(0x1003))
    body = _post("/api/v1/control/axis/timed", svc, {"y": 0.3, "duration_s": 2}).json()
    assert "warning" in body and "0x3002" in body["warning"]
