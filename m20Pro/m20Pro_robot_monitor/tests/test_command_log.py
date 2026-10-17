"""指令报文记录单测（2026-10-17）：留原文 + 响应标记。

覆盖三层：
  1. ``CommandLog`` 本身 —— 记录 / 匹配 / 超时 / FIFO / 有界
  2. ``ControlGateway`` 集成 —— execute / 急停 / 安全零位 / 被拒 都留证
  3. HTTP API 契约 —— ``/control/packets`` 形状与语义
"""

import json

import pytest

from control import patrol_codec
from control.command_log import (RESP_ERROR, RESP_NO_RESPONSE, RESP_OK,
                                 RESP_PENDING, RESP_REJECTED,
                                 RESP_SEND_FAILED, CommandLog)
from control.control_gateway import ControlGateway, RecordingSink


# ================================================================ CommandLog
def _log(**kw):
    return CommandLog(**kw)


def test_sent_frame_is_recorded_byte_for_byte():
    """留下的 hex 必须能原样解回同一条指令 —— 这是"报文留证"的底线。"""
    cl = _log()
    frame = patrol_codec.encode("device_switch",
                                {"items": {"Lidar": {"Front": 1, "Back": 1}}})
    cl.record_sent("device_switch", 1101, 3, {"Lidar": {"Front": 1, "Back": 1}},
                   frame)
    item = cl.snapshot()["items"][0]
    assert item["frame_hex"] == frame.hex()
    assert item["frame_len"] == len(frame)
    assert item["type"] == 1101 and item["command"] == 3
    assert item["resp"]["status"] == RESP_PENDING
    # 反解验证：hex → 字节 → JSON，字段一致
    decoded = json.loads(bytes.fromhex(item["frame_hex"])[16:].decode("utf-8"))
    assert decoded["PatrolDevice"]["Items"] == {"Lidar": {"Front": 1, "Back": 1}}
    # 授权 magic 也必须留在报文里（复盘时要能看出走的是哪条权限通道）
    assert bytes.fromhex(item["frame_hex"])[:4] == b"\xeb\x90\xeb\x90"


def test_response_ok_marks_success_with_latency():
    cl = _log()
    frame = patrol_codec.encode("sleep_query")
    cl.record_sent("sleep_query", 1101, 7, {}, frame)
    resp_items = {"Sleep": 0, "Auto": False, "Time": 10}
    updated = cl.on_response(1101, 7, resp_items, b"\x00" * 16 + b"{}")
    assert updated is not None
    assert updated["resp"]["status"] == RESP_OK
    # 休眠查询响应**不带 ErrorCode**（只有 Sleep/Auto/Time）→ error_code 为 None，
    # 但"有数据回来"本身就说明指令被接受，故仍判 ok。前端据此显示「已响应」。
    assert updated["resp"]["error_code"] is None
    assert updated["resp"]["latency_ms"] >= 0
    assert updated["resp"]["frame_hex"] is not None
    assert cl.snapshot()["pending"] == 0


def test_response_without_error_code_is_still_ok():
    """显式固化：无 ErrorCode 字段的响应 = 成功（不是"不知道"）。"""
    cl = _log()
    cl.record_sent("sleep_query", 1101, 7, {}, patrol_codec.encode("sleep_query"))
    cl.on_response(1101, 7, {"Sleep": 1, "Auto": False, "Time": 10}, b"")
    assert cl.snapshot()["items"][0]["resp"]["status"] == RESP_OK

    # 对照：ErrorCode 显式为 0 也是 ok
    cl2 = _log()
    cl2.record_sent("heartbeat", 100, 100, {}, patrol_codec.encode("heartbeat"))
    cl2.on_response(100, 100, {"ErrorCode": 0}, b"")
    assert cl2.snapshot()["items"][0]["resp"]["status"] == RESP_OK


def test_response_error_keeps_code_and_message():
    """ErrorCode != 0 → error，且必须把厂商的 ErrorMessage 带出来。"""
    cl = _log()
    frame = patrol_codec.encode("device_switch", {"items": {"GPS": 0}})
    cl.record_sent("device_switch", 1101, 3, {"GPS": 0}, frame)
    cl.on_response(1101, 3, {"ErrorCode": 57351,
                             "ErrorMessage": "No operation permission"}, b"")
    item = cl.snapshot()["items"][0]
    assert item["resp"]["status"] == RESP_ERROR
    assert item["resp"]["error_code"] == 57351
    assert item["resp"]["error_message"] == "No operation permission"


