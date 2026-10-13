# user-f20-103 / user-f20-120 主机维护说明

## 1. 概述、依据与边界

两台主机处于同一 `192.168.1.0/24` 业务网段，角色互补：

- `user-f20-103`（实际主机名 `lite`）是 NVIDIA L4T/Jetson 平台上的 ROS 感知、定位、导航和传输侧；当前实际运行 ROS 2 Transfer。
- `user-f20-120`（实际主机名 `ysc`）是 Rockchip RK3588 平台上的 Lite3 运动控制、相机流与视觉跟随侧；当前实际运行 `jy_exe`、`rtsp_stream` 和 `track`。

| 信息来源 | 范围与使用方式 |
| --- | --- |
| 本次实测 | 2026-09-07 通过 MCP 在两机读取 `hostnamectl`、`lscpu`、`free`、`lsblk`、`findmnt`、`ip`、`systemctl`、进程、监听端口、软件路径和包清单。现状类结论均以此为准。 |
| [`103 感知导航主机文档`](../hosts/103-感知导航主机/README.md) | 103 的 ROS 1/ROS 2 工作区、启动脚本、地图、传感器和风险分析。实测已确认其当前 ROS 2 Transfer 服务、目录和网络地址。 |
| [`120 运动控制主机文档`](../hosts/120-运动控制主机/README.md) | 120 的运动控制、热点、RTSP、跟随、SDK、账户及底层部署分析。实测已确认其板型、地址、活动服务、进程和关键监听端口。 |

未修改远端文件、服务、网络或机器人控制状态。未抓取业务 UDP/RTP 报文，因此“端口和配置一致”不等同于“端到端业务已成功验证”。密码、Wi-Fi 密钥、客户端信息等敏感值不在本文记录。

## 2. user-f20-103：配置清单

### 2.1 基础硬件与存储

| 项目 | 实测结果 |
| --- | --- |
| 实际主机名 / 连接地址 | `lite`；`192.168.1.103`（`eth0`） |
| 操作系统 | Ubuntu 20.04.6 LTS，`aarch64` |
| 内核 | `5.10.120-tegra`，`#5 SMP PREEMPT Tue Sep 26 13:34:25 CST 2023` |
| 平台证据 | `/etc/nv_tegra_release` 为 L4T `R35`、revision `4.1`、board `t186ref`。未采集到可据此无歧义确认的商业 Jetson 模块型号。 |
| CPU | 6 个在线 ARMv8 核（0–5）；`lscpu` 报告 NVIDIA vendor，最大 1907.2 MHz、最小 115.2 MHz。 |
| 内存 / Swap | 6.7 GiB；采集时 1.1 GiB 已用、5.4 GiB 可用。zram swap 共 3.3 GiB，采集时未使用。 |
| 系统盘 | `/dev/mmcblk1` 119.1 GiB；根分区 `/dev/mmcblk1p1` ext4，116.5 GiB，已用 75.4 GiB（65%），可用 36.2 GiB。 |
| 其他块设备 | 另有 `/dev/mmcblk0` 14.7 GiB 的多分区设备；本次未见其分区挂载为业务文件系统。 |

### 2.2 网络

| 项目 | 实测结果 |
| --- | --- |
| 有线业务网 | `eth0` 为 UP，`192.168.1.103/24`；有 link-local IPv6。 |
| 容器网桥 | `docker0` 为 DOWN，地址 `172.17.0.1/16`。 |
| 路由 | 仅见 `192.168.1.0/24`、`172.17.0.0/16` 和 `169.254.0.0/16` 路由；**采集时未见 IPv4 默认路由**。 |
| DNS | `systemd-resolved` 显示 DNS 服务器 `223.5.5.5`、`119.29.29.29`。 |

### 2.3 关键服务和组件

| 分类 | 实测结果与说明 |
| --- | --- |
| 当前机器人服务 | `transfer_ros2.service` 已启用且 active；入口为 `/home/ysc/lite_cog_ros2/system/scripts/transfer/start_transfer.sh`。运行进程为 `ros2 launch transfer transfer_launch.py`，并包含 `jetson2app`、`jetson2motion`、`sensor_checker`。 |
| 未启用的机器人入口 | `transfer.service`（ROS 1）、`nav.service`、`track.service`、`voa.service`、`voa_ros2.service` 均 loaded 但 disabled/inactive。 |
| ROS 环境 | `/opt/ros/foxy` 和 `/opt/ros/noetic` 均存在；`~/.ros_version.sh` 当前 source Foxy，设置 `ROS_DOMAIN_ID=0`、Cyclone DDS 与 ROS 2 日志目录。此次非交互 MCP shell 未 source 该文件，因此 `ros2`/`roslaunch` 不在该 shell 的 `PATH`；这不能解释为 ROS 未安装。 |
| 已见基础组件 | Docker、containerd、SSH、NetworkManager、NoMachine、NVIDIA Argus 与风扇服务均 active；`docker.service` 已启用。`ros-foxy`、Nav2、PCL、OctoMap 等包存在于 dpkg 清单。 |
| 容器状态 | 以 `ysc` 执行 `docker ps` 未能获得容器列表（命令返回不可用/无权限结果）；本文不臆测容器数量或运行负载。 |
| 监听证据 | UDP `43897`、`43899` 及 ROS 2 DDS 常用 UDP `7400/7401` 正在监听；TCP SSH `22` 正在监听。 |

