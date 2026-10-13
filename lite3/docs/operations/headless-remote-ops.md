# Lite3 无头化改造：被控端纯终端 + 控制端 Foxglove 远程可视化

> 目标：把 `docs/operations/indoor-patrol-fire-detection.md` 的执行方案，改造成
> **被控端（103）完全无图形界面、控制端（笔记本）远程可视化**的部署形态。
> 全部操作通过终端完成，不新建独立工程或 ROS 包，直接在原项目上重构。
>
> 依据：`docs/hosts/103-感知导航主机/`、`docs/operations/fire-candle-detection.md`、
> `docs/operations/indoor-patrol-fire-detection.md`；
> foxglove_bridge 支持矩阵来自 ROS Index 与 foxglove/ros-foxglove-bridge 仓库（核查于 2026-09）。

---

## 0. 一句话结论

**被控端用 tmux + 自建 headless launch 彻底去掉 RViz 和 gnome-terminal；
可视化不在 103 上做——`foxglove_bridge` 跑在控制端，通过 DDS 加入同一个 `ROS_DOMAIN_ID=0`
网络，被控端零新增进程。**

这么做不是风格选择，而是被一个硬约束逼出来的：**Foxy 装不了 foxglove_bridge。**

---

## 1. 前提与假设（先说清楚，再动手）

### 1.1 仓库现状：本仓库只有文档

本仓库（`lite3/`）当前**只有 `docs/`、LICENSE、README.md**，真正的 ROS 代码
（`lite_cog_ros2`）在 103 主机上。因此本次改造的产出分两部分：

| 部分 | 位置 | 说明 |
|---|---|---|
| 可部署资产 | `ops/`（仓库内新增） | 拷到 103 即可用，不需要 `colcon build` |
| 说明文档 | 本文档 | 命令流程、原理、待确认项 |

`ops/` 不是新工程、也不是新 ROS 包——launch 文件用**绝对路径**启动，
不引入 `package.xml`/`CMakeLists.txt`。

### 1.2 ROS 版本假设：Foxy + Cyclone DDS + DOMAIN_ID=0

来自 `docs/hosts/103-感知导航主机/概览与环境/主机控制与环境脚本.md`：

- `.ros_version.sh` 当前指向 **ROS 2 Foxy**、Cyclone DDS、`ROS_DOMAIN_ID=0`
- 工作区 `/home/ysc/lite_cog_ros2`，103 IP `192.168.1.103`
- RealSense / transfer / VOA 脚本显式设置 `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`

**所有网络与环境变量都围绕这一组值配置。** 若实机不同，`ops/env/lite3_env.sh` 是唯一改动点。

### 1.3 决定性约束：Foxy 装不了 foxglove_bridge（这是全文最重要的前提）

| 事实 | 证据 |
|---|---|
| ROS 2 版 bridge 已迁到 `foxglove-sdk` | `ros-foxglove-bridge` 仓库 2025-10 起"Remove all references to ROS 2"，现只留 ROS 1 代码 |
| 官方发行版不含 Foxy | ROS Index 的 distro 列表只有 jazzy / kilted / lyrical / rolling / humble |
| 官方明说旧发行版需源码构建 | Foxglove 文档："For ROS 2 distributions older than Humble, you will have to build from source" |
| 旧仓库声明不支持 Humble 之前 | "ROS 1 Melodic and Noetic, and ROS 2 Humble and Rolling. Earlier releases of ROS will not be supported" |

**推论**：在 103 上 "装个 bridge 就能用" 这条路是走不通的。硬要在 Foxy 上源码构建
一个已停止 ROS 2 支持的包，属于给自己埋雷。

### 1.4 由此确定的三条可视化通道

| 通道 | bridge 位置 | 被控端开销 | Foxglove 能力 | 定位 |
|---|---|---|---|---|
| **A. 控制端 bridge** | 笔记本（Humble+） | **零新增进程** | 完整（参数/服务/节点图/assets） | **默认推荐** |
| **B. 103 侧 rosbridge** | 103（Foxy） | +1 个 Python 进程 | 基础（无参数/服务） | 控制端跑不了 ROS 2 时的兜底 |
| **C. MCAP 离线回放** | 无，只录制 | 仅磁盘 I/O | 完整 | 建图复盘、事后取证 |

