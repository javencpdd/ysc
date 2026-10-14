# 架构（architecture）

> 本文是 M20 Pro Web 控制台的开发者架构文档。**完整设计论证在 [note/ 计划书](../note/M20%20Pro%20Web%20控制台%20—%20计划书v1.md) §3–§9**，本文聚焦"代码怎么组织、为什么这么切、改代码要动哪里"。
> 相关文档：[deployment.md](deployment.md)（部署）· [debugging.md](debugging.md)（调试）· [replay.md](replay.md)（回放与测试）

---

## 1. 架构选型一句话

**模块化单体：单进程 FastAPI 驻 AOS 196**，UDP 心跳 + ASDU 解析为主通道；ROS2 为预留增强通道。
选型对比（方案 A 单体 / B ROS2 中心化 / C 微服务）见计划书 §4——结论是 A；B 留接口；C 明确拒绝（单人维护、运维成本不值）。

**部署形态与数据来源正交**：单体是部署形态（一个进程、一个 systemd 单元、一台主机），ROS2 是数据来源与总线语义。二者被三层抽象隔开：

1. `DataSource`（数据入口）——`UdpHeartbeatSource` 与未来的 `Ros2TopicSource` 同接口 `start() / stop() / on_frame(cb)`；
2. `ControlSink`（控制出口，ADR-010）——`UdpControlSink` 与未来的 `Ros2ControlSink` 同接口 `send(cmd) / close()`；
3. WS 快照 schema 契约（`/api/v1/schema`）——前端只依赖 schema，不依赖数据来源。

> 一句话：**换数据来源不动上层，换后端不动前端。**

---

## 2. 运行时视图（单进程内的模块边界）

```
┌──────────────────────── m20pro-console（FastAPI 单进程） ────────────────────────┐
│                                                                                 │
│  [数据源线程]                          [asyncio 主循环]                          │
│  UdpHeartbeatSource                    FastAPI 路由（REST）                      │
│   ├─ hb thread：5Hz 心跳 ──────────►    ├─ /health /ready /api/v1/*              │
│   └─ rx thread：recvfrom ──┐           ├─ /ws/state（WS 端点）                   │
│                            │           ├─ /hls/*（StaticFiles，先挂）            │
│                            ▼           └─ /（前端静态，后挂）                    │
│  MonitorService._on_frame      WsHub._loop（10Hz broadcast）                     │
│   ├─ asdu_parser.parse_frame         ▲                                           │
│   │   失败 → state.record_error      │ snapshot()（读一致性快照）                │
│   └─ state.update(parsed, raw) ──────┤                                           │
│                                      │                                           │
│  [看门狗线程] AxisWatchdog（20Hz）     │         StateStore（唯一权威状态）         │
│   └─ gateway.execute("axis") ────────┼────────►  ├ per-topic 时间戳(monotonic)    │
│                                      │           ├ per-topic stale 阈值            │
│  [视频守护线程] video-supervise       │           └ 有界原始报文 deque(1000)       │
│   └─ ffmpeg 子进程（RTSP→HLS）        │                                           │
│                                                                                 │
│  ControlGateway（四道闸）◄── REST 控制端点 / 看门狗                               │
│   └─ UdpControlSink.send(bytes) ──► 机器人 :30000                                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

线程模型（关键约束）：

| 线程/循环 | 职责 | 与主循环的边界 |
| --- | --- | --- |
| `m20-udp-rx` | 阻塞 `recvfrom`，回调 `_on_frame` | 回调只做解析+入库（纯内存操作，快）；**绝不阻塞等 IO** |
| `m20-udp-hb` | 5Hz 发心跳（与 rx 共用同一 socket，Q3 实测要求） | 无共享可变状态（socket 本身线程安全） |
| `WsHub._loop` | asyncio 任务，10Hz 广播 | 读 StateStore 快照（RLock 保护） |
| `m20-axis-watchdog` | 20Hz 发送轴指令，超时兜底 | 调 `gateway.execute`（内部有锁语义即靠单线程调用方） |
| `m20-video-supervise` | 监控 ffmpeg 子进程，退出退避重启 | 不碰状态层 |
| `m20-replay` / `m20-mock` | MockSource 发射帧 | 同 rx 回调路径 |

---

## 3. 模块职责与失败行为

| 模块 | 职责 | 失败行为（重要） |
| --- | --- | --- |
| `ingestion/asdu_parser.py` | **ACL 防腐层**：帧头校验（`EB91EB90`+长度+protocolType）、`json.loads`、topic 映射（`TOPIC_BY_KEY`）、字段归一化、关节名对照（16 名） | 解析失败抛 `ProtocolError` → 由 `_on_frame` 捕获转 `state.record_error`（死信计数，**不炸数据源线程**） |
| `ingestion/data_source.py` | `DataSource` 抽象；`UdpHeartbeatSource` 同一 socket 收/发心跳 | 心跳发送失败仅告警重试；rx 超时（`OSError`）继续循环；回调异常被 `_emit` 吞掉并告警（消费侧不拖死数据源） |
| `ingestion/mock_source.py` | 6 类真实字节帧构造 + JSONL 回放（`{"t":秒,"hex":"..."}`） | 回放文件缺失/坏行 → 告警跳过 |
| `state/state_store.py` | 唯一写入口 `update()`；per-topic monotonic 时间戳；有界原始报文 deque；计数器；`ready()` | **停更只标脏（stale）不删旧值**；缓冲满丢最旧（`dropped` 计数） |
| `state/models.py` | 契约模型 `RobotSnapshot`（pydantic）+ `snapshot_json_schema()` | `extra="allow"`：协议新增字段不导致响应失败 |
| `realtime/ws_hub.py` | WS 连接池 + 10Hz fan-out；建连即推一帧；最后客户端断开 → 回调 `_on_last_client_gone` | 单连接发送失败 → 摘除该连接；广播循环异常 → 记录后 0.5s 重试，**循环不死** |
| `control/patrol_codec.py` | 指令全集（type/command/items 构造）；`_clamp` 值域钳制 | 未知指令名 `KeyError` → 网关侧转结构化拒绝 |
| `control/control_gateway.py` | 四道闸 + 审计 + 急停锁存 | 拒绝时返回 `{ok:false, reason, detail}`（403 语义），审计留痕 |
| `control/axis_watchdog.py` | 20Hz 轴循环；超时/断开/页面隐藏 → 零位 + 软急停（一次性） | 兜底本身失败 → ERROR 日志（不吞） |
| `video/video_proxy.py` | ffmpeg 子进程托管：RTSP→HLS（`-c:v copy`，不转码）；退避重启（2s→30s） | ffmpeg 不存在 → `start()` 返回 False，`status().available=False`；进程退出 → 守护线程自动重启 |
| `config.py` | 集中配置 + `validate_startup()` fail-fast | 校验失败抛 `ConfigError` → 进程**拒绝启动**（不静默跑错配置） |
| `main.py` | 装配 + lifespan（起停顺序）+ REST/WS 路由 + 静态挂载 | 优雅停机顺序：看门狗（补零位）→ 控制 → 数据源 → 广播 |

---

## 4. 三条关键流

### 4.1 状态上行（正常路径）

```
机器人 2/10/2/2/1 Hz 推送 ──► rx thread ──► asdu_parser.parse_frame
  ──► StateStore.update（per-topic 时间戳）──►（10Hz）snapshot ──► WS 广播 ──► 前端渲染
