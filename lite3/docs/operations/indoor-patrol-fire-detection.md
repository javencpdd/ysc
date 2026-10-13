# Lite3 室内多房间巡检 + 烛火检测执行方案

> 范围：在 `docs/operations/fire-candle-detection.md`（下称"检测方案"）已定义的算法、阈值与 ROS 2 话题基础上，设计"多房间建图 → 路点预设 → 自主导航巡检（支持**按路段自定义速度**）→ 途中/到点烛火检测 → 结果处理"的可落地执行方案。
>
> 依据：`docs/hosts/103-感知导航主机/`、`docs/hosts/120-运动控制主机/`、`docs/operations/host-maintenance.md`，采集时间 2026-09-07；Foxglove/rosbridge 结论核查于 2026-09-15。
>
> **运行形态**：被控端（103 车载主机）**纯终端无 GUI**；控制端（笔记本）通过 Foxglove 远程可视化。被控端部署细节（tmux 会话、`lite3` CLI、headless launch）以 [`headless-remote-ops.md`](headless-remote-ops.md) 为准；本文是**流程、速度分区、阈值、异常处理**的权威依据。
>
> 凡笔记未覆盖或需实机标定的量，标注 **[待确认]** 并给出建议默认值。

## 0. 运行形态与架构决策

### 0.1 三端职责

| 端 | 设备 | 职责 | 图形 |
| --- | --- | --- | --- |
| **被控端** | 103 车载 Jetson（`192.168.1.103`） | 建图、定位、导航、避障、烛火检测、巡检任务、运动桥接 | **无任何 GUI**（无 RViz / 无 X / 无桌面依赖） |
| **控制端** | 笔记本 | Foxglove 可视化、下发目标、查看告警、运维操作 | 有 GUI（Foxglove Studio） |
| **运动端** | 120 RK3588（`192.168.1.120`） | `jy_exe` 运动控制、`rtsp_stream` 相机推流 | 无 |

### 0.2 无 GUI / 低占用原则（被控端）

103 是 Jetson（6.7 GiB 可用内存），需同时承载定位 + Nav2 + VOA + 烛火检测 + 巡检，**图形开销必须清零**：

| 原则 | 具体措施 |
| --- | --- |
| 不启动任何 RViz2 | 用自建 headless launch 替代 `dr_nav2.launch.py` 与 `pcd2grid.launch.py` |
| 不依赖 `gnome-terminal` | 用 tmux 会话替代 `start_slam.sh` 的三窗口编排 |
| 环境层兜底 | `lite3_env.sh` 显式 `unset DISPLAY` + `QT_QPA_PLATFORM=offscreen`，让残留图形依赖快速失败而非挂起 |
| 可视化外移 | Foxglove bridge 优先跑在**控制端**，103 零新增进程 |
| 按需开启调试通道 | 103 侧 rosbridge 仅调试时启动，正式巡检前关闭 |

**验收**：任何时刻 `ros2 node list | grep -i rviz` 应为空。
**收益**：去掉建图与导航各一个 RViz2 实例，约省 **0.5~1 核 CPU 与 300~600 MB 内存**。

### 0.3 关键冲突与决策

| # | 冲突 | 处理 |
| --- | --- | --- |
| 1 | **ROS 1 有巡检管线但无 Nav2；ROS 2 有 Nav2 但无巡检管线**；检测方案部署在 ROS 2 | **全栈 ROS 2**，自建 `patrol_manager` |
| 2 | ROS 1 `dyn_reconfigure.py` 会**禁用 costmap 两层障碍物层**，与"实时避障"冲突 | **不使用**；避障交给 VOA + Nav2 costmap |
| 3 | 检测方案建议串 `safe_cmd_vel_mux`，但 `jetson2motion` 只订阅 `cmd_vel` / `cmd_vel_corrected` | 告警走**任务层中断**（cancel Nav2 goal），不抢占速度话题 |
| 4 | **Foxy 装不了官方 `foxglove_bridge`**（官方仅支持 Humble+） | 见第 4 节：优先"控制端 bridge"，用户指定的 rosbridge 作为通道 B |
| 5 | `dr_nav2.launch.py` 硬编码启动 RViz2 | 改用 `nav2_bringup/navigation_launch.py` 自建 headless 导航 launch |

