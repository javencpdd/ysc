# 02 · GPU 与计算平台分析

> 结论先行：**有 GPU，但是处理器内置的集成 GPU；无独立显卡、无 NPU。** 官方文档从未公布 GPU 型号，本文以 SSH 实测钉死。

## 一、官方口径（文档层）

| 来源 | 原文 |
|---|---|
| 产品手册 V1.1.0 | "内部搭载 3 台工业级高性能主机，用于运动控制和环境感知计算以及建图导航等"（无型号） |
| 官方宣传册 | "M20 Pro：八核 64 位工业级处理器 ×3（16GB+128GB）"（无 GPU/算力字段） |
| 官网 lynx 页 | 算力配置同上，无 GPU 字段 |
| 钉钉开发知识库（5 份） | 只有三主机架构与 IP，无 GPU/NPU 信息 |

## 二、实测钉死（SSH 巡检，详见报告 03）

| 证据 | 实测值 | 判读 |
|---|---|---|
| `/proc/device-tree/model` | `RK3588 YSC(Linux)` | 平台 = RK3588（云深处定制板 YSC） |
| `/dev/mali0` + `/sys/class/misc/mali0` | 存在 | Mali GPU 在线 |
| mali uevent `OF_COMPATIBLE` | `arm,mali-bifrost` | Bifrost/Valhall 系 |
| dmesg `mali fb000000.gpu` | `Kernel DDK version g18p0-01eac0` | **g18p0 DDK = Mali-G610 MP4** |
| devfreq 频率档 | 300/400/500/600/700/800/900/1000 MHz，当前 300MHz（simple_ondemand） | 8 档 DVFS |
| `/dev/rknpu`、misc npu 节点 | **三主机均未见** | RK3588 的 6TOPS NPU **未启用** |
| `/dev/mpp_service` + `/dev/rga` | 存在 | 硬件视频编解码 + 2D 加速可用 |

**最终判定：每台主机 1 颗 Mali-G610 MP4**（ARM Valhall 架构，OpenGL ES 3.2 / Vulkan 1.2 / OpenCL 2.0）。

## 三、架构与性能定位

- **架构**：ARM big.LITTLE —— 4×Cortex-A76（part 0xd0b，最高 2352MHz）+ 4×Cortex-A55（0xd05）；GPU 为 Mali-G610 MP4（移动级，GFLOPS 在 10² 量级）。
- **为什么没有独显**：IP66 全密封、-20~55℃ 宽温、整机 35kg/电池约 324Wh、对外供电总 360W——物理上不支持独显的功耗与散热。
- **定位**：中低端图形 + 实时感知平台，服务 SLAM 建图、全向避障、点云环视、ROS2 生态；**不是** AI 训练/重度 3D 渲染平台。云深处用"三主机分工"（AOS 运控 / NOS 感知 / GOS 开发+对外服务）替代单颗大算力芯片。
- **注意**：lscpu 在 RK BSP 上会把 8 核全误显为 A55，真实大小核以 `/proc/cpuinfo` 的 CPU part 为准（0xd0b=A76、0xd05=A55）。

## 四、实际场景表现与影响

| 场景 | 表现 | 建议 |
|---|---|---|
| 建图导航 + RViz | Mali-G610 MP4 驱动 50m×50m 点云/栅格 + RViz 无压力 | 大场景用 `drmap mapping -s` 关 RViz，事后回放 |
| VNC 远程桌面 | 可用的软抓屏桌面，帧率/分辨率有限 | 调试排障用，别当图形工作站 |
| 点云环视 | 实时渲染两路 96 线点云，低刷新可跑 | OTA 功能，官方标注后续升级 |
| RTSP 视频流 | 相机侧编码、GOS 转发，不吃 GPU；重编码走 MPP 硬编 | 接入 MediaMTX/SRS 链路时优先 `mpph264enc` |
| 二次开发 AI 推理 | Mali 只有 OpenCL（无 CUDA）、NPU 未启用 | 重模型外接算力盒（背部 5 网口 + 24V≤250W 供电） |

## 五、复现实测命令（经 m20ssh）

```bash
m20ssh gos 'cat /proc/device-tree/model; ls /dev/dri /dev/mali0 /dev/mpp_service'
m20ssh gos 'dmesg | grep -i mali | head -3'
m20ssh gos 'cat /sys/class/misc/mali0/device/devfreq/*/available_frequencies'
m20ssh gos 'grep "CPU part" /proc/cpuinfo | sort | uniq -c'
```