通道 A 反而更契合"被控端尽量省资源"的初衷：**可视化成本全部转移到笔记本。**

---

## 2. 改造后的目录结构

```
lite3/
├── docs/operations/
│   ├── headless-remote-ops.md          ← 本文档
│   ├── indoor-patrol-fire-detection.md ← 原巡检方案（流程与阈值仍以此为准）
│   └── fire-candle-detection.md        ← 检测方案（算法与阈值仍以此为准）
└── ops/                                ← 新增：被控端运维资产
    ├── README.md
    ├── env/lite3_env.sh                统一环境（无 DISPLAY / Foxy / DDS）
    ├── bin/lite3                       统一 CLI
    ├── scripts/lib_headless.sh         tmux 会话管理与检查函数
    ├── launch/
    │   ├── gridmap_headless.launch.py  PCD→栅格，无 RViz
    │   ├── nav_headless.launch.py      定位+Nav2，无 RViz
    │   ├── fire_detector.launch.py     烛火检测
    │   └── patrol.launch.py            巡检任务
    ├── config/
    │   ├── patrol_params.yaml
    │   ├── fire_detector_params.yaml
    │   ├── cyclonedds_peer.xml
    │   └── waypoints.json
    ├── systemd/
    │   ├── fire_detector_ros2.service
    │   └── lite3_patrol.service
    └── foxglove/
        ├── README.md                   控制端三种通道与排障
        ├── bridge.sh                   控制端启动 bridge
        └── cyclonedds_peer.xml
```

---

## 3. 改动文件清单与关键改动说明

### 3.1 新增（本次产出）

| 文件 | 作用 | 关键改动点 |
|---|---|---|
| `ops/env/lite3_env.sh` | 统一运行环境 | **显式 `unset DISPLAY` + `QT_QPA_PLATFORM=offscreen`**，让任何残留图形依赖快速失败而非挂起；统一 `ROS_DOMAIN_ID=0` / Cyclone DDS / 日志目录 |
| `ops/bin/lite3` | 统一 CLI | 建图/导航/检测/巡检/路点/录制/状态/停止 八类子命令，全部无 GUI |
| `ops/scripts/lib_headless.sh` | 公共函数 | tmux 会话管理、地图三件套检查、120 连通性检查 |
| `ops/launch/gridmap_headless.launch.py` | PCD→栅格 | **去掉 RViz2**，只保留 octomap_server + map_saver_server + lifecycle_manager |
| `ops/launch/nav_headless.launch.py` | 定位 + Nav2 | **改用 `nav2_bringup/navigation_launch.py`**（官方"纯导航"入口，不含 RViz、不含 AMCL），自配 map_server + hdl_localization |
| `ops/launch/fire_detector.launch.py` | 烛火检测 | 参数外置到 YAML；`env={"DISPLAY": ""}` 双保险；可关带框图像省带宽 |
| `ops/launch/patrol.launch.py` | 巡检任务 | 路点文件与行为参数全部 launch 参数化 |
| `ops/config/patrol_params.yaml` | 巡检行为 | 重试上限、驻留时长、去重距离、告警动作、日志目录 |
| `ops/config/fire_detector_params.yaml` | 检测阈值 | 沿用检测方案第 5 节，不另起一套；normal/sensitive 双档 |
| `ops/config/waypoints.json` | 巡检路点 + **速度分区** | **v2**：`defaults`（全局默认速度）+ `waypoints` + `speed_zones`（区间限速，支持 absolute/percent/divisor） |
| `ops/config/cyclonedds_peer.xml` | DDS 单播配置 | 组播被 Wi-Fi 过滤时的救命配置 |
| `ops/foxglove/bridge.sh` | 控制端 bridge | 自动装 bridge、做 DDS 连通性自检、话题白名单控带宽 |
| `ops/foxglove/README.md` | 控制端接入 | 三种通道、三种控制端形态、面板配置、排障表 |
| `ops/systemd/*.service` | 常驻管理 | 检测崩溃自愈；巡检**不自动重启**（避免掩盖故障） |
| `ops/README.md` | 部署说明 | 拷贝、装 tmux、改 `.bashrc`、参数入口索引 |

