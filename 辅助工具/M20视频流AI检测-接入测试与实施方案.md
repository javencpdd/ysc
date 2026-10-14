# M20 Pro 视频流 × AI 识别服务 · 接入测试与实施方案

> 版本 v1.0 ｜ 编制：运维通（架构 / SLO / 部署 / 验收） ｜ 日期：2026-10-14
> 适用对象：M20 Pro 196 主机（`aos`，RK3588 级 8 核）+ 外部 AI 识别服务 `http://jsxy.aihyzh.com:30881`
> 依据：本工作区 `视频检测接口.md` + `m20Pro/rtsp-rtmp/note/推流方案优化评估-20261014.md` + **本次上机实测新增证据（§1）**

---

## 0. 结论先行（TL;DR）

| 问题 | 结论 |
|---|---|
| **部署在哪台主机** | **三选一，按优先级**：① **方案 F：GOS `10.21.31.104`**（厂商定位"开发+对外服务"，**最符合设计意图**）—— 内网直达 AOS 相机流 `rtsp://10.21.31.103:8554`（实测 0.46 ms，不经 WiFi）、完全不碰 AOS 运控；② **方案 S：SRS 汇聚服务器 `172.31.68.227`** —— 一套覆盖所有机器人、机器人侧零改动；③ **方案 E：AOS `192.168.0.196`** —— 兜底。**GOS/NOS 能否出公网是唯一未验证项**：AOS 上 NAT 规则 `-s 10.21.31.0/24 -o p2p0 -j MASQUERADE` + FORWARD 放行 eth2↔p2p0 **均在位**，出口路径存在，只差 DNS/实连验证。一次性验证仍用**方案 G（运维机）** |
| **怎么通过视频流执行检测** | 走「**常驻抽帧 → HTTP 上行推理**」。常驻 ffmpeg 按 1–2 fps 抽帧落盘，采样器逐帧 `POST /api/v1/tasks/{capability_id}`。❌ **不要**用"服务端拉流"（AI 服务在公网，拉不到内网流）；❌ **不要**用"每次 ffmpeg 单帧启动"（实测 1.6–2.0 s/帧，比推理本身慢 20 倍）。**换主机只改 `SRC_*` 一行配置，代码不变** |
| **结果存哪** | **跟随部署位**：方案 S → 权威数据直接落在 227 本地（服务器磁盘、稳定供电、易备份），**196 上不存任何检测结果**；方案 E → 196 只留 15 min 环形缓冲（≤200 MB）+ 异步回传集中存储。理由：机器人根分区仅 14 GB 可用（overlayroot）、eMMC 写寿命、可能断电/失联、结果需与 GPS/地图/遥测关联分析。例外是"离线巡检、回场取数"（§4.3），此时反过来全量存本地 |
| **结果图要不要存** | **默认不存**。`result_image` 是必返字段、约占单次响应 94% 体积（120 KB/帧 ≈ 432 MB/h/路），可事后用 JSONL + 原始帧离线重绘。**只在命中告警规则时保存结果图** |
| **是否影响既有推流** | 不影响。采样器实测链路与 RTMP 中继解耦，新增负载预计 <0.2 核 / <150 MB，抽帧走 mediamtx 多读者能力（`maxReaders: 0`），不抢相机设备 |
| **最大前置阻塞项** | 196 **系统时钟慢 846 天**（`date`=2024-06-20）。不修，所有文件 mtime、日志时间线、与检测事件的时间关联全部失效 → **P0，必须先做** |
| **最大安全项** | AI 服务**无任何鉴权**（OpenAPI 无 securitySchemes），画面经公网明文 HTTP 上行。测试阶段可接受，正式运行必须加网关/鉴权或改走内网自建推理 |
| **专家分工** | 计划由**运维通**制定（架构/SLO/回滚/验收）；执行由**嵌入式 Linux + 流媒体**背景的执行者上机落地，运维通做验收与变更把关（详见 §9） |

---

## 1. 实测基线（本次新增证据，2026-10-14 03:50 GMT+8）

| # | 验证项 | 命令/方式 | 实测结果 |
|---|---|---|---|
| E1 | 本机 → 196 可达 | `ping 192.168.0.196` | 通，3–4 ms |
| E2 | 196 → AI 服务可达 | `ssh 196 "curl -o /dev/null -w %{http_code} http://jsxy.aihyzh.com:30881/api/v1/health"` | **HTTP 200，52.8 ms** ✅ |
| E3 | AI 服务能力状态 | `GET /api/v1/health` | `status:ok`，**33/33 能力就绪**，11 模型已加载，**`default_device:cpu`、无 CUDA** |
| E4 | 源流在线 | `curl http://127.0.0.1:8888/video1|video2/index.m3u8` | **均为 200**（相机侧推流活着） |
| E5 | 196 工具链 | `command -v ffmpeg python3 curl jq` + `import cv2/requests` | **全部具备**（cv2 4.2.0、requests OK），无需装依赖 |
| E6 | 196 磁盘 | `df -h / /home` | overlayroot **18 GB 总 / 14 GB 可用**，占 24% |
| E7 | 抓帧方式 A：单次启动抓 1 帧 | `ffmpeg -rtsp_transport tcp -i rtsp://127.0.0.1:8554/video1 -frames:v 1` ×3 | **1.63 / 2.01 / 2.00 s** —— RTSP 握手开销主导 ❌ 不可用于逐帧 |
| E8 | 抓帧方式 B：常驻进程抽帧 | `ffmpeg -rtsp_transport tcp -i ... -vf fps=2 -frames:v 8` | 8/8 帧成功，单帧 JPEG **39 KB** ✅ 可行 |
| E9 | **端到端检测** | 抓帧 → `POST /api/v1/tasks/ai-04-yolov8-object-detection` ×6 | 全部 200；**墙钟 0.242–0.279 s**，服务端 `elapsed_ms=65.42`，上行 39–81 KB，下行 **107–144 KB** |
| E10 | 结构化结果字段 | `jq .results.items[0]` | `{"label":"chair","class_id":56,"score":0.6551,"box":[173,211,236,302],"box_norm":[0.2162,0.3517,0.295,0.5033]}` —— 可直接入 JSONL |
| E11 | 196 系统时钟 | `date` | **Thu 20 Jun 2024 01:53 CST** —— 慢 846 天 ❌（P0） |
| **E12** | **SRS 服务器 227 端口** | TCP 探测 22/1936/8080/8554 | **22 OPEN、1936 OPEN、8080 OPEN、8554 closed** —— 是一台可 SSH 的正常服务器 |
| **E13** | **227 上 SRS 实际在收哪些流** | `curl http://172.31.68.227:1985/api/v1/streams/`（只读） | **`live/lite3` 3671 kbps、`live/m20pro-b` 2021 kbps、`live/m20pro-f` 2014 kbps（2 个观看者）**，全部 `publish=true`、H264 High ✅ **227 是多机器人汇聚点** |
| **E14** | Lite3 主机可达性 | `ssh lite3-f20-1-103` / `lite3-f20-1-120` | **均 Connection timed out** —— 跨网段当前不通，排除作为部署位 |
| **E15** | 227 的未知项 | — | 无登录凭据，**ffmpeg / python3 / 出公网能力 / 磁盘容量未验证** → 列为 V0′ 待办（§6） |

