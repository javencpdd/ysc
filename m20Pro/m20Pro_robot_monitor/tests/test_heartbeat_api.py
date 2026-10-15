"""心跳（遥测）暂停 / 恢复 API 契约测试（2026-10-16 加）。

守住四条底线：

1. **不蒙眼开车** —— 暂停遥视前必须先零位停发正在进行的控制（摇杆 / 定时移动）；
2. **二次确认** —— 停心跳 = 放弃遥测，需 ``confirmed``（与 L1 开启同级谨慎）；
3. **不假成功** —— 数据源不支持暂停时明确 ``NOT_SUPPORTED``，不静默返回 ok；
4. **降级标志可达前端** —— ``ServiceSnapshot.degraded`` 落进快照，前端才能把
   "主动暂停"与"链路故障"区分开（两者提示语义相反）。

关于"机器人会不会因为没心跳而趴下"：**不会**。2026-10-16 实证——控制台重启后
``sent_packets=0``（零指令）持续数分钟，车仍稳定保持 ``motion_state=17``（RL 站立）。
车侧真正的断链保护在 rl_deploy 的 DDS_CMD 看门狗（``Disable lynx``），
效果是停运动而非趴下。见 ADR-015。
"""

from fastapi.testclient import TestClient

import time

import main
from config import Settings


class _FakeSource:
    """可暂停的假数据源（替掉 mock 源：mock 故意不支持暂停，见 NOT_SUPPORTED 用例）。"""

    mode = "udp"

    def __init__(self) -> None:
        self._paused = False
        self.pause_calls = 0
        self.resume_calls = 0

    @property
    def pausable(self) -> bool:
        return True

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> bool:
        self.pause_calls += 1
        self._paused = True
        return True

    def resume(self) -> bool:
        self.resume_calls += 1
        self._paused = False
        return True

    def stats(self) -> dict:
        return {"mode": self.mode, "running": True, "paused": self._paused,
                "target": "127.0.0.1:30000", "sent_heartbeats": 42}


class _StubWatchdog:
    """只记录 pause 调用的看门狗替身（本文件只关心"暂停前有没有停控制"）。"""

    def __init__(self, active: bool = True) -> None:
        self._active = active
        self.paused_with = None

    def is_active(self) -> bool:
        return self._active

    def pause(self, reason: str = "") -> None:
        self.paused_with = reason
        self._active = False

    def status(self) -> dict:
        return {"timed_active": False}


def _service(source=None, watchdog_active=True):
    """真实 MonitorService（mock 数据源、记录型出口），再替换 source/watchdog。"""
    svc = main.MonitorService(Settings(data_source="mock"))
    # 喂一份站立态基础状态：否则前置闸（MotionState∈{1,17}）会拒发，
    # 测的就不是遥测闸了
    svc.state.update({"topic": "basic",
                      "fields": {"motion_state": 1, "control_usage_mode": 0},
                      "recv_monotonic": time.monotonic(), "recv_wall": time.time()})
    svc.source = source if source is not None else _FakeSource()
    svc.watchdog = _StubWatchdog(active=watchdog_active)
    return svc


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


def test_pause_requires_confirmation():
    """未确认 → CONFIRM_REQUIRED，且**不能**真的停心跳 / 停控制。"""
    svc = _service()
    body = _post("/api/v1/link/heartbeat", svc, {"paused": True}).json()
    assert body["ok"] is False and body["reason"] == "CONFIRM_REQUIRED"
    assert svc.source.paused is False
    assert svc.watchdog.paused_with is None


def test_pause_stops_running_control_first():
    """★ 不蒙眼开车：暂停遥测前先把正在进行的控制零位停发。"""
    svc = _service(watchdog_active=True)
    body = _post("/api/v1/link/heartbeat", svc,
                 {"paused": True, "confirmed": True}).json()
    assert body["ok"] is True
    assert body["heartbeat_paused"] is True
    assert body["control_stopped"] is True            # 先停了车
    assert svc.watchdog.paused_with == "heartbeat_paused"
    assert svc.source.paused is True
    # 降级标志落进快照（前端据此分色，不与"链路故障"混淆）
    service = svc.state.snapshot()["service"]
    assert service["degraded"] is True
    assert service["degraded_reason"] == main.DEGRADED_HEARTBEAT_PAUSED


def test_pause_without_running_control_is_still_ok():
    """本来就没在控制 → 直接暂停，control_stopped=False（不是每次都要停车）。"""
    svc = _service(watchdog_active=False)
    body = _post("/api/v1/link/heartbeat", svc,
                 {"paused": True, "confirmed": True}).json()
    assert body["ok"] is True and body["control_stopped"] is False
    assert svc.source.paused is True


def test_paused_telemetry_blocks_axis_via_gate():
    """暂停后走真实网关发轴指令 → TELEMETRY_PAUSED（端到端过闸）。"""
    svc = _service()
    svc.control.enable()
    svc.control.renew_lease(999.0)
    res = svc.control.execute("axis", {"y": -0.3})
    assert res["ok"] is True                          # 未暂停：正常放行
    _post("/api/v1/link/heartbeat", svc, {"paused": True, "confirmed": True})
    res2 = svc.control.execute("axis", {"y": -0.3})
    assert res2["ok"] is False and res2["reason"] == "TELEMETRY_PAUSED"
    # 软急停仍然可达（安全手段优先）
    assert svc.control.execute("soft_estop")["ok"] is True


def test_resume_restores_telemetry_and_clears_degraded():
    svc = _service()
    _post("/api/v1/link/heartbeat", svc, {"paused": True, "confirmed": True})
    assert svc.heartbeat_paused is True
    body = _post("/api/v1/link/heartbeat", svc, {"paused": False}).json()
    assert body["ok"] is True and body["heartbeat_paused"] is False
    assert svc.source.paused is False
    service = svc.state.snapshot()["service"]
    assert service["degraded"] is False and service["degraded_reason"] is None
    # 恢复后指令放行
    svc.control.enable()
    svc.control.renew_lease(999.0)
    assert svc.control.execute("axis", {"x": 0.2})["ok"] is True


def test_mock_source_reports_not_supported():
    """mock 数据源不支持暂停 → 明确 NOT_SUPPORTED（不假成功）。"""
    svc = _service(source=main.MonitorService(Settings(data_source="mock")).source)
    body = _post("/api/v1/link/heartbeat", svc,
                 {"paused": True, "confirmed": True}).json()
    assert body["ok"] is False and body["reason"] == "NOT_SUPPORTED"
    assert svc.state.snapshot()["service"]["degraded"] is False   # 没真暂停就别标降级


def test_status_endpoint_reports_paused():
    svc = _service()
    _post("/api/v1/link/heartbeat", svc, {"paused": True, "confirmed": True})
    body = _get("/api/v1/link/heartbeat", svc).json()
    assert body["ok"] is True and body["heartbeat_paused"] is True
    assert body["source"]["paused"] is True
