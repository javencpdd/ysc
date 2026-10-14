# M20 Pro Web 控制台 — 计划书v1

> 版本：v1（一体化版，2026-10-14）· 状态：**全部决策点已锁定，可进入实现**
> 归档位置：`m20Pro/m20Pro_robot_monitor/note/`（本项目所有开发相关计划书统一存放于此）
> 本文档由原三份文档整合而成（内容全量保留、去重、统一编号）：
> - 原 `PLAN.md` v1.2（开发计划书：目标 / 复用映射 / 执行清单 / 部署 / 风险）
> - 原 `DESIGN.md` v2.1（架构设计：约束 / 领域分析 / 选型 / ADR / 质量属性 / 演进）
> - 原 `PROTOCOL.md` v1.1（协议实现参考：帧格式 / 指令全集 / 5 类状态消息确切结构）
>
> 原 DESIGN.md / PROTOCOL.md 已降级为指引桩（内容以本文档为准）；如需拆回独立文档，按 §10（协议）/ §4–§9（架构）切分即可。
> 参照项目：`../../../lite3/lite3_robot_monitor/`（FastAPI + Vue3 前后端分离 Web 监控控制台）
> 目标平台：云深处 山猫 M20 Pro 四足机器人（AOS/NOS/GOS 三主机，ROS 2 体系）
> 资料依据：`../../docs/04-软件开发指南V1.3.0-钉钉全文.txt`（本体监控协议 + ROS2 话题）、`../../analysis/05-M20-pro资料整合评估报告.md`、工作区记忆（`m20Pro`/`196` 主机条目）

---

## 0. 结论先行

1. **方案与架构已定稿**：**模块化单体**——单进程 FastAPI 驻 AOS 196，UDP 心跳 + ASDU 解析为主通道，ROS2 为可选增强通道（`DataSource` / `ControlSink` 双层抽象 + WS schema 契约冻结，三条迁移路径见 §18）。
2. **执行策略：先 mock 后真机**。M1 全程无需真机、零风险：MockSource 驱动全链路（心跳→解析→状态→WS 10Hz→前端→stale 降级）并冻结 schema 契约；M2 才上 196，只做"替换数据源 + 核对字段"这一件事。
3. **三个范围决策点已锁定**（§14.1，2026-10-14 用户确认无异议）：视频本期做但收缩为 HLS 单路先行；**控制通道本期集成、分层开放**（L0 只监 / L1 低危可控 / L2 黑名单，轴指令看门狗兜底）；MockSource 覆盖全部 5 类 ASDU 消息集 + 回放模式。
4. **协议真相已判明**（§10）：16 字节帧头 + JSON（PatrolDevice 信封），控制指令全集来自 docs/04 §1.2，参考 `m20-android-sdk`（Apache-2.0，只参考协议不复制代码）——**Q2「字节布局」风险关闭**；5 类状态消息的 Type/Command 与 Items 结构已按 docs/04 原文逐条核实（§10.4），残留仅为状态字段语义的真机核对。
5. **协议事实三处修正**（v1.2 起，依据 docs/04 原文）：① M20 Pro 为**轮足**，运控关节 **16 个**（4 腿 × HipX/HipY/Knee/Wheel），非 lite3 式 12 关节；② 步态切换字段名为 **`GaitParam`**，值域 0x1001/0x1003/0x3002/0x3003；③ MotionParam 只保留原文值 0/1/2/3/4/17（旧稿推测值已删）。
6. **关键路径**：T1.1→T1.3→T1.4→T1.5→T1.6→T1.7→T1.9→T3.1→T3.6→T4.1→T4.4；控制链在 M1 内用 MockSource 全闭环，不占真机窗口；**196 上机窗口是唯一外部约束**（T2.7 控制首测须空旷场地 + 人员看护）。
7. **依赖总原则**：没有 mock 不上真机；契约先行（前端只认 schema 不认后端细节）；视频与数据链零依赖可并行；配置/口令只进 `*.example`（仓库脱敏红线）。

---

# 第一部分 总纲与约束

## 1. 背景、目标与非目标

### 1.1 背景
- M20 Pro 现场缺一个好用的本地 Web 监控界面：厂商 3000 端口控制台（`m20video`）已停用禁自启，手柄/APP 是另一套体系。
- Lite3 已有成熟方案 `lite3_robot_monitor`（FastAPI + Vue3 + WebSocket 10Hz + ECharts），**应当复用而非重造**。
- m20Pro 当前在 196（AOS）上**曾有过 3000 端口 Web 控制台**（`m20video` 服务，已禁用；`basic_server` 监听 30001/30002），说明厂商本就有前端范式可借鉴。
- 现有资料已厘清 m20Pro 的数据接口形态（§10/§11），具备动手条件。

### 1.2 目标（本期）
- 浏览器实时查看 M20 Pro 状态：**基础状态、运控状态（含关节 `MotorStatus`——16 个：4 腿 × HipX/HipY/Knee/Wheel，M20 Pro 为轮足）、设备状态（电池 `BatteryList` 多电池）、异常状态（`ErrorList`）**。
- **Web 控制**（分层开放，ADR-004）：**运动控制**（六轴轴指令 20Hz + 站立/趴下/软急停/步态/使用模式）、**休眠/唤醒（唤醒全车含传感器）**、照明灯、自主充电开始/退出；默认 L0 只监，L1 需显式开启 + 二次确认 + WS 租约；Charge=2 黑名单；轴指令看门狗零位兜底。
- 集成相机视频流（前/后，`video1`/`video2`）。

### 1.3 非目标（本期不做）
- 不重复造前端栈（直接复用 Vue3 组件，仅做字段对齐）。
- **不开放高危指令**（清除充电状态 Charge=2）、不做手柄硬件对接（ControllerSDK 是 Android 侧的事，Web 端用虚拟摇杆替代）。
- 不做导航任务编排、不做 AI 识别回环（可后续叠加，架构预留接口）。

## 2. 硬约束与质量属性优先级

### 2.1 硬约束（来自 2026-10-14 实测，不可假设）

| # | 约束 | 架构含义 |
|---|---|---|
| C1 | LAN 只能直连 AOS `192.168.0.196`；**监控协议与 MediaMTX 均监听在 AOS 本机**（`10.21.31.103`/`10.21.33.103` 皆 AOS 内网 IP，非 GOS；GOS 是 `10.21.31.104`） | 后端驻 196 后**同主机内网口直达**监控协议与视频源，无需跨主机；LAN 只暴露 Web/WS |
| C2 | 监控协议：机器人=服务端，UDP `10.21.31.103:30000` / TCP `:30001`；外部 ≥1Hz 发心跳后机器人**主动推送**（基础 2Hz / 运控 10Hz / 设备 2Hz / 异常 2Hz+变更额外）；**载荷为帧头+JSON（PatrolDevice 信封）**，见 §10 | 数据层是"**主动心跳 + 被动接收**"；解析 = 16 字节帧头 + `json.loads`，无二进制布局风险 |
| C3 | 视频：相机物理接在 **AOS**（前后 `SM_USB_107X`），MediaMTX 也在 **AOS 本机**运行 → RTSP `10.21.31.103:8554/video1\|video2`（`10.21.31.103` 即 AOS 内网 IP，**非 GOS**.104），196 上等价于 `127.0.0.1:8554` | 取流优先用 **196 本机 MediaMTX**（近零中继）；**视频源与监控协议同在 AOS**，进一步锁定部署主机 |
| C4 | 控制指令含危险项（清除充电状态=2，官方标注**危险**） | 控制通道默认关闭 + 安全闸 + 黑名单 |
| C5 | 端口已被占：`30001/30002`(basic_server)、`8554/1935/8888/8889`(MediaMTX)、`3000`(遗留 m20video)、`21/22/9393` | 控制台端口必须避开，建议 `8080`/`8081` |
| C6 | 196 时钟慢 ~846 天（**TLS 必失败**）、WiFi 间歇丢包、`/`（overlayroot）仅 14G 可用 | 不依赖 HTTPS；应用装 `/home/djw/monitor`（用户指定，与 `/` 同分区）；心跳带重试；时钟修复后再议 TLS |
| C7 | ~~ASDU 报文逐字节布局未精读~~ **已关闭**：协议 = 16 字节帧头 + JSON（§10），无二进制布局谜团 | ACL（防腐层）从"struct 拆字节"降为"帧头校验 + JSON 字段映射"；残留仅为**字段语义真机核对**，ACL 的隔离价值不变 |

### 2.2 质量属性优先级
**可靠性 > 可维护性 > 可观测性 > 性能**。
理由：这是运维/调试工具——"状态停更但界面不报"比"帧率低 5Hz"危险得多。宁可少做一个图表，不可让用户看到假数据。

## 3. 领域分析（Bounded Contexts）

划分六个上下文，彼此用明确边界隔开：

```
 ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
 │  数据接入 Ingestion │ → │   状态 State      │ → │  实时推送 Realtime │
 │  心跳发送          │   │  唯一权威状态      │   │  WS fan-out 10Hz  │
 │  UDP 收包          │   │  + 新鲜度(stale)   │   │                   │
 │  帧头+JSON 解码    │   │                   │   │                   │
 └───────────────────┘   └───────────────────┘   └───────────────────┘
 ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
 │  视频 Video        │   │  控制 Control      │   │  展示 Presentation │
 │  MediaMTX 代理     │   │  分层开放          │   │  Vue3 + ECharts   │
 │  RTSP → HLS        │   │  L0只监/L1低危/    │   │  + 运动面板        │
 │                   │   │  L2黑名单+看门狗   │   │                   │
 └───────────────────┘   └───────────────────┘   └───────────────────┘
```

**Context Mapping（最重要的一条边界）**：Ingestion → State 之间必须放**防腐层（Anti-Corruption Layer, ACL）**。ASDU 解析器负责把协议报文翻译成领域状态对象；**协议怎么变，都关在解析器里**，不污染 State、不污染前端。这是整个设计里唯一不可妥协的边界。

---

# 第二部分 架构设计

## 4. 架构选型：三个方案与决策

### 4.1 方案 A：模块化单体（复用 lite3 骨架）
单进程 FastAPI：ingestion 线程 + state + ws hub + 视频代理 + 前端静态资源，模块间以清晰接口相连，**不拆进程**。

| 获得 | 放弃 |
|---|---|
| 最小部署面（一个 systemd unit，一次 `systemctl restart`） | ingestion 与 API 同生共死（需靠线程隔离 + 看门狗 + `/ready` 缓解） |
| 复用度最高，与 lite3 同构，团队学习成本近零 | 无法独立扩展视频/数据两条通路 |
| 调试简单（一个 journald 日志流） | 单进程内存上限即整机上限 |

### 4.2 方案 B：ROS2 中心化
后端订阅 ROS2 话题（传感器/运动/速度/自主充电），前端经 rosbridge 或自研 WS 网关展示。

| 获得 | 放弃 |
|---|---|
| 数据语义最丰富（话题类型自带 schema），与厂商生态一致 | 必须在 196 装配 ROS2 + DDS 环境，依赖链重 |
| 控制走 topic 最自然 | ROS2 话题清单**未实测**（Q4）；DDS 发现/QoS 排障成本高 |
| 后续可无缝接导航任务监控 | 发现不稳定时"整链黑屏"；与 lite3 前端复用度低 |

**适用时机**：后续要做导航任务监控、rviz 级可视化时再引入——届时只是新增一个数据源实现（见 ADR-001 与 §18）。

### 4.3 方案 C：微服务化（ingestion / video / api / frontend 各自成服务）

| 获得 | 放弃 |
|---|---|
| 各通路独立扩缩、故障隔离彻底 | 4 进程/端口的运维成本 |
| — | 进程间通信（谁持有 state 权威？） |
| — | 在 RK3588 单机上跑微服务是典型的 architecture astronautics |

### 4.4 决策：**选 A**；B 作为后续增强通道**预留接口**；C **明确拒绝**
理由：团队 1–2 人、单机部署、架构已被参照项目钉死、当前最大风险是"协议没吃透"而非"吞吐不够"。A 的取舍（同生共死）用"线程隔离 + 心跳看门狗 + `/ready` 探针 + systemd Restart"缓解，可接受。
**保留可逆性**：把数据源抽象为 `DataSource` 接口（lite3 已有 `data_source.py` 雏形），未来接 ROS2 只是新增一个实现类，上层零改动——这是让 B 随时可来的关键，且成本几乎为零。

## 5. 总体架构