**容量推算（供 §4 用）**

| 数据 | 单帧体积 | 1 fps 双路 | 1 天 |
|---|---|---|---|
| 结构化 JSONL | ≈ 600 B | ≈ 4.3 MB/h | **≈ 104 MB** |
| 原始 JPEG 帧（留 15 min 环形） | 39 KB | 281 MB/h | 环形封顶 **70 MB** |
| `result_image`（base64，默认丢弃） | 107–144 KB | 432 MB/h/路 | 不落盘 |

---

## 2. 架构设计

### 2.1 三条候选路径对比

| 路径 | 做法 | 可行性 | 优点 | 致命问题 | 结论 |
|---|---|---|---|---|---|
| **A 边侧抽帧 + 上行推理**（推荐） | 196 常驻 ffmpeg 抽帧 → `POST /tasks/{id}` | ✅ **已实测跑通** | 零转码、结构化结果完整、与既有推流解耦、196 无需 GPU | 每帧 40 KB 上行（弱网敏感）；依赖公网可达 | **主线** |
| **B 边侧回传 + 服务端推流** | 196 `POST /stream/{id}/push` → 人看 MJPEG | ✅ 可用 | 响应是原始 JPEG（比 base64 省 33%），适合做"实时可视化" | **不返回结构化结果**（元数据只在响应头），**不能当存档通道** | **辅助**（仅可视化） |
| **C 服务端拉流** | `GET /stream/{id}?source=rtsp://192.168.0.196:8554/video1` | ❌ | 196 侧零改造 | AI 服务在公网，M20 RTSP 在 192.168.0.x 私网，**反向不可达**；`source` 明确是"服务端机器"的源 | 否决（除非把 AI 服务部署到内网） |
| **D 网关侧代拉** | 运维笔记本 / 内网网关机拉 RTMP → 推 AI | ✅ 可用 | **不改机器人任何东西**，退回零成本 | 结果不含机器人本地时间/位姿；笔记本不能长期在线 | **阶段 0 一次性验证** |

> 补充探测（V0，见 §6）：若 AI 服务所在网络能访问内网 SRS `172.31.68.227:1936`，则 C 的变体（source 指向 RTMP 转发地址）成立，196 可完全免改造。**先做这条探测，成本 1 分钟。**

### 2.2 推荐架构（路径 A 主线 + B 可视化）

```
┌─────────────── 192.168.0.196 (aos) ─────────────────────────────────────┐
│                                                                          │
│  USB 相机 ×2 ──► push_video.sh (MPP 硬编 H.264, 核 4-7)                  │
│                        │ rtspclientsink loopback                          │
│                        ▼                                                  │
│              MediaMTX v1.4.2  :8554/video1 /video2   ← 多读者，maxReaders=0│
│                   │                    │                                  │
│      ┌────────────┘                    └─────────────┐                    │
│      ▼                                              ▼                    │
│  rtmp_1012 中继(核 0-3)  ←既有，不动          【新增】m20-ai-sampler        │
│      │ RTMP out                          ├─ ffmpeg 常驻 -vf fps=1(核 3)    │
│      ▼                                   ├─ 抽帧落 spool/ (strftime 命名)  │
│  SRS 172.31.68.227:1936                  ├─ POST /api/v1/tasks/{cap}      │
│                                          ├─ 结果 JSONL (事件目录)          │
│                                          └─ 环形缓冲清理(≤200MB)          │
└──────────────────────────────────────────────────────────────────────────┘
          │                                        │ HTTPS/HTTP 上行
          │ RTMP(既有)                              ▼
          ▼                            AI 识别服务 jsxy.aihyzh.com:30881
   内网监看/录证                        (33 能力，CPU 推理，无鉴权)
                                                   │ 结果 JSONL
                                                   ▼  （196 → 内网 异步回传）
                                        集中存储：内网 NAS / 对象存储 / DB
                                                   │
                                                   ▼
                                        检索看板 / 告警（邮件/企微/QQ邮箱）
```

> **采样器物理位置是可选项**（上图按方案 E 画在 196 内）：**推荐放在 SRS 服务器 227**，此时它从 `rtmp://127.0.0.1:1936/live/*` 取流，机器人侧不出现任何新组件。详见 §2.3。

**分层职责**

| 层 | 组件 | 职责 | 状态 |
|---|---|---|---|
| 采集 | `push_video.sh` + MediaMTX | 相机 → RTSP 本机自环 | 既有，不动 |
| 分发 | `rtmp_1012` 中继 → SRS | 低时延监看 | 既有，不动 |
| 采样 | **m20-ai-sampler（新增）** | 抽帧、节流、重试、环形缓冲 | 本次实施 |
| 推理 | AI 识别服务 | 一帧进一帧出 | 外部依赖 |
| 落盘 | `results/*.jsonl` + `raw/` 环形 | 短期权威 + 短期证据 | 本次实施 |
| 归档 | 内网集中存储 | 长期留存、检索、关联分析 | 本次实施 |
| 消费 | 看板 / 告警 | 事件通知 | 可选 |