### 2.4 用途与笔记互证

103 感知导航主机文档显示该机维护 ROS 1 Noetic 与 ROS 2 Foxy 两套工作区；包括激光雷达/相机驱动、Faster-LIO、HDL localization、Nav2、地图、VOA 和视觉跟踪集成。实测的 ROS 2 Transfer 服务和 Foxy 环境与该记录一致，故当前可定位为**感知/导航侧，运行模式为 ROS 2 Transfer**。

笔记同时记录 Transfer 将运动命令发往 `192.168.1.120:43893`，并使用本地 `43897` 接收状态；本次实测的地址和 UDP `43897` 监听与之相符。地图、点云、传感器和导航服务当前并未由 systemd 自动启动，需按对应脚本手工 bring-up。

## 3. user-f20-120：配置清单

### 3.1 基础硬件与存储

| 项目 | 实测结果 |
| --- | --- |
| 实际主机名 / 连接地址 | `ysc`；业务网地址 `192.168.1.120`（`eth1`） |
| 操作系统 | Ubuntu 20.04.5 LTS，`aarch64` |
| 内核 | `5.10.198`，`#45 SMP Thu Aug 15 15:31:26 CST 2024` |
| 板型 | 设备树：`Rockchip RK3588 WEB-S3588-YSC-V10`。 |
| CPU | 8 个在线核（0–7）；`lscpu` 报告 Cortex-A55、最大 2208 MHz、最小 1200 MHz。 |
| 内存 / Swap | 3.8 GiB；采集时 707 MiB 已用、3.0 GiB 可用；未配置 swap。 |
| 系统盘 | `/dev/mmcblk0` 29.1 GiB；根分区 `/dev/mmcblk0p8` ext4，27.9 GiB，已用 11.2 GiB（40%），可用 15.5 GiB。 |
| 其他挂载 | `/dev/mmcblk0p6` 挂载 `/oem`（242.3 MiB，12% 已用）；`/dev/mmcblk0p7` 挂载 `/userdata`（502 MiB，近乎未用）。 |

### 3.2 网络

| 接口 / 项目 | 实测结果 |
| --- | --- |
| `eth1` | UP；`192.168.1.120/24` 和 `192.168.137.120/24`。这是与 103 相连的业务网接口。 |
| `wlan0` | UP；`192.168.0.197/24`。采集时默认路由为 `192.168.0.1`，metric `601`；DNS 也为 `192.168.0.1`。 |
| `p2p0` | UP；`192.168.2.1/24`。监听中可见该地址的 DHCP（UDP 67）和 DNS（TCP/UDP 53）端口。结合[网络与无线热点分析](../hosts/120-运动控制主机/网络与连接/网络与无线热点分析.md)，它是 NetworkManager shared/NAT 热点接口。 |
| 其他网络 | `eth0` DOWN；`can0`–`can3` UP、`can4` DOWN；存在 `192.168.2.0/24`、`192.168.137.0/24` 路由。 |
| 热点历史记录差异 | 笔记中 2026-09-05 的 DHCP 默认路由 metric 为 `600`；本次为 `601`，以本次实测为当前值。热点 profile、SSID 与密钥没有在本文复写。 |

### 3.3 关键服务和组件

