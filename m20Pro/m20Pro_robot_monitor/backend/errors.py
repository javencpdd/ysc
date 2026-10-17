"""类型化错误层次（PLAN §5.3）。

为什么要分层：不同错误需要不同的**处理策略**，而不是不同的字符串。
  - AppError        —— 所有业务错误的基类
  - ConfigError     —— 启动期配置错，进程应当退出（fail fast）
  - ProtocolError   —— 报文解析错，计入死信计数，**绝不抛出到 ingestion 之外**
  - StaleError      —— 数据过期，用于降级路径判定
  - ControlError    —— 控制指令被安全闸拒绝（含分层/黑名单/前置校验/值域）
"""

from __future__ import annotations

from typing import Optional


class AppError(Exception):
    """所有业务错误基类。"""

    default_message = "应用错误"

    def __init__(self, message: Optional[str] = None, **detail: object) -> None:
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict:
        out = {"error": type(self).__name__, "message": self.message}
        out.update(self.detail)
        return out


class ConfigError(AppError):
    """配置错误：启动期即应失败（ADR-008）。"""

    default_message = "配置错误"


class ProtocolError(AppError):
    """协议/报文解析错误：解析层自己消化，不向外抛（PLAN §5.5）。"""

    default_message = "协议解析失败"


class StaleError(AppError):
    """数据过期：上层据此降级（红色横幅 / /ready degraded）。"""

    default_message = "数据已停更"


class ControlError(AppError):
    """控制指令被拒绝。"""

    default_message = "控制指令被拒绝"

    #: 拒绝原因码，便于前端分场景提示
    def __init__(self, message: Optional[str] = None, reason: str = "rejected",
                 status: int = 403, **detail: object) -> None:
        super().__init__(message, **detail)
        self.reason = reason
        self.status = status


class ControlDisabledError(ControlError):
    """L0 只监状态下的拒绝（急停除外）。"""

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message or "控制通道未启用（L0 只监）",
                         reason="CONTROL_DISABLED", status=403)


class ControlBlacklistError(ControlError):
    """L2 黑名单指令：任何配置下都拒绝（Charge=2）。"""

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message or "该指令在黑名单中，任何配置下都不可调用",
                         reason="BLACKLISTED", status=403)


class ControlConfirmError(ControlError):
    """不可逆操作缺二次确认（2026-10-17 加：设备供电关闭）。

    设备开关（1101/3）能物理断电相机 / 雷达 / GPS / 风扇，断错的后果不可逆，
    因此"关闭"一律要求前端 confirm 后带 ``confirmed=true``。
    """

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message or "该操作不可逆，需二次确认",
                         reason="CONFIRM_REQUIRED", status=409)


class ControlPreconditionError(ControlError):
    """前置条件不满足（如未站立、非常规模式）。"""

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message, reason="PRECONDITION_FAILED", status=409)


class ControlLeaseError(ControlError):
    """租约失效（WS 断开或未续约）。"""

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message or "控制租约已失效，请重新获取",
                         reason="LEASE_EXPIRED", status=409)


class ControlTelemetryError(ControlError):
    """遥测已暂停（心跳停发）：看不见车，禁止驱动指令。

    2026-10-16 加：`POST /api/v1/link/heartbeat {paused:true}` 会停发心跳、
    放弃状态推送（basic_server 随后清除本客户端）。此时**指令链路仍然活着**
    （心跳与指令是两个独立 UDP socket），若放任驱动就是"蒙眼开车"——
    故暂停遥测时一律拒绝驱动类指令，软急停除外（安全手段优先）。
    """

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message or "遥测已暂停（心跳停发）——看不见车时禁止驱动，请先恢复心跳",
                         reason="TELEMETRY_PAUSED", status=409)
