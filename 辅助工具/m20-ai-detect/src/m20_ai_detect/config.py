"""配置加载与校验。

所有配置都经环境变量注入（前缀 ``M20AI_``），不在代码里写死任何主机地址。
默认值面向 GOS（10.21.31.104）部署，但换成 227 / AOS / 运维机只改 env 文件。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .identity import DEFAULT_APP_ID, Identity, check_app_id

ENV_PREFIX = "M20AI_"

#: 响应留存条件（ADR-006）：off=只写 JSONL；alert=命中告警规则；any=检出任意目标；all=每帧
SAVE_MODES = ("off", "alert", "any", "all")

#: 上游机器人服务的 restart.sh 会 ``pkill -f`` 这些关键词，
#: 本项目的任何进程/脚本/命令行都不得包含它们，否则会被误杀。
FORBIDDEN_TOKENS = ("push_video", "v4l2", "gst-launch")


# ---------------------------------------------------------------- 数值 + 可选单位（ADR-010）
#: 体积单位 → MB 换算系数。裸数字按 **MB** 解释（"200" = 200MB）。
SIZE_UNITS_MB = {"": 1.0, "K": 1.0 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024.0}
#: 时长单位 → 天 换算系数。裸数字按 **天** 解释（"7" = 7 天）。
TIME_UNITS_DAYS = {
    "": 1.0, "S": 1.0 / 86400, "M": 1.0 / 1440, "H": 1.0 / 24, "D": 1.0, "W": 7.0,
}
_NUM_UNIT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)$")


def parse_number_with_unit(
    raw: str, key: str, units: Dict[str, float], default_unit: str, what: str
) -> float:
    """解析 "200" / "200M" / "1G" 这类带可选单位的数值（ADR-010）。

    * 裸数字按 ``default_unit`` 解释（体积=MB，时长=天）；
    * 带单位不区分大小写（"7d" 与 "7D" 等价）；
    * 单位无法识别或格式非法时抛 ConfigError，消息列出全部合法写法。
    """
    text = (raw or "").strip()
    m = _NUM_UNIT_RE.match(text)
    if not m:
        raise ConfigError(
            "%s=%r 不是合法数值（示例：%s）。%s" % (key, raw, _examples_of(units), what)
        )
    num, unit = m.group(1), m.group(2).upper()
    if unit not in units:
        raise ConfigError(
            "%s=%r 的单位 %r 无法识别。合法单位：%s；裸数字按 %s 解释"
            % (key, raw, m.group(2) or "(空)", _unit_names(units), default_unit or "(无)")
        )
    return float(num) * units[unit]


def _unit_names(units: Dict[str, float]) -> str:
    named = {k: v for k, v in units.items() if k}
    order = sorted(named.items(), key=lambda kv: kv[1])
    return "/".join(k.lower() for k, _ in order) + "（或裸数字）"


def _examples_of(units: Dict[str, float]) -> str:
    if units is SIZE_UNITS_MB:
        return "体积写法：200（=200MB）、200M、1G、512K"
    return "时长写法：7（=7天）、7d、24h、2w"


def parse_size_mb(raw: str, key: str) -> float:
    """体积 → MB。裸数字按 MB；支持 K/M/G/T。"""
    return parse_number_with_unit(raw, key, SIZE_UNITS_MB, "MB", "该字段单位是体积（MB）")


def parse_days(raw: str, key: str) -> float:
    """时长 → 天。裸数字按天；支持 s(秒)/m(分)/h(时)/d(天)/w(周)。"""
    return parse_number_with_unit(raw, key, TIME_UNITS_DAYS, "天", "该字段单位是时长（天）")


class ConfigError(ValueError):
    """配置缺失或非法。消息必须可操作（告诉用户该设哪个变量）。"""


#: 逻辑名会成为目录名（``raw/<name>/``）与 JSONL 的 ``cam`` 字段，字符集必须收紧
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")


@dataclass
class Source:
    """一路视频源（ADR-016）。

    ``uri`` 的 scheme 决定它的类型（rtsp / rtmp / device / file / http / onvif），
    见 ``sources.py``；本类只负责"是什么"，不负责"怎么拉"。

    向后兼容：老代码一律用 ``cam.src``，这里保留 ``src`` 属性别名；
    类名保留 ``Camera`` 别名，构造签名（name, uri）也不变。
    """

    name: str
    uri: str = ""
    transport: str = "auto"        # rtsp 的 tcp / udp / auto
    fps: Optional[float] = None    # 逐路 fps；None = 继承全局 M20AI_FPS
    extra: Tuple[str, ...] = ()    # 逐路 ffmpeg 附加参数
    enabled: bool = True
    note: str = ""

    @property
    def src(self) -> str:
        """老代码与既有 API 字段名（``/"src"/`` 出现在快照与配置接口里）。"""
        return self.uri

    @property
    def type(self) -> str:
        """源类型 = uri 的 scheme（``device:///dev/video0`` → ``device``）。"""
        scheme = self.uri.split("://", 1)[0].lower()
        if scheme.startswith("rtsp+") or scheme.startswith("rtmp+"):
            return scheme.split("+", 1)[0]
        if scheme == self.uri:  # 没有 "://"
            return "raw"
        return scheme

    def effective_fps(self, default: float) -> float:
        """逐路 fps；未设则继承全局（``M20AI_FPS``）。"""
        return self.fps if self.fps is not None else default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "uri": self.uri,
            "type": self.type,
            "transport": self.transport,
            "fps": self.fps,
            "extra": list(self.extra),
            "enabled": self.enabled,
            "note": self.note,
        }