### 3.2 被替代的旧流程（不再使用）

| 旧入口 | 问题 | 替代 |
|---|---|---|
| `slam/start_slam.sh` | 用 `gnome-terminal` 开三个窗口，纯 SSH 直接失败 | `lite3 slam start`（tmux 会话） |
| 在 gridmap 终端敲 `1` | 需要人在机器人旁 | `lite3 slam grid` |
| 在 save-map 终端敲 `2` | 同上；且脚本先 `rm` 后保存 | `lite3 slam save`（**先自动备份**再保存） |
| `nav/start_nav.sh` → `lite_localization.launch.py` | 链路末端固定起 RViz2 | `lite3 nav start` → `nav_headless.launch.py` |
| RViz2 中读位姿手填路点 | 必须有 GUI | `lite3 waypoint add <name>`（TF 读取 + 写 JSON） |
| `ros2 launch fire_detector ...`（硬编码参数） | 参数改一次要动代码 | 参数外置 `fire_detector_params.yaml` |

### 3.3 明确不动的部分

`transfer_ros2.service`、`jetson2motion`、`sensor_checker`、VOA、120 侧
`rtsp_stream.service` / `jy_exe.service` 全部保持原样。
告警仍走"取消 Nav2 目标"的任务层中断，**不抢占 `/cmd_vel`**。

---

## 4. 图形依赖是怎么被移除的

| 原做法 | 依赖 | 现在 |
|---|---|---|
| `start_slam.sh` 用 `gnome-terminal` 开 3 个终端 | X server | tmux 会话（SSH 断开不丢进程） |
| `pcd2grid.launch.py` 起 RViz2 | X server | `gridmap_headless.launch.py` |
| `dr_nav2.launch.py` 起 RViz2 | X server | `nav_headless.launch.py` |
| 环境里残留 `DISPLAY` | 节点挂起等 X | `lite3_env.sh` 显式清空 + offscreen 兜底 |

**验证**：任何时刻执行 `ros2 node list | grep -i rviz` 应为空。

**省下来的资源**（103 是 Jetson，6.7 GiB 内存且要同时跑定位/Nav2/VOA/检测）：
去掉建图与导航各一个 RViz2 实例，约省 **0.5~1 核 CPU 与 300~600 MB 内存**。
通道 A 下 bridge 也不在 103 上跑，这部分开销为 **0**。

---

## 5. 被控端完整终端命令流程

### 5.0 首次部署（只做一次）

```bash
# 从开发机拷贝
scp -r ops/ ysc@192.168.1.103:/home/ysc/lite_cog_ros2/ops/

# 在 103 上（SSH）
sudo apt update && sudo apt install -y tmux      # 唯一新增依赖

cat >> ~/.bashrc <<'EOF'
export OPS_DIR=/home/ysc/lite_cog_ros2/ops
export PATH="$OPS_DIR/bin:$PATH"
source $OPS_DIR/env/lite3_env.sh
EOF
source ~/.bashrc

# 确认 ROS 2 模式与 transfer
sudo /home/ysc/scripts/switch_ros_version.sh ros2
systemctl is-active transfer_ros2.service        # 期望 active

lite3 status                                     # 环境自检
```

> `.bashrc` 不要再追加其它 ROS 变量：`switch_ros_version.sh` 会**覆盖式**改写
> `.ros_version.sh`，手工追加的内容会丢。

### 5.1 建图

```bash
# 启动（默认 Leishen C16；Livox MID360 用 LITE3_LIDAR=livox）
lite3 slam start

# 查看各窗口输出（Ctrl-b d 脱离，Ctrl-b n/p 切窗口）
lite3 slam attach

# 遥控机器人慢速走遍所有房间与门口（≤ 0.3 m/s）
#   [待确认] 实机遥控方式（手柄 / 上位机 / 120 私有指令）

# 生成二维栅格
lite3 slam grid

# 控制端 Foxglove 里确认 /projected_map 墙体连续、门口可通行后，保存地图
lite3 slam save            # 自动备份旧图 → 保存 → 校验三件套
```

