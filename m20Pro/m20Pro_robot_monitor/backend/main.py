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


class HeartbeatToggle(BaseModel):
    """暂停 / 恢复心跳（遥测让渡）。"""
    paused: bool = True
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

        # 控制出口：udp 真实 socket；mock 场景用记录型（不发包）
        if self.settings.data_source == "mock":
            from control.control_gateway import RecordingSink
            sink: Any = RecordingSink()
        else:
            sink = UdpControlSink(self.settings.robot.target_ip,
                                  self.settings.robot.target_port)
        self.control = ControlGateway(
            sink=sink,
            enabled=self.settings.control.enabled,
            lease_seconds=self.settings.control.lease_seconds,
            audit_size=self.settings.control.audit_size,
            axis_min=self.settings.control.axis_min,
            axis_max=self.settings.control.axis_max,
            state_provider=self._basic_fields,
            telemetry_provider=self._telemetry_paused,
        )
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

    def _basic_fields(self) -> Dict[str, Any]:
        """供控制闸读取基础状态（前置校验用）。"""
        snap = self.state.snapshot()
        topic = snap.get("topics", {}).get("basic") or {}
        return topic.get("data", {}) or {}

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
    """WS 快照 JSON Schema —— 前后端契约（PLAN §5.4）。"""
    return {"version": SCHEMA_VERSION, "schema": snapshot_json_schema()}


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


# ---------------------------------------------------------------- 视频（M3）
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