### 5.1 部署拓扑

```
浏览器(LAN)
   │  HTTP + WebSocket
   ▼
[m20pro-console 后端]  ← 跑在 AOS 192.168.0.196
   │  ├─ 心跳发送器 ≥1Hz ──► AOS 本体 10.21.31.103:30000 (UDP, 同主机内网口)
   │  ├─ UDP 接收 ◄──────── 机器人 ASDU 状态推送(回同一 socket)
   │  ├─ 帧头+JSON 解析 → StateStore
   │  ├─ 控制出口(同一 socket) ──► 轴指令20Hz / 站立 / 步态 / 照明 / 休眠唤醒 / 充电
   │  ├─ MediaMTX RTSP 代理 ──► 127.0.0.1:8554/video1|video2 (196 本机 MediaMTX)
   │  └─ (可选) ROS2 订阅 ← 196 本机 ROS2 话题
   ▼
WebSocket 10Hz 推送 + 视频流 → Vue3 前端
```

**为何后端跑在 196**：监控协议与 MediaMTX **均监听在 AOS 本机**（`10.21.31.103` 系 AOS 内网 IP，196 即 AOS 的 LAN 侧）→ 后端驻 196 后同主机内网口/回环直达，LAN 只暴露 Web/WS。这也契合"开发都在 AOS"的现场约定。

**数据层选型**：**主通道 = UDP 心跳 + ASDU 解析**（不需要 ROS2 环境，最稳，复用 lite3 套接字骨架）；ROS2 话题作为**可选增强**，复用参照项目 `ros_*` 模块思路（ADR-001）。

### 5.2 容器视图

```
[浏览器 LAN]
   │  HTTP :8080（页面 / REST / 静态资源）
   │  WS   /ws（状态快照 10Hz，双向：控制 L0 默认关，急停除外）
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│ m20pro-console   单进程 · 驻 AOS 192.168.0.196 · venv + systemd      │
│                                                                        │
│  ┌──────────────────┐   ┌────────────────┐   ┌──────────────────┐    │
│  │ HeartbeatSender  │ → │ UdpReceiver    │ → │ AsduParser (ACL) │    │
│  │ ≥1Hz → AOS:30000 │   │ 收 ASDU 推送    │   │ 帧头+JSON→领域模型│    │
│  └──────────────────┘   └────────────────┘   └────────┬─────────┘    │
│  ┌────────────────┐                                    ▼             │
│  │ VideoProxy     │ ← 127.0.0.1:8554/video1|2   ┌──────────────┐    │
│  │ RTSP → HLS:8081│   （196 本机 MediaMTX）      │  StateStore  │    │
│  └───────┬────────┘                              │ 唯一权威+新鲜度│    │
│  ┌────────────────┐                              └──────┬───────┘    │
│  │ ControlGateway │  分层 L0/L1/L2 · 租约 · 看门狗 · 黑名单  ▼            │
│  │ + AxisWatchdog │  轴指令 20Hz → 同一 UDP socket       ┌──────────┐  │
│  └────────────────┘                                     │ WsHub 10Hz│ │
│   /health  /ready（含数据新鲜度）                        └──────────┘  │
└──────────────────────────────────────────────────┴──────────┴──────────┘
        │ 内网 UDP（同主机）                      │ 本机回环
        ▼                                       ▼
 AOS 本体 10.21.31.103:30000（监控+控制）   196 本机 MediaMTX :8554（视频源）
```

**数据源可插拔**：`DataSource` 接口 ← { `M20UdpHeartbeatSource`（默认）, `MockSource`（无真机开发/回放）, `Ros2TopicSource`（预留）}。

### 5.3 后端目录（feature-first，三层边界适配）

```
backend/
  config.py            集中配置 + 启动校验（fail fast，ADR-008）
  errors.py            类型化错误层次（AppError / ProtocolError / StaleError…）
  logging_setup.py     结构化 JSON 日志
  main.py              FastAPI 装配 + /health /ready + 优雅停机(SIGTERM)
  ingestion/           数据接入上下文
    data_source.py     DataSource 抽象（udp / mock / ros2 三实现可换）
    heartbeat_sender.py  心跳发送（≥1Hz，可配频率，带重试）
    udp_receiver.py    UDP 接收（**同一 socket 收发**：机器人推回心跳发送方 IP:端口）
    asdu_parser.py     ← ACL：16 字节帧头 + JSON(PatrolDevice) → 领域状态对象
    mock_source.py     构造/回放报文（无真机开发与单测）
  state/
    models.py          领域模型：BasicState / MotionState / DeviceState / FaultState
    state_store.py     唯一权威状态 + per-topic 时间戳 + stale 判定
  realtime/
    ws_hub.py          连接管理 + 10Hz 快照 fan-out + ping/pong
  video/
    video_proxy.py     RTSP → HLS（ll-hls）代理，:8081
  control/             控制上下文（分层开放，ADR-004）
    control_gateway.py 安全闸：L0/L1/L2 分层 + 租约 + 黑名单 + 运动前置校验 + 审计日志
    patrol_codec.py    PatrolDevice JSON 编解码 + 16 字节帧头（指令全集见 §10.3）
    axis_watchdog.py   轴指令看门狗：20Hz 循环 + 只停不趴（停更 → 零位停发等待恢复；绝不自动软急停）
frontend/               复用 lite3，字段对齐 + 新增 VideoPanel.vue + MotionPanel.vue（运动控制）
```

### 5.4 关键接口（契约先行）

| 接口 | 签名 / 语义 | 备注 |
|---|---|---|
| `DataSource` | `start() / stop() / on_frame(cb)` | 三种实现可互换，上层不感知来源 |
| `StateStore.update(topic, payload, ts)` | **仅 ingestion 可写**；读侧只读快照 | 写入口唯一，杜绝并发写乱 |
| `StateStore.snapshot()` | → dict，含 per-topic `ts` 与 `stale` 标志 | 前端永远不猜数据新鲜度 |
| `WsHub.broadcast(snapshot)` | 每 100ms 一次，JSON | 与 lite3 前端 `api/index.js` 兼容 |
| `ControlGateway.execute(cmd, params)` | L0 → `403 CONTROL_DISABLED`；L1 需租约+前置校验；L2 任何配置拒绝 | 黑名单指令（Charge=2）任何配置下都拒绝 |
| `POST /api/v1/control/motion` | 运动状态转换/步态/模式/照明/休眠/充电（L1 白名单） | 入参白名单校验，审计日志 |
| `POST /api/v1/control/axis` | 轴指令（X/Y/Z/Roll/Pitch/Yaw ∈ [-1,1]；**服务端安全上限 ±0.40**） | 20Hz 由看门狗循环发送；单发=一次性指令 |
| `POST /api/v1/control/estop` | 软急停（MotionParam=2） | **无需 enable 也可用**（安全手段优先于开关） |
| `GET /api/v1/schema` | WS 快照 JSON schema（带 `version` 字段） | **前后端契约，版本化冻结**——后端换数据源时前端零改动（§18 路径 3 的保险） |

### 5.5 模块职责与失败行为

| 模块 | 职责 | 失败行为 |
|---|---|---|
| HeartbeatSender | ≥1Hz 向 AOS:30000 发心跳 | 发送异常 → 重试 + 计数；连续失败 → `/ready` degraded |
| UdpReceiver | 本地端口收 ASDU 推送 | socket 异常 → 重建；收包速率掉零 → 触发 stale |
| AsduParser (ACL) | 协议 → 领域模型 | 解析失败 → 死信计数 + warn 日志，**不抛出到 ingestion 之外** |
| StateStore | 权威状态 + 新鲜度 | 超阈未更新 → 标记 stale（不删旧值，只标脏） |
| WsHub | 快照 fan-out | 客户端断连自动清理；服务端 ping 30s |
| VideoProxy | RTSP→HLS | 上游断 → HLS 列表保留最后片段 + 前端提示"视频中断" |
| ControlGateway | 指令安全闸（分层/租约/黑名单/前置校验/审计） | 默认 L0 disabled；租约随 WS 断开失效（**前端每 2s 自动续约**，2026-10-15 修复：此前 UI 侧无续约调用方，开启 5s 后指令全被租约闸拒发）；**急停永不受开关限制** |

## 6. 关键流

### 6.1 状态上报链路（正常路径）
`HeartbeatSender(≥1Hz)` → AOS:30000 → 机器人开始推送 → `UdpReceiver` 收到 ASDU → `AsduParser` 解码（帧头+JSON） → `StateStore.update(ts=now)` → `WsHub` 每 100ms 取快照广播 → 前端 `useRobotState` 渲染。
**时延预算**：网络 + 解析 < 10ms；WS 广播周期 100ms → 端到端 < 200ms，对 10Hz 遥测充分。

### 6.2 降级路径（重点：不许假数据）
- 心跳发送失败 / 超过 `stale_threshold`（默认 500ms，可配）无推送 → StateStore 标 stale → 前端**顶部红色横幅"数据已停更 mm:ss"** + 各面板置灰。**绝不把旧数据当新数据展示。**
- 解析失败率 > 阈值 → `/ready` 返回 degraded + warn 日志，不静默。
- 后端崩溃 → systemd `Restart=on-failure` 自动拉起；前端 WS 断线自动重连。
- 目标：**MTTR < 1 分钟（自动恢复）**。

### 6.3 视频链路
`VideoProxy` 从 **196 本机 MediaMTX** `127.0.0.1:8554/video1|video2` 拉流 → 切 HLS → 前端 `VideoPanel`（hls.js）播放。

> **端口取舍（2026-10-15 实现定稿）**：HLS 产物**挂载在主应用 `/hls` 路径下**（单端口 8080），
> 而非原规划的独立 `:8081` —— 少一个进程/端口，与前端静态托管保持"单端口"一致。
> `video.hls_port` 保留为可选项（未来需独立端口时启用）。

#### 6.3.1 ⚠️ 前置：相机需先唤醒（2026-10-15 实测，运维必知）
机器人**休眠时相机不通电**：实测休眠态下 `/dev/video*` 不存在、`lsusb` 无 `0bda:3035`、
MediaMTX 无 `video1/video2` 路径（ffmpeg 取流返回 404）。
- 唤醒指令：`1101/6` + `Items={"Sleep": false}`（即 §10.3.2 的"退出休眠/唤醒全车含传感器"）；
- 验证：唤醒后 `Sleep` 由 `1` → `0`，`/dev/video0~3` 出现，两颗 `SM_USB_107X (0bda:3035)` 挂载，
  `video1/video2` 均有流（`h264 High 800×600 30fps`）。
- **Auto 自动休眠当前为 `true` + `Time=5` 分钟**：控制台持续发心跳应可抑制自动休眠（待观察）；
  若发现相机周期性掉线，优先查是否被自动休眠。

#### 6.3.2 实测参数（2026-10-15）
| 项 | 实测值 |
|---|---|
| 编码 | **必须用 `-c:v copy` 不转码** —— 196 的 ffmpeg 4.2.7 **无 rkmpp 硬编**（只有 libx264 软编） |
| 首切片耗时 | **1 s**（验收标准 ≤3s ✅），加了 `-fflags nobuffer -flags low_delay -probesize 32 -analyzeduration 0` |
| 片段 | 1s/片 ~250KB，`hls_list_size=3` + `delete_segments` → 目录有界 ~1.1MB |
| 传输 | `-rtsp_transport tcp`（WiFi/内网丢包环境比 UDP 稳） |
**取舍**：选 HLS 而非 WebRTC——实现简单、穿越代理/防火墙友好、延迟 1–3s 对**监控**可接受。若后续要低延迟（如遥控），再开 WebRTC（MediaMTX 8889 已就绪）。**遥控低延迟诉求应通过带安全闸的控制通道满足，而不是靠压视频延迟**——这是两条不同的路，不要混。

