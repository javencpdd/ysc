# ROS Topic 数据源（ros 模式）部署说明

## 背景

103 上的 `transfer_ros2` 是宇树官方 ROS2 桥接节点，它**已经**在监听 UDP 43897
并把机器人状态发布为 ROS topic（`/leg_odom2`、`/imu/data`、`/joint_states` …）。
中控后端（`lite3_robot_monitor`）默认走 **sniff 旁路抓包**读取同一份原始 UDP。

本项目的 `ros` 数据源模式让中控后端**改为订阅这些 ROS topic**，从而：

- 完全不碰 43897 端口，与 `transfer_ros2` 彻底解耦；
- 拿到的已是结构化消息（odom / imu / joint），无需再解析私有协议；
- 中控页面可在「ROS 话题订阅」与「sniff 旁路抓包」之间一键切换。

> 注意：`transfer_ros2` 本身**不要改**——它的职责就是 UDP 43897 → ROS topic，
> 改了反而会让 Nav2 失去本体里程计。我们要做的是让中控后端去「订阅它已发布的 topic」。

## 架构

```
机器人固件 (192.168.1.120)
      │  UDP 43897（私有协议）
      ▼
transfer_ros2  ──发布──►  /leg_odom2  /imu/data  /joint_states
      │                          │
      │                   ros_bridge_node.py（本仓库，运行在 ROS2 环境）
      │                          │ UDP JSON（本地 127.0.0.1:43900）
      ▼                          ▼
   Nav2                  lite3_robot_monitor  (data_source.RosBridgeSource)
                          └─ StateManager ─► /ws/state ─► 中控页面
```

`ros_bridge_node.py` 在 ROS2 环境里跑（订阅 topic），把消息转成中控后端能直接
消费的 JSON，通过**本地 UDP** 转发。中控后端因此无需依赖 rclpy / ROS2 环境，
二者只用本地 UDP 解耦。

## 中控后端配置

环境变量（`backend/config.py` 的 `DataSourceConfig`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `LITE3_DATA_SOURCE` | `auto` | `auto`/`ros`/`sniff`/`bind`；`auto` = **ros 为主 + sniff 兜底，且双向自愈**（见下节） |
| `LITE3_ROS_BRIDGE_HOST` | `127.0.0.1` | ros_bridge_node 转发到的本地地址 |
| `LITE3_ROS_BRIDGE_PORT` | `43900` | 本地桥接端口 |
| `LITE3_ROS_STALE_TIMEOUT` | `10.0` | ros 曾正常但随后断流时，静默多少秒判定失效并降级 |
| `LITE3_ROS_RETRY_INTERVAL` | `15.0` | 处于 sniff 兜底时，每隔多少秒探测一次 ros 是否已恢复 |

### `auto` 模式的双向自愈

策略是「**ROS topic 订阅为主 + sniff 旁路抓包兜底**」，且**不是一次性降级**：

```
        ros 正常 ────────────────────────────────►
           │                                      │
   ros 无数据（> link_timeout）          ros 恢复 且探测到数据
   或断流 > LITE3_ROS_STALE_TIMEOUT            （每 15s 试一次）
           │                                      │
           ▼                                      │
        sniff 兜底 ◄───────────────────────────────
```

两个方向的关键实现（`backend/main.py` 的 `MonitorService`）：

- **降级**：覆盖两种情形——① ros 从未产出数据（桥接没起 / topic 名不匹配），
  按 `LITE3_LINK_TIMEOUT` 快速判定；② ros 先正常、**后来才断流**（`transfer_ros2`
  重启、ROS 抖动），按距最后一帧的时间判定。早期版本只看"有没有收到过帧"，
  会把情形 ② 漏掉，导致页面停在陈旧数据上。
- **恢复**：回退 sniff 后仍周期性探测 ros。**探测不丢数据**——sniff 走 AF_PACKET
  不占用端口，所以可以临时 bind 桥接端口收一个包再释放，无需停掉正在工作的 sniff。

> 为什么"端口上有包"就能代表 ROS 活着：`ros_bridge_node.py` 的 `_flush_state()`
> 由 `_dirty` 标记门控，只有真正收到 topic 回调时才发送，**topic 一停就立刻静默**。
> 所以不会把陈旧缓存误判为已恢复。

