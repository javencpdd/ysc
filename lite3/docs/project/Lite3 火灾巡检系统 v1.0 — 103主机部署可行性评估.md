# Lite3 火灾巡检系统 v1.0：103 主机部署可行性评估

评估时间：2026-09-16（远端系统时钟显示 2026-09-15）。评估对象：SSH 别名 lite3-f20-1-103，ysc@192.168.1.103，远端 hostname 为 lite。状态：**基础平台有条件可用；完整 v1.0 仍不可直接上线**。

## 1. 结论摘要

已完整读取[工程实施计划](Lite3%20火灾巡检系统%20v1.0%20工程实施计划.md)18 个章节，并通过 mcp-ssh-apply-patch 对远端完成只读采集。计划要求在 103 上运行无头 ROS2 Foxy、Nav2 巡检、VOA 安全层、RTSP/YOLO 火焰检测、事件管理和数据取证；120 提供摄像头 RTSP、语音与运动执行；控制笔记本运行 Foxglove Studio。

计划文件 SHA-256：3C3EB139BE93FDFA579447C87A169B29720C6C4F71AD31B722B784F083773FB3。

关键判断：

- 主机硬件足以作为 ROS2 感知/导航和 TensorRT 推理节点：Jetson Xavier NX、aarch64、6 个在线 CPU、6.7 GiB 内存，当前可用内存约 4.8 GiB；根分区剩余约 34 GiB。
- 103→120 网络基础可用：同一 192.168.1.0/24，ping 0% 丢包、平均 0.665 ms；TCP 22 与 8554 可连通。运动端口 43893 是 UDP，不能以 TCP 探测失败判定 UDP 不通。
- 当前长期服务只有 transfer_ros2.service，已 enabled/active 且默认以 root 运行；实时 ROS 图只有 app_receiver、motion_receiver、motion_sender、sensor_checker。Nav2、VOA、RealSense、Foxglove bridge/rosbridge 均没有运行。
- 用户补充的 /home/test/foxglove 确实存在，但仅包含 foxglove_ws 的 COLCON_IGNORE/空安装骨架和一个指向 rosbridge_server 的 readme，没有 package.xml 或 bridge 可执行文件；source 该工作区不会提供新包。系统 /opt/ros/foxy 中存在 rosbridge_server、rosapi 和 rosbridge_library，可作为替代 WebSocket bridge。foxglove_bridge 与 vision_msgs 仍未找到；Python ultralytics 未安装。TensorRT、CUDA、GStreamer/NVIDIA 解码插件存在，但火焰模型和新增节点尚不存在。
- 现有地图目录只有 lite3.yaml，没有其引用的 lite3.pgm 或定位所需的 lite3.pcd；pipeline/src/data 为空。固定路线不能直接执行。
- 当前 transfer 已发布 /imu/data 与 /leg_odom2，但 /rslidar_points、/camera/depth/color/points 没有发布者；/cmd_vel 和 /cmd_vel_corrected 也没有发布者。感知/导航闭环尚未运行。
- 计划 F7 要求 VOA 为最终速度安全层，但现有 transfer 同时订阅原始与修正速度，pipeline/track 还存在直接控制旁路；必须先整改安全链。

本文件只做检查与分析，没有安装软件、修改远端配置、重启服务、发运动命令或启动相机/导航。历史源码结论与实时采集结果分开标记。

## 2. 工程计划要求梳理

### 2.1 软件目录与主机分工

计划建议在 /home/ysc/lite_cog_ros2 下扩展 fire_detector、patrol_manager、fire_event_manager、safe_cmd_mux、lite3_interfaces，并增加 ops/launch、ops/config、ops/systemd、ops/scripts。

计划闭环为：

    RTSP → GStreamer → HSV+Motion/YOLOv8n TensorRT → 时序确认
         → /fire_alert → 取消巡检、减速/停车、语音、图片/时间/位置记录
    waypoints.yaml → patrol_manager → Nav2 Action → cmd_vel
    Nav2/遥控 → safe_cmd_mux → VOA → 唯一运动发送器 → 120