### 2.3 部署位置选型（不只 196：逐主机评估）

> 采样器只有三个硬条件：**① 能看到视频流 ② 能访问 AI 服务出公网 ③ 有地方落盘**。满足即可部署，代码完全通用（只改 `SRC_*` 一行）。

| 候选主机 | ① 看得到流 | ② 出公网 | ③ 资源/存储 | 对既有业务影响 | 结论 |
|---|---|---|---|---|---|
| **`10.21.31.104` GOS 通用主机** | ✅ 内网直达 AOS `rtsp://10.21.31.103:8554/video1\|2`（实测 0.46 ms、0 丢包） | ⚠️ **大概率通**：AOS 的 `MASQUERADE -s 10.21.31.0/24 -o p2p0` + FORWARD 放行 eth2↔p2p0 **在位**（2026-10-14 23:3x 复核），只差 DNS/实连验证 | 同规格 16GB+128GB；**隔离 4 个 A76 大核**，普通任务 4 小核；带 gnome 桌面 | **零影响**（不在 AOS 上跑） | ⭐⭐ **方案 F · 首选**（最符合厂商"开发+对外服务"定位） |
| **`172.31.68.227` SRS 汇聚服务器** | ✅ **本机回环** `rtmp://127.0.0.1:1936/live/m20pro-f\|b`，实测三路流在收（E13） | 待验（V0′） | 服务器级，供电/磁盘/备份都不是问题 | **零影响** | ⭐ **方案 S · 次选**（覆盖多机器人最强，但要账号） |
| **`192.168.0.196` AOS 运控主机** | ✅ 本机 `rtsp://127.0.0.1:8554/video1\|2` | ✅ 实测 200（E2） | 14 GB 可用（overlayroot）、与算法抢核、WiFi 上行 | 需绑核隔离，有回归风险（V6 一票否决） | **方案 E · 兜底**（GOS/227 都拿不到时） |
| **`10.21.31.106` NOS 感知/导航主机** | ✅ 同内网，可达 AOS RTSP | ⚠️ 同 GOS（走 AOS NAT） | 同规格；**无核隔离，8 核随便用** | 低（NOS 负载实测很轻） | **方案 N · 备选**：适合本地推理或 GOS 不可用；勿与 NOS 自身感知任务抢核 |
| **`192.168.1.103` Lite3 感知（Jetson）** | 跨网段，**当前不可达** | 未知 | 有 GPU，但被 Lite3 感知/建图占满 | 高（拖慢 Lite3 导航） | ❌ 排除 |
| **`192.168.1.120` Lite3 运动控制** | 同上不可达 | 未知 | 运动控制实时性要求最高 | 极高 | ❌ **排除，不要碰** |
| **`192.168.0.197`** | 同网段可达 | 未知 | 用途不明 | 未知 | ❌ 不推荐 |
| **运维笔记本（Windows）** | ✅ 能 ping 196 与 227 | ✅ | 够用但不能常驻 | 零 | ✅ **方案 G：阶段 0 一次性验证 / 演示** |
| **AI 服务所在公网主机** | ❌ 拉不到任何内网流 | — | — | — | ❌ 排除（除非内网主动把帧推给它，即路径 B） |

**四个机器人内网/汇聚位的差异对照**

| 维度 | **F：GOS 104** | S：227 汇聚点 | E：AOS 196 | N：NOS 106 |
|---|---|---|---|---|
| 源地址 | `rtsp://10.21.31.103:8554/video1` | `rtmp://127.0.0.1:1936/live/m20pro-f` | `rtsp://127.0.0.1:8554/video1` | 同 GOS |
| 机器人侧改动 | **零** | **零** | 装服务、绑核、占磁盘 | **零** |
| 取流路径 | 内网有线，**0.46 ms 0 丢包** | 本机回环 | 本机回环 | 内网有线 |
| 受 196 慢性问题影响 | **不受**（绕开时钟/磁盘/WiFi/相机休眠） | **不受**（还绕开中继） | 全受（时钟 P0 必先修） | 不受 |
| 时间语义 | 事件时刻 ≈ 机器人时刻（内网，仅 mediamtx 一跳） | ≈ 机器人时刻 **+0.5~1.5 s** | 最接近真实时刻（但 196 时钟本身错） | 同 GOS |
| 覆盖范围 | 仅 M20 双路 | M20 双路 + `lite3`（E13） | 仅 M20 双路 | 仅 M20 双路 |
| 新增依赖 | mediamtx + 相机存活 | **m20video 中继必须存活**（停推则无流，只发 `source_down` 心跳，不误判"无目标"） | mediamtx + 相机存活 | 同 GOS |
| 故障域 | 采样器挂了机器人完全无感 | 同左 | 采样器挂了可能占 CPU/磁盘 | 同 F |
| 落地阻点 | **需 GOS 账号 + 验证公网出口**（PC 公钥尚未投递） | 需 227 账号 | 已有 root（口令 `'`） | 需 NOS 账号 |
| 额外红利 | 厂商设计用途就是干这个 | 覆盖 Lite3 | — | 无核隔离，可跑更重负载 |

**一句话决策**：**先在 GOS 上验一件事——`curl http://jsxy.aihyzh.com:30881/api/v1/health` 是否返回 200**。通 → **方案 F 落地**（最合规、不碰运控、取流最优）；不通 → 并行申请 **227 账号走方案 S**（覆盖多机器人最强）；两路都断 → 方案 E（AOS）兜底。**三种共用同一份代码和同一套验收（§6）。**

---

## 3. 数据流转

> 以下 §3 的时序、字段、降级语义对**方案 S / E / G 通用**，差别只有三处：源地址、落盘目录、以及"谁是权威存储"。