### 6.4 控制链路（分层开放，ADR-004）
```
[浏览器 MotionPanel] --WS/REST--> ControlGateway（安全闸）
                                      │ 分层校验（L0/L1/L2）+ 前置条件 + 值域钳制
                                      ▼
                              patrol_codec 编码（帧头+JSON）
                                      │ 同一 UDP socket
                                      ▼
                              AOS 10.21.31.103:30000
```
- **L0 只监（默认）**：任何控制请求返回 `403 CONTROL_DISABLED`——**急停除外**（安全手段优先于开关）。
- **L1 低危可控（需显式开启）**：站立/趴下/软急停/步态/使用模式/照明/休眠唤醒/充电开始-退出。开启条件：配置显式 `enable` + 前端二次确认 + **心跳租约**（WS 断开即失效）。
- **L2 高危黑名单（永不开放）**：`Charge=2`（清除充电状态，官方标注危险）。
- **轴指令看门狗**（**只停不趴**，2026-10-15 二次事故修正）：20Hz 循环发送中，① **松杆 / feed 停更 250ms / WS 断开 / 服务停机** → 一律 **零位一帧 + 停发**（不软急停——车侧 rl_deploy 150ms 速度看门狗自动清零，车体平滑停住）；此后保持"停"等待恢复，新 feed 即续发；② **绝不自动软急停** —— 软急停只能由人显式触发（两次真机事故均为"自动软急停"所致：运动中被打急停栽倒 / 站立中被打急停卸力软塌，机制已整体切除）；③ 安全零位帧豁免四道闸（`send_safety_zero`）。**绝不让机器人带着最后一条指令无限运动**——这是控制通道最重要的单点设计。
- **运动前置校验**：轴指令下发前校验 `MotionState ∈ {站立(1), RL控制(17)}` 且 `ControlUsageMode=0`（常规模式，docs/04 §1.2.5 原文约束），否则拒绝并提示先站立/切模式。
- 指令经 `patrol_codec` 编码后走**同一 UDP socket**（与心跳/接收复用）发往 `10.21.31.103:30000`。

## 7. 架构决策记录（ADR）

> ADR 记录 **WHY**，不只是 WHAT。原 PLAN 旧稿的 D1–D5 关键技术决策已分别并入 ADR-001~004 与 §6.1（推送频率），不再单列。

### ADR-001 数据通道：UDP 心跳 + ASDU 解析，而非 ROS2 订阅
- **Context**：需要读取全部状态；UDP 心跳与 ROS2 订阅两条路都可行。
- **Decision**：默认 UDP 心跳通道；ROS2 作为 `DataSource` 的另一个实现**预留接口**，不上主链路。
- **Consequences**：获得零 ROS2 依赖、最稳、与 lite3 同构；放弃话题级 schema 与语义丰富度；协议字段语义未吃透前解析器可能反复改——**用 ACL 隔离该代价**。

### ADR-002 部署位置：后端驻 AOS 196
- **Consequences**：内网直达监控协议与 MediaMTX，LAN 只暴露 Web/WS；放弃"部署在开发机"（够不到内网）。代价：须绕开 196 的时钟/TLS/丢包问题（C6）。

### ADR-003 视频经后端代理（RTSP→HLS），浏览器不直连
- **Consequences**：规避浏览器不支持 RTSP 与跨网直连；放弃"零中转"的极低延迟（监控场景可接受）。代理消耗 CPU（RK3588 可用 `/dev/mpp_service` 硬解）。

### ADR-004 控制通道分层开放：L0 只监 / L1 低危可控 / L2 高危黑名单
- **Context**：初版设计"本期零真实指令，只留闸门接口"。用户 2026-10-14 要求**本期集成控制指令**（Web 控制运动 + 唤醒传感器），参考 `m20-android-sdk`；协议真相判明后（帧头+JSON，§10）实现成本大幅下降。安全红线（C4：Charge=2 官方标注危险）不变。
- **Decision**：控制通道本期实现，按危险度分层：
  - **L0 只监（默认）**：任何控制请求 `403 CONTROL_DISABLED`——**软急停除外**（安全手段优先于开关）；
  - **L1 低危可控**（需配置 `enable` + 前端二次确认 + WS 心跳租约）：站立/趴下/软急停/步态切换/使用模式/照明灯/休眠唤醒/充电开始-退出；
  - **L2 高危黑名单（永不开放）**：`Charge=2`（清除充电状态）。
- **Consequences（获得）**：Web 端可遥控运动（轴指令 20Hz）+ 一键急停 + 休眠/唤醒；打开"上装设备/机械臂"等未来集成的协议底座（PatrolDevice 自定义消息）。
- **Consequences（代价与缓解）**：机器人可被 Web 端驱动 → 运动风险 → 用四道闸缓解：① 分层开关 + 租约；② **轴指令看门狗（只停不趴）**（松杆/停更/断连 → 零位停发等待恢复；**绝不自动软急停**——两次事故复盘后整体切除，§6.4）；③ 运动前置校验（MotionState ∈ {站立, RL控制} + 常规模式）+ 服务端值域钳制（安全上限 ±0.40）；④ 全量审计日志（谁/何时/发了什么）。
- **为何不是"全开"或"全关"**：全开违背 C4 安全红线；全关不满足用户本期需求。分层让"监控用户"和"操作员"两种角色各得所需，且黑名单指令在任何配置下都到不了机器人。

### ADR-005 实时通道选 WebSocket 而非 SSE
- **Context**：监控是 server→client；未来控制需 client→server。
- **Decision**：WS（复用 lite3 前端 composables/api；控制指令可走同一连接或 REST）。
- **Consequences**：获得双向能力与前端复用；放弃 SSE 的简洁自动重连——需自实现 ping/pong 与重连（成熟模式，成本可控）。

### ADR-006 状态权威唯一 + 新鲜度语义
- **Decision**：StateStore 是唯一权威，ingestion 独占写；快照带 per-topic `ts`；超时即 stale。
- **Consequences**：前端永远不猜数据新鲜度；放弃"各 topic 独立订阅推送"的带宽优化（单客户端 10Hz 快照仅数 KB/s，无需优化）。

### ADR-007 无数据库：内存状态 + 有界原始报文环形缓冲
- **Context**：监控工具，状态即问即答，无历史查询需求。
- **Decision**：不引入 DB；保留最近 N 帧原始 ASDU（有界，默认 1000 帧）供调试（对齐 lite3 `RawPacket`/`PacketMonitor`）。
- **Consequences**：重启即失历史（可接受）；放弃事件历史查询——若后续要"异常事件时间线"再加 SQLite（见 §18 演进）。

### ADR-008 配置集中 + 启动校验（fail fast）
- **Decision**：目标 IP/端口/心跳频率/阈值全部走 `config.py`（env 可覆盖），启动时校验必填项与端口冲突。
- **Consequences**：换主机只改一处；放弃"改了就跑"的随意性——**配置错误要在启动时炸出来，而不是运行时静默失败**。

### ADR-009 后端语言与框架：Python 3 + FastAPI（而非 Go / Node / Rust）
- **Context**：需选定后端语言；候选 Python(FastAPI) / Go / Node(TS) / Rust。
- **Decision**：**Python 3.10+ + FastAPI + uvicorn**，venv 隔离。
- **Consequences（获得）**：
  1. lite3 后端代码（`parser.py` / `state_manager.py` / WS / `main.py`）可**复制改造**，工期从周降到天；
  2. 团队是 ROS/Python 原生，零学习成本；
  3. ADR-001 预留的 `Ros2TopicSource` 用 `rclpy` 零摩擦接入；
  4. `pydantic-settings` 直接兑现 ADR-008 的 fail-fast；
  5. 196 已具备 `python3` / `ffmpeg` / `cv2`（2026-10-14 实测），无需另装运行时。
- **Consequences（放弃）**：
  1. Go 的单静态二进制部署便利——用 venv + systemd 弥补，RK3588 上差异可忽略；
  2. Go 的 goroutine 并发模型——asyncio + 单 ingestion 线程已够；视频转码是**独立 ffmpeg 进程，不吃 GIL**，故 GIL 在本项目不是瓶颈；
  3. 前后端同语言的类型共享——以 OpenAPI / 共享 JSON 契约替代。
- **为何不选**：
  - **Go**：lite3 后端**一行都不能留**（全量重写），且 `rclpy` 不可用会关死 ROS2 增强门；收益（静态二进制）在 venv 方案前不明显。
  - **Node**：196 运行时未验证；二进制解析与数据校验生态弱于 Python 的 `struct` + pydantic；团队不熟。
  - **Rust**：10Hz 遥测属过度工程，编译期与学习成本不成比例。

#### ADR-009 补充：换其他语言的损益账（2026-10-14，用户追问"换语言会不会有增强"）

**先算工作量画像——本控制台是低速率遥测面板，不是高并发服务**：

| 负载 | 量级 | 语言敏感度 |
|---|---|---|
| ASDU ingestion | 2+10+2Hz ≈ **14 帧/秒**，每帧数十至数百字节，解析**微秒级/帧** | 任何语言均 <0.1% 单核 |
| WS 扇出 | 10Hz 快照 × LAN 内 1–5 个浏览器，数 KB/s | 可忽略 |
| 视频转码 | **独立 ffmpeg 子进程**（C 实现，不吃 GIL） | 与语言无关 |
| 心跳发送 | 1Hz，一个 socket | 可忽略 |

**语言不在瓶颈上**。真正的约束是 Q2（ASDU 字段语义待真机核对）、C6（196 时钟/丢包）、联调迭代速度——三者均与语言无关。且 AOS 普通进程虽只剩 3 个小核（isolcpus 隔离了大核），本控制台预算也仅 ~1% 单核，余量充足。

**换语言的净损益**：

| 候选 | 增强 | 代价 | 净判断 |
|---|---|---|---|
| Go | 单静态二进制；goroutine（本负载用不上） | lite3 后端 **100% 重写**（T1.3–T1.7 全废）；**无 `rclpy` 等价物 → 关死 §18 路径 1 的 ROS2 零摩擦接入**；venv 已弥补部署差异 | **负** |
| Node(TS) | 前后端同语言 | 196 运行时未验证；二进制解析/数据校验生态弱于 `struct`+pydantic；后端全重写 | **负** |
| Rust | 理论最快 | 10Hz 遥测属过度工程；编译期+学习成本；后端全重写；同样无 rclpy | **负** |
| C++ | 与机器人本体同栈 | Web 开发生态最差；全重写；无净收益 | **负** |

**何时重议语言（触发条件，出现任一才重开此决策）**：
1. **实测**控制台在 196 上持续占用 >20% CPU，或 WS 并发客户端 >50——按实测数据说话，不按想象；
2. 范围升级为**多机器人汇聚网关**（N 台 × 高速率扇入——那更是 172.31.68.227 汇聚点的活，不是本控制台）；
3. 团队更替为 Go/Rust 原生团队；
4. 196 上 `python3` 被厂商裁剪不可用。

**架构已留的口子**：`DataSource` / `ControlSink` / WS schema 契约三层抽象意味着——即使将来真需换语言，替换单位是**模块或旁路进程**（如解析热循环用 Rust 写 PyO3 扩展，或按 §18 路径 2 拆独立进程），**不是整个后端**；前端因 schema 冻结而零改动。

### ADR-010 控制出口对称抽象：`ControlSink`
- **Context**：数据入口已抽象为 `DataSource`；若控制出口写死 UDP socket，未来接 ROS2 控制回路（`cmd_vel` → topic）必须重构。
- **Decision**：控制出口同样抽象为 `ControlSink` 接口，本期实现 `UdpControlSink`（复用同一 UDP socket，真实出口），**预留 `Ros2ControlSink`**。
- **Consequences**：与 `DataSource` 严格对称，"数据来源 / 控制出口"两个维度均可替换；代价是本期多一层薄抽象（一个接口 + 一个实现，约 20 行）。`UdpControlSink` 不再是 no-op，但 `ControlSink` 接口签名不变——**上层（网关/看门狗/前端）对"出口是 UDP 还是 ROS2"零感知**。

## 8. 质量属性设计

| 属性 | 设计 | 目标 |
|---|---|---|
| 可靠性 | stale 语义 + 心跳看门狗 + systemd Restart + WS 自动重连 + 心跳重试 | MTTR < 1min |
| 可维护性 | ACL 隔离协议、feature-first 目录、三层边界、ADR 记录 WHY | 协议变更只改 `asdu_parser.py` |
| 可观测性 | 结构化 JSON 日志（收包数/解析失败/stale 事件/WS 连接数）、`/health` `/ready`、原始报文环形缓冲 | 排障不登主机 |
| 性能 | 10Hz 广播、HLS 单路 1–2Mbps | CPU 预算 < 15%（196 已有负载） |
| 可测试性 | `MockSource` 支持无真机开发；解析器喂构造报文单测 | 无真机即可验证主干 |

## 9. 安全设计（不可妥协）