**成功判据**：`lite3 status` 的"地图三件套"三项全 `[OK]`；
控制端 Foxglove 的 Map/3D 面板里墙体连续、房间连通。

### 5.2 路点录制

```bash
lite3 nav start            # 先起导航与定位（见 5.3）
# 遥控机器人到目标位置并调整朝向后：
lite3 waypoint add roomA-center
lite3 waypoint add doorway-A-B
lite3 waypoint list        # 查看当前 JSON
```

`waypoints.json` 可直接编辑；`dwell_sec: 0` 表示只途经不停留（门口用）。
布点规则沿用原方案：房间内 `sensitive`、门口走廊 `normal`、点距墙 ≥ 0.5 m、点间距 ≥ 1.5 m。

**同时规划"重点区间慢速"**（v2 新增，详见 `indoor-patrol-fire-detection.md` 第 2 节）：
在 `speed_zones` 里给需要重点检查的路段单独配速度，三种写法任选：

```json
"speed_zones": [
  {"name": "kitchen-focus", "range": [3, 5], "speed": {"mode": "percent",  "value": 40},   "detect_mode": "sensitive"},
  {"name": "roomA-approach","range": [1, 2], "speed": {"mode": "absolute", "value": 0.15}},
  {"name": "corridor-slow", "range": [5, 6], "speed": {"mode": "divisor",  "value": 2.5}}
]
```

- `range: [a, b]` 覆盖 `a→a+1 … b-1→b` 的全部连续路段；`loop` 下 `a > b` 自动环绕。
- 多区间重叠**取最慢**；未命中用 `defaults.max_speed`。
- 慢速区间建议同时设 `detect_mode: sensitive`——画面更稳，时序判定更可靠。

### 5.3 导航 + 检测 + 巡检

**启动顺序不能颠倒**：

```bash
lite3 nav start            # 雷达 → RealSense → 定位+Nav2 → VOA
lite3 status               # 等 ~10s 后确认节点与话题
lite3 detect start         # 烛火检测（拉 rtsp://192.168.1.120:8554/test）
lite3 patrol start         # 最后启动巡检任务
```

全程可 `lite3 <子系统> attach` 回看输出，`Ctrl-b d` 安全脱离。

**成功判据**（`lite3 status` 一次看完）：

- `ros2 node list` 中 `hdl_localization`、`nav2`、`voa`、`jetson2motion`、`fire_detector` 均在
- `/odom` 有输出且与机器人实际运动一致
- 导航时 `/cmd_vel_corrected` 非零（说明 VOA 已接管）
- `ros2 node list | grep -i rviz` 为空

### 5.4 状态查看与停止

```bash
lite3 status               # 环境 / 会话 / 地图 / 连通性 / 节点 / 话题频率 / 资源
lite3 speed list           # 每条路段的生效速度（解析 waypoints.json）
lite3 speed zones          # 列出 speed_zones 定义
lite3 speed check          # 校验 order 引用、重叠冲突、越界值
lite3 detect stop          # 单独停某个子系统
lite3 nav stop
lite3 bridge stop          # 停可视化桥（正式巡检前务必关，见 6.2）
lite3 stop                 # 停全部（不动 transfer_ros2.service）
```

**速度下发是否生效的验证**（重点区间是否真的慢下来）：

```bash
ros2 param get /controller_server FollowPath.max_vel_x   # 与 lite3 speed list 期望值比对
```

> **[待确认]** 参数名随 Nav2 控制器插件而变：DWB 为 `FollowPath.max_vel_x`，
> TEB/其他需 `ros2 param list /controller_server` 确认。若参数不支持动态生效，
> 降级方案见 `indoor-patrol-fire-detection.md` 2.7。
> 实际速度还受 VOA 限速：最终 = **min(Nav2, VOA)**。

**用 systemd 常驻**（可选，适合正式部署）：

```bash
sudo cp ops/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fire_detector_ros2.service
sudo systemctl status fire_detector_ros2.service
```

