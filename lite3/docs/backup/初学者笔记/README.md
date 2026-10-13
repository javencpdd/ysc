# 初学者笔记总览

本目录用于整理 Docker、Ubuntu、ROS 1 与机器人可视化的入门笔记。内容采用“总览—专题—操作清单”的结构：先确定学习路线，再按需进入具体主题，避免把安装、概念、实验和排错混在一篇长文中。

## 推荐学习路线

```text
环境确认
  ↓
Docker 与 ROS Noetic 安装
  ↓
容器、挂载与工作空间
  ↓
ROS 节点、话题、服务和参数
  ↓
TF、URDF 与 RViz
  ↓
Gazebo、SLAM 与 Navigation
  ↓
多容器、局域网与真实硬件
  ↓
迁移到 Linux 原生环境和 ROS 2
```

建议先在 Windows + Docker Desktop 中完成 ROS 1 基础和轻量可视化实验；当项目开始频繁使用 Gazebo、大规模点云、USB 设备或局域网多机通信时，再迁移到 WSLg 或原生 Ubuntu。

## 文档入口

- [Docker + ROS 1 学习导航](docker+ros1学习.md)：专题简介、学习计划和全部分支入口。
- [环境选择与整体架构](docker-ros1/01-环境选择与整体架构.md)：理解 Windows、WSL2、Docker、X Server 和 ROS 的边界。
- [安装与可复现配置](docker-ros1/02-安装与可复现配置.md)：准备环境、获取 ROS、验证安装并固定镜像。
- [Docker 开发工作流](docker-ros1/03-Docker开发工作流.md)：容器启动、目录挂载、Dockerfile 和 Compose。
- [ROS 1 基础与实践](docker-ros1/04-ROS1基础与实践.md)：ROS Graph、catkin、turtlesim、TF、URDF 和进阶练习。
- [GUI、RViz 与 Gazebo](docker-ros1/05-GUI-RViz与Gazebo.md)：X11、OpenGL、图形工具和仿真性能。
- [网络、多容器与硬件](docker-ros1/06-网络多容器与硬件.md)：ROS 网络、GPU、USB、串口和真实机器人。
- [故障排查手册](docker-ros1/07-故障排查手册.md)：按层定位 Docker、GUI、ROS、网络和设备问题。
- [迁移与进阶路线](docker-ros1/08-迁移与进阶路线.md)：判断何时切换 WSLg、原生 Linux 或 ROS 2。

## 使用原则

1. 先运行最小示例，再增加功能；不要同时排查 Docker、X11、ROS 网络和 Gazebo。
2. 源码和配置放在宿主机并纳入 Git，容器用于提供可重建的运行环境。
3. ROS Noetic、Ubuntu 20.04 与 Gazebo Classic 11 应视为遗留学习栈；不要把它直接当作长期联网生产环境。
4. 命令需要在标注的终端中执行。PowerShell 与 Ubuntu Bash 的续行符、路径和环境变量语法不同。