Phase 0 是无头启动、Foxglove、DDS 与监控；Phase 1 是 Nav2 固定路线；Phase 2 是 YOLO 火焰检测；Phase 3 是停止、取证、语音告警闭环；Phase 4 是持续优化。验收包括至少 2 小时巡检、8 小时长测、检测延迟 ≤500 ms、导航频率 ≥10 Hz、CPU <80%、100% 无 GUI 和异常人工恢复。

### 2.2 计划接口与兼容问题

计划列出 /candle_detected（vision_msgs/Detection2DArray）、/fire_alert（std_msgs/Bool）、/fire_bbox（未明确具体 geometry_msgs 类型）、/fire_debug_image（sensor_msgs/Image），以及 /mission_cancel、/voice_alert、/event_record、/patrol_status 等未完整定义的接口。

需要先统一以下契约：

- /fire_alert 不能一处使用 std_msgs/Bool、另一处又使用 FireAlert.msg；建议自定义事件消息并另设简单 Bool 状态话题。
- FireAlert 草案中的 string class 建议改为 class_name，并通过 rosidl 编译确认。
- /mission_cancel 应调用 Nav2 Action cancel 并处理确认/超时；单独发布一个未定义 Topic 不会自动取消导航。
- 单目检测框不能直接提供可信三维 fire_pose；v1.0 可先记录图像、时间、机器人位姿，并把三维火源位置标为未知。
- dataset.yaml 与 fire.yaml 的示例结构需要统一；召回率/误报率必须定义测试集、事件窗口和统计口径。

## 3. 103 主机实测条件

### 3.1 操作系统、CPU、内存和 GPU

| 项目 | 实测值 |
| --- | --- |
| hostname/时间 | lite；远端 2026-09-15T15:48:41+08:00 |
| OS | Ubuntu 20.04.6 LTS (Focal Fossa) |
| 内核 | Linux 5.10.120-tegra #5 SMP PREEMPT，aarch64 |
| 平台 | NVIDIA Jetson Xavier NX Developer Kit；L4T R35.4.1 |
| CPU | aarch64；6 CPU 在线（0–5）；3 sockets × 每 socket 2 cores；1 thread/core；最高 1907.2 MHz |
| 内存 | 总 6.7 GiB；已用 1.7 GiB；available 4.8 GiB；buff/cache 1.7 GiB |
| Swap | 6 个 zram 分区，每个约 571 MiB；合计约 3.3 GiB，当前使用 0 |
| CUDA/TensorRT | CUDA runtime 11.4.298；TensorRT Python 8.5.2.2；libnvinfer 8.5.2 |
| 视频插件 | nvv4l2decoder 1.14.0；nvvidconv 1.2.3；GStreamer 可发现 |
| Python | 3.8.10；torch 2.1.0a0+41361538.nv23.6；torchvision 0.16.1；numpy 1.23.1；opencv-python 4.9.0.80 |
| 缺失项 | /home/test/foxglove 不是可运行 bridge 安装；pip 未找到 ultralytics；ros2 pkg prefix 未找到 foxglove_bridge、vision_msgs；/opt/ros/foxy 可找到 rosbridge_server |

硬件加速基础存在，但未测 GPU 利用率、温度、功耗、降频、TensorRT engine 实际加载时间和共享显存。不能由版本存在推导火焰模型可运行。

### 3.2 磁盘和目录权限

| 项目 | 实测值 |
| --- | --- |
| 根文件系统 | /dev/mmcblk1p1，ext4，117 GiB |
| 空间 | 已用 79 GiB，可用 34 GiB，70% |
| inode | 7,636,608 总；7,087,137 可用；使用率 8% |
| 挂载 | /home/ysc/lite_cog_ros2 位于根分区，rw |
| 工作区 | /home/ysc/lite_cog_ros2 及 system/map、pipeline/src/data 为 ysc:ysc，drwxrwxr-x |
| 写权限 | test -w /home/ysc/lite_cog_ros2 返回 0 |
| systemd 目录 | /etc/systemd/system 为 root:root，drwxr-xr-x；普通用户不能直接写 |
| 地图 | system/map 只有 lite3.yaml（157 bytes）；无 lite3.pgm、lite3.pcd |
| 航点 | pipeline/src/data 存在但为空 |
| 模型 | yolov8n.pt 6.53 MB、yolov8n.onnx 6.41 MB、yolov8n_amd.engine 22.7 MB、yolov8n_arm.engine 19.9 MB |

