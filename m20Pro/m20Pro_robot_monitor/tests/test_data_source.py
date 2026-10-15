"""UDP 心跳数据源：发 / 停 / 恢复 + 暂停语义（2026-10-16 加）。

用**真实 localhost UDP socket** 验证，不 mock 收发——"暂停期间真的不再发包"
是这个功能的核心承诺，值得用真 socket 背书。

背景：心跳（类型100/命令100）只决定"机器人往谁推送状态"；停发后 basic_server
会心跳超时并清除本客户端。控制台据此提供"主动让渡遥测"的能力
（``POST /api/v1/link/heartbeat``）。
"""

import socket
import time

from ingestion.data_source import DataSource, UdpHeartbeatSource
from ingestion.mock_source import MockSource


def _free_port() -> int:
    """抓一个空闲端口（用完即关，端口号可复用）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _drain(sock: socket.socket, seconds: float) -> int:
    """在 seconds 窗口内收包计数；窗口内无包即提前返回。"""
    n = 0
    deadline = time.monotonic() + seconds
    while True:
        remain = deadline - time.monotonic()
        if remain <= 0:
            return n
        sock.settimeout(remain)
        try:
            sock.recvfrom(4096)
            n += 1
        except socket.timeout:
            return n


def test_heartbeat_sends_pauses_and_resumes():
    port = _free_port()
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", port))
    try:
        src = UdpHeartbeatSource("127.0.0.1", port, heartbeat_hz=20.0)
        src.start()
        try:
            assert _drain(rx, 0.8) > 0, "启动后应持续发心跳"
            assert src.stats()["paused"] is False

            # 暂停：真的不再发（清掉在途后开一个静默窗）
            assert src.pause() is True
            assert src.paused is True
            _drain(rx, 0.3)
            assert _drain(rx, 0.6) == 0, "暂停期间仍在发心跳"
            assert src.stats()["sent_heartbeats"] > 0

            # 重复 pause 是幂等 no-op（不报错、不改状态）
            assert src.pause() is False

            # 恢复：重新开始发
            assert src.resume() is True
            assert _drain(rx, 0.8) > 0, "恢复后应重新发心跳"
            assert src.paused is False
            assert src.resume() is False      # 未暂停时恢复 = no-op
        finally:
            src.stop()
            assert src.is_running() is False
    finally:
        rx.close()


def test_paused_source_keeps_socket_and_thread():
    """暂停不拆 socket / 不停线程 —— 恢复是瞬时的，不需要重新建链。"""
    port = _free_port()
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", port))
    try:
        src = UdpHeartbeatSource("127.0.0.1", port, heartbeat_hz=20.0)
        src.start()
        try:
            src.pause()
            assert src.is_running() is True
            assert src._hb_thread is not None and src._hb_thread.is_alive()
            assert src._sock is not None
        finally:
            src.stop()
    finally:
        rx.close()


def test_pause_after_stop_is_rejected():
    """已停止的数据源不允许暂停（停了就是停了，没有"半死不活"态）。"""
    port = _free_port()
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", port))
    try:
        src = UdpHeartbeatSource("127.0.0.1", port, heartbeat_hz=20.0)
        src.start()
        src.stop()
        assert src.pause() is False
        assert src.paused is False
    finally:
        rx.close()


def test_base_and_mock_source_do_not_support_pause():
    """基类 / mock 源默认不支持暂停 —— API 层据此返回 NOT_SUPPORTED，
    而不是静默"成功"（假成功比失败更危险：用户以为让渡了遥测）。"""

    class _Bare(DataSource):
        """只实现抽象方法的最小具体子类（DataSource 本身是 ABC）。"""

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    bare = _Bare()
    assert bare.pausable is False
    assert bare.paused is False
    assert bare.pause() is False
    assert bare.resume() is False
    mock = MockSource()
    assert mock.pausable is False
    assert mock.pause() is False
    assert mock.paused is False
