# M20 Pro Web 控制台（m20Pro_robot_monitor）

> 云深处 **山猫 M20 Pro** 四足（轮足）机器人的 **Web 监控控制台**：浏览器实时查看机器人状态、播放前后相机画面、分层开放地控制机器人。
> 参照 Lite3 的成熟方案 `../../../lite3/lite3_robot_monitor/` 改造而来（FastAPI + Vue3 + WebSocket）。
> 当前已部署在 AOS 主机 **192.168.0.196** 的 `/home/djw/monitor`，LAN 内浏览器直接访问。

> **新人先读这里**
> - 想快速部署/上手 → [QUICKSTART.md](QUICKSTART.md)：构建 → 打包 → 安装 → 验证，10 分钟版
> - 想看完整方案与决策过程 → [note/ 计划书](note/M20%20Pro%20Web%20控制台%20—%20计划书v1.md)（一体化母文档，含协议参考 / ADR / 执行清单）
> - 开发与排障 → [docs/](docs/)：架构 / 部署 / 调试 / 回放 四份开发者文档

---

## 一、架构总览

```
┌─────────────────────── AOS 196（192.168.0.196）───────────────────────┐
│                                                                      │
│  机器人本体状态推送                         ┌── 浏览器（LAN）────────┐ │
│  basic_server 0.0.0.0:30000 (UDP)         │  状态面板 / 关节 / 控制  │ │
│      ▲  心跳 5Hz（同一 socket 收发）        │  视频面板（WebRTC 双路）│ │
│      │                                    └───────┬────────────────┘ │
│  ┌───┴────────────────────────────────────────────▼──────────────┐  │
│  │              m20pro-console（单进程 FastAPI @ :8080）           │  │
│  │                                                                 │  │
│  │  ingestion/           state/            realtime/               │  │
│  │  ├ udp_heartbeat ◄──► ├ StateStore       └ WsHub 10Hz 广播      │  │
│  │  ├ asdu_parser (ACL)  │  per-topic 新鲜度          ▲            │  │
│  │  └ mock/replay        └ 有界原始报文缓冲           │            │  │
│  │        │                      │                    │            │  │
│  │        ▼                      ▼                    ▼            │  │
│  │  control/  patrol_codec ─ ControlGateway(四道闸) ─ AxisWatchdog │  │
│  │  video/    VideoProxy: ffmpeg RTSP→HLS（-c:v copy 不转码）       │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│        │ 控制指令 UDP :30000          │ ffmpeg 拉流                   │
│        ▼                             ▼                               │
│   机器人本体（AOS 内）        MediaMTX rtsp://127.0.0.1:8554/video1|2 │
└──────────────────────────────────────────────────────────────────────┘
```

设计要点：

| 项 | 说明 |
| --- | --- |
| **协议真相** | 16 字节帧头（`EB 91 EB 90` …）+ UTF-8 JSON（`PatrolDevice` 信封）；解析 = 帧头校验 + `json.loads`，无二进制布局谜团 |
| **先 mock 后真机** | `MockSource` 用真实字节帧驱动全链路，无真机也可开发/回归；真机只做"换数据源 + 核对字段" |
| **契约先行** | WS 快照 JSON Schema（`/api/v1/schema`，版本 `1.0`）是前后端唯一契约；前端只认 schema 不认后端细节 |
| **绝不假数据** | per-topic 新鲜度（`stale`）显式下发，前端置灰/横幅提示；停更只标脏不删旧值 |
| **控制分层** | 默认 L0 只监；L1 需显式开启 + 二次确认 + WS 租约（**前端每 2s 自动续约**，2026-10-15 修复）；`Charge=2` 黑名单；软急停永不受限 |
| **看门狗兜底** | 轴指令 20Hz 循环 + **只停不趴**：停更/松杆/断连 → 零位停发等待恢复，**绝不自动软急停**（两次真机事故教训；软急停仅由人触发，2026-10-15 二次修正） |
| **视频链路（2026-10-16 改）** | **浏览器直连 MediaMTX v1.4.2**：主链路 WHEP/WebRTC `:8889`（~0.3s）、兜底 MediaMTX HLS `:8888`（~2–3s）、第三层后端 ffmpeg `/hls`；**前后两路同时看**，后端不再中转视频流 |
| **四标签页布局（2026-10-16 加，2026-10-17 增 GPS）** | 传感器监控 / 相机画面 / **GPS 定位** / 运动控制（写方向，放最后 + 警示色）；**一律 `v-show` 不卸载**（VideoPanel 卸载会拆取流、倒计时会断更）；**每次加载回到只读标签、不记忆上次标签**（防止重新开页直接落在写方向页误触）；**切走即松手**（摇杆有 `setPointerCapture`，多指触屏下会在后台继续驱动）；定时移动在后端继续跑，顶部黄条 + 标签角标跨标签可见 |
| **状态栅格防抖（2026-10-17 修）** | `.kv` 的数值 `white-space: nowrap` + `flex: 0 0 auto`（**数值优先、绝不折行**），标签空间不足时省略号；运动控制 / GPS 页的 `.grid` 改用**固定列数**（4/3/2/1 按断点），不再用 `auto-fill` —— 后者容器宽度差几像素就会跳变列数，造成"动不动就突然换行" |
| **心跳让渡（2026-10-16 加）** | `POST /api/v1/link/heartbeat` 主动停/恢复心跳。**心跳与指令是两个独立 UDP socket**——停心跳只断遥测、不动指令，故暂停前服务端**先自动零位停发控制**（不蒙眼开车），暂停期间驱动类指令被新闸 `TELEMETRY_PAUSED` 拒绝（软急停豁免）。前端把"主动暂停"（琥珀）与"链路故障"（红）分色展示。**实测：系统关停 50s 后机器人仍保持 RL 站立，不会趴** |
| **单端口** | 页面 / REST / WS / 后端 HLS 兜底 全部走 `8080`，少一个进程少一个端口 |
| **可换数据源** | `DataSource` / `ControlSink` 对称抽象；ROS2 接入（计划书 §18 路径 1）零架构改动 |
| **Python 3.8** | 196 实测 `python3` = 3.8.10，全工程不使用 3.9+ 语法 |

---

## 二、目录结构

```text
m20Pro_robot_monitor/
├── backend/
│   ├── main.py                # FastAPI 入口：REST + WS + 生命周期装配 + 静态托管
│   ├── config.py              # 集中配置（pydantic-settings，M20_ 前缀）+ 启动校验（fail fast）
│   ├── errors.py              # 领域异常（ProtocolError / ControlError 族）
│   ├── logging_setup.py       # 日志初始化（含 event 字段结构化）
│   ├── ingestion/             # 数据接入
│   │   ├── asdu_parser.py     #   ACL 防腐层：帧头校验 + JSON 解析 + topic 映射
│   │   ├── data_source.py     #   DataSource 抽象 + UdpHeartbeatSource（同 socket 收发）
│   │   └── mock_source.py     #   MockSource：构造 6 类真实字节帧 / JSONL 回放
│   ├── state/
│   │   ├── models.py          #   RobotSnapshot 契约模型 + snapshot_json_schema()
│   │   └── state_store.py     #   唯一权威状态仓库 + per-topic 新鲜度 + 有界原始报文缓冲
│   ├── realtime/
│   │   └── ws_hub.py          #   WS 连接池 + 10Hz 快照 fan-out
│   ├── control/
│   │   ├── patrol_codec.py    #   指令全集编解码（类型/命令/Items，值域钳制）
│   │   ├── control_gateway.py #   四道闸：开关+租约 / 黑名单 / 前置校验+钳制 / 审计
│   │   ├── axis_watchdog.py   #   20Hz 轴指令循环 + 只停不趴（停更→零位停发等待恢复；绝不自动软急停）
│   │   └── command_log.py     #   指令报文记录：完整字节帧 hex + 响应六态 + 查询缓存
│   ├── net/
│   │   ├── ap_ctl.py          #   WiFi 热点受控读写（SSID/密码），仿 video/service_ctl.py
│   │   └── __init__.py
│   └── video/
│       ├── video_proxy.py     # ffmpeg 子进程托管：RTSP → HLS（**第三层兜底**，主链路已改为直连）
│       └── service_ctl.py     # 推流服务受控提权入口（local / relay 两条链）
├── frontend/                  # Vue3 + Vite（echarts / hls.js）
│   └── src/
│       ├── App.vue            # 主布局 + 停更横幅（降级显式暴露）+ 五标签页（监控/相机/GPS/运动控制/机器人设置）
│       ├── api/index.js       # WS 客户端（自动重连）+ REST 助手
│       ├── composables/useRobotState.js
│       ├── webrtc/whep.js       # WHEP(WebRTC) 拉流客户端：连接 / 自动重连 / 释放会话
│       └── components/
│           ├── RobotStatus.vue  # 基础 / 设备（**逐块电池**+低电量告警）/ 异常 三面板
│           ├── JointPanel.vue   # 16 关节（轮足 4 腿 × HipX/HipY/Knee/Wheel）
│           ├── MotionPanel.vue  # 运动控制：**虚拟摇杆（模拟遥感）**/速度上限输入/站立(起立)/趴下/软急停/步态
│           ├── RobotConfigPanel.vue # 机器人设置：补光灯 / 首启回零 / 休眠 / WiFi 热点
│           ├── DeviceToggle.vue # 设备开关（状态+动作分离，高亮当前态；==0 才判关）
│           └── VideoPanel.vue   # 前后双路：WebRTC(WHEP) 主 + HLS 兜底 + 布局切换
├── deploy/
│   ├── pack.sh                # PC 侧：打精简部署包（自动剔除 node_modules / venv）
│   ├── _apply.sh              # 196 侧：应用部署包（**自己解压 tarball**，避免"传新包用旧目录"）
│   ├── install.sh             # 196 侧：一键安装（venv + http 镜像装依赖 + systemd + m20monitor 命令）
│   ├── deploy_196.sh          # PC 侧：日常迭代增量同步（rsync backend + dist → restart）
│   ├── deploy_196_tar.sh      # PC 侧：无 rsync 降级版（tar over scp，Windows 用这个）
│   ├── m20monitor             # 服务管理命令（up/down/reset/status/log/enable/disable）
│   ├── install_m20monitor.sh  # 安装 m20monitor + sudoers 免密白名单（幂等；install.sh 第 7 步调用）
│   ├── m20-ap-ctl             # WiFi 热点受控提权脚本（status / set --confirmed，值走 stdin）
│   ├── sudoers-m20-ap-ctl     # 对应 sudoers 白名单（零通配符，只放行上述两条）
│   ├── m20-video-ctl          # 推流服务受控提权脚本（local / relay × status|start|stop|restart）
│   ├── sudoers-m20-video-ctl  # 对应 sudoers 白名单
│   └── m20pro-console.service # systemd 单元（含全部环境变量）
├── tools/
│   ├── probe_asdu.py          # 独立探针（仅标准库）：上机只读探测 + 抓包到 JSONL
│   ├── probe_cmd.py           # 指令探针：先发心跳注册再发目标指令，可监听 1002/5 设备帧
│   ├── re_cmdtable.py         # 逆向：从 objdump 反汇编还原 (Type,Command) → handler 地址表
│   ├── re_cmdname.py          # 逆向：地址 → cmdHandle_* 函数名
│   ├── analyze_capture.py     # 抓包分析：按消息类型统计 + 与映射表比对
│   ├── verify_deploy.py       # 部署验收 13 项（在 196 本地或 LAN 跑）
│   └── capture/               # 真机抓包 fixtures（226 帧，测试用）
├── tests/                     # pytest 212 项（解析 / 状态 / 契约 / 控制 / 看门狗 / 视频 / 机器人设置 / 热点 / 回归）
├── docs/                      # 开发者文档：architecture / deployment / debugging / replay
├── note/                      # 计划书（母文档）+ DESIGN/PROTOCOL 指引桩
├── config.example.toml        # 配置示例（真实配置只走环境变量或 *.example）
└── requirements.txt
```

