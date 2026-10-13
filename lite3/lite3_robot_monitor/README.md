# Lite3 Robot Monitor

  git config --global user.email "1904650862@qq.com"
  git config --global user.name "jack"


> **版本边界**：本目录是 `lite3` 笔记库保留的早期监控应用及前端原型，不是 103 主机功能复现仓库的完整当前部署版本。本目录有 `frontend/`，但没有下文历史说明中提到的 `deploy/` 和部分后端文件。部署 103 时请先核对 `/home/jack/lite3Code/lite3_robot_monitor/` 的实际文件及其文档；本库与代码库的对应关系见 [协作索引](../docs/codebase-map.md)。

把原先基于 **Python Tkinter** 的 Lite3 状态接收工具（`script/lite3_robot_state_receiver.py`）改造成 **前后端分离的 Web 监控系统**。

> 通过浏览器访问监控页面，即可实时查看 Lite3 四足机器人通过 UDP 上报的状态数据。

> **新人先读这里**
> - 想快速部署 → [QUICKSTART.md](QUICKSTART.md)：克隆 → 构建 → 安装 → 验证，10 分钟版
> - 部署踩坑与排错 → [note/](note/README.md)：按环境搭建 / 构建 / 通信 / 调试 / 运维分章，
>   每条含「现象 → 原因 → 解决 → 规避」

---

## 一、架构总览

```text
Lite3 机器人本体（120 运动主机）
      │
      ├─── UDP 二进制报文 (0x0901 / 0x0902 / 0x0903) ───┐
      │                                                │
      │    ① sniff        AF_PACKET 旁路抓包，不占端口   │
      │    ② bind         bind 43897（无 CAP_NET_RAW 时兜底）│
      │                                                │
      └─── transfer_ros2（官方节点：UDP → ROS topic）────┤
                /leg_odom2  /imu/data  /joint_states    │
                  │                                     │
                  ├─ ③ ros         ros_bridge_node.py 独立进程
                  │                → 本地 UDP JSON :43900
                  └─ ④ ros_direct  ros_direct_source.py 内嵌 rclpy 订阅
                                                        │
      ┌─────────────────────────────────────────────────┘
      ▼
┌─────────── data_source.py：四种数据源统一接口 ───────────┐
│  raw 帧（sniff / bind，需 parser）                       │
│  parsed 帧（ros / ros_direct，已是结构化 dict）          │
│  auto：ros 系为主 + sniff 兜底，双向自愈                 │
└───────────────────────────┬─────────────────────────────┘
                            ▼
┌──────────────────────── Backend (FastAPI) ────────────────────────┐
│  parser.py         bytes → 结构化 dict（协议逻辑与原脚本一致）       │
│        ▼                                                           │
│  state_manager.py  保存最新状态 + 原始报文环形缓存 + 在线判定        │
│        ▼                                                           │
│  main.py           REST (/api/*) + WebSocket (/ws/state, 10Hz)     │
└────────────────────────────────────────────────────────────────────┘
        ▲ 控制回程（可选，默认关闭）
        │  control_service.py → UDP 192.168.1.120:43893
        │  SimpleCMD(12B) / ComplexCMD(20B) / 手柄帧(42B)
└────────────────────────────────────────────────────────────────────┘
      │  WebSocket JSON 推送
      ▼
┌──────────────────────── Frontend (Vue3) ──────────────────────────┐
│  RobotStatus.vue   状态 / 步态 / 电池 / 连接                        │
│  IMUChart.vue      Roll / Pitch / Yaw 实时曲线（ECharts）           │
│  JointPanel.vue    12 个关节角度与角速度                            │
│  RawPacket.vue     接收侧原始 UDP 报文十六进制预览                  │
│  SentPacket.vue    发包监控：code / 指令值 / type / data 结构化展示  │
│  ControlPanel.vue  预置指令 / 速度 / 自定义报文 / 摇杆               │
└────────────────────────────────────────────────────────────────────┘
```

设计要点：

| 项 | 说明 |
| --- | --- |
| 协议不变 | 完全沿用原脚本的消息码、struct 格式与字段顺序，未删减任何字段 |
| 去 GUI | 不再依赖 Tkinter，UDP 线程与 Web 事件循环彻底解耦 |
| 单一职责 | 接收、解析、状态管理、接口、展示分别独立成模块 |
| 数据源可换 | sniff / bind / ros / ros_direct 统一接口，运行时可切（见第五节与 `docs/ros_bridge.md`） |
| 可扩展 | 视频、AI 检测等新能力只需加模块 + 接口，不动收发骨架 |
| **零侵入** | 103 上走旁路抓包，与 `transfer_ros2` 共存，不抢 43897（见第五节） |
| **3.8 兼容** | 面向 103 的 Ubuntu 20.04 / Python 3.8，未使用 3.9+ 语法 |

---

## 二、目录结构

