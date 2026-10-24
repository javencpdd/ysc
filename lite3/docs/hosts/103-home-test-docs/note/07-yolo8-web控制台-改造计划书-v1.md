# Lite3 yolo8 Web 控制台改造计划书 v1

| 项 | 值 |
| --- | --- |
| 文档版本 | v1.0 |
| 日期 | 2026-10-22 |
| 状态 | 待评审（本文为设计文档，未做任何真机改动） |
| 目标机 | Lite3 103 感知主机（`lite`，Jetson Xavier NX / aarch64 / Ubuntu 20.04） |
| 作用对象 | `/home/test/yolo8`（YOLOv8 人体跟踪 + 双通路发布工程） |
| 上游参考 | `/home/ysc/lite_cog_ros2/track`（只读） |
| 关联文档 | `note/部署笔记.md`、`note/双通路发布-避坑记录.md`（在 git 索引中，磁盘副本已缺失） |

---

## 0. 结论摘要

1. **可行**：需求全部可实现，且大部分是低风险改造；真正有技术含量的只有两块——① onnx → TensorRT engine 的异步导出，② 推流分路的热切换时序。
2. **架构主线**：**双进程解耦**。推理进程（`yolo_worker`，改造 `run_tracker_publish.py`）只管帧循环；新增控制台进程（`console`）只做管理。两者以 `config.json` 为唯一接口，靠 mtime 轮询实现**秒级热更新，全程不重启、不重载模型**。
3. **技术路线硬约束**：103 的 Python 3.8.10 **无 venv、无可用 pip 源**（`pypi.org` 超时），因此控制台与前端默认采用 **Python 标准库 + 原生 HTML/JS 单文件**，零第三方依赖、零构建。Vue3 方案仅作为"与 M20 控制台统一观感"的可选项。
4. **三条不可妥协的设计原则**：
   - **不重启原则**：阈值、推流开关、抓拍开关一律热生效；重启要付 35s 冷启动代价。
   - **抓拍绝不在主循环同步写盘**：JPEG 编码 10–30ms，直接做会把 22–26fps 打成个位数。
   - **一切写操作有配额与上限**：磁盘仅剩 41G，无配额会被单张高置信画面写爆。
5. **工作量**：约 **13 人日**（区间 10–16），分 6 期，每期可独立上线、独立回滚。
6. **最大风险**：`R1 源码缺失`（已发生，是开工的前置阻塞项，但有完整 git 副本可一键恢复）。

---

## 1. 背景与目标

### 1.1 背景（2026-10-22 实测现状）

| 项 | 现状 | 影响 |
| --- | --- | --- |
| 服务状态 | `lite3-yolo-publish.service` / `lite3-yolo-rosbridge.service` 已 install 但 **disabled + inactive** | 现网不跑 YOLO |
| 进程 | `logs/yolo.pid = 69305` 已死；无相关进程 | 无法验证 |
| 日志 | `yolo-publish.log` 停在 2026-09-23 17:58，尾部为 `no detections` | 无近期运行证据 |
| 自研源码 | `src/` 下 12 个 `.py` **本体全部不在磁盘**，只剩 `__pycache__/*.pyc` 与 3 个 `.bak-2026092x` | **当前无法启动** |
| 部署脚本 | `deploy/` 只剩 `yolo-publish.env.bak-20260923`，配置正主与全部脚本缺失 | 无配置入口 |
| 文档 | `note/` 目录不存在（git 索引中有 2 篇，带 skip-worktree） | 经验无法查阅 |
| 第三方 | `ultralytics 8.1.0` 源码树、`hub_sdk`、4 个模型文件（含 `yolov8n_arm.engine` 19.9MB）完好 | 恢复后即可跑 |
| 磁盘 | `/` 117G 已用 71G（64%），余 41G | 抓拍需配额 |

> 源码缺失被掩盖的原因：git 索引对这些路径打了 **`skip-worktree`（`S`）** 标志，`git status` 因此一路报"干净"。

### 1.2 目标

| 编号 | 目标 |
| --- | --- |
| G1 | Web 控制台随主机自启动，内网可访问，含基础认证 |
| G2 | 通过 Web 启停 yolo 服务（yolo / rosbridge 两个 unit） |
| G3 | 通过 Web **分路**开关推流：RTMP、ROS2 图像，各自独立、热生效 |
| G4 | 检测置信度阈值可配置，Web 与配置文件双入口同源 |
| G5 | 预测目标置信度 ≥ 阈值时，自动把该帧存到 `pic/`，带冷却与配额 |
| G6 | 通过 Web 上传 onnx，异步导出 TensorRT engine，原子替换并支持重载 |

