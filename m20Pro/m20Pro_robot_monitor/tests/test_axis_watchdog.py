"""轴指令看门狗单测：20Hz 循环 + "只停不趴"兜底（PLAN §6.4）。

2026-10-15 二次事故修正后行为（v3）：
- feed 停更 → 零位 + 停发（等待恢复）；**任何时长都绝不自动软急停**
- 任何 pause（松手 / 断连 / 页面隐藏 / 停机）→ 零位 + 停发；绝不软急停
- 恢复 = 收到新 feed

两次真机事故（均为"自动软急停"所致）见 ``axis_watchdog.py`` 模块文档。
"""


class FakeClock:
    """可控时钟：让"超时"不需要真的 sleep。"""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _watchdog(state=None, timeout_ms=250, clock=None):
    from control.control_gateway import ControlGateway, RecordingSink
    clock = clock or FakeClock()
    sink = RecordingSink()
    gw = ControlGateway(sink, enabled=True, lease_seconds=999.0,
                        state_provider=(lambda: state) if state is not None else None)
    gw.enable()
    gw.renew_lease(999.0)
    from control.axis_watchdog import AxisWatchdog
    wd = AxisWatchdog(gw, hz=20, timeout_ms=timeout_ms, clock=clock,
                      sleeper=lambda _s: None)
    return wd, sink, clock, gw


def test_feed_then_tick_sends_axis():
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.5, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.2})
    assert wd.tick() == "axis"
    assert len(sink.sent) == 1
    assert wd.status()["sent_frames"] == 1


# ---------------------------------------------------------------- feed 停更（只停不趴）
def test_feed_stale_sends_zero_and_never_estop():
    """停更 → 零位一帧 + 停发；无论多久无恢复都绝不软急停（事故二修正）。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.6})
    assert wd.tick() == "axis"
    clock.advance(0.5)                      # 超过 250ms 未见新指令
    assert wd.tick() == "stale"             # 零位一帧 + 停发
    assert gw.estop is False                # 不软急停
    assert wd.status()["stale"] is True
    # 等待期内保持沉默：不再发送任何帧
    n = len(sink.sent)
    assert wd.tick() is None
    assert len(sink.sent) == n
    # v3 关键断言：过 10s（旧升级点）/ 60s 也绝不软急停
    clock.advance(10.0)
    assert wd.tick() is None
    clock.advance(60.0)
    assert wd.tick() is None
    assert len(sink.sent) == n
    assert gw.estop is False


def test_feed_stale_resume_continues():
    """停更后恢复 feed → 继续发送，永不软急停。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.3})
    wd.tick()
    clock.advance(0.5)
    assert wd.tick() == "stale"
    wd.feed({"x": 0.2})                     # 恢复
    assert wd.tick() == "axis"
    assert gw.estop is False
    assert wd.status()["stale"] is False


# ---------------------------------------------------------------- 异常断开（只停不趴）
def test_pause_on_ws_disconnect_sends_zero_never_estop():
    """异常断开：零位 + 停发；过任意久也不自动软急停（升级机制已切除）。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.3})
    gw._lease_until = 0.0                   # 模拟 _on_last_client_gone 清租约
    n = len(sink.sent)
    wd.pause("ws_disconnected")
    assert len(sink.sent) == n + 1          # 零位一帧
    assert gw.estop is False
    clock.advance(600.0)                    # 10 分钟无恢复
    assert wd.tick() is None
    assert gw.estop is False                # 仍然不软急停


# ---------------------------------------------------------------- 停机 / 松手
def test_stop_while_active_sends_zero_not_estop():
    """服务停机：补零位一帧，不软急停（机器人保持站立等待人工处理）。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.3})
    wd._running = True                      # 模拟已启动的循环
    n = len(sink.sent)
    wd.stop()
    assert len(sink.sent) == n + 1          # 停机补零位
    assert gw.estop is False


def test_stop_when_idle_sends_nothing():
    wd, sink, clock, gw = _watchdog()
    wd._running = True
    n = len(sink.sent)
    wd.stop()
    assert len(sink.sent) == n
    assert gw.estop is False