1. **分层开放（ADR-004）**：L0 只监默认（不发送任何控制/运动指令）→ L1 低危需配置 enable + 前端二次确认 + WS 心跳租约（断开即失效）→ L2 黑名单。
2. **危险指令硬禁用**：清除充电状态（Charge=2）**任何配置下不可调用**（无"除非"）。
3. **轴指令四道闸**：看门狗只停不趴（松杆/停更/断连 → 零位停发等待恢复；绝不自动软急停）+ 运动前置校验（MotionState∈{站立,RL控制} + 常规模式）+ 服务端值域钳制（**安全上限 ±0.40**，2026-10-15 实测）+ 全量审计日志（结构化 JSON：操作者/时间/指令/参数/结果）。
4. **软急停优先**：急停按钮不受控制开关限制——安全手段永远可达。
5. **不依赖 HTTPS**（C6 时钟问题）；监听限内网可达；CORS 显式来源（不用 `*`）。
6. **输入校验**：任何来自 client 的参数都当不可信——控制指令参数白名单校验（浏览器不是可信边界）。
7. **脱敏合规**：遵循仓库约定——真实口令/密钥不入库，只提交 `*.example`；不提交第三方二进制。
8. **端口不冲突**：不与 `basic_server`(30001/30002)、遗留 `m20video`(3000) 争抢。

---

# 第三部分 协议实现参考

## 10. 协议实现参考（M20 Pro 本体监控/控制协议）

> 本部分是控制台的**实现直接依据**，合并两个来源：
> ① `../../docs/04-软件开发指南V1.3.0-钉钉全文.txt`（协议语义：指令全集 + 字段含义）
> ② GitHub `DeepRoboticsLab/m20-android-sdk`（RobotProtocol / RobotConnectUDP：传输帧格式 + 连接参数，Apache-2.0）
>
> **结论先行：整套协议 = 16 字节二进制帧头 + UTF-8 JSON 信封（`PatrolDevice`）**。
> 早期判断"ASDU 逐字节布局未吃透"（Q2）系误判——ASDU 指应用层消息信封，载荷是 JSON，无二进制字段布局谜团。

### 10.1 传输层（帧格式来自 m20-android-sdk `RobotProtocol.Head`）

| 项 | 值 |
|---|---|
| 传输 | UDP（docs/04 另给 TCP `:30001` 备选，本期不走） |
| 端口 | `30000` |
| 目标 IP | `10.21.31.103`（docs/04 §1.1.2）或 `10.21.33.103`（SDK 默认）——**二者均为 AOS 本体内网 IP**（196 即 AOS 的 LAN 侧，属同主机内网口，非 GOS）；最终以 196 上机 `ss -lunp` 确认监听地址（Q1 收敛） |
| 帧头 | 16 字节：`EB 91 EB 90`(4) + `dataSize` LE16(2，帧体长度) + `messageID` LE16(2，线程安全自增) + `protocolType`(1，`0x01`=JSON) + `RESERVE`(7×`0x00`) |
| 帧体 | UTF-8 JSON，见 §10.2 |

帧头小端序。`parseUdpFrame` 校验 `HEAD_TAG` 与长度，不匹配丢弃。

**地址真相**：`10.21.31.103`/`10.21.33.103` 均为 AOS 本体内网 IP（非 GOS；GOS 是 `10.21.31.104`）。后端驻 196（=AOS LAN 侧）后**同主机内网口直达**，无需跨主机。

### 10.2 应用层信封（PatrolDevice）

```json
{
  "PatrolDevice": {
    "Type": 100,
    "Command": 100,
    "Time": "2026-10-14 14:00:00",
    "Items": {}
  }
}
```

- `Type`（消息大类）+ `Command`（命令码）组合唯一标识一条消息（SDK `CommandType(type, command)`，`toString()` 为 `"type-command"`）。
- `Time`：`yyyy-MM-dd HH:mm:ss` 本地时间串。**注意 196 时钟慢 ~846 天（C6），该字段不可信**——一律透传，新鲜度判断只用本机单调时钟（§6.2 stale 语义不变）。
- `Items`：参数/字段体，随消息类型变化（确切结构见 §10.3/§10.4）。
- 推荐 JSON 格式（docs/04：JSON 下 ASDU 处理性能更快且数据结构更全面）。

### 10.3 指令全集

#### 10.3.1 心跳与连接

| Type | Command | 功能 | Items | 频率 |
|---|---|---|---|---|
| 100 | 100 | 心跳 | `{}` | docs ≥1Hz；SDK 默认 200ms(5Hz) |

- **机器人只向持续发送心跳的 IP:端口主动推送状态**——不发心跳就没有任何推送（这是与 lite3 裸 UDP 推送的本质区别）。
- **同一 socket 收发**：机器人把状态推回心跳发送方的 IP:端口，因此发送心跳的 socket 即接收 socket（Q3 由此收敛，无需独立 bind）。
- 连接语义（SDK）：收到心跳才判定连接成功；`connectSuccessTimeOut`（默认 3000ms）内无任何数据 → 标记断开，但**不关 socket**，消息照常发送，恢复后自动重连。

#### 10.3.2 控制指令（docs/04 §1.2 全集）

| Type | Command | 功能 | Items 关键字段 | 危险级 |
|---|---|---|---|---|
| 1101 | 5 | 使用模式切换 | `Mode`: 0=常规(手动) 1=导航 2=辅助 | 低 |
| 2 | 22 | 运动状态转换 | `MotionParam`: 0=空闲 1=站立 2=关节阻尼(软急停) 3=开机阻尼 4=趴下 17=RL控制（**以此表为准**，旧稿推测值 -2/-1/5 不见于 docs/04，勿用） | 低（软急停是安全手段） |
| 2 | 23 | 步态切换 | **`GaitParam`**（字段名以原文为准，勿写 `Gait`）：`0x1001`=基础(标准模式) `0x1003`=楼梯(标准模式) `0x3002`=平地(敏捷模式) `0x3003`=楼梯(敏捷模式)。注：步态切换会自动切到对应运动模式；上报侧 BasicStatus.Gait 枚举另含 `0x1002`=高台(标准)（命令侧不列出） | 低 |
| 2 | 21 | 六轴轴指令（**运动控制**） | `X`/`Y`/`Z`/`Roll`/`Pitch`/`Yaw` ∈ [-1,1] 归一化（相对最大速度比例，正负参考右手坐标系）；**服务端安全上限 ±0.40**（实测：0.25≈0.32m/s 舒适 / 0.40≈0.54m/s 上限 / ≥0.70 危险）；**建议 20Hz 循环发送**；移动步态仅 X/Y/Yaw 生效；**⚠️ 仅支持常规模式（ControlUsageMode=0）下执行** | **高（机器人会动）** |
| 1101 | 2 | 照明灯 | `Front`/`Back`: 0=关 1=开 | 低 |
| 1101 | 14 | 自定义灯语 | `CustomMode` + `Led[]`（Type/Color/Cycle） | 低 |
| 2 | 24 | 自主充电 | `Charge`: 1=开始 0=退出 2=重置 3=取消前往电桩 4=停止退桩 | 中（**Charge=2 官方标注危险**：强制切断充电电流、状态归零、清除错误记录） |
| 1101 | 6 | 休眠模式设置（**唤醒传感器入口**） | `Sleep`: true=开启休眠 / **false=退出休眠（唤醒全车，含传感器）**；`Auto`: 无消息自动休眠开关；`Time`: [5,30] 分钟 | 中 |
| 1101 | 16 | GPS 时间同步 | 开启后机器人以 GPS 卫星时间统一校准所有主机系统时间；默认关 | 中（**或可修复 196 时钟慢 846 天（C6）**；但当前 GPS 无定位（可见 1–5 颗星），待验证） |
| 1101 | 7 | 休眠状态及设置信息查询 | 请求 `Items:{}`；响应 `Items:{Sleep, Auto, Time}` | 低（查询） |
| 1002 | 1 | 基础状态查询（请求） | `Items:{}`（触发一次 1002/6 响应） | 按需 |

**控制指令分层归属**（ADR-004）：上表中除 Charge=2（L2 黑名单，永不开放）外，其余控制指令均属 L1 低危可控（需 enable + 二次确认 + WS 租约）；心跳为基础设施；查询类只读。

### 10.4 状态消息确切结构（docs/04 §1.3 + **2026-10-14 真机抓包实测**）

> **实测说明**：2026-10-14 经 SSH 在 196 上运行 `tools/probe_asdu.py`（目标 `127.0.0.1:30000`），
> 10 秒抓取 **226 帧真实报文**，零解析失败。本节所有"实测"标注均来自该抓包
> （已存 `tools/capture/asdu_loopback_20261015.jsonl`，并作为回归测试 fixtures，见 §14.3 T2.6）。

> 置信度标注：**[已确认]** = docs/04 原文表格/示例直给；**[推断]** = 由上下文推得待真机核对；**[未知]** = 文档未载，须 M2 实测。帧体均为 `{"PatrolDevice": {"Type", "Command", "Time", "Items"}}` 信封。

**① 基础状态上报 `1002/6`（2Hz）** — `Items.BasicStatus` **[已确认]**：
```
MotionState(0=空闲 1=站立 2=关节阻尼/软急停 3=开机阻尼 4=趴下 17=RL控制) · Gait(0x1001/0x1002/0x3002/0x3003) ·
Charge(0=空闲 1=前往充电桩 2=充电中 3=退出充电桩 4=机器人异常) · HES(硬急停 0=未触发 1=已触发) ·
ControlUsageMode(0=常规 1=导航 2=辅助) · Direction(0=正向为前进正方向 1=后向为) · OOA(辅助避障 0=未启动 1=空闲 2=未触发 3=主动避障中) ·
PowerManagement(0=常规 1=单电池) · Sleep(0=未休眠 1=已休眠 2=进入休眠中) · Version(山猫M20=STD / 山猫M20 Pro=PRO)
```

**② 运控状态上报 `1002/4`（10Hz）** — **[已确认]**：
```
Items.MotionStatus: Roll · Pitch · Yaw · OmegaZ · LinearX · LinearY · Height · Payload · RemainMile（单位待核对 [推断]）
Items.MotorStatus:  Joint[16] + 命名字段 LeftFront/RightFront/LeftBack/RightBack × HipX/HipY/Knee/Wheel（共 16 关节，轮足）
```
> ⚠️ **轮足结构（已由真机实测确认）**：M20 Pro 每腿 4 自由度（含 `Wheel` 轮毂），与 lite3 的 3 自由度×4 腿不同——前端 `JointPanel` 不能直接复用 lite3 的 12 关节布局，须按 16 关节重排（T3.1 已含此项）。
> 实测：`MotorStatus` = 17 个键（`Joint[16]` + 16 个命名键），关节数 **16 ✅**（此项原为 docs 推断，现已实测坐实）。

**③ 设备状态上报 `1002/5`（2Hz）** — `Items.BatteryList`（**数组，多电池**）**[已确认]**：
```
[{ Voltage, BatteryLevel(0-100 float), battery_temperature, charge(bool), serial }, ...]
```
> ~~电池个数未知~~ → **实测确认 2 块** ✅（`BatteryList` 2 项 + `BatteryStatus` 带 Left/Right 左右电池）。
> **⚠️ 实测还发现 Items 实含 7 大类**（docs/04 只写了 `BatteryList`）：
> `BatteryList`(2) / `BatteryStatus`(左右电池 10 字段) / `DeviceTemperature`(含 `Motor[16]` 电机温度等 34 项) / `Led` / `GPS`(11) / `DevEnable`(9) / `CPU`。
> 控制台本期只取电池 + 电机温度 + GPS/CPU，其余落库备查。

**④ 异常状态 `1002/3`（2Hz 固定 + 变更额外上报）** — `Items.ErrorList` **[已确认]**：
```
[{ errorCode, component }, ...]   // errorCode 取值表文档未给全 [未知]，M2 实测积累
```

**⑤ 休眠状态及设置信息查询 `1101/7`（按需查询）** — 请求 `Items:{}`；响应 `Items:{Sleep, Auto, Time}` **[已确认]**。
> 与"休眠模式设置 `1101/6`"（控制指令）配对：设置写入、查询回读。前端休眠面板用 7 回读状态、用 6 执行唤醒。
> 注：抓包中未出现（需主动查询才会响应），MockSource 已覆盖。

**⑥ 心跳应答 `100/100`（**实测新增**，随心跳 1:1 回帧）** — `Items:{"ErrorCode": 0}`。
> 机器人对**每条心跳**回一帧应答并带 `ErrorCode` —— 可作为"链路是否真的活着"的更强信号（比单纯收推送更直接）。已登记为 topic `ack`。