### 0.4 两条图像链路（务必区分）

| 用途 | 来源 | 话题 / 地址 |
| --- | --- | --- |
| **VOA 避障** | RealSense 深度点云 | `/camera/depth/color/points` |
| **烛火检测** | 120 普通 USB 摄像头 `/dev/video0` → H.264 → RTSP | `rtsp://192.168.1.120:8554/test` |

二者**不是同一路图像**；烛火检测不依赖 RealSense，也不依赖 VOA。

---

## 1. 分阶段总体流程

```text
阶段1 建图保存 → 阶段2 路点录制（含速度分区规划）→ 阶段3 自主导航巡检（按路段变速）
                                                        ↓ 全程并行
                                                 阶段4 烛火检测与判定
                                                        ↓
                                                 阶段5 结果处理
```

所有阶段在被控端**纯终端**完成；可视化在控制端 Foxglove 进行。

### 阶段 1：多房间建图与地图保存

**目的**：生成定位用 PCD 点云地图与导航用二维栅格地图。

**前置条件**：ROS 2 模式（`sudo /home/ysc/scripts/switch_ros_version.sh ros2`）、`transfer_ros2.service` active、120 的 `jy_exe` 与 `rtsp_stream` active、业务网互通。**无需图形桌面**。

**操作（被控端 CLI）**

```bash
lite3 slam start                 # 启动建图（tmux 会话，无 gnome-terminal）
lite3 slam attach                # 查看输出（Ctrl-b d 脱离）

# 遥控机器人慢速走遍所有房间与门口（≤ 0.3 m/s，四足振动会恶化点云）
# 控制端 Foxglove 实时看 /projected_map 与 /rslidar_points

lite3 slam grid                  # 生成二维栅格
lite3 slam save                  # 自动备份旧图 → 保存 → 校验三件套
```

**关键参数**

| 项 | 值 / 说明 |
| --- | --- |
| 雷达 | `LITE3_LIDAR=leishen`（默认，C16）或 `livox`（MID360） |
| Faster-LIO | `mapping_c16.launch.py`；点过滤 `4`、最大迭代 `3`、滤波 `0.5`、地图立方体 `1000` |
| pcd2grid | 点云 Z `0.4..1.2`、栅格 Z `0..1.6`、分辨率 `0.05` |
| 产物 | `system/map/lite3.pcd` + `lite3.yaml` + `lite3.pgm` |

**成功判据**：`lite3 status` 地图三件套全 `[OK]`；控制端 Foxglove 中墙体连续、房间连通、门口可通行。

### 阶段 2：路点录制与速度分区规划

**目的**：固化观察位姿，**并标注需要慢速通过的重点区间**。

```bash
lite3 nav start                       # 先起定位与导航
# 遥控到目标位置并调整朝向：
lite3 waypoint add roomA-center
lite3 waypoint add doorway-A-B
lite3 waypoint list
```

**布点规则**

- 每个房间 ≥ 1 个观察点；遮挡多的房间设 2–3 个。
- **门口 / 门槛 / 窄通道不设停留点**（`dwell_sec: 0`，只途经）。
- 点距墙 ≥ 0.5 m，点间距 ≥ 1.5 m。
- 房间内 `detect_mode: sensitive`，走廊/门口 `normal`。

**同时规划速度分区**（详见第 2 节）：在 `waypoints.json` 的 `speed_zones` 中标注重点区间，例如"3→5 号点之间的厨房区用 40% 速度"。

**成功判据**：路点按 `order` 排序正确、均落在自由空间；`speed_zones` 引用的 order 均存在；`lite3 speed list` 能正确解析出每条路段的生效速度。

### 阶段 3：自主导航巡检（含按路段变速 + 实时避障）

**启动顺序不能颠倒**

```bash
lite3 nav start       # 雷达 → RealSense → 定位+Nav2 → VOA
lite3 status          # 确认节点与话题
lite3 detect start    # 烛火检测
lite3 patrol start    # 最后启动巡检
```

**速度链与避障（不做任何禁用）**

