# m20Pro — 山猫 M20 Pro 资料与调研库

> 云深处（DEEP Robotics）山猫 M20 Pro 四轮足机器人调研成果归档。
> 覆盖：官方文档 → 钉钉开发文档 → GPU/硬件巡检 → RTSP/RTMP 推流链路与协议逆向 → 官方开源仓库（模型/RL 训练/导航栈/SDK）→ 部署路线选型。
> 上层工作区总索引见 `../README.md`。

## 目录结构

```
m20Pro/
├── README.md            ← 本文件（总索引）
├── docs/                官方文档资料（9 个文件）
├── images/              关键页截图（12 张）
├── scripts/             跳板工具、巡检脚本与现场核查脚本（13 个跟踪文件；真实配置 m20ssh.conf 已 gitignore）
├── analysis/            分析报告（5 份）+ AI 服务调研原始数据
├── models/              官方机器人模型 M20/M20S 文本描述符（17 个文件）
├── rl-training/         Isaac Lab 强化学习训练工程（49 个文件）
├── nav-stack/           Odin-Nav-Stack ROS 1 导航栈参考实现（235 个文件）
├── sdk-deploy/          官方 SDK 部署源码（124 个文件）
├── m20Pro_robot_monitor/  M20 Pro Web 监控控制台（FastAPI + Vue3；部署于 AOS 196 /home/djw/monitor）
└── rtsp-rtmp/           196 主机流媒体链路工程资产（89 个文件）
```

## 各目录入口

| 目录 | 内容 | 入口 |
|---|---|---|
| `docs/` | 产品手册、钉钉开发文档全文、宣传册 + 部署路线选型 | 本文件「文件清单」 |
| `images/` | 产品手册/软件指南关键页截图 | 本文件「文件清单」 |
| `scripts/` | `m20ssh` 跳板工具与三主机巡检脚本 | `scripts/` 内说明 + 本文件「工具用法」 |
| `analysis/` | RTSP 能力、GPU、硬件巡检、AI 服务调研、整合评估 | 各报告首页 |
| `models/` | M20/M20S URDF/MJCF/USD（BSD-3） | [`models/README.md`](models/README.md) |
| `rl-training/` | rl_training（Isaac Lab 2.3.2 + RSL-RL） | [`rl-training/README.md`](rl-training/README.md) |
| `nav-stack/` | Odin-Nav-Stack（ROS 1 Noetic，参考） | [`nav-stack/README.md`](nav-stack/README.md) |
| `sdk-deploy/` | sdk_deploy（ROS 2 Sim-to-Real） | [`sdk-deploy/README.md`](sdk-deploy/README.md) |
| `m20Pro_robot_monitor/` | **Web 监控控制台**（状态监控 + 视频 + 分层控制；已部署 AOS 196） | [`m20Pro_robot_monitor/README.md`](m20Pro_robot_monitor/README.md) · [QUICKSTART](m20Pro_robot_monitor/QUICKSTART.md) · [docs/](m20Pro_robot_monitor/docs/architecture.md) |
| `rtsp-rtmp/` | 196 主机 RTSP/RTMP 全链路 + rtmp_1012 项目 | [`rtsp-rtmp/README.md`](rtsp-rtmp/README.md) |

## 文件清单（与实际存放一一对应）

### docs/ — 官方文档资料