**⑦ 导航状态 + 定位位姿 `1002/7`（**实测新增**，1Hz）** — `Items:{NavStatus, LocationStatus}`：
```
NavStatus:      Value · Status · ErrorCode · LoopCnt · RemainingCnt · Name（任务名）
LocationStatus: Location(定位状态) · PosX/PosY/PosZ · Roll/Pitch/Yaw · Confidence · Relocation
```
> **价值**：这一帧给出机器人在地图中的位姿与定位置信度 —— 本期非目标（不做导航编排），
> 但字段先落库，将来要在页面上画"机器人位置/轨迹"时无需再改协议层。

#### 10.4.1 实测频率对照（10 秒窗口，226 帧）

| 消息 | 实测帧数 | 折算频率 | docs/04 标称 | 结论 |
|---|---|---|---|---|
| `1002/4` 运控 | 101 | ~10Hz | 10Hz | ✅ 一致 |
| `100/100` 心跳应答 | 50 | 5Hz（=心跳频率） | 未载 | ✅ 新增 |
| `1002/3` 异常 | 25 | ~2.5Hz（2Hz + 变更额外） | 2Hz + 变更额外 | ✅ 一致 |
| `1002/5` 设备 | 20 | 2Hz | 2Hz | ✅ 一致 |
| `1002/6` 基础 | 20 | 2Hz | 2Hz | ✅ 一致 |
| `1002/7` 导航/定位 | 10 | 1Hz | 未载 | ✅ 新增 |

#### 10.4.2 实测闭合的问题

| 问题 | 实测结论 |
|---|---|
| **Q1** 监听地址 | `basic_server`(pid 3063) 监听 **`0.0.0.0:30000`(UDP) / `0.0.0.0:30001`(TCP)** —— 绑全网卡，故 `127.0.0.1` / `10.21.31.103` / `10.21.33.103` **均可达**。✅ 闭合（后端配置可用 `127.0.0.1`，最稳） |
| **Q3** 同一 socket 回包 | 心跳发出 50 条，**同一 socket 收回 226 帧**。✅ 闭合 |
| **Q12** 电池块数 / 关节数 | 电池 **2 块** ✅、关节 **16 个** ✅、电机温度 **16 路** ✅。闭合（剩余仅 errorCode 枚举与 MotionStatus 单位未载） |

### 10.5 控制安全序列（实现约束，与服务端闸门一一对应）

1. **轴指令双重前置条件**（docs/04 §1.2.5 原文"仅支持在常规模式下执行" + §1.2.3 状态机）：`ControlUsageMode=0`（常规）**且** `MotionState∈{站立(1), RL控制(17)}`。步态切换会自动切到对应运动模式（标准/敏捷），无需手动先切模式。服务端下发轴指令前校验这两项。
2. **软急停**：`MotionParam=2`（关节阻尼）= 停止所有运动，Web 端必备急停按钮（比"断网"可靠——断网只停发送，不停机器人）。
3. **持续指令看门狗（只停不趴，2026-10-15 二次事故修正）**：轴指令 20Hz 循环中，**松杆 / 停更 250ms / 断连 / 停机 → 零位一帧 + 停发**，之后保持停等待恢复；**绝不自动软急停**（两次真机事故均为自动软急停所致：运动中被打急停栽倒、站立中被打急停卸力软塌——机制整体切除，软急停只由人触发）。**绝不让机器人带着最后一条指令无限运动。**
4. **值域钳制**：服务端对 [-1,1] 截断——浏览器不是可信边界。
5. **黑名单**：`Charge=2` 任何配置下拒绝（ADR-004）。

### 10.6 与 lite3 协议的区别（改造点）

| lite3 | m20Pro |
|---|---|
| 裸 UDP 推送，无需请求 | **心跳驱动**：不发心跳就收不到任何推送 |
| 二进制 `0x0901/0x0902/0x0903` + `struct` 解析 | **帧头 + JSON**：`struct` 只解 16 字节帧头，帧体 `json.loads` |
| 对端 IP 直推 | 机器人=服务端(:30000)，外部=客户端；推送回到心跳发送方 socket |
| 12 关节（3 自由度×4 腿） | **16 关节（4 自由度×4 腿，轮足含轮毂）** |

### 10.7 来源与许可
- docs/04：厂商《软件开发指南 V1.3.0》（内部资料，字段语义以此为准）。
- m20-android-sdk：Apache-2.0，<https://github.com/DeepRoboticsLab/m20-android-sdk>。**只参考其帧格式与连接参数，按协议以 Python 重实现，不复制其代码。**

## 11. 其余数据接口

### 11.1 ROS2 话题（增强通道，可选）
- 传感器驱动话题（docs/04 §2.1）、运动相关话题（§2.2，含运动状态转换 / 运动基本状态与步态）、速度相关话题（§2.3）、自主充电相关话题（§2.4）。
- 用途：作为本体监控协议之外的补充（如更细的传感器流）。参照项目已内置 `ros_direct_source` 思路，可低成本启用（ADR-001、§18）。
- 真实话题列表待 `ros2 topic list` on 196 实测（Q4）。

### 11.2 视频
- MediaMTX（**运行在 AOS 本机**：`10.21.31.103:8554/video1`（前）/`video2`（后），196 上即 `127.0.0.1:8554`）；外部 SRS 汇聚点 `172.31.68.227` 收 `live/m20pro-f|b`。
  > 注：早期稿曾误写为"GOS 提供 RTSP"，但 `10.21.31.103` = AOS 内网 IP（GOS 为 `.104`），相机与 mediamtx 进程实测均在 AOS → 已修正。
- 控制台前端播放建议走后端代理 RTSP → HLS/WebRTC（§6.3），避免浏览器直连跨网/协议不兼容。
- `video1`/`video2` 前后映射**已于 2026-10-15 目视核实**（Q5 闭环）：**video1 = 前路，video2 = 后路**；取证帧存 `note/evidence-20261015/`（cam-video1=前：开放实验区视角；cam-video2=后：柜门特写）。前端"前相机/后相机"按钮映射与之一致。

### 11.3 既有 Web 控制台（196）
- 196 上 `m20video`（3000 端口）**已停用、禁自启**；`basic_server` 监听 30001/30002。可借鉴其前端交互范式，但**端口不能与之冲突**（C5）。

---

# 第四部分 执行计划

## 12. 复用映射（lite3 → m20Pro）

### 12.1 参照项目结构（已核对）

```
lite3_robot_monitor/
backend/
  main.py              # FastAPI 应用 + WebSocket 10Hz 推送
  config.py            # 配置（IP/端口/频率/视频源）
  data_source.py       # 数据源抽象
  udp_receiver.py      # UDP 接收
  udp_sniffer.py       # AF_PACKET 旁路抓包（无 CAP_NET_RAW 时回退 bind）
  parser.py            # Lite3 报文解析（0x0901/0x0902/0x0903）
  state_manager.py     # 状态聚合
  models.py            # 数据模型
  ros_bridge_node.py / ros_direct_source.py / ros_env.py /
  ros_profiles.py / ros_switch.py / ros_topic_adapter.py   # 已内置 ROS2 桥接
  control_protocol.py / control_service.py                 # 已内置控制通道（默认关）
  requirements.txt
frontend/
  src/App.vue
  src/components/  IMUChart / JointPanel / RobotStatus / PacketMonitor /
                   RawPacket / ControlPanel / HoverTip / SentPacket / RosInfoTip /
                   ToastHost.vue
  src/composables/ useRobotState.js / useToast.js
  src/api/index.js  # WebSocket 客户端
  src/utils/rosMeta.js
  vite.config.js / package.json
deploy/  # systemd + venv 部署资产
```

**可直接复用**：FastAPI 应用、WebSocket 推送、状态管理、前端 Vue 组件与样式、`useRobotState` 组合式函数、部署骨架。
**需改造**：数据接入层（解析器 + 增加心跳发送器）、配置项、状态字段模型、新增视频组件。

### 12.2 文件级映射表

| lite3 文件 | 动作 | m20Pro 对应 / 说明 |
|---|---|---|
| `backend/config.py` | 改 | 目标 IP/端口（AOS 本体:30000）、心跳频率、视频源（MediaMTX）、控制开关（enable/分层/黑名单）、监听端口（避开 30001/30002） |
| `backend/parser.py` | **重写** | Lite3 `0x0901/0x0902/0x0903` 二进制 → m20Pro **16 字节帧头 + JSON(PatrolDevice) 解析**（基础/运控含 16 关节/设备/异常）；字段映射按 §10.4 已核实结构 |
| `backend/udp_receiver.py` + `udp_sniffer.py` | 改 | 复用 socket 机制；**新增心跳发送线程**（≥1Hz 发往 :30000）；同一 socket 收发；**不移植 AF_PACKET 旁路抓包**（m20Pro 同主机内网口，无需也不应旁路） |
| `backend/ros_*.py` | 复用/可选 | 若启用 ROS2 增强通道，直接复用 `ros_direct_source` 思路 |
| `backend/control_*.py` | **改造+启用** | 本期真实实现：`ControlSink`/`UdpControlSink` + `patrol_codec`（指令全集 §10.3）+ `axis_watchdog`（看门狗）+ 分层安全闸（L0/L1/L2）+ 审计日志 |
| `backend/main.py` | 复用 | FastAPI + WebSocket 10Hz 推送，接 m20Pro `StateStore`；新增控制 REST 端点（`/api/v1/control/*`） |
| `backend/state_manager.py` | 改 | 字段对齐 m20Pro 状态集（基础/运控/设备/异常，§10.4） |
| `backend/models.py` | 改 | 数据模型对齐 m20Pro ASDU 字段（含 16 关节、BatteryList、ErrorList） |
| `frontend/src/components/*` | 复用+对齐 | 字段对齐；**新增视频播放组件**（hls.js，本期只做 HLS；WebRTC 后续升级）；`JointPanel` 须按 **16 关节（轮足 4 自由度×4 腿）** 重排，不能沿用 lite3 的 12 关节布局 |
| `frontend/src/composables/useRobotState.js` | 复用 | 基本不变 |
| `deploy/` | 复用 | systemd unit（端口/可达性适配），README/QUICKSTART 改写 |

## 13. 技术栈清单

### 13.1 后端（Python 3 + FastAPI）

| 层 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.8.10（venv 隔离） | ADR-009。**2026-10-14 实测修正**：196 上是 3.8.10（原写 3.10+），故全工程按 3.8 兼容编码——不使用 `dict[str,x]` 等 3.9+ 运行时泛型，统一走 `typing` |
| Web 框架 | FastAPI | REST + WS + 静态托管一体，单端口部署 |
| ASGI 服务器 | uvicorn（workers=1） | 单进程足够；ingestion 独立线程 |
| 配置 | pydantic-settings | 启动校验 fail-fast（ADR-008） |
| 数据校验 / 模型 | pydantic v2 | 领域模型 + 边界校验 |
| 并发 | asyncio（HTTP/WS）+ 1 个 ingestion 线程（UDP 阻塞收包） | 收包与推送解耦 |
| 二进制解析 | 标准库 `struct` | 16 字节帧头解析，零第三方依赖 |
| 视频 | ffmpeg 子进程（RTSP → HLS） | 复用 196 已有 ffmpeg，硬解走 `/dev/mpp_service` |
| 持久化 | 无（内存 + 有界环形缓冲）；后续 SQLite（标准库 `sqlite3`） | ADR-007 |
| 日志 | stdlib logging + JSON formatter | 结构化，零额外依赖 |
| 测试 | pytest + `MockSource` | 无真机验证主干 |

### 13.2 前端（复用 lite3，仅增量）

| 层 | 选型 |
|---|---|
| 框架 | Vue 3 + Vite |
| 图表 | ECharts（`IMUChart` / `JointPanel` 复用） |
| 状态 | 组合式函数 `useRobotState`（WS 快照） |
| 视频播放 | **hls.js**（新增，`VideoPanel.vue`） |
| 构建产物 | FastAPI 静态托管（单端口） |

### 13.3 依赖最小化原则
后端**只引入**：`fastapi` / `uvicorn` / `pydantic` / `pydantic-settings`（开发态加 `pytest`）。其余一律标准库或外部进程（ffmpeg）——**依赖越少，196 上出问题的面越小**。

## 14. 分阶段执行清单（优先级 / 依赖 / 验收标准）