```

- 心跳 5Hz 是**前提**：机器人只向"持续发心跳的 socket"推送（同一 socket 收回，Q3 实测 226 帧）。
- 频率表（真机实测）：`basic` 2Hz / `motion` 10Hz / `device` 2Hz / `fault` 2Hz+变更 / `nav` 1Hz / `sleep` 0.2Hz。

### 4.2 降级路径（**不许假数据**，质量第一优先级）

```
停更检测：age_ms > threshold_for(topic) → stale=true（数据保留，前端置灰）
链路断开：link_timeout(3s) 内无任何帧 → connected=false → 全屏横幅提示"数值可能过期"
解析失败：计入死信；error_rate > 20% → /ready degraded=true 并给出原因
```

- **per-topic 阈值**（实测修正）：阈值 = `max(0.5s, 2.5×推送周期)`。1Hz 的 `nav` 和 0.2Hz 的 `sleep` 用统一 500ms 会永远误判停更（已踩坑）。
- **monotonic 计时**：新鲜度一律用 `time.monotonic()`，机器人 `Time` 字段只展示不参与判定——196 时钟慢 846 天的实测反过来验证了该决策。

### 4.3 控制下行（四道闸 + 看门狗）

```
前端按住摇杆（≥20Hz feed）──► /api/v1/control/axis {continuous:true}
  ──► AxisWatchdog.feed() ──►（20Hz 循环）gateway.execute("axis", values)
      ──► 闸1 黑名单 ──► 闸2 开关/急停/租约 ──► 闸3 前置校验+钳制 ──► 编码 ──► UDP 发送