```text
lite3_robot_monitor/
├── backend/
│   ├── main.py              # FastAPI 入口：REST + WebSocket + 数据源看门狗
│   ├── config.py            # 集中配置（frozen dataclass），支持环境变量覆盖
│   ├── models.py            # Pydantic 响应模型
│   │
│   │   # ---- 状态读取（读方向）----
│   ├── data_source.py       # 数据源抽象：sniff / bind / ros / ros_direct 统一接口
│   ├── udp_receiver.py      # UDP 接收线程 + 队列（bind 模式，含丢包统计）
│   ├── udp_sniffer.py       # 旁路抓包接收器（Linux AF_PACKET，不占端口，103 专用）
│   ├── parser.py            # 0x0901 / 0x0902 / 0x0903 协议解析
│   ├── state_manager.py     # 最新状态仓库 + 原始报文缓存 + 在线判定
│   ├── ros_bridge_node.py   # 独立桥接进程：订阅 ROS topic → 本地 UDP JSON
│   ├── ros_direct_source.py # 内嵌订阅数据源：本进程直接 import rclpy 订阅 topic
│   ├── ros_topic_adapter.py # ROS 消息 → 状态字典 的纯转换（两种 ros 模式共用）
│   │
│   │   # ---- 控制下发（写方向）----
│   ├── control_protocol.py  # 控制报文构造 + 结构化解析（describe_packet）
│   ├── control_service.py   # 指令发送、心跳保活、急停、限幅与审计
│   └── requirements.txt
├── docs/
│   ├── protocol/
│   │   └── lite3-udp-protocol.md  # 厂商《运动主机 UDP 通讯接口》摘录存档
│   ├── ros_bridge.md              # ROS 数据源部署：桥接模式 + 内嵌订阅模式
│   └── ros_troubleshooting.md     # ROS 数据源排查手册（含页面自检面板说明）
├── deploy/
│   ├── install.sh                 # 103 一键部署（venv + 依赖 + systemd）
│   ├── lite3-monitor.service      # systemd 单元，含 CAP_NET_RAW 能力配置
│   ├── lite3-monitor-rosdirect.service  # 内嵌订阅版单元（ExecStart 会 source ROS）
│   ├── lite3-ros-bridge.service   # ros_bridge_node 常驻服务
│   ├── deploy_103.sh              # 笔记本侧增量同步（rsync + 重启，支持 TAG）
│   ├── pack.sh                    # 笔记本侧全量打包（自动剔除 node_modules）
│   └── README.md                  # 部署、验证、排错与回滚
├── frontend/
│   ├── package.json
│   ├── vite.config.js       # 内置 /api、/ws 代理
│   ├── index.html
│   └── src/
│       ├── main.js
│       ├── App.vue          # 主面板布局
│       ├── api/index.js     # REST 封装 + WebSocket 客户端（自动重连）
│       ├── composables/useRobotState.js
│       ├── components/
│       │   ├── RobotStatus.vue    # 状态 / 步态 / 电池 / 连接
│       │   ├── IMUChart.vue       # Roll / Pitch / Yaw 实时曲线（ECharts）
│       │   ├── JointPanel.vue     # 12 个关节角度与角速度
│       │   ├── RawPacket.vue      # 接收侧原始 UDP 报文十六进制预览
│       │   ├── PacketMonitor.vue  # 发包监控通用组件（表格 + 结构化解析 + 展开详情）
│       │   ├── SentPacket.vue     # Sent UDP Packets：PacketMonitor 的预置配置
│       │   ├── ControlPanel.vue   # 控制通道：预置指令 / 速度 / 自定义报文 / 摇杆
│       │   ├── HoverTip.vue       # 悬停提示
│       │   ├── RosInfoTip.vue     # ROS 数据源说明提示
│       │   └── ToastHost.vue      # 全局轻提示
│       └── style.css
├── tools/
│   ├── mock_sender.py               # 本地联调用的 Lite3 数据模拟器
│   ├── smoke_test.py                # 端到端冒烟测试：UDP → 解析 → WS → REST → 离线判定
│   └── inspect_control_packets.py   # 控制通道侦查：pcap 解析 + 逐字节差分 + 受控重放
├── .gitignore                       # 忽略 .venv / node_modules / dist
├── requirements.txt
└── README.md
```

> `.venv/` 由 `deploy/install.sh` 在 103 上首次安装时创建，不需要提交到仓库。
> 前端依赖走 `npm install`（笔记本侧），只有构建产物 `frontend/dist` 会被部署到 103。

---

## 三、支持的协议

| 消息码 | 内容 | 报文长度 |
| --- | --- | --- |
| `0x0901` | 机器人综合状态：基本状态 / 步态 / AI 步态 / IMU（姿态、角速度、加速度）/ 世界系位姿与速度 / 机体系速度 / 电池 / 错误码 / 标志位 / 前后超声波 | 头 12B + 负载 208B |
| `0x0902` | 12 个关节角度（rad） | 头 12B + 负载 96B |
| `0x0903` | 12 个关节角速度（rad/s） | 头 12B + 负载 96B |

消息头统一为 3 个 `uint32`（`<3I`）：消息码、长度、序号。

---

## 四、快速开始

> **运行环境：仅 103 感知导航主机**（Jetson Xavier NX，Ubuntu 20.04 / Python 3.8 / ROS 2 Foxy，
> 用户 `ysc`，IP `192.168.1.103`）。本项目不在 Windows / macOS 上运行，
> 也不再维护开发机启动脚本。

### 4.1 一键部署

```bash
# ── 笔记本侧：构建前端后打包（Jetson 上 npm build 很慢，建议本地构建后传产物）──
cd frontend && npm run build && cd ..
bash deploy/pack.sh
scp lite3-monitor-deploy.tar.gz ysc@192.168.1.103:/home/test/

# ── 103 侧：解压并安装（自动建 venv、装依赖、抓包自检、注册 systemd 并启动）──
ssh ysc@192.168.1.103
cd /home/test && tar xzf lite3-monitor-deploy.tar.gz
sudo bash lite3_robot_monitor/deploy/install.sh /home/test/monitor
```

内网 pip 源：

```bash
PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
  sudo -E bash lite3_robot_monitor/deploy/install.sh /home/test/monitor
```

安装脚本只做「安装与注册」，**不改动** `transfer_ros2`、`jy_exe` 及任何现有配置。

### 4.2 验证

```bash
systemctl is-active lite3-monitor                 # 期望 active
curl -s http://127.0.0.1:8000/api/status          # 接口自检
```

| 字段 | 期望值 | 含义 |
| --- | --- | --- |
| `udp_mode` | `sniff` | 旁路抓包生效，未占用 43897 |
| `connected` | `true` | 已收到机器人状态 |
| `packets_received` | 持续增长 | 数据链路正常 |

笔记本浏览器打开 <http://192.168.1.103:8000> 即可看到监控面板，
接口文档在 <http://192.168.1.103:8000/docs>。

### 4.3 常用运维命令

| 用途 | 命令 |
| --- | --- |
| 服务状态 | `systemctl status lite3-monitor` |
| 实时日志 | `journalctl -u lite3-monitor -f` |
| 重启服务 | `sudo systemctl restart lite3-monitor` |
| 清崩溃计数 | `sudo systemctl reset-failed lite3-monitor` |
| 接口自检 | `curl -s http://127.0.0.1:8000/api/status` |
| 数据源模式 | `curl -s http://127.0.0.1:8000/api/source` |

若服务起不来，优先看日志：

```bash
journalctl -u lite3-monitor -n 50 --no-pager
```

### 4.4 部署后手册：怎么用 / 怎么配 / 怎么更新