### 3.1 时序（单帧，1 fps 稳态）

```
t0         ffmpeg 写入 spool/20261014_035012.jpg      (39 KB)
t0+~10ms   采样器发现新文件 → 计 sha1、读本地墙钟
t0+~15ms   POST multipart file=@frame  （上行 ~40 KB）
             ──► AI 服务端推理 65 ms ──►
t0+0.28s   收到响应（下行 ~120 KB，含 base64 结果图）
t0+0.30s   写 results/YYYYMMDD.jsonl 一行；按规则决定是否存结果图
t0+0.31s   原始帧移入 raw/ 环形缓冲；超配额则删最旧
```

**端到端时延预算（1 fps，实测外推）**

| 环节 | 耗时 | 来源 |
|---|---|---|
| ffmpeg 抽帧 + 写盘 | ≤ 1/fps（管线内，无额外延迟） | E8 |
| HTTP 上行 40 KB（WiFi） | ~30–80 ms | E9 墙钟 - 服务端 elapsed 推算 |
| 服务端推理 | **65 ms**（YOLOv8n/CPU） | E9 `elapsed_ms` |
| 下行 120 KB | ~100–150 ms | E9 |
| 写 JSONL | < 5 ms | 估算 |
| **合计** | **≈ 0.3–0.5 s/帧** | 验收阈值取 **< 1.5 s**（留 3× 余量） |

### 3.2 JSONL 数据字典（权威落库格式）

```jsonc
{
  "v": 1,                        // schema 版本
  "ts_host": "2026-10-14T03:50:12.481+08:00",  // 196 本地墙钟（时钟修复后才有意义）
  "ts_recv": "2026-10-14T03:50:12.760+08:00",  // 收到响应的时间
  "host": "aos", "src": "video1", "cam": "front",
  "cap": "ai-04-yolov8-object-detection",
  "frame": "20261014_035012.jpg", "frame_sha1": "…", "frame_bytes": 39169,
  "http": 200, "elapsed_ms": 65.42, "device": "cpu", "provider": "CPUExecutionProvider",
  "params": {"obj_thresh": 0.25, "nms_thresh": 0.45},
  "items": [                     // 只存结构化项，不存图
    {"label":"chair","class_id":56,"score":0.6551,"box":[173,211,236,302]}
  ],
  "n_items": 4,
  "result_image_saved": false,   // 命中告警规则时置 true 并记录路径
  "e2e_ms": 279                  // 端到端墙钟
}
```

### 3.3 失败与降级语义

| 故障 | 采样器行为 | 数据后果 |
|---|---|---|
| AI 服务超时/5xx | 指数退避（1→2→4→…→30 s），帧保留在 `spool/` 待重试，不丢 | 时延增大，无丢数据 |
| 公网不可达 > 阈值 | 继续抽帧入环形缓冲，**停止上行**（避免刷日志），恢复后从最新帧开始（**不回填**，防突发打爆服务） | 断网窗口内只有原始帧，无结构化结果 |
| 源流 404（相机侧挂了） | ffmpeg 退出 → systemd 重启采样器；源恢复前只记录 `source_down` 心跳 | 有心跳可区分"无画面"与"无结果" |
| 磁盘超配额 | 删最旧原始帧；JSONL **永不删**（体积小，是权威数据） | 证据窗口缩短 |

---

## 4. 存储位置决策

### 4.0 先定部署位，存储结论跟着变

| 部署方案 | 机器人上存什么 | 权威数据在哪 |
|---|---|---|
| **F（GOS 104，首选）** | **什么都不存**（AOS 196 上零部署零存储） | **GOS 本地**（同规格 128GB eMMC，配 logrotate + 定期备份） |
| **S（227 汇聚点）** | **什么都不存** | **227 本地**（服务器磁盘，配 logrotate + 定期备份） |
| **E（AOS 196）** | JSONL 本地 7 天 + 原始帧 15 min 环形（≤200 MB） | 内网集中存储（异步回传） |
| **N（NOS 106）** | **什么都不存** | **NOS 本地** |
| **G（运维机）** | 不存 | 运维机本地，仅演示用，不做留存 |

### 4.1 三档数据，三种策略

| 数据类型 | 体积 | 存哪 | 保留期 | 理由 |
|---|---|---|---|---|
| **结构化结果 JSONL** | ~104 MB/天(双路 1fps) | **部署主机本地**（S:227 / E:196）；E 方案再异步回传集中存储 | 本地 7 天，集中 90 天+ | 体积小、价值最高、是分析主体；E 方案本地副本用于断网续传 |
| **原始帧 JPEG** | 281 MB/h | **部署主机本地环形缓冲**（S:227 / E:196） | **15 min / ≤200 MB**（227 上可放宽到 2 GB） | 只是重绘与复核的证据，不需要长期留存 |
| **结果图 base64** | 432 MB/h/路 | **不落盘**（仅告警帧落） | 告警帧 30 天 | 可由 JSONL + 原始帧离线重绘，重复存储无意义 |
| 视频录证 | 大 | 复用既有 RTMP → SRS 侧录制 | 按既有策略 | 不要为检测再造一条录制链 |

### 4.2 为什么权威数据**不**放在 196

> 采用**方案 S 时本条自动成立**——检测结果根本不经过 196。下面的论证用于方案 E，以及"是否要把数据留在机器人上"这个通用判断。

| 维度 | 放 196 | 放内网集中存储 |
|---|---|---|
| 容量 | 根分区 **14 GB 可用**（overlayroot），检测数据 1 天吃掉 ~100 MB + 环形 200 MB，长期会挤压算法与日志 | 可扩展 |
| 可靠性 | 机器人断电/掉电/eMMC 写寿命/整机送修 → **数据随机器风险** | 与机器人解耦 |
| 可用性 | 数据在机器人上，要分析得先连机器（WiFi 间歇丢包，scp 需重试） | 随时可查 |
| 关联分析 | 检测结果需与 GPS / 地图 / 里程 / 遥测拼在一起看 | 集中侧拼表最自然 |
| 合规 | 画面数据留在移动设备上，丢失难以追溯 | 集中审计 |
| **什么时候该放 196** | 上行不稳定 / 离线巡检 / 只做短时试验 | — |