### 1.3 非目标（v1 明确不做）

- 不做训练、数据集管理、标注工具。
- 不做多路视频源（维持单 RTSP 源 `rtsp://192.168.1.120:8554/test`）。
- 不做外网直暴露（仅内网 + SSH 隧道/反代）。
- **不改控制律**：`RobotController` 的 PD 跟踪逻辑冻结，只做钩子化改造。
- 不升级/替换 ultralytics 8.1.0 源码树（AGPL 传染面已由 .gitignore 控制）。

---

## 2. 现状评估与前提

### 2.1 环境事实（设计约束来源）

| 类别 | 事实 | 对设计的约束 |
| --- | --- | --- |
| 硬件 | Jetson Xavier NX，6 核 / 6.7G | 控制台不得与推理抢 CPU |
| CPU 亲和 | **cpu5-7 有 SCHED_FIFO 实时线程**（hsLidar prio54、lio_ddsnode prio64） | 控制台必须绑 **CPU 0-2**；worker 维持 0-3 |
| Python | 3.8.10，系统 python3，无 venv，`import ultralytics` 失败（靠 cwd 源码树） | 禁 `X \| None`、`list[]` 注解；标准库优先 |
| 网络 | 103 无 WiFi；出网经 120 做 MASQUERADE；内网 192.168.1.x | 默认绑 `192.168.1.x` + token；外网走隧道 |
| ROS | Foxy | 脚本 source 时必须 `set +u`（B3 坑） |
| 磁盘 | 余 41G，logs 已 27M | 抓拍配额 + 保留期 + 日志轮转 copytruncate |
| 启动 | 冷启动约 35s（RTSP 建链 + TRT engine 加载） | 高频操作一律热切换 |
| 帧率 | 端到端 22–26fps，单核 ~80% CPU | 抓拍必须异线程 |

### 2.2 前置阻塞项（P0，必须先做）

1. 恢复源码：`git -C /home/test checkout -- yolo8/src yolo8/deploy yolo8/note`（git 对象库完整，含 12 个源文件 + 12 个部署脚本 + 2 篇 note）。
2. 建议同时解除 skip-worktree 掩盖：`git update-index --no-skip-worktree <files>`，让后续缺失重新可见。
3. 重建 `deploy/yolo-publish.env`（现有 `.bak-20260923` 可直接改名，内容仍有效：模式 rtmp、流名 `live/lite3_yolo`、bitrate 1Mbps）。
4. 备选恢复源：`/home/ysc/lite_cog_ros2/track/src`（完整，但缺 `RtmpPublisher` 与 `run_tracker_publish.py`）。

---

## 3. 需求清单（MoSCoW）

| 优先级 | 需求 |
| --- | --- |
| **Must** | G1 自启动控制台、G2 服务启停、G3 分路推流热开关、G4 阈值可配、G5 抓拍存 pic/ |
| **Should** | 抓拍图片的浏览/下载/删除、状态面板（fps/推理 ms/CPU/内存/流错误）、日志 tail、立即抓拍 |
| **Could** | 录制短视频片段、多 engine 管理、Web 修改 RTMP 地址与码率、sparkline 历史曲线 |
| **Won't（v1）** | 训练、多路视频、外网暴露、控制律修改、ultralytics 升级 |

---

## 4. 总体架构

### 4.1 双进程解耦

```text
数据面（既有，改造）                     控制面（新增）
120 RTSP ─► nvv4l2decoder 硬解          浏览器(PC)
   ─► yolo_worker（YOLOv8n TRT） ◄──配置── console server.py（标准库）
        · conf 每帧热读                     · CPUAffinity=0-2
        · 抓拍独立写盘线程 ──► pic/         ─► config.json（唯一入口）
   ─► RTMP 硬编 / ROS2 图像                ─► systemctl / PID 直管
      （分路热开关）                        ─► model/uploads ─► engine 导出
```

### 4.2 为什么这样切

- **不在 worker 内嵌 Web 框架**：ThreadingHTTPServer 与推理同进程会争抢 GIL，直接吃掉本就不富裕的帧率余量。
- **"配置即接口"**：worker 不监听任何端口（攻击面最小、无并发问题），每秒检查一次 `config.json` 的 mtime（stat 成本可忽略），变化则重载。控制面只负责改文件，双方零 IPC。
- **console 独立进程**：崩了不影响推流；CPU 绑 0-2 避开实时线程。

