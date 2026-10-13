# 103 感知导航主机

本目录保存 `ysc-f20-103`（实际 hostname 为 `lite`）的 `/home/ysc` 审计报告。该机承担 ROS 感知、定位、建图、导航与传输侧职责；跨主机配置基线见 [`../../operations/host-maintenance.md`](../../operations/host-maintenance.md)。

103 上建立的功能复现代码已单独整理为 `/home/jack/lite3Code`（[仓库](https://github.com/javencpdd/lite3Code)）。本目录是主机审计，不是该代码库的部署入口；YOLO、监控面板、SCAN-Planner 等模块的当前脚本请按 [两库协作索引](../../codebase-map.md)定位。

## 专题目录

新增：[lite_cog_ros2 源码导读](lite_cog_ros2/README.md)（2026-09-16）。包含全部 12 个一级目录的独立笔记、50 份功能包清单及源码采集索引；保留本目录原有专题作为历史资料。旧报告中的 `lite3-f20-1-103` 是历史别名；本机当前技能配置使用 `ysc-f20-103`，实际连接前仍需核对 [SSH 技能配置](../../../script/lite3-robot-ssh/config/hosts.conf) 和 `ssh -G` 解析结果。

| 目录 | 内容 | 使用方式 |
| --- | --- | --- |
| [`概览与环境/`](概览与环境/README.md) | 总体职责、ROS 环境、网络与服务切换 | 首次了解主机或切换 ROS 版本前阅读。 |
| [`ROS1软件栈/`](ROS1软件栈/README.md) | ROS 1 传感器、导航、建图、传输、避障与跟踪 | 维护 Noetic 工作区或旧版启动链时阅读。 |
| [`ROS2软件栈/`](ROS2软件栈/README.md) | ROS 2 传感器、导航、地图、传输、避障与跟踪 | 维护当前 Foxy/Transfer 链时优先阅读。 |
| [`第三方依赖与构建产物/`](第三方依赖与构建产物/README.md) | SDK、上游组件、构建与运行时目录边界 | 升级、构建或清理依赖前阅读。 |

## 使用方式

1. 先阅读“概览与环境”确认当前 ROS 模式、服务与网络地址；
2. 再按 ROS 1 或 ROS 2 选择对应专题，避免混用两套 shell 环境和服务；
3. 涉及地图、VOA、Transfer、视觉跟踪或硬件驱动时，先核验脚本中的硬编码路径、IP 和传感器话题。