#: 旧名。新代码请用 ``Source``——一路源未必是"相机"（也可能是文件或 ROS 话题）。
Camera = Source


def parse_sources(raw: str) -> List[Source]:
    """解析 ``M20AI_SOURCES`` 单行语法：``name=uri[|opt=v]``，源之间以 ``;`` 分隔。

    示例::

        front=rtsp://10.21.31.103:8554/video1;back=rtsp://.../video2|off
        cam0=device:///dev/video0|fps=2
        gate=rtmp://192.168.2.1:1935/live/0|transport=tcp|extra=-vf,hflip

    选项白名单（其余忽略并记入 note）：``off``（停用但保留配置）、``fps``、
    ``transport``、``extra``（逗号分隔的 ffmpeg 片段）、``note``。

    ⚠️ 分隔符是 ``;`` 不是 ``,``：URL 与 extra 里都可能含逗号。
    """
    out: List[Source] = []
    text = (raw or "").replace("\n", ";")
    for item in text.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ConfigError(
                "M20AI_SOURCES 片段 %r 缺少 '='（正确写法：name=uri）" % item
            )
        name, _, uri = item.partition("=")
        name = name.strip()
        opts: Dict[str, str] = {}
        if "|" in uri:
            head, _, tail = uri.partition("|")
            uri = head
            for piece in tail.split("|"):
                piece = piece.strip()
                if not piece:
                    continue
                k, eq, v = piece.partition("=")
                opts[k.strip().lower()] = v.strip() if eq else "1"
        uri = uri.strip()
        if not NAME_RE.match(name):
            raise ConfigError(
                "源名 %r 非法：只能含字母/数字/下划线/连字符，最长 32 位"
                "，且以字母或数字开头（它会成为 raw/<name>/ 目录名）" % name
            )
        if not uri:
            raise ConfigError("源 %r 的地址为空（正确写法：%s=rtsp://host/path）" % (name, name))
        fps: Optional[float] = None
        if opts.get("fps"):
            try:
                fps = float(opts["fps"])
            except ValueError:
                raise ConfigError("源 %r 的 fps=%r 不是数字" % (name, opts["fps"]))
            if not (0 < fps <= 30):
                raise ConfigError("源 %r 的 fps=%r 应在 (0, 30] 区间" % (name, fps))
        extra = tuple(s.strip() for s in (opts.get("extra") or "").split(",") if s.strip())
        out.append(
            Source(
                name=name,
                uri=uri,
                transport=(opts.get("transport") or "auto").strip() or "auto",
                fps=fps,
                extra=extra,
                enabled=opts.get("off") != "1",
                note=opts.get("note", ""),
            )
        )
    return out