**结论：默认「本地短缓冲 + 集中长留存」。** 只有当"上行带宽不可靠或任务本身是离线巡检"时，才切到"本地全量 + 回场 rsync"。

### 4.3 决策矩阵（按任务类型选）

| 任务形态 | 上行条件 | 推荐存储 | 采样率 |
|---|---|---|---|
| 现场联调 / 算法选型 | 稳定 WiFi | 集中存储为主 | 1–2 fps，短时 |
| 园区巡检（在线） | 稳定 | 本地 15 min 环形 + 集中 | 0.5–1 fps |
| 长时无人巡检（弱网） | 不稳定 | **本地全量 JSONL（可跑 100+ 天）**，帧只留告警帧 | 0.2–0.5 fps |
| 离线取数（无上行） | 无 | 本地全量 + 回场 rsync | 事件触发 |

---

## 5. 部署配置

### 5.0 按部署位选一套配置（三选一，代码不变）

| 配置项 | **S：227 服务器（推荐）** | **E：196 机器人** | **G：运维笔记本** |
|---|---|---|---|
| 配置项 | **F：GOS 104（首选）** | **S：227 服务器** | **E：196 机器人** | **G：运维笔记本** |
|---|---|---|---|---|
| `BASE_DIR` | `/opt/ai-detect` | `/opt/ai-detect` | `/opt/ai-detect` | `./ai-detect`（当前目录） |
| `SRC_F` | `rtsp://10.21.31.103:8554/video1` | `rtmp://127.0.0.1:1936/live/m20pro-f` | `rtsp://127.0.0.1:8554/video1` | `rtmp://172.31.68.227:1936/live/m20pro-f` |
| `SRC_B` | `rtsp://10.21.31.103:8554/video2` | `rtmp://127.0.0.1:1936/live/m20pro-b` | `rtsp://127.0.0.1:8554/video2` | `rtmp://172.31.68.227:1936/live/m20pro-b` |
| `CAM_NAME_F/B` | `front` / `back` | `m20pro-f` / `m20pro-b` | `front` / `back` | `m20pro-f` / `m20pro-b` |
| `FFMPEG_EXTRA` | 留空（内网有线稳定） | `-fflags nobuffer -rw_timeout 10000000` | 留空 | `-fflags nobuffer -rw_timeout 10000000` |
| `RING_MAX_MB` | `2000` | `2000` | `200` | `200` |
| 绑核 | 避开隔离的 4 个大核：`taskset -c 0-3` | 不需要 | `taskset -c 3` + `CPUAffinity=3` | 不需要 |
| 开机自启 | `enable`（常驻合理） | `enable` | **先不 enable**，验收后再定 | 手动跑 |
| 前置依赖 | GOS 账号（公钥投递）+ ffmpeg + python3 + **公网出口验证** | 227 账号 + ffmpeg + python3 | 已具备（E5） | 本机装 ffmpeg |
| 额外可覆盖 | — | 把 `SRC_B` 换成 `.../live/lite3` 即可**顺带覆盖 Lite3**（E13） | — | — |

> 四套共用同一个 `m20_ai_sampler.py`（`辅助工具/m20-ai-sampler/`），差异**全部在 env 文件里**。

### 5.0.1 前置：打通 GOS/NOS 登录（一次性）

**网络已通（2026-10-14 23:5x 实测）**：PC **可直达** `10.21.31.104` / `10.21.31.106`（ICMP 3–7 ms、TTL 63 = 经 AOS 路由；**TCP 22 均 OPEN**）。`~/.ssh/config` 别名 `m20pro-GOS.104` / `m20pro-NOS.106` 已改为**默认直连**（原本缺 `ProxyJump` 又走不通直连，两头落空；备份 `~/.ssh/config.bak-20261014`）。换网络后若直连失效，用 `ssh -o ProxyJump=m20pro-f20-0-196 m20pro-GOS.104` 兜底。

**还差一步（需要你在有口令的终端执行一次）**：PC 公钥目前只写进了 **AOS** 的 `authorized_keys`，GOS/NOS 还没有，所以免密登录仍被拒（`Permission denied (publickey,password)`）。执行下面两行（各提示输一次口令）：

```bash
cat ~/.ssh/id_rsa.pub | ssh m20pro-GOS.104 \
  "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
cat ~/.ssh/id_rsa.pub | ssh m20pro-NOS.106 \
  "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

投递完成后即可免密登录，V0″ 的四项验证（ffmpeg/python3、出公网实连、时钟、内网拉流）我可以直接跑完，然后就能定方案 F 是否落地。

### 5.1 前置修复（仅方案 E 需要）

> ⚠️ **仅方案 E（196）需要**；方案 F/S/N/G 跳过。但**部署位自身时钟仍必须核对**（V7）——尤其 GOS 若也慢，JSONL 时间线照样废。

```bash
# 在 196 上（sudo 口令为半角单引号）
printf "'\n" | sudo -S chronyc makestep          # 立即步进校时
printf "'\n" | sudo -S sed -i 's/^makestep .*/makestep 1 -1/' /etc/chrony/chrony.conf
printf "'\n" | sudo -S systemctl restart chrony
date    # 必须回到 2026-10-14，再继续后续步骤
```

### 5.2 目录与配额

```bash
sudo mkdir -p /opt/ai-detect/{spool,raw,results,alerts,log}
sudo chown -R user:user /opt/ai-detect
# 配额：raw 环形 ≤200 MB（由采样器自管，不用 quota 工具，避免 overlayroot 兼容问题）
```

### 5.3 采样器配置（`/opt/ai-detect/sampler.env`）

```ini
AI_BASE=http://jsxy.aihyzh.com:30881
CAP_ID=ai-04-yolov8-object-detection          # 第二阶段可加 ai-14 火情 / ai-12 安全帽 / ai-16 抄表