> `frontend/node_modules`、`frontend/dist`、`venv`、`__pycache__`、`hls` 产物均不入库（见 `.gitignore`）。

---

## 三、协议速览（细节见计划书 §10）

**帧格式**：16 字节帧头 + UTF-8 JSON。

```
EB 91 EB 90 | dataSize(LE16) | messageID(LE16) | protocolType(0x01) | 7×00 | JSON...
```

> ⚠️ **帧头 magic 有第二个取值 `EB 90 EB 90`**（厂商 App 使用）。2026-10-17 真机取证：
> **DeviceControl 类指令（`1101 / 3` 设备开关）只认 `EB 90 EB 90`**，用 `EB 91 EB 90` 下发会得到
> `ErrorCode 57351 / "No operation permission"`。两种 magic 对其余指令（心跳 / 运动 / 查询）
> **完全等价**，因此只在 `1101 / 3` 上按需切换，绝不全局替换。由
> `patrol_codec.encode()` 按指令自动处理，调用方无感。详见计划书 ADR-018。

JSON 为 `PatrolDevice` 信封：`{"PatrolDevice": {"Type": …, "Command": …, "Time": …, "Items": {…}}}`。

**状态消息（机器人 → 控制台）**：

| Type/Command | topic | 内容 | 实测频率 |
| --- | --- | --- | --- |
| `1002 / 6` | `basic` | 运动状态 / 步态 / 充电 / 硬急停 HES / 使用模式 / 休眠 / 机型 | 2Hz |
| `1002 / 4` | `motion` | 姿态角速度 + **16 关节**（4 腿 × HipX/HipY/Knee/Wheel，轮足） | 10Hz |
| `1002 / 5` | `device` | `BatteryList`（多电池：电压/电量/温度/充电）、16 路电机温度 | 2Hz |
| `1002 / 3` | `fault` | `ErrorList`（错误码 + 部件），正常为空 | 2Hz + 变更 |
| `1002 / 7` | `nav` | `NavStatus` + `LocationStatus`（位姿/置信度） | 1Hz（真机实测新增） |
| `1101 / 7` | `sleep` | 休眠状态查询响应 | 0.2Hz |
| `100 / 100` | `ack` | 心跳应答（含 ErrorCode） | — |

**控制指令（控制台 → 机器人，全集见 `backend/control/patrol_codec.py`）**：

| 指令 | Type/Command | 说明 |
| --- | --- | --- |
| 运动状态 | `2 / 22` | `MotionParam`：0 空闲 / 1 站立 / 2 阻尼(软急停) / 3 开机阻尼 / 4 趴下 / 17 RL 控制 |
| 步态 | `2 / 23` | `GaitParam`：0x1001 基础 / 0x1003 楼梯 / 0x3002 平地敏捷 / 0x3003 楼梯敏捷 |
| 六轴轴指令 | `2 / 21` | X/Y/Z/Roll/Pitch/Yaw ∈ [-1,1]（**服务端安全上限 ±0.40**），**仅站立/RL + 常规模式可执行** |
| 使用模式 | `1101 / 5` | 0 常规 / 1 导航 / 2 辅助 |
| **前后补光灯** | `1101 / 2` | 前/后照明灯开关（**不是** `LedHost/LedExt` 电源指示灯）。状态在设备帧 `1002/5` 的 `Led.Fill.Front/Back` 回读，约 1s 翻转 → 可闭环校验 |
| **休眠设置** | `1101 / 6` | `Sleep=true` 整车休眠（趴下+依次断电，需确认）；`Sleep=false` 唤醒；`Auto`/`Time` 只改自动休眠策略。⚠️ `Time` 车侧**静默夹取**到 5~30，见 §3.5 |
| 休眠查询 | `1101 / 7` | 回 `{"Sleep":0,"Auto":false,"Time":10}` |
| **首启回零开关** | `1101 / 10`（写）/ `1101 / 11`（读） | 写**车侧不回帧**，必须靠 `1101/11` 回读校验（回 `{"Enable":bool}`） |
| **设备开关** | `1101 / 3` | **分设备供电控制**（2026-10-17 抓包破解，需授权 magic）。Items 键名决定目标：`Video`/`Lidar`（前后两路）、`GPS`/`LedHost`/`LedExt`/`LoadPower`/`FP`（单路）、`FanSpeed`（0~100）、`GPSMode`。键名走**白名单**，不透传任意键 |
| 整车重启 | `1101 / 17` | ⚠️ **故意不实现**（重启整车风险不可逆） |
| 充电 | `2 / 24` | ⚠️ `Charge=2`（清除充电状态）为 L2 黑名单，任何配置下拒绝 |

> 协议事实三处修正（v1.2 起）：M20 Pro 为**轮足 16 关节**（非 lite3 的 12 关节）；步态字段名是 **`GaitParam`**；`MotionParam` 值域只有 0/1/2/3/4/17。

### 3.1 关节回零与"唤醒"的真实语义（2026-10-17 取证，详见计划书 ADR-017）

**回零**：车侧 `basic_server.toml` 默认 `autoResetJointsZero = true` —— 这就是**开机后第一次站立会先回零**的成因。`BasicStatus` 里本来就有 `ResetJointsZero` / `StatusCode` 字段（此前未解析），控制台现已呈现到运动控制页。约束：basic_server 原文 `can not reset joints zero unless standing or lying down`。⚠️ 该字段**值域未见官方文档**，故界面只标注实测的 `0 = 无需回零`，其余透传数值，不臆造标签。

**唤醒**：docs/04 请求指令全集只有 11 条，**没有任何按相机 / 雷达 / GPS 单独开关的指令**；`1101 / 6` 是**整车**休眠开关。但休眠确实会连带关传感器 —— 运行日志实证进入休眠依次关 `LED_FILL` → `FAN_SPEED` → **`VIDEO_POWER`** → `JOINTS_POWER`。所以「唤醒退出休眠」**在效果上**就是恢复相机 / 雷达 / 灯 / 风扇供电，界面按钮因此统一标注为「唤醒**整车**」。

**分设备供电：状态可见 + 现在真的可控制了**（2026-10-17 抓包破解，详见计划书 ADR-018）。

`DeviceStatus.DevEnable` 实测结构如下，控制台已拆分呈现到各标签页：

| 字段 | 含义 | 呈现 / 控制位置 |
| --- | --- | --- |
| `Video.Front/Back` | 前/后相机供电 | **相机画面页**（前后独立开关） |
| `Lidar.Front/Back` | 前/后激光雷达供电 | **运动控制页**（前后独立开关） |
| `GPS` / `GPSMode` | GPS 使能 / 模式 | **GPS 定位页**（GPS 供电开关） |
| `LedHost` / `LedExt` / `FanSpeed` / `LoadPower` / `FP` | 主机灯 / 外接灯 / 风扇 / 负载电源 / 对频模块 | **运动控制页**「其他设备」 |

### 3.2 分设备开关 `1101 / 3`（2026-10-17 抓包 + 真机逐键实证）

**取证路径**：`tcpdump -i any` 抓 `30000` 端口 → 过滤掉 99 字节心跳 → 只留厂商 App
（`10.21.33.11`）的非心跳报文 → 对照车侧 `Basic_server.*.log` 的 `[CmdHandle]` 行确认语义。
破解关键一步：**对比 App 与我们自己的帧头**，发现差异在 magic —— 换用 `EB 90 EB 90` 后
`ErrorCode 57351` 立刻变 `0`。

**控制表**（Items 键名 → 车侧日志实证）：

