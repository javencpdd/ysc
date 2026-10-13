# Lite3 建图（SLAM）与导航代码审计报告

> 审计方式：通过 `mcp-ssh-apply-patch` 连接 `user-f20`，仅执行目录、Git 元数据、源码、配置、服务状态和端口的读取操作；**未修改远端任何文件、服务、网络或机器人控制状态**。
>
> 审计范围：`/home` 下的代码、部署目录、Git 元数据、系统服务定义和运行进程；重点检查 `/home/ysc`、`/home/user`。文中行号均为远端当前工作树的行号。

## 1. 结论摘要

本机可见范围内**没有部署可读的 SLAM 或完整 Navigation 源码/ROS 运行栈**。未发现 ROS 1/ROS 2 的可执行程序、软件包、`package.xml`、launch 文件、RViz 配置、地图/点云文件，且在源码与配置中未命中 `cartographer`、`slam_toolbox`、`rtabmap`、`gmapping`、`move_base`、`nav2`、`amcl`、`map_server`、`robot_localization`、`/scan`、`/map`、`/cmd_vel` 等实现标识。

**更正（后续只读取证）：这不等于 Lite3 没有建图/导航能力。**用户指定的开发指南明确声明该功能；并且当前运动主机的厂商闭源二进制 `backup/deeprcs` 带有完整调试信息与未剥离符号，已检出 `kSlam`、`kNavigation`、`slam_client_ip`、`slam_client_port`、SLAM 速度/加速度/失联/航向校正字段，以及原始编译单元 `gridmap_listener.cpp`。它更符合“运动主机侧接收 SLAM/栅格地图结果、将其接入运动控制”的角色。真正的感知/SLAM 引擎源码很可能运行在另一台感知主机；`192.168.1.103` 是当前唯一明确的候选，已由运动主机 ARP 与 ICMP 只读验证在线，但尚未登录，因此不能把它的代码情况写成已审计事实。

远端实际存在且与“自主移动”边界相关的组件有三类：

1. **`Lite3_MotionSDK`：有源码的底层关节控制 SDK 示例。**它实现 UDP 命令/状态交换、1 ms 周期、关节位置/速度/力矩/PD 增益控制和起立演示；不是定位、建图、路径规划或速度导航框架。
2. **`track`：正在运行的闭源视觉目标跟踪/跟随程序。**它从本机 RTSP 拉取视频，使用 RKNN/YOLOv5 目标检测，配置中有轨迹阈值和线速度/角速度 PD 参数，并向本机运动服务发送私有 UDP 数据。它没有地图、里程计、全局/局部规划或 ROS 接口；因只有 ELF 二进制，不能进一步确认跟踪或控制报文算法。
3. **`jy_exe`：正在运行的闭源底层运动控制服务，同时含 SLAM/导航结果接入层。**它在 UDP `43893` 接收控制，并按 `network.toml` 对接上位机；其 `deeprcs` 二进制带有 SLAM 客户端、栅格地图监听、位姿、速度、超时和导航状态符号，但不含可读的建图/规划引擎源码。

因此，准确结论是：**Lite3 的厂商系统具备并宣称支持建图/导航；当前已审计到运动主机侧的闭源导航接口/适配层，但尚未定位感知主机上的 SLAM 引擎或其源码。**不能仅以当前 `/home` 下没有 ROS 工程，推断设备不具备建图和导航功能。

## 2. 检索方法、权限与判断依据

### 2.1 只读访问与权限结论

所有下列候选文件均已能通过当前远端会话读取；未变更权限。

| 路径 | 所有者/权限（抽样） | 读取结论 |
| --- | --- | --- |
| `/home/ysc/Lite3_MotionSDK`、`.git` | `ysc:ysc`，`775` | 当前会话可读取源码与 Git 原始元数据 |
| `/home/ysc/sdk_lib` | `ysc:ysc`，`755` | 当前会话可读取 SDK 传输层源码 |
| `/home/ysc/jy_exe` | `ysc:ysc`，`755` | 当前会话可读取启动脚本与配置；控制核心是二进制 |
| `/home/ysc/track/track`、`config.json` | `root:root`，分别为 `755`、`644` | 当前会话可读取元数据、配置和二进制字符串；无源码 |
| `/home/ysc/rl_deploy/bin/rl_deploy` | `root:root`，`666` | 当前会话可读取二进制及部署脚本；无源码 |