| 分类 | 实测结果与说明 |
| --- | --- |
| 核心运动控制 | `jy_exe.service` enabled/active，入口 `/home/ysc/jy_exe/run.sh`；其下实际运行 `catchsegv /home/ysc/jy_exe/bin/jy_exe`。该链路以 root 运行。 |
| 视频与跟随 | `rtsp_stream.service`、`track.service` 均 enabled/active。RTSP 入口为 `/home/ysc/rtsp_stream/start_stream.sh`；实测 `mediamtx` 和从 `/dev/video0` 推送 `rtsp://127.0.0.1:8554/test` 的 GStreamer 进程正在运行。 |
| 失败服务 | `jy_rl.service`、`lora.service` 都已启用但当前为 failed；其 `ExecStart` 分别指向缺失路径 `/home/ysc/rl/bin/run_rl.sh`、`/home/ysc/lora/start_lora.sh`。 |
| 备用网络/视频服务 | `host.service` enabled 但 inactive；`wifi.service`、`multi_master.service`、`streaming.service` disabled/inactive。笔记说明 `host.service` 为一次性热点引导，inactive 本身不能据此断言热点已关闭。 |
| 已见基础组件 | SSH、NetworkManager、WPA supplicant、Bluetooth、NoMachine、ADB、RPC bind 均 active。dpkg 清单包含 GStreamer（含 Rockchip 插件）、OpenCV 4.2、hostapd、dnsmasq-base、OpenSSH。未见 ROS 安装目录。 |
| Docker | 本次 shell 中未找到 `docker`、`docker-compose` 或 `podman` 命令，且过滤后的 dpkg 清单没有 Docker 包；不将 Docker 视为本机已验证组件。 |
| Codex 远端支持 | 在显式补足用户级 PATH 后，实测 Node `v22.23.2`、npm `10.9.8`、Codex CLI `0.153.4` 可用；常规非交互 shell 未自动加入该 PATH。 |
| 监听证据 | UDP `43893`、`43899`、`43901` 正在监听；RTSP TCP `8554`、RTMP `1935`、HLS `8888`、WebRTC `8889`、SRT UDP `8890` 和 SSH `22` 正在监听。 |

### 3.4 用途与笔记互证

120 运动控制主机文档将 `/home/ysc` 定位为 Lite3 运动主机部署根：`jy_exe` 提供厂商闭源运动控制，`rtsp_stream` 发布相机流，`track` 使用该流进行视觉跟随。上述三项服务、进程和端口均在本次实测中存在，故当前可定位为**运动控制、视频发布和视觉跟随侧**。

笔记中的 `jy_exe/conf/network.toml` 记录上位/感知侧为 `192.168.1.103`、目标端口 `43897`、本地端口 `43893`。本次实测 120 的地址为 `192.168.1.120` 且监听 `43893`，103 则监听 `43897`，配置和监听关系一致；未抓取报文，不能据此替代通信健康检查。

## 4. 配置与用途对比

| 维度 | user-f20-103（实际 `lite`） | user-f20-120（实际 `ysc`） |
| --- | --- | --- |
| 平台 | NVIDIA L4T R35.4.1 / 6 核 ARMv8 | Rockchip RK3588 / 8 核 Cortex-A55 |
| 内存与根盘 | 6.7 GiB；116.5 GiB 根分区，65% 已用 | 3.8 GiB；27.9 GiB 根分区，40% 已用 |
| 运行重心 | ROS 双栈资产；当前 ROS 2 Transfer、传感器/定位/导航集成 | Lite3 闭源运动控制、CAN 相关环境、视频发布、视觉跟随和热点 |
| 业务网 | `eth0: 192.168.1.103/24`；采集时无默认路由 | `eth1: 192.168.1.120/24`；另有 Wi-Fi 上行和热点网段 |
| 控制接口 | Transfer 本地接收状态并向 120 侧桥接速度/状态 | `jy_exe` 监听 `43893`；按配置向 103 的 `43897` 回传状态 |
| 视频接口 | 笔记中的跟踪脚本使用 `rtsp://192.168.1.120:8554/test` | MediaMTX 监听 `:8554`，本机摄像头推送 `/test` |
| 容器 / ROS | Docker 与 ROS Foxy/Noetic 已验证存在 | Docker 和 ROS 未验证存在；GStreamer、OpenCV、Rockchip 插件已验证 |

可据配置和当前监听关系得到下列维护视图：

```text
103：传感器 / ROS 2 Transfer / 定位导航资产
  ├─ 运动或状态接口：192.168.1.103:43897  <->  120:43893
  └─ 视觉侧配置拉流：rtsp://192.168.1.120:8554/test

120：jy_exe（运动控制） + RTSP 相机流 + track（视觉跟随）
```

箭头表示笔记中配置的目标关系及实测监听端口相互匹配，不代表本次已验证 ROS 话题、UDP 协议内容、控制指令或视频客户端健康。

## 5. 差异说明与已知问题