| Items 键 | 值 | 车侧日志 | 说明 |
| --- | --- | --- | --- |
| `Video` | `{Front,Back}` 0/1 | 设置广角相机开关 | 断电后 `/dev/video*` 消失 + 推流 404 |
| `Lidar` | `{Front,Back}` 0/1 | 设置雷达开关 | 断电后感知输入消失 |
| `GPS` | 0/1 | 设置GPS开关 | 与 `1101/16` 时间同步是两回事 |
| `LedHost` / `LedExt` | 0/1 | 主机/外部负载电源指示灯开关 | — |
| `FanSpeed` | 0~100 | 设置风扇转速 | — |
| `LoadPower` | 0/1 | 设置外部负载开关 | — |
| `FP` | 0/1 | 设置对频模块开关 | 遥控器配对模块 |
| `GPSMode` | int | 设置GPS模式为 | **GNSS 系统掩码**（不是代号黑盒，位定义见 §3.3），GPS 页可切换 |

> ⚠️ **下发值统一 0/1，上报值不全是布尔**：真机实测 `DevEnable.Lidar` 开启后会变 `2`
> （车侧日志 `mLIDAR_POWER_.front 2` = 运行中；1 = 已供电/启动中；0 = 关）。
> 所以判定"是否关闭"只能用 `== 0`，写 `== 1` 会把运行中的雷达误判成已关闭。

### 3.3 GPSMode = GNSS 系统掩码（2026-10-17 取证，非推测）

`DevEnable.GPSMode` 不是"代号"，是**哪些卫星系统参与定位的位掩码**。位定义来自车侧
GNSS 驱动配置 `/opt/robot/share/node_driver/config/gps.yaml` 的 `sysMask` 注释原文：

| 位 | 值 | 系统 | 频点 |
| --- | --- | --- | --- |
| bit0 | `0x00001` | GPS | L1CA |
| bit4 | `0x00010` | BDS 北斗 | B1I |
| bit8 | `0x00100` | GLONASS | L1 |
| bit12 | `0x01000` | Galileo | E1 |
| bit16 | `0x10000` | QZSS | L1 |
| 全 | `0x11111` | 全系统（GN 模式） | — |

控制台**只显示星座真名**（`全系统（GN 模式）` / `仅 GPS` / `仅 北斗（BDS）` / …），
原始掩码 `0x11111` 作为副标注保留。GPS 页提供切换器；可选清单由后端
`/api/v1/schema` 的 `gps_modes` 提供（协议常量单一来源在 `asdu_parser`，
前端不硬编码掩码，避免与 `gps.yaml` 漂移）。

**★读数语义（重要，别误读）**：`DevEnable.GPSMode` 是**车侧实际生效值** ——
basic_server 收到 `gps_node` 上报后才更新。下发瞬间会短暂显示期望值，约 1–2s 后被
车侧真实值覆盖。**所以切换后必须回读校验**：GPS 页在 4s 后回读，若值没变就明确
提示「⚠ 已下发但车侧未生效」，**绝不假装成功**。

**★实测行为（2026-10-17）**：
- 切「仅 GPS」`0x00001`、切「仅北斗」`0x00010` → **真的生效**（`gps_node` 日志里
  `系统模式: GP / GB`、`系统掩码:` 同步变化）。
- **直接切回「全系统」`0x11111` 曾失败两次**（车侧回 `ErrorCode: 0` 但模块不应用）；
  改用**增量法**先切 `0x00011`（GPS+BDS）再切 `0x11111` → 成功。
- 旁证手段：`gps_node` 日志里的 `系统模式: XX` 是**从 NMEA 语句前缀反推的观测量**
  （`GP`/`GB`/`GA`/`GL`/`GN`）—— 多系统模式下前缀会**跳变**，单系统模式下**固定不变**，
  可用来判别"是否真的切了"。该日志在 `/var/opt/robot/log/<日期>/gps_node.*.log`。

**安全设计**（`control_gateway._check_device_switch`，第五道闸）：

1. **关闭必须二次确认** —— 断电不可逆，`confirmed=false` 一律 `CONFIRM_REQUIRED`（409）。
   ⚠️ **"是否在关闭"必须对比当前 `DevEnable` 判定**，不能只看目标值：Items 是**整键覆写**，
   开前相机时必然带上 `{"Video":{"Back":0}}` —— 那个 0 只是"保持后相机原本就关着"，
   不是关闭操作。只看目标值会把它误判成关闭 → 弹确认 → 而前端点「开」不弹框 →
   用户看到 `CONFIRM_REQUIRED`，表现为"点开启没反应"（2026-10-17 真踩）。
   读不到当前状态时**回退保守判定**（有 0 就要确认），宁严勿松。
2. **站立 / RL 态禁关雷达** —— 雷达是运控的平衡参考输入，`MotionState ∈ {1, 17}` 时
   关闭 `Lidar` 直接 `PRECONDITION_FAILED`。厂商 App 不拦，我们拦：真机连摔过两次，
   这类风险不该交给"手快点错"。开启随时允许。
3. **键名白名单** —— 不透传任意 Items：这条指令能断电任何设备，键名猜错等于盲目操作硬件。
   `pair` 类型必须显式给出 `Front` 与 `Back`（绝不默认 0，那等于悄悄断电）。

**按钮位置**（按用户要求分区）：相机页 → 相机；GPS 页 → GPS；运动控制页 → 雷达 + 其他设备。

### 3.4 推流服务控制（2026-10-17，相机页）

相机画面页底部有「推流服务」区，可启停**两条链**。**它们不是一回事，界面上分开标注**：

| 链条 | 组成 | 作用 | 关掉会怎样 |
| --- | --- | --- | --- |
| `local` **本地推流** | 厂商 `mediamtx` + `push_video.sh` | 把相机画面推到本机 MediaMTX | **控制台画面消失**（本页要看的画面） |
| `relay` **外推中继** | `m20video.service`（rtmp_1012） | 把 MediaMTX 画面转发到远端 RTMP 服务器 | 控制台**照旧**，只是外部看不到 |

**权限**：两条链都以 root 运行，而控制台跑在普通用户 `user`。做法是**收一个受控入口**
`/usr/local/sbin/m20-video-ctl`（源码 `deploy/m20-video-ctl`），它只接受
`status|start|stop|restart` × `local|relay` 这 8 种组合、**参数严格白名单、无可注入内容**；
sudoers 只放行它，且**逐条列出、不用通配符**（`deploy/sudoers-m20-video-ctl`）——
不给控制台 root，也不放开 systemctl 全权。

**★状态语义（比"进程在不在"重要得多）**：本地推流有个经典坏法 ——
**进程活着但不出流**（gst 存活、`mpph264enc` 内部报 NULL、HLS 拉不到）。
所以状态判的是 **HLS 能否 200 拉到**（`local.ready`），并把"有进程、没流"单独标成
`local.stuck` → 界面显示「**进程在但没出流（需重启推流）**」。
只报进程数会把坏链路显示成正常的 —— 实测第一次跑就靠这个抓到了现存故障。

**为什么 `start local` 不走厂商 `start_server.sh`**：那个脚本会 `sudo ./mediamtx &`
**再起一个 mediamtx**（本机 8554/8888 早已有一个），端口冲突；且它会「等 PTP 同步最多
60s」再**前台运行**推流脚本，直接把控制台 HTTP 线程挂住。而 `push_video.sh` 自身就是
带自愈的 supervisor（每路独立监控 + 指数退避重连 + trap 清理），后台直接跑它即可；
`mediamtx` 只在确实不在时才补启。

**★`local` 与 `relay` 是上下游，不是竞争关系**（用户问过"是不是冲突了"）：`config.env`
原文写着「源：本机 MediaMTX 提供的 RTSP 流 / 由 push_video.sh 推入」——
`local` 是**生产者**（独占相机 `/dev/video*` → 推入 MediaMTX），
`relay` 是**消费者**（从 MediaMTX 拉 RTSP → 转封 RTMP 发远端）。**两者碰的不是同一个资源。**
> `relay` 的派生现象：`local` 断流时它拉不到源 → 退避重试 → `rtmp-conn-guard.timer`
> 可能反复重启它 → **进程数堆积是 local 断流的连锁反应，不是冲突的原因。**

**★踩坑：多组 supervisor 抢同一批相机（画面"出几秒又断"的真因）**。
`push_video.sh` 必须**单实例**：多个并存会互相把对方的 gst 踢掉，实测表现为
`gst 2→0→2` 反复、`HLS 200` 一闪就没。成因有二：① `start` 不幂等（重复点就重复起）；
② 厂商 `stop.sh` 的 `pkill` 是异步的且**会留孤儿**（父进程先死、子进程被 init 收养后继续跑，
实测残留过整整两组）。故入口做了两件事：**`start` 先查已有 supervisor，有就不起**；
**`stop` 复查到清干净为止**（TERM → 等 → KILL），只对本脚本精确匹配的进程动手。

**⚠️ 命名禁忌**：厂商 `stop.sh` 会执行 `pkill -f v4l2` / `pkill -f push_video`，
任何调用链的**命令行里都不能出现这些字样**，否则会把自己杀掉。故入口用
`local` / `relay` 两个词，绝不写完整进程名。

**★链路全景（别把两条链搞混，常见误解）**：

```
相机 USB ──[local 本地推流]──► MediaMTX ──┬──► 控制台浏览器（WebRTC :8889 / 兜底 HLS :8888）
   /dev/video*   v4l2src→mpph264enc       │            ← 你看画面的这条路
                 →rtspclientsink（推 RTSP）│
                                  (:8554)  └──[relay 外推中继]──► 远端 RTMP
                                              rtspsrc→flvmux→rtmpsink   172.31.68.227:1936
                                              （拉 RTSP → 转 RTMP）
```

- **`local` 不是"拉 RTSP"，是"推 RTSP"**：从相机设备采集、硬编 H.264，再 `rtspclientsink`
  **推入**本机 MediaMTX（生产者）。