运行时切换（中控页面开关调用）：

```
POST /api/source/set?mode=ros      # 切到 ROS 话题订阅
POST /api/source/set?mode=sniff    # 切回 sniff 旁路抓包
GET  /api/source                  # 查看当前/配置模式
```

> 手动调用 `/api/source/set` 会重置自动降级标记，从手动指定的模式重新开始。

## 运行 ros_bridge_node（在 103 的 ROS2 终端）

```bash
source /opt/ros/<distro>/setup.bash
# 若使用了 colcon 工作区，还需： source <ws>/install/setup.bash
python3 backend/ros_bridge_node.py \
    --imu /imu/data --odom /leg_odom2 --joints /joint_states \
    --host 127.0.0.1 --port 43900
```

topic 名若与 103 实际发布的不一致，用参数覆盖即可。

## ros 模式与 sniff 模式的差异

| 维度 | sniff（旁路抓包） | ros（话题订阅） |
|------|-------------------|-----------------|
| 端口占用 | 不占 43897（AF_PACKET） | 不占 43897（订阅 topic） |
| 数据完整度 | 完整私有协议（含状态机/电池/超声波） | 仅 odom/imu/joint，状态机字段为默认值 |
| 依赖 | 需 CAP_NET_RAW | 需 `transfer_ros2` + `ros_bridge_node` 在跑 |
| 适用 | 调试 / 全保真 | 正常监控 / 与 Nav2 同生态 |

> 简言之：ros 模式给「干净、结构化、与导航同生态」的监控；sniff 模式给「完整私有协议保真」。
> 二者可运行时互切，互不影响 `transfer_ros2`。

## 部署到 103（持久化）

后端改动（含 `data_source.py` / `main.py` 的 `/api/source` 接口、前端 `dist`）按常规方式
同步到 103 的 `/home/test/monitor` 并 `systemctl restart lite3-monitor` 即可；前端已
用 `npm run build` 重新构建，新的「监听模式」开关已包含在 `frontend/dist`。

`ros_bridge_node.py` 需要在 103 的 ROS2 环境里常驻运行（否则 ros 模式收不到数据，
后端 `auto` 会自动回退 sniff）。本仓库提供了两个部署辅助文件：

| 文件 | 作用 |
|------|------|
| `deploy/lite3-ros-bridge.service` | systemd 单元，把 `ros_bridge_node.py` 作为常驻服务，开机自愈、崩溃重启 |
| `deploy/deploy_103.sh` | 一键 rsync 同步 `backend/` + `frontend/dist` 到 103 并重启服务 |

**安装 ros 桥接服务（在 103 上，install.sh 会自动处理）：**

```bash
# 已随 install.sh 自动注册并启动；手动操作等同：
sudo cp deploy/lite3-ros-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lite3-ros-bridge
journalctl -u lite3-ros-bridge -f
```

**一键同步（在本机，替代 pack.sh 的增量方式）：**

```bash
LITE3_HOST=ysc@192.168.1.103 bash deploy/deploy_103.sh
```

> ⚠️ `deploy/` 下的文件已对齐 103 实测参数：用户名 `ysc`、IP `192.168.1.103`、
> 目录 `/home/test/monitor`。`lite3-ros-bridge.service` 与 `lite3-monitor.service`
> 共用 `__DIR__`/`__USER__`/`__GROUP__`/`__HOME__` 占位符，由 `install.sh` 自动替换。
> 仍需你按 103 实际环境确认的两点：① ROS 发行版目录（ExecStart 用 `ls /opt/ros/*/setup.bash`
> 自动探测，若装在别处请改路径）；② topic 名是否真是 `/imu/data` `/leg_odom2` `/joint_states`
> （不一致可改 `--imu/--odom/--joints` 参数，或直接用 `/api/source` 切回 sniff）。
> 若 `transfer_ros2` 在 103 上是 systemd 服务，建议在 `lite3-ros-bridge.service` 里把
> `After`/`Wants` 指向它，保证启动顺序。

## 附：内嵌订阅模式 `ros_direct`（去掉 lite3-ros-bridge）

### 什么时候该用它