# —— 方案 S（部署在 227）——
SRC_F=rtmp://127.0.0.1:1936/live/m20pro-f
SRC_B=rtmp://127.0.0.1:1936/live/m20pro-b     # 想覆盖 Lite3 就填 .../live/lite3
CAM_NAME_F=m20pro-f
CAM_NAME_B=m20pro-b
FFMPEG_EXTRA=-fflags nobuffer -rw_timeout 10000000
RING_MAX_MB=2000

# —— 方案 E（部署在 196）—— 放开下面几行、注释掉上面 SRC_*/FFMPEG_EXTRA 两行
# SRC_F=rtsp://127.0.0.1:8554/video1
# SRC_B=rtsp://127.0.0.1:8554/video2
# RING_MAX_MB=200

ENABLE_F=1
ENABLE_B=1
FPS=1                                          # 起步 1 fps；无 CUDA，别贪
JPEG_Q=3                                       # ffmpeg -q:v，3≈39KB/帧
TIMEOUT=10                                     # 单次 HTTP 超时
RETRY_MAX=30                                   # 退避上限(秒)
RING_MAX_MB=200                                # 原始帧环形上限
ALERT_LABELS=person,fire,smoke                 # 命中即存结果图并告警
ALERT_SCORE=0.60
SAVE_RESULT_IMAGE=false                        # 常态关，命中告警才存
CPU_AFFINITY=3                                 # 避开相机 4-7、中继 0-3 中已占用的核
```

> 命名禁忌（既有坑）：脚本/路径/命令行**不得包含** `push_video`、`v4l2`、`gst-launch` 字样——上游 `restart.sh` 会无差别 `pkill -f`，会误杀。本项目统一用 `m20-ai-sampler`。

### 5.4 采样器核心逻辑（`/opt/ai-detect/m20_ai_sampler.py`，随本文档交付）

```
主循环：
  1) spawn ffmpeg：ffmpeg -rtsp_transport tcp -i $SRC -vf fps=$FPS -q:v $JPEG_Q \
        -strftime 1 -f image2 /opt/ai-detect/spool/%Y%m%d_%H%M%S.jpg
     （常驻，避免 E7 的 1.6-2.0s/帧 握手开销；崩溃由 systemd 重启）
  2) 每 0.5 s 扫描 spool/，按名字升序取新文件
  3) requests.post($AI_BASE/api/v1/tasks/$CAP_ID, files={'file': …}, timeout=$TIMEOUT)
  4) 成功 → 写 results/YYYYMMDD.jsonl（字段见 §3.2）→ 帧移入 raw/
     失败 → 保留在 spool/，指数退避重试
  5) raw/ 超 RING_MAX_MB → 删最旧
  6) 命中 ALERT_LABELS 且 score≥ALERT_SCORE → 存结果图到 alerts/ 并写告警行
```

### 5.5 systemd 单元（`/etc/systemd/system/m20-ai-sampler.service`）

```ini
[Unit]
Description=M20 AI detection sampler (RTSP frame -> AI service)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=user
EnvironmentFile=/opt/ai-detect/sampler.env
ExecStart=/usr/bin/taskset -c 3 /usr/bin/python3 /opt/ai-detect/m20_ai_sampler.py
Restart=always
RestartSec=5
CPUAffinity=3
MemoryMax=300M
StandardOutput=append:/opt/ai-detect/log/sampler.log
StandardError=append:/opt/ai-detect/log/sampler.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now m20-ai-sampler
journalctl -u m20-ai-sampler -f
```

> 注：任务默认**不开机自启**（与既有 `m20video` 策略一致，避免机器人重启后自动往公网发画面）；验收通过后由运维决定是否 `enable`。

### 5.6 安全与合规（测试阶段也必须遵守）

| 项 | 措施 |
|---|---|
| 无鉴权公网服务 | 仅用于非敏感画面测试；正式运行必须前置网关/鉴权，或把推理服务部署到内网 |
| 明文 HTTP | 画面内容需脱敏评估；含人脸/车牌的画面默认不上传（或改用 `opencv-08`/`opencv-09` 本地离线能力） |
| 出站白名单 | 196 只放行 `jsxy.aihyzh.com:30881` 出站；AI 服务**不需要**反向访问 196 |
| 数据分类 | JSONL 不含像素，可长期留；`alerts/` 含图像，按敏感数据管理 |
| 可撤回 | `systemctl stop m20-ai-sampler` 即完全停止上行；`rm -rf /opt/ai-detect` 完全卸载，**不触碰既有推流** |

---

## 6. 验证步骤（V0–V8，每步有命令与验收阈值）

| # | 验证项 | 操作 | 验收阈值 | 不通过怎么办 |
|---|---|---|---|---|
| **V0** | AI 服务能否反向拉到内网 SRS（1 分钟探测，决定能否走路径 C） | `curl -m 20 "http://jsxy.aihyzh.com:30881/api/v1/stream/ai-04-yolov8-object-detection/snapshot?source=rtmp://172.31.68.227:1936/live/m20pro-f"` | 200 且有画面 → 路径 C 变体成立，196 免改造；503/超时 → 走路径 A | 直接走 A |
| **V0′** | **227 是否具备部署条件（方案 S 前置）** | `ssh <227账号> "command -v ffmpeg python3; curl -s -o /dev/null -w %{http_code} http://jsxy.aihyzh.com:30881/api/v1/health; df -h /"` | ffmpeg+python3 在、AI 服务 **200**、可用磁盘 **≥20 GB** | 账号/依赖批不下来 → **退回方案 E**；出公网不通 → 结果先落 227，由别处代发 |
| **V0″** | **GOS 是否具备部署条件（方案 F 前置，四项全过才落地）** | ① 投递 PC 公钥后 `ssh 10.21.31.104` 能登；② `command -v ffmpeg python3` + `python3 -c 'import requests'`；③ `curl -s -o /dev/null -w %{http_code} http://jsxy.aihyzh.com:30881/api/v1/health` → **200**；④ `date` 与标准时间偏差 **<1 s** | ①②③④ 全过 → **方案 F 落地**；③ 不过 → 走 S/E；③ 是 DNS 解析失败但 TCP 通 → 给 GOS 配 `nameserver 223.5.5.5`；② 缺 ffmpeg → `apt install ffmpeg` | 换 227（S）或 196（E） |
| **V1** | 链路连通 | 部署主机上执行 E2/E9（F/N/S 在对应主机，E 在 196） | `health` 200、`tasks` 200、`n_items≥0` | 查 DNS/出站防火墙 |
| **V2** | 抽帧稳定性 | 常驻 ffmpeg 跑 **10 min**，统计 `spool` 产生帧数 | 帧数 / 期望(600) ∈ **[0.95, 1.05]**，无断流 | 查 mediamtx 读者数、源流 HLS 200 |
| **V3** | 检测成功率 | 连续 100 次调用统计 | HTTP 200 率 **≥ 99%**；5xx=0 | 加大 `TIMEOUT`、降 `FPS` |
| **V4** | 端到端时延 | 采样器日志 `e2e_ms` P50/P95 | **P50 < 0.6 s，P95 < 1.5 s** | 降 JPEG 质量/分辨率，或改 B 路径只做可视化 |
| **V5** | 断网降级 | `iptables` 临时封 30881 出站 3 min，再放开 | 采样器**不崩**、不刷屏；恢复后 60 s 内自动续传；JSONL 无损坏行 | 修退避逻辑 |
| **V6** | **不影响既有推流**（关键回归） | 采样器运行前后各测一次：两路 RTMP 出流帧率、`m20video status`、CPU/内存 | 出流仍 **30.0 fps**；采样器 **<0.3 核 / <150 MB**；mediamtx 未重启。**方案 S 下本项自动降级为观察项**（不在机器人上跑，无干扰路径） | 立即停采样器，重调 `CPU_AFFINITY`/`FPS` |
| **V7** | 时间一致性 | `date` 与标准时间比对；抽查 10 条 JSONL `ts_host` 与文件 mtime | 偏差 **< 1 s**，且与 NTP 一致 | 回 §5.1 修 chrony |
| **V8** | 存储配额 | 跑满 30 min 后 `du -sh /opt/ai-detect/raw` | **≤ 200 MB**；`results/` 增长 ≈ 预期（±20%） | 调 `RING_MAX_MB` / `FPS` |

