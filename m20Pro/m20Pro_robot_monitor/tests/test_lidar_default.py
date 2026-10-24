"""雷达默认关闭策略（显式配置开关）单测 —— 2026-10-20。

覆盖四条硬边界 + 两个触发时机：
  1. 开关没开 → 一条不发（默认行为不变）；
  2. 雷达已经关着 → 一条不发（启动时绝大多数情况）；
  3. 站立 / RL 态 → 跳过（与人工操作共用同一道运动锁）；
  4. 系统通道只准"关雷达"这一种形状（不许借它开机、不许借它关别的设备）；
  5. 触发时机只有"启动（等设备帧）"与"唤醒后"两个，且都限速；
  6. 页面开关可覆盖部署配置，重启后回到配置值（source 字段）。
"""

import time

import pytest

from control import patrol_codec
from control.control_gateway import ControlGateway, RecordingSink
from control.command_log import CommandLog
from control.lidar_default import LidarDefaultPolicy, MIN_INTERVAL_S


# ---------------------------------------------------------------- 工具
class FakeClock:
    """可手动推进的单调时钟（测限速用）。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, sec: float) -> None:
        self.now += sec


def _policy(gateway, device, basic, enabled=True, clock=None):
    return LidarDefaultPolicy(
        gateway=gateway,
        device_provider=lambda: device,
        basic_provider=lambda: basic,
        enabled=enabled,
        clock=clock or FakeClock(),
        wall_clock=time.time)


def _gw_with(device=None, basic=None):
    """真网关 + 记录型出口 + 状态/设备提供者（与生产接线一致）。"""
    sink = RecordingSink()
    gw = ControlGateway(
        sink, enabled=True, lease_seconds=5.0,
        state_provider=lambda: {"basic": basic or {}},
        device_provider=lambda: device or {})
    gw.renew_lease()
    gw.enable()
    gw.command_log = CommandLog(size=50, timeout_s=2.0)
    return gw, sink


def _lidar_items(frame: bytes):
    """从发出的帧里解出 Items（验证发的确实是"关雷达"）。"""
    import json
    body = json.loads(frame[16:].decode("utf-8"))
    return body["PatrolDevice"]["Items"]


# ---------------------------------------------------------------- 默认行为
def test_disabled_by_default_sends_nothing():
    """开关没开（部署配置默认 False）→ 一条不发，页面显示原因。"""
    gw, sink = _gw_with(device={"dev_enable": {"Lidar": {"Front": 2, "Back": 2}}},
                        basic={"motion_state": patrol_codec.MOTION_LIE_DOWN})
    pol = _policy(gw, {"dev_enable": {"Lidar": {"Front": 2, "Back": 2}}},
                  {"motion_state": patrol_codec.MOTION_LIE_DOWN}, enabled=False)
    res = pol.maybe_apply("startup")
    assert res["outcome"] == "skipped" and res["reason"] == "disabled"
    assert sink.sent == []
    assert pol.status()["enabled"] is False
    assert pol.status()["source"] == "config"


def test_already_off_sends_nothing():
    """雷达已经是关的 → 不发（启动瞬间的常态，避免每次重启都多发一帧）。"""
    gw, sink = _gw_with(device={"dev_enable": {"Lidar": {"Front": 0, "Back": 0}}},
                        basic={"motion_state": patrol_codec.MOTION_LIE_DOWN})
    pol = _policy(gw, {"dev_enable": {"Lidar": {"Front": 0, "Back": 0}}},
                  {"motion_state": patrol_codec.MOTION_LIE_DOWN})
    res = pol.maybe_apply("startup")
    assert res["outcome"] == "skipped" and res["reason"] == "already_off"
    assert sink.sent == []


def test_no_device_data_skips():
    """还没收到设备帧 → 不猜、不发（不能因为"不知道"就默认它开着）。"""
    gw, sink = _gw_with(device={}, basic={"motion_state": patrol_codec.MOTION_LIE_DOWN})
    pol = _policy(gw, {}, {"motion_state": patrol_codec.MOTION_LIE_DOWN})
    res = pol.maybe_apply("startup")
    assert res["outcome"] == "skipped" and res["reason"] == "no_device_data"
    assert sink.sent == []


# ---------------------------------------------------------------- 安全边界
@pytest.mark.parametrize("motion", [patrol_codec.MOTION_STAND, patrol_codec.MOTION_RL])
def test_standing_or_rl_is_skipped(motion):
    """站立 / RL 态 → 跳过：与人工操作共用同一道运动锁，一条都没放宽。"""
    dev = {"dev_enable": {"Lidar": {"Front": 2, "Back": 2}}}
    gw, sink = _gw_with(device=dev, basic={"motion_state": motion})
    pol = _policy(gw, dev, {"motion_state": motion})
    res = pol.maybe_apply("wake")
    assert res["outcome"] == "skipped" and res["reason"] == "motion_locked"
    assert sink.sent == []


def test_applies_when_lying_down_and_lidar_on():
    """趴下 + 雷达开着 → 发一帧"关雷达"，且内容正确（前后都 0）。"""
    dev = {"dev_enable": {"Lidar": {"Front": 2, "Back": 1}}}
    gw, sink = _gw_with(device=dev, basic={"motion_state": patrol_codec.MOTION_LIE_DOWN})
    pol = _policy(gw, dev, {"motion_state": patrol_codec.MOTION_LIE_DOWN})
    res = pol.maybe_apply("startup")
    assert res["outcome"] == "applied" and res["trigger"] == "startup"
    assert len(sink.sent) == 1
    assert _lidar_items(sink.sent[0]) == {"Lidar": {"Front": 0, "Back": 0}}


def test_rate_limit_between_auto_applies():
    """两次自动下发之间限速：连点「唤醒」不会突发。"""
    clock = FakeClock()
    dev = {"dev_enable": {"Lidar": {"Front": 2, "Back": 2}}}
    basic = {"motion_state": patrol_codec.MOTION_LIE_DOWN}
    gw, sink = _gw_with(device=dev, basic=basic)
    pol = _policy(gw, dev, basic, clock=clock)
    assert pol.maybe_apply("wake")["outcome"] == "applied"
    # 立刻再触发：雷达"仍开着"（出口是记录型，不会真改车侧状态）→ 被限速拦下
    clock.advance(1.0)
    res = pol.maybe_apply("wake")
    assert res["outcome"] == "skipped" and res["reason"] == "too_soon"
    assert len(sink.sent) == 1
    # 过了限速窗口才允许再发
    clock.advance(MIN_INTERVAL_S + 1)
    assert pol.maybe_apply("wake")["outcome"] == "applied"
    assert len(sink.sent) == 2


def test_system_channel_only_allows_lidar_off():
    """系统通道不是通用后门：只准 device_switch/Lidar 且只能关。"""
    gw, sink = _gw_with()
    with pytest.raises(Exception):
        gw.execute_system_device("device_switch", {"items": {"GPS": 0}})
    with pytest.raises(Exception):
        gw.execute_system_device("device_switch", {"items": {"Lidar": {"Front": 1, "Back": 1}}})
    with pytest.raises(Exception):
        gw.execute_system_device("stand_up", {})
    assert sink.sent == []


def test_system_channel_still_enforces_motion_lock():
    """系统通道保留运动锁：站着的时候策略也发不出去（真网关判定，不是策略自己判）。"""
    dev = {"dev_enable": {"Lidar": {"Front": 2, "Back": 2}}}
    gw, sink = _gw_with(device=dev, basic={"motion_state": patrol_codec.MOTION_STAND})
    res = gw.execute_system_device("device_switch",
                                   {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                                   reason="test")
    assert res["ok"] is False and res["reason"] == "PRECONDITION_FAILED"
    assert sink.sent == []


# ---------------------------------------------------------------- 页面开关
def test_runtime_override_and_source():
    """页面可覆盖部署配置；source 说明值来自哪里（重启后回到配置值）。"""
    gw, sink = _gw_with()
    pol = _policy(gw, {}, {}, enabled=False)
    assert pol.status()["source"] == "config"
    st = pol.set_enabled(True)
    assert st["enabled"] is True and st["source"] == "runtime"
    # 关掉时只改策略，不重新打开雷达（不会发任何帧）
    st = pol.set_enabled(False)
    assert st["enabled"] is False and sink.sent == []


# ---------------------------------------------------------------- 启动触发
def test_startup_waits_for_device_frame_then_applies():
    """启动路径：设备帧从"陈旧"变"新鲜"后才应用一次（不阻塞 start()）。"""
    dev = {"dev_enable": {"Lidar": {"Front": 2, "Back": 2}}}
    basic = {"motion_state": patrol_codec.MOTION_LIE_DOWN}
    gw, sink = _gw_with(device=dev, basic=basic)
    pol = _policy(gw, dev, basic)

    calls = {"n": 0}

    def is_stale(topic):
        # 前两次陈旧，第三次新鲜 —— 模拟"等帧到达"
        calls["n"] += 1
        return calls["n"] < 3

    pol.apply_after_startup(is_stale)
    assert calls["n"] >= 3
    assert len(sink.sent) == 1
    assert _lidar_items(sink.sent[0]) == {"Lidar": {"Front": 0, "Back": 0}}


def test_startup_gives_up_when_device_frame_never_arrives(monkeypatch):
    """链路断 / mock 无数据：等满超时静默退出，不发帧、不留线程。"""
    gw, sink = _gw_with()
    pol = _policy(gw, {}, {})

    # 把 60s 超时压成 0.2s，避免测试真的等一分钟
    import control.lidar_default as ld
    monkeypatch.setattr(ld, "STARTUP_WAIT_S", 0.2)
    monkeypatch.setattr(ld, "POLL_S", 0.05)
    pol.apply_after_startup(lambda topic: True)
    assert sink.sent == []
    assert pol.status()["last_apply"]["outcome"] == "never"


# ---------------------------------------------------------------- API 契约
def _svc():
    """mock 数据源的 MonitorService（RecordingSink，不发真包）。"""
    import main
    from config import Settings
    svc = main.MonitorService(Settings(data_source="mock"))
    svc.control.enable()
    svc.control.renew_lease()
    return svc, svc.control._sink


def _inject(svc, topic, **fields):
    """直接往状态仓库写一帧（等价于收到一帧上报）。

    ⚠️ 扁平字段要放在 ``fields`` 下 —— ``StateStore.snapshot`` 取的是
    ``frame["fields"]``，不是帧的顶层键（2026-10-20 踩过：放顶层会静默变成空数据）。
    """
    svc.state.update({"topic": topic, "items": {}, "fields": fields})


def _post(path, svc, body=None):
    import main
    from fastapi.testclient import TestClient
    prev = main.service
    main.service = svc
    try:
        return TestClient(main.app).post(path, json=body or {})
    finally:
        main.service = prev


def _get(path, svc):
    import main
    from fastapi.testclient import TestClient
    prev = main.service
    main.service = svc
    try:
        return TestClient(main.app).get(path)
    finally:
        main.service = prev


def test_config_get_includes_lidar_default():
    """/robot/config 带出策略状态（前端进设置页就能看到，无需另开轮询）。"""
    svc, _ = _svc()
    res = _get("/api/v1/robot/config", svc)
    assert res.status_code == 200
    ld = res.json()["lidar_default"]
    assert ld["enabled"] is False and ld["source"] == "config"
    assert ld["last_apply"]["outcome"] == "never"


def test_setting_requires_confirmation_and_sends_nothing():
    """改策略同样要二次确认；被拦时一条报文都不发。"""
    svc, sink = _svc()
    res = _post("/api/v1/robot/lidar-default", svc, {"enabled": True})
    assert res.status_code == 200
    assert res.json()["ok"] is False and res.json()["reason"] == "CONFIRM_REQUIRED"
    assert sink.sent == []


def test_enabling_applies_immediately_when_lidar_on():
    """开开关 + 雷达开着 + 趴着 → 立即应用一次，发出"关雷达"帧。"""
    svc, sink = _svc()
    _inject(svc, "device", dev_enable={"Lidar": {"Front": 2, "Back": 2}})
    _inject(svc, "basic", motion_state=4, motion_state_label="趴下")
    res = _post("/api/v1/robot/lidar-default", svc,
                {"enabled": True, "confirmed": True, "apply_now": True})
    body = res.json()
    assert body["ok"] is True and body["enabled"] is True
    assert body["applied"]["outcome"] == "applied"
    assert len(sink.sent) == 1
    assert _lidar_items(sink.sent[0]) == {"Lidar": {"Front": 0, "Back": 0}}


def test_enabling_when_lidar_already_off_sends_nothing():
    """雷达本来就关着 → 开开关也不发帧（应用结果显示 already_off）。"""
    svc, sink = _svc()
    _inject(svc, "device", dev_enable={"Lidar": {"Front": 0, "Back": 0}})
    _inject(svc, "basic", motion_state=4, motion_state_label="趴下")
    res = _post("/api/v1/robot/lidar-default", svc,
                {"enabled": True, "confirmed": True})
    body = res.json()
    assert body["ok"] is True
    assert body["applied"]["outcome"] == "skipped"
    assert body["applied"]["reason"] == "already_off"
    assert sink.sent == []


def test_disabling_does_not_turn_lidar_back_on():
    """关掉策略 ≠ 打开雷达：一条帧都不发（要开雷达请走运动控制页开关）。"""
    svc, sink = _svc()
    _inject(svc, "device", dev_enable={"Lidar": {"Front": 0, "Back": 0}})
    res = _post("/api/v1/robot/lidar-default", svc,
                {"enabled": False, "confirmed": True})
    assert res.json()["ok"] is True and res.json()["enabled"] is False
    assert sink.sent == []


def test_disabling_with_apply_now_does_not_overwrite_last_apply():
    """关闭策略时 apply_now 缺省也不该跑应用 —— 否则"最近一次应用"会被
    覆盖成"策略未开启"，让人误以为刚才那次应用失败了（真机验证时踩到）。"""
    svc, sink = _svc()
    _inject(svc, "device", dev_enable={"Lidar": {"Front": 2, "Back": 2}})
    _inject(svc, "basic", motion_state=4, motion_state_label="趴下")
    # 先开启一次（会真应用），再带着 apply_now 关掉
    _post("/api/v1/robot/lidar-default", svc,
          {"enabled": True, "confirmed": True, "apply_now": True})
    assert svc.lidar_default.status()["last_apply"]["outcome"] == "applied"
    res = _post("/api/v1/robot/lidar-default", svc,
                {"enabled": False, "confirmed": True, "apply_now": True})
    body = res.json()
    assert body["enabled"] is False
    assert body["applied"] is None                      # 关闭时压根不尝试应用
    assert body["last_apply"]["outcome"] == "applied"   # 上一次的记录没被冲掉
    assert len(sink.sent) == 1                          # 只有开启时那一帧


def test_wake_command_triggers_policy_once():
    """唤醒整车之后策略自动应用一次（唤醒会恢复传感器供电，见取证笔记 §4.3）。"""
    svc, sink = _svc()
    _inject(svc, "device", dev_enable={"Lidar": {"Front": 2, "Back": 2}})
    _inject(svc, "basic", motion_state=4, motion_state_label="趴下")
    svc.lidar_default.set_enabled(True)
    res = _post("/api/v1/control/command", svc,
                {"name": "wake_up", "params": {}, "confirmed": True})
    assert res.json()["ok"] is True
    # 一帧唤醒 + 一帧关雷达
    assert len(sink.sent) == 2
    assert _lidar_items(sink.sent[1]) == {"Lidar": {"Front": 0, "Back": 0}}
    assert svc.lidar_default.status()["last_apply"]["trigger"] == "wake"
