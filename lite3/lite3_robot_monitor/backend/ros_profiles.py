"""ROS 版本执行方案声明表 —— 各版本"怎么干"全部集中在此声明。

为什么单独一个文件
------------------
``ros_env.py`` 只回答"是 ROS1 还是 ROS2"，**不关心**拿到版本后要做什么；
本文件只声明"某个版本该用什么方式做事"，**不关心**版本是怎么来的。
二者通过 ``ros_switch.py`` 组装，实现检测与执行的解耦。

新增一个 ROS 版本支持的步骤就三步：在 ``PROFILES`` 里加一条声明、
确认 ``ros_env.RosVersion`` 有对应枚举、其余代码无需改动。

字段说明
--------
topic_list_cmd   : 话题发现命令（argv 列表，不用 shell，避免注入）
node_list_cmd    : 节点发现命令
topic_hz_cmd     : 话题频率探测命令模板，``{topic}`` 占位
process_patterns : 进程与资源采集时用来匹配的目标进程名（ps / proc 扫描用）
resource_cmd     : 资源采集命令模板，``{pid}`` 占位（取该进程 CPU/内存）
data_source_mode : 该版本推荐的数据源模式（见 config.DataSourceConfig）
ros_impl         : 该版本下 ros 数据源的实现：bridge / direct / none
notes            : 人类可读备注，会出现在 /api/ros 里供排障
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ros_env import RosVersion


@dataclass(frozen=True)
class RosProfile:
    """某一 ROS 大版本对应的监控执行方案。"""

    version: RosVersion
    label: str
    distros: Tuple[str, ...]

    # ---- 发现类 ----
    topic_list_cmd: List[str] = field(default_factory=list)
    node_list_cmd: List[str] = field(default_factory=list)
    topic_hz_cmd: List[str] = field(default_factory=list)

    # ---- 进程与资源采集 ----
    process_patterns: Tuple[str, ...] = ()
    resource_cmd: List[str] = field(default_factory=list)

    # ---- 数据源策略 ----
    data_source_mode: str = "sniff"
    ros_impl: str = "none"

    notes: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version.value,
            "label": self.label,
            "distros": list(self.distros),
            "topic_list_cmd": list(self.topic_list_cmd),
            "node_list_cmd": list(self.node_list_cmd),
            "topic_hz_cmd": list(self.topic_hz_cmd),
            "process_patterns": list(self.process_patterns),
            "resource_cmd": list(self.resource_cmd),
            "data_source_mode": self.data_source_mode,
            "ros_impl": self.ros_impl,
            "notes": self.notes,
        }


#: 版本 → 方案。键与 ``RosVersion`` 的取值一致（ros1 / ros2）。
PROFILES: Dict[RosVersion, RosProfile] = {
    RosVersion.ROS1: RosProfile(
        version=RosVersion.ROS1,
        label="ROS1 (roscore / rostopic / rosnode)",
        distros=("kinetic", "lunar", "melodic", "noetic"),
        topic_list_cmd=["rostopic", "list"],
        node_list_cmd=["rosnode", "list"],
        topic_hz_cmd=["rostopic", "hz", "{topic}"],
        # ROS1 侧 transfer 由 start_transfer.sh 拉起，进程名与 ROS2 不同
        process_patterns=(
            "rosmaster", "roscore", "rosout",
            "qnx2ros", "ros2qnx", "nx2app", "sensor_checker",
        ),
        resource_cmd=["ps", "-o", "pid,pcpu,pmem,rss,etime,comm", "-p", "{pid}"],
        # 关键差异：ROS1 没有可用的 ros→监控桥接（现有 ros_bridge_node 是 ROS2 节点），
        # 因此走 sniff 旁路抓 43897——它与 ROS 版本无关，是 ROS1 下的安全选择。
        data_source_mode="sniff",
        ros_impl="none",
        notes=(
            "ROS1 环境下 ros_bridge_node(ROS2) 不可用，数据源强制走 sniff 旁路抓包；"
            "话题/节点发现改用 rostopic / rosnode。"
        ),
    ),
    RosVersion.ROS2: RosProfile(
        version=RosVersion.ROS2,
        label="ROS2 (ros2 CLI / rclpy)",
        distros=("dashing", "eloquent", "foxy", "galactic", "humble", "iron", "jazz", "rolling"),
        topic_list_cmd=["ros2", "topic", "list"],
        node_list_cmd=["ros2", "node", "list"],
        topic_hz_cmd=["ros2", "topic", "hz", "{topic}"],
        process_patterns=(
            "jetson2motion", "jetson2app", "sensor_checker", "ros2",
        ),
        resource_cmd=["ps", "-o", "pid,pcpu,pmem,rss,etime,comm", "-p", "{pid}"],
        data_source_mode="ros",
        ros_impl="bridge",
        notes=(
            "ROS2 环境可用 ros_bridge_node(43900) 或内嵌 rclpy 订阅；"
            "话题/节点发现用 ros2 CLI。"
        ),
    ),
}


def get_profile(version: RosVersion) -> RosProfile:
    """按版本取方案；版本不受支持时抛 KeyError（由 ros_switch 转成明确错误）。"""
    return PROFILES[version]


def supported_versions() -> List[str]:
    return [v.value for v in PROFILES]