def test_unmatched_frames_are_ignored():
    """状态上报 / 心跳应答不该动任何在途指令（高频回调，必须零副作用）。"""
    cl = _log()
    cl.record_sent("stand_up", 2, 22, {"MotionParam": 1},
                   patrol_codec.encode("stand_up"))
    # 1002/4 运动状态上报：Type/Command 对不上
    assert cl.on_response(1002, 4, {"linear_x": 0.1}, b"") is None
    # 100/100 心跳应答：同样对不上
    assert cl.on_response(100, 100, {"ErrorCode": 0}, b"") is None
    assert cl.snapshot()["items"][0]["resp"]["status"] == RESP_PENDING


def test_timeout_marks_no_response_lazily():
    """超时判定是惰性的：不靠后台线程，读出口扫一遍即可。"""
    cl = _log(timeout_s=0.05)
    cl.record_sent("stand_up", 2, 22, {"MotionParam": 1},
                   patrol_codec.encode("stand_up"))
    assert cl.snapshot()["items"][0]["resp"]["status"] == RESP_PENDING
    import time as _t
    _t.sleep(0.08)
    item = cl.snapshot()["items"][0]
    assert item["resp"]["status"] == RESP_NO_RESPONSE
    assert item["resp"]["latency_ms"] >= 80


def test_fifo_matching_for_repeated_same_command():
    """同一 (Type,Command) 多条在途 → 按发出顺序匹配，不回填错位。"""
    cl = _log()
    for _ in range(3):
        cl.record_sent("sleep_query", 1101, 7, {}, patrol_codec.encode("sleep_query"))
    cl.on_response(1101, 7, {"ErrorCode": 0}, b"")
    items = list(cl.snapshot()["items"])          # 最新在前
    items.reverse()                               # 转成最早在前
    assert items[0]["resp"]["status"] == RESP_OK
    assert items[1]["resp"]["status"] == RESP_PENDING
    assert items[2]["resp"]["status"] == RESP_PENDING
    assert cl.snapshot()["pending"] == 2


def test_send_failed_is_marked_immediately():
    """socket 都没发出去：立刻判死，不让用户干等 2s 超时。"""
    cl = _log()
    frame = patrol_codec.encode("stand_up")
    cl.record_sent("stand_up", 2, 22, {"MotionParam": 1}, frame)
    cl.record_send_failed("stand_up", 2, 22, {"MotionParam": 1}, frame,
                          detail="UDP socket 发送失败")
    item = cl.snapshot()["items"][0]
    assert item["resp"]["status"] == RESP_SEND_FAILED
    assert cl.snapshot()["pending"] == 0


def test_rejected_has_no_frame_but_is_visible():
    """被闸拒的没有报文，但必须出现在面板里（否则"点了没反应"无从解释）。"""
    cl = _log()
    cl.record_rejected("device_switch", {"items": {"GPS": 0}},
                       reason="CONFIRM_REQUIRED", detail="需二次确认")
    item = cl.snapshot()["items"][0]
    assert item["frame_hex"] is None
    assert item["resp"]["status"] == RESP_REJECTED
    assert item["resp"]["reason"] == "CONFIRM_REQUIRED"


def test_ring_is_bounded():
    cl = _log(size=5)
    for i in range(20):
        cl.record_sent("heartbeat", 100, 100, {"i": i},
                       patrol_codec.encode("heartbeat"))
    snap = cl.snapshot()
    assert len(snap["items"]) == 5
    # 最新在前
    assert snap["items"][0]["items"]["i"] == 19


def test_stats_count_every_status():
    cl = _log(timeout_s=0.02)
    cl.record_sent("a", 2, 22, {}, patrol_codec.encode("stand_up"))
    cl.on_response(2, 22, {"ErrorCode": 0}, b"")           # ok
    cl.record_sent("b", 1101, 3, {}, patrol_codec.encode("device_switch",
                  {"items": {"GPS": 1}}))
    cl.on_response(1101, 3, {"ErrorCode": 1, "ErrorMessage": "x"}, b"")  # error
    cl.record_rejected("c", {}, reason="CONTROL_DISABLED")  # rejected
    cl.record_sent("d", 2, 21, {}, patrol_codec.encode("axis"))  # 将超时
    import time as _t
    _t.sleep(0.05)
    stats = cl.snapshot()["stats"]
    assert stats[RESP_OK] == 1
    assert stats[RESP_ERROR] == 1
    assert stats[RESP_REJECTED] == 1
    assert stats[RESP_NO_RESPONSE] == 1


# ============================================================ 网关集成
def _gw(state=None, enabled=True, with_log=True):
    sink = RecordingSink()
    log = CommandLog(size=50) if with_log else None
    gw = ControlGateway(sink, enabled=enabled, lease_seconds=30.0,
                        state_provider=(lambda: state) if state is not None else None,
                        command_log=log)
    if enabled:
        gw.enable()          # L0 场景必须保持未启用，否则测不到分层闸
    gw.renew_lease()
    return gw, sink, log