---

## 5. 功能详细设计

### 5.1 服务生命周期管理（G2）

- **双模判定**（沿用部署笔记 B7 结论）：`unit 已安装` **且** `systemctl is-enabled` 成功 → 走 systemd（自动提权）；否则 → **PID 文件直管，免 sudo**。
- PID 直管流程：启动前检查 `logs/yolo.pid` 活性 → 写新 pid → `SIGTERM` 停止（等 20s，超时 `SIGKILL`）→ 清 pid 文件。
- 防重入：启动前持有 `logs/yolo.lock`（`fcntl.flock`），已持锁则拒绝。
- 若采用 systemd 模式，配 sudoers 白名单（仅放行本工程 3 个 unit，禁止通配）：

```text
ysc ALL=(root) NOPASSWD: /bin/systemctl start lite3-yolo-publish.service, \
    /bin/systemctl stop lite3-yolo-publish.service, \
    /bin/systemctl restart lite3-yolo-publish.service, \
    /bin/systemctl start lite3-yolo-rosbridge.service, \
    /bin/systemctl stop lite3-yolo-rosbridge.service, \
    /bin/systemctl restart lite3-yolo-rosbridge.service
```

### 5.2 推流分路热切换（G3）

- `RtmpPublisher` 改为**惰性创建/销毁**：`stream.rtmp=false` 时主循环跳过；由 false→true 时按需构造，构造失败记 `rtmp_err` 并回滚到上一态。
- 关闭时序（关键）：`appsrc.emit("end-of-stream")` → `bus` 收 EOS → `pipeline.set_state(NULL)` → 释放对象。**不可直接丢弃对象**，否则泄漏 GStreamer 资源与 fd。
- ROS2 侧同理：`publisher`/`node` 惰性创建与 `destroy_node`。
- 状态机：`idle → starting → running → stopping → idle`，异常进 `error`；前端只读状态机，不直接下指令给 pipeline。
- 生效延迟 ≤ 1s（mtime 轮询粒度）。

### 5.3 置信度阈值热更新（G4）

- ultralytics 8.1.0 的 `model.track()` **接受逐次调用的 `conf` 参数**，因此热更新 = 每帧多读一个变量，无需重建模型。
- 主循环：`conf = cfg.conf_threshold` → `model.track(img, persist=True, classes=[0], conf=conf)`。
- 取值约束：`0.05 – 0.95`，步进 `0.05`；越界由服务端拒绝并返回 400（不静默夹取——吸取 M20 休眠 Time 被静默夹取的教训）。
- 双入口：Web `PUT /api/config` 与手改 `config.json` 都写入同一文件，`updated_at` 字段记录来源。

### 5.4 高置信帧抓拍（G5）

| 子项 | 设计 |
| --- | --- |
| 触发条件 | `max(results[0].boxes.conf) >= cfg.conf_threshold` 且抓拍开关为真 |
| 挂点 | `RobotController.Run()` 返回后（注意 P9 坑：无结果时 `Run()` 返回 `None`，该帧不抓） |
| 线程模型 | 主循环只 `queue.put_nowait()`（有界 64，满则丢弃并计数）；**独立 daemon 线程**负责 `cv2.imwrite` |
| 写盘前处理 | P10 坑：RobotController 绘制路径会把帧转成 `UMat`，必须先 `frame.get()` 再编码 |
| 文件命名 | `YYYYmmddTHHMMSS_mmm_c<置信度百分位>_id<trackid>.jpg`，例：`20261022T011500_120_c87_id3.jpg` |
| 元数据 | 可选 sidecar `.json`（框坐标、类别、推理耗时、帧号、阈值快照） |
| 冷却 | 默认 2000ms 全局冷却（v1 不做按 track id 冷却，见 Q3） |
| 配额 | 500 张/天 + 保留 7 天；启动时与每小时各扫一次，超限删最旧 |
| 目录 | `/home/test/yolo8/pic/`（加入 `.gitignore`） |

### 5.5 图片管理