**验收签字项**：
- **方案 E**：V6（不影响既有推流）与 V7（时间一致）**一票否决**——任一不过，不得上线。
- **方案 S**：V7 一票否决；V6 降为观察项（采样器不在机器人上，无干扰路径）；**新增 V0′ 为前置门禁**。

---

## 7. 风险与回滚

| ID | 风险 | 等级 | 缓解 | 回滚 |
|---|---|---|---|---|
| AR1 | 采样器拖垮推流（争 CPU/内存/USB） | 高 | `taskset -c 3` + `MemoryMax=300M` + V6 回归 | `systemctl stop m20-ai-sampler` |
| AR2 | 公网不可达导致帧堆积撑爆磁盘 | 中 | `spool/` 也纳入环形配额；断网停抽 | 同上 + `rm -rf spool raw` |
| AR3 | AI 服务无鉴权，画面外泄 | 高 | 敏感场景禁用 / 加网关 | 停服务即切断上行 |
| AR4 | 196 时钟错 846 天 → 时间线全废 | **P0** | §5.1 chrony 修复 | —（不涉及推流，无回滚面） |
| AR5 | 上游 `pkill` 误杀 | 中 | 命名规避（`m20-ai-sampler`，不含敏感字样） | — |
| AR6 | 结果图体积失控 | 中 | 默认丢弃，仅告警帧存 | — |
| AR7 | 相机侧 OTA 回退 H.265 → 源流异常（既有 R5） | 中 | 采样器对"抽不出帧"发心跳告警，与 `m20video doctor` 联动 | — |
| **AR8** | **方案 S 依赖 `m20video` 中继存活**：中继一停，227 就无流，采样器只能发 `source_down` 心跳，**不会误判"无目标"但会产生数据空洞** | 中 | 心跳接入告警；空洞区间在 JSONL 里显式标记，分析时剔除 | 切方案 E 或先修中继 |
| **AR9** | 227 无账号/无公网出口导致方案 S 落空 | 中 | G0 阶段就把门禁走完，批不下来立即切 E | 改用方案 E |

---

## 8. 实施排期

| 阶段 | 内容 | 产出 | 依赖 | 角色 |
|---|---|---|---|---|
| **G0** | **投递 PC 公钥到 GOS/NOS + V0″ 前置确认**（决定走 F / S / E） | 部署位决策 | 用户提供 GOS 登录方式 | 执行者 |
| G0′ | 并行：申请 227 账号 + V0′ 确认（方案 S 备选） | 备选路径就绪 | 227 管理员 | 运维通发起 |
| G1 | 用运维机跑**方案 G** 做一次性验证（不改任何主机） | 先看效果、定能力清单 | 无 | 执行者 |
| P0 | chrony 校时 + 目录/权限（**仅方案 E**） | `date` 正确 | 上机窗口 | 执行者 |
| 阶段 0 | V0 + V1 探测 | 路径决策（A or C） | 无 | 执行者 |
| 阶段 1 | 采样器上线（单路、1 fps、15 min） | V2/V3/V4 通过 | P0 | 执行者 |
| 阶段 2 | V6 回归 + V7 + V8 | 回归报告 | 阶段 1 | 执行者 + 运维通验收 |
| 阶段 3 | 双路 + 告警规则 + 集中存储回传 | V5 通过、看可用 | 阶段 2 | 执行者 |
| 阶段 4 | 决定是否 `enable` 开机自启、纳入监控告警 | 运维手册 | 阶段 3 | 运维通 |

---

## 9. 专家 / 专家团 / 连接器 分工建议

### 9.1 谁制定计划、谁执行