`Lite3_MotionSDK` 的普通 Git 命令受 Git 的 *dubious ownership* 保护限制；为避免写入全局 `safe.directory`，本审计仅读取 `.git/config`、`HEAD`、reflog 和直接指定 Git 目录的查询。没有改变 Git 配置。

### 2.2 检索路径和排除依据

检索了 `/home` 的 Git 根、源码/配置/启动文件和 systemd 服务；仅发现两个 Git 根：

- `/home/ysc/Lite3_MotionSDK/.git`
- `/home/ysc/.zetton/third_libs/.git`（第三方依赖目录，未发现建图/导航实现）

此外，检查了 ROS/导航典型清单与运行态：未找到 `roscore`、`roslaunch`、`ros2`、`rviz`、`rviz2`，也未找到对应的 Debian 软件包或 ROS package/launch/地图资产。上述关键词仅在 Eigen、PyBind、VS Code、npm 等第三方依赖的通用 `map` 名称中出现，不属于机器人地图。

这不能证明机器人从未在其他磁盘、容器、外接计算机或厂商不可见分区上运行 SLAM；它证明的是：**在本次允许读取的主机可见 `/home` 代码与本机服务范围内，没有可分析的 SLAM/Navigation 工程。**

## 3. 代码与部署位置清单

| 层级/主次 | 项目或组件 | Git 地址、版本 | 目录 | 入口与启动方式 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 主：可读 SDK | Lite3 Motion SDK | `https://github.com/DeepRoboticsLab/Lite3_MotionSDK.git`；`main`；`d019c8d41bfcb7a05390e25e7d8310374ca56b48`（`2024-03-04`，`update urdf`） | `/home/ysc/Lite3_MotionSDK` | `main.cpp`；`CMakeLists.txt` 生成 `Lite_motion` | 关节级运动控制样例；非 SLAM/Nav |
| 支撑库 | Lite3 SDK library（无 Git） | 未见 Git 元数据 | `/home/ysc/sdk_lib` | `src/sender.cpp`、`src/receiver.cpp`、`src/command.cpp` | UDP 协议/收发实现；非 SLAM/Nav |
| 运行中 | `jy_exe` / `deeprcs` | 无可读仓库；`bin/jy_exe -> backup/deeprcs`，AArch64 闭源二进制，保留调试信息 | `/home/ysc/jy_exe` | `jy_exe.service` → `run.sh` → `bin/jy_exe` | 底层运动服务，内含 SLAM/导航结果接入与运动侧融合线索；非可读 SLAM 引擎源码 |
| 运行中 | `track` | 无 Git；AArch64 ELF，Build ID `2b9e04…` | `/home/ysc/track` | `track.service` → `start_track.sh` → `./track` | 视觉检测/跟踪/跟随；非 SLAM/Nav |
| 次要候选 | `rl_deploy` | 无 Git；AArch64 ELF，Build ID `2f267a…` | `/home/ysc/rl_deploy` | `run_rl_deploy.sh` → `rl_deploy` | 多个步态/特技 ONNX/PT 策略；非地图/导航源码 |
| 视频依赖 | `rtsp_stream` | 本报告不展开其源码 | `/home/ysc/rtsp_stream` | `rtsp_stream.service` → `start_stream.sh` | 为 `track` 提供 `rtsp://127.0.0.1:8554/test` 视频输入 |
| 待审计主机 | 感知/SLAM 主机候选 | 尚未登录 | `192.168.1.103`（从运动主机的 `eth1` 可达） | 未知 | 极可能承载传感器、建图/定位或导航业务；须登录后确认 |

### 3.1 版本与工作树注意事项

`Lite3_MotionSDK` 的 `origin` 与上表 GitHub 地址一致，当前分支是 `main`。但工作树不是干净状态：`main.cpp`、`include/robot_types.h`、两个预编译 SDK `.so` 被修改，且有未跟踪的 Python 目录等内容。因此本报告的代码结论以**远端当前实际工作树**为准，不能把提交 `d019c8d` 当成完整的当前行为快照。

### 3.2 关键文件

