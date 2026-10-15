"""数据源抽象：把不同的「机器人状态来源」统一成同一种接口（PLAN §5.4 / §18）。

为什么需要它：本期走 UDP 心跳，将来可能加 ROS2 订阅（路径 1）。上层 StateStore
只见规范化后的帧，**不知道也不关心帧来自 UDP 还是 DDS topic** —— 这是"换数据来源
不动上层"的全部机制。

归一化帧（回调收到的 dict）：
    {"kind": "raw",    "data": bytes, "addr": (ip, port)}  # udp / mock：还需 asdu_parser 解析
    {"kind": "parsed", "frame": {...}}                     # ros2 / 回放：已归一化，直接入库

mock 也 emit raw 字节（用真实帧头编码），这样 M1 就能把「解析」这一段真实跑通，
而不是绕过去 —— 无真机也验证主干（PLAN §14.2）。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import abc
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from logging_setup import get_logger

logger = get_logger("ingestion.source")

FrameCallback = Callable[[Dict[str, Any]], None]


class DataSource(abc.ABC):
    """所有数据源的基类。"""

    mode: str = "abstract"

    def __init__(self) -> None:
        self._running = False
        self._cb: Optional[FrameCallback] = None
        self._lock = threading.RLock()

    @abc.abstractmethod
    def start(self) -> None:
        """启动数据源（创建 socket / 线程等）。"""

    @abc.abstractmethod
    def stop(self) -> None:
        """停止数据源并释放资源。"""

    def on_frame(self, cb: FrameCallback) -> None:
        """注册帧回调（PLAN §5.4 契约）。"""
        with self._lock:
            self._cb = cb

    def _emit(self, frame: Dict[str, Any]) -> None:
        """向回调投递一帧；回调异常不影响数据源继续运行。"""
        with self._lock:
            cb = self._cb
        if cb is None:
            return
        try:
            cb(frame)
        except Exception as exc:  # noqa: BLE001 - 消费侧异常不应拖死数据源
            logger.warning("帧回调抛出异常: %s", exc)

    def is_running(self) -> bool:
        return self._running

    # ---------------------------------------------- 心跳暂停（遥测让渡）
    #: 是否支持"暂停产出"（默认不支持；udp 心跳源支持）
    @property
    def pausable(self) -> bool:
        return False

    @property
    def paused(self) -> bool:
        return False

    def pause(self) -> bool:
        """暂停向机器人发心跳（= 主动放弃状态推送）。默认不支持，返回 False。"""
        return False

    def resume(self) -> bool:
        """恢复发心跳。默认不支持，返回 False。"""
        return False

    def stats(self) -> Dict[str, Any]:
        return {"mode": self.mode, "running": self._running}


class UdpHeartbeatSource(DataSource):
    """真机数据源：**同一 socket 收发**（PLAN §10.3.1 / Q3）。

    机器人只向"持续发送心跳的 IP:端口"推送状态，且推回同一个 socket ——
    所以心跳发送器与接收器必须共用这一个 socket。
    """

    mode = "udp"

    def __init__(self, target_ip: str, target_port: int, heartbeat_hz: float = 5.0,
                 buffer_size: int = 65535, timeout: float = 0.2) -> None:
        super().__init__()
        self.target_ip = target_ip
        self.target_port = target_port
        self.heartbeat_hz = heartbeat_hz
        self._buffer_size = buffer_size
        self._timeout = timeout
        self._sock = None
        self._rx_thread: Optional[threading.Thread] = None
        self._hb_thread: Optional[threading.Thread] = None
        self._paused = False
        self._paused_at: Optional[float] = None
        self.sent_heartbeats = 0
        self.received_packets = 0

    @property
    def pausable(self) -> bool:
        return True

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> bool:
        """停发心跳（不收 socket、不停线程）—— 机器人侧 basic_server 会在心跳
        超时后**清除本客户端**，不再向我们推送状态 = 主动放弃遥测。

        ⚠️ 语义边界：这只影响"机器人 → 我们"的状态推送；**指令链路是另一个
        独立 socket，照旧可达**。所以暂停遥测前必须先停控制（见
        ``MonitorService.set_heartbeat_paused``），否则就是蒙眼开车。
        """
        with self._lock:
            if not self._running or self._paused:
                return False
            self._paused = True
            self._paused_at = time.time()
        logger.warning("心跳已暂停：目标 %s:%s（将失去遥测，指令链路仍可达）",
                       self.target_ip, self.target_port)
        return True

    def resume(self) -> bool:
        """恢复发心跳（重新注册为 basic_server 的推送客户端）。"""
        with self._lock:
            if not self._running or not self._paused:
                return False
            self._paused = False
            paused_for = None if self._paused_at is None else round(
                time.time() - self._paused_at, 1)
            self._paused_at = None
        logger.warning("心跳已恢复（暂停了 %ss），重新获得状态推送", paused_for)
        return True

    def start(self) -> None:
        import socket

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(self._timeout)
        # 不 bind：由内核分配端口，机器人推回该端口（同一 socket）
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, name="m20-udp-rx", daemon=True)
        self._hb_thread = threading.Thread(target=self._hb_loop, name="m20-udp-hb", daemon=True)
        self._rx_thread.start()
        self._hb_thread.start()
        logger.info("UDP 心跳数据源已启动: 目标 %s:%s", self.target_ip, self.target_port)

    def _rx_loop(self) -> None:
        while self._running and self._sock is not None:
            try:
                data, addr = self._sock.recvfrom(self._buffer_size)
            except OSError:
                # timeout 属正常（让线程有机会检查退出标志）
                continue
            self.received_packets += 1
            self._emit({"kind": "raw", "data": data, "addr": addr})
        logger.debug("UDP 接收线程退出")

    def _hb_loop(self) -> None:
        from ingestion import asdu_parser

        interval = 1.0 / max(1.0, self.heartbeat_hz)
        next_at = time.monotonic()
        while self._running:
            # 暂停期间**不发**（但保持 socket 与线程：恢复是瞬时的，不需要重连）
            if not self._paused:
                try:
                    payload = asdu_parser.encode_frame(100, 100, {})
                    if self._sock is not None:
                        self._sock.sendto(payload, (self.target_ip, self.target_port))
                        self.sent_heartbeats += 1
                except OSError as exc:
                    logger.warning("心跳发送失败（将重试）: %s", exc)
            next_at += interval
            delay = next_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        logger.debug("心跳线程退出")

    def stop(self) -> None:
        self._running = False
        for t in (self._rx_thread, self._hb_thread):
            if t and t.is_alive():
                t.join(timeout=2.0)
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        logger.info("UDP 心跳数据源已停止")

    def stats(self) -> Dict[str, Any]:
        base = super().stats()
        base.update({
            "target": "%s:%s" % (self.target_ip, self.target_port),
            "sent_heartbeats": self.sent_heartbeats,
            "received_packets": self.received_packets,
            "pausable": self.pausable,
            "paused": self._paused,
            "paused_seconds": (None if self._paused_at is None
                               else round(time.time() - self._paused_at, 1)),
        })
        return base


def build_data_source(mode: str, settings: Any = None) -> DataSource:
    """按模式构造数据源（mock / udp；ros2 预留，PLAN §18 路径 1）。"""
    from ingestion.mock_source import MockSource

    mode = (mode or "mock").lower()
    if mode == "mock":
        return MockSource(replay_file=getattr(settings, "replay_file", "") if settings else "")
    if mode == "udp":
        if settings is None:
            raise ValueError("udp 数据源需要传入 settings（robot.target_ip/port）")
        return UdpHeartbeatSource(
            target_ip=settings.robot.target_ip,
            target_port=settings.robot.target_port,
            heartbeat_hz=settings.robot.heartbeat_hz,
        )
    if mode == "ros2":
        raise NotImplementedError("Ros2TopicSource 为 PLAN §18 路径 1 预留，本期不实现")
    raise ValueError("不支持的数据源: %s" % mode)