> 服务装好之后的日常操作都在这里。部署原理（为什么不能 bind 43897、多实例、排错表）
> 见 [第五节](#五部署到-103-感知导航主机) 与 [`deploy/README.md`](deploy/README.md)，
> 踩坑案例见 [`note/`](note/README.md)。

#### 4.4.1 怎么用

| 你想做的事 | 怎么做 |
| --- | --- |
| 看监控面板 | 浏览器打开 <http://192.168.1.103:8000> |
| 查接口文档 | <http://192.168.1.103:8000/docs>（FastAPI 自动生成） |
| 查运行状态 | `curl -s http://127.0.0.1:8000/api/status` |
| 查数据源模式 | `curl -s http://127.0.0.1:8000/api/source` |
| 查 ROS 版本识别 | `curl -s http://127.0.0.1:8000/api/ros` |
| 看最近原始报文 | `curl -s http://127.0.0.1:8000/api/raw` |
| 实时数据（程序接入） | WebSocket `ws://192.168.1.103:8000/ws/state`，10Hz 推送 |

面板展示：机器人连接状态、12 个关节角度/温度、IMU、里程计、电量、
原始报文十六进制预览等（详见 [第六节](#六接口说明) 与 [第九节](#九验收对照)）。

**控制机器人（可选，默认关闭）**：控制通道直连运动主机、绕过 VOA 安全层，
必须先读 [第十二节](#十二控制通道写方向)，再按 12.7 的典型顺序操作
（启用通道 → 起立 → 切自主模式 → 开心跳 → 发速度指令 → 停止）。

**机器人没上电时**想验证链路，用内置模拟器：

```bash
cd /home/test/monitor
/home/test/monitor/.venv/bin/python tools/mock_sender.py     # 向 127.0.0.1:43897 发 10Hz 数据
```

#### 4.4.2 怎么配

配置集中在 `backend/config.py`，**全部可用环境变量覆盖**。三种改法：

| 方式 | 适用场景 | 操作 |
| --- | --- | --- |
| **unit 里加 `Environment=`**（推荐） | 长期生效、随服务重启保持 | `sudo systemctl edit lite3-monitor` 写 `[Service]` 段 |
| 改 `backend/config.py` 默认值 | 改代码默认行为 | 改完需同步到 103 并重启（见 4.4.3） |
| 前台临时指定 | 调试 | `sudo LITE3_XXX=... ../.venv/bin/python -m uvicorn ...` |

用 drop-in 改（**推荐，不会被 `install.sh` 覆盖**）：

```bash
sudo systemctl edit lite3-monitor
```

```ini
[Service]
Environment=LITE3_UDP_MODE=sniff
Environment=LITE3_UDP_IFACE=eth0
```

> ⚠️ **改完必须重启**：配置是 **frozen dataclass**，在 import 时固化，不重启不生效。

```bash
sudo systemctl daemon-reload
sudo systemctl restart lite3-monitor
```

高频配置项速查（**完整表见 [第七节](#七配置项)**）：

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `LITE3_UDP_MODE` | `auto` | 监听模式，103 上建议显式写 `sniff` |
| `LITE3_UDP_IFACE` | 空 | 抓包网卡，建议填连 `192.168.1.120` 的那张 |
| `LITE3_DATA_SOURCE` | `auto` | 数据源：ROS 为主 + sniff 兜底（双向自愈） |
| `LITE3_HTTP_PORT` | `8000` | HTTP 端口（多实例 `8000+TAG`） |
| `LITE3_CTRL_ENABLED` | `false` | 控制通道，**建议保持 false** |
| `LITE3_ROS_VERSION` | `auto` | ROS 版本手动指定（详见 [第十三节](#十三ros-版本识别与方案切换)） |

#### 4.4.3 怎么更新

**日常改代码走增量更新**（不删、不重装、不重跑 install.sh）：

```bash
# 1) 同步后端（排除缓存）
sudo rsync -av --exclude '__pycache__' --exclude '*.pyc' \
  /home/test/lite3_robot_monitor/backend/ /home/test/monitor/backend/

# 2) 清旧字节码，避免用到过期 .pyc
sudo find /home/test/monitor/backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# 3) 重启（配置 frozen，不重启不生效）
sudo systemctl restart lite3-monitor
```

前端改动：本地 `npm run build` 后只同步产物：

```bash
rsync -av /path/to/lite3_robot_monitor/frontend/dist/ \
  ysc@192.168.1.103:/home/test/monitor/frontend/dist/
```

**只有这 4 种情况才重跑 `install.sh`**：改了 `requirements.txt`、改了 `deploy/*.service`、
要部署新构建的 `frontend/dist`、首次安装或换安装目录。

完整重部署（笔记本 → 103）：

```bash
cd frontend && npm run build && cd ..     # 必须先构建，否则 103 上前端会被删坏
bash deploy/pack.sh
scp lite3-monitor-deploy.tar.gz ysc@192.168.1.103:/home/test/
# 103 上
cd /home/test && tar xzf lite3-monitor-deploy.tar.gz
sudo bash lite3_robot_monitor/deploy/install.sh /home/test/monitor
```

> ⚠️ `install.sh` 会 `rm -rf $TARGET/frontend` 再拷贝新 `dist`；
> **如果这次打包没带 `dist`，旧前端会被删且没有新内容补上 → 页面白屏**。
> 顺序必须是「构建 → 打包 → 安装」。

#### 4.4.4 出问题先看哪

**第一步永远是这条**（一句话把问题切成"数据没来"和"我没抓到"）：

```bash
sudo tcpdump -i any -nn udp dst port 43897 -c 5
```

- 有输出 → 数据到了，问题在 Monitor（查 `LITE3_UDP_IFACE`、CAP_NET_RAW 权限）
- 无输出 → 数据没到 103，去查 120 侧 `jy_exe/conf/network.toml`

| 现象 | 处理 |
| --- | --- |
| `udp_mode` 是 `bind` | 抓包降级了，`journalctl -u lite3-monitor -n 50` 看权限错误 |
| `connected` 一直 false | 按上面的 tcpdump 分流排查 |
| 页面打不开 | `systemctl status lite3-monitor` + `sudo ufw allow 8000/tcp` |
| 改了配置没生效 | 没重启（见 4.4.2） |

完整排错表见 [`deploy/README.md`](deploy/README.md) 第四节，
按主题整理的踩坑案例见 [`note/`](note/README.md)。

---

## 五、部署到 103 感知导航主机

> **历史流程，勿直接照搬**：本库已无下文所述 `deploy/`，当前部署脚本在 `lite3Code/lite3_robot_monitor/deploy/`。先核对该仓库的实际文件、适用分支和 103 状态。

> 正式运行环境：**103（Jetson Xavier NX，Ubuntu 20.04 / Python 3.8，用户 `ysc`，IP 192.168.1.103）**
> 安装目录：`/home/test/monitor`　当前运维与排错见 [`lite3Code` 的部署文档](https://github.com/javencpdd/lite3Code/blob/main/lite3_robot_monitor/deploy/README.md)。

### 5.1 为什么不能直接在 103 上 bind 43897

103 的 UDP **43897 已被 `transfer_ros2` 独占**。UDP 单播端口被两个进程同时 bind 时，
Linux **不会**给两份拷贝——后 bind 的会把报文抢走：

```
Monitor 抢走 43897 → transfer_ros2 收不到状态
                   → leg_odom2 / /imu/data 断流
                   → Nav2 失去本体里程计
```

因此 103 上默认使用 **旁路抓包（sniff）**：用 `AF_PACKET` 从链路层读取流经网卡的报文，
**不 bind 任何端口**，与 `transfer_ros2` 完全共存。

### 5.2 两种接收模式

| 模式 | 环境要求 | 占用 43897 | 适用 |
| --- | --- | --- | --- |
| `sniff` | Linux + `CAP_NET_RAW` | 否 | **103 部署（推荐）** |
| `bind` | 任意 | 是 | 无 `CAP_NET_RAW` 时的兜底（**103 上不要主动用**，见 5.1） |

`LITE3_UDP_MODE=auto`（默认）优先 sniff，失败自动退回 bind。
当前生效模式可通过 `GET /api/status` 的 `udp_mode` 字段确认。

> 以上指**监听模式**（怎么收 43897 原始报文）。另有**数据源模式**
> `LITE3_DATA_SOURCE`，决定状态来自 sniff 还是 ROS 话题订阅；
> 其中话题订阅又有 `bridge`（外部 ros_bridge_node 转发）与 `ros_direct`
> （后端内嵌 rclpy 订阅，可省掉桥接进程，但仅限 103 运行）两种实现，
> 详见本仓库 [`docs/ros_bridge.md`](docs/ros_bridge.md)；
> 排错见 [`docs/ros_troubleshooting.md`](docs/ros_troubleshooting.md)。

### 5.3 部署步骤

```bash
# 1) 笔记本：构建前端（Jetson 上 npm build 很慢，建议本地构建后传产物）
cd frontend && npm run build

# 2) 笔记本：打包（自动剔除 node_modules，几百 MB → 几十 KB）
bash deploy/pack.sh
scp lite3-monitor-deploy.tar.gz ysc@192.168.1.103:/home/test/

# 3) 103：解压并安装（自动建 venv、装依赖、抓包自检、注册 systemd 并启动）
#    解压出的 /home/test/lite3_robot_monitor 即「本机源码树」，
#    后续增量更新就是从它 rsync 到 /home/test/monitor（见 4.4.3）
ssh ysc@192.168.1.103
cd /home/test && tar xzf lite3-monitor-deploy.tar.gz
cd /tmp && tar xzf lite3-monitor-deploy.tar.gz
sudo bash lite3_robot_monitor/deploy/install.sh /home/test/monitor
```

内网 pip 源：

```bash
PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple sudo -E bash deploy/install.sh /home/test/monitor
```

安装脚本只做「安装与注册」，**不改动** `transfer_ros2`、`jy_exe` 及任何现有配置。

### 5.4 验证

```bash
curl http://127.0.0.1:8000/api/status
```

| 字段 | 期望值 | 含义 |
| --- | --- | --- |
| `udp_mode` | `sniff` | 旁路抓包生效，未占用 43897 |
| `connected` | `true` | 已收到机器人状态 |
| `packets_received` | 持续增长 | 数据链路正常 |

笔记本浏览器打开 `http://192.168.1.103:8000` 即可看到面板。

### 5.5 常见问题

| 现象 | 处理 |
| --- | --- |
| `udp_mode` 是 `bind` | 抓包降级了，`journalctl -u lite3-monitor -n 50` 看权限错误 |
| 日志报 `PermissionError` | 确认 unit 中 `AmbientCapabilities=CAP_NET_RAW`，或改 `User=root` |
| `connected` 一直 false | 先确认 103 有没有收到：`sudo tcpdump -i any -nn udp dst port 43897 -c 5` |
| 抓到无关流量太多 | 设置 `LITE3_UDP_IFACE` 为业务网网卡名（连 `192.168.1.120` 的那张） |

当前排错表与回滚步骤见 [`lite3Code` 的部署文档](https://github.com/javencpdd/lite3Code/blob/main/lite3_robot_monitor/deploy/README.md)。

### 5.6 改完代码怎么更新（不必重跑 install.sh）

日常改后端**不需要**重跑 `install.sh`——那会重建 venv、重装依赖，且会
`rm -rf $TARGET/frontend`（源目录没带新 `dist` 时反而会把页面弄坏）。

在 103 本机（源目录与运行目录都在本地）：

```bash
# 1) 同步后端（排除缓存）
sudo rsync -av --exclude '__pycache__' --exclude '*.pyc' \
  /home/test/lite3_robot_monitor/backend/ /home/test/monitor/backend/

# 2) 清旧字节码，避免用到过期 .pyc
sudo find /home/test/monitor/backend -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# 3) 重启（config 是 frozen dataclass，import 时固化，不重启不生效）
sudo systemctl restart lite3-monitor
```

从笔记本同步则用 `deploy/deploy_103.sh`（rsync + 重启，按 TAG 只动对应实例）。

**只有以下情况才需要重跑 `install.sh`**：改了 `requirements.txt`、改了 `deploy/*.service`、
要部署新构建的 `frontend/dist`、首次安装或更换安装目录。

前端改动的正确更新方式是本地 `npm run build` 后同步 `dist`：

```bash
rsync -av /path/to/lite3_robot_monitor/frontend/dist/ ysc@192.168.1.103:/home/test/monitor/frontend/dist/
```

---

## 六、接口说明

### WebSocket

`ws://<host>:8000/ws/state`

服务端以 **10Hz** 主动推送完整快照：

```json
{
  "type": "snapshot",
  "server_time": 1726400000.123,
  "connected": true,
  "robot_state": {
    "type": "robot_state",
    "code": "0x0901",
    "basic_state": "力控状态",
    "basic_state_code": 6,
    "gait_state": "平地高速",
    "imu": { "roll": 1.02, "pitch": -0.31, "yaw": 8.4 },
    "position": { "x": 1.2, "y": -0.4, "yaw": 0.15 },
    "velocity": { "x": 0.3, "y": 0.0, "yaw": 0.02 },
    "battery": 78.0,
    "ultrasound": { "forward": 1.25, "backward": 0.86 }
  },
  "joint_angle": { "type": "joint_angle", "joint": [0.01, -0.02] },
  "joint_velocity": { "type": "joint_velocity", "velocity": [0.0, 0.01] },
  "others": []
}
```

客户端发送任意文本，服务端立即回推一帧最新快照（可用于降频探测）。

### REST

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/state` | 当前完整状态快照（HTTP 轮询备用） |
| GET | `/api/status` | 服务与链路状态：是否在线、收发包计数、WS 连接数 |
| GET | `/api/raw?limit=20` | 最近 N 条原始报文摘要（时间、消息码、长度、来源、hex 预览） |
| POST | `/api/raw/clear` | 清空原始报文缓存 |
| GET | `/api/health` | 轻量健康检查 |

---

## 七、配置项

所有参数集中在 `backend/config.py`，可用环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LITE3_UDP_HOST` | `0.0.0.0` | UDP 监听地址 |
| `LITE3_UDP_PORT` | `43897` | 目标 UDP 端口（需与 Lite3 发送目标端口一致） |
| `LITE3_UDP_MODE` | `auto` | **监听模式**：`auto` / `sniff`（旁路抓包）/ `bind`（绑定端口） |
| `LITE3_UDP_IFACE` | 空 | 旁路抓包监听的网卡名，留空为全部网卡；建议填业务网网卡 |
| `LITE3_UDP_BUFFER` | `2048` | 单次接收缓冲区大小 |
| `LITE3_UDP_QUEUE` | `1024` | 接收队列容量，满时丢弃最旧数据 |
| `LITE3_HTTP_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `LITE3_HTTP_PORT` | `8000` | HTTP 监听端口 |
| `LITE3_PUSH_HZ` | `10` | WebSocket 推送频率 |
| `LITE3_LINK_TIMEOUT` | `3.0` | 超过该秒数未收到数据判定离线 |
| `LITE3_RAW_HISTORY` | `30` | 原始报文环形缓存条数 |
| `LITE3_LOG_LEVEL` | `INFO` | 日志级别 |
| `LITE3_SERVE_FRONTEND` | `true` | 是否挂载 `frontend/dist` |

**数据源相关**（决定状态来自哪种途径，详见 `docs/ros_bridge.md`）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LITE3_DATA_SOURCE` | `auto` | `auto` / `ros` / `ros_direct` / `sniff` / `bind`；`auto` = ROS 系为主 + sniff 兜底，**双向自愈** |
| `LITE3_ROS_IMPL` | `bridge` | auto 用哪种 ROS 实现：`bridge` 外部桥接进程 / `direct` 后端内嵌 rclpy |
| `LITE3_ROS_BRIDGE_HOST` | `127.0.0.1` | `ros_bridge_node` 转发到的本地地址 |
| `LITE3_ROS_BRIDGE_PORT` | `43900` | 本地桥接端口（多实例为 `43900 + TAG`） |
| `LITE3_ROS_NODE_NAME` | `lite3_monitor_ros` | 内嵌订阅的 ROS 节点名，**多实例必须不同** |
| `LITE3_ROS_TOPIC_IMU` | `/imu/data` | 内嵌订阅 topic（须与 `transfer_ros2` 实际发布的一致） |
| `LITE3_ROS_TOPIC_ODOM` | `/leg_odom2` | 同上 |
| `LITE3_ROS_TOPIC_JOINTS` | `/joint_states` | 同上 |
| `LITE3_ROS_STALE_TIMEOUT` | `10.0` | ROS 曾正常后断流多少秒判定失效并降级 |
| `LITE3_ROS_RETRY_INTERVAL` | `15.0` | 处于 sniff 兜底时，每隔多少秒探测 ROS 是否恢复 |

**ROS 版本识别相关**（详见第十三章）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LITE3_ROS_VERSION` | `auto` | 手动指定 ROS 版本：`auto`（自动检测）/ `ros1` / `ros2`；**优先级高于自动检测** |
| `LITE3_ROS_STRICT` | `false` | 严格模式：识别失败时 `true`=抛异常终止启动，`false`=报错后回退安全默认 |
| `LITE3_ROS_FALLBACK_MODE` | `sniff` | 回退时使用的数据源模式（sniff 与 ROS 版本无关，是唯一两头安全的选项） |
| `LITE3_ROS_DETECT_TIMEOUT` | `3.0` | 自动检测时单条外部命令（如 `systemctl`）的超时秒数 |

**控制通道相关**：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LITE3_CTRL_IP` | `192.168.1.120` | 控制指令目标 IP（运动主机；WiFi 网段 2 时为 `192.168.2.1`） |
| `LITE3_CTRL_PORT` | `43893` | 控制指令目标端口 |
| `LITE3_CTRL_HEARTBEAT` | `0.25` | 心跳周期（秒），文档要求频率 ≥ 2Hz |
| `LITE3_CTRL_LEASE` | `5.0` | 心跳租约（秒），前端失联后自动停心跳并下发零速 |
| `LITE3_CTRL_MAX_LINEAR` | `1.0` | 前后线速度硬上限（m/s），文档取值 ±1.0 |
| `LITE3_CTRL_MAX_LINEAR_Y` | `0.5` | 左右线速度硬上限（m/s），文档仅允许 ±0.5 |
| `LITE3_CTRL_MAX_ANGULAR` | `1.5` | 角速度硬上限（rad/s） |
| `LITE3_CTRL_ENABLED` | `false` | 启动即启用控制通道（**建议保持 false**） |
| `LITE3_CTRL_INVERT_VEL_X` | `false` | 前后速度取反（实机方向与文档相反时开启） |
| `LITE3_CTRL_INVERT_VEL_Y` | `false` | 左右速度取反 |
| `LITE3_CTRL_INVERT_VEL_YAW` | `false` | 旋转方向取反 |

> 布尔型变量接受 `1 / true / yes / on`（真）与 `0 / false / no / off`（假），大小写不敏感。
> 全部配置在 **import 时读取且为 frozen dataclass**，修改后**必须重启服务**才生效。

前端可通过 `VITE_BACKEND_URL` 指定后端地址（跨域直连模式）。

---

## 八、无机器人上电时的联调

机器人未上电时，可用内置模拟器向 103 本机发送符合协议的数据，验证解析链路：

```bash
cd /home/test/monitor

# 默认向 127.0.0.1:43897 以 10Hz 发送
/home/test/monitor/.venv/bin/python tools/mock_sender.py

# 只发一轮用于协议校验
/home/test/monitor/.venv/bin/python tools/mock_sender.py --once
```

> 注意：`sniff` 走 AF_PACKET 抓的是**网卡流量**，`127.0.0.1` 的回环包抓不到。
> 模拟器要发往 103 的业务网 IP（如 `192.168.1.103`），或临时把监听模式切到 `bind`：
> `curl -X POST 'http://127.0.0.1:8000/api/source/set?mode=bind'`（测完切回 `auto`）。

随后刷新页面，应能看到：状态卡片显示「力控状态 / 平地高速 / 78.0%」，IMU 曲线随时间摆动，
12 个关节数值滚动更新。停止模拟器 3 秒后（默认超时），页面自动切换为 **Disconnected**。

也可直接在命令行做一次完整链路自检（UDP → 解析 → WebSocket → REST → 离线判定）：

```bash
/home/test/monitor/.venv/bin/python tools/smoke_test.py
```

测试会临时占用本机 8000 端口，**请先停掉 `lite3-monitor` 服务**，通过后打印「全部冒烟测试通过」。

---

## 九、验收对照

| 验收项 | 结果 |
| --- | --- |
| 启动后端后可收到 Lite3 UDP 数据 | ✅ 通过 `/api/status` 的接收包计数验证 |
| 浏览器显示 Battery / Mode / IMU / Position | ✅ `RobotStatus.vue` + `IMUChart.vue` + 位置速度面板 |
| 机器人状态变化时网页同步变化 | ✅ WebSocket 10Hz 推送 |
| 关闭机器人后显示 Disconnected | ✅ 超过 `LITE3_LINK_TIMEOUT` 未收到数据即判定离线 |

---

## 十、扩展状态与预留

| 方向 | 状态 | 说明 |
| --- | --- | --- |
| ROS 话题订阅 | ✅ 已实现 | `ros_bridge_node.py`（外部进程）与 `ros_direct_source.py`（内嵌 rclpy）两种，转换逻辑共用 `ros_topic_adapter.py`，详见 `docs/ros_bridge.md` |
| 发包结构化解析 | ✅ 已实现 | `control_protocol.describe_packet` 产出 `fields[]`；前端 `PacketMonitor.vue` 做十六进制分段着色与逐字段展开 |
| 多实例并行部署 | ✅ 已实现 | `install.sh <目录> <TAG>`：服务名 / HTTP 端口 / 桥接端口按 TAG 派生 |
| 视频（RealSense / RTSP） | 预留 | 新增 `backend/video_stream.py`，接口 `GET /api/video` 或 `WS /ws/video` |
| AI 检测（YOLO 火焰检测） | 预留 | 新增 `backend/detector.py`，接口 `GET /api/detection`，前端增加 `DetectionPanel.vue` |

新增能力只需：在 `parser.py` 增加消息码分支 → 在 `models.py` 增加模型 → 在前端增加组件，
不需要改动 UDP 接收与 WebSocket 推送骨架。

---

## 十一、注意事项

1. 监控（读取状态）部分**只读**；控制指令需**显式启用通道**后才会下发，默认关闭（见第十二章），且会绕过 VOA 安全层；
2. 关节顺序依据文档 1.3.2：**左前 → 右前 → 左后 → 右后**（LF/RF/LB/RB），每腿 `hip_x`（侧摆）/`hip_y`（髋）/`knee`（膝）；如固件不同，改 `backend/config.py` 的 `DisplayConfig` 即可；
3. `0x0901` 中的 `touch_down_and_stair_trot`、`is_charging`、`error_state`、`task_state` 在部分固件版本上为无效值，界面已做弱化处理但仍完整透传。
4. **Python 版本**：代码面向 **3.8**（103 的 Ubuntu 20.04），未使用 3.9+ 的内置泛型与 3.10+ 的 `X | None` 语法；新增代码请保持该兼容级别，否则 103 上会启动失败；
5. **103 上不要强制 bind 43897**：会抢走 `transfer_ros2` 的报文，导致 Nav2 失去里程计。如需 bind，请先用 `sudo ss -lunp | grep 43897` 确认端口确实空闲。

---

## 十二、控制通道（写方向）

> ⚠️ **风险提示**：控制指令直连运动主机上的闭源 `jy_exe`（`192.168.1.120:43893`），
> **不经过 103 侧的 VOA 安全层**（限速、避障、防撞均不生效）。
> 务必在开阔场地、机器人架空或有人持遥控器待命时使用。

### 12.1 协议来源

依据**厂商文档《运动主机 UDP 通讯接口》**，摘录已存档于
历史引用的 `docs/protocol/lite3-udp-protocol.md` 未随本库原型保留；协议细节应以当前代码仓库中的解析器、厂商文档和实测为准。

### 12.2 报文格式（文档 1.1 节）

```cpp
// 简单指令：12 字节，type = 0
struct CommandHead {
    uint32_t code;            // xxxx 指令码
    uint32_t paramters_size;  // yyyy 指令值；无有效指令值时为 0
    uint32_t type;            // zzzz = 0
};

// 复杂指令：12 + N 字节，type = 1
struct Command {
    CommandHead head;         // yyyy = 数据长度
    uint32_t data[kDataSize]; // bbbb… 数据内容
};
```

- **字节序**：小端。文档附录实例 `0209 0000 | 6000 0000 | 0100 0000` 即
  `code=0x0902`、`paramters_size=0x60(96)`、`type=1`，报文总长 108 字节
- **发送长度**：`sizeof(head) + paramters_size`
- **校验**：简单/复杂指令均**无校验字段**

> 早前版本曾据 `Lite3_ROS` 源码把头部第 2、3 字段理解为 `cmd_value` / `sequence`，
> 现据厂商文档更正为 `paramters_size` / `type`。

### 12.3 控制指令集（文档 1.2 节，共 31 条预置）

| 分组 | 指令 | 指令码 | type |
| --- | --- | --- | --- |
| **状态** | 起立/趴下（轮流切换） | `0x21010202` | 0 |
| | 回零 | `0x21010C05` | 0 |
| | 进入 AI / 退出 AI | `0x21010528` / `0x2101052B` | 0 |
| | 软急停 | `0x21020C0E` | 0 |
| **模式** | 原地模式 / 移动模式 | `0x21010D05` / `0x21010D06` | 0 |
| | **自主模式** / 手动模式 | `0x21010C03` / `0x21010C02` | 0 |
| **步态** | 平地低速 / 中速 / 高速 | `0x21010300` / `0x21010307` / `0x21010303` | 0 |
| | 正常/匍匐（轮换） | `0x21010406` | 0 |
| | 通用越障 / 抓地越障 / 高踏步越障 | `0x21010401` / `0x21010402` / `0x21010407` | 0 |
| **动作** | 扭身体 / 太空步 / 扭身跳 | `0x21010204` / `0x2101030C` / `0x2101020D` | 0 |
| | 翻身 / 向前跳 / 后空翻 / 打招呼 | `0x21010205` / `0x2101050B` / `0x21010502` / `0x21010507` | 0 |
| | 停止动作（需连发指令值 0 和 1） | `0x21010C0B` | 0 |
| **AI** | AI 基础 / 跳跃 / 站立 / 极速步态 | `0x2101052A` / `0x21010529` / `0x2101052C` / `0x2101052E` | 0 |
| **其他** | 持续运动（-1 开 / 2 关） | `0x21010C06` | 0 |
| | 保存数据 | `0x21010C01` | 0 |
| **心跳** | 心跳包 | `0x21040001` | 0 |

速度指令（文档 1.2.12，复杂指令，**需在自主模式下发送**）：

| 指令 | 指令码 | 数据范围 |
| --- | --- | --- |
| 前后平移 | `0x0140` | ±1.0 m/s（正值前进） |
| 左右平移 | `0x0145` | ±0.5 m/s（**正值向右**） |
| 旋转角速度 | `0x0141` | ±1.5 rad/s（**正值向右转**） |

轴指令（文档 1.2.3，简单指令，值为 int32 原始量）：前后 `0x21010130`（±6553）、
左右 `0x21010131`（±12553）、转向 `0x21010135`（±9553）；
文档要求**下发频率 ≥ 20Hz，超时 250ms 后机器人自动停止运动**。

### 12.4 心跳机制

| 项 | 取值 | 依据 |
| --- | --- | --- |
| 心跳指令码 | `0x21040001`（简单指令，type=0） | 文档 1.2.1 |
| 心跳周期 | `0.25s`（4Hz） | 文档要求 **≥ 2Hz** |
| 心跳内容 | 心跳包 + 当前速度指令（非零时重发） | 避免速度超时失效 |
| 租约 | `5s`，前端失联后自动停心跳并补发零速 | 本工程安全加固 |
| 页面关闭 | `beforeunload` + `sendBeacon` | 主动通知；失败由租约兜底 |
| 组件卸载 | `onUnmounted` 清定时器 + 停心跳 | 防资源泄漏 |
| 服务退出 | FastAPI `lifespan` → `control.close()` | 停心跳 → 零速 → 关 socket |

三层保护确保**不会出现后台持续发送**。

### 12.5 已实现的安全约束

1. **默认禁用**：`LITE3_CTRL_ENABLED=false`，需显式 `/api/control/enable`
2. **后端硬限幅**：前后 ±1.0、左右 ±0.5、旋转 ±1.5（按文档取值，不信任前端）
3. **急停**：停心跳 → 连发零速 → 发厂商**软急停** `0x21020C0E` → 锁定后续指令
4. **危险动作二次确认**：后空翻 / 向前跳 / 扭身跳 / 翻身等在界面需确认后才下发
5. **心跳租约**：前端消失自动停止并补发零速
6. **审计日志**：每条报文含指令码、参数、时间戳，`GET /api/control/audit`
7. **错误处理**：参数非法、未启用、网络异常均返回结构化错误

**仍需人工遵守**：人与机器人保持 5 米距离 / 首次测试架空 / 遥控器随时可接管。

### 12.6 控制接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/control/status` | 启用状态、急停、心跳、发包计数 |
| GET | `/api/control/presets` | 指令表（含分组、指令码、危险标记） |
| POST | `/api/control/enable` / `disable` | 启用 / 停用控制通道 |
| POST | `/api/control/velocity` | 速度 `{x, y, yaw}` |
| POST | `/api/control/preset` | 按名称下发预置指令 |
| POST | `/api/control/custom` | 自定义报文（code/value/type/data） |
| POST | `/api/control/raw` | 原始十六进制报文 |
| POST | `/api/control/stop` | 零速停止 |
| POST | `/api/control/estop` / `estop/clear` | 急停（含软急停指令）/ 解除 |
| POST | `/api/control/heartbeat/start` / `stop` / `renew` | 心跳控制 |
| GET | `/api/control/audit` | 指令审计记录 |

每条审计记录（`control_protocol.describe_packet` 的输出）除原始 `hex` 外还带结构化字段：

| 字段 | 说明 |
| --- | --- |
| `code_hex` / `name` | 指令码十六进制 + 中文名（未知码为空串） |
| `paramters_size` | 包头第 2 个 uint32：简单指令即**指令值**，复杂指令为**数据长度** |
| `param_i32` | 同上字段按 int32 的解读（轴指令会下发 `-1`、`±6553` 这类负值） |
| `type` | `0` 简单指令 / `1` 复杂指令 |
| `data_hex` / `data` | 数据区十六进制 / 按 double 的解读 |
| `fields` | 逐字段结构化列表（偏移 / 长度 / hex / 值 / 说明），前端据此给预览分段着色 |
| `data_views` | 数据区多视角解码（double / float / int32 / uint32 / int16 …） |

界面一律以**十六进制**呈现，与报文原文逐字节对应；十进制换算只在需要时手动切换。

### 12.7 典型使用顺序

```text
1) 启用控制通道
2) 起立/趴下（0x21010202）→ 让机器人起立
3) 切「自主模式」（0x21010C03）← 关键：否则速度指令无效
4) 开启心跳（0x250ms 周期，含 0x21040001）
5) 发送速度指令（0x0140 / 0x0145 / 0x0141）
6) 停止移动 → 停止心跳 → 停用控制通道
```

---

## 十三、ROS 版本识别与方案切换

> 103 上**同时装有 ROS1（noetic）与 ROS2（foxy）**，两套 transfer **抢同一个 UDP 43897**。
> 监控必须知道自己当前身处哪个版本，因为两者可用的数据接入方式不同：
>
> - **ROS2**：可用 `ros_bridge_node`（43900）转发或内嵌 rclpy 订阅；
> - **ROS1**：**没有**对应的桥接（现有桥接节点是 ROS2 的），只能用 sniff 旁路抓包。
>
> 本章描述的就是"自动识别当前版本 + 加载对应执行方案"的能力。
> 相关代码：`backend/ros_env.py`、`backend/ros_profiles.py`、`backend/ros_switch.py`。

### 13.1 三层解耦

| 文件 | 职责 | 说明 |
| --- | --- | --- |
| `ros_env.py` | **只检测** | 判断 ROS1 / ROS2 / UNKNOWN，纯 stdlib，可独立运行 |
| `ros_profiles.py` | **只声明** | 各版本的话题/节点发现命令、进程与资源采集方式、数据源策略 |
| `ros_switch.py` | **只裁决** | 手动 > 自动的优先级、失败报错与回退 |

检测与执行解耦，新增一个 ROS 版本只需在 `ros_profiles.py` 加一条声明。

### 13.2 检测信号优先级

按可信度从高到低，取**第一个明确无歧义**的信号：

| 顺序 | 信号 | 判据 |
| --- | --- | --- |
| 1 | `env_version` | 环境变量 `ROS_VERSION` |
| 2 | `env_distro` | `ROS_DISTRO`（noetic/melodic…→ROS1；foxy/humble…→ROS2） |
| 3 | `env_marker` | `AMENT_PREFIX_PATH`→ROS2；`ROS_MASTER_URI`/`ROS_ROOT`→ROS1 |
| 4 | **`process`** | 实际在跑的进程：`jetson2motion`→ROS2，`qnx2ros`→ROS1 |
| 5 | `systemd_service` | 同 `print_ros_version.sh`：`systemctl is-enabled transfer` |
| 6 | `install_path` | `/opt/ros/<distro>` 扫描（仅结果唯一时采信） |
| 7 | `executable` | PATH 上的 `ros2` / `roscore`（仅结果唯一时采信） |

**为什么 `process` 排在参考脚本的 systemd 判据之前**：`print_ros_version.sh` 用
`systemctl is-enabled transfer` 判断，但 ROS1 链路是 `start_transfer.sh` **脚本拉起**、
并非 systemd 常驻，此时该判据会**误判为 ROS2**。以真实在跑的进程更贴近事实，
systemd 判据仅作兜底保留，以维持与参考脚本的一致性。

实测 103 上 systemd 拉起服务时 `ROS_VERSION` / `ROS_DISTRO` **全部缺失**，
且 `/opt/ros` 下 noetic 与 foxy 并存、PATH 上 `ros2` 与 `roscore` 并存 ——
前三个信号与后两个信号都不可用，**只有 `process` 可靠**。

### 13.3 手动指定（优先级高于自动检测）

两个入口，同时存在时 CLI 更高：

```bash
# 方式 A：环境变量（systemd 场景用这个，写在 unit 的 [Service] 段）
Environment=LITE3_ROS_VERSION=ros1      # 或 ros2 / auto

# 方式 B：启动参数
python main.py --ros-version ros1       # 可选值 auto / ros1 / ros2
```

> CLI 参数之所以写进环境变量再传给 uvicorn，是因为
> `uvicorn.run("main:app")` 会重新 import 模块，进程内全局变量跨模块实例不可见。

### 13.4 各版本方案差异

| | ROS2 | ROS1 |
| --- | --- | --- |
| 话题发现 | `ros2 topic list` | `rostopic list` |
| 节点发现 | `ros2 node list` | `rosnode list` |
| 进程采集 | `jetson2motion` / `jetson2app` / `sensor_checker` | `rosmaster` / `qnx2ros` / `ros2qnx` / `nx2app` |
| 数据源策略 | `ros`（桥接 43900 或内嵌 rclpy） | **`sniff`**（无 ros 桥接可用） |

`LITE3_DATA_SOURCE` 显式指定为 `ros`/`sniff`/`bind`/`ros_direct` 时**尊重配置**；
只有 `auto` 才由版本方案决定 —— 这样 ROS1 下不会再白等 ros 桥接超时。

同时切回 ros 的看门狗会检查 `profile.ros_impl`，**ROS1 下禁止切回**，
避免反复尝试切到 ROS2 桥接上。

### 13.5 失败策略（禁止静默继续）

检测失败 / 版本不受支持 / 手动值非法时：

1. 打 **ERROR** 日志，说明具体原因（含手动值、检测轨迹、受支持列表）；
2. 置 `degraded=true` 并保留错误文本，暴露在 `/api/ros` 与启动日志；
3. 回退到安全默认数据源 `LITE3_ROS_FALLBACK_MODE`（默认 `sniff`，与版本无关）；
4. 若 `LITE3_ROS_STRICT=true`，**不回退**，直接抛 `RosSwitchError` 终止启动。

### 13.6 验证

```bash
# 独立检测（含每条信号的命中轨迹）
/home/test/monitor/.venv/bin/python /home/test/monitor/backend/ros_env.py --verbose

# 运行时生效情况
curl -s http://127.0.0.1:8000/api/ros

# 一键验证 4 项（自动识别 / 运行时生效 / 手动切换 / 失败回退）
bash /home/test/monitor/tools/verify_ros_switch.sh
```

`/api/status` 也会带上 `ros_version`、`ros_source`、`ros_degraded`、`ros_error` 四个字段。

### 13.7 与 `print_ros_version.sh` 的关系

`/home/ysc/scripts/print_ros_version.sh` **未做任何修改**，其既有行为保持不变；
本能力只是把它的判据（`systemctl is-enabled transfer`）复用为兜底信号之一。

> ⚠️ 切换 ROS1 / ROS2 时注意：`transfer_ros2.service` 若处于 `enabled`，
> **103 重启后会自启并抢回 43897**。长期跑 ROS1 请先
> `sudo systemctl disable transfer_ros2.service`。详见 `note/05-部署运维.md` 5.7。

### 13.8 ROS 环境切换实操

本章前面的内容是**监控程序如何自适应版本**；如果你要问的是
**"103 主机上的 ROS 环境怎么从 ROS2 切到 ROS1、怎么切回来"**，
那是运维操作，完整步骤见 [`note/06-ROS1与ROS2环境切换.md`](note/06-ROS1与ROS2环境切换.md)，
包含：双栈现状、端口与进程对照表、两种切换的完整命令、开机自启陷阱、对各系统的影响。

最常用的一条判断命令：

```bash
printf "\047\n" | sudo -S ss -lunp | grep 43897   # jetson2motion → ROS2；qnx2ros → ROS1
```

（103 上 `sudo` 需要密码，非交互场景必须 `printf "\047\n" | sudo -S`；
直接 `sudo ss` 会报 `a terminal is required to read the password`。）

> 注意：厂商脚本 `print_ros_version.sh` 用 `systemctl is-enabled transfer` 判断，
> 而 ROS1 是脚本拉起的、不会让该服务变成 enabled，因此**跑着 ROS1 时它仍会输出 ROS 2**
> （误判）。判断版本请用上面这条命令或 `ros_env.py`。
>
> ⚠️ **切换 ROS 环境后必须重启监控服务**：ROS 方案在首次使用时计算一次并缓存
> （`main.py` 的 `_ROS_PLAN_CACHE`），不重启的话 `/api/ros` 会一直报旧版本。
> `sudo systemctl restart lite3-monitor.service`
>
> ⚠️ **双栈并存时自动判定会退化**：若 `roscore`（ROS1）与 `jetson2motion`（ROS2）
> 同时在运行，`process` 信号会判为歧义并向下退化，命令行与在线服务可能给出**不同答案**。
> 此时以端口归属为准，或直接用 `LITE3_ROS_VERSION=ros1|ros2` 显式指定。
