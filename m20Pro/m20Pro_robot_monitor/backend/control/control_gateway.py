"""控制安全闸：分层开放 L0/L1/L2（ADR-004）+ 四道闸（PLAN §9 / §10.5）。

四道闸：
1. **分层开关 + 租约** —— L0 只监默认；L1 需 enable + 前端二次确认 + WS 租约（断开即失效）
2. **黑名单** —— Charge=2（清除充电状态，官方标注危险）任何配置下拒绝
3. **运动前置校验 + 值域钳制** —— 轴指令要求 MotionState∈{站立,RL控制} 且常规模式；
   值域在服务端二次截断（浏览器不是可信边界）
4. **全量审计日志** —— 谁/何时/发了什么/结果，有界留存
5. **设备供电开关专项**（2026-10-17 加，1101/3）—— 关闭需二次确认；
   站立/RL 态禁关雷达（平衡参考输入，见 ``_check_device_switch``）

**软急停永远可用**：安全手段优先于开关，L0 下也能发（ADR-004）。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import abc
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from control import patrol_codec
from control.command_log import CommandLog
from errors import (ControlBlacklistError, ControlConfirmError,
                    ControlDisabledError, ControlError, ControlLeaseError,
                    ControlOwnerError, ControlPreconditionError,
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
    """真实 UDP 出口（发往 AOS :30000）。

    **2026-10-17 补上接收侧**：basic_server 把指令应答发回**请求的源地址**
    （实测：从同一 socket 发 ``1101/7`` 就能在同一 socket 收到
    ``{"Sleep":0,"Auto":false,"Time":10}``）。此前本类只发不收 —— 应答全堵在
    socket 缓冲区里，报文记录因此永远标 ``no_response``。现在起一个守护线程
    专收应答并转交 ``on_response`` 回调（范式与 ``UdpHeartbeatSource._rx_loop``
    一致），指令链路与遥测链路仍是两个独立 socket，互不影响。

    ⚠️ 回调运行在接收线程中：``CommandLog.on_response`` 已按"单次原子操作"
    设计（deque/dict 的 append/popleft），可安全跨线程调用。
    """

    def __init__(self, target_ip: str, target_port: int, sock: Any = None,
                 on_response: Optional[Callable[[bytes], None]] = None,
                 timeout: float = 0.2) -> None:
        self.target_ip = target_ip
        self.target_port = target_port
        self._sock = sock
        self._owns_socket = sock is None
        self.failed = 0
        self.received_responses = 0
        self._on_response = on_response
        self._timeout = float(timeout)
        self._rx_thread: Optional[Any] = None
        self._running = False

    def _ensure_socket(self) -> None:
        if self._sock is None:
            import socket
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, payload: bytes) -> bool:
        self._ensure_socket()
        self._ensure_rx()
        try:
            self._sock.sendto(payload, (self.target_ip, self.target_port))
            return True
        except OSError as exc:
            self.failed += 1
            logger.warning("控制指令发送失败: %s", exc)
            return False

    # ------------------------------------------------------------ 接收侧
    def _ensure_rx(self) -> None:
        """惰性启动接收线程（首次发送时）—— 不发送就没有应答可收。"""
        if self._running or self._on_response is None:
            return
        import threading
        self._ensure_socket()
        # 必须设超时，否则 close() 时线程会永久阻塞在 recvfrom 上
        self._sock.settimeout(self._timeout)
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop,
                                           name="m20-ctrl-rx", daemon=True)
        self._rx_thread.start()
        logger.info("控制出口接收线程已启动（收指令应答 → 报文记录）")

    def _rx_loop(self) -> None:
        while self._running:
            try:
                data, _addr = self._sock.recvfrom(65535)
            except OSError:
                # timeout（正常轮询）或 socket 已关闭 → 退出
                if not self._running:
                    break
                continue
            except Exception as exc:  # noqa: BLE001 - 接收线程绝不拖死主流程
                logger.warning("控制出口接收异常: %s", exc)
                continue
            if not data:
                continue
            self.received_responses += 1
            if self._on_response is None:
                continue
            try:
                self._on_response(data)
            except Exception as exc:  # noqa: BLE001 - 回调异常不影响接收循环
                logger.warning("指令应答回调异常: %s", exc)

    def stats(self) -> Dict[str, int]:
        return {"failed": self.failed, "received_responses": self.received_responses}

    def close(self) -> None:
        self._running = False
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
                 device_provider: Optional[Callable[[], Dict[str, Any]]] = None,
                 command_log: Optional[CommandLog] = None,
                 clock: Callable[[], float] = time.monotonic,
                 owner_timeout_seconds: float = 15.0) -> None:
        self._sink = sink
        self._enabled = bool(enabled)
        self._lease_seconds = float(lease_seconds)
        # 控制权归属（2026-10-19 加，见 acquire/release/_check_owner）：
        # 控制闸是全局单例、多终端共享同一把开关 → 同一时刻只允许一个 owner。
        # ``None`` = 无主模式（旧行为：任何人可发，供单测/本机脚本直接 enable 用）。
        self._owner: Optional[Dict[str, Any]] = None
        # owner 超过这么久没续约 → 自动释放（浏览器崩溃/断网不至于把所有人锁死）
        self._owner_timeout = float(owner_timeout_seconds)
        # 轴值安全上限（2026-10-15 真机实测：0.25 舒适 / 0.40 上限 / ≥0.70 危险）
        self._axis_limits = {"min": axis_min, "max": axis_max}
        self._state_provider = state_provider
        #: 遥测是否暂停（心跳停发）—— 返回 True 时禁止驱动（见 _check_telemetry）
        self._telemetry_provider = telemetry_provider
        self._clock = clock

        #: 供"设备开关是否真的在关闭"的精确判定读取当前 ``DevEnable``
        #: （见 ``_check_device_switch``：只看目标值会把"保持不变"误判成关闭）
        self._device_provider = device_provider
        #: 报文记录（2026-10-17 加）：留下发出的原始字节帧 + 机器人响应。
        #: ``None`` = 不记录（mock/单测可关）
        self.command_log = command_log
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
        """无主启用（旧路径）：不清归属，仅供单测 / 配置自动开启使用。

        HTTP 路径请走 :meth:`acquire`——它同时登记 owner，多终端才互斥。
        """
        self._enabled = True
        logger.info("控制通道已启用（L1 低危可控）")

    def disable(self) -> None:
        """停用：先补发零位，再关闭开关，并一并释放归属。

        （归属与控制开关是绑定的：没人持有控制权时就不该开着，否则
        "释放后又回到无人归属却可驱动"的状态，互斥形同虚设。）
        """
        # 复用 send_safety_zero：它已豁免全部闸并落报文记录（留证"停用前最后发了什么"）
        self.send_safety_zero(actor="gateway", reason="disable")
        self._enabled = False
        self._lease_until = 0.0
        self._owner = None
        logger.info("控制通道已停用（回到 L0 只监）")

    # ---------------------------------------------- 控制权归属（多操作员互斥）
    # 背景：控制闸是**全局单例**——所有浏览器终端连的是同一个后端，共享同一个
    # ``_enabled``。此前"谁最后点谁说了算"：A 正在遥控，B 点一下停止就把 A 断了；
    # 更糟的是 A、B 可以同时开启、同时往一条狗发运动指令。
    # 方案：同一时刻只允许一个 owner（按终端 session_id 认定），非 owner 发驱动类
    # 指令一律拒绝；安全指令（心跳 / 软急停）不受归属限制（安全手段优先）。
    def owner_view(self) -> Dict[str, Any]:
        """对外展示的控制权信息（不含内部 session 全串，只给短码）。"""
        if self._owner is None:
            return {"held": False, "session": "", "label": "",
                    "age_s": 0.0, "idle_s": 0.0}
        now = self._clock()
        return {
            "held": True,
            "session": str(self._owner["session"])[:8],   # 短码，够区分终端即可
            "label": self._owner.get("label") or "",
            "age_s": round(now - float(self._owner["since"]), 1),
            "idle_s": round(now - float(self._owner["last_seen"]), 1),
        }

    def _expire_owner_if_needed(self) -> bool:
        """owner 超时未续约 → 自动释放（返回是否发生了释放）。

        必要性：浏览器崩溃 / 拔网线 / 笔记本合盖时不会有"主动释放"请求，
        若不回收，控制权会被一个已消失的终端**永久占死**，其他人再也开不了。
        释放前先发安全零位——操控者失联时让车停下，这是正确的兜底。
        """
        if self._owner is None:
            return False
        idle = self._clock() - float(self._owner["last_seen"])
        if idle <= self._owner_timeout:
            return False
        label = self._owner.get("label") or self._owner["session"]
        self.send_safety_zero(actor="gateway", reason="owner_expired")
        self._enabled = False
        self._lease_until = 0.0
        self._owner = None
        logger.info("控制权超时自动释放：%s（%.0fs 未续约 > %.0fs）",
                    label, idle, self._owner_timeout)
        return True

    def is_owner(self, session_id: Optional[str]) -> bool:
        """当前终端是否持有控制权。

        - **无主模式**（``_owner is None``，单测/本机脚本直接 ``enable()``）→ True，
          保持旧行为、不破坏既有调用；
        - 有主 → 必须 session 完全匹配；owner 超时则先回收再判（回到无主）。
        """
        if self._owner is None:
            return True
        if self._expire_owner_if_needed():
            return True
        sid = (session_id or "").strip()
        return bool(sid) and self._owner["session"] == sid

    def acquire(self, session_id: str, label: str = "",
                force: bool = False) -> Dict[str, Any]:
        """申请控制权（HTTP 路径的唯一入口）。

        - 无人占用 → 成为 owner，并启用 L1 + 开租约；
        - **自己**已占用 → 幂等成功（续期即可，不重复发零位）；
        - 他人占用且 ``force=False`` → 409 ``CONTROL_HELD``，附占用者信息；
        - 他人占用且 ``force=True`` → 强制接管：先发安全零位（把前一个人的
          运动停下来），再易主。接管属危险动作，前端需二次确认。
        """
        sid = (session_id or "").strip()
        if not sid:
            return {"ok": False, "reason": "NO_SESSION",
                    "detail": "缺少终端标识 session_id（前端需生成并透传）"}
        self._expire_owner_if_needed()
        cur = self._owner
        if cur is not None and cur["session"] != sid:
            if not force:
                return {"ok": False, "reason": "CONTROL_HELD",
                        "detail": "控制权已被其他终端占用，如需接管请确认后重试",
                        "owner": self.owner_view()}
            # 接管：换人开车前必须先停下车
            self.send_safety_zero(actor="gateway", reason="takeover")
            logger.info("控制权被强制接管：%s → %s", cur.get("label"), label or sid[:8])
        now = self._clock()
        if cur is not None and cur["session"] == sid:
            cur["last_seen"] = now                      # 幂等续期
            if label:
                cur["label"] = label
        else:
            self._owner = {"session": sid, "label": label or sid[:8],
                           "since": now, "last_seen": now}
        self._enabled = True
        self.renew_lease()
        return {"ok": True, "enabled": self._enabled, "owner": self.owner_view()}

    def release(self, session_id: str = "", force: bool = False) -> Dict[str, Any]:
        """释放控制权（= 停用控制并回到 L0）。

        - owner 自己释放 → 正常；
        - 非 owner 释放 → 拒绝（避免"旁观者随手把操作员掐了"），
          除非 ``force=True``（管理员/应急路径）。
        """
        sid = (session_id or "").strip()
        self._expire_owner_if_needed()
        if self._owner is not None and sid and self._owner["session"] != sid and not force:
            return {"ok": False, "reason": "NOT_OWNER",
                    "detail": "控制权属于其他终端，无法释放",
                    "owner": self.owner_view()}
        self.disable()
        return {"ok": True, "enabled": self._enabled, "owner": self.owner_view()}

    def renew_lease(self, seconds: Optional[float] = None,
                    session_id: Optional[str] = None) -> float:
        """续约（前端定期调用；WS 断开即自然失效）。

        ``session_id`` 给出时按归属校验：非 owner 续约无效（返回 0），
        否则一个旁观终端只要开着页面就能替操作员把租约一直续下去，
        让"断开即失效"这条保护失效。owner 续约同时刷新 last_seen。
        """
        if session_id is not None and not self.is_owner(session_id):
            return 0.0
        if self._owner is not None and session_id is not None:
            self._owner["last_seen"] = self._clock()
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
        msg = patrol_codec.build("soft_estop")
        payload = patrol_codec.encode("soft_estop")
        self._log_sent("soft_estop", msg, payload, actor="web", forced=True)
        ok = self._send_raw(payload)
        if not ok and self.command_log is not None:
            self.command_log.record_send_failed(
                "soft_estop", msg["type"], msg["command"], msg["items"], payload)
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
        payload = patrol_codec.encode(command, params)
        msg = patrol_codec.build(command, params)
        # 安全零位帧也必须留证：事故复盘时"停机前最后发的是什么"是关键证据
        self._log_sent(command, msg, payload, actor=actor, forced=True)
        ok = self._send_raw(payload)
        if not ok and self.command_log is not None:
            self.command_log.record_send_failed(
                command, msg["type"], msg["command"], msg["items"], payload)
        self._audit_append(command, params, "ok" if ok else "send_failed",
                           actor=actor, forced=True, reason=reason or "safety_zero")
        return ok

    def precheck(self, name: str, params: Optional[Dict[str, Any]] = None,
                 confirmed: bool = False,
                 session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """仅过闸、不发送（供"先验后行"场景：定时移动等需要即时反馈的入口）。

        ``session_id``：发起终端标识，用于归属校验（见 :meth:`_check_owner`）。

        返回 ``None`` = 通过；否则返回与 ``execute()`` 同构的拒绝信息。
        只保证"起步可行"——时序性闸（租约）在执行期间仍会逐帧复检；
        被拒同样计入审计与 rejected 计数（前端"点了没反应"可查审计定位）。
        """
        params = dict(params or {})
        try:
            self._check_blacklist(name, params)
            self._check_enabled(name)
            self._check_owner(name, session_id)
            self._check_estop(name)
            self._check_telemetry(name)
            self._check_lease(name)
            self._check_precondition(name)
            self._check_device_switch(name, params, confirmed)
            self._check_confirm(name, params, confirmed)
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
                actor: str = "web", confirmed: bool = False,
                session_id: Optional[str] = None) -> Dict[str, Any]:
        """执行一条指令，依次过各道闸。

        ``session_id``：发起终端标识，用于归属校验（见 :meth:`_check_owner`）。
        """
        params = dict(params or {})
        try:
            self._check_blacklist(name, params)
            self._check_enabled(name)
            self._check_owner(name, session_id)
            self._check_estop(name)
            self._check_telemetry(name)
            self._check_lease(name)
            self._check_precondition(name)
            self._check_device_switch(name, params, confirmed)
            self._check_confirm(name, params, confirmed)
            try:
                params = self._clamp_params(name, params)
                payload = patrol_codec.encode(name, params)
            except (KeyError, ValueError) as exc:
                # 编码层白名单/值域校验失败 = 调用方参数问题，不是安全事件，
                # 但同样要走审计与计数（前端"点了没反应"要能查到原因）。
                raise ControlError(str(exc), reason="BAD_PARAMS", status=400)
            # 报文记录：先落"已生成报文"，再发送 —— 顺序反了会漏掉
            # "socket 刚发出去那一下"的记录（send_failed 也要有据可查）。
            msg = patrol_codec.build(name, params)
            self._log_sent(name, msg, payload, actor=actor, confirmed=confirmed)
            ok = self._send_raw(payload)
            if not ok and self.command_log is not None:
                self.command_log.record_send_failed(
                    name, msg["type"], msg["command"], msg["items"], payload,
                    detail="UDP socket 发送失败")
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
            reason = getattr(exc, "reason", "rejected")
            self._audit_append(name, params, "rejected", actor=actor,
                               confirmed=confirmed, reason=reason)
            # 被拦下的也进报文记录（frame_hex=None）—— 否则用户"点了没反应"
            # 在报文面板里完全看不到，只会以为面板坏了。
            if self.command_log is not None:
                self.command_log.record_rejected(
                    name, params, reason=reason, detail=str(exc),
                    actor=actor, confirmed=confirmed)
            return {"ok": False, "command": name, "reason": reason,
                    "detail": str(exc), "status": getattr(exc, "status", 403)}

    def _check_blacklist(self, name: str, params: Dict[str, Any]) -> None:
        """闸 2：L2 黑名单 —— Charge=2 任何配置下拒绝（无"除非"）。"""
        if name == "charge" and int(params.get("action", -1)) == patrol_codec.CHARGE_RESET:
            raise ControlBlacklistError(
                "Charge=2（清除充电状态）属高危黑名单指令，官方标注危险，任何配置下都不可调用")

    # ------------------------------------------------ 系统策略通道（2026-10-20）
    def execute_system_device(self, name: str, params: Optional[Dict[str, Any]] = None,
                              actor: str = "system",
                              reason: str = "") -> Dict[str, Any]:
        """**系统策略**专用下发通道（目前唯一使用者：雷达默认关闭策略）。

        与 :meth:`execute` 的差别只有一处：**只保留安全类闸**，绕过授权类闸。

          - 照常执行的闸：黑名单、设备开关专项闸（含"站立/RL 态禁关正在运行的雷达"
            这条运动锁，以及"关闭需二次确认"—— 本方法内部固定 confirmed=True，
            因为策略是配置显式开启的，等价于用户在设置页确认过）；
          - 绕过的闸：L1 分层（``_check_enabled``）、控制权归属（``_check_owner``）、
            租约（``_check_lease``）、遥测暂停（``_check_telemetry``）、
            软急停态（``_check_estop``）。

        **为什么必须绕过授权类闸**：默认关闭雷达生效的时机本来就是"没有人在操作"
        （服务刚启动、刚被唤醒）—— 那时 L1 未开启、也没有 owner，走 ``execute()``
        必然被第一道闸拒下，策略将永远不可能生效，只剩一个假开关。

        **收紧边界（防止它变成通用后门）**：
          1. 只接受 ``name == "device_switch"`` 且 Items **仅含 "Lidar" 一键**；
          2. 动作只能是关闭（``device_switch_turns_off`` 判定），不允许借这条路开机；
          3. 审计 + 报文记录全量落账，``actor=system``、``reason`` 由调用方给出
             可读原因，事后可逐条追溯；
          4. 调用方（``LidarDefaultPolicy``）另有"雷达已关就不发 / 运动中不发 /
             两次之间限速"三重自我保护，本方法不信任调用方。

        返回结构与 :meth:`execute` 同构（``ok`` / ``reason`` / ``detail`` / ``status``）。
        """
        params = dict(params or {})
        items = params.get("items") or {}
        # 边界 1 + 2：只准"关雷达"这一种形状，别的一概拒（调用方参数问题，400）
        if name != "device_switch" or set(items) != {"Lidar"}:
            raise ControlError(
                "系统通道只允许下发 device_switch/Lidar，收到 %r %r"
                % (name, sorted(items)), reason="BAD_PARAMS", status=400)
        if not patrol_codec.device_switch_turns_off(items, None):
            raise ControlError("系统通道只允许关闭雷达，不允许开启", reason="BAD_PARAMS",
                               status=400)
        try:
            self._check_blacklist(name, params)
            self._check_device_switch(name, params, True)   # 运动锁在这一道里
            try:
                params = self._clamp_params(name, params)
                payload = patrol_codec.encode(name, params)
            except (KeyError, ValueError) as exc:
                raise ControlError(str(exc), reason="BAD_PARAMS", status=400)
            msg = patrol_codec.build(name, params)
            self._log_sent(name, msg, payload, actor=actor, confirmed=True)
            ok = self._send_raw(payload)
            if not ok and self.command_log is not None:
                self.command_log.record_send_failed(
                    name, msg["type"], msg["command"], msg["items"], payload,
                    detail="UDP socket 发送失败")
            result = "ok" if ok else "send_failed"
            self.sent_packets += 1
            self.last_command = name
            self._audit_append(name, params, result, actor=actor, confirmed=True,
                               reason=reason or "system_policy")
            return {"ok": ok, "command": name, "params": params, "result": result}
        except ControlError as exc:
            self.rejected_packets += 1
            self.last_error = str(exc)
            rsn = getattr(exc, "reason", "rejected")
            self._audit_append(name, params, "rejected", actor=actor, confirmed=True,
                               reason=rsn)
            if self.command_log is not None:
                self.command_log.record_rejected(
                    name, params, reason=rsn, detail=str(exc), actor=actor,
                    confirmed=True)
            return {"ok": False, "command": name, "reason": rsn,
                    "detail": str(exc), "status": getattr(exc, "status", 403)}

    def _check_enabled(self, name: str) -> None:
        """闸 1：分层开关（急停例外）。"""
        always = patrol_codec.COMMANDS.get(name, {}).get("always_allowed", False)
        if not self._enabled and not always:
            raise ControlDisabledError("控制通道未启用（L0 只监）；需先开启 L1 并二次确认")

    def _check_owner(self, name: str, session_id: Optional[str] = None) -> None:
        """闸 0.5：控制权归属（2026-10-19 加，多操作员互斥）。

        控制闸是全局单例、多终端共享同一把开关，因此必须回答"**这条指令是谁发的、
        他现在有没有权发**"，否则会出现两人同时开一台车 / 旁观者随手掐断操作员。

        判定：
        - ``always_allowed`` 的安全指令（心跳 / 软急停 / 解急停）→ **豁免**，
          "安全手段优先于归属"——被别人占着控制权也必须能按急停；
        - **无主模式**（``_owner is None``：单测或本机脚本直接 ``enable()``）→ 放行，
          保持旧行为，不破坏既有调用；
        - 有主 → 必须由 owner 发起；缺 session_id 或不是 owner 一律 409。
        """
        always = patrol_codec.COMMANDS.get(name, {}).get("always_allowed", False)
        if always:
            return
        if self._owner is None:
            return                                  # 无主模式：向后兼容
        sid = (session_id or "").strip()
        if not sid:
            # 单用户最容易踩：换了窗口/新标签页（= 新终端标识），或某个面板
            # 走了没带身份的旧调用。文案要说清"怎么办"，而不是甩一句"被占用"。
            raise ControlOwnerError(
                "本终端尚未登记控制权（当前由终端 %s 持有）。"
                "如果你就是操作者，请到「运动控制」点「接管控制权」"
                % self.owner_view()["session"])
        if self._owner["session"] != sid:
            raise ControlOwnerError(
                "控制权属于终端 %s（已持有 %.0fs），本终端为只读；"
                "如确需操作，请到「运动控制」点「接管控制权」"
                % (self.owner_view()["session"], self.owner_view()["age_s"]))

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

    def _check_device_switch(self, name: str, params: Dict[str, Any],
                             confirmed: bool) -> None:
        """闸 5：设备供电开关（1101/3）的安全约束。

        这条指令能**物理断电**任何设备，比运动指令更"硬"——断错的后果不可逆
        （相机断电 → /dev/video* 消失 + 推流 404；雷达断电 → 感知输入消失）。

        两条约束：
        1. **关闭必须二次确认** —— 断电不可逆，前端 confirm 后才会带 confirmed=True。
        2. **运动中禁关雷达** —— 站立/RL 态下雷达是运控的平衡参考输入，
           保守起见直接拒绝（开启随时允许）。厂商 App 不拦，但我们拦：
           真机连摔过两次，这类风险不该交给"手快点错"。
        """
        if name != "device_switch":
            return
        items = params.get("items") or {}
        # ★必须带上"当前 DevEnable"再判定"是否在关闭"：Items 是**整键覆写**，
        #   开前相机时会带上 {"Back":0}（保持后相机原本就关着），只看目标值会
        #   把这个 0 误判成关闭操作 → 要求二次确认 → 前端没弹框就发 → 用户看到
        #   "点开启被拒"（2026-10-17 真踩，回归测试已锁）。
        current = None
        if self._device_provider is not None:
            try:
                current = (self._device_provider() or {}).get("dev_enable")
            except Exception:  # noqa: BLE001 - 状态读取异常不阻塞安全判定
                current = None
        if not patrol_codec.device_switch_turns_off(items, current):
            return                      # 纯开启 / 调高 / 状态未变，不设额外闸
        if not confirmed:
            raise ControlConfirmError(
                "关闭设备供电属不可逆操作，需前端二次确认（confirmed=true）")
        if self._state_provider is None:
            return
        state = self._state_provider() or {}
        basic = state.get("basic") if "basic" in state else state
        basic = basic or {}
        motion_state = basic.get("motion_state")
        # 运动锁同样按"当前是否开着"判定：关正在运行的雷达才算危险动作
        cur_lid = (current or {}).get("Lidar")
        cur_lid = cur_lid if isinstance(cur_lid, dict) else {}
        locked = [k for k in patrol_codec.DEVICE_SWITCH_MOTION_LOCKED
                  if any(patrol_codec._as_int(v) == 0
                         and (current is None or patrol_codec._as_int(cur_lid.get(s)) != 0)
                         for s, v in (items.get(k) or {}).items())]
        if locked and motion_state in (patrol_codec.MOTION_STAND,
                                       patrol_codec.MOTION_RL):
            raise ControlPreconditionError(
                "运动中禁止关闭 %s 供电（当前 MotionState=%s，站立/RL 态下雷达是"
                "运控平衡参考输入）；请先「趴下」或「软急停」再关"
                % ("/".join(locked), motion_state))

    def _check_confirm(self, name: str, params: Dict[str, Any],
                       confirmed: bool) -> None:
        """闸 6：整车行为类指令的二次确认（2026-10-18 加）。

        与闸 5（设备供电）分工：闸 5 管"会不会掉硬件"，本闸管"整车会不会
        改变行为/丢掉安全动作"。只对**危险方向**拦——
          · 整车休眠（1101/6）：车侧依次关 LED→风扇→视频→关节供电，会趴下；
          · 关掉"首次站立前回零"（1101/10）：下次开机不标定直接站立。
        反向操作（唤醒、开启回零）不拦。
        """
        if not patrol_codec.needs_confirm(name, params):
            return
        why = {
            "sleep": "整车休眠会依次关闭 LED/风扇/视频/关节供电并趴下",
            "auto_reset_set": "关闭后开机首次站立不再回零，关节位置未经标定",
        }.get(name, "该操作会改变整车行为")
        if not confirmed:
            raise ControlConfirmError("%s，需前端二次确认（confirmed=true）" % why)

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

    def _log_sent(self, name: str, msg: Dict[str, Any], payload: bytes,
                  actor: str = "web", confirmed: bool = False,
                  forced: bool = False) -> None:
        """把一条已编码指令落入报文记录（``command_log`` 为 None 时静默跳过）。"""
        if self.command_log is None:
            return
        self.command_log.record_sent(
            name=name, type_=msg["type"], command=msg["command"],
            items=msg.get("items"), frame=payload, actor=actor,
            confirmed=confirmed, forced=forced)

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
        # 快照是最常被读的地方，顺便回收僵尸 owner（否则状态页会一直显示"被占用"）
        self._expire_owner_if_needed()
        return {
            "enabled": self._enabled,
            "estop": self._estop,
            "owner": self.owner_view(),
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