```text
Nav2 ─> /cmd_vel ─> VOA SafetyController ─> /cmd_vel_corrected ─> jetson2motion ─> UDP 43893 ─> 120 jy_exe
  ↑                       ↑
Nav2 costmap        RealSense 点云 + 超声 + leg_odom2
（全局/局部）       （局部地形与安全限速）
  ↑
按路段下发 max_vel_x（第 2 节）
```

- **Nav2 costmap**：全局/局部障碍层**保持启用**。
- **VOA**：局部地形安全修正，输出 `cmd_vel_corrected`。
- **禁止**使用 ROS 1 的 `dyn_reconfigure.py`。

**成功判据**：`lite3 status` 中 `hdl_localization`、`nav2`、`voa`、`jetson2motion`、`fire_detector` 均在；`/odom` 与 `/cmd_vel_corrected` 有输出；无 rviz 节点；重点路段实测速度符合配置。

### 阶段 4：烛火检测触发与判定

| 时机 | 行为 |
| --- | --- |
| **巡检途中（移动）** | 连续检测，仅产生 **WARN** 级记录（移动中抖动大，不据此中断） |
| **到达路径点（驻留）** | 驻留 `dwell_sec`，切 **sensitive** 模式，是 ALERT 主要来源 |
| **重点慢速区间** | 移动中即可提升灵敏度（速度低 → 画面稳 → 时序判定可靠），见 2.6 |

**阈值（沿用检测方案，不另起一套）**

| 项 | 值 |
| --- | --- |
| L1 颜色门 | H ∈ [10,35]，S ≥ 100，V ≥ 130（室内） |
| L1 运动门 | 与帧差重叠 > 30% |
| L2 后处理 | NMS IoU `0.45`，置信度 `0.35`（sensitive）/ `0.45`（normal） |
| 时序稳定 | 连续 5 帧 ≥ 3 帧（sensitive）/ ≥ 4 帧（normal）；中心抖动 < 30 px |
| 冷却 / 撤销 | 冷却 `2 s`；连续 10 帧无检出 → RETRACT |

### 阶段 5：结果处理

见第 5 节（记录、去重、告警与回传）。

---

## 2. 巡检区间自定义移动速度 ★

### 2.1 需求语义

允许用户选取**需要重点检查的巡检点区间**（几个相邻点之间，或多个点组成的区域），为该区间内的**通行路段**单独设置较慢速度。三种配置方式：

| 模式 | 含义 | 示例 |
| --- | --- | --- |
| `absolute` | 固定速度值（m/s） | `0.15` → 该路段限速 0.15 m/s |
| `percent` | 全局默认速度的百分比 | `40` → 默认 0.40 的 40% = 0.16 m/s |
| `divisor` | 全局默认速度的减速倍数 | `3.0` → 0.40 / 3 ≈ 0.13 m/s |

### 2.2 配置格式

扩展 `ops/config/waypoints.json`（**v2**）：

```json
{
  "version": 2,
  "map_frame": "map",
  "loop": true,
  "defaults": {
    "max_speed": 0.40,
    "min_speed": 0.08,
    "dwell_sec": 5.0,
    "detect_mode": "normal"
  },
  "waypoints": [
    {"order": 1, "name": "hall-start",   "x": 0.00, "y": 0.00, "yaw_deg":   0.0},
    {"order": 2, "name": "roomA-center", "x": 2.10, "y": 1.35, "yaw_deg":  90.0, "dwell_sec": 8.0, "detect_mode": "sensitive"},
    {"order": 3, "name": "kitchen-in",   "x": 4.20, "y": 1.10, "yaw_deg":  90.0, "detect_mode": "sensitive"},
    {"order": 4, "name": "kitchen-out",  "x": 5.30, "y": 1.00, "yaw_deg":  90.0},
    {"order": 5, "name": "corridor",     "x": 6.00, "y": 0.20, "yaw_deg":   0.0, "dwell_sec": 0},
    {"order": 6, "name": "roomB-center", "x": 7.50, "y": 2.40, "yaw_deg": 180.0, "dwell_sec": 8.0, "detect_mode": "sensitive"}
  ],
  "speed_zones": [
    {
      "name": "roomA-approach",
      "range": [1, 2],
      "speed": {"mode": "absolute", "value": 0.15},
      "note": "进入 A 房间的窄通道：直接给固定值"
    },
    {
      "name": "kitchen-focus",
      "range": [3, 5],
      "speed": {"mode": "percent", "value": 50},
      "detect_mode": "sensitive",
      "note": "厨房与茶水间：明火风险高，按默认速度的 50%（0.20 m/s）慢速通过"
    },
    {
      "name": "corridor-slow",
      "range": [5, 6],
      "speed": {"mode": "divisor", "value": 3.0},
      "note": "长走廊：默认速度 ÷ 3（0.13 m/s）"
    }
  ]
}
```