- **`relay` 才是"拉 RTSP → 转 RTMP"**（消费者，一进一出）。
- **控制台页面既不是 RTSP 也不是 RTMP** —— 浏览器走 WHEP/HLS；**RTSP 只是本机内部链路**。

**⚠️ 动作按钮不得依赖"状态读取成功"**（2026-10-17 真踩）：面板的动作按钮曾多带一个
`!state.ok` 条件，而「刷新」只判 `busy` —— 结果**状态查询一变慢/失败，启停按钮全灰、
只剩「刷新」可点**，用户原话就是"只能刷新不能停止"。动作与状态读取是**独立**的：
该让它去试、失败再报错，不要先替它断定不可用。

**⚠️ 不受控制闸约束（有意为之）**：这不是机器人指令，是 AOS 本机服务，与机器人运动无关。
而且"画面黑了想重启推流"很可能正好发生在控制通道没打开（L0）的时候 ——
把恢复手段锁在 L1 后面才是错的。`stop` 仍需二次确认。

**故障排查顺序（画面黑时）**：
1. 看「本地推流」是不是 `进程在但没出流` → 点「重启」；
2. 本地推流显示「在出流」但画面仍黑 → 问题在**取流侧**（看 `/api/v1/video/status`）；
3. 本地推流「未运行」且有摄像头设备 → 点「启动」；
4. 推流正常在等设备（日志 `等待摄像头设备...`）→ **问题在相机侧**：车侧供电
   （`DevEnable.Video`）+ USB 枚举。

**三层都要对，缺一层就没画面**（用户报"相机供电开了还是 HLS stopped"就是这个）：

| 层 | 怎么看 | 说明 |
| --- | --- | --- |
| ① 车侧供电标志 | `DevEnable.Video = 1/1` | 只是**软件标志**，置位 ≠ 设备出现 |
| ② 内核设备节点 | `ls /dev/video*` + `lsusb \| grep SM_USB_107X` | 真出现才算数 |
| ③ 推流服务 | 本页「推流服务」区的状态 | `在出流` 才是真的在推 |

> 实测过 ①② 都 OK 但 ③ 停了（推流进程在设备上线**之前**收到退出信号 →
> 之后没人等设备了）→ 点「启动」即可。也实测过 ① 置位、② 还没枚举完，
> 过一段时间 USB 自己回来了 —— **车侧 `restartVideoServer` 后设备重新枚举有滞后**，
> 别急着判硬件故障。

### 3.5 机器人设置页（2026-10-18，逆向 42 条指令表后新增）

2026-10-18 用 `nm` + `objdump -d` 反汇编 `/opt/robot/share/basic_server/bin/basic_server`
（符号未剥离）还原出**整张指令注册表共 42 条**，方法：注册结构是
`unordered_map<int, unordered_map<int, std::function>>`，以**内层 map 的 `operator[]`
调用为锚点**向前找两个不同栈槽的 `str` 即得 (Type, Command)，再用 `nm` 把 handler 地址
映射回 `cmdHandle_*` 函数名。工具在 `tools/re_cmdtable.py` / `tools/re_cmdname.py`。
新增的四个功能全部**真机实证**后才进界面。

#### 补光灯（`1101 / 2`）——唯一能闭环校验的一项

写 `{"Front":1,"Back":1}` 车侧回 `{"ErrorCode":0}`，**但状态不在响应里**；真正的状态在
设备帧 `1002/5` 的 `Items.Led.Fill.Front/Back`，下发后约 1s 翻转。所以界面是
"下发 → 等 2.5s → 读设备帧比对"，与 GPSMode 的回读校验同一套路。

⚠️ **与 `DevEnable.LedHost / LedExt` 不是一回事**：后者是主机/外接**电源指示灯**，
走 `1101/3` 设备供电；`Led.Fill` 才是**前后照明灯**。两者都叫 "Led"，极易混。

`1101/2` 是**整键下发**：开前灯必须把后灯当前值一起带上，缺一路等于把另一路关掉
（后端 `light()` 已保证，前端回填时也要注意）。

#### 首启回零开关（`1101 / 10` 写 / `1101 / 11` 读）

成因见 §3.1（`basic_server.toml` 的 `autoResetJointsZero`）。**写指令车侧不回帧** ——
实测发完 3s 无应答，但值确实改了。所以：

- 报文记录里这条会显示 `no_response`，**那是"不知道"，不是失败**；
- 界面点完自动补发 `1101/11` 回读，以回读结果为准（`age_s > 30` 标过期）；
- 关闭它（下次开机不标定直接站立）**需二次确认**，开启不需要。

#### 休眠（`1101 / 6` 写 / `1101 / 7` 读）

`1101/7` 回 `{"Sleep":0,"Auto":false,"Time":10}`：`Sleep` = 当前是否休眠（整数），
`Auto` = 自动休眠开关，`Time` = 分钟。三种用法差别很大：

| 用法 | 效果 | 需确认 |
| --- | --- | --- |
| `sleep=true` | **整车休眠**：趴下并依次断 LED→风扇→视频→关节供电 | ✅ |
| `sleep=false` | 唤醒整车 | ❌ |
| `auto=…, minutes=…` | 只改自动休眠策略，**不会立刻睡着** | ❌ |

⚠️ **`Time` 车侧静默夹取**：实测 12→生效、60→**30**、3→**5**，且**不回错误码**
（二进制里有串 `Sleep time shoud between 5 and 30`，但响应帧里没有它）。
用户填 60 被静默降成 30 是最难排查的一类问题，因此**后端 `robot_sleep` 先拒越界**
（`MINUTES_OUT_OF_RANGE`），根本不给车侧夹取的机会。前端输入框虽带 `min/max`，
但 HTML 校验不拦提交，不能依赖。

#### 喇叭 / 音响：无硬件，**做不了**

用户问过"能不能加外放声音"。2026-10-18 取证：`aplay -l` 输出为空、
`/proc/asound/cards` = `--- no soundcards ---`、`/dev/snd` 下只有 `seq` 和 `timer`，
**没有 PCM 设备**。即 AOS 主机本身不带音频硬件，不是软件没接 —— 故不加，也不造假。

#### WiFi 热点：双接口·单射频（ADR-026）

M20 的无线是**一块射频两个接口**：`phy#0` 上同时有 `wlan0`（type AP，`10.21.41.1/24`，
dnsmasq 发地址）和 `p2p0`（type managed，上联外部 WiFi，`192.168.0.196`）。
**AP 信道被上联绑架**：配置写的是 `band=bg`（2.4G），实际跟着上联跑
channel 40（5200 MHz）。

**结论（用户原始问题："连着外部 WiFi 时能不能改自身热点？"）**：
实测 `nmcli con down/up myap24G` 期间 **`p2p0` 全程 `100 connected`、`192.168.0.196`
未丢** → **可以改 SSID / 密码**。但**频段/信道改不了也不该开放**：与上联抢射频的
结果是 AP 起不来或直接把上行（我们的 SSH 通路）带下去。

厂商用**明文文件**管热点，这也是唯一可行的改法：

| 文件 | 内容 | 截断 |
| --- | --- | --- |
| `/var/opt/robot/conf/host_name` | 热点名 base | `head -c 12`，自动补 `_24G` / `_5G` |
| `/opt/robot/scripts/wifi/password` | 密码 | `head -c 16` |

生效靠 `/opt/robot/scripts/board_resources/wifi/ap_start.sh start 24G`
（先 `nmcli c delete myap…` 再 `nmcli c add` 重建连接）。

**为什么不能走 `nmcli con modify`**（两条路都实测走不通）：
① AP 处于 activated 时改 SSID 不生效，`con up` 也不会重新应用；
② 先 `con down` 再改，会撞上"AP 关停 → `wlan0` 消失 → 连接短暂不存在"，
`nmcli con modify` 直接报 `unknown connection`（rc=10）。
另外 AP 激活后有 **4~8s 假死期**（NetworkManager 的 ip-check/secondaries 状态机），
采一次状态就下结论会误判 —— 必须轮询到 `activated`。

`m20-ap-ctl` 的安全设计：

- 受控提权 `/usr/local/sbin/m20-ap-ctl`（root:root 0755）+ sudoers 白名单
  **零通配符**，只放行 `status` 与 `set --confirmed` 两条；
- **写入**的新值走 **stdin**（`ssid=…\npassword=…`）而不是 argv —— 密码不进 `ps` 输出，
  sudoers 也就不需要通配符。**读取**不受此限（见下）；
- **当前密码会回显**（2026-10-18 应用户要求加）：`status` 输出 `ap.password=<值>`，
  优先取 nmcli 连接 profile（那才是真正在生效的值），取不到再退回厂商明文文件。
  前端**默认打掩码**、点「显示」才展开 —— 控制台走 HTTP（196 时钟异常导致 HTTPS
  起不来），密码是明文过局域网的，掩码至少保证截图/屏幕共享不会顺手带出去。
  密码含控制字符或首尾空白时只报 `password_unreadable=1`：显示一个照着输会连不上
  的密码，比不显示更糟；
- 流程：值域校验 → 写两文件 → `ap_start.sh start 24G` → 轮询 AP activated(30s) →
  **复查上联(20s)**（掉了就回滚文件 + 重建 AP + 抢救上联）→
  用 `iw dev wlan0 info` 校验实际 SSID 是否等于 `base_24G`，不等也回滚；
- Python 侧（`backend/net/ap_ctl.py`）先手校验 SSID 1~32 / 密码 8~63，
  **只挡不可打印字符**（车上原名 `CA9B_NO.1273_24G` 含点，白名单若写
  `[a-zA-Z0-9_-]` 会连还原都做不到）。

**两个输入框留空即表示该项不改**（2026-10-18 真机实证）：只改 SSID 时
`/opt/robot/scripts/wifi/password` 的 md5 一字不变。所以不必为了改个名字
而去打听旧密码。

---

## 四、快速开始

> 完整步骤（含验证与排错）见 [QUICKSTART.md](QUICKSTART.md)。