### 14.0 优先级与依赖约定

- **优先级**：**P0** = 阶段目标成立的必要条件，缺失则里程碑不成立；**P1** = 本期应完成，可容忍降级（如视频先单路）；**P2** = 后续用例驱动，本期不承诺。
- **依赖总原则**：
  1. **没有 mock 不上真机**——一切真机任务（T2.x）必须等 M1 全链路绿；
  2. **契约先行**——前端依赖 `GET /api/v1/schema`（T1.7），不依赖后端实现细节；
  3. **视频与数据链零依赖**——T3.2 只依赖后端代理框架（T1.6）与 196 MediaMTX 在线，可与 M2 并行；
  4. **脱敏红线**——任何配置/口令只进 `*.example`，真实凭据不入库（仓库约定）。

### 14.1 范围决策点（2026-10-14 用户确认无异议，已锁定）

| # | 决策点 | 锁定结论 | 理由 |
|---|---|---|---|
| D1 | 视频是否本期 | **做，但收缩范围**：HLS 单路先行（video1），video2 复用同管道；**WebRTC 不做** | 视频是参照项目核心体验；取流源用 196 本机 MediaMTX `127.0.0.1:8554`（近零中继，风险低）；hls.js 1–3s 延迟满足监控场景，WebRTC（8889）留作后续低延迟升级 |
| D2 | 控制通道 | **本期集成（分层开放）**：L0 只监默认；L1 低危可控（站立/趴下/软急停/步态/模式/照明/休眠唤醒/充电/轴指令，需 enable+二次确认+WS 租约）；L2 黑名单（Charge=2 永不开放）；软急停不受开关限制；轴指令看门狗零位兜底 | 用户本期明确要求 Web 控运动 + 唤醒传感器；协议真相判明（帧头+JSON）后成本大降；安全用四道闸保障（分层+看门狗+前置校验+审计），详见 ADR-004 与 §10.5 |
| D3 | MockSource 覆盖 | **全部 5 类 ASDU 消息集 + 文件回放模式**：`1002/6` 基础 / `1002/4` 运控（16 关节）/ `1002/5` 设备（BatteryList）/ `1002/3` 异常（ErrorList）/ `1101/7` 休眠查询响应 | M1 零真机验证全链路（含异常展示与 stale 降级）；mapping 表成为 Q2 的占位契约——真机对接只换解析函数不改上层；回放模式让 M2 之后可无真机回归 |

### 14.2 M1：骨架 + Mock 全链路（无需真机、零风险）

| ID | 任务 | 优先级 | 依赖 | 验收标准 |
|---|---|---|---|---|
| T1.1 | 项目骨架：按 §5.3 目录建 `m20Pro_robot_monitor/` 后端（feature-first），参照 lite3 复用可复用部分，**剥离 Lite3 专属**（`0x0901` 解析 / `ros_profiles` / AF_PACKET 旁路抓包），建 venv 跑通空壳前后端 | P0 | — | 空壳前后端本地跑通，`/health` 200 |
| T1.2 | 配置系统：pydantic-settings + fail-fast（端口占用检测、IP 格式校验、目标不可达早失败），产出 `config.example.toml` | P0 | T1.1 | 缺配/错配启动即报错并指明字段名 |
| T1.3 | `DataSource` 抽象 + `MockSource`：接口 `start()/stop()/on_frame(cb)`；构造**全部 5 类 ASDU 帧**（§10.4 确切结构）+ 文件回放模式（按时间戳重发） | P0 | T1.1 | Mock 驱动下 5 类帧全链路可见 |
| T1.4 | 协议 ACL `asdu_parser.py`：16 字节帧头校验 + JSON(PatrolDevice) 字段映射表（按 §10.4），逐字段标注置信度 `[已确认]`/`[推断]`/`[未知]` | P0 | T1.3 | 每字段有置信度标注；未知字段进核对清单 |
| T1.5 | 领域模型 + 状态管理：`RobotSnapshot` 模型（含 16 关节 / BatteryList / ErrorList）、字段级 stale（>500ms 标记停更）、有界原始报文环形缓冲（调试用） | P0 | T1.4 | stale 语义单测通过；环形缓冲有界不涨内存 |
| T1.6 | 后端服务：FastAPI + WS 10Hz 推送 + `/health` `/ready`（ready 含数据新鲜度）+ SIGTERM 优雅停机 + 结构化 JSON 日志 | P0 | T1.5 | WS 10Hz 实测；优雅停机无丢连接异常 |
| T1.7 | 契约冻结：`GET /api/v1/schema` + WS 快照 JSON schema 契约测试 | P0 | T1.6 | schema 测试进 pytest，契约破坏即红 |
| T1.8 | 控制通道实现（ADR-004）：`ControlSink`/`UdpControlSink`（同一 UDP socket 真实出口）+ `patrol_codec`（指令全集 §10.3）+ 分层安全闸（L0/L1/L2 + 黑名单 + 前置校验 + 值域钳制 + 审计日志） | P0 | T1.2 | L1 白名单指令可发；Charge=2 任何配置拒绝；审计日志完整 |
| T1.9 | 前端骨架：Vue3 构建 + `useRobotState` 接 WS + `RobotStatus`/`JointPanel` 字段对齐 + stale 红色横幅与面板置灰 | P0 | T1.7 | Mock 驱动下四大状态面板有数据，停更时正确降级 |
| T1.10 | 轴指令看门狗 `axis_watchdog.py`：20Hz 循环发送；**只停不趴**（停更/断连/停机 → 零位停发等待恢复；**绝不自动软急停**） | P0 | T1.8 | ✅ **2026-10-15 二次事故修正完成**：自动软急停机制整体切除（两次事故复盘，车侧日志实锤）；单测 69 项全绿（含 10s/60s/10min 超长"不软急停"断言）；196 真机行为验证通过（断流不软急停、恢复继续、松手/停机只停不趴） |
| T1.11 | 测试套件：MockSource 全链路 pytest（状态流 / stale / 降级 / WS 快照 / schema 契约 / 控制分层 / 看门狗时序） | P0 | T1.10 | `pytest` 全绿 |

### 14.3 M2：真机数据接入（需 196 上机窗口）

| ID | 任务 | 优先级 | 依赖 | 验收标准 |
|---|---|---|---|---|
| T2.1 | 上机前置核查（只读）：`ss -lunp`/`ss -ltnp` 核实监听地址与端口（Q1）、回包是否同 socket（Q3）；chrony 状态复查（C6） | P0 | 196 在线 | ✅ **已于 2026-10-14 经 SSH 完成**（无需现场）：Q1/Q3/C6 全部闭环，结论见 §10.4.2 / §17；工具 `tools/probe_asdu.py`，抓包 `tools/capture/asdu_loopback_20261015.jsonl` |
| T2.2 | 心跳发送器：≥1Hz 发往 `10.21.31.103:30000`，WiFi 丢包重试、断线重连 | P0 | T2.1, T1.6 | 连续心跳 5 分钟无中断记录 |
| T2.3 | UDP 接收：同 socket 收 ASDU 推送；乱序/丢包容错（时间戳或序列号检测） | P0 | T2.2 | 推送持续到达，WS 面板实时更新 |
| T2.4 | `asdu_parser` 字段精化：真机回放逐字段核对（**Q2 闭环**），更新 mapping 表置信度，输出《ASDU 字段核对报告》（含电池块数、errorCode 枚举、MotionStatus 单位） | P0 | T2.3, T1.4 | docs/04 §1.3 逐字段有结论，`[未知]` 清零或转风险 |
| T2.5 | 推送频率实测核对（基础 2Hz / 运控 10Hz / 设备 2Hz / 异常 2Hz+变更 是否与文档一致） | P1 | T2.4 | 实测频率表入文档 |
| T2.6 | 回放模式固化：真机抓包存为回放文件，供后续无真机回归测试 | P1 | T2.4 | 回放文件 + 一键重放入口 |
| T2.7 | **控制指令真机首测（Q10，高风险）**：空旷场地 + 人员看护；顺序 = 照明/休眠唤醒（最稳）→ 站立/趴下 → 步态 → 轴指令（低速短时，先确认常规模式+站立前置）；每步核对审计日志与状态反馈 | P0 | T2.4, T1.8 | ✅ **2026-10-15 完成**：全链路实测通过，**车体首次被控制台驱动移动**；轴值标定（0.25≈0.32m/s 舒适 / 0.40≈0.54m/s 上限 / ≥0.70 危险已禁用）；顺带修正"松手即软急停"缺陷；详见 `note/T2.7 控制实测记录（2026-10-15）.md` |
| T2.8 | GPS 时间同步实验（可选）：发 (1101,16) 观察是否校准 196 时钟（C6） | P2 | T2.1 | 有效则记录命令；无效则关闭并备注 |

### 14.4 M3：前端对齐 + 视频（视频支线与数据链零依赖，可并行）

| ID | 任务 | 优先级 | 依赖 | 验收标准 |
|---|---|---|---|---|
| T3.1 | 前端全字段对齐：IMUChart / JointPanel / PacketMonitor / RawPacket 按 m20Pro 字段改造（**JointPanel 按 16 关节轮足结构重排**） | P0 | T1.9 | 面板字段与 schema 契约一致 |
| T3.2 | 视频管道：ffmpeg 子进程 `rtsp://127.0.0.1:8554/video1` → HLS；`VideoPanel.vue` + hls.js | P1 | T1.6, 196 MediaMTX 在线 | ✅ **已实现并在真机验证**：`backend/video/video_proxy.py` + `VideoPanel.vue`；196 实测**首切片 1s**（≤3s ✅）、片段有界 1.1MB、无转码（`-c:v copy`）。⚠️ 前置：需先唤醒机器人（§6.3.1）。**2026-10-15 修复**：`VideoPanel.vue` 曾遗漏未挂进 `App.vue`（页面看不到视频面板）→ 已修复并重建部署，新 bundle 含 HLS 逻辑（LAN 实测 200） |
| T3.3 | video2 复用同管道（前/后切换 UI） | P1 | T3.2 | ✅ **已实现**：`POST /api/v1/video/source` + `VideoPanel` 前/后按钮；196 实测 `video2` 同样有流（800×600 H.264 30fps） |
| T3.4 | 视频降级：源不可用时面板状态提示而非白屏 | P1 | T3.2 | ✅ **已实现**：`status().available=False` → 面板显示"视频源不可用/未开启"及原因；3s 轮询，上游恢复自动重挂播放器 |
| T3.5 | Q5 闭环：video1/video2 前后映射物理核实（插拔/现场确认） | P1 | T3.2 | ✅ **已闭环**（2026-10-15）：两路 RTSP 各抓一帧存证（`note/evidence-20261015/cam-video1.jpg` / `cam-video2.jpg`），**用户目视确认：video1 = 前路，video2 = 后路**；前端标签映射与之一致，结论已回写 §11.2 与 §17 |
| T3.6 | **MotionPanel 运动控制面板**：**虚拟摇杆（模拟遥感，参考 lite3 ControlPanel；前后+左右 / 前后+转向 两模式）** + 速度上限输入（满舵=所填数值）+ 站立(起立)/趴下/唤醒/软急停按钮 + 步态开关；拖动 ≈16Hz 持续下发、松手零位停发（不软急停）；控制开关二次确认；断连自动停 | P0 | T1.9, T1.8 | Mock 驱动下 UI 全流程可走通；看门狗行为可见（停发即零位）；**2026-10-15 真机实测通过**（轴指令驱动车体移动 + 速度标定 + 摇杆改造上线；二次事故后加固：切后台自动松手 + 首推自动续约） |

### 14.5 M4：部署 + 文档 + 验收