> 上例在 `defaults.max_speed = 0.40` 下的实际取值为：
> `1→2`: **0.15**、`2→3`: **0.40**（未命中，用默认）、`3→4`: **0.20**、`4→5`: **0.20**、`5→6`: **0.13**。

### 2.3 区间匹配规则

- **路段定义**：相邻巡检点之间的一次移动为一个路段，记作 `(i → i+1)`。
- **`range: [a, b]`** 覆盖从 `a` 号点出发到 `b` 号点的**全部连续路段**：
  `(a→a+1), (a+1→a+2), …, (b-1→b)`。
  - 例：`range: [3,5]` 覆盖路段 `3→4` 与 `4→5`。
- **环绕**：若 `loop: true` 且 `a > b`，则跨末尾环绕：`(a→a+1) … (N→1) … (b-1→b)`。
- **多区间重叠**：**取最慢**（安全优先）。例：某路段同时被 40% 与 0.15 m/s 命中，取 0.15。
- **未命中任何区间**：使用 `defaults.max_speed`。

### 2.4 速度计算与下发

**计算**

```
absolute: v = value
percent : v = defaults.max_speed × value / 100
divisor : v = defaults.max_speed / value
最终    : v = clamp(v, defaults.min_speed, defaults.max_speed)
```

**下发生效点**：`patrol_manager` 在**每次发送 `NavigateToPose` 之前**，计算该路段目标速度，若与当前生效值不同则更新：

```bash
ros2 param set /controller_server FollowPath.max_vel_x 0.15
ros2 param get /controller_server FollowPath.max_vel_x     # 验证
```

> **[待确认]** 参数名取决于 Nav2 实际控制器插件：
> - DWB（Foxy 默认）：`FollowPath.max_vel_x`
> - TEB / 其他：参数名不同，需 `ros2 param list /controller_server` 确认。
>
> **[待确认]** Foxy 的 DWB 是否支持参数**动态生效**（部分参数需 lifecycle 重新 configure）。
> 若实测不生效，降级方案见 2.7。

### 2.5 与 VOA / 全局速度的叠加

最终实际速度 = **min(Nav2 `max_vel_x`, VOA 安全限速, 全局默认)**。

- VOA 的 `SafetyController` 会基于地形/超声独立限速，**无论如何配置都无法突破它**——这是安全特性，不是 bug。
- 因此配置重点区间速度后，若发现实际速度仍快，先查 VOA 是否已在限速；若想让某段更慢，Nav2 侧设更小值即可。

### 2.6 慢速区间的额外收益：可提升检测灵敏度

移动中画面抖动是误报来源。在**慢速区间内**，可将检测从 `normal` 提升到 `sensitive`（`speed_zones[].detect_mode`），因为：

- 画面更稳 → 时序稳定判定（5 帧 ≥3）更可靠；
- 通行时间更长 → 有效观测帧数更多；
- 机器人自身抖动更小 → L1 运动门的帧差噪声更低。

即"慢速"不只是安全考虑，也直接提升该区间的检测质量。

### 2.7 降级方案（若参数动态设置不生效）

| 优先级 | 方案 | 代价 |
| --- | --- | --- |
| 1 | `ros2 param set` 动态改控制器最大速度 | 无（首选） |
| 2 | 该区间拆成多个短 goal，逐段前重设参数并等待生效 | 复杂度上升 |
| 3 | 用 Nav2 的 SpeedFilter / costmap filter 做区域限速 | 需额外配置 filter mask |
| 4 | 放弃路段变速，改为**在重点区间增加巡检点密度 + 延长驻留** | 达不到用户目标，仅兜底 |

### 2.8 CLI 与验证