```bash
# ① PC：构建前端（196 的 Node 未验证 + 时钟问题，前端必须本地构建）
cd frontend && npm run build && cd ..

# ② PC：打精简包并上传
bash deploy/pack.sh /tmp/m20console.tgz
scp /tmp/m20console.tgz m20pro-f20-0-196:/tmp/
scp deploy/_apply.sh    m20pro-f20-0-196:/tmp/

# ③ 196：解压安装（自动建 venv、http 镜像装依赖、注册 systemd 并启动）
ssh m20pro-f20-0-196
cd /tmp && tar xzf m20console.tgz
sudo bash m20pro_console/deploy/install.sh /home/djw/monitor
```

**日常迭代（依赖没变时，省掉 install.sh 的外网 pip 安装）**：

```bash
# PC：重新构建 + 打包 + 传包
cd frontend && npm run build && cd ..
bash deploy/pack.sh /tmp/m20console.tgz
scp /tmp/m20console.tgz m20pro-f20-0-196:/tmp/
scp deploy/_apply.sh    m20pro-f20-0-196:/tmp/

# 196：应用（_apply.sh 会自己解压，见下）
ssh m20pro-f20-0-196 "printf \"'\n\" | sudo -S bash /tmp/_apply.sh /tmp/m20console.tgz"
```

> ⚠️ `_apply.sh` **自己解压 tarball**，不是复用上一次解压的目录。曾经的坑：
> 只 scp 了新包却用旧目录，改动的代码没上车、页面还是旧的，而日志照样打印
> "部署成功" —— 这类"假成功"最难查。脚本现在会在日志里打出**包时间 + md5**，
> 可与 PC 侧 `md5sum` 对照确认用的就是这一包。
> 依赖有变化时才需要走完整的 `install.sh`（会建 venv 装依赖，需外网）。

验证：`python3 /home/djw/monitor/tools/verify_deploy.py`（13 项全绿即通过），浏览器打开 `http://192.168.0.196:8080/`。

**跑测试**（196 的 venv 只装运行依赖，没有 pytest；测试在 PC 侧跑）：

```bash
# PC：需要 fastapi/pydantic/httpx/pytest 的环境
python -m pytest tests/ -q          # 212 项
```

**无真机演练（本地 Mock）**：

```bash
cd backend
M20__DATA_SOURCE=mock python -m uvicorn main:app --port 8080
```

---

## 五、常用运维命令（196 上执行）

### 服务管理：`m20monitor`（2026-10-15 新增，风格对齐厂商 `m20video`）

| 命令 | 作用 |
| --- | --- |
| `m20monitor status` | 状态总览：服务 / 端口 / HTTP 健康 / 访问地址（**不带参数时的默认命令**） |
| `m20monitor up` | 启动（等待健康检查通过才返回成功） |
| `m20monitor down` | 停止（等待端口释放） |
| `m20monitor reset` | 重启（up/down 的合并流） |
| `m20monitor log [n\|f]` | 日志：默认最近 50 行；`n`=行数；`f`=持续跟踪 |
| `m20monitor enable` / `disable` | 开机自启开关（不影响当前运行） |

- **从 PC 一步直达**：`ssh m20pro-f20-0-196 "m20monitor status"`
- **实现与安装**：源 `deploy/m20monitor` → `/usr/local/bin/m20monitor`；`sudo bash deploy/install_m20monitor.sh [用户名]`（幂等，`--uninstall` 可卸载）；主 `install.sh` 第 7/7 步已自动包含。
- **提权模型**（最小面）：`/etc/sudoers.d/m20-monitor` 精确免密白名单——仅本服务的 `start / stop / restart / enable / disable` 五条 systemctl 命令；`status` / `log` 只读不提权。**不整脚本提权**（脚本被替换也拿不到白名单外权限）。白名单缺失时自动回退交互式 sudo。
- **196 现状（2026-10-17 起）**：控制台服务**已开启开机自启**（`is-enabled = enabled`，`WantedBy=multi-user.target`），机器人/196 重启后无需人工拉起。此前的"关闭自启"状态已作废。注意 `enable` / `disable` 只影响"下次开机"，**不影响当前运行**；需要临时改回手动启动时执行 `m20monitor disable`。
- **开机顺序加固**：单元新增 `After=start.service`（**仅排序、不加 `Requires`**）。厂商 `start.service`（Type=forking, enabled）负责拉起 `basic_server`（UDP 30000 状态源）与 `mediamtx`（RTSP 8554 相机源），让它先跑可以避免开机瞬间出现"链路断开/相机离线"的假警报；反之若厂商服务启动失败，控制台**照常启动**（只监不控，界面如实显示链路断开），绝不拖死开机。
- **开启自启的依据（2026-10-17 实测，AOS 独占测量）**：见下表 —— 控制台 CPU/内存占用**低于**运控 `rl_deploy` 与 `systemd-journal`，且 CPU 亲和与运控零重叠，不存在抢占运控资源的可能。

| 指标 | 控制台 `m20pro-console` | 对照 |
| --- | --- | --- |
| 常驻内存 RSS | **≈ 49 MB** | — |
| 线程数 | **4** | — |
| CPU（8 核总量口径）空载 | **1.71 %** | `rl_deploy` 12.7 %、`systemd-journald` 11.2 %、`yesense_node` 8.5 %、`basic_server` 3.7 %、`hsLidar` 2.6 % |
| CPU：1 客户端 10 Hz 取数 | **6.22 %** | — |
| CPU：2 个远程客户端 10 Hz | **4.33 %** | — |
| CPU：3 并发客户端 | **15.13 %** | — |
| 进程生命周期均值 %CPU | **6.7** | — |
| CPU 亲和 `Cpus_allowed_list` | **0-3** | `rl_deploy` 钉 **4-5**（内核 `isolcpus=0,4,5,6,7`）→ **与运控零重叠** |

> 测量口径说明：CPU 百分比为 8 核总量口径（非单核）。加压场景下请求**从 PC 侧发起**，避免把 HTTP 客户端自身的 CPU 算进目标进程。

### 其余运维与数据命令

| 用途 | 命令 |
| --- | --- |
| 服务状态 | `systemctl status m20pro-console` |
| 实时日志 | `journalctl -u m20pro-console -f` |
| 重启服务 | `sudo systemctl restart m20pro-console` |
| 健康检查 | `curl -s http://127.0.0.1:8080/health` |
| 就绪/降级 | `curl -s http://127.0.0.1:8080/ready` |
| 链路统计 | `curl -s http://127.0.0.1:8080/api/v1/status` |
| 原始报文 | `curl -s 'http://127.0.0.1:8080/api/v1/raw?limit=20'` |
| 部署验收 | `python3 /home/djw/monitor/tools/verify_deploy.py` |
| 唤醒机器人（相机通电） | `python3 /home/djw/monitor/tools/probe_asdu.py --send 1101/6 --items '{"Sleep":false}'` |

> 196 上 `sudo` 需要密码且非交互场景必须走管道：`printf "'\n" | sudo -S <cmd>`。

---

## 六、接口说明

### WebSocket

`ws://<host>:8080/ws/state` —— 服务端以 **10Hz** 主动推送完整快照（`RobotSnapshot`，schema 版本 `1.0`）。
建连即推一帧；客户端发任意文本可立即触发一帧（前端重连兜底用）。

```json
{
  "schema_version": "1.0",
  "type": "snapshot",
  "server_time": 1760500000.1,
  "connected": true,
  "since_last_update_ms": 32.5,
  "topics": {
    "basic":  {"ts": 1760500000.0, "age_ms": 120.0, "stale": false, "data": {"motion_state": 1, "gait": 4097, "...": "..."}},
    "motion": {"ts": 1760500000.1, "age_ms": 20.0,  "stale": false, "data": {"motor_status": {"Joint": ["...16 个"]}}}
  },
  "control": {"enabled": false, "estop": false, "lease_active": false, "lease_remaining": 0.0},
  "service": {"uptime_seconds": 120.0, "push_hz": 10, "data_source": "udp", "ws_clients": 1}
}
```