#: 序列化时不能被 URI/note 容纳的字符（会破坏 ``name=uri[|opt=v]`` 语法）。
_SOURCES_UNSAFE = (";", "|", "\n", "\r")


def dump_sources(sources: List[Source]) -> str:
    """``List[Source]`` → ``M20AI_SOURCES`` 单行文本（``parse_sources`` 的逆运算）。

    供控制台源管理（ADR-016 §6）与部署脚本用：parse→改→dump 闭环，
    保证网页上改完的配置与手写在 env 里的语法完全一致
    （``front=rtsp://h/p;back=rtmp://...|off|fps=2``）。

    选项只写非默认值：``transport`` 恒写出（手写 env 常带它，语义显式），
    ``fps/extra/note`` 有则写，停用写 ``|off``。
    含 ``;``/``|``/换行的 URI 或 note 无法表达，直接抛 ConfigError
    ——宁可拒绝也不写出一条会被 parse 阶段误读的配置。
    """
    parts: List[str] = []
    for s in sources:
        for label, val in (("uri", s.uri), ("note", s.note)):
            if any(ch in val for ch in _SOURCES_UNSAFE):
                raise ConfigError(
                    "源 %r 的 %s 含无法序列化的字符（%s），请更换：%r"
                    % (s.name, label, "/".join(_SOURCES_UNSAFE), val[:60])
                )
        opts = ["transport=%s" % ((s.transport or "auto").strip() or "auto")]
        if s.fps is not None:
            opts.append("fps=%s" % _num_text(s.fps))
        if s.extra:
            opts.append("extra=%s" % ",".join(s.extra))
        if not s.enabled:
            opts.append("off")
        if s.note:
            opts.append("note=%s" % s.note)
        parts.append("%s=%s|%s" % (s.name, s.uri, "|".join(opts)))
    return ";".join(parts)


def _num_text(v: float) -> str:
    """float → 最短文本（2.0 → '2'），避免 env 里出现 'fps=2.0' 这种噪声。"""
    return "%d" % int(v) if float(v).is_integer() else "%g" % v


