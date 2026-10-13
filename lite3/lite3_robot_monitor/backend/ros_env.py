"""ROS 版本检测 —— 只负责"判断当前是 ROS1 还是 ROS2"，不含任何监控执行逻辑。

设计约束
--------
1. **与执行解耦**：本模块只产出 ``DetectionResult``，不 import 任何数据源/监控模块，
   也不启动线程、不建 socket。执行方案的声明在 ``ros_profiles.py``，
   方案的选用在 ``ros_switch.py``。
2. **多信号按优先级**：单一信号在 103 上普遍不可靠（noetic 与 foxy 同时安装、
   systemd 拉起时不 source ROS 导致环境变量缺失），因此按可信度排序逐个尝试，
   第一个**明确无歧义**的信号即为结论。
3. **保留参考脚本语义**：``print_ros_version.sh`` 用
   ``systemctl is-enabled transfer``（enabled→ROS1，否则→ROS2）判断，
   本模块把它作为 ``systemd_service`` 信号保留，**该脚本本身不做任何修改**。
4. **失败可解释**：检测不出就返回 ``UNKNOWN`` 并带上每一条信号的尝试记录，
   绝不抛异常、绝不静默猜测。

信号优先级（由高到低）
----------------------
env_version   : 环境变量 ``ROS_VERSION``（1 / 2 / ros1 / ros2）
env_distro    : 环境变量 ``ROS_DISTRO``（noetic/melodic…→ROS1；foxy/humble…→ROS2）
env_marker    : ``AMENT_PREFIX_PATH`` 存在→ROS2；``ROS_MASTER_URI``/``ROS_ROOT``→ROS1
process       : 实际在跑的 transfer 进程（jetson2motion→ROS2；qnx2ros→ROS1）
systemd_service: 参考脚本逻辑（``systemctl is-enabled transfer``）
install_path  : ``/opt/ros/<distro>`` 扫描（仅当结果唯一时采信）
executable    : PATH 上的 ros2 / roscore 等（仅当结果唯一时采信）

为什么 process 排在 systemd_service 之前
----------------------------------------
``print_ros_version.sh`` 依赖 ``transfer`` 这个 unit 是否存在且 enabled，
但 ROS1 链路在 103 上是脚本拉起（``start_transfer.sh``）而非 systemd 常驻，
此时该判据会**误判为 ROS2**。以真实在跑的进程为准更贴近事实，
systemd 信号仅作为兜底保留，以维持与参考脚本的一致性。

命令行用法（验证/排障）
----------------------
    python3 ros_env.py              # 人类可读输出
    python3 ros_env.py --json       # 机器可读
    python3 ros_env.py --verbose    # 打印每条信号的尝试过程
"""

from __future__ import annotations

import enum
import glob
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class RosVersion(str, enum.Enum):
    """当前环境的 ROS 大版本。

    继承 ``str`` 便于直接放进 JSON / 日志 / 配置比较。
    """

    ROS1 = "ros1"
    ROS2 = "ros2"
    UNKNOWN = "unknown"


#: 已知发行版 → 大版本。未收录的发行版返回 None（判为未知，不猜测）。
DISTRO_MAP: Dict[str, RosVersion] = {
    # ROS1
    "kinetic": RosVersion.ROS1,
    "lunar": RosVersion.ROS1,
    "melodic": RosVersion.ROS1,
    "noetic": RosVersion.ROS1,
    # ROS2
    "dashing": RosVersion.ROS2,
    "eloquent": RosVersion.ROS2,
    "foxy": RosVersion.ROS2,
    "galactic": RosVersion.ROS2,
    "humble": RosVersion.ROS2,
    "iron": RosVersion.ROS2,
    "jazzy": RosVersion.ROS2,
    "rolling": RosVersion.ROS2,
}

#: ROS2 独占的环境变量标记
ROS2_ENV_MARKERS = ("AMENT_PREFIX_PATH", "ROS_PYTHON_VERSION", "ROS_DOMAIN_ID")
#: ROS1 独占的环境变量标记
ROS1_ENV_MARKERS = ("ROS_MASTER_URI", "ROS_ROOT", "ROS_PACKAGE_PATH")

#: 各版本 transfer 进程的可执行文件名（用于 process 信号）
PROCESS_MARKERS: Dict[RosVersion, tuple] = {
    RosVersion.ROS2: ("jetson2motion", "jetson2app", "ros2"),
    RosVersion.ROS1: ("qnx2ros", "ros2qnx", "nx2app", "rosmaster"),
}

