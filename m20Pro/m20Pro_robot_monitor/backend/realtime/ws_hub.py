"""WebSocket 连接管理与 10Hz 快照 fan-out（ADR-005 / PLAN §5.5）。

- 服务端以 ``push_hz`` 主动广播完整快照（不逐个 topic 推，ADR-006 已论证带宽可忽略）；
- 客户端发任意文本即触发一次即时快照（便于前端首帧与重连）；
- 断连自动清理；控制租约订阅 WS 在线状态（断开即失效）。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from logging_setup import get_logger

logger = get_logger("realtime.ws")


class WsHub:
    """WS 连接池 + 广播循环。"""

    def __init__(self, snapshot_provider: Callable[[], Dict[str, Any]],
                 push_hz: int = 10,
                 on_disconnect: Optional[Callable[[], None]] = None) -> None:
        self._provider = snapshot_provider
        self.push_hz = max(1, int(push_hz))
        self._on_disconnect = on_disconnect
        self._clients: Set[WebSocket] = set()
        self._task: Optional[asyncio.Task] = None

    @property
    def count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("WS 客户端接入，当前 %d", self.count)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.discard(ws)
            logger.info("WS 客户端断开，当前 %d", self.count)
        if self.count == 0 and self._on_disconnect is not None:
            # 最后一个客户端断开 → 通知控制层（看门狗兜底/租约失效）
            self._on_disconnect()

    async def _send(self, ws: WebSocket, message: str) -> bool:
        try:
            await ws.send_text(message)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("WS 发送失败: %s", exc)
            return False

    def render(self) -> str:
        """取一次快照并序列化（紧凑 JSON，减小广播体积）。"""
        return json.dumps(self._provider(), ensure_ascii=False,
                          separators=(",", ":"), default=str)

    async def broadcast_once(self) -> None:
        if not self._clients:
            return
        message = self.render()
        dead = []
        for ws in list(self._clients):
            if not await self._send(ws, message):
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def start(self) -> None:
        """启动广播循环（幂等）。"""
        if self._task is not None:
            return
        self._task = asyncio.get_event_loop().create_task(self._loop())
        logger.info("WS 广播循环已启动: %dHz", self.push_hz)

    async def _loop(self) -> None:
        interval = 1.0 / self.push_hz
        while True:
            try:
                await asyncio.sleep(interval)
                await self.broadcast_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 广播异常不能终止循环
                logger.exception("广播循环异常: %s", exc)
                await asyncio.sleep(0.5)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        for ws in list(self._clients):
            self.disconnect(ws)
