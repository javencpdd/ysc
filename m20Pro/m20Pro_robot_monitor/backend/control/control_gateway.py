"""控制安全闸：分层开放 L0/L1/L2（ADR-004）+ 四道闸（PLAN §9 / §10.5）。

四道闸：
1. **分层开关 + 租约** —— L0 只监默认；L1 需 enable + 前端二次确认 + WS 租约（断开即失效）
2. **黑名单** —— Charge=2（清除充电状态，官方标注危险）任何配置下拒绝
3. **运动前置校验 + 值域钳制** —— 轴指令要求 MotionState∈{站立,RL控制} 且常规模式；
   值域在服务端二次截断（浏览器不是可信边界）
4. **全量审计日志** —— 谁/何时/发了什么/结果，有界留存

**软急停永远可用**：安全手段优先于开关，L0 下也能发（ADR-004）。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import abc
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from control import patrol_codec
from errors import (ControlBlacklistError, ControlDisabledError, ControlError,
                    ControlLeaseError, ControlPreconditionError,
                    ControlTelemetryError)
from logging_setup import get_logger

logger = get_logger("control.gateway")


class ControlSink(abc.ABC):
    """控制出口抽象（ADR-010：与 DataSource 对称）。

    本期实现 UdpControlSink（真实 UDP 出口）；将来 Ros2ControlSink 实现同一接口，
    上层（网关/看门狗/前端）对"出口是 UDP 还是 ROS2"零感知。
    """

    @abc.abstractmethod
    def send(self, payload: bytes) -> bool:
        """发送已编码的字节帧；成功返回 True。"""

    @abc.abstractmethod
    def close(self) -> None:
        """释放资源。"""


class RecordingSink(ControlSink):
    """测试用出口：记录所有发出的帧，不真正发包。"""

    def __init__(self) -> None:
        self.sent: List[bytes] = []

    def send(self, payload: bytes) -> bool:
        self.sent.append(payload)
        return True

    def close(self) -> None:
        pass


class UdpControlSink(ControlSink):
    """真实 UDP 出口（发往 AOS :30000）。"""

    def __init__(self, target_ip: str, target_port: int, sock: Any = None) -> None:
        self.target_ip = target_ip
        self.target_port = target_port
        self._sock = sock
        self._owns_socket = sock is None
        self.failed = 0

    def _ensure_socket(self) -> None:
        if self._sock is None:
            import socket
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, payload: bytes) -> bool:
        self._ensure_socket()
        try:
            self._sock.sendto(payload, (self.target_ip, self.target_port))
            return True
        except OSError as exc:
            self.failed += 1
            logger.warning("控制指令发送失败: %s", exc)
            return False

    def close(self) -> None:
        if self._sock is not None and self._owns_socket:
            self._sock.close()
        self._sock = None


class ControlGateway:
    """指令安全闸。"""

    def __init__(self, sink: ControlSink, enabled: bool = False,
                 lease_seconds: float = 5.0, audit_size: int = 500,
                 axis_min: float = -0.40, axis_max: float = 0.40,
                 state_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 telemetry_provider: Optional[Callable[[], bool]] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._sink = sink
        self._enabled = bool(enabled)
        self._lease_seconds = float(lease_seconds)
        # 轴值安全上限（2026-10-15 真机实测：0.25 舒适 / 0.40 上限 / ≥0.70 危险）
        self._axis_limits = {"min": axis_min, "max": axis_max}
        self._state_provider = state_provider
        #: 遥测是否暂停（心跳停发）—— 返回 True 时禁止驱动（见 _check_telemetry）
        self._telemetry_provider = telemetry_provider
        self._clock = clock

        self._lease_until = 0.0
        self._estop = False
        self._audit: Deque[Dict[str, Any]] = deque(maxlen=int(audit_size))
        self.sent_packets = 0
        self.rejected_packets = 0
        self.last_error: Optional[str] = None
        self.last_command: Optional[str] = None

    # ------------------------------------------------------ 开关 / 租约
    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        logger.info("控制通道已启用（L1 低危可控）")

    def disable(self) -> None:
        """停用：先补发零位，再关闭开关。"""
        try:
            self._send_raw(patrol_codec.encode("axis", {
                "x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}))
        except ControlError:
            pass
        self._enabled = False
        self._lease_until = 0.0
        logger.info("控制通道已停用（回到 L0 只监）")

    def renew_lease(self, seconds: Optional[float] = None) -> float:
        """续约（前端定期调用；WS 断开即自然失效）。"""
        self._lease_until = self._clock() + (seconds if seconds is not None
                                             else self._lease_seconds)
        return self.lease_remaining()

    def lease_remaining(self) -> float:
        return max(0.0, self._lease_until - self._clock())

    def lease_active(self) -> bool:
        return self.lease_remaining() > 0

    @property
    def estop(self) -> bool:
        return self._estop

    def clear_estop(self) -> None:
        self._estop = False
        logger.info("急停锁定已解除")

    def emergency_stop(self) -> Dict[str, Any]:
        """软急停：**不受开关限制**（安全手段优先）。"""
        self._estop = True
        ok = self._send_raw(patrol_codec.encode("soft_estop"))
        self._audit_append("soft_estop", {}, "ok" if ok else "send_failed", forced=True)
        return {"ok": ok, "estop": True}

    def send_safety_zero(self, actor: str = "watchdog", reason: str = "",
                         command: str = "axis") -> bool:
        """安全零位帧（全轴 0）—— **豁免全部四道闸**（内部专用，不暴露 HTTP）。

        零位在任何车体状态下都是安全操作（速度清零），与 soft_estop 同理念
        "安全手段优先"：不能因为租约过期 / 开关关闭 / 前置不满足就把机器人
        留在运动中。2026-10-15 实测发现：看门狗零位兜底被租约闸拦截
        （``控制指令 axis -> rejected``）→ 兜底形同虚设，特设本通道。

        ``command``：零位走哪条轴通道（"axis" 主 / "axis_real" 实时）——
        与正在控制的通道一致，确保同一订阅方立刻看到零位。
        """
        params = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        ok = self._send_raw(patrol_codec.encode(command, params))
        self._audit_append(command, params, "ok" if ok else "send_failed",
                           actor=actor, forced=True, reason=reason or "safety_zero")
        return ok

    def precheck(self, name: str, params: Optional[Dict[str, Any]] = None
                 ) -> Optional[Dict[str, Any]]:
        """仅过闸、不发送（供"先验后行"场景：定时移动等需要即时反馈的入口）。

        返回 ``None`` = 通过；否则返回与 ``execute()`` 同构的拒绝信息。
        只保证"起步可行"——时序性闸（租约）在执行期间仍会逐帧复检；
        被拒同样计入审计与 rejected 计数（前端"点了没反应"可查审计定位）。
        """
        params = dict(params or {})
        try:
            self._check_blacklist(name, params)
            self._check_enabled(name)
            self._check_estop(name)
            self._check_telemetry(name)
            self._check_lease(name)
            self._check_precondition(name)
            return None
        except ControlError as exc:
            self.rejected_packets += 1
            self.last_error = str(exc)
            self._audit_append(name, params, "rejected",
                               reason=getattr(exc, "reason", "rejected"))
            return {"ok": False, "command": name, "reason": getattr(exc, "reason", "rejected"),
                    "detail": str(exc), "status": getattr(exc, "status", 403)}

    # ------------------------------------------------------ 指令执行
    def execute(self, name: str, params: Optional[Dict[str, Any]] = None,
                actor: str = "web", confirmed: bool = False) -> Dict[str, Any]:
        """执行一条指令，依次过四道闸。"""
        params = dict(params or {})
        try:
            self._check_blacklist(name, params)
            self._check_enabled(name)
            self._check_estop(name)
            self._check_telemetry(name)
            self._check_lease(name)
            self._check_precondition(name)
            params = self._clamp_params(name, params)
            payload = patrol_codec.encode(name, params)
            ok = self._send_raw(payload)
            result = "ok" if ok else "send_failed"
            self.sent_packets += 1
            self.last_command = name
            # 软急停是"状态"而不只是一条指令：发出后必须锁存，
            # 否则后续指令会在机器人仍在急停态时被放行（真实缺陷，单测已覆盖）
            if name == "soft_estop":
                self._estop = True
            self._audit_append(name, params, result, actor=actor, confirmed=confirmed)
            return {"ok": ok, "command": name, "params": params, "result": result}
        except ControlError as exc:
            self.rejected_packets += 1
            self.last_error = str(exc)
            self._audit_append(name, params, "rejected", actor=actor,
                               confirmed=confirmed, reason=getattr(exc, "reason", "rejected"))
            return {"ok": False, "command": name, "reason": getattr(exc, "reason", "rejected"),
                    "detail": str(exc), "status": getattr(exc, "status", 403)}

    def _check_blacklist(self, name: str, params: Dict[str, Any]) -> None:
        """闸 2：L2 黑名单 —— Charge=2 任何配置下拒绝（无"除非"）。"""
        if name == "charge" and int(params.get("action", -1)) == patrol_codec.CHARGE_RESET:
            raise ControlBlacklistError(
                "Charge=2（清除充电状态）属高危黑名单指令，官方标注危险，任何配置下都不可调用")

    def _check_enabled(self, name: str) -> None:
        """闸 1：分层开关（急停例外）。"""
        always = patrol_codec.COMMANDS.get(name, {}).get("always_allowed", False)
        if not self._enabled and not always:
            raise ControlDisabledError("控制通道未启用（L0 只监）；需先开启 L1 并二次确认")

    def _check_estop(self, name: str) -> None:
        if self._estop and name not in ("soft_estop", "clear_estop"):
            raise ControlDisabledError("急停已激活，需先解除急停锁定")

    def _check_telemetry(self, name: str) -> None:
        """闸 3.5：遥测暂停时禁止驱动（2026-10-16 加，"蒙眼不开车"）。

        停发心跳后我们**看不到车**（basic_server 会清除本客户端、停止状态推送），
        但指令链路是另一个独立 UDP socket、照旧可达 —— 此时任何驱动指令都是
        "蒙眼开车"，一律拒绝。

        豁免：``heartbeat``（恢复遥视的路径本身，否则"停心跳→想恢复"会被自己
        的闸锁死）、``soft_estop``（``always_allowed``，安全手段优先）。
        """
        if self._telemetry_provider is None:
            return
        if name in ("heartbeat", "soft_estop"):
            return
        try:
            paused = bool(self._telemetry_provider())
        except Exception:  # noqa: BLE001 - 探针异常不拖死指令链路
            return
        if paused:
            raise ControlTelemetryError()

    def _check_lease(self, name: str) -> None:
        """闸 1：租约（WS 断开即失效）。"""
        always = patrol_codec.COMMANDS.get(name, {}).get("always_allowed", False)
        if name in ("heartbeat", "sleep_query") or always:
            return
        if not self.lease_active():
            raise ControlLeaseError("控制租约已失效（%.1fs 内未续约），请重新获取"
                                    % self._lease_seconds)

    def _check_precondition(self, name: str) -> None:
        """闸 3：运动前置校验（docs/04 §1.2.5：轴指令仅常规模式可执行）。"""
        if not patrol_codec.COMMANDS.get(name, {}).get("motion", False):
            return
        if self._state_provider is None:
            return  # 无状态源时不阻塞（M1 mock 场景由单测显式覆盖）
        state = self._state_provider() or {}
        # 兼容两种形态：直接给基础字段 dict（main._basic_fields 如此），或 {"basic": {...}}
        basic = state.get("basic") if "basic" in state else state
        basic = basic or {}
        motion_state = basic.get("motion_state")
        mode = basic.get("control_usage_mode")
        if motion_state not in (patrol_codec.MOTION_STAND, patrol_codec.MOTION_RL):
            raise ControlPreconditionError(
                "轴指令需先站立（MotionState∈{1 站立,17 RL控制}），当前=%s" % motion_state)
        if mode not in (None, patrol_codec.MODE_NORMAL):
            raise ControlPreconditionError(
                "轴指令仅支持常规模式（ControlUsageMode=0），当前=%s" % mode)

    def _clamp_params(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """闸 3：值域钳制（服务端二次截断）——两条轴通道同构，都要钳。"""
        if name in ("axis", "axis_real"):
            limits = self._axis_limits
            for key, field in (("x", "X"), ("y", "Y"), ("z", "Z"),
                               ("roll", "Roll"), ("pitch", "Pitch"), ("yaw", "Yaw")):
                if key in params:
                    params[key] = patrol_codec._clamp(params[key], limits["min"], limits["max"])
        return params

    def _send_raw(self, payload: bytes) -> bool:
        return self._sink.send(payload)

    # ------------------------------------------------------ 审计 / 状态
    def _audit_append(self, name: str, params: Dict[str, Any], result: str,
                      actor: str = "web", confirmed: bool = False,
                      reason: str = "", forced: bool = False) -> None:
        self._audit.append({
            "ts": time.time(),
            "command": name,
            "params": {k: v for k, v in params.items()},
            "result": result,
            "actor": actor,
            "confirmed": bool(confirmed),
            "forced": bool(forced),
            "reason": reason,
        })
        logger.info("控制指令 %s -> %s", name, result,
                    extra={"event": "control", "cmd": name})

    def audit(self, limit: int = 50) -> List[Dict[str, Any]]:
        items = list(self._audit)
        items.reverse()
        return items[:limit]

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "estop": self._estop,
            "lease_active": self.lease_active(),
            "lease_remaining": round(self.lease_remaining(), 2),
            "axis_hz": 20,
            "sent_packets": self.sent_packets,
            "rejected_packets": self.rejected_packets,
            "last_error": self.last_error,
            "last_command": self.last_command,
        }

    def close(self) -> None:
        self._sink.close()