#: ROS 安装根路径
ROS_ROOT_DIR = "/opt/ros"


@dataclass
class SignalTrace:
    """一条信号的尝试记录，用于排障时解释"为什么得出这个结论"。"""

    name: str
    version: Optional[RosVersion]
    detail: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "signal": self.name,
            "version": self.version.value if self.version else None,
            "detail": self.detail,
        }


@dataclass
class DetectionResult:
    """检测结果。

    Attributes:
        version:  结论；UNKNOWN 表示没能确定。
        signal:   命中的信号名；UNKNOWN 时为 None。
        evidence: 人类可读的判据说明。
        ok:       version != UNKNOWN。
        traces:   全部信号的尝试过程（排障用）。
    """

    version: RosVersion
    signal: Optional[str] = None
    evidence: str = ""
    traces: List[SignalTrace] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.version is not RosVersion.UNKNOWN

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version.value,
            "signal": self.signal,
            "evidence": self.evidence,
            "ok": self.ok,
            "traces": [t.to_dict() for t in self.traces],
        }


def _norm_version(raw: str) -> Optional[RosVersion]:
    """把 1/2/ros1/ros2/noetic/foxy… 归一化成 RosVersion；无法识别返回 None。"""
    if raw is None:
        return None
    token = str(raw).strip().lower()
    if token in ("1", "ros1", "ros_1", "noetic", "melodic"):
        return RosVersion.ROS1
    if token in ("2", "ros2", "ros_2", "foxy", "humble", "galactic"):
        return RosVersion.ROS2
    return DISTRO_MAP.get(token)


def _run(cmd: List[str], timeout: float) -> Optional[str]:
    """跑一条外部命令，返回 stdout；任何异常都吞掉并返回 None。"""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip()


def _scan_processes() -> Dict[RosVersion, List[str]]:
    """扫描 /proc，统计各版本 transfer 进程的出现情况（无需额外依赖）。"""
    found: Dict[RosVersion, List[str]] = {RosVersion.ROS1: [], RosVersion.ROS2: []}
    try:
        entries = list(glob.glob("/proc/[0-9]*/comm"))
    except OSError:
        return found
    for path in entries:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                comm = fh.read().strip()
        except (OSError, UnicodeDecodeError):
            continue
        for version, names in PROCESS_MARKERS.items():
            if comm in names:
                found[version].append(comm)
    return found