> 巡检服务故意设 `Restart=no`：任务中途自动重启会让机器人从当前点重来，
> 掩盖真实故障，需要人工确认后再拉起。

---

## 6. 控制端接入与 Foxglove 查看

### 6.1 加入同一 ROS 网络（三个必须一致）

```bash
export ROS_DOMAIN_ID=0                               # ① 与 103 一致
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp         # ② 与 103 一致
export CYCLONEDDS_URI=file://<cyclonedds_peer.xml>   # ③ 组播不通时改单播
```

跨发行版（Foxy ↔ Humble）DDS 对标准消息类型是通的，但**必须实测**：

```bash
ros2 topic list | grep -E '^/odom|^/rslidar_points'
```

能看到即说明已加入同一网络。看不到 → 见 `ops/foxglove/README.md` 排障表。

### 6.2 启动 bridge

```bash
cd ops/foxglove
./bridge.sh              # 标准：含点云
./bridge.sh --lean       # 精简：不含点云，Wi-Fi 差时用
./bridge.sh --docker     # 本机不装 ROS 2
```

脚本会自动：装 `foxglove_bridge` → 加载环境 → 做 DDS 连通性自检 → 打印连接地址。

**控制端形态选择**（Windows 用户重点看）：

| 形态 | 要求 | 坑 |
|---|---|---|
| 原生 Ubuntu 22.04/24.04 | ROS 2 Humble 或 Jazzy | 最省事，推荐 |
| WSL2 | Ubuntu 22.04 + **桥接网络** | 默认 NAT，必须改 `.wslconfig` 为 `networkingMode=bridged` |
| Docker | `--net host` | Windows Docker Desktop 同样受 WSL2 NAT 限制 |

### 6.3 通道 B：103 侧 rosbridge（Foxy 可用，调试用）

当控制端跑不了 ROS 2（Windows 且不愿改 WSL2 桥接、或不想装 ROS）时，用这条。
**优点**：控制端零安装，Foxglove 直接连。
**代价**：103 上多一个 Python 进程做 JSON 序列化，**与"给机器人省资源"相冲突**——
因此定位为**调试通道，正式巡检前必须 `lite3 bridge stop`**。

**被控端（103）**

```bash
# 安装（只需一次）
sudo apt update
sudo apt install -y ros-foxy-rosbridge-server

# 启动（默认 9090）
source /opt/ros/foxy/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml

# 需要时指定端口 / 绑定地址
ros2 launch rosbridge_server rosbridge_websocket_launch.xml port:=9090 address:=192.168.1.103
```

> **[待确认]** Foxy 中该 launch 接受的参数名（常见 `port` / `address` / `ssl`），
> 以 `ros2 launch rosbridge_server rosbridge_websocket_launch.xml --show-args` 为准。

**验证与停止**

```bash
ss -lntp | grep 9090        # 应看到监听
lite3 bridge stop           # 停止（或 pkill -f rosbridge_websocket）
```

**安全提醒**：rosbridge 无认证。建议绑定业务网地址 `192.168.1.103`（而非 `0.0.0.0`），
避免经 `p2p0` 热点或 `wlan0` 上行暴露到外部网络。

### 6.4 Foxglove Studio 连接

1. 打开 Foxglove（Web app.foxglove.dev 或桌面版）
2. `Open connection` → 选 **Foxglove WebSocket**
3. 地址填 `ws://<控制端IP>:8765`（bridge 跑在本机则 `ws://localhost:8765`）
4. 通道 B 例外：地址 `ws://192.168.1.103:9090`，类型选 **Rosbridge**

**建议面板配置**：

| 面板 | 话题 | 看什么 |
|---|---|---|
| 3D | `/rslidar_points`、`/map`、`/tf` | 建图结果、机器人位姿 |
| Map | `/projected_map` | 二维栅格俯视图、路点合理性 |
| Image | `/fire_detector/annotated_image` | 带检测框的实时画面 |
| Raw Messages | `/candle_detected`、`/fire_alert` | 检测结果与告警 |
| Plot | `/odom` 线速度/角速度 | 导航是否卡住 |
| Diagnostics | `/sensor_status/*` | 传感器存活 |

