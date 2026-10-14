# 调试（debugging）

> 出问题时按"**先分流、再定位**"的顺序查：服务活着吗 → 数据到了吗 → 字段对吗 → 哪个环节坏。
> 相关：[deployment.md](deployment.md)（部署与 196 环境坑）· [replay.md](replay.md)（回放与测试）

---

## 1. 工具三件套

### 1.1 `tools/probe_asdu.py` —— 独立探针（仅标准库，可单文件 scp 上机）

与工程解耦的"万能听诊器"：只发心跳 + 可选查询/控制指令，**不依赖本项目 venv**（196 的 python3.8 直接跑）。

```bash
# 基本探测：向默认目标 10.21.31.103:30000 发 8 秒心跳，统计收到的帧
python3 probe_asdu.py

# 指定目标/时长/频率
python3 probe_asdu.py --target 10.21.33.103 --seconds 15

# 保存全部原始帧为 JSONL（供 analyze_capture 分析与测试 fixtures）
python3 probe_asdu.py --out /tmp/asdu.jsonl

# 依次探测候选地址（Q1 排查：101 地址段是哪一个）
python3 probe_asdu.py --scan

# 只读查询：发 1101/7 查休眠状态，并单独打印响应 Items
python3 probe_asdu.py --query 1101/7

# ⚠️ 控制指令：发 1101/6 唤醒全车（会改变机器人状态！）
python3 probe_asdu.py --send 1101/6 --items '{"Sleep":false}'
```

判读输出：
- `心跳发出 N 条，收到 M 帧` 且列出各消息类型计数 → 链路通；
- `✅ 推送回到了同一个 socket（Q3 成立）` → 心跳与接收共用 socket 的协议前提成立；
- `❌ 未收到任何推送` → 目标地址不对 / 心跳未被接受 / 机器人休眠或未上电。

### 1.2 `tools/analyze_capture.py` —— 抓包分析

```bash
# 在 PC（项目 venv）上分析 probe 抓到的 JSONL
python tools/analyze_capture.py tools/capture/asdu_loopback_20261015.jsonl
python tools/analyze_capture.py <file> --sample 2      # 每类打印 2 条样本
```

输出：按消息类型统计 + Items 结构摘要 + 与工程映射表的差异——用于**字段核对报告**（新增/改名/消失的字段）。

### 1.3 `tools/verify_deploy.py` —— 部署验收

```bash
python3 tools/verify_deploy.py --base http://127.0.0.1:8080
```

13 项逐条核对（见 deployment.md §9）。**排障时先跑它**：哪一项红就直接指向对应子系统。

---

## 2. 日志与可观测端点

```bash
# 实时日志（196）
journalctl -u m20pro-console -f
journalctl -u m20pro-console -n 100 --no-pager

# 典型日志事件（结构化 event 字段，可 grep）
journalctl -u m20pro-console | grep event=parse_error      # 解析失败（死信）
journalctl -u m20pro-console | grep event=watchdog_trip    # 看门狗兜底
journalctl -u m20pro-console | grep event=control          # 控制指令
```

| 端点 | 看什么 |
| --- | --- |
| `/health` | `connected`（3s 内有无任何帧）、`data_source`、uptime |
| `/ready` | `degraded` + `reason`；`fresh_topics` / `stale_topics`；`error_rate` |
| `/api/v1/status` | `source_stats`（发出心跳数/收到包数）、`counters`（received/parsed/errors/dropped）、`ws_clients`、`control`、`watchdog` |
| `/api/v1/raw?limit=50` | 最近原始报文 hex 预览——确认"帧真的长这样" |
| `/api/v1/fields` | 逐字段置信度表 + 16 关节名对照 |
| `/api/v1/control/audit` | 控制指令全量审计（含被拒原因） |

---

## 3. 分级排查决策树