```bash
lite3 speed list          # 列出每条路段的生效速度（解析 waypoints.json）
lite3 speed zones         # 列出 speed_zones 定义
lite3 speed check         # 校验 order 引用合法性、重叠冲突、越界值
```

**验证步骤**

1. `lite3 speed check` 无报错（order 存在、值在范围内）。
2. 巡检启动时日志打印每段的目标速度与实际下发值。
3. 控制端 Foxglove 的 Plot 面板看 `/odom` 线速度：进入重点区间后应**明显下降**，离开后恢复。
4. 实测记录：`lite3 speed list` 期望值 vs Foxglove 实测值，偏差 > 20% 需排查 VOA 限速或参数未生效。

---

## 3. 被控端命令行运行体系

### 3.1 模块 CLI 总表

所有命令在被控端 SSH 终端执行；`lite3` CLI 由 `headless-remote-ops.md` 定义（`ops/bin/lite3`）。

| 模块 | 启动 | 关键参数入口 | 状态查看 | 停止 |
| --- | --- | --- | --- | --- |
| ROS 模式 | `sudo /home/ysc/scripts/switch_ros_version.sh ros2` | — | `systemctl is-active transfer_ros2.service` | 切 `ros1` |
| 运动桥接 | `transfer_ros2.service`（常驻） | systemd | `systemctl status transfer_ros2` | **不建议停** |
| 建图 | `lite3 slam start` | `LITE3_LIDAR`、`LITE3_SLAM_LAUNCH` | `lite3 slam attach` | `lite3 slam stop` |
| 栅格/存图 | `lite3 slam grid` / `lite3 slam save` | `pcd2grid` Z 范围 | `lite3 status` | — |
| 定位+导航 | `lite3 nav start` | `lite_nav2.yaml` | `ros2 node list`、`ros2 topic hz /odom` | `lite3 nav stop` |
| 避障 VOA | 随 `lite3 nav start` 启动 | `config/voa.yaml` | `ros2 topic hz /cmd_vel_corrected` | 随 nav 停止 |
| 烛火检测 | `lite3 detect start` | `fire_detector_params.yaml` | `ros2 topic echo /candle_detected` | `lite3 detect stop` |
| 巡检 | `lite3 patrol start` | `patrol_params.yaml`、`waypoints.json` | `lite3 patrol attach` | `lite3 patrol stop` |
| 速度分区 | （随巡检生效） | `waypoints.json` 的 `speed_zones` | `lite3 speed list` | — |
| 可视化桥 | `lite3 bridge start`（调试用） | 端口 `9090` | `ss -lntp \| grep 9090` | `lite3 bridge stop` |
| 一键总览 | `lite3 status` | — | 环境/会话/地图/连通性/节点/频率/资源 | `lite3 stop`（停全部） |

**systemd 常驻（正式部署）**

```bash
sudo systemctl enable --now fire_detector_ros2.service   # 检测崩溃自愈
sudo systemctl enable --now lite3_patrol.service          # 巡检 Restart=no（避免掩盖故障）
```

### 3.2 无 GUI 化：被移除的图形依赖

| 原做法 | 图形依赖 | 现在 |
| --- | --- | --- |
| `start_slam.sh` 用 `gnome-terminal` 开 3 窗 | X server | tmux 会话 |
| `pcd2grid.launch.py` 起 RViz2 | X server | `gridmap_headless.launch.py` |
| `dr_nav2.launch.py` 起 RViz2 | X server | `nav_headless.launch.py` |
| ROS 1 `track/run_tracker.py` OpenCV 窗口 | X server | 不使用（检测为自研 `fire_detector`，无窗口） |
| 环境残留 `DISPLAY` | 节点挂起等 X | `lite3_env.sh` 显式清空 + offscreen |
| VOA 发布 MarkerArray 可视化 | 带宽 | 可关闭（无 GUI 时无消费者） |

### 3.3 资源优化项

- 去掉 2 个 RViz2：省 **0.5~1 核 CPU、300~600 MB 内存**。
- 检测帧率 5–10 FPS（无需 30 FPS）。
- 点云按需降采样；Foxglove 带宽紧张时关闭 `/rslidar_points` 面板。
- 调试通道（rosbridge）**仅调试时开**，正式巡检前 `lite3 bridge stop`。
- 可视化 bridge 优先跑控制端 → 103 侧开销为 **0**。