| 文件 | 内容 | 来源 |
|---|---|---|
| `01-产品手册V1.1.0-全文提取.txt` | 产品手册全文（pdftotext -layout 提取，32 页） | `~/下载/山猫M20 Pro产品手册 V1.1.0.pdf` |
| `02-软件使用指南V1.0.2-钉钉全文.txt` | 开发指南-软件使用指南全文（含**附录1 RTSP 地址**） | 钉钉知识库，2026-06 版 V1.0.2 |
| `03-硬件参数V1.0.4-钉钉全文.txt` | 开发指南-硬件参数全文（网络架构图、接口定义） | 钉钉知识库 V1.0.4 |
| `04-软件开发指南V1.3.0-钉钉全文.txt` | 开发指南-软件开发指南全文（监控协议 + ROS2 话题） | 钉钉知识库 V1.3.0 |
| `05-山猫M20开发者文档-钉钉全文.txt` | 开发者文档（与软件指南内容重合，存档备查） | 钉钉知识库 |
| `06-二次开发教程与示例-钉钉全文.txt` | 二次开发教程（与软件指南内容重合，存档备查） | 钉钉知识库 |
| `07-M20官方宣传册.pdf` | 云深处官方 M20 系列宣传册（繁中） | deeprobotics.cn CDN |
| `07-M20官方宣传册-提取文本.txt` | 上述宣传册的文本提取（含规格对比表） | 本地提取 |
| `08-ROS2导航与强化学习部署路线.md` | **选型总纲**：Nav2+MPPI Omni 主链路、RL 链路隔离、组件表、阶段 0–6 学习路线 | 2026-07-29 整理，2026-10-14 入库 |

### images/ — 关键页截图（文本提取易漏图表，故留图备核）

| 文件 | 内容 |
|---|---|
| `产品手册-P1-产品概述.png` / `-P2-部件名称.png` | 三主机结构、部件位置 |
| `产品手册-P3-主要参数.png` / `-P4-传感器与环境参数.png` | 处理器"八核64位×3(16GB+128GB)"、通讯接口 Ethernet/WiFi/USB |
| `产品手册-P20-背部航插接口.png` | 7 个航插口定义（72V、网口1、网口2~5+24V、USB-C） |
| `软件指南-P10-连接与WiFi.png` | WiFi 热点 CA9B_NO.XXX_5G / 密码 12345678 |
| `软件指南-P11/P12/P13-控制界面.png` | 手柄 APP 界面（视频流切换、拍照、录屏） |
| `软件指南-P14-设置界面.png` | 传感器管理、辅助功能（WiFi 设置） |
| `软件指南-系统概况与网络架构.png` | AOS/NOS/GOS 三主机网络拓扑与 IP 分配 |
| `软件指南-远程登录与建图.png` | SSH/VNC 登录信息表、建图导航 |

### analysis/ — 分析报告

| 文件 | 内容 |
|---|---|
| `01-RTSP与推流能力分析.md` | 产品手册无 RTSP 章节；开发指南附录1 给出拉流地址；接入与推流落地建议 |
| `02-GPU与计算平台分析.md` | GPU 问题完整查证：集成 Mali-G610 MP4、无独显/NPU、架构与性能定位 |
| `03-三主机硬件巡检报告.md` | SSH 实测：三主机全部 RK3588 定制板的完整硬件数据 |
| `04-外部AI识别服务API调研.md` | 外部视觉能力中台（FastAPI/OpenAPI 3.1/122 路径）调研；支持 `ros://` 话题源；原始数据在 `ai-vision-api-raw/` |
| `05-M20-pro资料整合评估报告.md` | 2026-10-14 整合评估：筛选依据、脱敏清单、主机只读复核结论、遗留事项 |

## 核心结论速查

- **视频流**：前后广角相机 RTSP 拉流地址 `rtsp://10.21.31.103:8554/video1`（前）/ `video2`（后），由 GOS 提供（官方文档口径）。
  - 实测补充（2026-10-12/14，AOS `192.168.0.196` 现场）：本机 `~/rtmp_1012` 部署把相机流经本机 MediaMTX 在 `127.0.0.1:8554` 提供，并由 `rtmp_forward.sh` 转推外部 SRS `rtmp://172.31.68.227:1936/live/m20pro-f|b`；相机侧已改 H.264 硬编，中继退化为纯 remux（约 0.14 核）。详情见 `rtsp-rtmp/note/` 与 `rtsp-rtmp/README.md`。