> 点云很吃带宽。Wi-Fi 差时先关掉 `/rslidar_points`，只留 `/tf` + `/map`，
> 定位与地图照样看得清楚。

---

## 7. 关键参数入口

| 想改什么 | 改哪里 | 生效方式 |
|---|---|---|
| 检测阈值 / 图像源 / FPS | `ops/config/fire_detector_params.yaml` | `lite3 detect stop && lite3 detect start` |
| 驻留时长 / 重试次数 / 去重距离 | `ops/config/patrol_params.yaml` | `lite3 patrol stop && lite3 patrol start` |
| 巡检点位 | `ops/config/waypoints.json` 或 `lite3 waypoint add` | 同上 |
| **重点区间慢速（分区速度）** | `waypoints.json` 的 `speed_zones`（absolute/percent/divisor） | `lite3 speed check` 校验 → 重启 patrol；每段导航前自动下发 |
| Nav2 全局默认速度 / 代价地图 | dr_nav2 包内 `lite_nav2.yaml`（`FollowPath.max_vel_x`） | 重启 nav 会话 |
| 路段落速是否生效 | `ros2 param get /controller_server FollowPath.max_vel_x` | 与 `lite3 speed list` 比对 |
| RTSP 地址 | 环境变量 `LITE3_RTSP_URL` | 重启 detect 会话 |
| 雷达型号 | `LITE3_LIDAR=leishen\|livox` | 重启 slam/nav 会话 |
| Faster-LIO launch 名 | `LITE3_SLAM_LAUNCH=...` | 重启 slam 会话 |

---

## 8. 验证清单

| # | 步骤 | 通过标准 |
|---|---|---|
| **H0** | `lite3 status` | 环境、地图、连通性各项无 `[FAIL]`；无 rviz 节点 |
| **H1** | `lite3 slam start` → attach | 三个窗口均有输出，无 `cannot connect to display` 报错 |
| **H2** | `lite3 slam grid` | Foxglove 的 `/projected_map` 出现栅格，墙体连续 |
| **H3** | `lite3 slam save` | 三件套全 `[OK]`；旧图已备份到 `map/backup/` |
| **H4** | 控制端 `./bridge.sh` 自检 | 能看到 103 的话题 |
| **H5** | Foxglove 连 `ws://<控制端IP>:8765` | 3D/Map/Image 面板均有数据 |
| **H6** | `lite3 nav start` + `lite3 detect start` | `/odom`、`/cmd_vel_corrected`、`/candle_detected` 均有输出 |
| **H6b** | **速度分区**：`lite3 speed check` → 巡检 | `speed check` 无报错；进入重点区间后 Foxglove 的 `/odom` 线速度明显下降并恢复 |
| **H7** | `lite3 patrol start` | 按路点顺序导航，到点驻留，事件写入 `~/patrol_log/`（含 `speed_zone` 字段） |

> **H4 是最容易卡住的一步**，卡住就改单播 Peer（见 `ops/foxglove/README.md`）。
> 建议在做任何机器人动作之前先打通 H4/H5——否则建图时你既看不见地图，
> 又分不清是建图坏了还是可视化没通。

---

## 9. 待确认项

