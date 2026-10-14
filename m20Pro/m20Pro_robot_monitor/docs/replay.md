# 回放与测试（replay）

> 核心能力：**无真机也能做全链路回归**。真机抓包 → JSONL → 回放/测试 fixtures → 每次改动后自动验证解析层。
> 相关：[debugging.md](debugging.md)（探针工具）· [architecture.md](architecture.md)（测试与契约设计）

---

## 1. 抓包（在 196 / 能到机器人的机器上）

```bash
# 用独立探针抓 10~30 秒的真实帧，落地 JSONL
python3 tools/probe_asdu.py --target 127.0.0.1 --seconds 20 --out /tmp/asdu.jsonl

# 拷回 PC 存档（本工程约定放 tools/capture/）
scp m20pro-f20-0-196:/tmp/asdu.jsonl tools/capture/asdu_loopback_YYYYMMDD.jsonl
```

**JSONL 格式**（每行一帧，与回放/分析/回归三方兼容）：

```json
{"t": 0.201, "from": "127.0.0.1:30000", "key": "1002/4", "hex": "eb91eb90...", "length": 1893}
```

| 字段 | 说明 |
| --- | --- |
| `t` | 相对抓包开始的秒数（回放按此间隔还原节奏） |
| `key` | `Type/Command`（解析不出为 `null`） |
| `hex` | 完整原始帧（16 字节帧头 + JSON）的十六进制 |
| `from` / `length` | 来源地址 / 字节长度 |

现有 fixtures：`tools/capture/asdu_loopback_20261015.jsonl`（2026-10-14 于 196 抓取，10 秒 **226 帧**，覆盖 basic/motion/device/fault/ack/nav 六类）。

---

## 2. 回放模式（运行服务时重放抓包）

用环境变量把数据源切到 mock + 指定回放文件：

```bash
# 本地
cd backend
M20__DATA_SOURCE=mock M20__REPLAY_FILE=../tools/capture/asdu_loopback_20261015.jsonl \
  python -m uvicorn main:app --port 8080

# 196 上临时演练（不动 systemd 单元）
cd /home/djw/monitor/backend
M20__DATA_SOURCE=mock M20__REPLAY_FILE=/home/djw/monitor/tools/capture/asdu_loopback_20261015.jsonl \
  ./venv/bin/python -m uvicorn main:app --port 8081
```

行为（`MockSource._replay_loop`）：
- 按录制时的时间间隔**限速重放**（`t` 差值决定帧间等待），体验与真机一致；
- 时间戳重置为"当前"——新鲜度判定照常工作（跑完最后一批帧后自动转 stale，可验证降级路径）；
- 回放跑完即静默（不循环）；要循环重放写个 wrapper 或多次启动即可。

**回放能验证什么**：解析层对真实字节的鲁棒性、状态层各 topic 组装、前端渲染与 stale 表现——**验证不了**协议外的行为（如机器人实际响应控制指令）。

---

## 3. 测试体系（pytest 64 项）

```bash
# 项目根执行（依赖：fastapi / uvicorn / websockets / pydantic / pydantic-settings / httpx / pytest）
python -m pytest tests/ -q            # → 64 passed
python -m pytest tests/ -q -k schema  # 单跑契约测试
```

| 文件 | 项数焦点 | 守护的东西 |
| --- | --- | --- |
| `test_asdu_parser.py` | 编解码往返 / 帧头校验 / topic 映射 / 字段归一化 / 关节名 | ACL 层不漂移 |
| `test_state_store.py` | per-topic 阈值 / 停更标脏不删值 / 有界缓冲 / ready 判定 / monotonic | 降级语义（不许假数据） |
| `test_schema_contract.py` | `SCHEMA_VERSION` + `EXPECTED_FIELDS` 白名单 | 前后端契约冻结 |
| `test_control_gateway.py` | 四道闸逐项 / 黑名单 / 急停锁存 / 租约 / 审计 | 控制安全 |
| `test_axis_watchdog.py` | 20Hz tick / feed 超时兜底 / pause 兜底 / 不重复 trip | "绝不带着最后一条指令运动" |
| `test_pipeline.py` | mock → 解析 → 状态 → 快照（含 WS 渲染） | 全链路主干 |
| `test_real_capture.py` | **226 帧真机抓包回归**（见下） | 解析层的最强回归 |
| `test_video_proxy.py` | ffmpeg 命令构造（posixpath / 不转码 / 低延迟参数） | 视频代理不回归 |

### 3.1 真机抓包回归（`test_real_capture.py`）

把 fixtures 灌进解析层/状态层做端到端断言（文件缺失时自动 skip，保证无真机环境可跑）：

1. **226 帧零死信**——每帧都能解析成功；
2. topic 覆盖：`basic/motion/device/fault/ack/nav` 全部出现，且 motion（10Hz）帧数 > basic（2Hz）；
3. 运控帧 **16 关节**（`joint_names[3] == "LF_wheel"`）；
4. 设备帧 **双电池 + 16 路电机温度**；
5. 导航帧提供 `pos_x/y/z + rpy + confidence`；
6. 全量灌进 StateStore 后快照可用、零错误。

> 这组测试把"轮足 16 关节 / 双电池 / nav 实测新增"等**协议事实**钉死在代码里——将来协议变更会立刻红。

---

## 4. 加新测试的约定

| 场景 | 怎么写 |
| --- | --- |
| 新状态字段 | ① parser 映射补字段 → ② `test_asdu_parser` 加断言 → ③（若进契约）`test_schema_contract` 的 `EXPECTED_FIELDS` 白名单同步 |
| 新控制指令 | `test_control_gateway` 加：用 `RecordingSink` 断言编码字节与闸门行为 |
| 新前端行为 | 暂无前端单测——以 `verify_deploy.py` + 浏览器人工验收为准 |
| 协议真机新发现 | 抓包 JSONL 入库 `tools/capture/` + `test_real_capture` 加断言（**先抓包后改代码**） |

**测试原则**：
- 用 `RecordingSink` / `MockSource` 代替真实 IO（单测不碰网络、不起进程）；
- 时间相关逻辑注入假时钟（`clock=lambda: t`），不 `sleep`；
- 契约测试用白名单，**新增字段必须显式加白名单**（防止悄悄漂移）。

---

## 5. 从抓包到分析（字段核对流程）

```
probe_asdu.py --out  ──►  tools/capture/*.jsonl  ──►  analyze_capture.py（统计+差异）
                                │
                                ├──►  tests/test_real_capture.py（回归断言）
                                └──►  MockSource 回放（无真机演练）
```

完整的字段核对报告（M2 阶段产出）：用 `analyze_capture.py` 输出对照工程映射表，逐字段确认语义/单位/枚举，未核实项显式标注。