### REST

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 轻量健康检查（uptime / connected / data_source） |
| GET | `/ready` | 就绪 + 降级判定（fresh/stale topic、error_rate） |
| GET | `/api/v1/schema` | **WS 快照 JSON Schema（前后端契约）** |
| GET | `/api/v1/state` | 当前快照（HTTP 轮询备用） |
| GET | `/api/v1/status` | 服务与链路运行状态（含 source/ws 计数/控制/看门狗） |
| GET | `/api/v1/raw?limit=30` | 最近原始报文摘要（十六进制预览） |
| GET | `/api/v1/fields` | 逐字段置信度表 + 关节名对照 |
| GET | `/api/v1/video/streams` | **前后两路的取流要素**（WebRTC/HLS 端口与 path；**不含主机名**，前端按 `location.hostname` 拼） |
| GET | `/api/v1/video/status` | 视频代理状态（后端 ffmpeg 兜底：available/last_error/切片年龄） |
| POST | `/api/v1/video/start` / `stop` / `source` | 视频启停 / 前(后)切换 `{"url": "rtsp://…/video1\|video2"}` |
| GET | `/api/v1/control/status` | 控制开关 / 急停 / 租约 / 看门狗 |
| POST | `/api/v1/control/enable` | 开启/停用 L1（`{"enable": true, "confirmed": true}`，需二次确认） |
| POST | `/api/v1/control/lease` | 续约（**前端每 2s 自动续约**；WS 断开即失效） |
| POST | `/api/v1/control/command` | 白名单指令 `{"name": "stand_up", "params": {}, "confirmed": false}` |
| POST | `/api/v1/control/axis` | 轴指令（`continuous=true` 交看门狗 20Hz 循环）；`channel` 选通道（`steer` 2/21 默认 / `real` 2/25 实时） |
| POST | `/api/v1/control/axis/timed` | **定时移动**：`{x..yaw, duration_s: 0.5~30, channel}` → **后端计时**到点自动零位停止（先走 precheck，未开启/未站立即时拒发）；横移 + 标准系步态时响应附 `warning` 提示（只提示、不拦截） |
| POST | `/api/v1/control/axis/stop` | 松杆 / 中止定时：发零位停发（**不软急停**）；异常断开同走零位停发等待恢复 |
| POST | `/api/v1/control/estop` / `estop/clear` | 软急停（不受开关限制）/ 解除锁定 |
| POST | `/api/v1/link/heartbeat` | **暂停/恢复心跳（遥测让渡）**：`{"paused": true, "confirmed": true}` → 停发心跳、放弃状态推送（`paused=false` 恢复视野，安全动作不需确认）。**暂停前服务端自动零位停发正在进行的控制**；暂停期间驱动类指令被拒（`TELEMETRY_PAUSED`），软急停除外 |
| GET | `/api/v1/link/heartbeat` | 心跳状态：是否暂停 / 已发帧数 / 目标 |
| GET | `/api/v1/control/audit?limit=50` | 指令审计（谁/何时/发了什么/结果） |
| `GET /api/v1/video/service` | **推流服务状态**：本地推流 / 外推中继两条链（含"进程活着但没出流"识别） |
| `POST /api/v1/video/service` | **启停推流服务**：`{target: local\|relay, action: start\|stop\|restart, confirmed}`（`stop` 需确认） |
| `GET /api/v1/control/packets` | **指令报文记录**：发出的原始字节帧（hex）+ 机器人响应标记（见 §8.1） |
| GET | `/api/v1/robot/config` | **机器人设置三段当前值**：补光灯（`Led.Fill` 自动有）/ 首启回零 / 休眠（后两项需主动问，`known=false` 表示没问过，**不是"关闭"**） |
| POST | `/api/v1/robot/config/refresh` | 发 `1101/11` + `1101/7` 查询；应答异步到达，**2s 后**再读 GET |
| POST | `/api/v1/robot/light` | 补光灯 `{"front": 1, "back": 0}`（整键下发） |
| POST | `/api/v1/robot/auto_reset` | 首启回零 `{"enable": false, "confirmed": true}`（关需确认；**车侧不回帧**，成功时附 `verify_hint`） |
| POST | `/api/v1/robot/sleep` | 休眠 `{"sleep": true, "auto": false, "minutes": 10, "confirmed": true}`（`sleep=true` 需确认；`minutes` 越界 `MINUTES_OUT_OF_RANGE`） |
| GET | `/api/v1/net/ap` | **自身热点 + 上行链路状态**（共用一块射频，一起给；含当前密码，前端默认掩码） |
| POST | `/api/v1/net/ap` | 改热点 `{"ssid": "…", "password": "…", "confirmed": true}`（只开放 SSID/密码；**留空即不改该项**；失败自动回滚） |

---

## 七、配置速查（完整注释见 `config.example.toml`）

所有参数集中在 `backend/config.py`，环境变量覆盖，前缀 `M20_`（嵌套用 `__`）：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `M20__DATA_SOURCE` | `mock` | `mock` / `udp` / `ros2`(预留)；196 部署用 `udp` |
| `M20__REPLAY_FILE` | 空 | JSONL 回放文件（mock 模式下按时间戳重放） |
| `M20__LOG_LEVEL` | `INFO` | 日志级别 |
| `M20_ROBOT__TARGET_IP` | `127.0.0.1` | 监控协议服务端（basic_server 监听 0.0.0.0:30000，回环可达） |
| `M20_ROBOT__TARGET_PORT` | `30000` | UDP 监控协议端口 |
| `M20_ROBOT__HEARTBEAT_HZ` | `5.0` | 心跳频率（文档要求 ≥1Hz） |
| `M20_ROBOT__LINK_TIMEOUT` | `3.0` | 链路判定断开超时（秒） |
| `M20_STATE__STALE_THRESHOLD` | `0.5` | 停更基准阈值（秒）；per-topic 实际阈值 = max(基准, 2.5/推送周期) |
| `M20_SERVICE__PORT` | `8080` | Web 端口（已避让 196 全部冲突端口） |
| `M20_SERVICE__PUSH_HZ` | `10` | WS 推送频率 |
| `M20_CONTROL__ENABLED` | **`false`** | L0 只监默认；开启 L1 需同时改前端二次确认流程 |
| `M20_CONTROL__LEASE_SECONDS` | `5.0` | 控制租约（WS 断开即失效；前端每 2s 自动续约） |
| `M20_CONTROL__AXIS_TIMEOUT_MS` | `250` | 看门狗超时 → 零位停发（等待恢复，不软急停） |
| `M20_VIDEO__ENABLED` | `false` | 视频代理开关（196 部署为 `true`） |
| `M20_VIDEO__RTSP_URL` | `rtsp://127.0.0.1:8554/video1` | 取流源（196 本机 MediaMTX） |
| `M20_VIDEO__HLS_DIR` | `/tmp/m20-hls` | **后端 ffmpeg 兜底**的 HLS 产物目录（196 上为 `/home/djw/monitor/hls`） |
| `M20_VIDEO__WEBRTC_ENABLED` | `true` | WebRTC 主链路开关（置 false 则直接走 HLS 兜底） |
| `M20_VIDEO__WEBRTC_PORT` | `8889` | MediaMTX WebRTC/WHEP 端口（`webrtcAddress`） |
| `M20_VIDEO__MEDIAMTX_HLS_PORT` | `8888` | MediaMTX 自带 HLS 端口（兜底链路，非后端产物） |
| `M20_VIDEO__FRONT_PATH` / `BACK_PATH` | `video1` / `video2` | 前后两路 MediaMTX path（另有 `FRONT_LABEL`/`BACK_LABEL`） |

> ⚠️ 配置在启动时读取，**修改后必须重启服务**。不要改 `backend/config.py` 默认值再上机——用 systemd `Environment=`（或 `systemctl edit` drop-in）注入。

---

## 八、控制通道与安全（写方向）

六道闸（`ControlGateway.execute` 顺序执行）：

1. **黑名单**：`Charge=2`（清除充电状态，官方标注危险）任何配置下拒绝——**无"除非"**；
2. **分层开关**：L0 只监默认；开启 L1 需显式配置 + 前端二次确认；**软急停/心跳永不拦**（安全手段优先于开关）；
3. **前置校验 + 值域钳制**：轴指令要求 `MotionState∈{1 站立, 17 RL}` 且常规模式；X/Y/Z/Roll/Pitch/Yaw 服务端二次截断到 **±0.40 安全上限**（2026-10-15 实测：0.25≈0.32m/s 舒适 / 0.40≈0.54m/s 上限 / ≥0.70 危险；浏览器不是可信边界）；
4. **全量审计**：每条指令（含被拒）落审计环 500 条，`GET /api/v1/control/audit` 可查；
5. **设备供电开关专项**（2026-10-17 加，见 §3.2）：**按当前状态**判定"是否在关闭"（关闭需二次确认 `CONFIRM_REQUIRED`，409）；站立/RL 态禁关**正在运行**的雷达（`PRECONDITION_FAILED`）；Items 键名白名单 + 值域校验（`BAD_PARAMS`，400，**不发报文**）；
6. **按方向确认**（2026-10-18 加，见 §3.5）：`patrol_codec.needs_confirm()` 只拦**危险方向** ——
   整车休眠（`sleep` + `enable=true`）与关闭首启回零（`auto_reset_set` + `enable=false`）需
   `confirmed=true`；反向操作（唤醒 / 开回零）不拦。休眠时长越界在更前面就被
   `MINUTES_OUT_OF_RANGE` 挡掉（车侧会静默夹取，见 §3.5）。
   两条**只读查询**（`1101/7`、`1101/11`）标 `always_allowed`，豁免 L1 与租约闸 ——
   它们不改车上任何东西，锁在"先开控制"后面纯属自找麻烦。

### 8.1 指令报文记录（2026-10-17 加）

用户诉求：「像 lite3 控制台那样，保存发出的控制指令的报文，并给出是否成功响应的标记」。

**与审计的分工**（两个端点都要留着，回答的不是同一个问题）：

| | `/control/audit` | `/control/packets` |
|---|---|---|
| 视角 | **操作**（谁、何时、下了什么、被哪道闸拦） | **报文**（线上真实跑过哪些字节、机器人回了什么） |
| 含被闸拒的 | 含（没有报文） | 含（`frame_hex=null`，标 `rejected`） |
| 典型用途 | 追责 / "谁点的" | 协议复盘 / "车上到底出了什么" |

**留下的内容**：完整字节帧 hex（含 16 字节帧头，可原样反解）、`Type/Command`、
协议字段 `Items`（大写，线上真身）、`actor`/`confirmed`/`forced`。
⚠️ 报文里的 Items 是**协议字段**（`X/Y/Z/Roll/Pitch/Yaw`），不是前端的小写参数 ——
报文视角就必须以线上为准。

**响应六态**（前端分色直接认这些字符串）：

| 状态 | 含义 | 会不会误导 |
|---|---|---|
| `ok` | 收到响应且 `ErrorCode == 0` | 不会 |
| `error` | 收到响应但 `ErrorCode != 0`（附 `ErrorMessage`） | 不会 |
| `no_response` | 超时（默认 2s）未收到响应 | **会** —— 见下 |
| `send_failed` | 本地 socket 都没发出去（没上线） | 不会 |
| `rejected` | 被安全闸拦下，从未生成报文 | 不会 |
| `pending` | 已发出、还在等 | 不会 |

> ⚠️ **`no_response` 不代表车没执行**。basic_server 对部分指令执行了但并不回帧；
> 这一列是"不知道"，不是"失败"。界面文案已原样写明，避免把它当故障查。
> 另外：**无 `ErrorCode` 字段的响应也算 `ok`**（如休眠查询回 `{"Sleep":0,"Auto":false,"Time":10}`）——
> "有数据回来"本身就说明指令被接受。