松开/断连/超时 250ms ──► _trip()：零位指令 + 软急停（锁存）→ 审计 + 日志 event=watchdog_trip
```

看门狗是**控制链最重要的单点设计**：绝不让机器人带着最后一条指令无限运动。

---

## 5. 契约（前后端唯一接口）

| 项 | 位置 | 约定 |
| --- | --- | --- |
| WS 快照 schema | `GET /api/v1/schema`（`state/models.py` 生成） | 版本 `SCHEMA_VERSION="1.0"`；**改字段必须升版本 + 同步契约测试** |
| 契约测试 | `tests/test_schema_contract.py` | `EXPECTED_FIELDS` 白名单守护各 topic 字段集合 |
| topic 数据形态 | `topics.<name>.data` 为 `Dict[str, Any]` | 协议字段语义仍有未知项（Q12），过早强类型会频繁破坏契约 |
| 控制响应 | `{ok, command, reason, detail, status}` | 被拒时 `reason` 为稳定枚举字串（`CONTROL_DISABLED`/`LEASE_EXPIRED`/…），前端据此给提示 |

---

## 6. ADR 索引（详情见计划书 §7）

| 编号 | 决策 | 一句话理由 |
| --- | --- | --- |
| ADR-001 | 数据通道：UDP 心跳 + ASDU 解析（非 ROS2 订阅） | 无 ROS2 依赖、零侵入、实测最稳；ROS2 留路径 1 |
| ADR-002 | 部署位置：后端驻 AOS 196 | 监控协议与 MediaMTX 都在 AOS 本机，同机直达 |
| ADR-003 | 视频经后端代理（RTSP→HLS），浏览器不直连 | 浏览器不能播 RTSP；同源免额外端口/穿越 |
| ADR-004 | 控制分层开放 L0/L1/L2 | 默认只监；低危可控；高危黑名单 |
| ADR-005 | 实时通道 WebSocket（非 SSE） | 双向（前端消息触发快照）+ 断连即感知（租约绑定） |
| ADR-006 | 状态权威唯一 + 新鲜度语义 | 只有 StateStore 可写；monotonic 计时；停更标脏不删 |
| ADR-007 | 无数据库：内存状态 + 有界环形缓冲 | 运维工具不需要持久化；长时间运行内存不涨 |
| ADR-008 | 配置集中 + 启动校验 fail-fast | 配错在启动时炸，而不是运行时静默错 |
| ADR-009 | 后端语言：Python 3 + FastAPI | 复用 lite3 骨架与运维经验；3.8 兼容 |
| ADR-010 | 控制出口对称抽象 `ControlSink` | 与 DataSource 对称，ROS2 控制接入零改动 |

---

## 7. 安全设计（不可妥协，计划书 §9）

| 机制 | 实现 | 验证 |
| --- | --- | --- |
| 默认只监 | `control.enabled=false`（L0） | systemd 单元默认 false |
| 开启需二次确认 | `POST /control/enable` 必须 `confirmed:true`；前端弹确认 | `test_control_gateway.py` |
| 租约绑定 WS | 前端定期续约（5s）；WS 断开 → `_on_last_client_gone` 清租约 + 看门狗 pause | 同上 |
| 值域钳制 | `patrol_codec._clamp`（服务端不信任浏览器） | 同上 |
| 黑名单 | `Charge=2` 无条件拒绝 | 同上 |
| 急停永远可用 | `always_allowed: soft_estop`；不受开关/租约限制 | 同上 |
| 急停锁存 | 发急停后置 `_estop=True` 拦后续指令（曾是真缺陷，单测锁定） | 同上 |
| 全量审计 | deque(500)：ts/command/params/result/actor/confirmed/forced/reason | `/control/audit` |
| CORS 收敛 | 仅放行 Vite 开发源（5173），不用 `*` | `main.py` |
| 脱敏 | 真实配置只走环境变量；仓库只留 `*.example` | 提交前检查 |

---

## 8. 扩展点（往哪里加代码）

| 想做的事 | 动哪里 | 不要动 |
| --- | --- | --- |
| 新增一个状态面板字段 | `asdu_parser.py` 字段映射（若有新字段）+ `state/models.py` 契约（如升版本）+ `tests/test_schema_contract.py` 白名单 + 前端组件 | StateStore / WsHub 骨架 |
| 新增一个控制指令 | `patrol_codec.py` 的 `COMMANDS` 注册表（含 `motion` / `always_allowed` 标记） | 网关四道闸逻辑 |
| 换数据来源（ROS2） | 新增 `Ros2TopicSource(DataSource)`，`build_data_source` 加分支 | 所有上层 |
| 换控制出口（ROS2） | 新增 `Ros2ControlSink(ControlSink)` | 网关 / 看门狗 / 前端 |
| 新增调试端点 | `main.py` 路由 + `tools/` 脚本 | — |
| 调整频率/阈值 | `config.py` 默认值 + systemd `Environment=` | 硬编码 |

> 原则：**帧格式只写一处**（`asdu_parser.encode_frame`，`patrol_codec` 复用它）；**契约只在一处**（`state/models.py`）。

---

## 9. 已知边界与未竟事项

| 项 | 现状 | 影响 |
| --- | --- | --- |
| `nav` 数据仅在 API 可读 | 前端暂未做导航面板 | 不影响监控主功能；需要时加组件即可 |
| ~~前后相机方位未目视核实（Q5）~~ | ✅ 2026-10-15 已目视核实：**video1=前路 / video2=后路** | 前端"前/后"按钮映射与之一致 |
| 控制指令真机首测未做（Q10） | 需空旷场地 + 人员看护 | 首次实测前保持 L0 |
| `ros2` 数据源 | `build_data_source` 抛 `NotImplementedError`（预留） | 计划书 §18 路径 1 落地时实现 |
| `Charge`/`errorCode` 等枚举语义 | 透传原值展示 | M2 字段核对后可按需补映射 |