- `GET /api/pics?date=&page=&size=` 分页列表（默认 24/页，按时间倒序）。
- `GET /api/pics/<name>` 原图；`GET /api/pics/<name>?thumb=1` 缩略图（cv2 缩放至宽 320）。
- `DELETE /api/pics/<name>` 删除（前端二次确认）。
- **路径穿越防护**：文件名做白名单校验（`^[0-9T_Za-z._-]+$`）并 `os.path.realpath` 后确认仍在 `pic/` 内。

### 5.6 onnx 上传与 engine 导出（G6）

```text
上传 → 校验 → 落盘 uploads/<uuid>.onnx → 异步导出（子进程）
  → exported（新 engine 落 tmp 名）→ 原子 rename 替换 → 备份旧 engine
  → 用户点"重载模型"（写 config.model.pending_reload=true）
  → worker 在帧边界重建 YOLO 实例（阻塞 2–5s）→ active
```

| 子项 | 设计 |
| --- | --- |
| 上传校验 | 扩展名 `.onnx`；魔数检查（ONNX 为 protobuf，头部含 `ir_version` 字段，可做弱校验）；大小 ≤ 50MB；文件名白名单字符 |
| 异步任务 | `subprocess.Popen` 起 `python3 -u export_engine.py <onnx> <out>`，单任务队列（同时只允许一个导出）；超时 10min 强杀 |
| 导出命令 | 调 ultralytics API：`YOLO(onnx).export(format="engine", half=True, device=0)`（**不直接用 trtexec**，保证预处理/后处理与训练一致，见 Q5） |
| 进度 | 子进程 stdout 实时读入环形缓冲，`GET /api/model/export/status` 返回 `{state, progress_hint, tail[]}` |
| 原子替换 | 新 engine 写 `yolov8n_custom_arm.engine.tmp` → `os.replace()` 同分区原子改名 → 旧文件改名为 `.bak-<时间戳>` |
| 一致性告警 | 若新模型类别数与 `CocoTypeId.kPerson=0` 假设不符，导出成功但**告警提示**，由用户确认是否重载 |
| 失败处理 | 删除 tmp、保留旧 engine、错误写入 `logs/engine-export.log`，状态回 `failed` |

### 5.7 状态监控

- 采样指标：fps（5s 滑动窗口）、累计帧数、skipped、推理耗时 EMA、RTMP 错误、ROS2 频率、`os.getloadavg()`、`/proc/meminfo` 可用内存、进程 uptime、当前 conf、今日抓拍数、磁盘余量。
- 无 psutil，全部走 `/proc` 与标准库。
- 前端 1s 轮询 `GET /api/state`（**不用 WebSocket**，零依赖）；环形缓冲 300 点画 sparkline。
- `GET /api/logs?lines=200` tail 日志（复用 B1 坑经验：`tail_log()` 兜底，`[ -f ] || return 0`）。

### 5.8 控制台自启动（G1）

```ini
[Unit]
Description=Lite3 yolo8 web console
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ysc
Environment=HOME=/home/ysc
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/home/test/yolo8/console
ExecStart=/usr/bin/python3 -u server.py --bind 192.168.1.103 --port 8090
CPUAffinity=0-2
Restart=always
RestartSec=5
StandardOutput=append:/home/test/yolo8/logs/console.log
StandardError=append:/home/test/yolo8/logs/console.log

[Install]
WantedBy=multi-user.target
```

- 默认只 `enable` 控制台；**yolo-publish 维持"默认不启用"**的既有决策，由用户按需开启。
- 环回/内网绑定与 token 策略见 §8。

---

## 6. 接口设计

### 6.1 `config/yolo8.json`（唯一运行时配置）

```json
{
  "version": 1,
  "conf_threshold": 0.5,
  "snapshot": {
    "enabled": true,
    "cooldown_ms": 2000,
    "daily_quota": 500,
    "retention_days": 7,
    "save_meta": true
  },
  "stream": {
    "rtmp": true,
    "ros2_image": true,
    "ros2_every": 3,
    "rtmp_url": "rtmp://172.31.68.227:1936/live/lite3_yolo",
    "rtmp_bitrate": 1000000
  },
  "model": {
    "engine": "../model/yolov8n_arm.engine",
    "pending_reload": false
  },
  "pic_dir": "../pic",
  "updated_at": "2026-10-22T01:00:00+08:00"
}
```

规则：未知字段忽略、缺失字段填默认值、整体校验失败则**保持上一份有效配置**并在日志报错（绝不带病运行）。