**★踩坑记录（这一条最值得留）**：第一版做完后发现所有指令都标 `no_response`。
根因是 **basic_server 把指令应答发回「请求的源端口」**（实测：从同一 socket 发
`1101/7` 就能在同一 socket 收到响应），而 `UdpControlSink` **只发不收** ——
应答全堵在 socket 缓冲区里。修法：给出口加一个守护接收线程（范式与
`UdpHeartbeatSource._rx_loop` 一致），收到就转交 `CommandLog` 按
`(Type, Command)` 关联。指令链路与遥测链路仍是两个独立 socket，互不影响。
已加回归测试 `test_udp_sink_receives_command_response`（真实 UDP socket 对）锁住这条性质。

**匹配策略**：按 `(Type, Command)` 匹配、FIFO 取最早未匹配的那条。局限：同一
`(Type, Command)` 多条在途而只回来一条时会记在最早那条头上 —— 可接受，因为控制台
不会对同一指令并发下发（轴指令由看门狗串行化）。

**为什么 20Hz 看门狗 tick 不进记录**：看门狗走自己的发送循环，不经过
`execute()`。否则一秒 20 条，200 条环形 10 秒就滚掉，用户什么也看不到。
但**安全零位帧 / 软急停 / 停用补零**都经过 `send_safety_zero` / `emergency_stop`，
一律留证 —— 事故复盘时"停机前最后发了什么"是关键证据。

**界面**：全局底部可折叠面板（`PacketLogPanel.vue`），任何标签页发的指令都能就地看到响应，
不用切页。默认收起只占一行，展开后才按 1.5s 轮询（收起时不打后端）。点 hex 可整条复制，
「详情」展开完整 JSON（发出 + 响应）。

**配置**：`M20_CONTROL__PACKET_LOG_SIZE`（默认 200）、`M20_CONTROL__PACKET_TIMEOUT_MS`（默认 2000）。

**看门狗（只停不趴，2026-10-15 二次事故修正）**：以 20Hz 循环发送当前轴值 —— ① **松杆 / feed 停更 250ms / WS 断开 / 服务停机** → 一律 **零位一帧 + 停发**（车侧 rl_deploy 150ms 看门狗自然清零速度，**不软急停**）；此后保持"停"等待恢复，新 `feed()` 即续发；② **绝不自动软急停** —— 软急停只能由人显式触发（面板「软急停」按钮 / `POST /control/estop`）；③ 安全零位帧豁免四道闸（`send_safety_zero`——2026-10-15 发现零位兜底会被租约闸拦截，特设内部通道）。不存在"带着最后一条指令无限运动"。

> 事故复盘（2026-10-15，**两次同源事故**）：① 旧行为"feed 超时/松手 → **立即**软急停"——前端单发一次 feed → 250ms 即被软急停，且松手也软急停；车在**运动中**被打软急停 → 失稳栽倒（车侧日志实锤 `Recv [MotionState]: 2` + 姿态异常 pitch −20.3°）。② 改为"断流 10s 延迟升级"后仍误伤：一次 **10 秒链路静默**（页面/网络冻结，连租约续约都中断）触发升级，**站立中**的机器人被打软急停 → 关节卸力软塌（rl_deploy 日志 `rl_control → joint_damping`，全天无姿态异常），用户感知为"突然又倒了"。**结论：车侧 150ms 看门狗已保证"链路断了车必停"，控制台任何"自动放倒"都只会制造事故——自动软急停机制已整体切除。**

**定时移动（2026-10-16 加）**：`POST /api/v1/control/axis/timed {x..yaw, duration_s, channel}` —— **计时在后端**（浏览器定时器会被节流：切后台/省电，前端计时停不住车）；到点走与松手完全相同的路径（零位一帧 + 停发，**绝不软急停**）；`feed()` / `pause()` / `stop()` 都会中止它（人随时可以抢回控制权）；入口先走 `precheck`（只过闸不发送）——控制未开启 / 无租约 / 未站立**即时拒发并进审计**，不让用户看着倒计时空转。前端面板：方向（前后左右 / 左右转）+ 速度 + 秒数（0.5~30s）+ 通道 + 开始/中止 + 实时倒计时（轮询 `GET /control/status` 的 `watchdog.timed_*`，500ms/次、仅在执行中轮询）。

**横移步态警示（2026-10-16 真机对照实验结论）**：**横移能力由「步态」决定，与指令通道无关**——0x1001 基础（标准）步态下 Y 指令只原地调姿态、不位移（steer / real 两条通道表现一致，`|linear_y|max` 0.0543 vs 0.0503，均在空闲底噪 0.057 内）；切 0x3002 平地（敏捷）后立即可横移（`|linear_y|max` 0.1011 ≈2× 底噪 + 站高 0.574→0.46）。据此：后端 `/axis/timed` 响应在"横移 + 标准系步态"时附 `warning` 字段（**只提示、不拦截**）；前端两处**实时预判**——摇杆区（模式 = 前后+左右平移）与定时移动区（方向 = 左移/右移）在标准系步态下直接显示黄框警示，文案统一指向「平地（敏捷）0x3002」。⚠️ 切 0x3002 时站高会从 0.574 降到 ~0.46（机身降低约 11cm），属该步态正常行为。

**轴指令双通道（2026-10-16 取证 + 实测闭环）**：basic_server 内有三条话题 `/STEER`、`/HANDLE_STEER`（由 `2/21` cmdHandle_Steer 发布）与 `/REAL_STEER`（由 `2/25` cmdHandle_RealSteer 发布），两路指令**字段完全同构**（X/Y/Z/Roll/Pitch/Yaw）；`rl_deploy` 二进制里 `/STEER` 与 `/REAL_STEER` 字符串均在、其 steer 处理链产出 `current_cmd_velx / current_cmd_vely / current_cmd_velyaw`。控制台据此开放 `channel` 选项（`steer`=2/21 默认 / `real`=2/25），两条通道共用同一套四道闸与 ±0.40 钳制，零位帧跟随当前通道。**实测结论（2026-10-16，5Hz 探针 1290 样本）**：基础步态下两条通道行为完全一致——原"主通道没被车侧消费"假设**不成立**；横移不动的真因是**步态**（见上）。通道选择**保留作排查工具**，默认仍是 steer（最小惊讶）。

**前端交互契约（虚拟摇杆）**：拖动期间以 ≈16Hz（60ms 间隔）、**最多 3 发在途**（网络慢时多发抗抖动）持续 `POST /control/axis {continuous:true}` 刷新看门狗目标值——即使指针不动也必须续发（否则 250ms 停更）；摇杆含 **8% 中心死区**；松手时先等所有在途请求落地再调 `axis/stop`（零位停发），避免残余 feed 在暂停后重新激活看门狗；**页面切后台自动松手**（`visibilitychange` → 零位停止，2026-10-15 二次事故加固）；**每次按下摇杆先补一次续约**（防"从后台回来首推被租约闸拒"）。控制开启期间前端**每 2s 自动续约**（`POST /control/lease`）——缺陷修复：此前 `renewLease()` 在 UI 侧无任何调用方，开启控制 5s 后所有指令都会被租约闸拒发（`rejected` 计数的隐藏增长源）。

**仍需人工遵守**：首次控制实测在空旷场地 + 人员看护下进行；先做低危（站立/照明/休眠）后做轴指令；人机保持安全距离。

**心跳（遥测）让渡（2026-10-16 加）**：`POST /api/v1/link/heartbeat {"paused": true, "confirmed": true}` —— 主动停发心跳、放弃状态推送。**语义边界**：心跳（类型100/命令100，默认 5Hz）只决定"机器人往谁推送状态"；车侧 basic_server 有心跳超时机制（二进制内字符串 `Heartbeat timeout! Cleared %zu client(s).`），停发后它会**清除本客户端**。而**心跳与指令是两个独立 UDP socket**（`UdpHeartbeatSource._sock` vs `UdpControlSink._sock`）——停心跳**不影响**指令链路。正因如此，暂停前服务端会**先零位停发正在进行的控制**（不能蒙眼开车），且暂停期间所有驱动类指令被新闸拒绝（`TELEMETRY_PAUSED`，409），**软急停豁免**（安全手段优先）。前端据此把"主动暂停"（琥珀色横幅 + 恢复按钮）与"链路故障"（红色横幅）分色展示——两者提示语义相反，绝不能混为一类告警。

**★"系统关了车会不会趴下"—— 2026-10-16 真机实证：不会**：控制台服务 `systemctl stop` 停 50s（心跳与指令**全部中断**）后重启，机器人 `motion_state` 前后均为 **17（RL 站立）**、`height` 0.494 不变、`linear_x/y` 仅空闲底噪。三条独立证据互相印证：① 上述真机关停实验；② 控制台重启后 `sent_packets=0`（零指令）持续数分钟，车稳定保持站立；③ 车侧二进制显示真正的断链保护在 rl_deploy 的 **DDS_CMD 看门狗**（`DDS_CMD topic data update timeout %f. Disable lynx`）——效果是**停运动**（禁用 RL 策略）而非趴下。**结论：不要追求"断链自动趴下"**——2026-10-15 两次事故已证明站立中被卸力软塌 = 摔倒；"断链 → 停 + 保持站立"才是正确语义（看门狗 v3「只停不趴」）。

---

## 九、测试与验收

```bash
# 本地跑测试（212 项）
python -m pytest tests/ -q          # 在项目根执行；需 fastapi/pydantic/httpx 依赖

# 196 上跑部署验收（13 项）
python3 tools/verify_deploy.py
```