---

## 4. 控制端 Foxglove 远程可视化

### 4.1 两条通道

| 通道 | bridge 位置 | 被控端开销 | Foxglove 能力 | 推荐度 |
| --- | --- | --- | --- | --- |
| **A. 控制端 bridge** | 笔记本（需 ROS 2 Humble+） | **零新增进程** | 完整（参数/服务/节点图） | **默认推荐**（最省资源） |
| **B. 103 侧 rosbridge** | 103（Foxy） | +1 Python 进程（JSON 序列化） | 基础（无参数/服务） | **用户指定方案，可用；建议仅调试时开** |

> **关于你提到的 rosbridge 方案**：完全正确且可用——`ros-foxy-rosbridge-server` 在 Foxy 上有官方 apt 包，Foxglove Studio 支持以 **Rosbridge** 类型连接 `ws://192.168.1.103:9090`。
> 唯一需要说明的是：它是 **Python + JSON 序列化**，在 103 这种资源紧张、且要同时跑检测/导航的板子上持续运行会挤占算力——这与"降低 CPU 与内存占用"的目标有张力。因此本文把它定位为**调试通道**，正式巡检前关闭；日常可视化推荐通道 A。

### 4.2 通道 B：103 侧 rosbridge（你的方案）

**被控端（103）**

```bash
# 安装（只需一次）
sudo apt update
sudo apt install -y ros-foxy-rosbridge-server

# 启动（默认端口 9090）
source /opt/ros/foxy/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

# 或指定端口/地址
ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=9090 address:=192.168.1.103
```

> **[待确认]** `rosbridge_websocket_launch.xml` 在 Foxy 中接受的参数名（常见为 `port`、`address`、`ssl`）；以 `ros2 launch rosbridge_server rosbridge_websocket_launch.xml --show-args` 为准。

**验证**：`ss -lntp | grep 9090` 应看到监听。

**停止**：`lite3 bridge stop`（或 `pkill -f rosbridge_websocket`）。

**控制端**

1. 打开 Foxglove Studio（Web app.foxglove.dev 或桌面版）
2. `Open connection` → 选 **Rosbridge**
3. 地址：`ws://192.168.1.103:9090`

> 通道 B 下**控制端无需安装 ROS 2**——这是它最大的便利。

### 4.3 通道 A：控制端 foxglove_bridge（省资源推荐）

```bash
cd ops/foxglove
./bridge.sh              # 标准（含点云）
./bridge.sh --lean       # 精简（不含点云，Wi-Fi 差）
./bridge.sh --docker     # 本机不装 ROS 2
```

连接：`ws://<控制端IP>:8765`，类型 **Foxglove WebSocket**。

> **前提**：控制端需 ROS 2 **Humble 或更新**（Foxy 装不了官方 bridge）。Windows 用户注意：WSL2 默认 NAT，需改 `.wslconfig` 为 `networkingMode=bridged`；否则直接用通道 B。

### 4.4 控制端接入同一 ROS 网络

**通道 A 必须**满足三个一致；通道 B 只需网络可达 9090。

```bash
export ROS_DOMAIN_ID=0                              # ① 与 103 一致
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp        # ② 与 103 一致
export CYCLONEDDS_URI=file://<cyclonedds_peer.xml>  # ③ 组播不通时改单播
```

**自检**

```bash
ros2 topic list | grep -E '^/odom|^/rslidar_points'
```

能看到即已加入同一网络。

**网络要求**

- 控制端与 103 在同一网段（`192.168.1.0/24`）。
- ROS 2 DDS 走 UDP（103 侧已知监听 `7400/7401`），需放通 UDP 7400–7500 与组播。
- 组播被 Wi-Fi 过滤时，用 `cyclonedds_peer.xml` 配置单播 Peer（见 `ops/foxglove/README.md`）。

### 4.5 建议面板

