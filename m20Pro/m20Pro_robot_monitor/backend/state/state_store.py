"""唯一权威状态仓库（ADR-006）+ 有界原始报文环形缓冲（ADR-007）。

要点：
1. **ingestion 独占写**，读侧只读快照（StateStore.update 是唯一写入口）；
2. per-topic 独立时间戳与 stale 判定（500ms 可配）；
3. **停更只标脏，不删旧值**——绝不把旧数据当新数据展示（PLAN §6.2）；
4. 原始报文缓冲有界（deque maxlen），长时间运行内存不涨。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from logging_setup import get_logger
from state.models import RawPacketItem, RobotSnapshot, TopicSnapshot

logger = get_logger("state.store")


def _hex_preview(data: bytes, limit: int) -> str:
    return data[:limit].hex()


class StateStore:
    """线程安全的状态仓库。"""

    def __init__(self, stale_threshold: float = 0.5, raw_history_size: int = 1000,
                 raw_preview_bytes: int = 64, link_timeout: float = 3.0,
                 push_hz: int = 10, topic_hz: Optional[Dict[str, float]] = None) -> None:
        self._stale_threshold = float(stale_threshold)
        # per-topic 阈值：不能一刀切 500ms —— 1Hz 的导航/0.2Hz 的休眠会被误判停更
        # （实测踩过：nav 每 1s 一帧，500ms 阈值下永远显示 stale）。
        # 规则：阈值 = max(默认阈值, 2.5 个推送周期)，容忍偶发丢包。
        self._topic_stale: Dict[str, float] = {}
        for name, hz in (topic_hz or {}).items():
            if hz and hz > 0:
                self._topic_stale[name] = max(self._stale_threshold, 2.5 / float(hz))
        self._raw_history_size = int(raw_history_size)
        self._raw_preview_bytes = int(raw_preview_bytes)
        self._link_timeout = float(link_timeout)
        self._push_hz = int(push_hz)

        self._lock = threading.RLock()
        self._topics: Dict[str, Dict[str, Any]] = {}   # topic -> {"frame":..., "monotonic":..., "wall":...}
        self._raw: Deque[Dict[str, Any]] = deque(maxlen=self._raw_history_size)
        self._started_at = time.time()

        self._received = 0     # 收到的帧数（含解析失败）
        self._parsed = 0       # 解析成功的帧数
        self._errors = 0       # 解析失败（死信）
        self._dropped = 0      # 缓冲丢弃
        self._ws_clients = 0
        # 服务自状态降级（如心跳被主动暂停 → 遥测失效）。与"链路故障"是两回事：
        # 前者是操作者有意为之（提示语义相反，不能都显示成红色告警）。
        self._degraded = False
        self._degraded_reason: Optional[str] = None
        self._last_any_monotonic: Optional[float] = None
        self._data_source = "mock"

    # ------------------------------------------------------------------ 写
    def update(self, frame: Dict[str, Any], raw: Optional[bytes] = None) -> None:
        """写入一帧归一化数据（PLAN §5.4：仅 ingestion 可写）。"""
        if not isinstance(frame, dict) or "topic" not in frame:
            logger.warning("StateStore.update 收到非法帧: %r", type(frame))
            return
        topic = str(frame["topic"])
        mono = float(frame.get("recv_monotonic") or time.monotonic())
        wall = float(frame.get("recv_wall") or time.time())

        with self._lock:
            self._received += 1
            self._parsed += 1
            self._topics[topic] = {"frame": frame, "monotonic": mono, "wall": wall}
            if self._last_any_monotonic is None or mono > self._last_any_monotonic:
                self._last_any_monotonic = mono
            if raw is not None:
                self._append_raw_locked(frame, raw, wall)

    def record_error(self, raw: Optional[bytes] = None, reason: str = "") -> None:
        """记录一帧解析失败（死信计数，不抛到 ingestion 之外）。"""
        with self._lock:
            self._received += 1
            self._errors += 1
            if raw is not None and self._raw_history_size:
                if len(self._raw) >= self._raw_history_size:
                    self._dropped += 1
                self._raw.append({
                    "key": "parse_error", "topic": "unknown", "length": len(raw),
                    "received_at": time.time(), "source_ip": None, "source_port": None,
                    "hex_preview": _hex_preview(raw, self._raw_preview_bytes),
                })
        logger.warning("解析失败已计入死信: %s", reason, extra={"event": "parse_error"})

    def set_ws_clients(self, count: int) -> None:
        with self._lock:
            self._ws_clients = int(count)

    def set_data_source(self, name: str) -> None:
        with self._lock:
            self._data_source = str(name)

    def set_link_degraded(self, degraded: bool, reason: Optional[str] = None) -> None:
        """标记服务自状态降级（当前用途：心跳被主动暂停 → 遥测失效）。

        为什么要单独一个标志而不是复用 ``connected``：两者提示语义**相反** ——
        ``connected=False`` 是"链路故障，快检查"，而这里是"操作者主动放弃了遥测，
        车可能还在动，别被'没数据'误导成'车没事'"。前端据此分色展示。
        """
        with self._lock:
            self._degraded = bool(degraded)
            self._degraded_reason = str(reason) if (degraded and reason) else None

    def clear_raw(self) -> None:
        with self._lock:
            self._raw.clear()

    def _append_raw_locked(self, frame: Dict[str, Any], raw: bytes, wall: float) -> None:
        if len(self._raw) >= self._raw_history_size:
            self._dropped += 1  # deque 自动淘汰最旧的一条
        source = frame.get("source") or {}
        self._raw.append({
            "key": frame.get("key", ""), "topic": frame.get("topic", ""),
            "length": len(raw), "received_at": wall,
            "source_ip": source.get("ip"), "source_port": source.get("port"),
            "hex_preview": _hex_preview(raw, self._raw_preview_bytes),
        })

    # ------------------------------------------------------------------ 读
    def threshold_for(self, topic: str) -> float:
        """取该 topic 的停更阈值（秒）。"""
        return self._topic_stale.get(topic, self._stale_threshold)

    def is_stale(self, topic: str, now: Optional[float] = None) -> bool:
        """某 topic 是否已停更（monotonic 计时，不受 196 时钟错误影响）。"""
        now = time.monotonic() if now is None else now
        with self._lock:
            entry = self._topics.get(topic)
            if entry is None:
                return True
            return (now - float(entry["monotonic"])) > self.threshold_for(topic)

    def connected(self, now: Optional[float] = None) -> bool:
        """链路在线：link_timeout 内收到过任意帧。"""
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._last_any_monotonic is None:
                return False
            return (now - self._last_any_monotonic) <= self._link_timeout

    def snapshot(self, now: Optional[float] = None) -> Dict[str, Any]:
        """构造一次完整快照 dict（可直接 JSON 序列化）。"""
        now_mono = time.monotonic() if now is None else now
        with self._lock:
            topics: Dict[str, Dict[str, Any]] = {}
            for name, entry in self._topics.items():
                age_ms = max(0.0, (now_mono - float(entry["monotonic"])) * 1000.0)
                stale = age_ms > (self.threshold_for(name) * 1000.0)
                frame = entry["frame"]
                topics[name] = {
                    "ts": float(entry["wall"]),
                    "age_ms": round(age_ms, 1),
                    "stale": bool(stale),
                    "data": frame.get("fields", {}) or {},
                }
            last_any = self._last_any_monotonic
            since_ms = None if last_any is None else round(
                max(0.0, (now_mono - last_any) * 1000.0), 1)
            connected = self.connected(now_mono)
            service = {
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "push_hz": self._push_hz,
                "data_source": self._data_source,
                "ws_clients": self._ws_clients,
                "packets_received": self._received,
                "packets_parsed": self._parsed,
                "packets_error": self._errors,
                "packets_dropped": self._dropped,
                "degraded": self._degraded,
                "degraded_reason": self._degraded_reason,
            }
        return {
            "type": "snapshot",
            "server_time": time.time(),
            "connected": connected,
            "since_last_update_ms": since_ms,
            "topics": topics,
            "service": service,
        }

    def build_snapshot_model(self, control: Optional[Dict[str, Any]] = None,
                             now: Optional[float] = None) -> RobotSnapshot:
        """返回校验后的 pydantic 快照（契约出口）。"""
        data = self.snapshot(now)
        data["control"] = control or {}
        data.setdefault("schema_version", "1.0")
        return RobotSnapshot.model_validate(data)

    def get_raw_packets(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._raw)
        items.reverse()
        if limit and limit > 0:
            items = items[:limit]
        return items

    def get_raw_items(self, limit: int = 30) -> List[RawPacketItem]:
        return [RawPacketItem.model_validate(i) for i in self.get_raw_packets(limit)]

    def counters(self) -> Dict[str, Any]:
        with self._lock:
            received = self._received
            errors = self._errors
        return {
            "received": received,
            "parsed": self._parsed,
            "errors": errors,
            "dropped": self._dropped,
            "error_rate": (errors / received) if received else 0.0,
            "uptime": round(time.time() - self._started_at, 3),
        }

    def fresh_topics(self, now: Optional[float] = None) -> List[str]:
        now_mono = time.monotonic() if now is None else now
        with self._lock:
            names = list(self._topics.keys())
        return [n for n in names if not self.is_stale(n, now_mono)]

    def ready(self, error_rate_threshold: float = 0.2) -> Dict[str, Any]:
        """/ready 判定：链路在线 + 解析失败率未超阈。"""
        counters = self.counters()
        rate = counters["error_rate"]
        connected = self.connected()
        fresh = self.fresh_topics()
        with self._lock:
            names = list(self._topics.keys())
        stale = [n for n in names if n not in fresh]
        degraded = (not connected) or (rate > error_rate_threshold)
        reason = None
        if not connected:
            reason = "链路断开：超过 %.1fs 未收到任何状态推送" % self._link_timeout
        elif rate > error_rate_threshold:
            reason = "解析失败率 %.0f%% 超过阈值 %.0f%%" % (rate * 100, error_rate_threshold * 100)
        return {
            "ready": True,            # 进程存活即 ready；降级用 degraded 表达
            "degraded": degraded,
            "reason": reason,
            "connected": connected,
            "fresh_topics": fresh,
            "stale_topics": stale,
            "error_rate": round(rate, 4),
        }