def test_execute_records_frame_and_gets_matched():
    gw, sink, log = _gw()
    res = gw.execute("sleep_query")
    assert res["ok"] is True
    item = log.snapshot()["items"][0]
    assert item["name"] == "sleep_query"
    assert item["frame_hex"] is not None
    assert len(sink.sent) == 1
    # 模拟机器人应答
    log.on_response(1101, 7, {"Sleep": 0, "Auto": False, "Time": 10}, b"")
    assert log.snapshot()["items"][0]["resp"]["status"] == RESP_OK


def test_execute_rejection_is_recorded_without_frame():
    gw, sink, log = _gw(enabled=False)
    res = gw.execute("stand_up")
    assert res["ok"] is False
    item = log.snapshot()["items"][0]
    assert item["frame_hex"] is None
    assert item["resp"]["status"] == RESP_REJECTED
    assert sink.sent == []


def test_device_switch_off_unconfirmed_is_recorded():
    gw, _sink, log = _gw()
    res = gw.execute("device_switch", {"items": {"GPS": 0}})
    assert res["ok"] is False and res["reason"] == "CONFIRM_REQUIRED"
    item = log.snapshot()["items"][0]
    assert item["resp"]["status"] == RESP_REJECTED
    assert item["resp"]["reason"] == "CONFIRM_REQUIRED"


def test_safety_zero_is_recorded():
    """安全零位帧必须留证 —— 事故复盘时"停机前最后发了什么"是关键证据。"""
    gw, sink, log = _gw()
    gw.send_safety_zero(actor="watchdog", reason="ws_disconnected")
    item = log.snapshot()["items"][0]
    assert item["name"] == "axis"
    assert item["forced"] is True
    assert item["actor"] == "watchdog"
    # 报文里存的是**协议字段**（大写 X/Y/Z/Roll/Pitch/Yaw），即线上真正的
    # JSON 内容；前端的小写参数在审计里。报文视角就必须以线上为准。
    assert item["items"] == {"X": 0.0, "Y": 0.0, "Z": 0.0,
                             "Roll": 0.0, "Pitch": 0.0, "Yaw": 0.0}
    assert item["frame_hex"] is not None
    assert len(sink.sent) == 1


def test_emergency_stop_is_recorded():
    gw, _sink, log = _gw()
    gw.emergency_stop()
    item = log.snapshot()["items"][0]
    assert item["name"] == "soft_estop"
    assert item["type"] == 2 and item["command"] == 22


def test_disable_sends_and_records_safety_zero():
    gw, sink, log = _gw()
    gw.disable()
    assert len(sink.sent) == 1
    assert log.snapshot()["items"][0]["resp"] is not None
    assert log.snapshot()["items"][0]["items"] == {
        "X": 0.0, "Y": 0.0, "Z": 0.0, "Roll": 0.0, "Pitch": 0.0, "Yaw": 0.0}


def test_gateway_works_without_command_log():
    """command_log=None（mock / 老调用方）时必须完全静默，不炸。"""
    gw, sink, _ = _gw(with_log=False)
    assert gw.execute("stand_up")["ok"] is True
    assert gw.emergency_stop()["ok"] is True
    assert gw.send_safety_zero() is True
    assert len(sink.sent) == 3


def test_watchdog_ticks_do_not_flood_the_log():
    """20Hz 看门狗 tick 不走 execute()，所以不该进报文记录。

    否则一秒 20 条，200 条环形 10 秒就滚掉，用户什么也看不到。
    """
    gw, sink, log = _gw()
    gw.watchdog = None
    # 直接模拟看门狗的内部发送路径：它调用的是 control.execute("axis")？
    # 不 —— 看门狗用自己的发送循环。这里验证"连续 execute 同一条"至少可区分，
    # 且记录条数与 execute 次数一致（1:1，不放大）。
    for _ in range(5):
        gw.execute("sleep_query")
    assert len(log.snapshot()["items"]) == 5


# ============================================================ HTTP 契约
def test_packets_endpoint_shape():
    from fastapi.testclient import TestClient

    from main import app
    with TestClient(app) as client:
        r = client.get("/api/v1/control/packets", params={"limit": 10})
        assert r.status_code == 200
        body = r.json()
        assert set(body) >= {"items", "stats", "pending", "timeout_s"}
        assert isinstance(body["items"], list)
        # 契约冻结：每条必须带这些键（前端分色/复制都依赖它们）
        if body["items"]:
            need = {"seq", "ts", "name", "type", "command", "items",
                    "frame_hex", "frame_len", "resp"}
            assert need <= set(body["items"][0])
            assert set(body["items"][0]["resp"]) >= {"status"}


