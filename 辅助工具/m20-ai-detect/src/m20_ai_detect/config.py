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


@dataclass
class Camera:
    """一路视频源：逻辑名 + 取流地址。"""

    name: str
    src: str


@dataclass
class Config:
    # --- AI 服务 ---
    ai_base: str = "http://jsxy.aihyzh.com:30881"
    cap_id: str = "ai-04-yolov8-object-detection"
    params: Dict[str, Any] = field(default_factory=dict)

    # --- 采集 ---
    cameras: List[Camera] = field(default_factory=list)
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
            ai_base=get("AI_BASE", "http://jsxy.aihyzh.com:30881").rstrip("/"),
            cap_id=get("CAP_ID", "ai-04-yolov8-object-detection"),
            params=params,
            fps=get_float("FPS", 1.0),
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
            results_keep_days=get_days("RESULTS_KEEP_DAYS", 0.0),
            saved_max_bytes=int(get_size_mb("SAVED_MAX_MB", 500) * 1024 * 1024),
            saved_keep_days=get_days("SAVED_KEEP_DAYS", 0.0),
            save_mode=save_mode,
            save_result_image=legacy_save_image,
            alert_labels=get_list("ALERT_LABELS", ()),
            alert_score=get_float("ALERT_SCORE", 0.60),
            source_down_sec=get_float("SOURCE_DOWN_SEC", 30.0),
        )

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
        if not self.ai_base.startswith(("http://", "https://")):
            raise ConfigError("M20AI_AI_BASE 必须以 http:// 或 https:// 开头")
        if not self.cap_id.strip():
            raise ConfigError("M20AI_CAP_ID 不能为空")
        if not self.cameras:
            raise ConfigError("至少启用一路相机（M20AI_ENABLE_F / M20AI_ENABLE_B）")
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
            if not cam.src.strip():
                raise ConfigError("相机 %r 的 M20AI_SRC_* 为空" % cam.name)
            for token in FORBIDDEN_TOKENS:
                if token in cam.src:
                    raise ConfigError(
                        "源地址 %r 含禁用关键词 %r（会被上游 restart.sh 的 pkill 误杀）"
                        % (cam.src, token)
                    )

    # ---------------------------------------------------------------- 工具
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