| ID | 任务 | 优先级 | 依赖 | 验收标准 |
|---|---|---|---|---|
| T4.1 | 部署资产：`/home/djw/monitor` + venv + systemd `m20pro-console.service`（`Restart=on-failure`）；脚本 LF 行尾 | P0 | T2.3, T3.3 | ✅ **已完成并真机验收**（2026-10-15）：`deploy/{pack.sh, install.sh, deploy_196.sh, m20pro-console.service}`；`install.sh` 自带三层降级（venv→apt python3.8-venv→virtualenv）+ http 镜像装依赖；验收脚本 `tools/verify_deploy.py` **13/13 通过**，LAN 从 PC 访问 `http://192.168.0.196:8080/` 正常。**安装路径已按用户指定最终定为 `/home/djw/monitor`**（同日从首装位置 `/userdata/m20pro-console` 迁移并复验 13/13；旧目录已于同日清理，迁移后线上服务 `active`、6 topic 全 fresh） |
| T4.2 | 端到端时延记录：心跳→推送→WS→渲染全链路实测 | P1 | T4.1 | 时延数据入文档 |
| T4.3 | 文档：README / QUICKSTART / 开发者文档（架构-部署-调试-回放） | P0 | T4.1 | ✅ **已完成**（2026-10-15）：根目录 `README.md`（架构总览/目录/协议速览/接口/配置/安全/测试）+ `QUICKSTART.md`（三步部署/验证/无真机演练/日常迭代/故障速查）+ `docs/{architecture,deployment,debugging,replay}.md` 四份开发者文档；补 `.gitignore`；父级 `m20Pro/README.md` 索引已同步 |
| T4.4 | 部署验收清单：LAN 访问 / stale 降级 / 视频播放 / **控制分层与看门狗（断 WS 即停）** / 日志 / 端口无冲突 | P0 | T4.1 | 清单逐项通过 |
| T4.5 | 收尾：无硬编码 IP/口令、`*.example` 化、提交前脱敏检查 | P0 | 全部 | 脱敏检查通过后才可提交 |

## 15. 部署方案

- **目标主机**：AOS `192.168.0.196`（user / 公钥认证，参考 `../../scripts/m20ssh`）。
- **安装路径**：**`/home/djw/monitor`**（用户指定的最终部署目录；与 `/` 同在 overlayroot，14G 可用，磁盘结论同 C6 不变）。首装曾落在 `/userdata/m20pro-console`，2026-10-15 已整体迁移并复验；旧目录（26MB，无独有配置文件）已于同日审计后删除，删除后线上服务复检正常。
- **运行方式**：venv + systemd `m20pro-console.service`（`Restart=on-failure`，复用 lite3 `deploy/` 模式）；前端构建产物由 FastAPI 静态托管（**单端口，简化**）。
- **端口规划**（已按 C5 锁定）：Web + REST + WS 同源 `8080`、HLS `8081`；**避开 `30001`/`30002`（`basic_server`）、`3000`（`m20video` 遗留）、`8554`/`1935`/`8888`/`8889`（MediaMTX）与 `21`/`22`/`9393`**。
- **可达性**：前端对 LAN 开放；后端心跳对 AOS 内网（`10.21.31.103:30000`，同主机）。
- **绑核建议**：给 console 分配 2–3 个空闲核；注意 `nproc`=4 是登录 shell cgroup 假象，真实 8 核，避开已在用的核（见 196 巡检报告）。
- **时钟注意**：196 系统时钟慢约 846 天 → 任何 HTTPS/TLS 调用会失败；若控制台上 HTTPS 需先修 `chrony`（`chronyc makestep` + `makestep 1 -1`）。
- **日志**：journald（`SyslogIdentifier=m20pro-console`，`journalctl -u m20pro-console` 查看），无独立日志目录。

### 15.1 构建与交付流程（在哪写、在哪构建、在哪装）

> **结论：本地写码 + 本地构建前端 + 传源码到 103（196），由 103 侧建 venv 装依赖。**
> 即"本地开发打包 → 上传 → 主机安装"（复用 lite3 `deploy/pack.sh` + `install.sh` + `deploy_103.sh` 已跑通的链路）。
> 两个极端都不可取：**本地"编译"后整包装**不行（见下），**直接在 103 上编写**也不行。

| 环节 | 在哪做 | 为什么 |
|---|---|---|
| 写码 / 版本控制 | **本地 PC** | 仓库在工作区；改动可评审、可回溯。上机直接改会导致"主机上的版本才是真相"，无法回溯 |
| 前端 `npm run build` | **本地 PC** | 196 的 Node **未验证**（ADR-009）；且 196 时钟慢 846 天 → npm 走 HTTPS 会因证书校验失败；`node_modules` 数百 MB 不该上传 |
| 后端 Python 依赖 / venv | **103 主机（196）** | 目标是 aarch64 Linux，**Windows 上建的 venv 不可移植**——`pydantic-core` 等含 C 扩展的 wheel 平台不匹配，整包拷过去必崩 |
| venv 目录位置 | 196 `/home/djw/monitor/venv` | 用户指定最终路径；`/`（overlayroot）14G 可用（C6） |
| systemd 注册 / 启停 | 196 主机侧 | `install.sh` 在主机执行 |
| 日常迭代同步 | 本地 → rsync → restart | 复用 `deploy_103.sh`：只同步 `backend/` + `frontend/dist/`，再 `systemctl restart` |

**上机装依赖的前置阻塞（必做，否则 pip 100% 失败）**：196 系统时钟慢约 846 天 → 任何 HTTPS/TLS 调用（pip/npm/git）都会因证书校验失败。
处理方式（择一）：① `chronyc makestep` + 配置 `makestep 1 -1`（推荐，顺带修好时间线）；② `PIP_INDEX=<http 镜像>` 走非 TLS 源；③ 预先 `pip download` 取 aarch64 wheel 离线安装。

> **✅ 已选定方案一并已执行完毕**（2026-10-14）：
> - `chronyc makestep` 返回 `200 OK` **但 `date` 未变**（chrony 源全部 `^?` 不可用、Update interval 0.0）→ 追加 `sudo date -s @<本地 epoch>` 直接校时成功，`date` 已回到 `2026-10-14`。
> - chrony 配置 `makestep 1 -1` 已就位（固化）。
> - **经验**：`makestep` 不生效时用 `date -s` 兜底，不要卡在 chrony 上。
> - 后续 M2/部署时若发现时钟又漂移，先查 chronyd 是否具备 `CAP_SYS_TIME`。

**上机装依赖的第二、三个坑（2026-10-14 实测）**：
1. **缺 `ensurepip`** → `python3 -m venv` 必失败，须先 `sudo apt install -y python3.8-venv python3-pip`（这正是 lite3 `install.sh` 里已记录的 Ubuntu 20.04 老坑）。
2. **HTTPS 通但极慢**（`pypi.org/simple/` 约 47MB，12s 未传完）→ 见下方"时钟问题修订"。
3. 磁盘：`/userdata`（独立分区）剩 14G，`/` 同为 18G（overlayroot）——**两处容量等价**，最终按用户指定装 `/home/djw/monitor`（在 `/` 分区上）。

#### ⚠️ 时钟问题修订（2026-10-15 二次实测，方案一未持久）

按方案一校时后**时钟又被拉回 2024-06-20**（约 20 秒内），排查结论：
- chrony 的 **8 个参考源本身全部返回 `-20306h`（慢 846 天）**，且 Reach=377（源可达）——即上游 NTP 给出的就是错时间；
- `makestep 1 -1` 允许**反向**步进，反而让 chrony 把手动校时又拉了回去；
- 停掉 `chronyd`（`systemd-timesyncd`/`ntp` 本就未运行）后**仍**被拉回 → 存在未识别的第三方对时来源（待查，可能是机器人内部对时服务）；
- `hwclock -r` 显示 RTC 比系统时间快 846 天（硬件时钟本身偏移）。

**结论与对策**：
1. **控制台不受影响** —— 新鲜度一律用 `time.monotonic()`（ADR-006），`PatrolDevice.Time` 只作展示不做判定。**这次实测反过来验证了该决策的正确性。**
2. **装依赖改用 HTTP 镜像 + `--trusted-host`，绕开 TLS/时钟依赖**（实测 `http://mirrors.aliyun.com/pypi/simple/` 返回 200，清华 http 返回 403）：
   ```
   pip install -r requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ \
       --trusted-host mirrors.aliyun.com
   ```
3. 现场排障注意：**196 上日志/文件时间戳仍显示 2024**，不要据此判断事件先后。

**其余已知坑**：① 脚本换行符必须 LF（`.gitattributes` 已固化，Windows 检出仍可能带 CRLF，部署前 `sed -i 's/\r$//'`）；② 196 WiFi 间歇丢包 → `scp`/`rsync` 需带重试；③ 只传 `frontend/dist`，不传 `node_modules`（`pack.sh` 已如此处理）。

#### 部署期实测踩坑（2026-10-15，已在脚本/代码里修掉）

| 坑 | 现象 | 修法 |
|---|---|---|
| **`cp -r` 嵌套** | 目标目录已存在时 `cp -r src dst/` 会拷成 `dst/backend/backend`，服务仍跑旧代码（表现为"改了不生效"） | `install.sh` 改用 `copy_dir()`（`rsync -a --delete` 或 `cp -r src/. dst/`）+ 清理遗留嵌套目录 |
| **静态挂载顺序** | `/`（前端 catch-all）先挂载会把 `/hls/*` 吃掉 → HLS 播放列表 404 | `main.py` 先挂 `/hls` 再挂 `/`（具体路由先于兜底路由） |
| **CRLF** | Windows 编辑的 `.sh` 在 Linux 上 `bad interpreter` | 上传后 `sed -i 's/\r$//'` |
| **打包静默失败** | `pack.sh` 输出被丢弃时失败不易察觉，导致上传了**旧包**（部署后改动没生效） | 打包后核对包内文件版本再上传 |

#### 部署验收结果（2026-10-15，`tools/verify_deploy.py`）
13/13 通过：`/health`(connected, source=udp) · `/ready`(非降级) · 6 个 topic 全部 fresh ·
schema 契约 1.0 · 视频代理 running+available · 前端静态 200 · HLS 播放列表 200 ·
**LAN 从 PC 访问 `http://192.168.0.196:8080/` 正常**。
实测快照：关节 16 · 电池 2 块（左 88 / 右 16）· 电机温度 16 路 · 定位位置与置信度可读 · 机型 PRO。

**安装路径迁移（同日）**：按用户指定，部署目录由首装的 `/userdata/m20pro-console` 迁至 **`/home/djw/monitor`**，
`install.sh`/`m20pro-console.service`/`deploy_196.sh` 默认值已同步切换，迁移后复跑验收仍 13/13。
⚠️ 注意：`djw` 用户当时在 196 上不存在（`/home/djw` 属 root，`monitor` 子目录属 `user`）→
`install.sh` 的 `RUN_USER` 自动探测已降级为 `user` 并 warn；服务实际以 `user` 运行，功能不受影响，
待 `djw` 用户创建后可改为以 `djw` 运行（需 `chown -R djw:djw /home/djw/monitor` + 改 service `User=`）。

**M1 阶段无需 103**：M1 全程在本地用 MockSource 开发（§14.2），只有 M2（§14.3）才需要上机窗口。

### 15.2 服务管理命令 `m20monitor`（2026-10-15 新增）

统一的服务管理入口，命令风格对齐厂商 `m20video`（up/down/reset），解决"Web 页面不可用/服务挂掉时如何从终端恢复"：

| 命令 | 作用 |
|---|---|
| `m20monitor up` | 启动（health 就绪才返回成功） |
| `m20monitor down` | 停止（端口释放才返回） |
| `m20monitor reset` | 重启 |
| `m20monitor status` | 状态总览（服务/端口/HTTP 健康；默认命令） |
| `m20monitor log [n\|f]` | 日志（默认 50 行；f=跟踪） |
| `m20monitor enable / disable` | 开机自启开关 |

- **实现**：`/usr/local/bin/m20monitor`（源 `deploy/m20monitor`，无后缀、`.gitattributes` 已固化 LF）+ `/etc/sudoers.d/m20-monitor` 精确 NOPASSWD 白名单（仅本单元 5 个管理动作；**不整脚本提权**，脚本被替换也拿不到白名单外权限；白名单缺失自动回退交互式 sudo）。
- **安装**：`sudo bash deploy/install_m20monitor.sh [用户名]`（幂等；`--uninstall` 卸载）；主 `install.sh` 已含为第 **7/7** 步（重装即带）。
- **与 Web 控制台的关系**：网页「服务启停」按钮与本命令管理同一 systemd 单元，互为备份通道——**页面起不来时用本命令恢复**。
- 从 PC 一步直达：`ssh m20pro-f20-0-196 "m20monitor status"`。

## 16. 里程碑与关键路径

### 16.1 阶段门（每阶段出口标准，不达标不进下一阶段）