| 文件 | 职责 |
| --- | --- |
| `/home/ysc/Lite3_MotionSDK/main.cpp` | C++ 样例入口：启动定时器、状态接收、关节指令发送和控制权归还 |
| `/home/ysc/Lite3_MotionSDK/src/motionexample.cpp` | 起立轨迹、三次样条插值、关节 PD/力矩示例 |
| `/home/ysc/Lite3_MotionSDK/include/{sender,receiver,robot_types,motionexample,dr_timer}.h` | SDK 公共接口、数据结构、定时器声明 |
| `/home/ysc/sdk_lib/src/{sender,receiver,command}.cpp` | UDP 报文封装、`RobotCmd` 发送、`RobotData` 接收 |
| `/home/ysc/sdk_lib/include/{command,udpsocket,udpserver}.h(pp)` | 私有 UDP 协议头和 socket 封装 |
| `/home/ysc/jy_exe/scripts/run.sh` | 底层服务启动、CPU/IRQ 设置和日志重定向 |
| `/home/ysc/jy_exe/conf/network.toml` | 底层运动服务与候选 SLAM/上位机之间的 IP 和 UDP 端口 |
| `/home/ysc/track/config.json` | 视频输入、检测/跟踪阈值、控制 PD 参数及私有 UDP 端点 |
| `/home/ysc/track/start_track.sh` | 视觉跟踪二进制启动脚本 |

## 4. 架构与执行流程

### 4.1 当前可验证的数据链路

```text
本机 RTSP 服务 (:8554)
  └─ rtsp://127.0.0.1:8554/test
       └─ track（二进制；YOLOv5/RKNN 检测、目标跟踪、PD 跟随）
            ├─ 监听 UDP :43901（私有输入，具体报文不可由配置推断）
            └─ 发送到 127.0.0.1:43893
                 └─ jy_exe（运行中的闭源运动服务，监听 UDP :43893）
                      ├─ 控制下位执行器
                      └─ 状态回传至 network.toml 的 ip:43897

外部控制机上的 Lite3_MotionSDK 示例
  ├─ UDP 命令 -> 192.168.1.120:43893
  └─ UDP 状态 <- 本机 :43897，命令码 0x0906
```

端口观察结果与配置相符：本机 UDP `43893`、`43901` 和 TCP `8554` 正在监听。`jy_exe` 与 `track` 服务处于 active；旧的 `jy_rl.service` 指向不存在的 `/home/ysc/rl/bin/run_rl.sh`，当前为 failed，不能作为运行中的导航组件。

`track` 到 `jy_exe` 的细节来自配置和端口交叉验证，具体私有报文内容因 `track` 无源码而不可确认；图中“控制下位执行器”是按 `jy_exe` 的部署职责及 MotionSDK 协议推断，不应等同于已验证的 ROS `cmd_vel` 接口。

### 4.2 与 SLAM/Navigation 的关系

标准 SLAM/导航应至少形成下列闭环：

```text
LiDAR / 相机 / IMU / 关节里程计
  -> 时间同步与坐标变换（TF）
  -> 状态估计/里程计
  -> SLAM 建图或定位（map <-> odom <-> base）
  -> 全局规划 + 局部避障
  -> 速度命令桥接
  -> 步态/底层运动控制
```

当前主机并非只在最后两段有证据：除 SDK 可发关节级命令、`track` 可从视觉目标生成某种私有控制输入外，`deeprcs` 的调试元数据还保留原编译文件 `src/listener/gridmap_listener.cpp`，其 `Controller::KineticsDeduce(double&)` 中包含 `slam_flag_enable`、SLAM 超时记录和 `kSlam`/`kNavigation` 状态。结合 `slam_client_ip`、`slam_client_port`、激光当前位置/航向、SLAM x/y/yaw 速度与加速度字段，可确认它至少承担 SLAM 结果接入、连接超时和运动侧融合/仲裁的一部分。

但**没有**找到 SLAM 引擎、地图存储、定位器或路径规划器的可读源码、配置、话题、服务和进程；它们仍可能在感知主机。`Algorithm.toml` 的 `is_default_lidar = true`（第 13 行）和 `flat_rl_config.yaml` 的 `gridmap_port: 49998` 都是接口线索，不能单独证明本机运行了激光建图。

## 5. Lite3 MotionSDK 核心逻辑

### 5.1 构建、依赖与启动

