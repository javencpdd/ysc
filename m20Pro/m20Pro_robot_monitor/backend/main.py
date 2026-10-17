"""M20 Pro Web 控制台后端入口（PLAN §5.3 / §13）。

提供：
    GET  /health                 轻量健康检查
    GET  /ready                  含数据新鲜度与解析失败率（degraded）
    GET  /api/v1/schema          WS 快照 JSON Schema（**前后端契约，版本化冻结**）
    GET  /api/v1/state           当前快照（HTTP 轮询备用）
    GET  /api/v1/status          服务与链路运行状态
    GET  /api/v1/raw             最近若干条原始报文（调试）
    GET  /api/v1/fields          逐字段置信度表
    POST /api/v1/control/*       控制通道（分层开放，ADR-004）
    WS   /ws/state               10Hz 快照推送

设计约束：
1. 数据接入在独立线程（UDP 阻塞收包），解析与入库不阻塞 asyncio 事件循环；
2. 解析失败计入死信，不抛出到 ingestion 之外（PLAN §5.5）；
3. 优雅停机：先停看门狗（补零位）→ 关控制 → 停数据源 → 停广播。

⚠️ Python 3.8 兼容（196 实测 python3 = 3.8.10）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from config import Settings, load_settings  # noqa: E402
from control import patrol_codec  # noqa: E402
from control.axis_watchdog import AxisWatchdog  # noqa: E402
from control.control_gateway import ControlGateway, UdpControlSink  # noqa: E402
from control.command_log import CommandLog
from net import ap_ctl
from video import service_ctl as video_service
from errors import ConfigError, ProtocolError  # noqa: E402
from ingestion import asdu_parser  # noqa: E402
from ingestion.data_source import build_data_source  # noqa: E402
from logging_setup import setup_logging  # noqa: E402
from realtime.ws_hub import WsHub  # noqa: E402
from state.models import (SCHEMA_VERSION, ReadyResponse,  # noqa: E402
                          snapshot_json_schema)
from state.state_store import StateStore  # noqa: E402
from video.video_proxy import VideoProxy  # noqa: E402

logger = logging.getLogger("m20.console.main")


# ---------------------------------------------------------------- 请求模型
class AxisRequest(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    #: 是否持续（走看门狗 20Hz 循环）；False = 一次性指令
    continuous: bool = False
    #: 轴指令通道："steer"（2/21 主通道，默认）/ "real"（2/25 实时通道）
    channel: str = "steer"


class TimedAxisRequest(BaseModel):
    """定时移动：按给定轴值持续 duration_s 秒后自动零位停止（后端计时）。"""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    #: 持续秒数（0.5 ~ 30s；上限防"长按无人看管"）
    duration_s: float = Field(default=2.0, ge=0.5, le=30.0)
    #: 轴指令通道："steer"（默认）/ "real"
    channel: str = "steer"


class MotionRequest(BaseModel):
    """运动状态转换 / 步态：param 为 MotionParam 或 GaitParam。"""

    param: int = 0


class CommandRequest(BaseModel):
    """通用指令：name 取自 patrol_codec.COMMANDS。"""

    name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class ControlToggle(BaseModel):
    enable: bool = True
    confirmed: bool = False


class VideoServiceRequest(BaseModel):
    """视频推流服务控制：target=local|relay，action=start|stop|restart。"""

    target_local: str = Field(default="", alias="target")
    action: str = "status"
    confirmed: bool = False

    model_config = {"populate_by_name": True}


class HeartbeatToggle(BaseModel):
    """暂停 / 恢复心跳（遥测让渡）。"""
    paused: bool = True
    confirmed: bool = False


class LightRequest(BaseModel):
    """前后补光灯（1101/2）。"""
    front: bool = False
    back: bool = False


class AutoResetRequest(BaseModel):
    """首启回零开关（1101/10 写 / 1101/11 读）。"""
    enable: bool = True
    confirmed: bool = False


class SleepConfigRequest(BaseModel):
    """休眠设置（1101/6 写 / 1101/7 读）。

    ``sleep=True`` 是整车休眠（会趴下）——必须 confirmed；
    只改自动休眠开关/时长时 ``sleep`` 留 False，此时不触发休眠。
    """
    sleep: bool = False
    auto: bool = False
    minutes: int = 10
    confirmed: bool = False


class ApSetRequest(BaseModel):
    """改 M20 自身热点（只开放 SSID / 密码）。"""
    ssid: Optional[str] = None
    password: Optional[str] = None
    confirmed: bool = False


#: 服务自状态降级原因码（写入 ``ServiceSnapshot.degraded_reason``，前端分色展示）。
#: 与 ``connected=False``（链路故障）语义相反，**不能混为同一类告警**。
DEGRADED_HEARTBEAT_PAUSED = "heartbeat_paused"


# ---------------------------------------------------------------- 服务
class MonitorService:
    """组合数据源、状态仓库、WS 广播与控制闸的核心服务。"""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or Settings()
        self.state = StateStore(
            stale_threshold=self.settings.state.stale_threshold,
            raw_history_size=self.settings.state.raw_history_size,
            raw_preview_bytes=self.settings.state.raw_preview_bytes,
            link_timeout=self.settings.robot.link_timeout,
            push_hz=self.settings.service.push_hz,
            topic_hz=asdu_parser.TOPIC_HZ,
        )
        self.state.set_data_source(self.settings.data_source)

        # 报文记录（2026-10-17 加）：留下发出的原始字节帧 + 机器人响应标记。
        # mock 场景同样记录（RecordingSink 不发包，正好验证"不发也留证"的边界）。
        self.command_log = CommandLog(
            size=self.settings.control.packet_log_size,
            timeout_s=self.settings.control.packet_timeout_ms / 1000.0,
        )

        # 控制出口：udp 真实 socket；mock 场景用记录型（不发包）
        if self.settings.data_source == "mock":
            from control.control_gateway import RecordingSink
            sink: Any = RecordingSink()
        else:
            # 指令应答走**请求的源端口**回到本 socket，故出口必须能收：
            # 收到就转交 CommandLog 做 (Type,Command) 关联（见 UdpControlSink）
            sink = UdpControlSink(
                self.settings.robot.target_ip,
                self.settings.robot.target_port,
                on_response=self._on_command_response)
        self.control = ControlGateway(
            sink=sink,
            enabled=self.settings.control.enabled,
            lease_seconds=self.settings.control.lease_seconds,
            audit_size=self.settings.control.audit_size,
            axis_min=self.settings.control.axis_min,
            axis_max=self.settings.control.axis_max,
            state_provider=self._basic_fields,
            telemetry_provider=self._telemetry_paused,
            device_provider=self._device_fields,
        )
        self.control.command_log = self.command_log
        self.watchdog = AxisWatchdog(
            self.control, hz=self.settings.control.axis_hz,
            timeout_ms=self.settings.control.axis_timeout_ms,
        )
        self.source = build_data_source(self.settings.data_source, self.settings)
        self.ws = WsHub(self.snapshot, push_hz=self.settings.service.push_hz,
                        on_disconnect=self._on_last_client_gone)
        # 视频代理（M3，默认关）。HLS 产物目录由 M20_VIDEO__HLS_DIR 指定
        # （196 部署为 /home/djw/monitor/hls）
        self.video: Optional[VideoProxy] = None
        if self.settings.video.enabled:
            self.video = VideoProxy(rtsp_url=self.settings.video.rtsp_url,
                                    hls_dir=self.settings.video.hls_dir)

    # ------------------------------------------------------------ 数据接入
    def _on_frame(self, frame: Dict[str, Any]) -> None:
        """数据源回调（运行在数据源线程中）。"""
        if frame.get("kind") == "parsed":
            self.state.update(frame["frame"])
            return
        raw = frame.get("data", b"")
        try:
            parsed = asdu_parser.parse_frame(raw, frame.get("addr"))
        except ProtocolError as exc:
            self.state.record_error(raw, str(exc))
            return
        self.state.update(parsed, raw)
        # 报文响应关联（2026-10-17 加）：机器人对指令的应答带回 Type/Command，
        # 据此把"在途指令"标成 ok / error。未匹配上的（状态上报、心跳应答）
        # 是一次 dict 查找，开销可忽略。
        self.command_log.on_response(parsed["type"], parsed["command"],
                                     parsed.get("items"), raw)

    def _on_command_response(self, raw: bytes) -> None:
        """控制出口收到一帧机器人应答（运行在控制出口接收线程中）。

        basic_server 的应答信封带回 ``Type``/``Command``（实测
        ``{"PatrolDevice":{"Items":{"ErrorCode":0},"Type":1101,"Command":3,...}}``），
        据此把对应在途指令标成 ok / error。解析失败不影响接收循环。
        """
        try:
            decoded = asdu_parser.decode_frame(raw)
        except Exception as exc:  # noqa: BLE001 - 应答帧异常不该影响接收循环
            logger.debug("指令应答帧解析失败: %s", exc)
            return
        self.command_log.on_response(decoded["type"], decoded["command"],
                                     decoded.get("items"), raw)

    def _device_fields(self) -> Dict[str, Any]:
        """设备状态原始字段（含 ``dev_enable``）—— 供设备开关的"是否在关闭"判定用。

        必须给**原始 DevEnable 结构**（与 Items 同构），而不是扁平字段：
        判定要逐路比较 ``{"Video":{"Front":..,"Back":..}}``，扁平化会丢掉两路的结构。
        """
        snap = self.state.snapshot()
        topic = snap.get("topics", {}).get("device") or {}
        return topic.get("data", {}) or {}

    def _basic_fields(self) -> Dict[str, Any]:
        """供控制闸读取基础状态（前置校验用）。"""
        snap = self.state.snapshot()
        topic = snap.get("topics", {}).get("basic") or {}
        return topic.get("data", {}) or {}

    # ------------------------------------------------- 机器人设置（M4）
    def robot_config(self) -> Dict[str, Any]:
        """补光灯 / 回零开关 / 休眠配置 的当前值。

        **三条数据源性质不同，绝不能混为一谈**：

          - 补光灯 —— 设备帧（1002/5）里的 ``Led.Fill``，2Hz 自动到，
            **不用主动问**；
          - 回零开关 / 休眠配置 —— 必须主动发查询指令（1101/11、1101/7），
            异步回来。

        所以后两者一律带 ``age_s``：前端要靠它区分"还没问过"与"问过但车没答"，
        拿不到就显示"未知"——**不能拿旧值冒充当前值**（旧值可能是别人改过的）。
        """
        dev = self._device_fields()
        ar = self.command_log.query(1101, 11)
        sc = self.command_log.query(1101, 7)
        return {
            "fill_light": {
                "front": dev.get("fill_front"),
                "back": dev.get("fill_back"),
                "known": dev.get("fill_front") is not None
                         or dev.get("fill_back") is not None,
            },
            "auto_reset": _auto_reset_view(ar),
            "sleep": _sleep_view(sc),
        }

    def robot_config_refresh(self) -> Dict[str, Any]:
        """主动发两条查询指令（1101/11、1101/7）。

        只负责"问"，不负责"等"—— 应答是异步到 UDP 接收线程的，落到
        command_log 的查询缓存后由下一次 :meth:`robot_config` 读到。
        前端的节奏应该是「进页面问一次 → 2s 后读」。
        """
        sent = {}
        for name in ("auto_reset_query", "sleep_query"):
            res = self.control.execute(name, {})
            sent[name] = res.get("ok", False)
        return {"ok": any(sent.values()), "sent": sent}

    # ------------------------------------------------------- 心跳（遥测）控制
    def _telemetry_paused(self) -> bool:
        """遥测是否暂停（供控制闸的"蒙眼不开车"闸读取）。"""
        return bool(getattr(self.source, "paused", False))

    @property
    def heartbeat_paused(self) -> bool:
        return self._telemetry_paused()

    def set_heartbeat_paused(self, paused: bool, confirmed: bool = False) -> Dict[str, Any]:
        """暂停 / 恢复向机器人的心跳（= 主动让渡状态推送）。

        **语义边界（2026-10-16 查证）**：
        - 心跳（类型100/命令100）只决定"机器人往谁推送状态"；basic_server 有
          心跳超时机制（``Heartbeat timeout! Cleared %zu client(s).``），
          停发后它会**清除本客户端** → 我们失去遥测。
        - 心跳与指令是**两个独立 UDP socket**：停心跳**不影响**指令链路。
        - 机器人**不会**因为"没心跳"而趴下：2026-10-16 实证——控制台重启后
          ``sent_packets=0``（零指令）持续数分钟，车仍稳定保持 ``motion_state=17``
          （RL 站立）。车侧真正的断链保护在 rl_deploy 的 DDS_CMD 看门狗
          （``DDS_CMD topic data update timeout %f. Disable lynx``），
          效果是停运动而非趴下。

        **安全规则**：暂停遥测 = 看不见车，而指令链路仍可达 → 必须先停控制
        （看门狗零位停发），否则就是"蒙眼开车"。
        """
        if paused:
            # 只有"放弃遥测"这个危险方向需要二次确认；恢复视野是安全动作，不设卡
            if not confirmed:
                return {"ok": False, "reason": "CONFIRM_REQUIRED",
                        "detail": "停发心跳将失去遥测（车可能仍在运动），需二次确认"}
            stopped_control = False
            # 不能蒙眼开车：先零位停发正在进行的控制（摇杆 / 定时移动）
            if self.watchdog.is_active():
                self.watchdog.pause("heartbeat_paused")
                stopped_control = True
            if not self.source.pause():
                return {"ok": False, "reason": "NOT_SUPPORTED",
                        "detail": "当前数据源（%s）不支持暂停心跳"
                                  % getattr(self.source, "mode", "?")}
            self.state.set_link_degraded(True, DEGRADED_HEARTBEAT_PAUSED)
            return {"ok": True, "heartbeat_paused": True,
                    "control_stopped": stopped_control,
                    "source": self.source.stats()}
        if not self.source.resume():
            return {"ok": False, "reason": "NOT_SUPPORTED",
                    "detail": "当前数据源（%s）不支持恢复心跳"
                              % getattr(self.source, "mode", "?")}
        self.state.set_link_degraded(False)
        return {"ok": True, "heartbeat_paused": False, "source": self.source.stats()}

    def _on_last_client_gone(self) -> None:
        """最后一个 WS 客户端断开：看门狗兜底（PLAN Q11）。"""
        if self.watchdog.is_active():
            self.watchdog.pause("ws_disconnected")
        self.control._lease_until = 0.0

    # ------------------------------------------------------------ 快照
    def snapshot(self) -> Dict[str, Any]:
        """构造一次 WS 快照（契约出口）。"""
        model = self.state.build_snapshot_model(control=self.control.status())
        model.schema_version = self.settings.service.schema_version
        return model.model_dump()

    def status(self) -> Dict[str, Any]:
        counters = self.state.counters()
        return {
            "data_source": self.settings.data_source,
            "source_stats": self.source.stats(),
            "ws_clients": self.ws.count,
            "counters": counters,
            "uptime_seconds": counters["uptime"],
            "control": self.control.status(),
            "watchdog": self.watchdog.status(),
        }

    # ------------------------------------------------------------ 生命周期
    def start(self) -> None:
        self.source.on_frame(self._on_frame)
        self.source.start()
        if self.settings.control.enabled:
            self.control.enable()
        if self.video is not None:
            self.video.start()
        logger.info("监控服务已启动: data_source=%s video=%s",
                    self.settings.data_source, bool(self.video))

    def stop(self) -> None:
        """优雅停机顺序：看门狗兜底 → 关控制 → 停数据源 → 停广播。"""
        try:
            self.watchdog.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("停止看门狗异常: %s", exc)
        try:
            self.control.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭控制出口异常: %s", exc)
        try:
            self.source.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("停止数据源异常: %s", exc)
        if self.video is not None:
            self.video.stop()
        logger.info("监控服务已停止")


# ---------------------------------------------------------------- 应用装配
service: Optional[MonitorService] = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    global service
    cfg = load_settings()
    setup_logging(cfg.log_level)
    svc = MonitorService(cfg)
    service = svc
    svc.start()
    # 挂载已构建的前端静态资源（单端口部署）；必须在 settings 就绪后调用，
    # 否则 frontend_dist 路径拿不到，根路径会 404
    # ⚠️ 顺序要紧：先挂具体的 /hls，再挂兜底的 /（前端静态资源）。
    # 反过来 "/" 这个 catch-all 会把 /hls/* 请求吃掉（实测踩过：播放列表 404）。
    _mount_hls(cfg)
    _mount_frontend(cfg)
    await svc.ws.start()
    logger.info("HTTP 服务就绪: %s:%s", cfg.service.host, cfg.service.port)
    try:
        yield
    finally:
        await svc.ws.stop()
        svc.stop()
        service = None


app = FastAPI(
    title="M20 Pro Robot Console",
    description="云深处 山猫 M20 Pro 四足机器人 Web 监控控制台（LAN 内网使用）",
    version="1.0.0",
    lifespan=lifespan,
)
# 内网部署：仅放开 LAN；CORS 显式来源（PLAN §9 不用 *）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _svc() -> MonitorService:
    if service is None:  # pragma: no cover - 生命周期内必然已初始化
        raise RuntimeError("服务未初始化")
    return service


# ---------------------------------------------------------------- REST
@app.get("/health", tags=["ops"])
async def health() -> Dict[str, Any]:
    s = _svc()
    return {"ok": True, "uptime_seconds": s.state.counters()["uptime"],
            "connected": s.state.connected(), "data_source": s.settings.data_source}


@app.get("/ready", response_model=ReadyResponse, tags=["ops"])
async def ready() -> Any:
    s = _svc()
    return s.state.ready()


@app.get("/api/v1/schema", tags=["contract"])
async def schema() -> Dict[str, Any]:
    """WS 快照 JSON Schema —— 前后端契约（PLAN §5.4）。

    附带 ``gps_modes``：GPSMode 掩码的可选值清单（**协议常量，单一来源在
    ``asdu_parser``**）。前端据此渲染"卫星系统模式"选择器，避免把掩码值
    在 JS 里再硬编码一份 —— 那份迟早会和 gps.yaml 漂移。
    """
    return {
        "version": SCHEMA_VERSION,
        "schema": snapshot_json_schema(),
        "gps_modes": [
            {"mask": bit, "hex": "0x%05X" % bit, "label": label,
             "systems": asdu_parser.gps_mode_systems(bit)}
            for bit, label in sorted(asdu_parser.GPS_MODE_PRESETS.items())
        ],
    }


@app.get("/api/v1/state", tags=["state"])
async def state() -> Dict[str, Any]:
    return _svc().snapshot()


@app.get("/api/v1/status", tags=["state"])
async def status() -> Dict[str, Any]:
    return _svc().status()


@app.get("/api/v1/raw", tags=["debug"])
async def raw(limit: int = 30) -> Dict[str, Any]:
    limit = max(1, min(limit, 200))
    return {"count": limit, "items": _svc().state.get_raw_packets(limit)}


@app.get("/api/v1/fields", tags=["debug"])
async def fields() -> Dict[str, Any]:
    """逐字段置信度表（PLAN §10.4）。"""
    return {"confidence": asdu_parser.confidence_report(),
            "joint_names": asdu_parser.JOINT_NAMES}


# ---------------------------------------------------------------- 控制
@app.get("/api/v1/control/status", tags=["control"])
async def control_status() -> Dict[str, Any]:
    s = _svc()
    return {"control": s.control.status(), "watchdog": s.watchdog.status()}


@app.post("/api/v1/control/enable", tags=["control"])
async def control_enable(req: ControlToggle) -> Dict[str, Any]:
    """开启 L1（需二次确认）。"""
    s = _svc()
    if not req.confirmed:
        return {"ok": False, "reason": "CONFIRM_REQUIRED",
                "detail": "开启控制需前端二次确认"}
    if req.enable:
        s.control.enable()
        s.control.renew_lease()
    else:
        s.control.disable()
    return {"ok": True, "enabled": s.control.enabled}


@app.post("/api/v1/control/lease", tags=["control"])
async def control_lease() -> Dict[str, Any]:
    """续约（WS 断开即失效）。"""
    s = _svc()
    return {"ok": True, "lease_remaining": s.control.renew_lease()}


@app.post("/api/v1/link/heartbeat", tags=["link"])
async def control_heartbeat(req: HeartbeatToggle) -> Dict[str, Any]:
    """暂停 / 恢复向机器人的心跳（= 主动让渡状态推送）。

    **这不是运动指令**，但它决定"还能不能看见车"：

    - ``paused=true`` → 停发心跳；basic_server 心跳超时后清除本客户端，
      我们**失去遥测**。**指令链路是独立 socket、照旧可达**，所以暂停前
      服务端会先自动零位停发正在进行的控制（摇杆 / 定时移动）——不能蒙眼开车。
    - ``paused=false`` → 恢复心跳，重新获得状态推送。
    - 暂停期间所有驱动类指令被闸拒绝（``TELEMETRY_PAUSED``），
      **软急停除外**（安全手段优先）。

    实测结论（2026-10-16）：机器人**不会**因为"没心跳"而趴下——零指令下
    车稳定保持站立；车侧断链保护在 rl_deploy 的 DDS_CMD 看门狗，效果是
    停运动（``Disable lynx``）而非趴下。
    """
    s = _svc()
    return s.set_heartbeat_paused(req.paused, confirmed=req.confirmed)


@app.get("/api/v1/link/heartbeat", tags=["link"])
async def control_heartbeat_status() -> Dict[str, Any]:
    """心跳（遥测）当前状态：是否暂停、发了多少、目标是谁。"""
    s = _svc()
    return {"ok": True, "heartbeat_paused": s.heartbeat_paused,
            "source": s.source.stats()}


@app.post("/api/v1/control/command", tags=["control"])
async def control_command(req: CommandRequest) -> Dict[str, Any]:
    """下发白名单指令（name 取自 patrol_codec.COMMANDS）。"""
    s = _svc()
    return s.control.execute(req.name, req.params, confirmed=req.confirmed)


@app.post("/api/v1/control/axis", tags=["control"])
async def control_axis(req: AxisRequest) -> Dict[str, Any]:
    """轴指令：continuous=True 交给看门狗 20Hz 循环；channel 选通道（steer/real）。"""
    s = _svc()
    values = {"x": req.x, "y": req.y, "z": req.z,
              "roll": req.roll, "pitch": req.pitch, "yaw": req.yaw}
    if req.continuous:
        s.watchdog.feed(values, channel=req.channel)
        if not s.watchdog.is_active():
            s.watchdog.start()
        return {"ok": True, "continuous": True, "watchdog": s.watchdog.status()}
    return s.control.execute(patrol_codec.channel_command(req.channel), values)


@app.post("/api/v1/control/axis/timed", tags=["control"])
async def control_axis_timed(req: TimedAxisRequest) -> Dict[str, Any]:
    """定时移动（2026-10-16 加）：按给定轴值持续 ``duration_s`` 秒后自动零位停止。

    - **计时在后端**：浏览器定时器会被节流（切后台/省电），前端计时停不住车；
    - 到点 = 零位一帧 + 停发（与松手同路径，**绝不软急停**）；
    - 中止：``POST /api/v1/control/axis/stop``；
    - ``channel``：steer（2/21 主通道，默认）/ real（2/25 实时通道）—— 2026-10-16
      实测两通道在基础步态下行为完全一致，通道选择保留作排查工具；
    - **横移步态警示**：0x1001 基础（标准）步态实测不支持横移（Y 只原地调姿态、
      不位移）→ 响应带 ``warning`` 字段（**只提示、不拦截**）；
    - 先走 ``precheck``（不发送、即时反馈）：控制未开启 / 无租约 / 未站立
      等情况立即返回被拒原因，而不是让用户看着倒计时空转。
    """
    s = _svc()
    values = {"x": req.x, "y": req.y, "z": req.z,
              "roll": req.roll, "pitch": req.pitch, "yaw": req.yaw}
    rejected = s.control.precheck(patrol_codec.channel_command(req.channel))
    if rejected is not None:
        return rejected
    s.watchdog.feed_timed(values, req.duration_s, channel=req.channel)
    if not s.watchdog.is_active():
        s.watchdog.start()
    resp: Dict[str, Any] = {"ok": True, "timed": s.watchdog.status()}
    warn = _lateral_gait_warning(values, s._basic_fields())
    if warn:
        resp["warning"] = warn
    return resp


def _as_int(value: Any, default: int = 0) -> int:
    """尽力转 int（协议字段可能是字符串 / null）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _auto_reset_view(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """查询缓存 → 回零开关视图。没问过就整体 ``known=False``。"""
    if not entry:
        return {"enable": None, "known": False, "age_s": None}
    items = entry.get("items") or {}
    if "Enable" not in items:
        return {"enable": None, "known": False, "age_s": entry.get("age_s")}
    return {"enable": bool(items["Enable"]), "known": True,
            "age_s": entry.get("age_s")}


def _sleep_view(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """查询缓存 → 休眠配置视图。

    车侧应答实测为 ``{"Sleep":0,"Auto":false,"Time":10}``：
    ``Sleep`` 是**当前是否已休眠**（整数 0/1，不是布尔）、``Auto`` 是自动
    休眠开关、``Time`` 是等待分钟数（车侧校验 5~30）。
    """
    if not entry:
        return {"known": False, "age_s": None, "sleeping": None,
                "auto": None, "minutes": None}
    items = entry.get("items") or {}
    if "Time" not in items and "Auto" not in items:
        return {"known": False, "age_s": entry.get("age_s"), "sleeping": None,
                "auto": None, "minutes": None}
    return {
        "known": True,
        "age_s": entry.get("age_s"),
        "sleeping": _as_int(items.get("Sleep")) == 1,
        "auto": bool(items.get("Auto")),
        "minutes": _as_int(items.get("Time")),
    }


def _lateral_gait_warning(values: Dict[str, Any], basic: Dict[str, Any]) -> str:
    """横移步态警示（2026-10-16 真机对照实验结论）。

    实测：0x1001 基础（标准）步态下，Y 指令（两条通道均试过）只产生**原地
    姿态调整**、不位移；切 0x3002 平地（敏捷）后横移生效（vy 抬升 2× 底噪 +
    站高下沉 0.574→0.46，用户目视确认移动）。
    只提示、不拦截——保留用户自行验证/标定的余地。
    """
    try:
        lateral = abs(float(values.get("y", 0.0))) >= 0.01
    except (TypeError, ValueError):
        lateral = False
    if not lateral:
        return ""
    gait = (basic or {}).get("gait")
    if gait == patrol_codec.GAIT_BASIC_STD:
        return ("基础（标准）步态不支持横移（2026-10-16 实测）——Y 指令只会原地调整姿态；"
                "请先切「平地（敏捷）0x3002」")
    if gait == patrol_codec.GAIT_STAIR_STD:
        return ("楼梯（标准）步态与基础同系、横移未实测——若原地不动请切「平地（敏捷）0x3002」")
    return ""


@app.post("/api/v1/control/axis/stop", tags=["control"])
async def control_axis_stop() -> Dict[str, Any]:
    """松开摇杆 / 中止定时移动：发零位并停发（**不触发软急停**，车体保持站立）。

    异常断开路径（WS 断开 / 页面隐藏 / feed 超时）仍走零位兜底 ——
    2026-10-15 真机实测修正：此前松手也会软急停，表现为"一松手就趴下"。
    """
    s = _svc()
    reason = ("timed_aborted"
              if s.watchdog.status().get("timed_active") else "user_release")
    s.watchdog.pause(reason)
    return {"ok": True, "watchdog": s.watchdog.status()}


@app.post("/api/v1/control/estop", tags=["control"])
async def control_estop() -> Dict[str, Any]:
    """软急停：**不受开关限制**。"""
    return _svc().control.emergency_stop()


@app.post("/api/v1/control/estop/clear", tags=["control"])
async def control_estop_clear() -> Dict[str, Any]:
    s = _svc()
    s.control.clear_estop()
    return {"ok": True, "estop": s.control.estop}


@app.get("/api/v1/control/audit", tags=["control"])
async def control_audit(limit: int = 50) -> Dict[str, Any]:
    return {"items": _svc().control.audit(limit)}


@app.get("/api/v1/control/packets", tags=["control"])
async def control_packets(limit: int = 60) -> Dict[str, Any]:
    """指令报文记录：发出的原始字节帧 + 机器人是否响应、回了什么。

    与 ``/control/audit`` 的分工：审计是**操作视角**（含被闸拒的、没有报文），
    这里是**报文视角**（线上真实跑过的字节 + 应答）。事故复盘两个都要看。

    响应状态语义（前端分色直接认这些字符串）：
      - ``ok``          收到响应且 ErrorCode == 0
      - ``error``       收到响应但 ErrorCode != 0（附 ErrorMessage）
      - ``no_response`` 超时未响应 —— **不代表车没执行**，basic_server 对部分
                        指令执行了但并不回帧；这是"不知道"，不是"失败"
      - ``send_failed`` 本地 socket 都没发出去（没上线）
      - ``rejected``    被安全闸拦下，从未生成报文
      - ``pending``     已发出、还在等
    """
    return _svc().command_log.snapshot(limit)


# ---------------------------------------------------------------- 机器人设置（M4）
@app.get("/api/v1/robot/config", tags=["robot"])
async def robot_config() -> Dict[str, Any]:
    """补光灯 / 首启回零 / 休眠配置 的当前值。

    三条来源性质不同（详见 ``MonitorService.robot_config``），最重要的差异是
    **补光灯自动就有、另两项必须主动问**。拿到 ``known=False`` 时前端显示
    "未知"，不要显示成"关闭"——那是凭空断言。
    """
    return {"ok": True, **_svc().robot_config()}


@app.post("/api/v1/robot/config/refresh", tags=["robot"])
async def robot_config_refresh() -> Dict[str, Any]:
    """发查询指令（1101/11 + 1101/7）。应答异步到达，请 2s 后再读 GET。"""
    return _svc().robot_config_refresh()


@app.post("/api/v1/robot/light", tags=["robot"])
async def robot_light(req: LightRequest) -> Dict[str, Any]:
    """前后补光灯 (1101/2)。

    **闭环校验**：下发只回 ErrorCode（不回状态），真正的状态在设备帧
    ``Led.Fill`` 里，约 1s 后翻转。前端应当"下发 → 等 1.5s → 读设备帧比对"，
    与 GPS 模式切换的回读校验同套路。
    """
    s = _svc()
    return s.control.execute("light", {"front": 1 if req.front else 0,
                                       "back": 1 if req.back else 0})


@app.post("/api/v1/robot/auto_reset", tags=["robot"])
async def robot_auto_reset(req: AutoResetRequest) -> Dict[str, Any]:
    """首启回零开关 (1101/10)。

    ⚠️ **车侧对这条指令不回帧**（2026-10-18 实测）。所以这里的 ``result=ok``
    只表示"报文发出去了"，**不代表生效**。是否生效必须再发 1101/11 回读，
    前端要点亮"已验证"标记就得走这一步。
    """
    s = _svc()
    out = s.control.execute("auto_reset_set", {"enable": bool(req.enable)},
                            confirmed=req.confirmed)
    if out.get("ok"):
        out["verify_hint"] = "该指令无应答，请发 1101/11 回读确认是否生效"
    return out


@app.post("/api/v1/robot/sleep", tags=["robot"])
async def robot_sleep(req: SleepConfigRequest) -> Dict[str, Any]:
    """休眠设置 (1101/6)。

    三种用法差异很大，别混：
      - ``sleep=false``               → **唤醒整车**（同时也是"只改配置"的载体：
                                        改 Auto/Time 时 sleep 留 false 不会休眠）
      - ``sleep=true``                → 整车休眠，会趴下并依次断电，需 confirmed
      - ``auto=true/false, minutes``  → 只改自动休眠策略，不立即休眠
    """
    # 车侧会把 Time 夹取到 5~30（2026-10-18 实测：12→生效、60→30、3→5，且不回
    # 错误码），Auto 照常生效。也就是说用户填 60 会被静默降成 30 —— 必须在这里
    # 就拒掉并说清楚，而不是发给车侧让它静默夹取。
    if not 5 <= req.minutes <= 30:
        return {"ok": False, "command": "sleep", "reason": "MINUTES_OUT_OF_RANGE",
                "status": 409,
                "detail": "休眠时长必须在 5~30 分钟之间（车侧只接受该范围，当前 %r）" % req.minutes}
    s = _svc()
    return s.control.execute("sleep", {"enable": bool(req.sleep),
                                       "auto": bool(req.auto),
                                       "minutes": req.minutes},
                             confirmed=req.confirmed)


# ---------------------------------------------------------------- 热点（M4）
@app.get("/api/v1/net/ap", tags=["net"])
async def net_ap_status() -> Dict[str, Any]:
    """M20 自身热点 + 上行链路的状态。

    两个对象一起给是因为**它们共用一块射频**：只看 AP 会漏掉"改 AP 会不会
    拖垮上行"这个真正的风险源。
    """
    try:
        return ap_ctl.status()
    except ap_ctl.ApControlError as exc:
        return JSONResponse(
            {"ok": False, "reason": exc.reason, "detail": str(exc)},
            status_code=exc.status)


@app.post("/api/v1/net/ap", tags=["net"])
async def net_ap_set(req: ApSetRequest) -> Dict[str, Any]:
    """改热点的 SSID / 密码（只开放这两项）。

    不开放频段与信道：AP 与上行共用射频，改了会与上行走不同信道，
    结果是 AP 起不来或直接把上行（我们的 SSH 通路）带下去。

    失败时 ``result=rolled_back`` 表示已自动还原——**上行掉线一定会回滚**。
    """
    try:
        return ap_ctl.set_ap(ssid=req.ssid, password=req.password,
                             confirmed=req.confirmed)
    except ap_ctl.ApControlError as exc:
        return JSONResponse(
            {"ok": False, "reason": exc.reason, "detail": str(exc)},
            status_code=exc.status)


# ---------------------------------------------------------------- 视频（M3）
@app.get("/api/v1/video/service", tags=["video"])
async def video_service_status() -> Dict[str, Any]:
    """视频推流服务的状态（两条链：本地推流 / 外推中继）。

    与 ``/api/v1/video/status`` 的分工：那个看的是**取流侧**（MediaMTX 能否
    拉流），这里看的是**推流服务侧**（进程在不在、有没有真的在出流、以及
    能不能启停）。画面黑掉时两个都要看：进程活着但没流是最常见的一种坏法。

    **两条链不是一回事**：``local`` 是喂控制台画面的；``relay`` 是往外推的，
    关掉它控制台照旧能看到画面。
    """
    try:
        return video_service.status()
    except video_service.VideoServiceError as exc:
        return {"ok": False, "reason": exc.reason, "detail": str(exc),
                "targets": {}}


@app.post("/api/v1/video/service", tags=["video"])
async def video_service_control(req: VideoServiceRequest) -> Dict[str, Any]:
    """启动 / 停止 / 重启推流服务（``stop`` 需 ``confirmed=true``）。

    ⚠️ 这**不是机器人指令**，不受控制闸（L1/租约）约束：它是 AOS 本机服务，
    与机器人运动无关。而且"画面黑了想重启推流"很可能正好发生在控制通道没
    打开的时候 —— 把恢复手段锁在 L1 后面才是错的。
    """
    try:
        return video_service.control(req.target_local, req.action, req.confirmed)
    except video_service.VideoServiceError as exc:
        return {"ok": False, "reason": exc.reason, "detail": str(exc),
                "status": exc.status}


@app.get("/api/v1/video/status", tags=["video"])
async def video_status() -> Dict[str, Any]:
    """视频代理状态；`available=False` 时前端显示"视频中断"而非白屏。"""
    s = _svc()
    if s.video is None:
        return {"enabled": False, "available": False,
                "last_error": "视频功能未开启（M20_VIDEO__ENABLED=false）"}
    return s.video.status()


@app.get("/api/v1/video/streams", tags=["video"])
async def video_streams() -> Dict[str, Any]:
    """前后双路的取流**地址要素**（2026-10-16：双路 + WebRTC）。

    ⚠️ 故意**不含主机名**：前端按 `location.hostname` 拼接。若这里写死
    `127.0.0.1`，浏览器会去连"浏览器本机"而非 196（致命错误）；写死
    `192.168.0.196` 则换网段即失效。

    返回三档可用链路，前端按 WebRTC → MediaMTX HLS → 后端代理 的顺序降级。
    """
    s = _svc()
    v = s.settings.video
    proxy_st = s.video.status() if s.video is not None else {}
    return {
        "enabled": bool(v.enabled),
        "webrtc": {
            "enabled": bool(v.webrtc_enabled),
            "port": int(v.webrtc_port),
            "endpoint": "/{path}/whep",
            "note": "WHEP：POST application/sdp 换 answer，媒体走 ICE/UDP",
        },
        "hls": {
            "enabled": True,
            "port": int(v.mediamtx_hls_port),
            "endpoint": "/{path}/index.m3u8",
        },
        "proxy": {          # 后端 ffmpeg 中继：最后兜底（单路，可切前后）
            "enabled": s.video is not None,
            "available": bool(proxy_st.get("available", False)),
            "url": "/hls/live.m3u8",
            "rtsp_url": v.rtsp_url,
        },
        "streams": [
            {"key": "front", "label": v.front_label, "path": v.front_path},
            {"key": "back", "label": v.back_label, "path": v.back_path},
        ],
    }


@app.post("/api/v1/video/start", tags=["video"])
async def video_start() -> Dict[str, Any]:
    s = _svc()
    if s.video is None:
        return {"ok": False, "reason": "视频功能未开启"}
    return {"ok": s.video.start(), "status": s.video.status()}


@app.post("/api/v1/video/stop", tags=["video"])
async def video_stop() -> Dict[str, Any]:
    s = _svc()
    if s.video is None:
        return {"ok": False, "reason": "视频功能未开启"}
    s.video.stop()
    return {"ok": True}


@app.post("/api/v1/video/source", tags=["video"])
async def video_source(req: Dict[str, Any]) -> Dict[str, Any]:
    """切换前/后相机：{"url": "rtsp://127.0.0.1:8554/video2"}。"""
    s = _svc()
    if s.video is None:
        return {"ok": False, "reason": "视频功能未开启"}
    url = str(req.get("url", ""))
    if not url.startswith("rtsp://"):
        return {"ok": False, "reason": "URL 必须为 rtsp:// 开头"}
    return {"ok": s.video.switch(url), "status": s.video.status()}


# ---------------------------------------------------------------- WS
@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    s = _svc()
    await s.ws.connect(websocket)
    s.state.set_ws_clients(s.ws.count)
    try:
        # 建连即推一帧，避免页面空白等待
        await websocket.send_text(s.ws.render())
        while True:
            await websocket.receive_text()
            await websocket.send_text(s.ws.render())
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("WS 异常: %s", exc)
    finally:
        s.ws.disconnect(websocket)
        s.state.set_ws_clients(s.ws.count)


# ---------------------------------------------------------------- 静态前端
def _mount_hls(cfg: Settings) -> None:
    """挂载 HLS 片段目录（单端口提供 /hls/live.m3u8）。

    注：PLAN §14.3 原规划 HLS 走独立 8081 端口，实现改为挂在主应用下 —— 少一个
    进程/端口，与前端静态托管保持"单端口"一致（§15 部署方案已记录该取舍）。
    """
    if not cfg.video.enabled:
        return
    os.makedirs(cfg.video.hls_dir, exist_ok=True)
    app.mount("/hls", StaticFiles(directory=cfg.video.hls_dir), name="hls")
    logger.info("已挂载 HLS 目录: %s → /hls", cfg.video.hls_dir)


def _mount_frontend(cfg: Settings) -> None:
    if not cfg.service.serve_frontend:
        return
    dist = os.path.abspath(os.path.join(_BACKEND_DIR, cfg.service.frontend_dist))
    index = os.path.join(dist, "index.html")
    if os.path.isfile(index):
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
        logger.info("已挂载前端静态资源: %s", dist)
    else:
        logger.info("未发现前端构建产物（开发模式请用 npm run dev）")


@app.exception_handler(Exception)
async def unhandled(request, exc):  # noqa: ANN001, ANN201
    logger.exception("未处理异常: %s", exc)
    return JSONResponse(status_code=500,
                        content={"detail": "服务器内部错误", "error": str(exc)})


def main() -> None:
    import uvicorn

    try:
        cfg = load_settings()
    except ConfigError as exc:
        print("配置校验失败，拒绝启动: %s" % exc)
        raise SystemExit(2) from exc
    uvicorn.run("main:app", host=cfg.service.host, port=cfg.service.port,
                log_level=cfg.log_level.lower())


if __name__ == "__main__":
    main()