| 面板 | 话题 | 看什么 |
| --- | --- | --- |
| 3D | `/rslidar_points`、`/map`、`/tf` | 建图结果、机器人位姿 |
| Map | `/projected_map` | 二维栅格、路点合理性 |
| Image | `/fire_detector/annotated_image` | 带检测框画面 |
| Raw Messages | `/candle_detected`、`/fire_alert` | 检测与告警 |
| Plot | `/odom` 线速度 | **验证按路段变速是否生效** |
| Diagnostics | `/sensor_status/*` | 传感器存活 |

---

## 5. 检测结果记录、去重与告警回传

### 5.1 检测节点内部去重（已由检测方案定义）

| 机制 | 参数 |
| --- | --- |
| 时序窗口 | 连续 5 帧 ≥3 帧（sensitive）/ ≥4 帧（normal） |
| 空间稳定 | 相邻帧 bbox IoU ≥ 0.3 |
| 中心抖动 | < 30 px |
| 告警冷却 | 2 s |
| 撤销 | 连续 10 帧无检出 → RETRACT |

这一层解决单帧误报，**不解决跨路径点的重复事件**。

### 5.2 巡检层事件去重

| 判据 | 建议默认 |
| --- | --- |
| 地图坐标距离 | `< 1.5 m` |
| 时间窗 | `< 300 s` |
| 等级提升 | 不受去重限制（WARN → ALERT 立即更新并重新告警） |

**烛火世界坐标粗估**：取检测时 TF `map→base_link` 得机器人位姿，用 bbox 水平偏移估方位角，距离按固定估计值（建议 `2.0 m` **[待确认：相机 FOV/焦距]**）。若不追求精度，可用机器人位姿代替，距离阈值放宽到 `2.5 m`。

### 5.3 记录格式（JSONL）

```json
{
  "event_id": "2026-09-15T10:05:33.120-fire-0001",
  "level": "ALERT",
  "first_seen": "2026-09-15T10:05:31.884",
  "last_seen": "2026-09-15T10:05:33.120",
  "map_frame": "map",
  "fire_xy": [3.42, 1.18],
  "robot_pose": {"x": 2.10, "y": 1.35, "yaw": 1.5708},
  "waypoint": "roomA-center",
  "speed_zone": "kitchen-focus",
  "score_max": 0.87,
  "frames_confirmed": 4,
  "snapshot": "/home/ysc/patrol_log/2026-09-15/0001.jpg",
  "dedup_count": 3
}
```

- 目录 `~/patrol_log/<date>/`，JSONL + 快照（**存原分辨率**用于取证）。
- 新增 `speed_zone` 字段：记录事件发生在哪个速度区间，便于事后分析"重点区间是否真的覆盖到了风险点"。

### 5.4 告警与回传

| 层级 | 动作 |
| --- | --- |
| **WARN** | 写日志 + 快照；不中断、不语音；驻留点复核后升级 |
| **ALERT** | 取消 Nav2 目标 → 驻留确认 → 写事件 → 语音（120 `lite3_voice/`）→ 回传 → 人工决定 |
| **RETRACT** | 标记 `cleared`，不删除 |

**回传**：103→上位机既有通道笔记未记录 **[待确认]**。优先本地 JSONL + 拉取；其次可配置 UDP 上报（不与 43893/43897/43899 冲突）。**不要**通过 `jy_exe` 私有端口做告警联动。

---

## 6. 异常处理与降级

| 异常 | 检测 | 处理 |
| --- | --- | --- |
| **建图失败** | `lite3 status` 地图项 FAIL | 见 `headless-remote-ops.md`：无点云查雷达型号；栅格空查 Z 范围；重影降速重扫；**先缩小到单房间验证** |
| **定位丢失** | `/status` + `/aligned_points` + `sensor_checker` | 立即取消 Nav2 目标 → 回建图起点重启定位 → 或启用 `hdl_global_localization`（**默认关闭**，需事先确认可用） |
| **导航受阻** | Nav2 goal abort/超时 | 重试 **2 次** → 跳过该点、记 `missed_waypoints` → 连续多点失败转定位恢复。**禁止无限重试** |
| **速度下发失败** | `ros2 param get` 与期望不符 | 记日志，按 2.7 降级；至少保证全局默认速度可通行 |
| **检测模块无响应** | 心跳超时（默认 10 s） | **降级为"仅巡检不检测"，标记 `detector_unavailable` 区间并提示人工复核**。检测无输出 ≠ 无火情 |
| **bridge 异常** | Foxglove 无数据 | 不影响机器人运行；按 `ops/foxglove/README.md` 排障（先查 DDS 连通性） |
| **全局安全** | — | 保留人工急停，自动化不得覆盖或复位急停 |