`ros` 模式多一个进程、一跳本地 UDP、一个 systemd 单元，换来的是「后端不依赖 ROS 环境」——
这在需要 Windows 开发机直接跑后端时是必要的。

**若确认只在 103 上运行**，这一层就可以省掉：让后端进程自己 `import rclpy` 订阅 topic。
这就是 `ros_direct` 模式（103 实测为 **ROS 2 Foxy / Ubuntu 20.04 / Python 3.8**）。

### 两种模式对照

| 维度 | `ros`（桥接） | `ros_direct`（内嵌） |
|------|---------------|----------------------|
| 进程数 | monitor + ros_bridge_node | 仅 monitor |
| systemd 单元 | 2 个（含 BindsTo/PartOf 绑定） | 1 个 |
| 数据路径 | topic → 桥接 → 本地 UDP 43900 → 后端 | topic → 后端（进程内队列） |
| 后端依赖 | 无需 ROS 环境 | 必须 source ROS 后启动 |
| 跨平台 | Windows 开发机可直接跑 | 仅 103 |
| 故障域 | ROS 异常不影响 Web | 同进程，靠看门狗降级兜底 |
| 数据完整度 | 相同（都只有 odom/imu/joint） | 相同 |
| 恢复判定 | 探测 43900 是否有包 | 读常驻节点的「最后消息时间」 |

### 启用方式

```bash
# 安装时指定（推荐，install.sh 会自动换用 lite3-monitor-rosdirect.service 模板）
LITE3_ROS_IMPL=direct sudo -E bash deploy/install.sh /home/test/monitor

# 或已装好后改环境变量（drop-in 方式，避免被 install.sh 覆盖）
sudo systemctl edit lite3-monitor
#   [Service]
#   Environment=LITE3_DATA_SOURCE=auto
#   Environment=LITE3_ROS_IMPL=direct
```

相关环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `LITE3_ROS_IMPL` | `bridge` | `bridge` 外部桥接 / `direct` 内嵌订阅；仅影响 `auto` |
| `LITE3_DATA_SOURCE` | `auto` | 显式写 `ros_direct` 则强制内嵌（此时不做自动降级） |
| `LITE3_ROS_NODE_NAME` | `lite3_monitor_ros` | ROS 节点名，**多实例必须不同** |
| `LITE3_ROS_TOPIC_IMU` | `/imu/data` | 与 transfer_ros2 实际发布的一致 |
| `LITE3_ROS_TOPIC_ODOM` | `/leg_odom2` | 同上 |
| `LITE3_ROS_TOPIC_JOINTS` | `/joint_states` | 同上 |

### 部署要点（最容易踩的坑）

1. **ExecStart 必须先 source ROS**：venv 的 python 靠 `setup.bash` 设的 `PYTHONPATH`
   才能 import 到 rclpy。`lite3-monitor-rosdirect.service` 已处理。
2. **source 之后要把 venv 的 site-packages 提到 `PYTHONPATH` 最前**：
   `/opt/ros/foxy` 自带 numpy / PyYAML 等，会遮住 venv 里安装的版本。模板已处理。
3. **多实例并行**：要么 `LITE3_ROS_NODE_NAME` 各不相同，要么用 `ROS_DOMAIN_ID` 隔离。
4. **保持 `LITE3_DATA_SOURCE=auto`**：ROS 断流时自动回退 sniff，恢复后再切回，
   这是内嵌模式「同进程故障域」的安全网。显式写 `ros_direct` 则不做自动降级。

### 为什么内嵌模式恢复得更快

降级到 sniff 后，ROS 节点**并不销毁**，仍在后台收 topic 并更新「最后消息时间」。
看门狗只需读这个时间戳即可判定恢复（对应 bridge 模式的「43900 上有包」），
既不用停掉正在工作的 sniff，也不用重建节点再等首帧。

### 回退到桥接模式

```bash
sudo systemctl edit lite3-monitor   # 把 LITE3_ROS_IMPL 改回 bridge
sudo systemctl daemon-reload && sudo systemctl restart lite3-monitor
```

代码层面两者共用同一套转换实现（`backend/ros_topic_adapter.py`），不会出现两份逻辑漂移。
