# Docker + ROS 1 学习导航

这组笔记面向希望在 Windows 上借助 Docker Desktop 学习 Ubuntu 20.04、ROS 1 Noetic、RViz 和 Gazebo 的初学者。原先集中在一个长文中的内容现已按主题拆分；本文件保留为稳定入口，便于从旧链接进入。

> 定位：这套组合适合建立可删除、可重建的 ROS 1 教学实验室。涉及高负载 3D、复杂 USB 设备、实时控制或长期项目时，应逐步迁移到 WSLg 或原生 Linux。

## 先读结论

- `turtlesim`、`rqt_graph`：非常适合在 Docker + X Server 中学习。
- RViz：适合 TF、URDF、地图和基础传感器数据练习；大点云可能受图形链路影响。
- Gazebo：可以用于理解 ROS 1 经典仿真架构，但 GUI 性能不代表原生 Linux 的性能上限。
- 真实机器人：接入 LiDAR、IMU、相机、串口、CAN 或多机网络后，原生 Linux 通常更省事。
- Docker 的价值不会因迁移而消失；长期目标是从 Windows Docker Desktop 迁移到 Linux-native Docker，而不是放弃容器。

## 分支文档

| 顺序 | 主题 | 学完后的结果 |
|---:|---|---|
| 1 | [环境选择与整体架构](docker-ros1/01-环境选择与整体架构.md) | 能区分容器、WSL2、Windows 与显示链路的问题 |
| 2 | [安装与可复现配置](docker-ros1/02-安装与可复现配置.md) | 能获得 ROS Noetic 环境并完成最小验证 |
| 3 | [Docker 开发工作流](docker-ros1/03-Docker开发工作流.md) | 能持久化源码并通过 Dockerfile/Compose 重建环境 |
| 4 | [ROS 1 基础与实践](docker-ros1/04-ROS1基础与实践.md) | 能独立编写、运行和诊断基础 ROS 节点 |
| 5 | [GUI、RViz 与 Gazebo](docker-ros1/05-GUI-RViz与Gazebo.md) | 能验证 X11/OpenGL 并理解可视化和仿真边界 |
| 6 | [网络、多容器与硬件](docker-ros1/06-网络多容器与硬件.md) | 能为不同部署场景选择正确网络和设备方案 |
| 7 | [故障排查手册](docker-ros1/07-故障排查手册.md) | 能按层排查，而不是随机修改环境变量 |
| 8 | [迁移与进阶路线](docker-ros1/08-迁移与进阶路线.md) | 能判断何时以及如何迁移到长期技术栈 |

## 建议进度

按每天 1.5～2 小时、每周约 5 天估算：

| 阶段 | 重点 | 参考时间 |
|---|---|---:|
| 环境验证 | Docker、X11、OpenGL、turtlesim | 0.5～1 天 |
| ROS 核心机制 | node、topic、message、service、parameter | 3～5 天 |
| ROS 编程 | rospy、roscpp、catkin、launch | 1～2 周 |
| TF/URDF/RViz | 坐标系、机器人模型和数据可视化 | 1～2 周 |
| Gazebo | physics、sensor、plugin、gazebo_ros | 1～2 周 |
| SLAM/Navigation | scan、odom、map、move_base | 2～3 周 |
| 真实硬件与 ROS 2 | 驱动、多机网络与概念迁移 | 按项目推进 |

## 每阶段的通过标准

- 环境：`xeyes`、`glxinfo -B`、`roscore` 和 `turtlesim` 依次成功。
- ROS 基础：能解释节点如何通过 Master 发现彼此，并用 `rosnode`、`rostopic`、`rqt_graph` 定位问题。
- 编程：给定消息类型后，能独立写 publisher/subscriber，并用 launch 文件管理节点和参数。
- 可视化：能解释 `map → odom → base_link → sensor_link`，并处理 RViz 的 `No transform`。
- 仿真：能区分 `gzserver` 的物理仿真问题和 `gzclient` 的图形问题。
- 真实项目：能说明 `/scan`、`/odom`、TF、地图、规划器和 `/cmd_vel` 的数据来源与去向。

返回：[初学者笔记总览](README.md)

