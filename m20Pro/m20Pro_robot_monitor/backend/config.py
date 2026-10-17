"""集中配置 + 启动校验（fail fast，ADR-008）。

设计要点：
1. 所有可调参数集中在本文件，避免散落到业务模块；
2. 全部支持环境变量覆盖，前缀 ``M20_``（嵌套用 ``__``，如 ``M20_ROBOT__TARGET_IP``）；
3. 启动时校验：IP 格式 / 端口冲突 / 端口占用 / 目标可达——**配置错误在启动时炸出来，
   而不是运行时静默失败**（ADR-008）。

⚠️ Python 3.8 兼容：196（AOS）实测 ``python3`` = 3.8.10，本文件及全工程不使用
   3.9+ 的运行时内置泛型（``dict[str, x]``），统一走 ``typing``。

端口冲突清单来自 PLAN §2.1 C5：basic_server 30001/30002、m20video 3000、
MediaMTX 8554/1935/8888/8889、21/22/9393。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import List, Optional, Tuple

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from errors import ConfigError

logger = logging.getLogger(__name__)

#: 196 上已被占用的端口（PLAN C5），控制台必须避开
CONFLICT_PORTS = frozenset({3000, 30001, 30002, 8554, 1935, 8888, 8889, 21, 22, 9393})


class RobotSettings(BaseSettings):
    """AOS 本体（监控协议服务端）相关。"""

    model_config = SettingsConfigDict(env_prefix="M20_ROBOT__")

    # 监控协议服务端地址。
    # **2026-10-14 实测**：basic_server 监听 0.0.0.0:30000（绑全网卡），
    # 故 127.0.0.1 / 10.21.31.103 / 10.21.33.103 均可达；探针用 127.0.0.1 抓到 226 帧。
    # 默认取 127.0.0.1：后端按 PLAN §5.1 固定驻 196，回环比内网口更稳（不依赖 eth2 状态/网段变化）。
    # 若后端改到 196 之外部署，必须改成 AOS 内网 IP（如 10.21.31.103）。
    target_ip: str = "127.0.0.1"
    target_port: int = 30000
    # 心跳频率（Hz）：docs 要求 ≥1Hz；SDK 默认 5Hz
    heartbeat_hz: float = 5.0
    # 超过该时间没收到任何推送即判定链路断开（秒）
    link_timeout: float = 3.0
    # 是否在上机前校验目标可达（UDP 无连接语义，仅做 DNS/IP 层校验）
    check_reachable: bool = False


class StateSettings(BaseSettings):
    """状态层新鲜度语义（ADR-006）。"""

    model_config = SettingsConfigDict(env_prefix="M20_STATE__")

    # per-topic 超过该时间未更新即标记 stale（秒）。默认 500ms（PLAN §6.2）
    stale_threshold: float = 0.5
    # 原始报文环形缓冲条数（有界，ADR-007）
    raw_history_size: int = 1000
    raw_preview_bytes: int = 64


class ServiceSettings(BaseSettings):
    """Web 服务。"""

    model_config = SettingsConfigDict(env_prefix="M20_SERVICE__")

    host: str = "0.0.0.0"
    port: int = 8080
    push_hz: int = 10
    serve_frontend: bool = True
    frontend_dist: str = "../frontend/dist"
    # WS 快照契约版本（前端依赖它，冻结后不得随意改，见 PLAN §5.4）
    schema_version: str = "1.0"


class ControlSettings(BaseSettings):
    """控制通道（分层开放，ADR-004）。"""

    model_config = SettingsConfigDict(env_prefix="M20_CONTROL__")

    # 默认 L0 只监；开启 L1 需显式配置 + 前端二次确认 + WS 租约
    enabled: bool = False
    # 租约时长（秒）：前端需持续续约，断开即失效
    lease_seconds: float = 5.0
    # 轴指令循环频率（Hz）
    axis_hz: int = 20
    # 看门狗超时（毫秒）：超时未见新指令 → 零位停发（等待恢复）。
    # **绝不自动软急停**（2026-10-15 两次真机事故教训：任何"自动放倒"都会
    # 制造事故；车侧 rl_deploy 150ms 看门狗自会清零速度）。软急停只由人触发。
    axis_timeout_ms: int = 250
    # 审计日志条数（有界）
    audit_size: int = 500
    # 指令报文记录条数（有界）。报文带 hex 原文，比审计条目大，故默认给小一点
    packet_log_size: int = 200
    # 报文响应超时（毫秒）：超过即标 ``no_response``。
    # 真机响应在毫秒级，2s 足够宽容；再长只会让用户干等。
    # ⚠️ ``no_response`` **不代表车没执行** —— basic_server 对部分指令
    # （如运动状态转换）执行了但并不回帧，详见 command_log 模块文档。
    packet_timeout_ms: int = 2000
    # 轴指令值域钳制边界（安全上限，2026-10-15 真机实测：
    #   0.25≈0.32m/s 舒适档 / 0.40≈0.54m/s 上限 / ≥0.70≈1.1m/s 已实测危险）
    axis_min: float = -0.40
    axis_max: float = 0.40


class VideoSettings(BaseSettings):
    """视频（M3，本期默认关）。

    **链路（2026-10-16 改造为「浏览器直连 MediaMTX」）**：
      1. WebRTC / WHEP  ``http://<host>:8889/<path>/whep``        主链路 ~0.3s
      2. MediaMTX HLS   ``http://<host>:8888/<path>/index.m3u8``  兜底 ~2–3s
      3. 后端 ffmpeg 代理 ``/hls/live.m3u8``                       第三层兜底（可选）

    196 上是 MediaMTX **v1.4.2**（`webrtc: yes` / `webrtcAddress: :8889` /
    `webrtcAllowOrigin: '*'` / ICE UDP `:8189`），两路都已验证可出图
    （video1 前 / video2 后，均 H.264 800×600）。因此**后端不再中转视频流**——
    既省一路 ffmpeg，又能前后双路同时看（旧的单路 ffmpeg 中继做不到）。
    """

    model_config = SettingsConfigDict(env_prefix="M20_VIDEO__")

    enabled: bool = False
    # 取流源：196 本机 MediaMTX（近零中继）。前=video1 后=video2
    # （2026-10-15 目视核实，Q5 已闭环：video1=前路 / video2=后路）
    rtsp_url: str = "rtsp://127.0.0.1:8554/video1"
    #: HLS 片段输出目录（部署时由 systemd Environment=M20_VIDEO__HLS_DIR 覆盖，
    #: 196 上为 /home/djw/monitor/hls）
    hls_dir: str = "/tmp/m20-hls"
    #: 预留：若需独立端口提供 HLS（实现默认挂在主应用 /hls 路径下）
    hls_port: int = 8081
    #: ---- 直连 MediaMTX（WebRTC 主 + HLS 兜底）----
    #: 是否启用 WebRTC 主链路（浏览器原生 RTCPeerConnection + WHEP 拉流）
    webrtc_enabled: bool = True
    #: MediaMTX 的 WebRTC HTTP 端口（其配置 webrtcAddress: :8889）
    webrtc_port: int = 8889
    #: MediaMTX 自带 HLS 端口（其配置 hlsAddress: :8888；与后端代理的 /hls 不同）
    mediamtx_hls_port: int = 8888
    #: 前后两路（MediaMTX path 名），label 供前端显示
    front_path: str = "video1"
    front_label: str = "前相机"
    back_path: str = "video2"
    back_label: str = "后相机"


class Settings(BaseSettings):
    """顶层配置聚合。"""

    model_config = SettingsConfigDict(env_prefix="M20__")

    # 数据源：mock（无真机开发/单测）| udp（真机，默认部署）| ros2（预留，PLAN §18）
    data_source: str = "mock"
    # 回放模式：从文件按时间戳重发（T1.3 / T2.6），为空表示不启用
    replay_file: str = ""
    log_level: str = "INFO"

    robot: RobotSettings = Field(default_factory=RobotSettings)
    state: StateSettings = Field(default_factory=StateSettings)
    service: ServiceSettings = Field(default_factory=ServiceSettings)
    control: ControlSettings = Field(default_factory=ControlSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)

    @field_validator("data_source")
    @classmethod
    def _check_data_source(cls, v: str) -> str:
        v = (v or "mock").lower()
        if v not in ("mock", "udp", "ros2"):
            raise ValueError("data_source 必须是 mock / udp / ros2，收到 %r" % v)
        return v


def _validate_ip(name: str, value: str) -> None:
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ConfigError("%s 不是合法 IP 地址: %r（%s）" % (name, value, exc)) from exc


def _check_port_free(name: str, port: int) -> None:
    """端口是否被占用 / 是否落在冲突清单里。"""
    if port in CONFLICT_PORTS:
        raise ConfigError(
            "%s 端口 %d 与 196 上已有服务冲突（C5 清单：%s）"
            % (name, port, sorted(CONFLICT_PORTS))
        )
    if not (1 <= port <= 65535):
        raise ConfigError("%s 端口 %d 超出合法范围" % (name, port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
    except OSError as exc:
        raise ConfigError("%s 端口 %d 已被占用: %s" % (name, port, exc)) from exc
    finally:
        sock.close()


def _check_target_reachable(cfg: RobotSettings) -> None:
    """目标可达性：UDP 无连接语义，这里只做 IP/DNS 层校验 + 可选发包探测。"""
    try:
        ipaddress.ip_address(cfg.target_ip)
        return
    except ValueError:
        pass
    try:
        socket.gethostbyname(cfg.target_ip)
    except socket.error as exc:
        raise ConfigError("M20 目标主机 %r 无法解析: %s" % (cfg.target_ip, exc)) from exc
    if cfg.check_reachable:
        # 尽力而为：发一个空 UDP 包，不要求回应（ICMP 常被禁，不能作为判定依据）
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.5)
            sock.sendto(b"", (cfg.target_ip, cfg.target_port))
        except OSError as exc:
            logger.warning("目标 %s:%s 探测包发送失败（不阻塞启动）: %s",
                           cfg.target_ip, cfg.target_port, exc)
        finally:
            sock.close()


def validate_startup(cfg: Optional[Settings] = None) -> Settings:
    """启动校验入口：任一项不合法即抛 ConfigError（fail fast）。

    返回校验通过的 Settings。测试与 ``main.py`` 均调用本函数。
    """
    cfg = cfg or Settings()
    _validate_ip("robot.target_ip", cfg.robot.target_ip)
    _check_port_free("service.port", cfg.service.port)
    if cfg.video.enabled:
        _check_port_free("video.hls_port", cfg.video.hls_port)
    if cfg.service.push_hz <= 0:
        raise ConfigError("service.push_hz 必须 > 0，收到 %s" % cfg.service.push_hz)
    if cfg.state.stale_threshold <= 0:
        raise ConfigError("state.stale_threshold 必须 > 0")
    if cfg.robot.heartbeat_hz < 1.0:
        # docs/04 §1.2.1 明确要求 ≥1Hz，低于此值机器人不会推送
        raise ConfigError("robot.heartbeat_hz 必须 ≥1Hz（docs/04 §1.2.1），收到 %s"
                          % cfg.robot.heartbeat_hz)
    if cfg.data_source == "udp":
        _check_target_reachable(cfg.robot)
    logger.info(
        "启动校验通过: data_source=%s target=%s:%s http=%s:%s push=%sHz stale=%ss",
        cfg.data_source, cfg.robot.target_ip, cfg.robot.target_port,
        cfg.service.host, cfg.service.port, cfg.service.push_hz,
        cfg.state.stale_threshold,
    )
    return cfg


def load_settings() -> Settings:
    """构造并校验配置（供 main.py 使用）。"""
    return validate_startup(Settings())