```
页面打不开？
├── curl 127.0.0.1:8080/health（196 本地）
│    ├── 不通 → systemctl status m20pro-console → journalctl -n 50
│    │       常见：端口被占（不，启动校验会拦）/ 配置错误（fail-fast 会打印原因）/ venv 缺依赖
│    └── 通 → 浏览器/网络问题：从 PC curl http://192.168.0.196:8080/
│            不通 → 检查 196 是否在线、LAN 连通性
└── 通但页面白屏 → 前端 dist 是否在（ls frontend/dist/index.html）、浏览器控制台报错

页面能开，"链路断开"？
├── /api/v1/status 看 source_stats.received_packets 是否增长
│    ├── 不增长 → 数据没进来：
│    │   ├── 机器人上电了吗 / 休眠中？probe_asdu.py 先验证
│    │   ├── 196 上 tcpdump -i any -nn udp port 30000 -c 5 看有没有回包
│    │   └── 有回包但 received 不涨 → 目标地址/端口配置错（对照 probe 参数）
│    └── 增长但 connected=false → 不可能（同一判定）；检查 link_timeout
└── received 涨但 errors 涨得快 → 解析失败：看 raw 的 hex 与 parse_error 日志

某些面板置灰（stale）？
├── 是 nav（1Hz）或 sleep（0.2Hz）→ 阈值已是 per-topic（max(0.5, 2.5/周期)），仍 stale 说明真停更
├── 机器人趴着/休眠 → nav/motion 停更是正常
└── 单个 topic 停更但其他正常 → 该消息类型被机器人暂停（如异常列表只 2Hz+变更）

视频面板不可用？
├── 面板文字："视频功能未开启" → M20_VIDEO__ENABLED=false
├── "视频源不可用" → 依次查：
│   ├── 机器人是否休眠（相机不通电）→ probe_asdu.py --send 1101/6 --items '{"Sleep":false}'
│   ├── MediaMTX 是否在线：curl -v rtsp://127.0.0.1:8554/video1（或看 8554 端口）
│   ├── ffmpeg 是否在：which ffmpeg；journalctl | grep -i ffmpeg 看退出原因
│   └── HLS 目录：ls /home/djw/monitor/hls/（应有 live.m3u8 + seg_N.ts）

控制指令被拒？
├── CONTROL_DISABLED → 先 enable（confirmed:true）
├── LEASE_EXPIRED → 前端续约断了（WS 断）；重连即恢复
├── PRECONDITION → 轴指令需先站立（MotionState 1/17）且常规模式
├── BLACKLIST → Charge=2 永久拒绝（设计如此）
└── estop 锁定 → POST /estop/clear 解除
```

---

## 4. 常见故障表（按子系统）

### 4.1 数据链

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `received_packets` 不增长 | 心跳未发出/机器人未推 | 看 `sent_heartbeats`；probe_asdu 独立验证；确认机器人上电 |
| `errors` 持续增长 | 收到杂包或协议变更 | `/api/v1/raw` 看 hex 前缀是否 `eb91eb90`；非本协议包属正常噪声 |
| `dropped` 增长 | 原始报文缓冲满（1000 条） | 正常滚动，忽略；长时间不消费才需要关注 |
| 时间戳全部 2024 | 196 时钟慢 846 天 | **预期现象**，判定用 monotonic 不受影响；不要据时间戳判断事件先后 |
| 断断续续 stale | 196 WiFi 间歇丢包 | 设计已带 stale 兜底；持续严重则查 WiFi 信号 |

### 4.2 控制链

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 审计里大量 `rejected` | 前置条件不满足 | 看 `reason` 字段，对照决策树 |
| `watchdog_trip` 日志频繁 | 前端 feed 不足 20Hz 或松杆 | 检查前端 `sendAxis` 循环；松杆即 trip 属正常设计 |
| 指令发出但机器人不动 | 模式不对（非常规模式）/ 机器人自我保护 | 先站立 + 常规模式；真机首测按计划书 T2.7 流程 |

### 4.3 视频链

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 首帧等待 >3s | RTSP 握手 + ffmpeg 冷启动 | 常驻进程已解决；重启后首帧慢属正常 |
| 画面卡住但状态正常 | MediaMTX 上游断流 | ffmpeg 由守护线程退避重启（2s→30s）；查 MediaMTX |
| HLS 404 | 静态挂载顺序（历史 bug） | 已修：`main.py` 先挂 `/hls` 再挂 `/` |
| 切片目录磁盘涨 | `delete_segments` 未生效 | 查 ffmpeg 参数（build_cmd）；正常状况只有 ~3 个切片 |

### 4.4 部署/环境

见 [deployment.md §5](deployment.md#5-196-环境已知坑全部实测脚本已内置规避)（时钟/ensurepip/CRLF/cp 嵌套/打包静默失败）。

---

## 5. 抓包速查（196 上）

```bash
# 看监控协议回包（UDP 30000）
sudo tcpdump -i any -nn udp port 30000 -c 10

# 看是否有推到其他端口（排查多进程抢包/错端口）
sudo tcpdump -i any -nn udp and src port 30000 -c 10

# 看 RTSP 拉流（8554）
sudo tcpdump -i lo -nn tcp port 8554 -c 10
```

> 196 上 `sudo` 非交互必须：`printf "'\n" | sudo -S tcpdump …`

---

## 6. 快速自检清单（30 秒）

```bash
# 在 196 上一把梭
systemctl is-active m20pro-console && \
curl -s http://127.0.0.1:8080/health && echo && \
curl -s http://127.0.0.1:8080/ready && echo && \
journalctl -u m20pro-console -n 5 --no-pager
```

全绿仍有问题 → 跑 `tools/verify_deploy.py` 拿到逐项结果，再按第 3 节决策树分流。
