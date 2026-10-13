"""ROS 方案切换 —— 把"检测到的版本"翻译成"实际采用的监控执行方案"。

职责边界
--------
- ``ros_env``    : 是什么版本（检测）
- ``ros_profiles``: 每个版本怎么干（声明）
- **本模块**      : 用哪个方案 + 出问题怎么办（裁决与回退）

优先级
------
**手动指定 > 自动检测**

手动指定的两个入口（二者同时存在时 CLI 更高）：
  1. 启动参数 ``--ros-version ros1|ros2``（写入 ``MANUAL_OVERRIDE``）
  2. 配置项 ``LITE3_ROS_VERSION=ros1|ros2``（环境变量，systemd 场景用这个）
值为 ``auto`` / 空 表示不指定，交给自动检测。

失败策略（严禁静默继续）
------------------------
检测失败、版本不受支持、手动值非法，都会：
  1. ``logger.error`` 打出**明确**原因（含手动值/检测轨迹/受支持列表）；
  2. 置 ``degraded=True`` 并保留 ``error`` 文本，供 ``/api/ros`` 与启动日志暴露；
  3. 回退到**安全默认策略**：数据源走 ``ros_config.fallback_mode``（默认 sniff，
     与 ROS 版本无关，ROS1/ROS2 都能正常工作）；
  4. 若 ``LITE3_ROS_STRICT=true``，则**不回退**，直接抛 ``RosSwitchError``
     让进程启动失败（适合"宁可挂掉也不要跑错方案"的场景）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from config import ros_config
from ros_env import DetectionResult, RosVersion, detect
from ros_profiles import RosProfile, get_profile, supported_versions

logger = logging.getLogger(__name__)

#: CLI 手动指定（``--ros-version``）写入此处，优先级最高
MANUAL_OVERRIDE: Optional[str] = None


class RosSwitchError(RuntimeError):
    """版本不受支持 / 手动值非法 / 严格模式下切换失败。"""


@dataclass
class RosPlan:
    """最终采用的方案，以及它是怎么来的。"""

    version: RosVersion
    profile: Optional[RosProfile]
    #: manual-cli / manual-env / auto / fallback
    source: str = "auto"
    #: True 表示走过回退，未采用期望方案
    degraded: bool = False
    error: Optional[str] = None
    detection: Optional[DetectionResult] = None
    #: 实际生效的数据源模式（回退时被改写成 fallback_mode）
    effective_data_source_mode: str = "sniff"

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version.value,
            "source": self.source,
            "degraded": self.degraded,
            "error": self.error,
            "effective_data_source_mode": self.effective_data_source_mode,
            "profile": self.profile.to_dict() if self.profile else None,
            "detection": self.detection.to_dict() if self.detection else None,
            "supported": supported_versions(),
        }


def set_manual_override(value: Optional[str]) -> None:
    """由 CLI（``--ros-version``）调用，写入全局手动指定值。"""
    global MANUAL_OVERRIDE
    MANUAL_OVERRIDE = value


def _parse_manual(raw: str) -> Optional[RosVersion]:
    """解析手动指定的版本；``auto``/空 返回 None（表示交自动检测），非法返回 False。"""
    token = (raw or "").strip().lower()
    if token in ("", "auto", "detect"):
        return None
    if token in ("1", "ros1", "ros_1", "noetic", "melodic"):
        return RosVersion.ROS1
    if token in ("2", "ros2", "ros_2", "foxy", "humble", "galactic"):
        return RosVersion.ROS2
    return False  # type: ignore[return-value]


def _fallback(reason: str, detection: Optional[DetectionResult]) -> RosPlan:
    """统一的回退出口：显式报错 + 安全默认（sniff）。"""
    logger.error(
        "ROS 方案切换失败，回退到安全默认数据源 '%s'。原因: %s（受支持版本: %s）",
        ros_config.fallback_mode, reason, ", ".join(supported_versions()),
    )
    if detection is not None:
        logger.error("检测轨迹: %s", [t.to_dict() for t in detection.traces])
    if ros_config.strict:
        raise RosSwitchError(
            "ROS 方案切换失败且 LITE3_ROS_STRICT=true，拒绝回退: %s" % reason
        )
    return RosPlan(
        version=RosVersion.UNKNOWN,
        profile=None,
        source="fallback",
        degraded=True,
        error=reason,
        detection=detection,
        effective_data_source_mode=ros_config.fallback_mode,
    )


def resolve(override: Optional[str] = None) -> RosPlan:
    """裁决采用哪个方案。

    Args:
        override: CLI 传入的手动值，优先级高于环境变量与自动检测。

    Returns:
        RosPlan。非严格模式下**永不抛异常**（失败走回退）。
    """
    # 1) 手动指定优先：CLI > 环境变量
    manual_raw = override if override else None
    manual_source = "manual-cli"
    if manual_raw is None:
        manual_raw = MANUAL_OVERRIDE
        manual_source = "manual-cli"
    if manual_raw is None:
        manual_raw = ros_config.version
        manual_source = "manual-env"

    detection: Optional[DetectionResult] = None

    if manual_raw:
        parsed = _parse_manual(manual_raw)
        if parsed is False:
            return _fallback(
                "手动指定的 ROS 版本非法: %r（可选: auto/ros1/ros2）" % manual_raw,
                None,
            )
        if parsed is not None:
            logger.info("ROS 版本由%s指定: %s（跳过自动检测）", manual_source, parsed.value)
            detection = DetectionResult(parsed, manual_source, "手动指定，未执行检测")
            try:
                profile = get_profile(parsed)
            except KeyError:
                return _fallback(
                    "手动指定的版本 %s 不受支持（受支持: %s）"
                    % (parsed.value, ", ".join(supported_versions())),
                    detection,
                )
            return RosPlan(
                version=parsed,
                profile=profile,
                source=manual_source,
                degraded=False,
                detection=detection,
                effective_data_source_mode=_effective_mode(profile),
            )

    # 2) 自动检测
    detection = detect(timeout=ros_config.detect_timeout)
    if not detection.ok:
        return _fallback(
            "自动检测未能确定 ROS 版本（信号均未命中）", detection
        )
    logger.info(
        "ROS 版本自动检测: %s（信号=%s，判据=%s）",
        detection.version.value, detection.signal, detection.evidence,
    )
    try:
        profile = get_profile(detection.version)
    except KeyError:
        return _fallback(
            "检测到的版本 %s 不受支持（受支持: %s）"
            % (detection.version.value, ", ".join(supported_versions())),
            detection,
        )

    return RosPlan(
        version=detection.version,
        profile=profile,
        source="auto",
        degraded=False,
        detection=detection,
        effective_data_source_mode=_effective_mode(profile),
    )


def _effective_mode(profile: RosProfile) -> str:
    """方案推荐的数据源模式；显式配置的数据源模式优先级更高。"""
    from config import data_source_config

    configured = (data_source_config.mode or "auto").lower()
    # 显式指定了具体数据源（ros/sniff/bind/ros_direct）时尊重配置；
    # 只有 auto 才由版本方案决定。
    if configured in ("ros", "sniff", "bind", "ros_direct"):
        return configured
    return profile.data_source_mode