### 6.2 REST API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/state` | 状态快照（1s 轮询） |
| POST | `/api/service/{start\|stop\|restart}` | body `{target: yolo\|rosbridge}` |
| GET | `/api/service/status` | 各 unit / 进程状态与判定模式（systemd/PID） |
| POST | `/api/stream/{rtmp\|ros2}` | body `{enabled: bool}`，写 config |
| GET | `/api/config` | 读配置 |
| PUT | `/api/config` | 改配置（服务端校验，原子写 + `.bak`） |
| POST | `/api/snapshot` | 立即抓拍一帧（调试用） |
| GET | `/api/pics?date=&page=&size=` | 抓拍列表 |
| GET | `/api/pics/<name>[?thumb=1]` | 原图 / 缩略图 |
| DELETE | `/api/pics/<name>` | 删除（二次确认） |
| POST | `/api/model/upload` | multipart onnx |
| GET | `/api/model/export/status` | 导出任务状态与日志尾 |
| POST | `/api/model/reload` | 触发 worker 帧边界重载 |
| GET | `/api/model/info` | 当前 engine 大小/mtime/来源 |
| GET | `/api/logs?lines=` | tail 运行日志 |

### 6.3 `/api/state` 字段

```json
{
  "worker": {"alive": true, "pid": 123, "uptime_s": 3600,
             "fps": 24.1, "frames": 86400, "skipped": 12,
             "infer_ms_ema": 17.2, "conf_threshold": 0.5},
  "stream": {"rtmp": "running", "ros2_image": "running",
             "rtmp_url": "rtmp://...", "rtmp_err": null, "ros2_hz": 8.0},
  "snapshot": {"enabled": true, "today_count": 137, "queue_depth": 0,
               "dropped": 0, "last_file": "20261022T011500_120_c87_id3.jpg"},
  "model": {"engine": "yolov8n_arm.engine", "pending_reload": false,
            "export": {"state": "idle"}},
  "host": {"load1": 1.8, "mem_avail_mb": 2100, "disk_avail_gb": 41},
  "console": {"version": "1.0.0", "owner": "session-xxx"}
}
```

---

## 7. 前端设计

- **主方案**：`console/static/index.html` 单文件，原生 JS + CSS，零构建零依赖，直接由 `server.py` 伺服。
- **可选方案**：Vue3 + Vite 构建 dist（与 M20 控制台统一技术栈，可复用组件模式）。
- 页面结构：顶部徽标墙（服务/RTMP/ROS2/抓拍/模型/磁盘）→ 五个卡片：
  1. 服务（启停 + 自启开关 + 判定模式）
  2. 推流（RTMP / ROS2 分段开关 + 当前地址 + 错误）
  3. 检测与抓拍（阈值滑块 + 保存 + 冷却/配额 + 立即抓拍 + 今日计数）
  4. 模型（当前 engine 信息 + 上传拖拽 + 导出进度 + 重载）
  5. 图片与日志（网格分页 + 大图 + 删除 + 日志滚动）
- 深色主题；危险操作（停服务、删图片、重载模型）二次确认。
- UI 铁律（沿用 M20 ADR-020/021）：状态组件解构到顶层、开关用统一 `DeviceToggle` 模式（`setX(目标值)`，"正在关闭"须对比当前真实状态）、分段控制用 `SegmentedControl`。
- 验收必须 playwright 真机核对（M20 既有流程）。

---

## 8. 安全与可靠性

| 项 | 措施 |
| --- | --- |
| 监听地址 | 默认 `192.168.1.103:8090`（内网可达）；不绑 0.0.0.0 |
| 认证 | 32 位随机 token，首次启动生成写入 `console/token`（0600）并打印到日志；前端登录态存 sessionStorage |
| 控制权 | 借 M20 ADR-028：单 owner 会话，非 owner 只读；owner 60s 无续约自动释放 |
| 上传 | 大小/魔数/文件名三重校验；单任务导出队列 |
| 路径 | 所有文件操作白名单 + realpath containment 检查 |
| 原子性 | 配置与 engine 均"写 tmp → rename"；旧文件留 `.bak-<ts>` |
| 审计 | 所有写操作（启停/改配置/上传/删除）追加 `logs/console-audit.log` |
| 限流 | 简单 token bucket（如 10 req/s），防误触与脚本刷接口 |

---

## 9. 风险登记册

