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
| **三标签页布局（2026-10-16 加）** | 传感器监控 / 相机画面 / 运动控制（写方向，放最后 + 警示色）；**一律 `v-show` 不卸载**（VideoPanel 卸载会拆取流、倒计时会断更）；**每次加载回到只读标签、不记忆上次标签**（防止重新开页直接落在写方向页误触）；**切走即松手**（摇杆有 `setPointerCapture`，多指触屏下会在后台继续驱动）；定时移动在后端继续跑，顶部黄条 + 标签角标跨标签可见 |
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
│   │   └── axis_watchdog.py   #   20Hz 轴指令循环 + 只停不趴（停更→零位停发等待恢复；绝不自动软急停）
│   └── video/
│       └── video_proxy.py     # ffmpeg 子进程托管：RTSP → HLS（**第三层兜底**，主链路已改为直连）
├── frontend/                  # Vue3 + Vite（echarts / hls.js）
│   └── src/
│       ├── App.vue            # 主布局 + 停更横幅（降级显式暴露）+ 三标签页（监控/相机/运动控制）
│       ├── api/index.js       # WS 客户端（自动重连）+ REST 助手
│       ├── composables/useRobotState.js
│       ├── webrtc/whep.js       # WHEP(WebRTC) 拉流客户端：连接 / 自动重连 / 释放会话
│       └── components/
│           ├── RobotStatus.vue  # 基础 / 设备（**逐块电池**+低电量告警）/ 异常 三面板
│           ├── JointPanel.vue   # 16 关节（轮足 4 腿 × HipX/HipY/Knee/Wheel）
│           ├── MotionPanel.vue  # 运动控制：**虚拟摇杆（模拟遥感）**/速度上限输入/站立(起立)/趴下/软急停/步态
│           └── VideoPanel.vue   # 前后双路：WebRTC(WHEP) 主 + HLS 兜底 + 布局切换
├── deploy/
│   ├── pack.sh                # PC 侧：打精简部署包（自动剔除 node_modules / venv）
│   ├── install.sh             # 196 侧：一键安装（venv + http 镜像装依赖 + systemd + m20monitor 命令）
│   ├── deploy_196.sh          # PC 侧：日常迭代增量同步（rsync backend + dist → restart）
│   ├── deploy_196_tar.sh      # PC 侧：无 rsync 降级版（tar over scp，Windows 用这个）
│   ├── m20monitor             # 服务管理命令（up/down/reset/status/log/enable/disable）
│   ├── install_m20monitor.sh  # 安装 m20monitor + sudoers 免密白名单（幂等；install.sh 第 7 步调用）
│   └── m20pro-console.service # systemd 单元（含全部环境变量）
├── tools/
│   ├── probe_asdu.py          # 独立探针（仅标准库）：上机只读探测 + 抓包到 JSONL
│   ├── analyze_capture.py     # 抓包分析：按消息类型统计 + 与映射表比对
│   ├── verify_deploy.py       # 部署验收 13 项（在 196 本地或 LAN 跑）
│   └── capture/               # 真机抓包 fixtures（226 帧，测试用）
├── tests/                     # pytest 109 项（解析 / 状态 / 契约 / 控制 / 看门狗 / 视频 / 回归）
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
| 照明 | `1101 / 2` | 前/后灯开关 |
| 休眠 | `1101 / 6` | `Sleep=false` 即唤醒（**相机随车通电**） |
| 充电 | `2 / 24` | ⚠️ `Charge=2`（清除充电状态）为 L2 黑名单，任何配置下拒绝 |

> 协议事实三处修正（v1.2 起）：M20 Pro 为**轮足 16 关节**（非 lite3 的 12 关节）；步态字段名是 **`GaitParam`**；`MotionParam` 值域只有 0/1/2/3/4/17。

---

## 四、快速开始

> 完整步骤（含验证与排错）见 [QUICKSTART.md](QUICKSTART.md)。

```bash
# ① PC：构建前端（196 的 Node 未验证 + 时钟问题，前端必须本地构建）
cd frontend && npm run build && cd ..

# ② PC：打精简包并上传
bash deploy/pack.sh
scp m20pro-console-deploy.tar.gz m20pro-f20-0-196:/tmp/

# ③ 196：解压安装（自动建 venv、http 镜像装依赖、注册 systemd 并启动）
ssh m20pro-f20-0-196
cd /tmp && tar xzf m20pro-console-deploy.tar.gz
sudo bash m20pro_console/deploy/install.sh /home/djw/monitor
```

验证：`python3 /home/djw/monitor/tools/verify_deploy.py`（13 项全绿即通过），浏览器打开 `http://192.168.0.196:8080/`。

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
- **196 现状（2026-10-16 起）**：控制台服务**已关闭开机自启**（`disabled`，按用户要求"我自己会启动"）。机器人/196 重启后需手动拉起：在 196 上 `m20monitor up`，或从 PC `ssh m20pro-f20-0-196 "m20monitor up"`。注意 `disable` 只影响"下次开机"，**不影响当前运行**。需要恢复自启时执行 `m20monitor enable`。

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

四道闸（`ControlGateway.execute` 顺序执行）：

1. **黑名单**：`Charge=2`（清除充电状态，官方标注危险）任何配置下拒绝——**无"除非"**；
2. **分层开关**：L0 只监默认；开启 L1 需显式配置 + 前端二次确认；**软急停/心跳永不拦**（安全手段优先于开关）；
3. **前置校验 + 值域钳制**：轴指令要求 `MotionState∈{1 站立, 17 RL}` 且常规模式；X/Y/Z/Roll/Pitch/Yaw 服务端二次截断到 **±0.40 安全上限**（2026-10-15 实测：0.25≈0.32m/s 舒适 / 0.40≈0.54m/s 上限 / ≥0.70 危险；浏览器不是可信边界）；
4. **全量审计**：每条指令（含被拒）落审计环 500 条，`GET /api/v1/control/audit` 可查。

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
# 本地跑测试（109 项）
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

**当前状态（2026-10-16）**：**109 项**测试全绿；196 部署验收通过；LAN 访问正常；**视频升级为前后双路 + WebRTC**（浏览器直连 MediaMTX v1.4.2 的 WHEP `:8889`，HLS `:8888` 兜底，后端 ffmpeg 退为第三层兜底）；**电量面板已修**（逐块电池 + "未安装"识别 + 低电量告警）；**运动控制已真机实测**（轴指令驱动车体移动 + 速度标定 + 虚拟摇杆）；**新增定时移动**（`/axis/timed` 后端计时到点自动停）；**"左右平移无反应"已闭环定因**：横移能力由**步态**决定、与通道无关（0x1001 基础只原地调姿态，切 0x3002 平地敏捷即生效）→ 后端 `warning` 字段 + 前端摇杆区/定时区**实时黄框警示**已随本次上线；**看门狗"只停不趴"二次事故修正完成**（两次自动软急停事故复盘 → 机制整体切除）并真机行为验证通过。

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
6. **配置与口令不进仓库**：真实配置只走环境变量或 `*.example`。
