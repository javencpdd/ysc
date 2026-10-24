"""控制权归属（多操作员互斥）单测 —— 2026-10-19 加。

背景：控制闸是**全局单例**（``_svc()`` 只有一个 ``ControlGateway``），多个浏览器
终端共享同一把开关。改造前的行为是"谁最后点谁说了算"，存在两类真实风险：

1. A 正在遥控，B 点一下"停止"就把 A 掐断；
2. A、B 可同时开启、同时往一条狗发运动指令（两人开一台车）。

本文件守住改造后的六条底线：

1. **一人独占** —— 同一时刻只有一个 owner，他人申请返回 ``CONTROL_HELD``；
2. **非 owner 只读** —— 驱动类指令被拒（``NOT_OWNER`` / 409），一条帧都不发出去；
3. **安全手段优先** —— 软急停 / 心跳不受归属限制（被别人占着也必须能急停）；
4. **接管先停车** —— 强制接管前发安全零位，不能"换人时车还在走"；
5. **不会锁死** —— owner 超时未续约自动释放（浏览器崩溃 / 拔网线）；
6. **向后兼容** —— 无主模式（单测 / 本机脚本直接 ``enable()``）行为不变。
"""

import pytest

from control.axis_watchdog import AxisWatchdog
from control.control_gateway import ControlGateway, RecordingSink

STANDING = {"motion_state": 1, "control_usage_mode": 0}


class _Clock:
    """可控时钟：用于精确验证租约与 owner 超时。"""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _gw(enabled: bool = False, lease: float = 5.0, owner_timeout: float = 15.0):
    clk = _Clock()
    sink = RecordingSink()
    gw = ControlGateway(sink, enabled=enabled, lease_seconds=lease,
                        state_provider=lambda: dict(STANDING),
                        clock=clk, owner_timeout_seconds=owner_timeout)
    return gw, sink, clk


# ------------------------------------------------------------------ 1. 独占
def test_acquire_grants_ownership():
    gw, _sink, _clk = _gw()
    res = gw.acquire("terminal-AAAA", label="操作员A")
    assert res["ok"] is True
    assert gw.enabled is True
    view = gw.owner_view()
    assert view["held"] is True
    assert view["session"] == "terminal"          # 对外只给 8 位短码
    assert view["label"] == "操作员A"


def test_second_terminal_is_rejected_with_owner_info():
    """他人已占用 → 409 CONTROL_HELD，并带上占用者信息给前端展示。"""
    gw, _sink, clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    clk.advance(3.0)
    res = gw.acquire("terminal-BBBB", label="操作员B")
    assert res["ok"] is False
    assert res["reason"] == "CONTROL_HELD"
    assert res["owner"]["session"] == "terminal"
    assert res["owner"]["label"] == "操作员A"
    assert res["owner"]["age_s"] == pytest.approx(3.0)
    # 归属没被改写
    assert gw.owner_view()["label"] == "操作员A"


def test_acquire_is_idempotent_for_same_session():
    """自己重复申请 = 续期，不重复发零位、不重置持有时长。"""
    gw, sink, clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    clk.advance(4.0)
    before = sink.sent.copy()
    res = gw.acquire("terminal-AAAA", label="操作员A")
    assert res["ok"] is True
    assert sink.sent == before                     # 没多发帧
    assert gw.owner_view()["age_s"] == pytest.approx(4.0)
    assert gw.owner_view()["idle_s"] == pytest.approx(0.0)   # last_seen 已刷新


def test_acquire_without_session_is_rejected():
    gw, _sink, _clk = _gw()
    res = gw.acquire("")
    assert res["ok"] is False and res["reason"] == "NO_SESSION"


# -------------------------------------------------------------- 2. 非 owner 只读
def test_non_owner_command_is_rejected_and_sends_nothing():
    gw, sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    sink.sent.clear()
    res = gw.execute("stand_up", session_id="terminal-BBBB")
    assert res["ok"] is False
    assert res["reason"] == "NOT_OWNER"
    assert res["status"] == 409
    assert sink.sent == []                         # 一条都没发出去


def test_owner_command_passes():
    gw, sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    sink.sent.clear()
    assert gw.execute("stand_up", session_id="terminal-AAAA")["ok"] is True
    assert len(sink.sent) == 1