@dataclass
class Config:
    # --- 身份（ADR-017）：服务名 / helper / env 文件名均由 app_id 派生 ---
    # 缺省 "m20" ⇒ 老部署零改动；换成 Lite3 只改这一个变量。
    app_id: str = DEFAULT_APP_ID
    platform_name: str = ""
    profile: str = ""

    # --- AI 服务 ---
    ai_base: str = "http://jsxy.aihyzh.com:30881"
    cap_id: str = "ai-04-yolov8-object-detection"
    params: Dict[str, Any] = field(default_factory=dict)

    # --- 采集 ---
    cameras: List[Camera] = field(default_factory=list)
    #: 是否允许本地视频设备（``device://``）。它展开出的命令行含 FORBIDDEN_TOKENS
    #: 里的 ``v4l2``，在跑厂商 restart.sh 的平台上会被 pkill 误杀 ⇒ 必须显式放行。
    allow_local_device: bool = False
    fps: float = 1.0
    jpeg_q: int = 3
    fresh_age_sec: float = 0.8
    ffmpeg_bin: str = "ffmpeg"
    ffmpeg_extra: Tuple[str, ...] = ()

    # --- 推理调用 ---
    timeout: float = 10.0
    retry_max: float = 30.0
    retry_base: float = 1.0

    # --- 时钟（见 ADR-004）---
    # 车队 PTP 主时钟把系统时间钉在 2024-06-20，本机时钟系统性偏慢；
    # 此偏移量（秒）会加到 JSONL 时间戳上，输出真实时间。
    # 0 = 启动时自动向 AI 服务 Date 头测量；非 0 = 手动钉值（漂移 >2s 时 doctor 告警）。
    ts_offset_sec: float = 0.0

    # --- 存储 ---
    base_dir: str = "/home/djw/m20-ai-detect"
    ring_max_bytes: int = 200 * 1024 * 1024
    # spool/ 积压上限（帧数）：AI 服务长时间不可用时，抽帧仍在继续，若无上限会
    # 以 ~7 MB/min（2 路 1fps）无限增长，一夜能写十几 GB。超限后丢最旧的帧。
    spool_max_files: int = 600
    # results/ 保留天数：0 = 永不删除（默认，权威数据）；>0 时每小时清理一次
    # 超过天数的 *.jsonl（按 mtime；今天正在写的文件 mtime 新，不会被误删）。
    results_keep_days: float = 0.0
    # 响应留存条件（ADR-006）：触发时把 AI 标注结果图 + 原始响应（剥 base64）
    # 落 saved/<cam>/。旧开关 SAVE_RESULT_IMAGE=true 兼容映射为 "alert"。
    save_mode: str = "off"
    save_result_image: bool = False
    # saved/ 留存清理（ADR-008）：0 = 不按该维度清理。
    # saved_max_bytes：saved/ 总量上限，超出时从最旧开始成对删 .jpg/.json；
    # saved_keep_days：>0 时先按年龄删（mtime 早于 now-keep_days 的对）。
    # 两者可同时生效（先按年龄、再按体积）。时间轴卡片只能看到未被清理的图片。
    saved_max_bytes: int = 500 * 1024 * 1024
    saved_keep_days: float = 0.0

    # --- 告警 ---
    alert_labels: Tuple[str, ...] = ()
    alert_score: float = 0.60

    # --- 心跳 ---
    source_down_sec: float = 30.0

    # ---------------------------------------------------------------- 构造
    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "Config":
        env = os.environ if env is None else env

        def get(key: str, default: str) -> str:
            return env.get(ENV_PREFIX + key, default)

        def get_float(key: str, default: float) -> float:
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            try:
                return float(raw)
            except ValueError:
                raise ConfigError("%s%s=%r 不是数字" % (ENV_PREFIX, key, raw))

        def get_int(key: str, default: int) -> int:
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            try:
                return int(raw)
            except ValueError:
                raise ConfigError("%s%s=%r 不是整数" % (ENV_PREFIX, key, raw))

        def get_size_mb(key: str, default: float) -> float:
            """体积字段（MB）。兼容 "200" 与 "200M"/"1G"（ADR-010）。"""
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            return parse_size_mb(raw, ENV_PREFIX + key)

        def get_days(key: str, default: float) -> float:
            """时长字段（天）。兼容 "7" 与 "7d"/"24h"（ADR-010）。"""
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            return parse_days(raw, ENV_PREFIX + key)

        def get_bool(key: str, default: bool) -> bool:
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        def get_list(key: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            return tuple(s.strip() for s in raw.split(",") if s.strip())

        def get_choice(key: str, default: str, choices: Tuple[str, ...]) -> str:
            raw = env.get(ENV_PREFIX + key)
            if raw is None or raw.strip() == "":
                return default
            val = raw.strip().lower()
            if val not in choices:
                raise ConfigError(
                    "%s%s=%r 必须是 %s 之一" % (ENV_PREFIX, key, raw, "/".join(choices))
                )
            return val

        params: Dict[str, Any] = {}
        raw_params = env.get(ENV_PREFIX + "PARAMS_JSON", "").strip()
        if raw_params:
            try:
                params = json.loads(raw_params)
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    "%sPARAMS_JSON 不是合法 JSON：%s（示例：{\"obj_thresh\":0.3}）"
                    % (ENV_PREFIX, exc)
                )
            if not isinstance(params, dict):
                raise ConfigError("%sPARAMS_JSON 必须是 JSON 对象" % ENV_PREFIX)

        # SAVE_MODE 显式优先；未设时旧开关 SAVE_RESULT_IMAGE=true 兼容映射为 alert
        save_mode_explicit = (env.get(ENV_PREFIX + "SAVE_MODE") or "").strip() != ""
        save_mode = get_choice("SAVE_MODE", "off", SAVE_MODES)
        legacy_save_image = get_bool("SAVE_RESULT_IMAGE", False)
        if not save_mode_explicit and legacy_save_image:
            save_mode = "alert"

        cfg = cls(
            app_id=get("APP_ID", DEFAULT_APP_ID).strip() or DEFAULT_APP_ID,
            platform_name=get("PLATFORM_NAME", "").strip(),
            profile=get("PROFILE", "").strip(),
            ai_base=get("AI_BASE", "http://jsxy.aihyzh.com:30881").rstrip("/"),
            cap_id=get("CAP_ID", "ai-04-yolov8-object-detection"),
            params=params,
            fps=get_float("FPS", 1.0),
            allow_local_device=get_bool("ALLOW_LOCAL_DEVICE", False),
            jpeg_q=get_int("JPEG_Q", 3),
            fresh_age_sec=get_float("FRESH_AGE_SEC", 0.8),
            ffmpeg_bin=get("FFMPEG_BIN", "ffmpeg"),
            ffmpeg_extra=tuple(get("FFMPEG_EXTRA", "").split()),
            timeout=get_float("TIMEOUT", 10.0),
            retry_max=get_float("RETRY_MAX", 30.0),
            retry_base=get_float("RETRY_BASE", 1.0),
            ts_offset_sec=get_float("TS_OFFSET_SEC", 0.0),
            base_dir=get("BASE_DIR", "/home/djw/m20-ai-detect"),
            ring_max_bytes=int(get_size_mb("RING_MAX_MB", 200) * 1024 * 1024),
            spool_max_files=get_int("SPOOL_MAX_FILES", 600),
            results_keep_days=get_days("RESULTS_KEEP_DAYS", 0.0),
            saved_max_bytes=int(get_size_mb("SAVED_MAX_MB", 500) * 1024 * 1024),
            saved_keep_days=get_days("SAVED_KEEP_DAYS", 0.0),
            save_mode=save_mode,
            save_result_image=legacy_save_image,
            alert_labels=get_list("ALERT_LABELS", ()),
            alert_score=get_float("ALERT_SCORE", 0.60),
            source_down_sec=get_float("SOURCE_DOWN_SEC", 30.0),
        )

        # ---------------------------------------------------------------- 视频源
        # 新语法（任意 N 路）优先；没设才回落到旧的两槽位 ENABLE_F/ENABLE_B
        # —— 已部署的 m20-ai-detect.env 一个字都不用改（ADR-016 兼容承诺）。
        raw_sources = (env.get(ENV_PREFIX + "SOURCES") or "").strip()
        if raw_sources:
            cfg.cameras = parse_sources(raw_sources)
        else:
            # 相机：默认单路前视（GOS 部署时指向 AOS 内网 RTSP）
            cfg.cameras = []
            if get_bool("ENABLE_F", True):
                cfg.cameras.append(
                    Camera(get("CAM_NAME_F", "front"), get("SRC_F", "rtsp://10.21.31.103:8554/video1"))
                )
            if get_bool("ENABLE_B", False):
                cfg.cameras.append(
                    Camera(get("CAM_NAME_B", "back"), get("SRC_B", "rtsp://10.21.31.103:8554/video2"))
                )
        cfg.validate()
        return cfg

    # ---------------------------------------------------------------- 校验
    def validate(self) -> None:
        # app_id 会成为 unit 名 / helper 路径的一部分，必须在配置阶段就校验字符集
        try:
            check_app_id(self.app_id)
        except ValueError as exc:  # IdentityError 继承自 ValueError
            raise ConfigError(str(exc))
        self._validate_local_device()
        if not self.ai_base.startswith(("http://", "https://")):
            raise ConfigError("M20AI_AI_BASE 必须以 http:// 或 https:// 开头")
        if not self.cap_id.strip():
            raise ConfigError("M20AI_CAP_ID 不能为空")
        if not self.cameras:
            raise ConfigError(
                "至少启用一路视频源：M20AI_SOURCES='front=rtsp://host/path'"
                "（或旧写法 M20AI_ENABLE_F=1 + M20AI_SRC_F=...）"
            )
        if not [c for c in self.cameras if c.enabled]:
            raise ConfigError(
                "所有视频源都被标为停用（M20AI_SOURCES 里的 |off）——至少启用一路"
            )
        if not (0 < self.fps <= 30):
            raise ConfigError("M20AI_FPS 应在 (0, 30] 区间，当前 %r" % self.fps)
        if not (1 <= self.jpeg_q <= 31):
            raise ConfigError("M20AI_JPEG_Q 应在 [1, 31] 区间（ffmpeg -q:v），当前 %r" % self.jpeg_q)
        if self.timeout <= 0:
            raise ConfigError("M20AI_TIMEOUT 必须为正数")
        if not (0.0 <= self.alert_score <= 1.0):
            raise ConfigError("M20AI_ALERT_SCORE 应在 [0,1]，当前 %r" % self.alert_score)
        if self.ring_max_bytes < 10 * 1024 * 1024:
            raise ConfigError("M20AI_RING_MAX_MB 不应小于 10（MB）")
        if not (50 <= self.spool_max_files <= 10000):
            raise ConfigError("M20AI_SPOOL_MAX_FILES 应在 50~10000，当前 %r" % self.spool_max_files)
        if self.saved_max_bytes < 0:
            raise ConfigError("M20AI_SAVED_MAX_MB 不能为负（0 = 不按体积清理）")
        if self.saved_keep_days < 0:
            raise ConfigError("M20AI_SAVED_KEEP_DAYS 不能为负（0 = 不按年龄清理）")
        if self.save_mode not in SAVE_MODES:
            raise ConfigError(
                "M20AI_SAVE_MODE=%r 必须是 %s 之一" % (self.save_mode, "/".join(SAVE_MODES))
            )
        names = [c.name for c in self.cameras]
        if len(set(names)) != len(names):
            raise ConfigError("相机逻辑名重复：%s" % names)
        for cam in self.cameras:
            if not NAME_RE.match(cam.name):
                raise ConfigError(
                    "源名 %r 非法：只能含字母/数字/下划线/连字符，最长 32 位，"
                    "且以字母或数字开头（它会成为 raw/<name>/ 目录名）" % cam.name
                )
            if not cam.src.strip():
                raise ConfigError("源 %r 的地址为空" % cam.name)
            for token in FORBIDDEN_TOKENS:
                if token in cam.src:
                    raise ConfigError(
                        "源地址 %r 含禁用关键词 %r（会被上游 restart.sh 的 pkill 误杀）"
                        "；本地相机请写 device:///dev/video0，不要用 -f v4l2 裸参数"
                        % (cam.src, token)
                    )

    # ---------------------------------------------------------------- 工具
    def _validate_local_device(self) -> None:
        """``device://`` 的闸门：不放行就不许用（延迟 import 避免 config↔sources 成环）。"""
        from .sources import LOCAL_DEVICE_TOKENS, resolve

        for cam in self.cameras:
            if not cam.enabled:
                continue
            res = resolve(cam)
            if not res.needs_local_ok:
                continue
            if not self.allow_local_device:
                raise ConfigError(
                    "源 %r 是本地视频设备，展开后的命令行含 %s，"
                    "在跑厂商 restart.sh 的平台上（如 M20）会被 pkill 误杀。\n"
                    "确认本机不会触发该脚本后，显式放行：M20AI_ALLOW_LOCAL_DEVICE=1"
                    % (cam.name, "/".join(LOCAL_DEVICE_TOKENS))
                )

    @property
    def enabled_cameras(self) -> List[Source]:
        """启用的源（``|off`` 的不参与采集/预览）。

        停用的源仍然留在 ``cameras`` 里 —— UI 要显示它（否则用户没法重新启用），
        但 sampler / snapshot 一律用本属性过滤。
        """
        return [c for c in self.cameras if c.enabled]

    @property
    def identity(self) -> Identity:
        """身份：unit 名 / helper / env 文件名都由它派生。"""
        return Identity(
            app_id=self.app_id,
            platform_name=self.platform_name,
            profile=self.profile,
            base_dir=self.base_dir,
        )

    @property
    def task_url(self) -> str:
        return "%s/api/v1/tasks/%s" % (self.ai_base, self.cap_id)

    @property
    def health_url(self) -> str:
        return "%s/api/v1/health" % self.ai_base

    def redacted(self) -> Dict[str, Any]:
        """用于日志打印：屏蔽 URL 中可能存在的凭据。"""
        d = dict(self.__dict__)
        d["cameras"] = [dict(name=c.name, src=c.src) for c in self.cameras]
        if "@" in self.ai_base:
            scheme, rest = self.ai_base.split("://", 1)
            host = rest.split("@", 1)[1]
            d["ai_base"] = "%s://***@%s" % (scheme, host)
        return d