def test_pause_on_user_release_does_not_estop():
    """正常松手只发零位，不触发软急停（事故一修正的延续）。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.3})
    assert wd.tick() == "axis"
    n_before = len(sink.sent)
    wd.pause("user_release")
    assert gw.estop is False
    assert len(sink.sent) == n_before + 1        # 只多发一帧零位
    clock.advance(60.0)                          # 长时间后也不升级
    assert wd.tick() is None
    assert gw.estop is False


def test_user_release_pause_then_refeed_resumes():
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.3})
    wd.pause("user_release")
    assert wd.tick() is None                     # 暂停中不再发送
    wd.feed({"x": 0.2})
    assert wd.tick() == "axis"                   # 重新按住即恢复
    assert gw.estop is False


def test_resume_requires_refeed():
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed({"x": 0.3})
    wd.pause("page_hidden")
    wd.resume()
    # resume 只是解除暂停；未重新 feed 前不得发送任何轴指令（保持停止状态）
    assert wd.tick() is None
    wd.feed({"x": 0.1})
    assert wd.tick() == "axis"


def test_status_has_no_escalation_fields():
    """v3：升级/兜底相关字段已整体切除（防止误读为"仍会自动软急停"）。"""
    wd, _sink, _clock, _gw = _watchdog()
    st = wd.status()
    for gone in ("tripped", "escalate_pending", "stale_estop_ms", "trip_count"):
        assert gone not in st
    assert st["stale"] is False


# ---------------------------------------------------------------- 定时移动（2026-10-16）
def test_feed_timed_runs_until_deadline_then_auto_stops():
    """定时到点 → 自动零位停发（正常结束路径），绝不软急停。"""
    from ingestion import asdu_parser

    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed_timed({"y": 0.4}, 1.0, channel="real")
    st = wd.status()
    assert st["timed_active"] is True
    assert st["timed_remaining"] == 1.0
    assert st["timed_total"] == 1.0
    assert st["channel"] == "real"

    assert wd.tick() == "axis_timed"
    decoded = asdu_parser.decode_frame(sink.sent[-1])
    assert decoded["command"] == 25                      # 走实时通道
    assert decoded["items"]["Y"] == 0.4

    clock.advance(0.5)
    assert wd.tick() == "axis_timed"                     # 未到点：继续发
    clock.advance(0.6)                                   # 越过 1.0s
    n = len(sink.sent)
    assert wd.tick() == "timed_done"
    assert len(sink.sent) == n + 1                       # 零位一帧
    decoded_zero = asdu_parser.decode_frame(sink.sent[-1])
    assert decoded_zero["command"] == 25                 # 零位跟随通道
    assert decoded_zero["items"]["Y"] == 0.0
    assert gw.estop is False                             # 绝不软急停
    assert wd.status()["timed_active"] is False
    assert wd.tick() is None                             # 到点后停发


def test_feed_timed_ignores_feed_staleness():
    """定时模式不依赖 feed：跑 5s（远超 250ms 停更阈值）也不走 stale 分支。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed_timed({"x": 0.2}, 5.0)
    for _ in range(3):
        clock.advance(1.0)
        assert wd.tick() == "axis_timed"
    assert wd.status()["stale"] is False
    assert gw.estop is False


def test_feed_timed_abort_via_pause_cancels_and_never_estop():
    """中止（pause）后：定时作废 + 零位停发；原 deadline 过了也不再发。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed_timed({"x": 0.3}, 10.0)
    assert wd.tick() == "axis_timed"
    wd.pause("timed_aborted")
    assert wd.status()["timed_active"] is False
    n = len(sink.sent)
    clock.advance(20.0)
    assert wd.tick() is None
    assert len(sink.sent) == n
    assert gw.estop is False


def test_feed_timed_restart_replaces_previous():
    """重复开始 = 以新值/新时长重启（旧 deadline 作废）。"""
    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed_timed({"x": 0.3}, 10.0)
    wd.tick()
    clock.advance(1.0)
    wd.feed_timed({"y": 0.2}, 2.0, channel="steer")
    st = wd.status()
    assert st["timed_total"] == 2.0
    assert st["timed_remaining"] == 2.0
    assert st["channel"] == "steer"


def test_manual_feed_overrides_timed_and_returns_to_steer():
    """人抢回控制权：手动 feed 作废定时，且通道回默认主通道。"""
    from ingestion import asdu_parser

    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed_timed({"x": 0.3}, 10.0, channel="real")
    wd.tick()
    wd.feed({"x": 0.1})
    st = wd.status()
    assert st["timed_active"] is False
    assert st["channel"] == "steer"
    assert wd.tick() == "axis"
    assert asdu_parser.decode_frame(sink.sent[-1])["command"] == 21


def test_feed_timed_channel_defaults_to_steer_and_bad_key_falls_back():
    from ingestion import asdu_parser

    wd, sink, clock, gw = _watchdog(state={"motion_state": 1, "control_usage_mode": 0})
    wd.feed_timed({"x": 0.2}, 3.0, channel="banana")     # 非法通道：回退主通道
    assert wd.status()["channel"] == "steer"
    wd.tick()
    assert asdu_parser.decode_frame(sink.sent[-1])["command"] == 21