def test_missing_session_is_rejected_when_owned():
    """有主模式下不带身份 = 拒绝（否则任何脚本都能绕过互斥）。"""
    gw, _sink, _clk = _gw()
    gw.acquire("terminal-AAAA")
    res = gw.execute("stand_up")
    assert res["ok"] is False and res["reason"] == "NOT_OWNER"


# ---------------------------------------------------------- 3. 安全手段优先
def test_safety_commands_bypass_ownership():
    """被别人占着控制权时，软急停 / 解急停 / 心跳必须仍然可用。"""
    gw, sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    sink.sent.clear()
    res = gw.execute("soft_estop", session_id="terminal-BBBB")
    assert res["ok"] is True
    assert len(sink.sent) == 1
    assert gw.estop is True


# ------------------------------------------------------------ 4. 接管先停车
def test_forced_takeover_sends_zero_frame_first():
    gw, sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    # 让 A 先动起来，留下非零轴值
    gw.execute("axis", {"x": 0.3, "y": 0.0, "z": 0.0,
                        "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
               session_id="terminal-AAAA")
    sink.sent.clear()
    res = gw.acquire("terminal-BBBB", label="操作员B", force=True)
    assert res["ok"] is True
    assert gw.owner_view()["label"] == "操作员B"
    assert sink.sent, "接管前必须先发一帧安全零位把车停下"
    # 零位帧：axis 编码，全轴速度为 0
    assert sink.sent[0] != b""


def test_release_by_non_owner_is_rejected():
    """旁观者不能随手掐掉操作员（释放需是 owner 或 force）。"""
    gw, _sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    res = gw.release("terminal-BBBB")
    assert res["ok"] is False and res["reason"] == "NOT_OWNER"
    assert gw.enabled is True                      # 操作员 A 不受影响


def test_owner_release_returns_to_l0():
    gw, _sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    res = gw.release("terminal-AAAA")
    assert res["ok"] is True
    assert gw.enabled is False
    assert gw.owner_view()["held"] is False
    # 释放后回到无主：再申请即可（不会被僵尸 owner 卡住）
    assert gw.acquire("terminal-BBBB")["ok"] is True


# -------------------------------------------------------------- 5. 不会锁死
def test_owner_expires_when_not_renewed():
    """浏览器崩溃 / 拔网线不会有主动释放请求 —— 超时必须自动回收，否则锁死所有人。"""
    gw, sink, clk = _gw(owner_timeout=15.0)
    gw.acquire("terminal-AAAA", label="操作员A")
    clk.advance(16.0)
    sink.sent.clear()
    # 触发点：任意状态读取
    view = gw.status()["owner"]
    assert view["held"] is False
    assert gw.enabled is False
    assert sink.sent, "超时释放前应先发零位兜底（操控者失联时让车停下）"
    # 别人可以接手
    assert gw.acquire("terminal-BBBB")["ok"] is True


def test_owner_keeps_alive_by_renewing():
    gw, _sink, clk = _gw(owner_timeout=15.0)
    gw.acquire("terminal-AAAA")
    for _ in range(5):
        clk.advance(5.0)
        gw.renew_lease(session_id="terminal-AAAA")
    assert gw.owner_view()["held"] is True
    assert gw.enabled is True


def test_non_owner_cannot_renew_lease():
    """旁观终端开着页面不能替操作员续约 —— 否则"断开即失效"保护失效。"""
    gw, _sink, clk = _gw()
    gw.acquire("terminal-AAAA")
    clk.advance(4.0)
    assert gw.renew_lease(session_id="terminal-BBBB") == 0.0
    # owner 自己续约正常
    assert gw.renew_lease(session_id="terminal-AAAA") > 0


# ------------------------------------------------------------ 6. 向后兼容
def test_ownerless_mode_keeps_old_behavior():
    """无主模式（直接 enable()，单测 / 本机脚本）不带 session 也应照旧放行。"""
    gw, sink, _clk = _gw()
    gw.enable()
    gw.renew_lease()
    assert gw.execute("stand_up")["ok"] is True
    assert len(sink.sent) == 1
    assert gw.is_owner("随便哪个终端") is True


def test_disable_clears_ownership():
    gw, _sink, _clk = _gw()
    gw.acquire("terminal-AAAA")
    gw.disable()
    assert gw.owner_view()["held"] is False
    assert gw.enabled is False


# ------------------------------------------------------------ 看门狗（持续驱动）
def test_watchdog_rejects_non_owner_feed():
    """持续开车（摇杆）也必须受归属约束，否则能从侧门绕过互斥。"""
    gw, sink, _clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    wd = AxisWatchdog(gw, hz=20, timeout_ms=250, clock=_clk, sleeper=lambda _s: None)
    assert wd.feed({"x": 0.3}, session_id="terminal-BBBB") is False
    assert wd.is_active() is False
    assert sink.sent == []


def test_watchdog_owner_feed_passes_ownership():
    """owner 自己的持续驱动必须能走通（循环里每帧透传 session）。"""
    gw, sink, clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    wd = AxisWatchdog(gw, hz=20, timeout_ms=250, clock=clk, sleeper=lambda _s: None)
    assert wd.feed({"x": 0.3}, session_id="terminal-AAAA") is True
    sink.sent.clear()
    assert wd.tick() == "axis"                     # 循环里真的发出去了
    assert len(sink.sent) == 1


def test_watchdog_timed_move_respects_ownership():
    gw, _sink, clk = _gw()
    gw.acquire("terminal-AAAA", label="操作员A")
    wd = AxisWatchdog(gw, hz=20, timeout_ms=250, clock=clk, sleeper=lambda _s: None)
    assert wd.feed_timed({"x": 0.3}, 2.0, session_id="terminal-BBBB") is False
    assert wd.feed_timed({"x": 0.3}, 2.0, session_id="terminal-AAAA") is True


# --------------------------------------------------- 7. HTTP 端点必须透传身份
# 2026-10-19 真踩：机器人设置面板走 /api/v1/robot/* 独立端点，只改了
# /control/command 的 session 透传 → 单人使用也报 NOT_OWNER「未携带终端标识」。
# 下面把"每个写端点都要带身份"钉死，防止再漏。
import time

from fastapi.testclient import TestClient

import main
from config import Settings


def _api_service():
    svc = main.MonitorService(Settings(data_source="mock"))
    svc.state.update({"topic": "basic",
                      "fields": {"motion_state": 1, "control_usage_mode": 0},
                      "recv_monotonic": time.monotonic(), "recv_wall": time.time()})
    svc.control.acquire("aaa11111", label="操作员A")
    return svc


def _post(path, svc, body=None):
    prev = main.service
    main.service = svc
    try:
        return TestClient(main.app).post(path, json=body or {})
    finally:
        main.service = prev


def test_robot_light_passes_owner_session():
    svc = _api_service()
    res = _post("/api/v1/robot/light", svc,
                {"front": True, "back": False, "session_id": "aaa11111"}).json()
    assert res.get("reason") != "NOT_OWNER"


def test_robot_light_without_session_is_rejected():
    """有主模式下未带身份 → NOT_OWNER（正是用户截图里那条报错）。"""
    svc = _api_service()
    res = _post("/api/v1/robot/light", svc, {"front": True, "back": False}).json()
    assert res["ok"] is False and res["reason"] == "NOT_OWNER"


def test_robot_light_with_other_session_is_rejected():
    svc = _api_service()
    res = _post("/api/v1/robot/light", svc,
                {"front": True, "back": False, "session_id": "bbb22222"}).json()
    assert res["ok"] is False and res["reason"] == "NOT_OWNER"


def test_robot_sleep_and_auto_reset_pass_owner_session():
    svc = _api_service()
    r1 = _post("/api/v1/robot/auto_reset", svc,
               {"enable": True, "confirmed": True, "session_id": "aaa11111"}).json()
    assert r1.get("reason") != "NOT_OWNER"
    r2 = _post("/api/v1/robot/sleep", svc,
               {"sleep": False, "auto": True, "minutes": 10,
                "confirmed": True, "session_id": "aaa11111"}).json()
    assert r2.get("reason") != "NOT_OWNER"


def test_robot_config_refresh_is_readonly_for_non_owner():
    """两条都是只读查询（always_allowed）：非 owner 也要能读配置，不能因归属被拒。"""
    svc = _api_service()
    res = _post("/api/v1/robot/config/refresh", svc, {"session_id": "bbb22222"}).json()
    assert res["ok"] is True
    assert all(res["sent"].values())