| ID | 风险 | 概率 | 影响 | 缓解 | 回滚 |
| --- | --- | --- | --- | --- | --- |
| R1 | 源码缺失，无法开工 | **高（已发生）** | 阻断 | P0 用 git checkout 恢复；备选上游副本 / pyc 反编译 | 恢复失败则回到只读分析态 |
| R2 | engine 导出失败或超时 | 中 | G6 不可用 | 异步 + 10min 超时 + 旧 engine 保留 + 失败日志 | 删 tmp，继续用旧 engine |
| R3 | 推流热切换泄漏 GStreamer 资源 | 中 | 帧率下降 / fd 耗尽 | EOS→NULL 严格时序 + 状态机 + 50 次切换压测 + fd 计数监控 | 重启服务 |
| R4 | 抓拍写盘拖慢帧循环 | 中 | fps 跌落 | 独立线程 + 有界队列 + 丢弃计数 | 关闭抓拍开关 |
| R5 | 磁盘被写爆 | 中 | 系统故障 | 500/天 + 7 天保留 + 每小时巡检 + 余量 <5G 停抓拍 | 手动清理 |
| R6 | Py3.8 语法不兼容（`X \| None` 等） | 中 | 启动即崩 | 本机 3.13 测不出 → **必须真机 `python3 -c` 冒烟**；禁用新版语法 | 热修复 |
| R7 | 误操作停服务 / 删图片 | 中 | 数据丢失 | 二次确认 + 软删除（回收站，见 Q2） | 回收站恢复 |
| R8 | 控制台被未授权访问 | 低 | 误控 | 不绑 0.0.0.0 + token + 单 owner | 停 console 服务 |

---

## 10. 分期实施计划

| 期 | 范围 | 交付物 | 验收标准 | 工作量 |
| --- | --- | --- | --- | --- |
| **P0** | 前置恢复 | 源码/deploy/note 恢复；skip-worktree 解除；冒烟启动一次 | `verify_headless.py` 通过；RTMP 流可 ffprobe 拉取 | 0.5d |
| **P1** | 控制台骨架 | `console/server.py` + 单文件前端 + unit；服务启停 + 状态面板 | 控制台自启；启停 10 次无僵尸进程；`/api/state` 1s 内响应 | 2d |
| **P2** | 配置热更新 + worker 改造 | `config_loader.py`；阈值热读；推流分路热开关 | 改阈值 ≤1s 生效且无需重启；推流切换 50 次后 fps ≥ 基线 90%、fd 数不增长 | 3d |
| **P3** | 抓拍 + 图片管理 | `snapshot_writer.py`；pic/ 配额清理；图片 API 与页面 | 阈值 0.1/0.9 下抓拍数量符合预期；命名合规；主循环 fps 无显著下降 | 2d |
| **P4** | onnx 上传 + 导出 + 重载 | 上传校验、异步导出、原子替换、重载钩子 | 好 onnx 导出成功并可重载；坏文件（改扩展名 txt、超限、空文件）全部被拒 | 4d |
| **P5** | 安全加固 + 总验收 | token、单 owner、审计日志、限流；24h 长稳 | L0–L5 全部通过；RSS 波动 <10%；磁盘余量 >5G | 1.5d |

合计约 **13 人日**。每期独立可上线、独立可回滚（回滚 = 停 console + 恢复 config 备份，数据面不受影响）。

---

## 11. 验收测试方案

| 级别 | 内容 | 判据 |
| --- | --- | --- |
| L0 | 冒烟 | console 进程存活；`/api/state` 返回 200；真机 `python3 -c "import ..."` 无语法错 |
| L1 | 服务启停 | 连续 10 次启停，无僵尸、无重复实例、pid 文件一致 |
| L2 | 推流热切换 | 50 次切换，fps ≥ 基线 90%，`/proc/<pid>/fd` 数量回归稳定，无 GStreamer 报错 |
| L3 | 阈值与抓拍 | 阈值 0.1 / 0.9 下抓拍数量符合预期；命名合规；队列丢弃计数为 0 |
| L4 | 模型上传 | 好 onnx 走通全链路；三类坏文件全部被拒且不留残file |
| L5 | 长稳 24h | RSS 波动 <10%；磁盘余量 >5G；日志轮转正常；RTMP 可 ffprobe 拉取、Foxglove 8Hz |

---

## 12. 约束与依赖