34 GiB 可用于有限构建和模型部署，但不等于满足取证保留量。按 4 Mbit/s 录像估算，8 小时约 14.4 GB；还需预留系统、构建、日志、事件图片和回滚空间。

### 3.3 网络和端口

103 的 eth0 为 UP，地址 192.168.1.103/24；默认路由为 via 192.168.1.120。103 到 120 ping 两次均成功，0% 丢包，平均 0.665 ms；邻居表显示 REACHABLE。

| 用途 | 端口/协议 | 实测或配置状态 |
| --- | --- | --- |
| SSH | 22/TCP | 103 对外监听；MCP 连接成功 |
| Foxglove bridge / rosbridge | 建议 8765/TCP WebSocket | 当前未监听；/opt/ros/foxy 的 rosbridge_server 可作为替代，/home/test/foxglove 只提供说明和空工作区 |
| 120 RTSP | 8554/TCP | 从 103 TCP 可连；未用 ffprobe 验证帧解码 |
| Transfer → 120 | 43893/UDP | 未主动发送 UDP 探测；TCP 失败不具判断力 |
| Transfer 本地 | 43897/UDP、43899/UDP | 103 正在监听 |
| ROS2 DDS | UDP 7400/7401 等 | 当前有监听；需按 Domain ID、Cyclone 配置和防火墙核对 |
| 当前电脑代理 | 7897/TCP（可选） | 仅出网代理，不是机器人服务端口 |

103 上还监听 4000、111、4369、5900 等系统/远程服务端口。未监听 TCP 8765/9090。Foxglove 可连接 rosbridge WebSocket，但实际部署须先确认协议、鉴权和消息支持；建议通过受控 bridge 或 SSH 隧道访问，避免直接暴露命令和参数接口。

### 3.4 服务、进程和 ROS 图

transfer_ros2.service 位于 /etc/systemd/system，enabled/active/running。ExecStart 为 /bin/bash /home/ysc/lite_cog_ros2/system/scripts/transfer/start_transfer.sh，Type=forking、KillMode=control-group；unit 未设置 User/Group，因此默认 root。主进程为 ros2 launch，子进程为 jetson2app、jetson2motion、sensor_checker；采样时 service 内存约 108.4 MB，日志持续显示收到 16–380 字节 UDP 报文。

systemctl --failed 发现 nv-l4t-usb-device-mode.service、trojan_client.service failed。realsense_ros2.service 和 voa_ros2.service 已安装但 disabled/inactive；rtsp_stream.service、foxglove_bridge.service 不存在。/home/test/foxglove/foxglove_ws 只有 COLCON_IGNORE 和生成的空 prefix，不能作为已安装 bridge 进程。systemctl --user 没有 failed unit，用户服务和 GNOME 会话正在运行；Linger=no，说明当前不是无头登录环境。

source Foxy 与 transfer overlay 后，ROS 图为：

| 项目 | 实测 |
| --- | --- |
| 节点 | /app_receiver、/motion_receiver、/motion_sender、/sensor_checker |
| 有发布者 | /imu/data（1）、/leg_odom2（1）、/tf（1） |
| 只有订阅者 | /rslidar_points（0 publisher/1 subscriber）、/camera/depth/color/points（0/1）、/cmd_vel（0/1）、/cmd_vel_corrected（0/1） |
| 运行缺失 | Nav2、VOA、RealSense、hdl_localization、map_server |

采样进程列表中 sensor_checker、jetson2motion 瞬时 CPU 占用约 26.6%/22.7%，只能作基线警示，不能当长期平均值。计划 CPU<80% 必须统一采集整机和各进程 PSS/P95。

### 3.5 设备和 sudo

ysc 属于 sudo、audio、video、render、plugdev、gpio 等组。/dev/video0–5 存在且视频设备权限允许视频组访问；/dev/snd 下设备为 root:audio，ysc 属于 audio。未发现 /dev/ttyUSB* 或 /dev/ttyACM*。USB 设备存在，但没有确认具体设备型号。