| # | 待确认项 | 影响 | 确认方式 / 建议默认 |
|---|---|---|---|
| 1 | 控制端形态（原生 Linux / WSL2 / Docker） | 通道 A 可行性 | 若 Windows 且不愿改 WSL2 桥接 → 直接用通道 B |
| 2 | Foxy ↔ Humble 跨发行版 DDS 实测 | 通道 A 成败 | `ros2 topic list`；不通则转通道 B |
| 3 | 103 与控制端网卡名 | 单播 Peer 配置 | `ip addr`；103 常见 `wlan0`/`p2p0` |
| 4 | `octomap_server` 可执行名 | `gridmap_headless.launch.py` | `ros2 pkg executables octomap_server` |
| 5 | `hdl_localization` 可执行名 | `nav_headless.launch.py` | `ros2 pkg executables hdl_localization`；原文档记为 `hdl_localization_composition` |
| 6 | dr_nav2 是否支持 `use_rviz:=false` | 若支持可省掉自建 launch | `ros2 launch dr_nav2 dr_nav2.launch.py --show-args` |
| 7 | Faster-LIO launch 文件名 | `lite3 slam start` | `LITE3_SLAM_LAUNCH` 覆盖，默认 `mapping_c16.launch.py` |
| 8 | 雷达型号（C16 / MID360） | 建图与导航 | `LITE3_LIDAR` 覆盖，默认 `leishen` |
| 9 | 实机各子工作区目录名 | `lite3_env.sh` 的 overlay 循环 | 按 `lite_cog_ros2` 下实际 `install/` 调整 |
| 10 | `patrol_manager` / `fire_detector` 包已建立 | 巡检与检测能否启动 | 两者原方案中即为"待新建"，本文档只给 launch 与参数骨架 |
| 11 | 机器人遥控方式 | 建图与定位恢复 | 现场确认（手柄 / 上位机 / 120 私有指令） |
| 12 | **Nav2 控制器插件类型（DWB / TEB / 其他）** | 速度分区参数名 | `ros2 param list /controller_server`；DWB 为 `FollowPath.max_vel_x` |
| 13 | **该速度参数是否支持动态生效** | 速度分区成败 | `ros2 param set` 后立即 `get` 并实测；不生效则按主方案 2.7 降级 |
| 14 | `rosbridge_websocket_launch.xml` 参数名 | 通道 B 端口/地址配置 | `--show-args` |
| 15 | 103 侧 VOA 实际限速值 | 区间速度的最终上限 | 实际速度 = min(Nav2, VOA) |

---

## 10. 风险与边界

1. **不要让 103 上出现任何 GUI 进程**。若 `ros2 node list` 里出现 rviz，说明走了旧脚本，
   先 `lite3 stop` 再用新流程。
2. **通道 B（rosbridge）只在调试时开**。它是 Python + JSON 序列化，
   在 103 这种资源紧张的板子上持续跑会挤压检测与导航的算力；正式巡检前 `lite3 bridge stop`。
3. **`lite3 slam save` 前务必确认栅格正确**。`save_map.sh` 会无确认删除旧 YAML/PGM，
   本 CLI 已加自动备份，但仍需人工确认栅格质量。
4. **检测无输出 ≠ 无火情**。RTSP 流断、检测进程挂都会表现为"没有检测结果"。
   `patrol_params.yaml` 的 `detector_heartbeat_timeout_sec` 会标记 `detector_unavailable`
   区间，运维时必须复核这些区间，否则造成假阴性。
5. **人工急停优先级最高**，本方案任何自动化行为都不得覆盖或自动复位急停。
6. **跨发行版 DDS 属于"能用但不被官方保证"的组合**。重要任务前先跑一次 H4 自检；
   长期看，103 升级到 Humble 才是根治（同时能直接在 103 上用官方 bridge）。

---

## 11. 一句话总结

**被控端：tmux 会话 + 自建 headless launch 干掉 RViz 与 gnome-terminal，`lite3` 一条命令管
建图/导航/检测/巡检/**速度分区**/状态/停止，全程零 GUI；控制端：`foxglove_bridge` 跑在笔记本上，靠
`ROS_DOMAIN_ID=0` + Cyclone DDS 加入同一网络，`ws://<控制端IP>:8765` 连接——因为 Foxy
根本装不了官方 bridge，把可视化成本挪出机器人反而是更优解；控制端实在跑不了 ROS 2 时，
退回 103 侧 rosbridge（`apt install ros-foxy-rosbridge-server`，`ws://192.168.1.103:9090`）
或 MCAP 离线回放；**rosbridge 会让 103 多一个 Python 进程做 JSON 序列化，正式巡检前务必
`lite3 bridge stop`**。重点区间的慢速通过 `waypoints.json` 的 `speed_zones` 配置，由
`patrol_manager` 在每段导航前动态下发 Nav2 控制器限速，实际速度取 min(Nav2, VOA)。**