1. **主机别名与实际名称不一致。**用户给出的 `user-f20-103/120` 在 MCP 中不存在；连接应使用现有 `ysc-f20-103/120`，并以 IP 与实际 hostname 二次确认，避免误操作。
2. **计算平台和软件栈不同。**103 的 Tegra/ROS 环境不能直接复制到 RK3588/120；120 的 Rockchip MPP、RKNN、EtherCAT/CAN 相关制品也不应直接迁移到 103。
3. **103 的默认路由缺失。**采集时它没有 IPv4 default route；即使 `192.168.1.120` 可在同网段访问，访问外网、跨网段服务或依赖外部 DNS 的功能仍可能失败。须在变更前确认这是预期隔离还是配置缺失。
4. **120 的热点是 NetworkManager shared/NAT 设计。**`p2p0` 是热点侧、`wlan0` 是当前默认上行；`hostapd.service` 和系统级 `dnsmasq.service` 不应与其并行启动。笔记指出旧脚本会重建同名热点 profile、追加 NAT 规则，可能造成客户端掉线或规则重复。
5. **120 有两个已启用失败服务。**`jy_rl.service`、`lora.service` 的入口路径缺失。未明确其业务用途及正确制品前，不应盲目重启、补建空路径或删除单元。
6. **103 的自动化范围有限。**当前仅 ROS 2 Transfer 自动运行；导航、建图、传感器与 VOA 需要按依赖顺序启动。`track.service` 记录为指向缺失的 ROS 1 脚本，不能作为可用跟随启动入口。
7. **地图与地址被硬编码。**103 笔记中 ROS 工作区、地图 `lite3.yaml`/`lite3.pcd`、IP `192.168.1.103/120` 和 UDP 端口有多处固定引用；更新地图、迁移工作区或改变地址必须同步审计两端。

## 6. 常见问题与操作注意事项

| 场景 | 应做事项 | 不应做事项 |
| --- | --- | --- |
| 远程连接 | 先核对 MCP 别名、目标 IP、远端 hostname 与当前业务接口。 | 不要因名称相近直接在 `user-f20-*` 上假定已连接到正确主机。 |
| 机器人服务变更 | 先记录 `systemctl status`、`ip route`、端口监听和当前配置，再在维护窗口操作；现场保留急停/本地控制能力。 | 不要将 MotionSDK 示例、`jy_exe` 恢复脚本、CAN 电机脚本当作无副作用的测试工具。 |
| 120 网络/热点 | 修改前备份 NetworkManager profile、路由和 iptables；准备串口或本地回退路径；变更后验证 p2p0 DHCP/DNS 与 wlan0 默认路由。 | 不要 flush 防火墙、关闭 `ip_forward`、把 `p2p0` 改为普通 Wi-Fi 客户端、建立 bridge，或并行启用 hostapd/dnsmasq。 |
| 103 ROS 操作 | 先确认当前是 Foxy/ROS 2 环境和 `transfer_ros2.service` 状态；启动导航前核对传感器、地图、TF、DDS 环境。 | 不要因 MCP 非交互 shell 找不到 `ros2` 就认为 ROS 未安装，也不要混用 ROS 1/ROS 2 shell。 |
| 地图更新 | 成对保存并版本化 YAML/PGM 与 PCD，记录采集日期和适用机器。 | 不要直接运行会覆盖/删除既有 `lite3` 地图文件的脚本而不备份。 |
| 120 运动部署 | 正常启停优先使用已验证的 `jy_exe.service` 及其日志链；调整策略、算法、CPU/IRQ、EtherCAT/CAN 前取得厂商确认。 | 不要直接执行 `module/deploy.sh`（会写 boot 分区）、`disable_motor.sh`、`recovery.sh`、`runrpc.sh` 或旧 `push.service` 模板。 |
| 视频服务 | 先检查 `/dev/video0`、MediaMTX、GStreamer 和端口占用；将 `rtsp_stream.service` 状态与实际推流进程一并核对。 | 不要同时启用备用 `.zetton` 流媒体链和当前 `rtsp_stream`，以免争用摄像头或端口。 |
| 存储维护 | 103 根盘已用 65%，清理前先确认 ROS 构建产物、地图、日志和容器用途。 | 不要因目录名相似删除 120 的 `/home/user` 与 `/home/ysc` 副本；笔记证实它们不是实时同步目录。 |

## 7. 后续复核建议

- 服务异常时，先分别保存两机的 `systemctl --failed`、`journalctl -u <unit>`、`ip route`、`ss -lntup` 和磁盘占用，再做一次变更。
- 要验证 103↔120 的实际控制链，应在安全维护环境中做只读/非执行器测试：抓取或记录 UDP `43893/43897` 双向流量，并核对 103 ROS 节点、120 `jy_exe` 日志和传感器健康状态；不得通过发送运动控制包探测。
- 要验证 120 视频链，应先以不影响现有生产消费者的方式检查 MediaMTX 日志和单独健康指标；当前服务未启用 API/metrics 的情况需按配置另行确认。