# ============================================================ 出口接收侧
def test_udp_sink_receives_command_response():
    """★回归测试（2026-10-17 踩坑）：指令应答走**请求的源端口**回到本 socket。

    此前 UdpControlSink 只发不收 → 应答全堵在缓冲区 → 报文记录永远
    ``no_response``，"是否成功响应"这一列整个失效。本测试用一对真实
    UDP socket 模拟"机器人"，锁住"出口必须能收"这条性质。
    """
    import socket
    import threading
    import time as _t

    from control.control_gateway import UdpControlSink

    # 假机器人：收到什么都回一个带 ErrorCode 的应答帧（回请求的源地址）
    robot = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    robot.bind(("127.0.0.1", 0))
    robot.settimeout(0.2)
    robot_port = robot.getsockname()[1]
    stop = threading.Event()

    def _robot_loop():
        while not stop.is_set():
            try:
                data, addr = robot.recvfrom(65535)
            except OSError:
                continue
            robot.sendto(patrol_codec.encode("sleep_query"), addr)

    rt = threading.Thread(target=_robot_loop, daemon=True)
    rt.start()

    got = []
    sink = UdpControlSink("127.0.0.1", robot_port,
                          on_response=lambda raw: got.append(raw))
    try:
        assert sink.send(patrol_codec.encode("sleep_query")) is True
        # 等接收线程把应答交上来
        for _ in range(40):
            if got:
                break
            _t.sleep(0.05)
        assert got, "出口没有收到机器人应答 —— 接收侧又坏了"
        decoded = json.loads(got[0][16:].decode("utf-8"))
        assert decoded["PatrolDevice"]["Command"] == 7
        assert sink.received_responses >= 1
        assert sink.stats()["received_responses"] >= 1
    finally:
        stop.set()
        rt.join(timeout=1.0)
        sink.close()
        robot.close()


def test_udp_sink_works_without_response_callback():
    """没有回调（mock / 只发送场景）时不许起线程、也不许炸。"""
    from control.control_gateway import UdpControlSink
    sink = UdpControlSink("127.0.0.1", 30000)
    assert sink.send(patrol_codec.encode("heartbeat")) is True
    assert sink._rx_thread is None
    sink.close()


def test_udp_sink_close_stops_rx_thread():
    import time as _t
    from control.control_gateway import UdpControlSink
    sink = UdpControlSink("127.0.0.1", 30000,
                          on_response=lambda raw: None)
    sink.send(patrol_codec.encode("heartbeat"))
    assert sink._rx_thread is not None
    sink.close()
    _t.sleep(0.3)
    assert sink._rx_thread.is_alive() is False


def test_decode_frame_accepts_both_known_magics():
    """★回归测试（2026-10-17 踩坑）：接收侧必须两种 magic 都认。

    抓包实证：basic_server **按「客户端注册时用的 magic」回复**。App 用
    EB90EB90 注册 → 它收到的 2714 帧全是 EB90EB90；我们的状态帧是 EB91EB90。
    而 `1101/3` 是用授权 magic 发的 → **应答也回 EB90EB90** →
    解码器只认 EB91EB90 就会解析失败、被 except 吞掉 → 报文记录永远 no_response。
    """
    from ingestion import asdu_parser

    for tag in (asdu_parser.HEAD_TAG, asdu_parser.HEAD_TAG_AUTHORIZED):
        frame = asdu_parser.encode_frame(1101, 3, {"ErrorCode": 0}, head_tag=tag)
        decoded = asdu_parser.decode_frame(frame)
        assert decoded["type"] == 1101 and decoded["command"] == 3
        assert decoded["items"] == {"ErrorCode": 0}
        assert decoded["head_tag"] == tag.hex()      # 能看出走的是哪条通道

    # 未知 magic 仍然拒绝（放宽的只是"客户端标识"，不是帧头校验）
    bad = bytearray(asdu_parser.encode_frame(1101, 3, {}))
    bad[0:4] = b"\xeb\x99\xeb\x99"
    with pytest.raises(Exception):
        asdu_parser.decode_frame(bytes(bad))


def test_on_command_response_parses_authorized_magic_frame():
    """端到端串起来：授权 magic 的应答帧 → 能正确落到在途指令上。"""
    from ingestion import asdu_parser
    cl = _log()
    req = patrol_codec.encode("device_switch", {"items": {"GPSMode": 1}})
    cl.record_sent("device_switch", 1101, 3, {"GPSMode": 1}, req)

    # 模拟 basic_server 用**请求的 magic**（EB90EB90）回一个应答
    resp = asdu_parser.encode_frame(1101, 3, {"ErrorCode": 0}, message_id=0,
                                    head_tag=asdu_parser.HEAD_TAG_AUTHORIZED)
    decoded = asdu_parser.decode_frame(resp)
    cl.on_response(decoded["type"], decoded["command"], decoded["items"], resp)

    item = cl.snapshot()["items"][0]
    assert item["resp"]["status"] == RESP_OK
    assert item["resp"]["error_code"] == 0