| 角色 | 推荐 | 理由 | 具体职责 |
|---|---|---|---|
| **制定计划** | **运维通（infrastructure-operations-expert，本专家）** | 这件事的本质是"给正在运行的机器人加一条旁路数据链路"，核心风险是**影响既有推流**、磁盘/CPU 配额、时间与日志一致性、可回滚——全是可靠性与变更管理问题 | 架构选型、SLO 与验收阈值（V0–V8）、部署配置与 systemd 托管、风险登记与回滚、上线把关 |
| **执行计划** | 需要"**Linux 系统 + 流媒体**"背景的执行者落地（方案 S 是服务器运维活，方案 E 是嵌入式上机活） | 落地内容：ffmpeg/RTMP-RTSP 拉流管道、systemd 托管与绑核、环形缓冲与配额、与既有 `m20video`/`push_video.sh` 的隔离、chrony 修复（仅 E）——是实施活，不是架构活 | 按 §5 逐条实施、跑 §6 验证、回填实测数据 |
| **第三方评审（可选）** | 计算机视觉 / MLOps 角色 | 能力选型（33 项选哪几项）、阈值调优（obj_thresh / nms_thresh）、结果可用性评估 | 阶段 3 的能力与阈值调优 |

> 说明：当前会话可见的专家只有「运维通」一个，其余需你在左侧「专家」入口选择。**建议的组队方式**：运维通做**编排 + 验收**，嵌入式/流媒体方向专家做**执行**；若采用专家团模式，让运维通担任团长（握有验收与回滚权），执行专家只在其批准的变更范围内操作。

### 9.2 连接器（Connector）推荐

| 用途 | 推荐连接器 | 状态 | 怎么用 |
|---|---|---|---|
| **长期存储 / 检索** | **腾讯云 CloudBase** | 未连接 | 云数据库 + 云存储承接 §4 的"集中存储"：JSONL 入库、告警帧存对象存储、云函数暴露查询 API，省去自建 NAS |
| **告警通知** | **Agent Mail（智能体邮箱）** | **已连接** | 采样器命中 `ALERT_LABELS` 时发邮件，零额外依赖，阶段 3 直接可用 |
| **告警通知（备选）** | QQ 邮箱 | 未连接 | 若 Agent Mail 通道受限时的备用通知通道 |
| **团队协同告警** | 企业微信 | **本会话已关闭** | 需要群机器人告警时，请在聊天窗口左下角「+」菜单中开启企业微信连接器后再用 |
| **知识沉淀** | ima / Notion | 未连接 | 把验收报告、排障记录沉淀成可检索的知识库 |

---

## 10. 附：一句话运维手册

```bash
# 上线
sudo systemctl start m20-ai-sampler
# 看结果（实时）
tail -f /opt/ai-detect/results/$(date +%Y%m%d).jsonl | jq .
# 看告警帧
ls -lt /opt/ai-detect/alerts | head
# 出问题先停（不影响既有推流）
sudo systemctl stop m20-ai-sampler
# 彻底卸载
sudo systemctl disable --now m20-ai-sampler && sudo rm -rf /opt/ai-detect
```

---

## 11. 证据清单

| 结论 | 来源 | 时间 |
|---|---|---|
| E1–E11 全部实测数据 | 本机 `ping` + `ssh m20pro-f20-0-196` 上机执行 | 2026-10-14 03:50–03:58 GMT+8 |
| **E12–E14 部署位实测**（227 端口、SRS 三路流、103/120 不可达） | TCP 端口探测 + `curl http://172.31.68.227:1985/api/v1/streams/`（只读）+ `ssh` 103/120 | 2026-10-14 03:52–03:56 |
| **E16** GOS/NOS 登录打通情况 | PC `ping` + TCP 22 探测 + `ssh` 实测 | ICMP 3–7 ms（TTL 63，经 AOS 路由）、**TCP 22 均 OPEN、可直连**；认证仍 `Permission denied (publickey,password)` —— PC 公钥仅在 AOS，投递待用户执行。别名已改默认直连（备份 `~/.ssh/config.bak-20261014`） |
| **E17** GOS/NOS 公网出口路径 | AOS 上 `iptables -t nat -S POSTROUTING` / `-S FORWARD` | `-A POSTROUTING -s 10.21.31.0/24 -o p2p0 -j MASQUERADE` + `-A FORWARD -i eth2 -o p2p0 -m state --state RELATED,ESTABLISHED -j ACCEPT` + `-A FORWARD -i p2p0 -o eth2 -j ACCEPT` **均在位** → 出口路径存在，只差 DNS/实连验证 |
| **E18** AOS 内网口可达性 | `ssh 10.21.31.103`（ProxyJump 196，公钥） | **通**；AOS 内网自报 `date` 仍 2024-06-20、AI 服务 200/71 ms、load 0.73、Mem 15G/11G 可用 |
| 接口契约、`result_image` 为必返字段、`/push` 不返结构化结果 | `/openapi.json`（OpenAPI 3.1）+ `/api/v1/capabilities` | 2026-10-14 03:52 |
| 33/33 能力就绪、无 CUDA、无鉴权 | `/api/v1/health` | 2026-10-14 03:50 |
| 时钟慢 846 天、推流侧风险 R1–R25 | `推流方案优化评估-20261014.md` | 2026-10-14 02:20 |
| 源流地址、绑核、目标 SRS | `project/rtmp_1012/config.env` | 既有 |

**未验证/待办**：
1. **V0″（方案 F 门禁）**：GOS 的账号/公钥投递、ffmpeg+python3、**出公网实连**、时钟偏差 —— 只差公钥投递，其余我能自己跑；
2. **V0′（方案 S 门禁）**：227 的账号、ffmpeg/python3、出公网能力、磁盘容量（无登录凭据）；
3. V0（AI 服务能否反向拉到内网 SRS）；
4. 33 项能力在 M20 真实画面上的可用性（本文档只实测了 `ai-04`）；
5. 227 上拉本机 RTMP 的实际抽帧成功率与首帧延迟；
6. 长时（>1 h）运行的内存稳定性。