1. Python 3.8.10、无 venv、无可信 pip 源 → 全部新代码用标准库，禁 3.9+ 语法。
2. 控制台必须绑 CPU 0-2；worker 维持 0-3（cpu5-7 为 SCHED_FIFO 实时线程，无条件抢占）。
3. `ultralytics/` 与 `hub_sdk/` 源码树**不可删、不可移动**（系统 python3 无该包，靠 cwd 导入）。
4. ROS2 Foxy：任何 source `setup.bash` 的脚本必须先 `set +u`。
5. 磁盘余量 41G：抓拍配额 + 日志轮转（`copytruncate`）双保险。
6. 103 无 WiFi、经 120 NAT 出网：推流与上传的目标可达性依赖 120 的 MASQUERADE 规则（120 重启即失效，需复查 `host_start2.sh`）。

---

## 13. 待决问题（Open Questions）

| 编号 | 问题 | 倾向建议 |
| --- | --- | --- |
| Q1 | 控制台监听 `127.0.0.1` 还是 `192.168.1.103`？ | 后者 + token（用户需从 PC 访问）；默认不绑 0.0.0.0 |
| Q2 | 删除图片是否做软删除（回收站）？ | 做，7 天后清回收站；代价是双倍目录扫描 |
| Q3 | 抓拍冷却按全局还是按 track id？ | v1 全局；v2 再按 id（需维护 id→时间戳字典） |
| Q4 | 是否保留 `ROS1Transfer.py` 死代码？ | 保留不动（不影响运行），但在 README 标注"未启用" |
| Q5 | engine 导出用 ultralytics API 还是 `trtexec` 直调？ | ultralytics API（预处理/后处理一致，避免"能推不能检"） |
| Q6 | 是否需要 Web 端改 RTMP 地址/码率？ | v1 只读展示；可写列入 Could |

---

## 附录 A：worker 改造点清单

| 文件 | 位置 | 改动 | 风险 |
| --- | --- | --- | --- |
| `src/run_tracker_publish.py` | 主循环 | conf 热读；抓拍入队；推流分路开关判断；状态上报（写 `logs/worker_state.json` 供 console 读） | 中 |
| `src/RobotController/RobotController.py` | `Run()` | 暴露 `last_result`（max_conf / track_id / boxes），或在返回值附带元数据；控制律不动 | 中 |
| `src/RtmpPublisher/RtmpPublisher.py` | 类 | 惰性 start/stop；保留 `CheckError()`；补 EOS→NULL 关闭序列 | **高** |
| `src/RobotController/ROSTransfer/ROS2Transfer.py` | 类 | publisher 惰性创建/销毁 | 低 |
| `src/config_loader.py` | 新增 | mtime 轮询 + schema 校验 + 默认值合并 + 失败保持上一份 | 低 |
| `src/snapshot_writer.py` | 新增 | 队列消费者、UMat 处理、配额与保留期清理 | 低 |
| `src/export_engine.py` | 新增 | onnx → engine 子进程入口（被 console 调用） | 中 |
| `console/server.py` | 新增 | 标准库 HTTP 服务、REST、上传、token、限流 | 中 |
| `console/static/index.html` | 新增 | 单文件前端 | 低 |
| `console/systemd/lite3-yolo-console.service` | 新增 | 自启单元 | 低 |

## 附录 B：目录结构前后对比

```text
改前                              改后（新增项标注 +）
yolo8/
├── deploy/                       ├── console/          (+) 控制台
├── logs/                         ├── config/           (+) yolo8.json
├── model/                        ├── pic/              (+) 抓拍输出
├── note/                         ├── model/uploads/    (+) onnx 暂存
└── src/                          └── src/              (~) 改造 + 新增 3 个模块
```

## 附录 C：可复用资产（来自 M20 控制台经验）

1. 组件模式：`DeviceToggle`（`setX(目标值)`）、`SegmentedControl`、`CollapsibleSection`、状态徽标墙。
2. UI 铁律 ADR-020/021：composable 必须解构到顶层；拉流可见性 `flowWanted = active && pulled && !document.hidden`。
3. 部署脚本模式：`deploy/apply-dist.sh`（只换 dist、留 `.bak-<时间戳>`）。
4. 控制权归属 ADR-028：单 owner + 续约 + 安全指令豁免。
5. 验收方式：playwright 真机核对（M20 已固化流程）。
6. 后端改动后**必须真机 `curl /health` 确认**（Py3.8 注解坑，本机 3.13 测不出）。

---

*本文档为设计稿 v1，所有命令与代码均未在真机执行。评审通过后按 §10 分期实施，每期单独验收。*