| 测试文件 | 覆盖 |
| --- | --- |
| `test_asdu_parser.py` | 帧头校验 / 编码解码往返 / topic 映射 / 字段归一化 |
| `test_state_store.py` | per-topic 新鲜度 / 停更只标脏 / 有界缓冲 / ready 判定 |
| `test_schema_contract.py` | 快照 schema 冻结 + `EXPECTED_FIELDS` 白名单守护 |
| `test_control_gateway.py` | 四道闸逐闸 / 黑名单 / 急停锁存 / 审计 / **实时通道 2/25 同构验证（编码 + 钳制 + 前置）** / `precheck` 只过闸不发送 |
| `test_axis_watchdog.py` | 20Hz tick / 停更零位停发（**永不自软急停**，10s/60s/10min 超长断言）/ 恢复续发 / 断连/松手/停机只停不趴 / resume 需重新 feed / **定时移动（到点自动停 / 中止 / 手动接管 / 通道回退）** / 状态字段守护 |
| `test_axis_timed.py` | **定时移动 API 契约**：到点自动零位停 / 通道换发 command 25 / 未开启与未站立先验后行拒发（一帧不出）/ duration 0.5~30s 校验 / 中止路径 / **横移步态警示 5 例**（基础带警示且不拦截 / 敏捷系不带 / 纯 X·Yaw 不带 / 楼梯标准带 / basic 未上报不误报） |
| `test_data_source.py` | **真 localhost UDP socket**：心跳持续发送 / 暂停期间真的零发包 / 恢复续发 / 暂停不拆 socket 与线程 / 停止后拒暂停 / 基类与 mock 源不支持暂停（API 层据此返 `NOT_SUPPORTED`） |
| `test_heartbeat_api.py` | **心跳让渡 API 契约**：未确认拒暂停且不真停 / **暂停前先零位停发正在进行的控制** / 暂停中轴指令被 `TELEMETRY_PAUSED` 拒而软急停放行 / 恢复清除 degraded / mock 源 `NOT_SUPPORTED` / 状态端点 |
| `test_pipeline.py` | mock → 解析 → 状态 → 快照 全链路 |
| `test_real_capture.py` | 226 帧真机抓包回归（fixtures） |
| `test_video_proxy.py` | ffmpeg 命令构造（posixpath / 不转码）/ 进程托管 |
| `test_video_streams.py` | 双路取流 API：前后两路 / 三档链路 / **地址要素不得含主机名**（写死会让浏览器连错机器） |
| `test_device_switch.py` | **设备供电开关 `1101/3`**：授权 magic 只在该指令上生效（其余指令保持 `EB 91 EB 90`）/ 键名白名单与值域（`pair` 缺字段必须报错，**绝不默认 0**）/ 关闭需二次确认 / 站立态禁关雷达而趴下态放行 / 相机关闭只确认不拦 / 非法参数 `BAD_PARAMS` 且**一帧不出** / L1 与租约闸同样适用 / **Lidar 上报值 `2` 不得误判为关闭** / **★关闭判定必须对比当前状态**（开一路时另一路的 0 不算关闭·真关仍要确认·无当前值回退保守·运动锁只对运行中的雷达生效） |
| `test_command_log.py` | **指令报文记录**：hex 可原样反解 / 响应三态（ok·error·no_response）/ **无 `ErrorCode` 的响应也算 ok** / 未匹配帧零副作用 / 惰性超时 / FIFO 匹配 / `send_failed` 立即判死 / 被拒留证无报文 / 环形有界 / 统计 / 网关集成（execute·急停·安全零位·停用补零·L0·无 log 静默）/ HTTP 契约 / **★出口必须能收应答（真实 UDP socket 对，锁 2026-10-17 踩的坑）** |
| `test_robot_config.py` | **机器人设置页契约**：休眠时长越界**一帧不出**（车侧静默夹取，后端必须先拒）/ 5 与 30 边界放行 / 休眠与关回零需确认而唤醒与开回零不拦 / **确认闸拦下时零报文** / `1101/2`·`1101/6`·`1101/10` 编码 / 只读查询在 L1 关闭时仍可问 / 三段结构 `known=False` 不臆断 / 查询缓存带 `age_s` / `needs_confirm` 只看方向 |
| `test_net_ap.py` | **热点受控读写契约**：**纯数字密码必须按字符串解析**（`00123456` 被 `int()` 掉会丢前导零，用户照着连就连不上）/ 连接名同理 / 其余数字字段仍是 int / 读不出原文时只标 `password_unreadable` 而不给 `password` / 没设密码时不多出 `password` 字段 / **`ap` 分组整个缺失 = 状态未知，不能说成"没开热点"** / `no_ap_connection` 是已知状态而非未知 / 上行已连接与掉线的摘要分级 |

**当前状态（2026-10-18）**：**212 项**测试全绿；196 部署验收通过；LAN 访问正常；**视频升级为前后双路 + WebRTC**（浏览器直连 MediaMTX v1.4.2 的 WHEP `:8889`，HLS `:8888` 兜底，后端 ffmpeg 退为第三层兜底）；**电量面板已修**（逐块电池 + "未安装"识别 + 低电量告警）；**运动控制已真机实测**（轴指令驱动车体移动 + 速度标定 + 虚拟摇杆）；**新增定时移动**（`/axis/timed` 后端计时到点自动停）；**"左右平移无反应"已闭环定因**：横移能力由**步态**决定、与通道无关（0x1001 基础只原地调姿态，切 0x3002 平地敏捷即生效）→ 后端 `warning` 字段 + 前端摇杆区/定时区**实时黄框警示**已随本次上线；**看门狗"只停不趴"二次事故修正完成**（两次自动软急停事故复盘 → 机制整体切除）并真机行为验证通过；**分设备供电开关已上线**（`1101/3` 抓包破解，相机页/GPS 页/运动控制页三处独立开关 + 第五道闸，真机端到端验证通过、现场已恢复原状）；**指令报文记录已上线**（留下发出的原始字节帧 + 机器人响应六态标记，全局底部可折叠面板，真机验证 `1101/5` 1.2ms / `1101/7` 2.1ms 均标 `ok`）；**GPS 模式已语义化**（`0x11111` → 「全系统（GPS·BDS·GLONASS·Galileo·QZSS）」，GPS 页可切换 + 4s 生效校验）；**机器人设置页已上线**（逆向整张 42 条指令表后新增，见 §3.5）：补光灯 `1101/2` 真机闭环（下发 → `Led.Fill` 翻转回读）、首启回零 `1101/10+11`（写无应答 → 回读校验，真机 true/false 双向验证）、休眠 `1101/6+7`（读回 `{Sleep,Auto,Time}`，越界后端先拒）、WiFi 热点读写（双接口单射频实证，`m20-ap-ctl` 受控提权 + 失败自动回滚，真机改 `YSCTEST_24G` 后已精确还原 `CA9B_NO.1273_24G`，并实证**只改 SSID 时密码文件 md5 一字不变**）；**喇叭/音响确认无硬件**（无 PCM 设备，见 §3.5，不加也不造假）；**热点当前密码可回显**（前端默认掩码 + 「显示」展开；顺带修掉一个真 bug —— 纯数字密码被 `int()` 解析会丢前导零）。

---

## 十、扩展与预留

| 方向 | 状态 | 说明 |
| --- | --- | --- |
| ROS2 数据源（`Ros2TopicSource`） | 预留 | 与 `UdpHeartbeatSource` 同接口，接入零架构改动（计划书 §18 路径 1） |
| ROS2 控制出口（`Ros2ControlSink`） | 预留 | 与 `UdpControlSink` 同接口（ADR-010） |
| 多实例部署 | 不支持 | 监控协议需要唯一心跳方，且 196 单机部署（ADR-002） |
| AI 检测叠加 | 不预留 | 由 GOS 上独立工程 `m20-ai-detect` 承担，与本控制台解耦 |

---

## 十一、注意事项

1. **Python 3.8 兼容**：196 为 Ubuntu 20.04 / Python 3.8.10，新增代码不得使用 3.9+ 语法（`dict[str, x]`、`X | None` 等）；
2. **相机随车供电**：机器人休眠时 `/dev/video*` 不存在、MediaMTX 无流——先唤醒（`1101/6 {"Sleep":false}`）再看视频；
3. **命名禁忌**：196 上游 `restart.sh` 会 `pkill -f` `push_video` / `v4l2` / `gst-launch`，本工程进程名/脚本名已避开（`m20pro-console` / `m20-video-supervise`）；
4. **196 时钟慢 ~846 天**：与 HTTPS 相关的操作（pip 默认源等）会失败；本工程**不依赖系统时钟**（新鲜度用 `time.monotonic()`）；
5. **只传 `frontend/dist`，不传 `node_modules`**：前端必须本地构建（196 上没有 Node 验证 + npm 走 HTTPS 会挂）；
6. **配置与口令不进仓库**：真实配置只走环境变量或 `*.example`；
7. **196 的 venv 只有运行依赖**（无 pytest/httpx）→ 测试在 PC 侧跑，别为了跑测试往生产 venv 里装东西；
8. **`_apply.sh` 自己解压 tarball**：曾经"传了新包却复用旧解压目录"，代码没上车而日志显示部署成功。现在日志会打**包时间 + md5**，部署后务必与 PC 侧 `md5sum` 对照；
9. **车侧对 `1101/10`（首启回零写）不回帧**：报文记录里的 `no_response` 是"不知道"，不是失败，别让用户反复重试；
10. **休眠时长越界车侧会静默夹取**（60→30、3→5，不回错误码）→ 后端先拒，别指望前端 `min/max` 属性；
11. **热点 SSID/密码是厂商明文文件**，且 SSID base 只取前 12 字符、密码前 16 字符；`nmcli con modify` 的改动重启会丢，只能走 `ap_start.sh` 重建；
12. **别为了"验证一下"去点「立即休眠」**：会切断关节与视频供电，恢复要点「唤醒整车」；其报文路径与唤醒同源，确认闸已单独覆盖。