def detect(timeout: float = 3.0) -> DetectionResult:
    """按优先级检测当前 ROS 版本。

    Args:
        timeout: 单条外部命令（systemctl 等）的超时秒数。

    Returns:
        DetectionResult：绝不抛异常；不确定时 version=UNKNOWN。
    """
    traces: List[SignalTrace] = []

    def record(name: str, version: Optional[RosVersion], detail: str) -> Optional[DetectionResult]:
        traces.append(SignalTrace(name, version, detail))
        if version is not None and version is not RosVersion.UNKNOWN:
            return DetectionResult(version, name, detail, list(traces))
        return None

    # 1) 显式环境变量 ROS_VERSION
    raw = os.environ.get("ROS_VERSION")
    hit = record(
        "env_version",
        _norm_version(raw) if raw else None,
        "ROS_VERSION=%s" % raw if raw else "ROS_VERSION 未设置",
    )
    if hit:
        return hit

    # 2) 发行版环境变量 ROS_DISTRO
    distro = os.environ.get("ROS_DISTRO")
    version = DISTRO_MAP.get(distro.strip().lower()) if distro else None
    hit = record(
        "env_distro",
        version,
        "ROS_DISTRO=%s → %s" % (distro, version.value if version else "未知发行版")
        if distro
        else "ROS_DISTRO 未设置（systemd 拉起时通常如此）",
    )
    if hit:
        return hit

    # 3) 版本独占的环境变量标记
    has_ros2 = [m for m in ROS2_ENV_MARKERS if os.environ.get(m)]
    has_ros1 = [m for m in ROS1_ENV_MARKERS if os.environ.get(m)]
    if has_ros2 and not has_ros1:
        version = RosVersion.ROS2
        detail = "检测到 ROS2 标记: %s" % ",".join(has_ros2)
    elif has_ros1 and not has_ros2:
        version = RosVersion.ROS1
        detail = "检测到 ROS1 标记: %s" % ",".join(has_ros1)
    elif has_ros1 and has_ros2:
        version = None
        detail = "ROS1(%s) 与 ROS2(%s) 标记同时存在，歧义" % (",".join(has_ros1), ",".join(has_ros2))
    else:
        version = None
        detail = "无 ROS1/ROS2 环境变量标记"
    hit = record("env_marker", version, detail)
    if hit:
        return hit

    # 4) 实际在跑的 transfer 进程
    found = _scan_processes()
    n1, n2 = len(found[RosVersion.ROS1]), len(found[RosVersion.ROS2])
    if n2 and not n1:
        version = RosVersion.ROS2
        detail = "运行中的 ROS2 进程: %s" % ",".join(sorted(set(found[RosVersion.ROS2])))
    elif n1 and not n2:
        version = RosVersion.ROS1
        detail = "运行中的 ROS1 进程: %s" % ",".join(sorted(set(found[RosVersion.ROS1])))
    elif n1 and n2:
        version = None
        detail = "ROS1(%s) 与 ROS2(%s) 进程并存，歧义" % (
            ",".join(sorted(set(found[RosVersion.ROS1]))),
            ",".join(sorted(set(found[RosVersion.ROS2]))),
        )
    else:
        version = None
        detail = "未发现任何 transfer/ROS 进程"
    hit = record("process", version, detail)
    if hit:
        return hit

    # 5) 参考脚本 print_ros_version.sh 的判据（行为保持一致，仅作兜底）
    out = _run(["systemctl", "is-enabled", "transfer"], timeout)
    if out == "enabled":
        version = RosVersion.ROS1
        detail = "systemctl is-enabled transfer = enabled（同 print_ros_version.sh）"
    elif out in ("disabled", "static", "indirect", "masked", "alias"):
        version = RosVersion.ROS2
        detail = "systemctl is-enabled transfer = %s（同 print_ros_version.sh）" % out
    else:
        version = None
        detail = "无 transfer 单元或 systemctl 不可用（is-enabled=%r）" % out
    hit = record("systemd_service", version, detail)
    if hit:
        return hit

    # 6) 安装路径扫描（仅当唯一）
    known = []
    try:
        for entry in sorted(glob.glob(os.path.join(ROS_ROOT_DIR, "*"))):
            name = os.path.basename(entry)
            mapped = DISTRO_MAP.get(name.lower())
            if mapped:
                known.append((name, mapped))
    except OSError:
        known = []
    uniq = {v for _, v in known}
    if len(uniq) == 1:
        version = uniq.pop()
        detail = "/opt/ros 下仅有: %s" % ",".join(n for n, _ in known)
    elif len(uniq) > 1:
        version = None
        detail = "/opt/ros 下同时存在多版本: %s（歧义）" % ",".join(n for n, _ in known)
    else:
        version = None
        detail = "%s 下无可识别的发行版目录" % ROS_ROOT_DIR
    hit = record("install_path", version, detail)
    if hit:
        return hit

    # 7) 可执行文件（仅当唯一）
    has_ros2 = shutil.which("ros2") is not None
    has_ros1 = any(shutil.which(x) is not None for x in ("roscore", "rostopic", "rosversion"))
    if has_ros2 and not has_ros1:
        version = RosVersion.ROS2
        detail = "PATH 上仅有 ros2"
    elif has_ros1 and not has_ros2:
        version = RosVersion.ROS1
        detail = "PATH 上仅有 ROS1 命令（roscore/rostopic/rosversion）"
    elif has_ros1 and has_ros2:
        version = None
        detail = "PATH 上 ros2 与 ROS1 命令并存（103 常态），歧义"
    else:
        version = None
        detail = "PATH 上无 ROS 命令"
    hit = record("executable", version, detail)
    if hit:
        return hit

    return DetectionResult(RosVersion.UNKNOWN, None, "所有信号均未能确定版本", list(traces))


def main(argv: Optional[List[str]] = None) -> int:
    """命令行入口：便于在 ROS1 / ROS2 两种环境下独立验证检测逻辑。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    verbose = "--verbose" in argv or "-v" in argv

    result = detect()
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("ROS 版本: %s" % result.version.value)
        print("命中信号: %s" % (result.signal or "(无)"))
        print("判据    : %s" % (result.evidence or "(无)"))
        if verbose:
            print("信号轨迹:")
            for t in result.traces:
                print("  - %-16s %-8s %s" % (
                    t.name, t.version.value if t.version else "-", t.detail))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