- **计算平台**：三主机均为 RK3588（4×A76+4×A55，Mali-G610 MP4 GPU，16GB+128GB，Ubuntu 20.04 + kernel 5.10.198），无独显、无 NPU；`/dev/mpp_service` 硬编解码可用。
- **接入方式**：对外仅 AOS `192.168.0.196`（user / 公钥认证）；NOS `10.21.31.106`、GOS `10.21.31.104` 仅内网，经 AOS 跳板（用 `m20ssh`）。
- **GPS**：模块与串口正常，室内无定位解（需 ≥4 颗卫星；实测可见 5 颗仍不足）。获取途径与直连协议逆向见 `rtsp-rtmp/note/m20-GPS获取方式.md`。
- **部署选型**：主导航链路 = ROS 2 Jazzy + Nav2 + MPPI（Omni）+ `/NAV_CMD` 适配器；RL 训练（Isaac Lab）与真机部署（sdk_deploy）为后置独立链路，**禁止**把 Nav2 `/cmd_vel` 直接接 `/JOINTS_CMD`。见 `docs/08-ROS2导航与强化学习部署路线.md`。

## 工具用法

```bash
m20ssh <aos|nos|gos|IP> [命令...]   # 在目标执行命令；不带命令开交互 shell
echo cmd | m20ssh <目标>            # 将 stdin 当脚本在目标执行
m20ssh -f script.sh <目标>          # 将本地脚本文件送至目标执行
m20ssh --list                       # 列出目标
```

> 配置文件 `~/.config/m20pro/m20ssh.conf`（权限 600，含真实口令，**未入库**）；样例见 `scripts/m20ssh.conf.example`。

### scripts/ — 跳板工具与巡检脚本清单

| 文件 | 说明 |
|---|---|
| `m20ssh` | **跳板工具源码副本**。实际安装位置 `~/.local/bin/m20ssh`（在 PATH，直接敲 `m20ssh` 用） |
| `m20ssh.conf.example` | 配置样例（**密码已脱敏**）。实际生效配置在 `~/.config/m20pro/m20ssh.conf`（含真实密码，未入库，权限 600） |
| `lib/askpass.sh` | 免 pty 密码组件（SSH_ASKPASS） |
| `lib/aos_hw.sh` | AOS 全量硬件巡检脚本 |
| `lib/hw_all.sh` | 三主机通用精简巡检脚本 |
| `lib/remote_jump.sh` | AOS 上 askpass 中转方案（已被 sshpass 方案取代，存档） |
| `lib/diag.sh` | askpass 失效诊断脚本 |
| `lib/final_nos.sh` / `final_gos.sh` | NOS/GOS 巡检（sshpass + base64 方案） |
| `lib/final_gpu.sh` | GPU 细节专项巡检 |
| `lib/rtsp_dump.sh` / `rtsp_dump2.sh` / `rtsp_probe.sh` | RTSP 拉流探测与抓包 |

## 关联资产（不在本目录）

| 资产 | 位置 |
|---|---|
| Lite3 资料 | `../lite3/`（103 感知导航 / 120 运动控制主机文档；120 的 rtsp_stream 方案分析在 `../lite3/docs/hosts/120-运动控制主机/视频与流媒体/rtsp_stream/`） |
| 工作区记忆（逐日日志） | `../.workbuddy/memory/` |
| 可复用技能 | `~/.workbuddy/skills/`：`pdf-manual-analysis`、`dingtalk-knowledge-fetch`、`rk-robot-host-inspect` |
| 工具运行态 | `~/.local/bin/m20ssh` + `~/.config/m20pro/m20ssh.conf` |
| 原始 PDF 输入 | `~/下载/山猫M20 Pro产品手册 V1.1.0.pdf`（未移动） |
| 整合前的工作副本 | `Desktop/特种机器人/M20-pro/`（源目录，保留未删） |

## 维护约定

1. 本目录只收 M20 Pro 相关资料；Lite3 内容归同仓库子目录 `../lite3/`，不在此处重复归档（官方跨平台仓库 `sdk-deploy`、`rl-training` 刻意保持完整，Lite3 专属部分已在各自 README 标注）。
2. 新增文件后必须更新本清单与对应子目录 README，保持"文件 ↔ 索引"一致。
3. 密码/密钥一律脱敏：配置只提交 `*.example`，真实配置文件（含密码）禁止入库。
4. 第三方二进制与模型网格不入库，只在子目录 README 的"未入库内容"表中记录获取方式。
5. 主机状态类结论（服务起停、端口、GPS）均标注实测日期，引用前重新核验。
