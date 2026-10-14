"""领域模型与 WS 快照契约（PLAN §5.4「契约先行」）。

设计取舍：
- **对外契约用 pydantic 显式建模**（``RobotSnapshot``），``/api/v1/schema`` 直接由
  ``model_json_schema()`` 生成 —— 契约与实现同源，不会出现"文档说一套、代码发另一套"；
- **topic data 用 Dict[str, Any]**，因为 ASDU 字段语义仍有 [未知] 项（PLAN Q12），
  过早固化成强类型会在真机核对时频繁破坏契约。字段集合的冻结由 tests 里的
  ``EXPECTED_FIELDS`` 白名单守护，兼顾灵活与可测性。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

#: WS 快照契约版本：前端依赖它，变更必须走版本升级 + 契约测试
SCHEMA_VERSION = "1.0"


class _Permissive(BaseModel):
    """允许额外字段：协议新增字段不应导致响应失败。"""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class TopicSnapshot(BaseModel):
    """单个 topic 的最新值 + 新鲜度（前端永不猜新鲜度，ADR-006）。"""

    ts: Optional[float] = Field(None, description="最后一次更新的墙钟时间戳（秒）")
    age_ms: Optional[float] = Field(None, description="距最后一次更新的毫秒数")
    stale: bool = Field(True, description="是否停更（超过 stale_threshold 未更新）")
    data: Dict[str, Any] = Field(default_factory=dict, description="该 topic 的领域字段")


class ControlSnapshot(BaseModel):
    """控制通道状态（供前端渲染开关/租约/急停）。"""

    enabled: bool = False
    estop: bool = False
    lease_active: bool = False
    lease_remaining: float = 0.0
    axis_hz: int = 20
    sent_packets: int = 0
    rejected_packets: int = 0
    last_error: Optional[str] = None
    last_command: Optional[str] = None


class ServiceSnapshot(BaseModel):
    """服务自身运行状态（页面顶部状态灯）。"""

    uptime_seconds: float = 0.0
    push_hz: int = 10
    data_source: str = "mock"
    ws_clients: int = 0
    packets_received: int = 0
    packets_parsed: int = 0
    packets_error: int = 0
    packets_dropped: int = 0
    degraded: bool = False
    degraded_reason: Optional[str] = None


class RobotSnapshot(BaseModel):
    """WS 推送的完整快照 —— **前后端唯一契约**（PLAN §5.4 / §18 路径 3）。"""

    schema_version: str = Field(SCHEMA_VERSION, description="契约版本号")
    type: str = "snapshot"
    server_time: float = 0.0
    connected: bool = Field(False, description="机器人链路是否在线（link_timeout 内有过更新）")
    since_last_update_ms: Optional[float] = None
    topics: Dict[str, TopicSnapshot] = Field(default_factory=dict)
    control: ControlSnapshot = Field(default_factory=ControlSnapshot)
    service: ServiceSnapshot = Field(default_factory=ServiceSnapshot)


class RawPacketItem(BaseModel):
    """原始报文环形缓冲中的一条（供 PacketMonitor/RawPacket 面板调试）。"""

    key: str = ""
    topic: str = ""
    length: int = 0
    received_at: float = 0.0
    source_ip: Optional[str] = None
    source_port: Optional[int] = None
    hex_preview: str = ""


class ReadyResponse(BaseModel):
    """/ready 响应：含数据新鲜度，解析失败率过高时 degraded。"""

    ready: bool = False
    degraded: bool = False
    reason: Optional[str] = None
    connected: bool = False
    fresh_topics: List[str] = Field(default_factory=list)
    stale_topics: List[str] = Field(default_factory=list)
    error_rate: float = 0.0


def snapshot_json_schema() -> Dict[str, Any]:
    """WS 快照的 JSON Schema（契约冻结入口，``GET /api/v1/schema``）。"""
    schema = RobotSnapshot.model_json_schema()
    schema["title"] = "M20 RobotSnapshot"
    schema["x_schema_version"] = SCHEMA_VERSION
    return schema