---

## 7. 最小可行现场验证

| # | 步骤 | 通过标准 |
| --- | --- | --- |
| **V0** | 静止检测（不动机器人） | `/candle_detected` 有输出；手电/屏幕不触发 ALERT |
| **V1** | 控制端 Foxglove 连通（**在建图前先打通**） | 能看到 103 的话题，3D/Map 面板有数据 |
| **V2** | 单房间建图 | 三件套齐全，栅格墙体连续 |
| **V3** | 单点导航 | 到达误差 ≤ 0.3 m；`/cmd_vel_corrected` 有输出 |
| **V4** | **速度分区验证** | `lite3 speed list` 正确；实测进入重点区间 `/odom` 线速度明显下降并恢复 |
| **V5** | 单点检测联动 | 驻留触发 ALERT，取消后续目标并写事件 |
| **V6** | 多房间全流程（含速度分区） | 全部点位到达或按规则跳过；事件去重正确；日志含 `speed_zone` |
| **V7** | 异常演练 | 遮雷达/堵路/kill 检测进程 → 分别触发降级，机器人安全停下或跳过 |

> **V1 建议提前到 V0 之后**：否则建图时既看不见地图，又分不清是建图坏了还是可视化没通。

---

## 8. 待确认项

| # | 项 | 影响 | 建议 / 确认方式 |
| --- | --- | --- | --- |
| 1 | **Nav2 控制器插件类型（DWB/TEB？）** | 速度参数名 | `ros2 param list /controller_server`；DWB 为 `FollowPath.max_vel_x` |
| 2 | **该参数是否支持动态生效** | 速度分区成败 | `ros2 param set` 后立即 `ros2 param get` 并实测速度 |
| 3 | `lite_nav2.yaml` 现网值 | 全局默认速度 | 巡检建议 ≤ 0.4 m/s，首次验证 0.2 m/s |
| 4 | VOA 避障阈值 | 实际最终速度上限 | 保持现网值 |
| 5 | 雷达型号（C16 / MID360） | 建图与导航 | `LITE3_LIDAR` 覆盖 |
| 6 | `hdl_localization` `/status` 类型 | 定位丢失检测 | `ros2 topic info /status` |
| 7 | 相机 FOV / 焦距 / 安装位姿 | 坐标粗估 | 未标定前用 `d = 2.0 m` |
| 8 | 机器人尺寸 / 转弯半径 | 路点间距 | 距墙 ≥ 0.5 m，点距 ≥ 1.5 m |
| 9 | 控制端形态（Linux/WSL2/Docker） | 通道 A 可行性 | Windows 不愿改桥接 → 用通道 B |
| 10 | Foxy ↔ Humble 跨版本 DDS | 通道 A 成败 | `ros2 topic list` 自检；不通转通道 B |
| 11 | `rosbridge_websocket_launch.xml` 参数名 | 通道 B 配置 | `--show-args` |
| 12 | 103→上位机回传通道 | 告警回传 | 优先本地 JSONL |
| 13 | 机器人遥控方式 | 建图与定位恢复 | 现场确认 |
| 14 | TF 树结构 | 位姿关联 | `ros2 run tf2_tools view_frames` |

---

## 9. 一句话总结

**被控端纯终端跑通"建图 → 路点+速度分区 → Nav2/VOA 巡检（重点区间自动降速并提升检测灵敏度）→ 烛火检测 → 事件去重落盘"，全程无 RViz、无 X、无 gnome-terminal；控制端用 Foxglove 远程看建图、位姿与检测结果——优先把 bridge 跑在笔记本（103 零开销），你熟悉的 rosbridge（103:9090）作为调试通道随时可用；速度分区通过 `waypoints.json` 的 `speed_zones` 用固定值/百分比/减速倍数三种方式配置，由 `patrol_manager` 在每段导航前动态下发 Nav2 控制器限速，且实际速度取 Nav2 与 VOA 的较小值。**