sudo -n -l 返回“sudo: a password is required”。因此 MCP 非交互命令不能直接使用 sudo；ysc 在 sudo 组，通常可在交互输入密码后提权，但 sudoers 范围和密码未在本次使用。读取源码、工作区构建和用户目录写入不需要 sudo；编辑 systemd、apt/udev、防火墙、系统日志或设备策略通常需要管理员授权。

## 4. 需求逐项可行性

| 计划步骤/验收 | 现状对照 | 判断 |
| --- | --- | --- |
| Phase 0：headless 启动、DDS、监控 | systemd 有 Transfer；但 GNOME/GDM/VNC 服务运行、tmux 缺失、bridge 未装；当前只有 Transfer | **部分可行**。需独立无 GUI launch、bridge 和监控，不能复用会启动 RViz/gnome-terminal 的脚本 |
| Foxglove 远程查看 TF/map/odom | 103↔120 网络好，/tf 与 /leg_odom2 存在；bridge 和 map 未运行；/opt/ros/foxy 有 rosbridge_server | **有条件可行**。可先验证 rosbridge WebSocket 方案；若坚持 foxglove_bridge，仍需为 Foxy/aarch64 安装或构建它；两者都须白名单话题并确认 8765/TCP 或隧道 |
| Nav2 固定路线 | Nav2/HDL overlay 存在，但地图 PCD/PGM 缺失、航点为空、Nav2 未运行 | **阻塞**。恢复现场地图、TF、雷达/IMU，再开发 patrol_manager |
| RTSP→YOLO 火焰检测 | 120:8554 TCP 可达；GStreamer/TRT 基础存在；ultralytics、火焰 engine、fire_detector 不存在 | **部分可行/功能阻塞**。先用录像完成节点和模型验收，再做端到端解码 |
| 检测 ≤500 ms、召回率/误报率 | 无火焰模型、数据集和时延测量；10 FPS 下五帧确认的理想间隔约 400 ms | **未满足**。必须定义起止时间并测 P95/P99、事件级召回/误报 |
| 告警减速/停止/语音 | fire_event_manager、voice_alert、mission_cancel 未实现，语音协议未知 | **阻塞**。先定义接口和确认/超时语义，不以 Bool 代替制动 |
| VOA 最终安全层 | VOA 包已安装但未运行；Transfer 同时收 /cmd_vel 与 /cmd_vel_corrected；pipeline/track 有直连路径 | **P0 安全阻塞**。统一 mux、唯一发送器、末端 watchdog 和急停 |
| 图片/时间/位置取证 | 磁盘有余量、工作区可写；NTP active 但 system clock synchronized=no，RTC 显示 2000 | **部分可行**。先修时钟，设计事件 ID、原子写入、轮转和失败告警 |
| 连续 2 h/8 h、CPU<80%、导航≥10 Hz | 无动态测试；历史 lite_nav2.yaml controller_frequency=5 Hz | **未满足**。需安全场地长测；5→10 Hz 是配置和性能双重问题 |

## 5. 优先级整改建议

### P0：上线前必须完成

1. 确认 103/120 固定地址、SSH、RTSP 帧、雷达 UDP、IMU/里程计和 TF；补齐现场一致的 lite3.pcd、lite3.pgm 和航点文件。
2. 建立唯一安全控制链：Nav2/遥控/火灾停止 → safe_cmd_mux → VOA → 唯一 Transfer 发送器；移除或门控 Transfer 原始速度订阅及 pipeline/track 直接 UDP。
3. 加入人工急停、火灾停止锁存、输入超时和末端 watchdog；对进程退出、RTSP/DDS/网络中断、取消目标失败和旧命令重放做故障注入。
4. 不以 root 运行普通业务节点；建立专用用户/组和最小设备 ACL，仅 systemctl 管理动作保留 sudo。
5. 修正时钟同步，记录单调时钟和墙上时钟；设置图片/日志磁盘阈值、轮转和失败告警。

### P1：联调前完成