`/home/ysc/Lite3_MotionSDK/CMakeLists.txt`：

- 第 3 行项目名为 `Lite_motion`；第 4–11 行用 `BUILD_PLATFORM` 选择 x86 或 ARM 交叉编译器。
- 第 24–28 行包含本地 `include`、`include/common`、Eigen3；第 34 行生成 `Lite_motion` 可执行文件。
- 第 39–45 行链接 `libdeeprobotics_legged_sdk_{aarch64,x86_64}.so`、`pthread`、`m`、`rt`、`dl`、`stdc++`。

它没有 ROS、PCL、Cartographer、GTSAM、Ceres、OpenCV SLAM 或 Nav2 依赖。SDK 提供可选 Python 目录（`python/`），但其存在不改变“不是 SLAM/导航工程”的结论。

官方上游仓库将它定位为 Lite3 运动 SDK，提供 MPC/RL 运动控制接入而非 SLAM；本机 Git `origin` 指向同一仓库：[Lite3_MotionSDK](https://github.com/DeepRoboticsLab/Lite3_MotionSDK)。用户指定的[绝影 Lite3 开发指南](https://alidocs.dingtalk.com/i/p/OlnXRxOLAljEbGLp)作为对照依据列入；该页面在本次只读环境中未返回可公开读取的正文，因此没有臆造其中的章节或参数。

### 5.2 控制示例主流程

入口是 `/home/ysc/Lite3_MotionSDK/main.cpp`：

```cpp
// /home/ysc/Lite3_MotionSDK/main.cpp:39-47
Sender* send_cmd = new Sender("192.168.1.120", 43893);
Receiver* robot_data_recv = new Receiver();
robot_data_recv->RegisterCallBack(OnMessageUpdate);
MotionExample robot_set_up_demo;
RobotData *robot_data = &robot_data_recv->GetState();

robot_data_recv->StartWork();
set_timer.TimeInit(1);
send_cmd->RobotStateInit();
```

调用链如下：

1. `main` 创建 `Sender`，将命令目标显式设为 `192.168.1.120:43893`；创建 `Receiver` 并登记 `OnMessageUpdate`。
2. `Receiver::StartWork()` 创建 detached 工作线程；`Receiver::Work()` 把 UDP server 绑定到 `0.0.0.0:43897`。
3. 收到大载荷命令 `0x0906` 时，接收线程将载荷复制到 `state_rec_`（`RobotData`），再回调 `OnMessageUpdate` 标记数据更新。
4. 主线程以 `DRTimer` 的 1 ms 节拍读取状态：前 1000 个周期 `PreStandUp`，随后 `StandUp`；到第 10000 周期调用 `ControlGet(ROBOT)` 归还控制权并退出。
5. 每一周期调用 `Sender::SendCmd`，将 12 个关节的目标封装为私有 UDP 指令。

```cpp
// /home/ysc/sdk_lib/src/receiver.cpp:33-53
if (cm.command.type == command_type::CommandType::kMessValues) {
  switch (cm.command.code) {
    case ROBOT_STATE_CMD:                 // 0x0906
      memcpy(&state_rec_, cm.data_buffer, sizeof(state_rec_));
      if (CallBack_) CallBack_(ROBOT_STATE_CMD);
      break;
  }
}
udpServer.Bind(LOCAL_PORT, ...);          // LOCAL_PORT = 43897
```

#### 重要安全观察

`main.cpp:72-76` 虽然保留了“只在状态已更新时发送”的注释代码，但实际的 `send_cmd->SendCmd(robot_joint_cmd)` 位于条件外，会无条件执行。又因 `RobotStateInit()` 会先发送关节初始化命令（`sdk_lib/src/sender.cpp:80-87`），该示例是**会真实发出执行器控制命令的演示程序**，不能把它当作无风险的通信测试或导航桥接样板直接运行。

此外，`Receiver` 构造函数已经调用一次 `StartWork()`（`sdk_lib/src/receiver.cpp:18-20`），而 `main.cpp:45` 又调用一次。两个 detached 接收线程会竞争绑定同一个 UDP `43897`；绑定失败的线程只打印错误后仍进入休眠循环（`receiver.cpp:49-56`）。这是当前示例的实现缺陷，接入任何上层系统前应先修正并在不接执行器的环境验证。

### 5.3 指令/状态数据结构和协议

`/home/ysc/Lite3_MotionSDK/include/robot_types.h`：

- `ImuData`（第 17–36 行）：毫秒时间戳、欧拉角、角速度、加速度；
- `JointData`（第 39–44 行）：位置 rad、速度 rad/s、力矩 Nm、温度；
- `RobotData`（第 105–110 行）：`tick` + IMU + 12 关节状态 + 足端/接触力；
- `JointCmd`（第 60–67 行）：目标 `position`、`velocity`、`torque`、`kp`、`kd`；
- `RobotCmd`（第 69–80 行）：12 个 `JointCmd`，也可按前左/前右/后左/后右四腿访问。

命令载荷由 `CommandMessage` 组织：`EthCommand` 头（命令码、值或参数长度、类型/序号位域）+ 最多 1024 字节数据区，定义在 `/home/ysc/sdk_lib/include/command.h:19-47`。发送侧核心如下：

```cpp
// /home/ysc/sdk_lib/src/sender.cpp:67-72
void Sender::SendCmd(RobotCmd& cmd) {
  size_t cmd_size = sizeof(cmd);
  char *buffer = new char[cmd_size];
  memcpy(buffer, &cmd, cmd_size);
  Command command_temp(0x0111, sizeof(cmd), buffer);
  CmdDone(command_temp);
}
```

控制权相关命令：

| 用途 | 实现位置 | 命令码/行为 |
| --- | --- | --- |
| 发送 12 关节命令 | `sender.cpp:67-72` | `0x0111`，大载荷 `RobotCmd` |
| 收状态 | `receiver.cpp:14-15, 33-43` | `0x0906`，大载荷 `RobotData` |
| 归还机器人原控制 | `sender.cpp:94-107` | 先发送全关节 `kd=5` 的命令，再延时 2 秒后发 `0x0113` |
| 取得 SDK 控制 | `sender.cpp:108-111` | `0x0114` |
| 初始化/回零 | `sender.cpp:80-87` | `0x31010C05`，随后等待 7 秒 |

### 5.4 轨迹与关节控制算法

`MotionExample` 不是步态规划器。它只是把固定关节姿态通过三次多项式插值逐周期转换为关节目标：

- `PreStandUp`：1 秒内向 `(0°, -70°, 150°)` 收腿（`src/motionexample.cpp:18-40`）；
- `StandUp`：1.5 秒内到 `(0°, -42°, 78°)` 站立（第 46–81 行）；
- `CubicSpline`：由起/终位置和速度计算三次系数，并用相邻时刻差分出目标速度（第 201–231 行）；
- `SwingToAngle`：默认设置 `kp=60`、`kd=0.7`、前馈力矩为零（第 147–165 行）。备用分支则在上层计算 `torque = kp * position_error + kd * velocity_error`（第 167–186 行），但当前代码的 `if (true)` 使该分支不会运行。

```cpp
// /home/ysc/Lite3_MotionSDK/src/motionexample.cpp:140-165
CubicSpline(initial_angle[j], 0, final_angle[j], 0, run_time,
            cycle_time, total_time, goal_angle[j], goal_angle_next[j],
            goal_angle_next2[j]);
goal_velocity = (goal_angle_next - goal_angle) / cycle_time;
...
cmd.joint_cmd[3 * leg_side].kp = 60;
cmd.joint_cmd[3 * leg_side].kd = 0.7;
cmd.joint_cmd[3 * leg_side].position = goal_angle[0];
cmd.joint_cmd[3 * leg_side].velocity = goal_velocity[0];
```

### 5.5 UDP 地址、端口和配置关系

SDK 的地址设定存在需要特别注意的多处来源：

| 位置 | 当前值 | 作用/注意事项 |
| --- | --- | --- |
| `Lite3_MotionSDK/main.cpp:39` | `192.168.1.120:43893` | 示例明确使用的命令目的地 |
| `Lite3_MotionSDK/include/sender.h:40` | 默认 `192.168.1.120:43893` | 头文件默认参数 |
| `sdk_lib/src/sender.cpp:15-20` | 无参构造默认 `192.168.1.120:43897` | 与头文件默认端口不一致；应显式指定并抓包验证，不能依赖无参构造 |
| `sdk_lib/src/receiver.cpp:14-15, 50` | 本地监听 `43897`，状态码 `0x0906` | 上位机状态接收端口 |
| `jy_exe/conf/network.toml:1-3` | `192.168.1.103`、`43897`、`43893` | 已部署服务的状态回传主机和收命令端口 |

```toml
# /home/ysc/jy_exe/conf/network.toml:1-3
ip = '192.168.1.103'
target_port = 43897
local_port = 43893
```

结合上游 MotionSDK 的网络说明和当前文件，可合理推断外部控制机发送到机器人运动主机 `192.168.1.120:43893`，而机器人向配置中的上位机 `192.168.1.103:43897` 回传 `0x0906` 状态。地址必须随控制机网络变化同步调整；本报告未修改它。

## 6. `deeprcs`：闭源的运动侧 SLAM/Navigation 接入层

### 6.1 可复核的二进制与源码边界

实际执行文件是 `/home/ysc/jy_exe/bin/backup/deeprcs`（由 `bin/jy_exe` 符号链接到它），AArch64 ELF，Build ID 为 `3ad4124c7532df1fec374f84aebbb29de1822a14`。它**未剥离**，且含 `.debug_info`、`.debug_line` 和 `.symtab`，所以可在不反编译、不运行控制指令的前提下读取编译单元、函数名和枚举名。

调试信息显示原始工程为：

```text
/home/ysc/jy_mdk/deeprcs2019/
├── src/deeprcs_main.cpp
├── src/controller/controller.cpp
├── src/listener/gridmap_listener.cpp
├── src/listener/console_listener.cpp
├── src/sensor/{imu_sensor3.cpp, imu_sensor_wit2.cpp, ultrasonic_sensor .cpp}
├── src/motor_can/*
└── src/motor_spi/*
```

该原始目录目前不在运动主机文件系统中；因此调试路径只能用来界定其原始架构，不能替代源码级审计。程序还依赖 `libdeepras.so`，当前运行目录中存在多个厂商库副本，主二进制的 `RUNPATH` 为相对的 `../lib/ras_lib/`、`../lib/soem/`、`../lib/log_lib`。

### 6.2 建图/导航接入证据及可推断流程

以下信息来自该二进制的未剥离符号、DWARF 枚举和字符串，而不是猜测：

| 证据 | 可支持的结论 | 不可据此断言的内容 |
| --- | --- | --- |
| `deepros::controller::Controller::{RunRoutine, ReadConfigiration, ParseCommand, KineticsDeduce}` | 控制器读取配置、解析命令并在运动循环中融合输入 | 具体控制律或完整报文布局 |
| `kSlam = 0x30000000`、`kNavigation = 3`、`kSlamCorrect`、`kSlamYawCorrect` | 有独立的 SLAM 命令/状态类型、导航状态和校正分支 | 这些枚举的全部状态转移语义 |
| `slam_client_ip`、`slam_client_port`、`is_slam_lose`、`slam command is timeout.` | 存在与外部 SLAM 客户端的网络连接及失联/超时处理 | 外部客户端的实现语言、进程名和认证方式 |
| `current_lidar_pos_{x,y}`、`current_lidar_theta`、`lidar_location_{x,y,theta}`、`kLidarCurrentPos`、`kLidarWarningDistance` | 运动主机接收/保存激光定位位姿及告警距离 | 本机是否产生点云或执行 SLAM 优化 |
| `slam_{x_direction,y_direction,yaw}_vel`、对应加速度、`kVisionSlamVel*` | 将 SLAM/视觉 SLAM 的平面速度输入耦合到运动控制 | 限速、避障和轨迹规划具体算法 |
| `src/listener/gridmap_listener.cpp` 与 `gridmap_port: 49998` | 原工程有栅格地图监听模块，部署配置为 RL/运动侧保留了栅格地图端口 | 端口上当前是否有数据、地图格式和生产端 |

据此，较可靠的架构推断是：**感知主机产生 SLAM/定位、栅格地图和/或速度指令 → 经私有网络协议送入运动主机 `deeprcs` 的 listener/controller → `KineticsDeduce` 进行状态/超时/运动仲裁 → 下发步态或关节控制。**感知侧的 SLAM、地图管理和规划器代码尚未被读取，不应把上述运动侧适配层误写成完整 SLAM 引擎。

### 6.3 感知主机候选

运动主机的 `eth1` 地址为 `192.168.1.120/24`，路由直连 `192.168.1.0/24`；`192.168.1.103` 在该接口的邻居表中为 REACHABLE，ICMP 往返约 1.2 ms。它同时出现在 `/home/ysc/jy_exe/conf/network.toml` 的 `ip` 字段，并与 UDP `43897/43893` 对应。因此它是目前最强的感知/SLAM 上位机候选。

尚未对该主机执行 SSH 登录或文件读取，故本报告没有把它“已运行 SLAM”写成事实。登录后应优先检查：运行服务和容器、传感器驱动、地图/点云资产、`gridmap_port 49998` 的监听者、与运动主机的 UDP 会话，以及 Git/ROS/厂商工程根目录。

## 7. `track`：视觉跟随组件（非 SLAM）

### 6.1 部署、输入和运行状态

- 服务：`/etc/systemd/system/track.service`，`Type=forking`，执行 `bash /home/ysc/track/start_track.sh`。
- 脚本：`/home/ysc/track/start_track.sh:3-5` 切到目录，等待 10 秒，再以 `sudo ./track &` 启动。
- 二进制：`/home/ysc/track/track`，AArch64 动态 ELF，无 Git、无源文件；正在运行。
- 运行依赖：RKNN Runtime、RGA、GStreamer/App、OpenCV 4.2 等。`ldd` 的审计环境中显示 `librknnrt.so => not found`，但程序正在运行且目录中有 `lib/librknnrt.so`；重启前应先以受控方式核实动态库搜索路径，不能仅凭当前运行态假设重启一定成功。

### 6.2 可验证的功能和参数

```json
// /home/ysc/track/config.json:6-34
"communicate_params" : {
  "local_port" : 43901,
  "motion_addr" : "127.0.0.1",
  "motion_port" : 43893,
  "server_addr" : "127.0.0.1",
  "server_port" : 43800
},
"stream_params" : { "rtsp_uri": "rtsp://127.0.0.1:8554/test" },
"detect_params" : { "model_path": "yolov5s-640-640.rknn", "kConfThresh": 0.5, "kAreaThresh": 2000 },
"track_params" : { "kTrackHighThresh": 0.7, "kTrackLowThresh": 0.5, "kNewTrackThresh": 0.7 },
"control_params" : { "kp_linear_x": 5, "kd_linear_x": 0.2, "kp_angle": 5.0, "kd_angle": 0.1 }
```

由此可确认：视频来自本机 RTSP；检测模型是 `yolov5s-640-640.rknn`；跟踪器存在高/低/新目标阈值；控制器至少配置了前向与转向的 PD 项；运动目标是本机 `127.0.0.1:43893`。但由于没有源码或协议文档，以下内容**不能据此断言**：目标状态定义、误差公式、限速、停止条件、避障逻辑、`43901`/`43800` 的完整报文格式，以及它具体调用了 `jy_exe` 的哪个控制模式。

它没有 `map`、`odom`、`base_link`、激光扫描、占据栅格、路径或 ROS topic/service 定义，所以应命名为“视觉跟随/跟踪”，不能命名为 SLAM 或导航。

## 8. 话题、服务与模块接口

### 7.1 ROS 接口结论

本机没有找到 ROS 1/ROS 2 运行时和 package/launch 文件，因此不存在可列出的 ROS topic、service、action 或 TF 树。特别是没有证据证明存在 `/scan`、`/imu`、`/odom`、`/map`、`/tf`、`/cmd_vel`、`NavigateToPose` 等接口。

### 7.2 当前私有接口

| 接口 | 方向 | 内容 | 证据与限制 |
| --- | --- | --- | --- |
| UDP `:43893` | MotionSDK/track → `jy_exe` | 运动命令 | `jy_exe` 正监听；SDK `main.cpp:39` 使用该端口；`track/config.json:8-9` 指向它 |
| UDP `:43897` | `jy_exe` → 上位机 SDK | `0x0906` `RobotData` 状态 | SDK `receiver.cpp:14-15, 33-43`；`network.toml:1-3` |
| UDP `:43901` | 外部/本机 → track | track 私有输入 | `track` 正监听、配置声明；无源码，报文未知 |
| UDP `127.0.0.1:43800` | track ↔ 本机服务 | track 私有 server 接口 | 仅由配置可见，未观察到监听端，协议未知 |
| RTSP TCP `:8554` | `rtsp_stream` → track | 视频流 `/test` | 服务定义、端口与 `track/config.json:15` 相互印证 |

## 9. 与厂商资料的对照

| 对照项 | 资料侧 | 本机侧 | 结论 |
| --- | --- | --- | --- |
| 运动 SDK 来源 | [Lite3_MotionSDK 上游仓库](https://github.com/DeepRoboticsLab/Lite3_MotionSDK) | `origin` 指向同一仓库 | 可确认本机 SDK 基线来自官方上游 |
| 网络/UDP 运动控制 | 上游文档说明 Lite3 使用 UDP 进行 SDK 命令与状态交互，并给出 `43893/43897` 网络配置 | `main.cpp`、`receiver.cpp` 和 `jy_exe/conf/network.toml` 使用同一组端口 | 当前部署与该 SDK 模型一致；IP 必须按实际控制机调整 |
| 底层控制参数 | 上游 SDK 的命令含 position、velocity、kp、kd、feed-forward torque | 本机 `JointCmd` 和 `MotionExample` 对应实现完整可见 | 可用于关节级控制；不是高层速度导航 API |
| 开发指南 | [绝影 Lite3 开发指南](https://alidocs.dingtalk.com/i/p/OlnXRxOLAljEbGLp) | 本次环境不能匿名读取正文 | 只将其作为指定对照入口；部署变更前应由有权限者核对其中关于机型、网络、控制权和安全的章节 |

## 10. 风险、改进建议与后续方案

### 9.1 不应做的事

1. 不要把 `Lite3_MotionSDK/main.cpp` 当作无副作用示例运行：它会初始化关节、以 1 ms 循环连续下发命令，并在当前工作树中无条件发送。
2. 不要假设 `track` 的“线速度/角速度 PD 参数”就是 ROS `/cmd_vel` 或底层 SDK 的公开速度协议；现有证据只支持它通过私有 UDP 向本机 `43893` 发送数据。
3. 不要直接改 `jy_exe/conf/network.toml` 的 IP/端口、SDK 的默认端口或 `track/config.json` 的运动端点来“试通导航”。这些项处于运行中控制链路，错误修改会导致状态回传丢失、控制权异常或机器人动作不可预期。
4. 不要用当前 `track` 的纯视频跟随替代避障和导航：未发现地图、障碍物模型、局部代价地图或急停逻辑。

### 9.2 建议的实现路线

1. **先取得控制接口合同。**从厂商开发指南/支持渠道确认安全的高层步态速度接口、控制权申请/失效超时、急停和恢复语义。若厂商仅支持 `RobotCmd` 关节级接口，则不应直接把导航器的速度输出映射为关节角度。
2. **先审计候选感知主机，再决定是否新增工作区。**接入激光/深度相机、IMU 和可靠里程计的 SLAM/定位/规划服务很可能已部署在 `192.168.1.103`；运动主机本身没有可复用的 ROS 导航栈。只有在确认感知主机也缺失这些能力时，再考虑在外部开发机或隔离工作区新增部署。
3. **新增明确的速度桥接层。**桥接层应做限速、加速度限制、看门狗、状态健康检查、手动接管和安全停止；仅在收到新鲜定位、传感器和运动状态时向厂商认可的高层接口下发命令。
4. **保留 `track` 作为可选感知行为。**若需要“跟人”，将其目标输出作为导航目标或速度建议，并交给代价地图/局部规划器仲裁，不能绕过避障直连底层控制。
5. **分阶段验证。**先在悬空/仿真或厂商规定的安全测试环境验证状态收发，再验证零速度、限速、看门狗和人工急停，最后做低速空旷场地测试。每次只改变一个模块，并保留原配置、服务状态和回滚命令。

### 9.3 为获得完整代码分析所需的补充材料

若系统实际另有 SLAM/Navigation 工程，请提供其挂载目录、容器名称、外部控制机地址或对应 Git 仓库。若希望继续分析当前视觉跟随，需提供 `track` 的源码或厂商私有 UDP 协议文档；仅凭 ELF 与 JSON 配置不能可靠还原其控制算法或安全约束。
