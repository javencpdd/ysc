"""轴指令看门狗（PLAN §6.4 / ADR-004 闸 ②）。

**绝不让机器人带着最后一条指令无限运动** —— 这是控制通道最重要的单点设计。

行为（v3，**中断只停不趴**）：

1. **正常控制**：前端持续 ``feed()``（≥4Hz）→ 20Hz 循环发送当前轴值；
2. **feed 停更 > ``timeout_ms``（250ms）** → **零位一帧 + 停发**，之后保持
   "停"状态不动；前端恢复 ``feed()`` 即继续发送；
3. **任何暂停**（``pause()``：用户松手 / WS 断开 / 服务停机）→ 零位一帧 + 停发；
4. **绝不自动软急停** —— 软急停只能由人显式触发（面板「软急停」按钮 / HTTP）。

为什么切除"自动软急停"（两次真机事故，2026-10-15）：

- 事故一（凌晨）：旧版"feed 超时 / 松手 → **立即**软急停" → **运动中**的机器人
  被打软急停 → 失稳栽倒（basic_server 日志实锤 ``Recv [MotionState]: 2`` +
  姿态异常 ``pitch=-20.3°``）；
- 事故二（深夜）：v2 改为"断流 10s 延迟升级"后仍误伤 —— 一次 **10 秒链路静默**
  （浏览器卡顿/网络瞬断，连租约续约都中断）触发升级，**站立中**的机器人被打
  软急停 → 关节卸力软塌（rl_deploy 日志 ``rl_control -> joint_damping``，
  全天无姿态异常）。用户感知为"突然又倒了"。
- 结论：rl_deploy 自身有 **150ms steer 看门狗**（无新数据即清零速度字段），
  链路中断时机器人**本来就会停**；控制台做任何"自动放倒"都只会制造事故。
  **中断只停不趴。** 人不在场时机器人保持站立等待恢复，比被放倒更安全。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from control import patrol_codec
from logging_setup import get_logger

logger = get_logger("control.watchdog")


class AxisWatchdog:
    """20Hz 轴指令循环 + "只停不趴"兜底。"""

    def __init__(self, gateway: Any, hz: int = 20, timeout_ms: int = 250,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.gateway = gateway
        self.hz = max(1, int(hz))
        self.timeout_ms = int(timeout_ms)
        self._clock = clock
        self._sleep = sleeper

        self._values: Dict[str, float] = {}
        self._last_feed: Optional[float] = None
        self._paused = True          # 默认暂停：只有前端持续控制才运行
        self._running = False
        self._thread: Optional[threading.Thread] = None
        #: 停更起点（秒，monotonic）；None = 正常。停更期间只等待恢复，
        #: **不做任何自动动作**（v3：自动软急停已切除）。
        self._stale_since: Optional[float] = None
        self.sent_frames = 0

    # ------------------------------------------------------------ 控制面
    def feed(self, values: Dict[str, float]) -> None:
        """前端持续上报轴值（按住摇杆时以 ≥4Hz 调用；建议 ~16Hz）。"""
        self._values = {
            "x": float(values.get("x", 0.0)), "y": float(values.get("y", 0.0)),
            "z": float(values.get("z", 0.0)), "roll": float(values.get("roll", 0.0)),
            "pitch": float(values.get("pitch", 0.0)), "yaw": float(values.get("yaw", 0.0)),
        }
        self._last_feed = self._clock()
        self._paused = False
        self._stale_since = None

    def pause(self, reason: str = "ws_disconnected") -> None:
        """暂停发送：零位一帧 + 停发。

        适用所有中断（用户松手 / WS 断开 / 页面隐藏 / 服务停机）——语义统一：
        **只停不趴**，等前端恢复 ``feed()`` 或重新操作；绝不自动软急停。
        """
        if not self._paused:
            logger.warning("看门狗暂停（%s）", reason)
        self._paused = True
        self._stale_since = None
        # 暂停即作废当前 feed：即使之后 resume()，也必须等**新的** feed 才发送，
        # 防止用暂停前的旧轴值继续驱动（resume 语义：只解除暂停，不恢复旧指令）
        self._last_feed = None
        self._soft_pause(reason)

    def _send_zero_frame(self, reason: str) -> None:
        """零位一帧（走网关安全零位通道，豁免全部闸；失败仅记录，不抛出）。"""
        try:
            self.gateway.send_safety_zero(actor="watchdog", reason=reason)
        except Exception as exc:  # noqa: BLE001 - 兜底失败也要记录，不能吞
            logger.error("零位兜底下发失败（reason=%s；依赖车侧 150ms 看门狗清零）: %s",
                         reason, exc)

    def _soft_pause(self, reason: str) -> None:
        """停发 + 零位一帧（不软急停）。"""
        self._send_zero_frame(reason)
        logger.info("看门狗暂停（%s）：已发零位并停发（不软急停）", reason,
                    extra={"event": "watchdog_pause"})

    def resume(self) -> None:
        """恢复循环（需重新 feed 才会真正发送）。"""
        self._paused = False

    # ------------------------------------------------------------ 循环
    def tick(self) -> Optional[str]:
        """单步（供单测与循环共用），返回本步动作：axis / stale / None。"""
        if self._paused:
            return None
        # resume() 后未重新 feed：保持停发（等新 feed，不用旧值）
        if self._last_feed is None:
            return None
        now = self._clock()

        # feed 停更：零位一帧 + 停发，之后只等待恢复（绝不自动软急停）
        if (now - self._last_feed) * 1000.0 > self.timeout_ms:
            if self._stale_since is None:
                self._stale_since = now
                self._send_zero_frame("feed_stale")
                logger.warning(
                    "轴指令停更 >%dms：已发零位并停发（等待恢复；不软急停）",
                    self.timeout_ms, extra={"event": "watchdog_stale"})
                return "stale"
            return None

        # feed 新鲜：恢复正常标记 + 发送
        if self._stale_since is not None:
            logger.info("轴指令恢复（停更 %.0f ms）", (now - self._stale_since) * 1000.0,
                        extra={"event": "watchdog_resumed"})
            self._stale_since = None
        self.gateway.execute("axis", self._values, actor="watchdog")
        self.sent_frames += 1
        return "axis"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="m20-axis-watchdog", daemon=True)
        self._thread.start()
        logger.info("轴指令看门狗已启动: %dHz 超时 %dms（中断只停不趴）",
                    self.hz, self.timeout_ms)

    def _loop(self) -> None:
        interval = 1.0 / self.hz
        while self._running:
            self.tick()
            self._sleep(interval)

    def stop(self) -> None:
        """停止循环；若仍在控制中，先补零位再退出（不让机器人带着最后一条指令）。"""
        if self._running and not self._paused:
            self._soft_pause("watchdog_stop")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("轴指令看门狗已停止（发送 %d 帧）", self.sent_frames)

    def is_active(self) -> bool:
        """是否正在实际控制中（用于停机/断连时决定要不要兜底）。"""
        return self._running and not self._paused

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "paused": self._paused,
            "stale": self._stale_since is not None,
            "hz": self.hz,
            "timeout_ms": self.timeout_ms,
            "sent_frames": self.sent_frames,
            "values": dict(self._values),
        }