1. 建立独立 fire_patrol_ws/src/{fire_detector,patrol_manager,fire_event_manager,safe_cmd_mux,lite3_interfaces}，固定 overlay/source 顺序。
2. 先选择 bridge 协议：/opt/ros/foxy 已有 rosbridge_server，可用 /home/test/foxglove/readme 所指命令做兼容性验证；若需要 Foxglove Bridge 原生协议，再锁定 Foxy/aarch64 版本构建。无论选择哪种，都应白名单、限频、降采样并通过 SSH 隧道暴露；/home/test/foxglove 的空工作区不应当作构建产物。
3. 准备火焰/蜡烛/LED/手电/屏幕/反光负样本，按场景或视频划分训练验证；在 Jetson 上真实加载 yolov8n_fire.engine。
4. 明确 systemd WorkingDirectory、Environment、After/Requires、Restart、日志路径和运行用户；不要假定 Linger=no 的 user unit 能在无人登录时工作。
5. 以当前 5 Hz 导航配置为基线，分别测 planner/controller/VOA 周期，再决定是否提高到 ≥10 Hz。

### P2：持续优化

- 事件数据保留/加密、远程下载、健康状态、磁盘水位和版本回滚。
- RTSP 断线重连、模型加载失败、DDS 重启、地图失败和语音无响应的人工恢复。
- 2 小时功能巡检和 8 小时耐久测试，检查内存泄漏、TensorRT 降频、zram 压力、录像增长和日志轮转。

## 6. 替代实施方案

1. 保留 Ubuntu 20.04/Foxy 和现有导航 overlay，只新增独立工作区；冻结 CUDA 11.4、TensorRT 8.5.2、Jetson L4T R35.4.1 依赖，不在 v1.0 同时升级 ROS、JetPack 和导航算法。
2. 先用 120 录制的 RTSP/视频文件开发火焰检测和事件状态机；103 暂只联调导航/安全接口。外置推理时把网络断开定义为安全状态。
3. 若 rosbridge 与 Foxglove 兼容性不足，先用 rosbag/Mcap 做离线 Foxglove 验证，再锁定 Foxy bridge；不要把现代发行版预编译包直接装进 Foxy。
4. HSV+Motion 只作影子预筛选/低负载提示，不能过滤静止火焰或替代 YOLO 验收；资源不足可降低分辨率/频率，但须重新测召回率和延迟。
5. v1.0 先记录检测图像、时间和机器人位姿，火源三维坐标标为未知；深度/标定/多视角定位放到后续版本。

## 7. 仍需补采指标

基础主机条件已采到，但以下信息不足以给出最终上线批准：

- 120 的 OS/CPU/内存、RTSP 服务进程、8554 帧率/码率、语音服务和 43893/UDP 状态；
- ffprobe/GStreamer 实际拉流首帧、持续帧率、断线重连时间；
- GPU 利用率、温度、功耗模式、降频、推理显存/共享内存；
- Nav2/VOA/RealSense/HDL 启动后的 Topic 频率、TF 连通、QoS、控制输出周期；
- 火焰模型 Jetson TensorRT 加载结果、端到端延迟 P95/P99、事件级召回/误报；
- realsense_ros2.service、voa_ros2.service 的完整内容、运行用户、日志和重启策略；
- 防火墙、Cyclone DDS 配置/Domain ID、多播或 discovery server 设置；
- 现场地图、航点、相机标定、雷达外参、USB 设备对应关系；
- 2 小时路线和 8 小时耐久测试数据。

动态测试和真实运动需单独制定急停、安全场地与回滚方案；本评估不替代运动安全验收。

## 8. 交付判定

截至本次采集：

- **可直接做**：离线火焰数据集/模型开发、消息契约设计、无头 launch/systemd 设计、模拟 Action/mux/事件测试、日志与监控脚本设计。
- **需整改后做**：选择并启动 rosbridge 或 Foxglove bridge、Nav2/VOA/RealSense 联调、固定路线、TensorRT 实时推理、事件停车和语音闭环。
- **当前阻塞**：地图/航点缺失、bridge 尚未运行、vision_msgs/ultralytics 缺失、现有安全控制旁路、时间未同步、业务节点以 root 运行、运行频率/长测无证据。

建议先完成 P0，再按 Phase 0→1→2→3 逐阶段验收；在第 7 节数据和故障注入完成前，不应宣称 Lite3 火灾巡检 v1.0 已上线。

参考：[ROS 2 End-of-Life distributions](https://docs.ros.org/en/rolling/Releases/End-of-Life.html)；[Foxglove ROS 2](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2)。