| 里程碑 | 出口标准 | 外部依赖 |
|---|---|---|
| M1 | pytest 全绿 + Mock 驱动下浏览器可见四大状态面板与 stale 降级 + schema 契约测试通过 + **控制分层/看门狗单测全绿** | **无**（立即可开工） |
| M2 | 真机 ASDU 推送持续到达 + 字段核对报告完成 + **控制实测报告完成（Q10 闭环）** | **196 在线**（chrony 已校准更佳） |
| M3 | 前端字段全对齐 + HLS 视频可播（起播 ≤3s）+ **MotionPanel 可走通（含看门狗行为）** | 196 MediaMTX 在线 |
| M4 | 部署验收清单全过 + 文档齐备 + 脱敏检查通过 | M2 / M3 达标 |

### 16.2 关键路径与依赖关系

**关键路径（P0 串行链，任何一环卡住全线等待）**：

```
T1.1 → T1.3 → T1.4 → T1.5 → T1.6 → T1.7 → T1.9 → T3.1 → T3.6 → T4.1 → T4.4
```

**并行支线（不阻塞关键路径）**：

```
├─ T1.1 → T1.2 → T1.8 → T1.10 → T1.11   控制链：配置就绪 → 控制通道 → 看门狗 → 测试，与数据链并行
├─ T1.6 → T3.2 → T3.3/T3.5              视频支线：只依赖后端代理框架 + 196 MediaMTX，可与 M2 并行
└─ T1.6 → T2.2 → T2.3 → T2.4 → T2.7/T2.8 真机支线：需 196 上机窗口（外部约束）
```

**依赖关系要点**：

1. **M1 是 M2/M3/M4 的共同前置**——T1.6（后端服务）与 T1.7（schema 契约）是两个汇合点：真机支线、视频支线、前端支线全部从它们分出；
2. **控制链全程可在 M1 内闭环**（T1.8/T1.10 用 MockSource 验证，不占真机窗口）——真机上只做 T2.7 实测确认；
3. **M2 是唯一受外部条件约束的阶段**（196 在线 + 上机窗口），M1 收尾时即应预约，否则完成后空转；**T2.7 控制首测须排在空旷场地 + 人员看护的窗口**；
4. **T2.4（字段精化）回写 T1.4 的 mapping 表**——这是"先占位后精化"的闭环，mapping 表结构在 M1 冻结，M2 只改内容不改结构；
5. **T4.1 同时依赖 T2.3 与 T3.3**——部署前数据链与视频链都必须达标，避免部署一个半成品再返工。

## 17. 风险与开放问题（需实测/确认）

| ID | 问题 | 对架构的影响 / 处置 |
|---|---|---|
| ~~Q1~~ | ~~监控协议服务端实际监听地址~~ **已闭合**（2026-10-14 SSH 实测） | `basic_server`(pid 3063) 监听 **`0.0.0.0:30000`(UDP)/`30001`(TCP)** → `127.0.0.1`/`10.21.31.103`/`10.21.33.103` **均可达**；配置默认已改用 `127.0.0.1`（最稳）。见 §10.4.2 |
| Q2 | ~~ASDU 逐字节布局与类型码未精读~~ **已基本关闭**：协议 = 16 字节帧头 + JSON（§10），无二进制布局谜团 | 残留风险仅为**状态字段语义**（Items 内字段含义、单位、枚举），M2 真机报文核对后回填（T2.4） |
| ~~Q3~~ | ~~UDP 回包是否从同一 socket 返回~~ **已闭合**（实测） | 心跳发出 50 条，**同一 socket 收回 226 帧** ✅。见 §10.4.2 |
| Q4 | ROS2 话题真实列表 | 仅影响预留的 `Ros2TopicSource`，不阻塞主线 |
| ~~Q5~~ | ~~`video1`/`video2` 前后映射未物理核实~~ **已闭合**（2026-10-15） | 两路流在线且参数一致（800×600 H.264 30fps）：`/dev/video0`→video1、`/dev/video2`→video2；**用户目视确认 video1 = 前 / video2 = 后**（抓帧取证，见 §11.2、T3.5） |
| Q6 | 196 时钟慢 ~846 天 | 已用"不依赖 HTTPS"规避；**新机会**：GPS 时间同步指令（1101,16，§10.3）或可让机器人校准全主机——但当前 GPS 无定位（1–5 星），列为 M2 可选实验（T2.8） |
| Q7 | 196 WiFi 间歇丢包 | 心跳/WS 均已设计重试与 stale 兜底；**轴指令对丢包更敏感**（20Hz 丢几包影响平滑性）→ 看门狗**只停不趴**（停更只零位停发等待恢复；**绝不自动软急停**——链路断了车侧 150ms 看门狗自会清零；2026-10-15 二次修正） |
| Q8 | HLS 硬解在 196 上的可用性未验证 | 若不支持则软解，需重估 CPU 预算 |
| Q9 | `8080`/`8081` 是否被占用 | 部署前 `ss -ltn` 核查 |
| Q10 | **控制指令真机未验证**（轴指令响应特性、站立前置、软急停行为、步态值域） | M2 上机首测须在**空旷场地 + 人员看护**下进行；先 L1 低危（站立/照明/休眠）后轴指令；每步留审计日志（T2.7） |
| Q11 | 控制开启时 WS 断开 → 机器人运动状态未知 | 看门狗**只停不趴**（零位停发等待恢复；**绝不自动软急停**，2026-10-15 二次修正）；前端重连后自动续约恢复、切后台自动松手 |
| Q12 | ~~电池块数/关节数~~ **已闭合**（实测：2 块电池、16 关节、16 路电机温度）；残留：errorCode 枚举、MotionStatus 单位文档未载 | 残留项不影响本期功能（异常面板展示 code+component 原值即可）；M2 若需枚举映射再补 |

## 18. 演进策略（ROS2 兼容与迁移路径）

### 18.0 核心论据：部署形态与数据来源正交
模块化单体是**部署形态**（一个进程、一个 systemd 单元、一台主机 196），ROS2 中心化是**数据来源与总线语义**（谁产生状态、谁编排控制）。二者被三层抽象隔开，互不绑架：

1. **数据入口抽象 `DataSource`**（§5.4）：`M20UdpHeartbeatSource`（当前实现）与 `Ros2TopicSource`（未来）实现同一接口 `start() / stop() / on_frame(cb)`，上层 `StateStore` 只见规范化后的 `RobotSnapshot`，**不知道也不关心帧来自 UDP 还是 DDS topic**。
2. **控制出口抽象 `ControlSink`**（ADR-010，对称设计）：`UdpControlSink`（当前）与 `Ros2ControlSink`（未来）实现同一接口 `send(cmd) / result()`，上层控制服务只见 `ControlCommand` 领域对象，不知道出口是 ASDU 报文还是 ROS2 topic/service。
3. **前后端契约冻结 `GET /api/v1/schema`**（§5.4）：WS 快照 JSON 的 schema 由后端显式发布并做契约测试，**前端只依赖 schema 不依赖数据来源**。来源换了，schema 不变，前端零改动。

> 一句话：**换数据来源不动上层，换后端不动前端。** 这就是"后期兼容"的全部机制，从 v1 起就埋好，不需要推倒重来。

### 18.1 三条迁移路径（按侵入性递增）

**路径 1｜`Ros2TopicSource` 接入（推荐首选，零架构改动）**
- 在 `sources/` 下新增 `Ros2TopicSource`，实现 `DataSource` 接口；ROS2 依赖**运行时按需导入**（`rclpy` 缺失时优雅降级为"仅 UDP 源"）。
- 两个 source **可同时运行**：UDP 心跳源 + ROS2 订阅源并存，`StateStore` 按"字段级新鲜度"仲裁（ROS2 帧带 `frame.stamp`，UDP 帧带 `recv_monotonic`，各自 staleness 独立判定）。此模式可长期共存——比如运控关节走 ROS2（10Hz+）、设备电池走 UDP ASDU（协议里没有对应 topic 时）。
- 工作量：新增 1 个源适配器 + 字段仲裁规则，**不动**状态层、WS 层、控制层、前端。

**路径 2｜独立 ros_bridge 进程接入（隔离演进，适合 ROS2 生态爆炸期）**
- 若 ROS2 侧要挂的东西越来越多（多机器人、Nav2、SLAM、RViz 工具链），把 ROS2 相关代码拆为**独立进程** `m20pro-ros-bridge`（复用 lite3 的 `ros_bridge_node` 思路），它订阅 ROS2 后**以与 ASDU 推送相同的 WS/REST 契约**向主进程回传，或主进程反向订阅它。
- 好处：`rclpy` 的崩溃/资源占用不波及主控制台进程；ROS2 环境变量、DDS 发现、domain id 全部关在子进程里。
- 代价：多一个 systemd 单元、跨进程序列化开销（本地回环可忽略）。

**路径 3｜彻底 ROS2 中心化（换后端不换前端）**
- 终局形态：本体监控协议退居"ROS2 不可用时的降级通道"，主数据面换成 ROS2 topic（运动状态）/service（控制）。
- **前端零改动**——因为 §5.4 的 WS 快照 schema 从 v1 就冻结并由 `GET /api/v1/schema` 契约测试守护；换掉的是 FastAPI 后端（可整体换成 ROS2 `rclpy` + FastAPI 混合，或纯 `rosbridge_suite` + 前端 WebSocket）。
- 触发条件（三者其一）：① 官方本体监控协议弃用；② 需要消费第三方 ROS2 生态（Nav2 规划结果、语义地图）；③ 多机器人编排要求 DDS 原生发现机制。

### 18.2 迁移代价对比

| 路径 | 架构改动 | 代码改动 | 停机 | 可回退性 |
|---|---|---|---|---|
| 1 `Ros2TopicSource` | 无 | 新增源适配器 | 零（滚动重启） | 删文件即回退 |
| 2 独立 bridge 进程 | 中（+1 单元） | 拆进程 + 适配契约 | 零 | 停单元即回退 |
| 3 ROS2 中心化 | 大（换后端） | 前端 0 行、后端重写 | 计划窗口 | 保留 UDP 源即降级回退 |

### 18.3 里程碑之外的后续可选（每项都只是新增实现或新模块，不动主干）
1. `Ros2TopicSource` → 导航任务监控；
2. SQLite 异常事件时间线（补 ADR-007 放弃的能力）；
3. WebRTC 低延迟通道；
4. AI 识别叠加（外部 AI 服务调研已有结论，采样器可复用）；
5. 控制通道逐步开放——**每一步都必须过一次安全闸评审**。

## 19. 决策点状态与下一步

### 19.1 决策点状态（2026-10-14 用户确认，全部关闭）

| 决策点 | 结论 | 状态 |
|---|---|---|
| 架构形态 | **选 A（模块化单体）**，C（微服务）明确拒绝 | ✅ 已确认 |
| 后期兼容 ROS2 中心化 | **能，且为既定目标非事后补救**（见 §18 三条迁移路径） | ✅ 已确认 |
| 视频是否本期 | **做，收缩为 HLS 单路先行**（video1，video2 复用管道）；WebRTC 留后续低延迟升级 | ✅ 已确认 |
| 控制通道 | **本期集成、分层开放**（L0 只监默认 / L1 低危可控 / L2 黑名单；ADR-004） | ✅ 已确认 |
| MockSource 覆盖 | **全部 5 类 ASDU 消息集 + 文件回放模式** | ✅ 已确认 |
| 后端语言 | **Python 3 + FastAPI**（Go/Node/Rust/C++ 净损益均为负，ADR-009） | ✅ 已确认 |

### 19.2 下一步
1. **进入实现**：全部决策点已锁定（2026-10-14 用户确认无异议），本文档即执行依据。
2. **M1 立即开工**（无需真机、零风险）：T1.1–T1.11 按 §16.2 推进；**控制链（T1.8/T1.10）在 M1 内用 MockSource 全闭环**，不占真机窗口。T1.4 的字段映射表直接采用 §10.4 已核实结构（置信度标注随真机核对滚动更新）。
3. **同步预约 196 上机窗口**：M2 的唯一外部约束；建议 M1 收尾时预约，避免完成后空等。上机先做 T2.1 只读核查（Q1/Q3/C6），再动心跳；**T2.7 控制首测必须排在空旷场地 + 人员看护的时段**。
4. **视频支线可提前并行**：T1.6 完成后即可启动 T3.2（只依赖后端代理框架 + 196 MediaMTX 在线），不必等 M2。
5. M2 完成后按 §18 路径 1 评估是否加挂 `Ros2TopicSource`（本期不承诺，用例驱动）。

> 本文件为执行稿，未改动任何运行时/部署文件；全部决策点已锁定，进入 M1 实现阶段。
