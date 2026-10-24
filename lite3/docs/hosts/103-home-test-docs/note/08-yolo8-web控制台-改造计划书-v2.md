# Lite3 yolo8 Web 控制台改造计划书 v2.1

| 项 | 值 |
| --- | --- |
| 文档版本 | **v2.1（决策定稿版，完整自包含，替代 v1 / v2）** |
| 文件名说明 | 沿用 `...-v2.md`（按指示在原计划书 v2 上完善），内部修订号 v2.1 |
| 日期 | 2026-10-22 |
| 状态 | 设计定稿，待批准实施；**本文不含任何已执行的真机改动** |
| 目标机 | Lite3 103 感知主机（`lite`，Jetson Xavier NX / aarch64 / Ubuntu 20.04 / eth0 `192.168.1.103`） |
| 作用对象 | `/home/test/yolo8`（YOLOv8 人体跟踪 + 双通路发布工程） |
| 上游参考 | `/home/ysc/lite_cog_ros2/track`（只读） |
| 本次裁决 | D1 监听开放局域网 · D2 软删除 · D3 冷却全局+按类别 · D4 删 ROS1 死代码 · D5 TRT API 导出 · **D6 RTSP 源与 RTMP 目标均可配** · D7 恢复旧笔记 · D8 类别清单表格输入 |
| 关联文档 | `note/部署笔记.md`、`note/双通路发布-避坑记录.md`（git 索引存在、磁盘缺失，P0 恢复） |
| 变更索引 | v1→v2 见 §14；v2→v2.1 见 §15 |

---

## 0. 结论摘要

1. **可行，且比 v2 更省事**。八项裁决全部落地；其中「监听开放局域网」把认证从"可选"提升为"必须"，新增 §5.11 / §6.5 两节专门设计。
2. **架构主线不变**：**双进程解耦**。推理进程 `yolo_worker` 只管帧循环；新增 `console` 只做管理；两者以 `config/yolo8.json` 为唯一运行期接口，mtime 轮询实现秒级热更新，**不重启、不重载模型**。
3. **v2.1 修正了 v2 的三处事实性问题**（均已真机复核）：
   - v2 称"conf 经 `model.track(**kwargs)` 逐次生效"——**实际是 `YoloWrapper.__init__` 读一次 `YOLO8_CONF`，`Track()` 用 `self.conf` 属性**。改造反而更简单：改属性即可，无需碰模型。
   - v2 称"必须 EOS→NULL 关闭"——**现状 `RtmpPublisher.Stop()` 是裸 `set_state(NULL)`**，EOS 是待补的改进项而非既有行为。
   - v2 未发现 **`run_tracker_publish.py` 里 `if err: break`**：RTMP 一路报错会**直接杀掉整个推理进程**（systemd 再拉起重付 35s 冷启动）。这与"分路独立、热开关"根本冲突，v2.1 列为必修（R11）。
4. **新增两项硬约束（真机实测）**：
   - 103 上 **`avdec_h264` 不存在**（无 `gst-libav`）⇒ 解码器**只能 `hw` 或 `auto`，没有软解回退**。因此"源编码不支持"必须在**写配置前**用 ffprobe 探明并拒绝，不能等运行时崩。
   - 103 **没有防火墙**（`ufw: command not found`，无 netfilter 规则管理）⇒ 绑 `0.0.0.0` 后同网段任意主机可达，认证与来源白名单是**唯一屏障**，不是"加固项"。
5. **一处误判澄清**：`gst-inspect-1.0 --exists` 在 GStreamer 1.16.3 下对 NVIDIA 插件误报 MISS；实测 Python 运行时注册表 **304 个插件**，`nvv4l2decoder` / `nvv4l2h264enc` / `rtspsrc` / `rtmpsink` / `flvmux` 全部可用，两条管线 `Gst.parse_launch()` 均成功。**结论：不需要 `GST_PLUGIN_PATH`，不要往 systemd 单元里加。**
6. **工作量**：约 **15 人日**（区间 12–18），6 期，每期独立上线、独立回滚。
7. **最大风险**：`R1 源码缺失`（git 对象完整，P0 一条命令恢复）；其次 `R11 RTMP 失败杀进程`、`R10 源不可达阻塞启动`。

---

## 1. 背景与目标

### 1.1 背景（2026-10-22 实测现状）

| 项 | 现状 | 影响 |
| --- | --- | --- |
| 服务状态 | `lite3-yolo-publish.service` / `lite3-yolo-rosbridge.service` 已 install 但 **disabled + inactive** | 现网不跑 YOLO |
| 进程 | `logs/yolo.pid = 69305` 已死；无相关进程 | 无法验证 |
| 日志 | `yolo-publish.log` 停在 2026-09-23 17:58，尾部 `no detections` | 无近期运行证据 |
| 自研源码 | `src/` 12 个 `.py` **本体全部不在磁盘**，只剩 `__pycache__/*.pyc` 与 3 个 `.bak-2026092x` | **当前无法启动** |
| 部署脚本 | `deploy/` 只剩 `yolo-publish.env.bak-20260923`，`lite3-publish-ctl.sh`（9759 B）等全缺 | 无配置入口 |
| 文档 | `note/` 仅含本计划书；git 索引另有 2 篇旧笔记（skip-worktree） | 经验待恢复 |
| 第三方 | `ultralytics 8.1.0` 源码树、`hub_sdk`、`yolov8n_arm.engine`（19.9 MB）完好 | 恢复后即可跑 |
| 磁盘 | `/` 117G 用 71G（64%），余 **42G** | 抓拍需配额 |
| 负载 | load 2.98 / 6 核；available 4925M；`lite3-monitor`、`lite3-ros-bridge` active | 控制台必须轻量、绑核 0-2 |
| 视频源 | `rtsp://192.168.1.120:8554/test` **TCP 可达**，ffprobe 实测 **h264 / 1280×720 / 30fps** | 可作为 P0 冒烟基线 |
| 推流目标 | `172.31.68.227:1936` **TCP 可达** | 推流链路具备条件 |
| 防火墙 | **无**（`ufw` 未安装，无持久化 netfilter） | 绑 0.0.0.0 需认证兜底 |
| 端口 | 8090 / 8554 / 9090 / 8002 / 43900 **均空闲** | console 用 8090 |

> 源码缺失被掩盖的原因：git 索引对这些路径打了 **`skip-worktree`（`S`）** 标志，`git status` 因此一路报"干净"。`git ls-files -v yolo8/src yolo8/deploy` 可见 29 个 `S` 文件。

### 1.2 目标

| 编号 | 目标 |
| --- | --- |
| G1 | Web 控制台随主机自启动，**局域网内可访问**（绑 `0.0.0.0`），带 token 认证 + 来源网段白名单 |
| G2 | 通过 Web 启停 yolo / rosbridge 服务 |
| G3 | 通过 Web **分路**开关推流：RTMP、ROS2 图像，各自独立、热生效、**单路故障不影响另一路** |
| G4 | 检测置信度阈值可配置（Web 与配置文件双入口同源），热生效 |
| G5 | 目标置信度 ≥ 阈值时把该帧存到 `pic/`，带全局+按类别冷却、配额、软删除 |
| G6 | 通过 Web 上传 onnx，异步导出 TensorRT engine，原子替换并支持重载 |
| **G7** | **视频源（RTSP 地址/传输协议/输出分辨率/文件回放）可在配置与 Web 中修改，保存前先探测连通性** |
| **G8** | **RTMP 推流目标地址与码率可在配置与 Web 中修改，保存前先探测、切换失败可回滚** |

### 1.3 非目标

- 不做训练、数据集管理、标注工具。
- **不做多路并发源**：同一时刻只有一个活跃源，但**源地址可随时更换**（G7）。
- **不做外网暴露**：不开端口映射、不做 NAT 穿透、不做多用户账号体系。
- **不改控制律**：`RobotController` 的 PD 跟踪逻辑冻结，只做钩子化改造。
- 不升级/替换 ultralytics 8.1.0 源码树（AGPL 传染面由 `.gitignore` 控制）。
- **不安装 `torch2trt`、不安装 pip 包**（103 无可用 pip 源，`pypi.org` 超时）。
- **不装 `gst-libav` 追求软解**（aarch64 需源码编译，收益为零：源固定为 H.264，硬解已足够）。

---

## 2. 环境核查结论（全部 2026-10-22 真实命令验证）

| 类别 | 核查结果 | 对设计的影响 |
| --- | --- | --- |
| Python | `/usr/bin/python3` → 3.8.10 ✓ | unit 用绝对路径；禁 3.9+ 语法 |
| cv2 | **4.9.0**，位于 `/home/ysc/.local/lib/python3.8/site-packages/cv2`；`GStreamer: NO`、`FFMPEG: YES` | **采集不走 cv2**，走 PyGObject；cv2 只负责画框/编码/写盘 |
| PyGObject | `gi` + `Gst 1.0` **可用** ✓ | 采集与推流均可用 `Gst.parse_launch` |
| GStreamer | **1.16.3**，注册表 **304 个插件**；`nvv4l2decoder`/`nvv4l2h264enc`/`nvv4l2conv`/`rtspsrc`/`rtmpsink`/`flvmux`/`rtph264depay`/`rtph265depay`/`h264parse`/`h265parse`/`filesrc`/`qtdemux`/`videoscale`/`videorate`/`fakesink` **全 OK** | 编解码链与源/目标可配均有元件支撑 |
| **软解** | `avdec_h264` **MISS**（无 `gst-libav`）、`openh264dec` MISS | **`decoder` 只允许 `hw`/`auto`**；不支持软解回退，须前置探测编码 |
| `GST_PLUGIN_PATH` | 未设置，且**不需要**（实测 `Gst.Registry` 全量可见） | systemd 单元**不要**加该变量；`gst-inspect --exists` 的 MISS 是误报 |
| appsink | `try-pull-sample` 信号**可用**（id=26）；`new-sample`/`eos`/`max-buffers`/`drop`/`emit-signals` 齐备 | 可用 `try-pull-sample(timeout)` 替代**会永久阻塞**的 `pull-sample` |
| tensorrt | **8.5.2.2**（Python 包 + `/usr/src/tensorrt/bin/trtexec`）✓ | engine 构建走 TRT Python API |
| onnx / onnxruntime | 1.15.0 / 1.15.1 ✓ | 上传校验与模型检查可用 |
| torch | 2.1.0a0+41361538.nv23.06 ✓ | ultralytics 运行依赖 |
| torch2trt | **不存在** | 不影响（TRT API 路线）；**禁止尝试 pip 安装** |
| 工具链 | `/usr/bin/ffprobe`、`ffmpeg`、`curl`、`wget` **全有** ✓ | 连通性预检与验收可用现成工具 |
| 网络 | eth0 `192.168.1.103/24`；另有 `docker0 172.17.0.1/16` | 绑 0.0.0.0 会同时监听 docker 网桥 ⇒ 来源白名单必须包含 CIDR 校验 |
| 防火墙 | `ufw` **未安装**；无 netfilter 持久化 | 无系统级屏障，认证是唯一屏障 |
| 源可达性 | `192.168.1.120:8554` TCP OK；ffprobe：**h264 / 1280×720 / 30fps** | P0 冒烟基线；输出需 `videoscale` 到 640×360 |
| 目标可达性 | `172.31.68.227:1936` TCP OK | 可用 TCP 预检代替"盲推" |
| 端口 | 8090 无监听 ✓ | console 绑 8090 |
| 磁盘 | 117G / 已用 71G / **余 42G** | 500 张/天 × 7 天 ≈ 1.5 GB，安全 |
| git 对象 | `cat-file -e` 六路径全 OK；`src`+`deploy` 29 个文件均在索引 | P0 恢复可靠 |
| `.gitignore` | 未覆盖 `pic/`、`model/uploads/`、`config/yolo8.json`（含访问令牌） | P5 补规则（§12）；`console/token` 文件机制已废弃（见 §6.5 与 §17.1） |

---

## 3. 需求清单（MoSCoW，按 v2.1 裁决更新）

| 优先级 | 需求 |
| --- | --- |
| **Must** | G1 自启动 + 局域网访问 + token/CIDR、G2 服务启停、G3 分路推流热开关、G4 阈值可配、G5 抓拍存 pic/、**G7 视频源可配**、**G8 推流目标可配** |
| **Should** | 抓拍浏览/下载/删除/恢复、状态面板（fps/推理 ms/源状态/流错误/CPU/内存/磁盘）、日志 tail、立即抓拍、连通性测试按钮 |
| **Could** | 录制短视频、多 engine 管理、sparkline 历史曲线、MJPEG 网页实时预览、探测源时抓一帧缩略图 |
| **Won't** | 训练、多路并发源、外网暴露、多用户账号、控制律修改、ultralytics 升级、torch2trt、gst-libav 软解 |

---

## 4. 总体架构

### 4.1 双进程解耦（含可配源与目标）

```text
                     ┌──────────────── 配置唯一入口 ────────────────┐
                     │  config/yolo8.json  (mtime 轮询，≤1s 生效)    │
                     └───────▲──────────────────────────┬───────────┘
                             │ 写(原子+校验+备份)        │ 读
  浏览器 / PC                │                          ▼
  http://192.168.1.103:8090  │              ┌───────────────────────────────┐
        │                    │              │ yolo_worker（改造后）          │
        ▼                    │              │  · 源管线（可重建）            │
  ┌──────────────────┐       │              │    rtspsrc/file → nvv4l2decoder│
  │ console (8090)   │───────┘              │    → videoscale → appsink      │
  │ · token + CIDR   │                      │  · YOLOv8n TRT 推理            │
  │ · CPUAffinity=0-2│──► lite3-publish-ctl.sh（启停，复用）
  │ · 审计/限流      │──► model/uploads ─► export_engine.py（TRT API）
  └──────────────────┘                      │  · 抓拍队列 → pic/             │
        ▲                                   │  · 每 250ms 写 worker_state.json│
        └──────── 读 logs/worker_state.json ┘                              │
                                            │  · RTMP（可重建，失败降级）    │
                                            │  · ROS2 图像（惰性创建）       │
                                            └───────────────────────────────┘
  源：rtsp://192.168.1.120:8554/test（可换）      目标：rtmp://172.31.68.227:1936/live/lite3_yolo（可换）
```

### 4.2 为什么这样切

- **不在 worker 内嵌 Web 框架**：`ThreadingHTTPServer` 与推理同进程会争 GIL，直接吃掉本就不富裕的帧率余量。
- **"配置即接口"**：worker 不监听任何端口（攻击面最小、无并发问题），每秒查一次 `config.json` 的 mtime。控制面只改文件，双方零 IPC。
- **状态上行用文件**：worker 每 250ms 原子写 `logs/worker_state.json`（tmp + `os.replace`），console 只读。worker 崩了仍能读到最后一帧状态。
- **console 独立进程**：崩了不影响推流；CPU 绑 0-2 避开 cpu5-7 的 SCHED_FIFO 实时线程（hsLidar prio54、lio_ddsnode prio64，无条件抢占）。
- **源与目标都必须"可重建"而非"可改属性"**：GStreamer 管线的 location/编码参数不是运行时可改的 element 属性（`rtspsrc` 可改 location 但不会干净重建会话），因此设计上把它们当作**整条管线重建**，并配套"先探测、后切换、失败回滚"的三段式。

---

## 5. 功能详细设计

### 5.1 服务生命周期管理（G2）——复用既有脚本

- **console 不实现启停逻辑**，只 `subprocess` 调 `deploy/lite3-publish-ctl.sh`（P0 恢复后可用，9759 B）：

  ```text
  lite3-publish-ctl.sh start|stop|restart|status|logs  <yolo|rosbridge|all>
  ```

- 该脚本已内置全部正确行为（真机核实）：
  - **双模判定**（`any_systemd()`：unit 已安装 **且** `systemctl is-enabled` 成功才走 systemctl，否则 PID 文件直管、**免 sudo**）；
  - 启动逻辑唯一（`scripts/run-yolo-publish.sh`，systemd 与手工共用同一份，末尾 `exec` 成 python 主进程）；
  - 幂等、B1–B7 各坑已修（`targets_of()` 命令替换内 `exit` 不传播等）。
- console 侧只做：解析返回码/stdout → 映射状态 → 写审计日志。
- **`mode` 子命令弃用**（v2.1 新增）：其实现是 `sed -i s/^YOLO8_PUBLISH_MODE=.*/.../` 改 env 文件，与 config.json 形成双写。P2 起 `mode` 仅打印"已弃用，请改 config.json 的 stream.rtmp / stream.ros2_image"，不再改文件。
- **sudoers 白名单降级为可选项**：默认 unit 为 disabled → PID 直管免 sudo；仅当用户 `enable` 常驻后才需要（放行本工程 3 个 unit，禁通配）：

  ```text
  ysc ALL=(root) NOPASSWD: /bin/systemctl start lite3-yolo-publish.service, \
      /bin/systemctl stop lite3-yolo-publish.service, \
      /bin/systemctl restart lite3-yolo-publish.service, \
      /bin/systemctl start lite3-yolo-rosbridge.service, \
      /bin/systemctl stop lite3-yolo-rosbridge.service, \
      /bin/systemctl restart lite3-yolo-rosbridge.service
  ```

### 5.2 推流分路热切换（G3，含 R11 修复）

**现状缺陷（v2.1 新发现）**：`run_tracker_publish.py` 主循环内

```python
if err:
    print('[ABORT] RTMP 总线报错，停止推流')
    break          # ← 整个进程退出，ROS2 与抓拍一起死；systemd Restart=always 再起重付 35s
```

**改造为故障隔离**：

| 项 | 设计 |
| --- | --- |
| RTMP 出错 | 只销毁 RTMP publisher → 状态置 `stream.rtmp_state=error` → 指数退避重连（1s→2s→…→30s 封顶）→ **主循环继续** |
| 退避复位 | 连续正常推送满 10s 才清零退避计数（防抖动式重启风暴） |
| 用户显式关闭 | 写 `stream.rtmp=false` 才停止重连（意图与运行态分离：`enabled` vs `state`） |
| 对象生命周期 | 惰性创建/销毁；关闭时序 `src.emit("end-of-stream")` → `bus.timed_pop_filtered(2s, EOS)` → `set_state(NULL)` → `unref`（现状 `Stop()` 裸 `set_state(NULL)`，属待补） |
| ROS2 侧 | `publisher`/`node` 惰性创建与 `destroy_node`，同理不受 RTMP 影响 |
| 状态机 | `idle → starting → running → stopping → idle`，异常进 `error`；前端只读状态，不直接下指令 |
| 生效延迟 | ≤ 1s（mtime 轮询粒度） |

### 5.3 置信度阈值热更新（G4，含 v2 事实修正）

**现状（真机读码）**：

```python
class YoloWrapper:
    def __init__(self):
        self.model = YOLO('../model/yolov8n_arm.engine')
        self.conf = float(os.environ.get('YOLO8_CONF', '0.5'))   # ← 只在启动时读一次
    def Track(self, img):
        return self.model.track(img, persist=True, classes=[CocoTypeId.kPerson], conf=self.conf)
```

⇒ **热更新不需要重建模型、不需要动 ultralytics**，只需在每帧前同步属性：

```python
if cfg.conf_threshold != yolo.conf:
    yolo.conf = cfg.conf_threshold            # 1 次属性写，成本可忽略
```

- 取值约束 `0.05 – 0.95`，步进 `0.05`；越界由服务端返回 400，**不静默夹取**（吸取 M20 休眠 Time 被静默夹取的教训）。
- 双入口同源：Web `PUT /api/config` 与手改 `config.json` 写同一文件，`updated_at` 记录来源。
- 附带的 `detect.classes`（默认 `[0]` = person）同样可配，避免以后改类别要动源码。

### 5.4 高置信帧抓拍（G5）

| 子项 | 设计 |
| --- | --- |
| 触发条件 | `max(results[0].boxes.conf) >= conf_threshold` 且 `snapshot.enabled` |
| 挂点 | `draw_annotated()` 之前（要存**原始帧**还是**标注帧**由 `snapshot.save_annotated` 决定，默认标注帧便于人工核对） |
| **缓冲语义（关键）** | `GetFrame()` 返回的数组由采集线程复用 ⇒ **入队前必须 `frame.copy()`**，否则写盘的是后续被覆写的缓冲（静默数据错误，肉眼极难发现） |
| 线程模型 | 主循环只 `queue.put_nowait()`（有界 64，满则丢弃并 `dropped++`）；**独立 daemon 线程**做 `cv2.imencode/imwrite`（JPEG 编码 10–30 ms） |
| UMat | 绘制路径可能产出 `cv2.UMat`，写盘前统一 `frame.get()` |
| 冷却 | **全局 2000 ms**（`cooldown_ms`）+ **按类别 1000 ms**（`cooldown_ms_per_class`），两者 AND；不按 track id（列为 v3） |
| 文件命名 | `YYYYmmddTHHMMSS_mmm_c087_id3.jpg`（c=置信度千分位） |
| 元数据 | `save_meta=true` 时同目录写 `.json` sidecar（框坐标、类别、推理耗时、帧号、阈值快照） |
| 配额 | 500 张/天 + 保留 7 天；启动时与每小时各扫一次，超限删最旧；**`disk_avail < 5G` 直接停抓拍并告警** |
| 目录 | `/home/test/yolo8/pic/YYYYMMDD/`（P5 加入 `.gitignore`） |

### 5.5 图片管理（含软删除，D2）

| 接口 | 行为 |
| --- | --- |
| `GET /api/pics?date=&page=&size=` | 分页（默认 24/页，时间倒序），返回文件名/大小/时间/置信度/类别 |
| `GET /api/pics/<date>/<name>` | 原图 |
| `GET /api/pics/<date>/<name>?thumb=1` | 缩略图（cv2 缩到宽 320，缓存 `pic/.thumbs/`） |
| `DELETE` | **软删除**：`os.replace` 到 `pic/.trash/<YYYYMMDD>/`（同分区，原子，不复制） |
| `POST /api/pics/trash/<name>/restore` | 从回收站还原到原日期目录 |
| `GET /api/pics/trash` | 回收站列表；`retention` 任务顺带清理 `.trash` 中 >7 天的项 |
| 安全 | 文件名白名单 `^[0-9A-Za-z._-]+$` + `os.path.realpath` containment 检查（防 `../` 穿越） |

#### 5.5.1 抓拍时间轴预览（P3，2026-10-22 用户确认新增）

用户诉求：「在控制台预览保存的图片，且能通过**时间戳进度条拖动**查看」。形态定为**时间轴拖动 + 缩略图**（D10）。

| 子项 | 设计 |
| --- | --- |
| 索引来源 | 文件名自带毫秒时间戳（`YYYYmmddTHHMMSS_mmm_c087_id3.jpg`）⇒ **不额外维护索引文件**；服务端扫 `pic/YYYYMMDD/` 解析文件名建时间轴，解析失败按 `st_mtime` 兜底并标 `ts_source=mtime` |
| 新接口 | `GET /api/pics/timeline?date=YYYYMMDD` → 升序 `[{ts_ms,name,conf,cls,size}]`（**不含框坐标**，框走 meta sidecar 按需取）；按 date 缓存，目录 mtime 变化即失效；单日 >5000 条时返回等距抽稀刻度 + `total`，详情按需取 |
| **进度条语义（关键）** | 值 = **真实时间轴**（00:00:00–23:59:59 线性映射），**不是"第 N 张"等距** ⇒ 稀疏时段不会被误读为连续发生；拖动时**吸附到时间上最近的一张**，标题显示 `HH:MM:SS.mmm` |
| 取舍说明 | 「第 N 张等距」实现最简，但抓拍受冷却（D3）约束天然稀疏，等距会让拖动在无人时段"空跑"；真实时间轴贴合"按时间找画面"的诉求，代价是必须做吸附 |
| 密度带 | 进度条下方把一天切 240 槽（6 min/槽），有抓拍的槽染色 ⇒ 一眼看出目标在哪些时段出现；点击密度带直接跳到该槽首帧 |
| 缩略图 | `?thumb=1`（宽 320，`pic/.thumbs/` 缓存）；拖动中**预取当前 ±3 张**保证视觉连续 |
| 加载策略 | 拖动中只换缩略图；**停止 150 ms 防抖**后才拉原图（防拖动过程狂拉大图打满带宽） |
| 键盘 | ←/→ ±1 帧；Shift+←/→ ±10 帧 |
| 空态 | 当日无抓拍 → 「今日暂无抓拍」+ 一键跳到最近有抓拍的日期 |
| 删除 | 软删除（D2）二次确认；删后**重拉 timeline**，时间轴与密度带即时更新 |
| 安全 | 沿用 §5.5：文件名白名单 + `realpath` containment |

> 与 Q10 的区别：**时间轴预览针对已保存的抓拍**（离线回看）；Q10 的 MJPEG 是**实时画面**，仍按原裁决暂不做。

### 5.6 onnx 上传与 engine 导出（G6，沿用 v2 结论）

#### 5.6.1 为什么不能用 ultralytics 的 export

**`YOLO(onnx).export(format="engine")` 必然失败**（真机读码证实）：

```text
Exporter.__call__ → export_engine() → export_onnx() → torch.onnx.export(self.model, ...)
```

`YOLO("x.onnx")` 加载后 `self.model` 是 onnxruntime InferenceSession，不是 torch Module，`torch.onnx.export` 直接报错。且 `torch2trt` 在 103 上不存在。

#### 5.6.2 正确路线：TRT Python API + 手工复刻文件头

真机解析现有 `yolov8n_arm.engine`（头 4 字节 `4c 06 00 00` = 1612）与 `ultralytics/nn/autobackend.py:213` 证实文件结构：

```text
[4 字节小端 meta_len][meta_len 字节 JSON][TRT plan 序列化数据]
```

`autobackend.py:334-345` 要求 metadata **必须含 5 个 key**（缺一 KeyError）：`stride`、`task`、`batch`、`imgsz`、`names`。

真机 metadata 模板（来自现有 engine）：

```json
{
  "description": "Ultralytics YOLOv8n model trained on coco.yaml",
  "author": "Ultralytics",
  "license": "AGPL-3.0 https://ultralytics.com/license",
  "date": "2024-01-08T14:47:45.754312",
  "version": "8.0.234",
  "stride": 32, "task": "detect", "batch": 1, "imgsz": [640, 640],
  "names": {"0": "person", "1": "bicycle", "...": "..."}
}
```

`export_engine.py` 核心（Py3.8 兼容）：

```python
import json, os
import tensorrt as trt

TRT_LOGGER = trt.Logger(trt.Logger.INFO)

def build_engine(onnx_path, out_path, meta, workspace_gb=1, half=True):
    """onnx -> ultralytics 兼容 engine（带 metadata 头）。workspace 限 1GB：NX 仅 6.7G 内存。"""
    builder = trt.Builder(TRT_LOGGER)
    config = builder.create_builder_config()
    try:
        config.max_workspace_size = workspace_gb << 30          # 8.5 仍接受
    except Exception:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_gb << 30)
    flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(flag)
    parser = trt.OnnxParser(network, TRT_LOGGER)
    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            raise RuntimeError("ONNX parse failed: " + str(parser.get_error(0)))
    if half and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    blob = builder.build_engine(network, config).serialize()
    payload = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as t:
        t.write(len(payload).to_bytes(4, byteorder="little", signed=True))
        t.write(payload); t.write(blob)
    os.replace(tmp, out_path)                                   # 原子替换
    return out_path

def make_meta(names, imgsz=(640, 640), stride=32, task="detect"):
    if isinstance(names, (list, tuple)):
        names = {str(i): str(n) for i, n in enumerate(names)}
    return {"description": "Lite3 yolo8 console upload", "author": "lite3-console",
            "version": "1.0.0", "stride": int(stride), "task": task, "batch": 1,
            "imgsz": [int(imgsz[0]), int(imgsz[1])], "names": names}
```

#### 5.6.3 类别清单（D8 裁决）

- **主输入**：结构化表格（前端按 onnx 探测出的类别数生成 N 行输入框）；
- **一键预填**：类别数 = 80 时提供"填入 COCO 80 类"按钮（`CocoTypeId.py` 已内置名单，直接复用）；
- **兼容输入**：同时上传 `names.json`（`["person","dog"]` 或 `{"0":"person"}`）可整体覆盖表格；
- **校验**：类别数必须与 onnx 输出维度匹配（`onnx` 包读 `graph.output` 末维 / `4 + 5*K` 粗估；不符则拒绝并提示差值）；
- `person` 不在索引 0 时**告警但允许**（跟踪目标由 `detect.classes` 决定，用户自负责）。

#### 5.6.4 任务状态机

```text
idle → uploaded → exporting(读子进程 stdout 环形缓冲) → exported
     → activating(os.replace 原子替换，旧 engine 留 .bak-<ts>) → active
任意态 → failed（删 tmp、保留旧 engine、错误写 logs/engine-export.log）
```

- 单任务队列（同时只允许一个导出）；超时 10 min 强杀。
- `model.pending_reload` 写 config，worker 在**帧边界**重建 YOLO 实例（阻塞 2–5s），期间丢帧但不崩。
- **替换前必须试加载**：新 engine 先 `YOLO(path)` 建一次再替换（避免"换上去起不来"）。

### 5.7 状态监控

- **worker → console**：每 250 ms 原子写 `logs/worker_state.json`（字段见 §6.3）。
- **console 自身**：`/proc/self/status`（RSS）、`os.getloadavg()`、`shutil.disk_usage("/")`。
- **host**：`/proc/meminfo`（MemAvailable）、`/proc/loadavg`。无 psutil，全部标准库。
- 前端 1 s 轮询 `GET /api/state`（**不用 WebSocket**，零依赖）；环形 300 点画 sparkline。
- `GET /api/logs?lines=200` tail 日志（复用 B1 坑：`tail_log()` 兜底）。
- **首帧等待不空转**：现状主循环 `if bgr_frame is None: continue` 是**忙等**（启动期 35s 烧满一个核）。改造为 `GetFrame(timeout=0.5)` 内部 `threading.Event.wait(timeout)`。

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
# 监听地址来自 config 的 console.bind（默认 0.0.0.0 = 局域网可访问）
ExecStart=/usr/bin/python3 -u server.py
CPUAffinity=0-2
Restart=always
RestartSec=5
StandardOutput=append:/home/test/yolo8/logs/console.log
StandardError=append:/home/test/yolo8/logs/console.log

[Install]
WantedBy=multi-user.target
```

- 默认只 `enable` 控制台；**yolo-publish 维持"默认不启用"**的既有决策。
- 端口规划：console **8090**（已核实空闲）；不复用 9090（rosbridge）、8002/43900（ros-bridge）。
- **不加 `GST_PLUGIN_PATH`**（§2 已实测不需要，加了反而可能遮蔽默认路径）。

### 5.9 视频源可配置（G7，v2.1 新增）

#### 5.9.1 配置项

```json
"source": {
  "type": "rtsp",
  "rtsp_url": "rtsp://192.168.1.120:8554/test",
  "file_path": "",
  "codec": "h264",
  "decoder": "hw",
  "transport": "udp",
  "latency_ms": 200,
  "out_width": 640,
  "out_height": 360,
  "read_timeout_ms": 5000,
  "reconnect": {"enabled": true, "backoff_ms": 1000, "backoff_max_ms": 30000}
}
```

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `type` | `rtsp` / `file` | `file` 为调试回放（本地 mp4/h264），生产用 `rtsp` |
| `codec` | `h264`（默认）/ `h265` / `auto` | 与源编码一致时用显式链，最快、最确定 |
| `decoder` | `hw`（默认）/ `auto` | **无 `sw`**：`avdec_h264` 缺失（§2）；填 `sw` 会被拒绝并提示改用 `auto` |
| `transport` | `udp`（保持现状）/ `tcp` | `tcp` 抗丢包但延迟略高；跨交换机/无线建议 `tcp` |
| `latency_ms` | 默认 200 | **现状未设置 ⇒ GStreamer 默认 2000 ms**，这是端到端延迟的大头，改 200 显著降延时 |
| `out_width/height` | 默认 640×360 | 下游（推理前处理、抓拍、推流）以此为准；源 1280×720 由 `videoscale` 缩放 |

#### 5.9.2 管线模板

```python
def build_source_pipeline(src):
    w, h = int(src["out_width"]), int(src["out_height"])
    if src["type"] == "file":
        head = 'filesrc location="%s"' % src["file_path"]
        mid = "decodebin"
    else:
        head = ('rtspsrc location="%s" protocols=%s latency=%d drop-on-latency=true'
                % (src["rtsp_url"], src.get("transport", "udp"),
                   int(src.get("latency_ms", 200))))
        codec, dec = src.get("codec", "h264"), src.get("decoder", "hw")
        if dec == "auto":
            mid = "decodebin"
        elif codec == "h265":
            mid = "rtph265depay ! h265parse config-interval=1 ! nvv4l2decoder"
        else:
            mid = "rtph264depay ! h264parse config-interval=1 ! nvv4l2decoder"
    tail = (" ! nvvidconv ! video/x-raw,format=BGRx"
            " ! videoscale ! video/x-raw,width=%d,height=%d"
            " ! videoconvert ! video/x-raw,format=BGR"
            " ! queue max-size-buffers=5 max-size-bytes=0 "
            "max-size-time=50000000 leaky=downstream"
            " ! appsink name=sink sync=false max-buffers=1 drop=1" % (w, h))
    return head + " ! " + mid + tail
```

> 与现状管线（`GStreamerWrapper.py:24` 硬编码）的差异：去掉了固定 `location`、可切 `protocols`/`latency`、`file` 走 `decodebin`、输出尺寸参数化。**编码链本身未变**，属于低风险替换。

#### 5.9.3 启动阻塞修复（R10）

**现状缺陷**：`__init__` 里同步执行

```python
sample = self.sink.emit('pull-sample')     # ← 源不可达时永久阻塞，进程卡死且无日志
```

**改造**（利用实测可用的 `try-pull-sample`）：

```python
def _wait_first_sample(self, timeout_ms):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        sample = self.sink.emit('try-pull-sample', int(0.2 * Gst.SECOND))
        if sample is not None:
            caps = sample.get_caps().get_structure(0)
            return caps.get_value('width'), caps.get_value('height')
        bus = self.pipeline.get_bus()
        if bus.have_pending():
            msg = bus.pop()
            if msg.type == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                raise SourceUnavailable(str(err))
    raise SourceUnavailable('first frame timeout %d ms' % timeout_ms)
```

- 首帧超时（默认 5000 ms）→ 抛 `SourceUnavailable` → worker 进入 `reconnecting`，**不退出进程**；
- `GetFrame(timeout)` 同样用 `try-pull-sample`，杜绝忙等。

#### 5.9.4 切换流程（先验后写）

```text
[Web 点保存]
   │
   ├─ 1. 服务端 schema 校验（type/codec/decoder/尺寸/冷却…）
   ├─ 2. 连通性探测（ffprobe，≤10s；file 类型改为抽 1 帧）
   │     失败 → 400 + 具体错误，**不写 config，不动现网**
   ├─ 3. 原子写 config（tmp+rename，备份 config.json.bak-<ts>，记 last_good_source）
   ├─ 4. worker 检测 mtime 变化（≤1s）
   │     ├─ 停旧管线（set NULL，≤2s）
   │     ├─ 建新管线并等首帧（≤5s）
   │     ├─ 成功 → source.state=running，写回 worker_state
   │     └─ 失败 → 用 last_good_source 重建（≤5s）→ source.state=failed + err
   └─ 5. 前端 1s 轮询看到结果；失败时显示"回滚到上一个可用源"按钮
```

**为什么必须前置探测**：worker 重建失败时流会中断数秒，且如果新源本身不可用，会陷入"永远重连"。ffprobe 探测成本 1–2 s，能挡掉 95% 的填错（IP、端口、路径、编码不支持）。

**探测器实现**（已实测：返回 h264/1280×720/30fps，exit 0）：

```python
def probe_rtsp(url, transport="udp", timeout_s=10):
    cmd = ["ffprobe", "-v", "error", "-rtsp_transport", transport,
           "-select_streams", "v:0",
           "-show_entries", "stream=codec_name,width,height,avg_frame_rate",
           "-of", "json", url]
    try:
        out = subprocess.check_output(cmd, timeout=timeout_s, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return {"ok": False, "err": (e.output or b"").decode("utf-8", "replace")[:300]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "err": "probe timeout %ss" % timeout_s}
    st = json.loads(out.decode("utf-8", "replace"))["streams"][0]
    codec = st.get("codec_name")
    hint = ""
    if codec not in ("h264", "hevc"):
        hint = "编码 %s 无软解可用（avdec 缺失），仅支持 h264/h265" % codec
    return {"ok": True, "codec": codec, "width": st.get("width"),
            "height": st.get("height"), "fps": st.get("avg_frame_rate"), "hint": hint}
```

- **凭据脱敏**：日志/审计中 `rtsp://user:pass@host` 一律写成 `rtsp://user:***@host`；`config.json` 权限 0600。
- **探测不留副作用**：ffprobe 是一次独立 RTSP 客户端，mediamtx 支持多客户端；结束后连接即断，不影响 worker 现有拉流。

### 5.10 RTMP 推流目标可配置（G8，v2.1 新增）

#### 5.10.1 配置项

```json
"stream": {
  "rtmp": true,
  "rtmp_url": "rtmp://172.31.68.227:1936/live/lite3_yolo",
  "rtmp_bitrate": 1000000,
  "rtmp_sink": "rtmpsink",
  "out_width": 640, "out_height": 360, "fps": 30,
  "ros2_image": true, "ros2_every": 3,
  "reconnect": {"backoff_ms": 1000, "backoff_max_ms": 30000}
}
```

- 编码链维持现状（真机验证可用）：`appsrc(BGR) → videoconvert → I420 → nvvidconv → NVMM/NV12 → nvv4l2h264enc → h264parse → flvmux(streamable) → rtmpsink location="URL live=1"`。
- `rtmp_sink=fakesink` 用于本地自检（不对外推流），沿用现有能力。
- **`rtmpsink` 的 location 必须整体加引号**（PyGObject 的 `gst_parse` 按空格切 token，`location=URL live=1` 会被解析成给元素设 `live` 属性并报 `no property "live"`）。这条坑已写在现有代码注释里，改造时必须保留。

#### 5.10.2 URL 合法性校验（四条，硬性）

1. scheme ∈ {`rtmp`, `rtmps`}，且形如 `rtmp://host[:port]/app/stream`；
2. **拒绝 `rtmp://.../live/lite3`**——那是 120 摄像头转发占用的流名，同流名会互踢（现有 env 注释明确警告）；
3. 拒绝含空白/换行/引号的值（防管线注入）；
4. host 必须能 TCP 连通（端口默认 1936，可显式指定），3 s 超时。

#### 5.10.3 切换策略（按变更类型分两种）

| 变更类型 | 策略 | 理由 |
| --- | --- | --- |
| **URL 变更为不同流名** | **双缓冲**：先建新 publisher → 观察 bus 3 s 无 error → 再 EOS 停旧 | 新旧互不冲突（不同 stream key），失败可无损回滚 |
| **同 URL 改码率/分辨率/帧率** | **先停后建**：EOS→NULL→新建→失败则退避重试 | 同 stream key 双推会互相踢流，不能并存 |
| **关闭推流** | EOS → 等 EOS 消息（≤2 s）→ NULL → 释放 | 裸 `set_state(NULL)` 会漏 GStreamer 资源与 fd |

```python
def eos_stop(self, timeout_s=2):
    self.src.emit("end-of-stream")
    bus = self.pipeline.get_bus()
    bus.timed_pop_filtered(int(timeout_s * Gst.SECOND), Gst.MessageType.EOS)
    self.pipeline.set_state(Gst.State.NULL)
    self.pipeline = None
```

#### 5.10.4 预检与"深度探测"

| 级别 | 动作 | 默认 |
| --- | --- | --- |
| L1 TCP 预检 | `socket.create_connection((host, port), 3)` | **总是执行**，失败拒绝保存 |
| L2 推送自检 | `gst-launch-1.0 videotestsrc num-buffers=30 ! ... ! rtmpsink location=...` 推 1 s 彩条 | **手动按钮**，UI 明示"会短暂覆盖目标画面 1 秒" |
| L3 流可读校验 | 推流后用 `ffprobe` 读回（需服务器支持读） | 不做（SRS 读地址与推地址不同，收益低） |

- 运行时错误处理同 §5.2：**降级 + 退避，绝不 `break` 退出进程**。
- 状态呈现：`stream.rtmp_state ∈ {idle,starting,running,error,disabled}` + `rtmp_err` 最近一条 bus 错误（截断 300 字）。

### 5.11 配置优先级与双源治理（v2.1 新增，重要）

现状存在**两个配置源**：`deploy/yolo-publish.env`（env 变量）与即将新增的 `config/yolo8.json`。不定规矩必然出现"改了 Web 没生效"。

**三层优先级**（高 → 低）：

```text
config/yolo8.json  >  deploy/yolo-publish.env（仅作 fallback）  >  代码默认值
```

**职责切分**：

| 归属 | 键 |
| --- | --- |
| **config.json（运行期可热改）** | `conf_threshold`、`detect.classes`、`source.*`、`stream.rtmp*`、`stream.ros2_image`、`stream.ros2_every`、`snapshot.*`、`model.*`、`pic_dir` |
| **env（启动期静态，改了要重启）** | `HEADLESS`、`YOLO8_STATUS_INTERVAL`、`YOLO8_IMAGE_TOPIC`、`YOLO8_IMAGE_QOS`、`YOLO8_JPEG_QUALITY`、`YOLO8_FRAME_ID`、`ROSBRIDGE_PORT` |
| **env 中废弃（仅兼容回退）** | `YOLO8_PUBLISH_MODE`、`YOLO8_ENABLE_RTMP`、`YOLO8_ENABLE_ROS2_IMAGE`、`YOLO8_RTMP_URL`、`YOLO8_RTMP_BITRATE`、`YOLO8_CONF` |

**落地动作（P0/P2）**：

1. 新增 `deploy/migrate-env-to-config.py`（幂等）：读 env → 生成 `config/yolo8.json`（已存在则跳过）→ 把 env 中已迁移键**注释掉**并加一行说明 `# 已迁移至 config/yolo8.json，改这里不再生效`。
2. 改造 `run-yolo-publish.sh`：删除 `case "$YOLO8_PUBLISH_MODE"` 的模式推导块，改为仅打印提示；不再 `export` 已迁移键。
3. 改造 `lite3-publish-ctl.sh mode`：打印弃用提示，不写文件（保留入口避免旧脚本报错）。
4. worker 启动时：若 `config/yolo8.json` 不存在 → 自动生成默认文件（内容取自 env 回退值）；存在但解析失败 → **保持上一次有效内存配置并告警**，绝不带病运行。
5. **P0 实测偏差（已按此执行）**：env 的已迁移键**保持生效、不注释**。原因：worker 要到 P2 才消费 config，提前注释会让 `YOLO8_CONF=0.4` 静默失效、阈值回退到代码默认 0.5——这正是双源治理要防的坑。替代做法：`deploy/add-env-notice.py` 在 env 顶部插入分层说明（备份 `.bak-p0-notice`）；P2 接入 worker 时再统一注释。

---

## 6. 接口设计

### 6.1 `config/yolo8.json`（唯一运行时配置，schema v2）

```json
{
  "version": 2,
  "console": {
    "bind": "0.0.0.0",
    "port": 8090,
    "allowed_cidrs": ["192.168.1.0/24"],
    "session_ttl_s": 43200,
    "token": "jack1419"
  },
  "source": {
    "type": "rtsp",
    "rtsp_url": "rtsp://192.168.1.120:8554/test",
    "file_path": "",
    "codec": "h264",
    "decoder": "hw",
    "transport": "udp",
    "latency_ms": 200,
    "out_width": 640,
    "out_height": 360,
    "read_timeout_ms": 5000,
    "reconnect": {"enabled": true, "backoff_ms": 1000, "backoff_max_ms": 30000}
  },
  "detect": {"conf_threshold": 0.4, "classes": [0]},
  "snapshot": {
    "enabled": true, "cooldown_ms": 2000, "cooldown_ms_per_class": 1000,
    "daily_quota": 500, "retention_days": 7, "min_free_gb": 5,
    "save_meta": true, "save_annotated": true
  },
  "stream": {
    "rtmp": true,
    "rtmp_url": "rtmp://172.31.68.227:1936/live/lite3_yolo",
    "rtmp_bitrate": 1000000,
    "rtmp_sink": "rtmpsink",
    "out_width": 640, "out_height": 360, "fps": 30,
    "ros2_image": true, "ros2_every": 3,
    "reconnect": {"backoff_ms": 1000, "backoff_max_ms": 30000}
  },
  "model": {"engine": "../model/yolov8n_arm.engine", "pending_reload": false},
  "pic_dir": "../pic",
  "trash_retention_days": 7,
  "updated_at": "2026-10-22T02:00:00+08:00"
}
```

规则：未知字段忽略；缺失字段填默认值；**整体校验失败则保持上一份有效配置**并在日志报错。文件权限 0600；写入前备份 `<路径>.bak-<时间戳>`（P1.5 起由 `configlib.backup_and_write` 统一实现：保留最近 10 份，同秒内多次写入自动追加 `-1/-2…` 后缀防互相覆盖）。

`console.token` 专项规则（2026-10-22 实施期定稿，取代原 `console/token` 文件机制）：

- 默认值 `jack1419`（开发期固定值，见 `configlib.DEFAULT_TOKEN`）；缺失即用默认值，不会自动生成。
- 校验：1~128 位可打印 ASCII（`^[\x21-\x7e]{1,128}\Z`，禁空格与换行）——同一值既要进登录 JSON 体，也要进 `X-Yolo-Token` 请求头。
- `/api/config` 回显时脱敏为 `***`（键保留）；`/api/state` 不含令牌。
- **改令牌必须重启 console**（配置启动时一次性加载，无热更新）；重启后所有会话失效（token 不变也需重新登录）。

### 6.2 REST API

| 方法 | 路径 | 说明 | 认证 |
| --- | --- | --- | --- |
| GET | `/healthz` | 存活探针，仅 `{"ok":true,"version":"2.1.0"}` | 免 |
| POST | `/api/auth/login` | body `{token}` → 设 HttpOnly Cookie | 免（有限流） |
| POST | `/api/auth/logout` | 清会话 | 需 |
| GET | `/api/state` | 状态快照（1 s 轮询） | 需 |
| POST | `/api/service/{start\|stop\|restart}` | body `{target: yolo\|rosbridge\|all}` → 调 ctl 脚本 | 需+token |
| GET | `/api/service/status` | ctl status 输出 + unit 启用态 | 需 |
| POST | `/api/stream/{rtmp\|ros2}` | body `{enabled}` → 写 config | 需+token |
| **GET** | **`/api/topics`** | **P1.5 新增：ros2 topic list -t + rosbridge ws 连接串 + rosbridge 运行态（Foxglove 订阅入口）** | 需 |
| **POST** | **`/api/source/probe`** | **P1.5 已实现**：body `{url,transport}` → ffprobe 只探测不落盘，返回 codec/宽高/fps | 需+token |
| **POST** | **`/api/stream/probe`** | **P1.5 已实现**：body `{url}` → RTMP 目标 TCP 连通预检（不校验鉴权/流名） | 需+token |
| **POST** | **`/api/source/rollback`** | 回滚到 `last_good_source`（P2，未实现） | 需+token |
| GET | `/api/config` | 读配置（**token 字段永不返回**） | 需 |
| **POST** | **`/api/config`** | **P1.5 已实现**（设计原为 PUT，实现取 POST 与其它写口一致）：body `{config:{…}}`，白名单六节 deep_merge → 校验不过 400 不落盘 → 轮换备份原子写 → 热替换 → needs_restart 判定 → yolo 运行中则自动重启 | 需+token |
| POST | `/api/snapshot` | 立即抓拍一帧 | 需+token |
| GET | `/api/pics?date=&page=&size=` | 抓拍列表 | 需 |
| **GET** | **`/api/pics/timeline?date=`** | **P3 新增**：当日抓拍时间轴索引（升序 `[{ts_ms,name,conf,cls,size}]`，供进度条与密度带构建，见 §5.5.1） | 需 |
| GET | `/api/pics/<date>/<name>[?thumb=1]` | 原图/缩略图 | 需 |
| DELETE | `/api/pics/<date>/<name>` | 软删除到 `.trash` | 需+token |
| GET | `/api/pics/trash` | 回收站列表 | 需 |
| POST | `/api/pics/trash/<name>/restore` | 还原 | 需+token |
| POST | `/api/model/upload` | multipart onnx（+ names.json / 类别表格） | 需+token |
| GET | `/api/model/export/status` | 导出任务状态与日志尾 | 需 |
| POST | `/api/model/reload` | 触发 worker 帧边界重载 | 需+token |
| GET | `/api/model/info` | 当前 engine 大小/mtime/metadata 摘要 | 需 |
| GET | `/api/logs?lines=` | tail 运行日志 | 需 |

### 6.3 `worker_state.json` / `/api/state` 字段

```json
{
  "worker": {"alive": true, "pid": 123, "uptime_s": 3600, "fps": 24.1,
             "frames": 86400, "infer_ms_ema": 17.2,
             "conf_threshold": 0.4, "config_mtime_age_ms": 300},
  "source": {"type": "rtsp", "state": "running", "url_masked": "rtsp://192.168.1.120:8554/test",
             "codec": "h264", "in_w": 1280, "in_h": 720, "out_w": 640, "out_h": 360,
             "reconnects": 0, "err": null},
  "stream": {"rtmp_state": "running", "rtmp_url": "rtmp://...", "rtmp_err": null,
             "ros2_image_state": "running", "ros2_hz": 8.0,
             "bitrate": 1000000, "pushed_frames": 86200},
  "snapshot": {"enabled": true, "today_count": 137, "queue_depth": 0,
               "dropped": 0, "last_file": "20261022T011500_120_c87_id3.jpg"},
  "model": {"engine": "yolov8n_arm.engine", "pending_reload": false,
            "export": {"state": "idle", "progress": 0}},
  "host": {"load1": 2.98, "mem_avail_mb": 4925, "disk_avail_gb": 42},
  "console": {"version": "2.1.0", "sessions": 1}
}
```

### 6.4 multipart 上传解析（弃用 `cgi`）

`cgi` 在 Python 3.13 已移除（本机 3.14 无法测试），改用 `email` 标准库，跨 3.8→3.13+ 一致：

```python
from email.parser import BytesParser
from email.policy import default as email_policy

def parse_multipart(body, content_type):
    msg = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    return {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
            for part in msg.iter_parts()}
```

- 上传约束：单文件 ≤ 50 MB；请求体上限 64 MB；读超时 30 s；文件名白名单 + UUID 重命名落盘。

### 6.5 认证与会话（D1 裁决的必备件）

| 项 | 设计 |
| --- | --- |
| token | 取自 `config/yolo8.json` 的 `console.token`，默认 `jack1419`（开发期固定值；历史版本的"首次启动生成 32 hex 写 `console/token` 文件"机制**已废弃**，该文件存在也忽略）。`hmac.compare_digest` 比对；日志不打印明文 |
| 登录 | `POST /api/auth/login {token}`，`hmac.compare_digest` 比对；成功发 `Set-Cookie: yolo8_s=<sid>; HttpOnly; SameSite=Strict; Path=/` |
| 会话 | 内存表 `sid → {created, last_seen, ip}`，TTL 12 h 滑动续期；进程重启即全部失效（可接受，token 不变无需重配） |
| 读接口 | 仅校验 Cookie 会话 |
| **写接口** | Cookie 会话 **且** 请求头 `X-Yolo-Token: <token>` 双因子 |
| **CSRF 免疫原理** | 跨站表单无法设置自定义头；跨站 `fetch` 带自定义头会触发 CORS 预检，服务端对 `OPTIONS` 一律 403 ⇒ 无需 CSRF token |
| 来源白名单 | 用 `self.client_address[0]`（**不信任 `X-Forwarded-For`**，本机无代理），不在 `allowed_cidrs` 内直接 403 |
| 失败退避 | 同 IP 连续失败 5 次 → 锁 5 min（内存表，进程重启清零） |
| 限流 | 全局 token bucket 10 req/s/IP；上传与 probe 单独 1 req/2s |
| 审计 | `logs/console-audit.log` 单行 JSON：`{ts, ip, ua, action, target, result}`，含 `rule=token_reject/cidr_reject/login_fail` |

**边界声明**：103 **无防火墙**；`0.0.0.0` 意味着 `192.168.1.0/24` 全段可达（并同时监听 `docker0 172.17.0.1`，被 CIDR 白名单挡掉）。103 经 120 NAT **出网**是单向的，**入向无端口映射 ⇒ 公网不可达**。任何人**不得**在 120 上为 8090 做 DNAT。

---

## 7. 前端设计

- **主方案**：`console/static/index.html` 单文件，原生 JS + CSS，零构建零依赖，由 `server.py` 伺服。
- **可选方案**：Vue3 + Vite 构建 dist（与 M20 控制台统一技术栈，可复用组件模式）。
- 页面结构：
  1. **登录页**（token 输入 → 存 sessionStorage）；
  2. 顶部徽标墙：服务 / 源 / RTMP / ROS2 / 抓拍 / 模型 / 磁盘 / 连接数；
  3. 五张卡片：**服务**、**视频源（新）**、**推流（新：目标可编辑）**、**检测与抓拍（阈值滑块）**、**模型**、**图片与日志**（P3：拆出**抓拍浏览**子区，含时间轴预览，见 §5.5.1）。
- **抓拍浏览区（P3 新增）**：日期选择（默认今天）→ **时间轴进度条**（真实时间线性映射 + 吸附最近帧 + 下方 240 槽密度带）→ 当前帧信息（时间/置信度/类别）→ 大图预览 → 前后帧按钮 / 下载 / 软删除。拖动中只换缩略图（预取 ±3 张），**停止 150 ms 防抖**后拉原图；←/→ 逐帧、Shift+←/→ 跳 10 帧；当日无抓拍显示空态并可跳到最近有抓拍的日期。
- **视频源卡片**：类型下拉（rtsp/file）、URL 输入、传输协议（udp/tcp）、延迟、输出分辨率、`测试连通性` 按钮（→ `/api/source/probe`，显示 codec/分辨率/fps）、`保存`（保存前服务端再探一次）、失败时显示 `回滚到上一个可用源`。
- **推流卡片**：URL 输入、码率滑块（500 kbps–4 Mbps）、分辨率/帧率、`测试连通性`（TCP）、`深度测试（推 1 秒彩条）` 带红字警告、ROS2 分路独立开关。
- 深色主题；危险操作（停服务、删图片、重载模型、深度测试）二次确认。
- **UI 铁律（沿用 M20 ADR-020/021）**：状态组件解构到顶层（composable 返回普通对象必须解构，否则取 Ref 恒真导致按钮全禁用）；开关统一 `DeviceToggle` 模式（`setX(目标值)`，"正在关闭"须对比当前真实状态）；分段控制用 `SegmentedControl`；`v-show` 不卸载 ⇒ 停流不能写 `onUnmounted`。
- 验收必须 playwright 真机核对（M20 既有流程）。

---

## 8. 安全与可靠性

| 项 | 措施 |
| --- | --- |
| 监听地址 | `0.0.0.0:8090`（**D1 裁决**，局域网可访问，配置项 `console.bind`） |
| 来源限制 | `allowed_cidrs` 默认 `["192.168.1.0/24"]`，非白名单 403（挡掉 docker0 与其他网段） |
| 认证 | 配置令牌 `console.token`（`config/yolo8.json` 内，0600；默认 jack1419）+ HttpOnly Cookie 会话 + 写接口双因子（`X-Yolo-Token`） |
| 暴力破解 | 同 IP 5 次失败锁 5 min；登录接口 1 req/s |
| 上传 | 大小（≤50 MB）/魔数（protobuf 弱校验）/文件名三重校验；单任务导出队列；类别数与 onnx 输出维校验 |
| 路径 | 全部文件操作白名单 + `realpath` containment 检查 |
| 原子性 | 配置、engine、worker_state 一律 tmp+rename；旧 engine 与旧 config 留 `.bak-<ts>` |
| 审计 | 启停/改配置/上传/删除/登录失败 全部入 `console-audit.log`（含来源 IP） |
| 限流 | token bucket 10 req/s/IP；probe 与上传 1 req/2s |
| 凭据 | RTSP URL 含密码时日志脱敏；`config.json` 0600；token 文件不进 git |
| 资源 | console `CPUAffinity=0-2`；TRT workspace ≤1 GB；上传体 ≤64 MB；抓拍 500/天 |
| 故障隔离 | RTMP/ROS2/源 三路互不牵连；任一路 error 只降级不退出（§5.2） |

---

## 9. 风险登记册

| ID | 风险 | 概率 | 影响 | 缓解 | 回滚 |
| --- | --- | --- | --- | --- | --- |
| R1 | 源码缺失，无法开工 | 高（已发生） | 阻断 | **git 对象完整**，P0 一条 `checkout` 恢复；备选上游副本/pyc | 恢复失败回只读分析态 |
| R2 | engine metadata 不兼容导致加载即崩 | 中 | G6 不可用 | 按真机模板写 5 个必需 key；**替换前先 `YOLO(new)` 试加载** | 保留旧 engine，删 tmp |
| R3 | 推流热切换泄漏 GStreamer 资源 | 中 | fd 耗尽/fps 降 | EOS→NULL 严格时序 + 状态机 + 50 次切换压测 + fd 监控 | 重启服务 |
| R4 | 抓拍写盘拖慢帧循环 | 中 | fps 跌落 | 独立线程 + 有界队列 + 丢弃计数 + **入队前 copy** | 关抓拍开关 |
| R5 | 磁盘被写爆 | 中 | 系统故障 | 500/天 + 7 天 + 回收站 7 天 + 每小时巡检 + `<5G` 停抓拍 | 手动清理 |
| R6 | Py3.8 语法不兼容（`X \| None`） | 中 | 启动即崩 | 本机 3.13/3.14 测不出 ⇒ **必须真机 `python3 -c` 冒烟** | 热修复 |
| R7 | 误删图片 | 中 | 数据丢失 | 二次确认 + **软删除回收站 7 天（D2）** | 回收站还原 |
| R8 | 控制台被未授权访问 | **中**（绑 0.0.0.0 后上调） | 误控机器人 | token + CIDR 白名单 + 失败退避 + 审计（§6.5） | 停 console 服务 |
| R9 | 上传 onnx 与运行时不匹配 | 中 | 推理静默出错 | 读 onnx 输入 shape 回填 imgsz；类别数校验；重载前冒烟 | 回滚旧 engine |
| **R10** | **源不可达导致启动永久阻塞** | **高（现状已存在）** | 进程卡死无日志 | `try-pull-sample` + 首帧超时 + `reconnecting` 状态（§5.9.3） | 用 `last_good_source` 重建 |
| **R11** | **RTMP 报错直接杀进程** | **高（现状已存在）** | 推理/ROS2/抓拍全停，35s 冷启动 | 改降级 + 指数退避，不 `break`（§5.2） | 停 RTMP 分路 |
| **R12** | **双配置源（env vs config）不一致** | **高（改造期必然遇到）** | "改了没生效" | §5.11 三层优先级 + 迁移脚本 + `ctl mode` 弃用 | 回退 env |
| **R13** | **源编码不受支持（无软解）** | 中 | 建管线即失败 | 保存前 ffprobe 探 `codec_name`，非 h264/h265 直接拒绝 | 拒绝写入即无影响 |

---

## 10. 分期实施计划

| 期 | 范围 | 交付物 | 验收标准 | 工作量 |
| --- | --- | --- | --- | --- |
| **P0** | 前置恢复 | `git checkout` 恢复 `src/` `deploy/` `note/`（含 2 篇旧笔记）；解除 skip-worktree；`yolo-publish.env` 由 `.bak` 改名；跑 `migrate-env-to-config.py`；冒烟启动一次 | `verify_headless.py` 通过；RTMP 流可 ffprobe 拉取；`config/yolo8.json` 生成且 schema 合法 | 0.5d |
| **P1** | 控制台骨架 + 认证 | `console/server.py` + 单文件前端 + unit；登录/会话/CIDR；服务启停（调 ctl）+ 状态面板 | 控制台自启；**未登录 401、非白名单 403、写接口缺 `X-Yolo-Token` 401**；启停 10 次无僵尸 | 2.5d |
| **P2** | 配置热更新 + 源/目标可配 | `config_loader.py`；阈值热更新；`build_source_pipeline`；`GStreamerWrapper` 改造（首帧超时/`try-pull-sample`）；`RtmpPublisher` 参数化 + EOS 关闭 + 可重建；RTMP 故障降级；`worker_state.json` | 改阈值 ≤1 s 生效；源切到 `file` 回放 3 s 内成功；填错 URL 被 400 拒绝且旧源无感；RTMP 断网只降级不退出、恢复后自动重连；50 次切换 fps ≥ 基线 90%、fd 不增长 | **4d** |
| **P3** | 抓拍 + 图片管理 **（含 §5.5.1 时间轴预览）** | `snapshot_writer.py`；配额清理；图片 API；**回收站**；**`/api/pics/timeline` + 时间轴/密度带/缩略图预览 UI** | 阈值 0.1/0.9 下抓拍数符合预期；命名合规；**入队前 copy 验证**（连续抓拍无重复帧）；主循环 fps 无显著下降；**L10 时间轴预览全过** | **2.5d** |
| **P4** | onnx 上传 + 导出 + 重载 | `export_engine.py`（TRT API + metadata 头）；上传校验；异步任务；原子替换；重载钩子 | 好 onnx 走通全链路且 `YOLO(new.engine)` 可加载；三类坏文件（改扩展名 txt / 超限 / 空文件）全被拒 | 4d |
| **P5** | 安全加固 + 总验收 | 限流、审计、token 轮换说明；`.gitignore` 补规则；24 h 长稳；L0–L10 全跑 | L0–L10 全过；RSS 波动 <10%；磁盘余量 >5 G | 2d |

> **当前进度（2026-10-22 09:10 核对）**：**P0 ✅ / P1 ✅ / P1.5 ✅ / P2 ✅ / P3 ✅**（§16–§18 与 P2 轮验收、§20 均已验收通过）；P4（onnx 导出）/ P5（加固 + 长稳 + L0–L10 全量）待排。
> 顺序经用户确认（D11）：**先 P2 后 P3**——worker 先切到 `config/yolo8.json`，抓拍开关/冷却/阈值才能在线生效；否则 P3 做的抓拍只能读 env，在线改配置对它无效。

合计约 **15 人日**（区间 12–18）。每期独立上线、独立回滚（回滚 = 停 console + 恢复 config 备份，数据面不受影响）。

---

## 11. 验收测试方案

| 级别 | 内容 | 判据 |
| --- | --- | --- |
| L0 | 冒烟 | console 存活；`/api/state` 200；真机 `python3 -c "import ..."` 无语法错 |
| L1 | 服务启停 | 连续 10 次启停，无僵尸、无重复实例、pid 文件一致 |
| L2 | 推流热切换 | 50 次切换，fps ≥ 基线 90%，`/proc/<pid>/fd` 回归稳定，无 GStreamer 报错 |
| L3 | 阈值与抓拍 | 阈值 0.1/0.9 下抓拍数符合预期；命名合规；`dropped==0`；抓拍帧与推流帧内容一致（验证 copy 正确性） |
| L4 | 模型上传 | 好 onnx 全链路通；三类坏文件全拒且不留残 file |
| L5 | engine 兼容性 | 新 engine 前 4 字节可解析；5 个必需 key 齐全；`YOLO(new).names` 与清单一致 |
| L6 | 长稳 24 h | RSS 波动 <10%；磁盘 >5 G；日志轮转正常；RTMP 可 ffprobe 拉流、Foxglove 8 Hz |
| **L7** | **安全（D1 相关）** | 无 Cookie → 401；Cookie 有但缺 `X-Yolo-Token` → 写操作 401；非白名单 IP → 403；连续 5 次错 token → 锁定；审计日志有对应记录 |
| **L8** | **源切换（G7）** | `rtsp → file` 回放 3 s 内切换；错误 URL → 400 且旧源不中断；断开 120 → `reconnecting` 并在恢复后 ≤30 s 自动接上；RTSP 端口错 → 报错文案可读 |
| **L9** | **目标切换（G8）** | 改流名成功切换且旧流停止；填 `live/lite3` 被拒（互踢保护）；TCP 探测失败拒绝保存；断网 3 min 后恢复自动重连 |
| **L10** | **抓拍时间轴预览（P3 新增）** | 拖动进度条**吸附到时间上最近的一帧**且标题时间与实际一致；密度带槽位分布与实际抓拍时段一致；**连续拖动 100 次只拉 1 次原图**（150 ms 防抖生效）；缩略图缓存命中（`pic/.thumbs/` 落盘且二次请求明显更快）；软删一帧后时间轴与密度带**即时更新**；当日无抓拍显示空态且不报错；文件名带 `../` 的请求被拒 |

---

## 12. 约束与依赖

1. Python 3.8.10、无 venv、无可信 pip 源 ⇒ 全部新代码用标准库，禁 3.9+ 语法（用 `typing.Optional`）。
2. 控制台绑 CPU 0-2；worker 维持 0-3（cpu5-7 为 SCHED_FIFO 实时线程，无条件抢占）。
3. `ultralytics/` 与 `hub_sdk/` 源码树**不可删、不可移动**（系统 python3 无该包，靠 cwd 导入）。
4. ROS2 Foxy：任何 source `setup.bash` 的脚本必须先 `set +u`。
5. TRT workspace ≤ 1 GB（NX 内存 6.7 G，worker 已占 ~2.6 G）。**不得同期跑两个导出**。
6. 磁盘余量 42 G：抓拍配额 + 日志轮转（`copytruncate`）双保险。
7. 103 无 WiFi、经 120 NAT 出网：推流与上传目标可达性依赖 120 的 MASQUERADE 规则（120 重启即失效，需复查 `host_start2.sh`）。
8. **103 无防火墙**（`ufw` 未安装）：安全边界 = 认证 + CIDR 白名单，不得依赖网络层。
9. **不存在软解**：`avdec_h264`/`openh264dec` 均缺 ⇒ `decoder` 只支持 `hw`/`auto`；`codec` 必须 h264/h265。
10. **不要设置 `GST_PLUGIN_PATH`**（实测默认即可；设错会遮蔽默认路径）。`gst-inspect --exists` 在 1.16.3 下对 NV 插件误报，勿据此判断。
11. `rtmpsink` 的 `location` 必须整体加引号并把 `live=1` 并入同值（否则 `no property "live"`）。
12. `.gitignore` 需补充（P5）：

   ```gitignore
   yolo8/pic/
   yolo8/model/uploads/
   yolo8/console/token
   yolo8/logs/*.json
   yolo8/config/yolo8.json
   yolo8/config/yolo8.json.bak-*
   yolo8/config/yolo8.local.json
   ```

   > P1.5 起 `.bak-*` 行从"理论需要"变为**硬需求**：在线改配置每次写入前都会生成 `config/yolo8.json.bak-<时间戳>`（保留 10 份），备份是配置的完整拷贝，**同样含访问令牌**。主文件与备份必须一起忽略，建议同时提供 `config/yolo8.json.example`（脱敏模板）作版本内样本。

---

## 13. 决策与遗留问题

### 13.1 已裁决（2026-10-22，用户确认）

| 编号 | 决策 | 落地章节 |
| --- | --- | --- |
| D1 | 监听**开放局域网访问**（`0.0.0.0:8090`）+ token + CIDR 白名单 | §5.8 / §6.5 / §8 |
| D2 | 删除图片走**软删除回收站**，7 天后清理 | §5.5 |
| D3 | 抓拍冷却 = **全局 2000 ms + 按类别 1000 ms**（AND） | §5.4 |
| D4 | **删除 ROS1 死代码**（`ROS1Transfer.py`，git 可恢复） | 附录 A |
| D5 | engine 导出走 **TensorRT Python API**（不用 ultralytics export） | §5.6 |
| D6 | **RTSP 源与 RTMP 目标均可配**（配置文件 + Web 双入口，先探后写） | §5.9 / §5.10 |
| D7 | P0 **恢复 note/ 下 2 篇旧笔记** | §10 P0 |
| D8 | 类别清单用**结构化表格 + COCO 一键预填**，兼容 names.json | §5.6.3 |
| D9 | **console 段不在线可改**（P1.5，用户确认 A+B 范围时定）：在线编辑限 yolo 六节；`console.bind/port/allowed_cidrs/session_ttl_s/token` 改错会把操作者锁在门外，仍走手改 `config/yolo8.json` + 重启 console | §6.2 / §18.3 |
| **D10** | **抓拍预览 = 时间轴拖动 + 缩略图**（2026-10-22 用户确认）：进度条按**真实时间线性映射**（非"第 N 张"等距）+ 拖动吸附最近帧 + 240 槽密度带 + 缩略图预取 ±3 + **停止 150 ms 防抖**才拉原图 | §5.5.1 / §7 |
| **D11** | **先 P2 后 P3**（2026-10-22 用户确认）：worker 先切到 `config/yolo8.json`，抓拍开关/冷却/阈值才能在线生效 | §10 / §19 |

### 13.2 遗留问题（实施中确认即可，不阻塞开工）

| 编号 | 问题 | 现倾向 |
| --- | --- | --- |
| Q9 | 是否要"深度推流探测"（推 1 s 彩条，会短暂覆盖目标画面） | 做，但默认关闭，按钮上红字警告 |
| Q10 | 是否需要 MJPEG 网页实时预览（**实时画面**） | 暂不做（占带宽与 CPU；Foxglove 已能看 ROS2 图像）。注：§5.5.1 的时间轴预览是**已保存抓拍的离线回看**，与本条无关，P3 要做 |
| Q11 | token 是否需要定期轮换/多用户 | 单用户单 token，提供"重新生成 token"按钮即可 |
| Q12 | `console.bind` 改回 `192.168.1.103` 的快捷开关是否要做 | 不做，改配置重启即可 |

---

## 14. v1 → v2 变更记录

| # | 类别 | v1 | v2 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | **缺陷修正** | `YOLO(onnx).export(format="engine")` | 改用 **TRT Python API** + 手工写 metadata 头 | onnx 加载后 `self.model` 是 onnxruntime session，`torch.onnx.export` 必败 |
| 2 | **缺陷修正** | multipart 用 `cgi` | 改用 `email` 标准库 | `cgi` 在 3.13 已移除，本机 3.14 无法测 |
| 3 | **架构优化** | console 自实现 PID/systemd 双模 + sudoers | 只调 `lite3-publish-ctl.sh` | 该脚本已内置双模判定与 B1–B7 修复 |
| 4 | **设计补全** | 状态采集仅附录提及 | 新增 §5.7 worker 写 `worker_state.json` | 消除"worker 是否开 HTTP"歧义 |
| 5 | **需求强化** | 类别不一致仅告警 | 强制类别清单 + onnx 输出维校验 | metadata `names` 无法自动推断，缺失即 KeyError |
| 6 | **参数明确** | 未提 TRT workspace | 限 1 GB + `set_memory_pool_limit` 回退 | NX 内存 6.7 G |
| 7 | **核查增信** | git 可恢复为推断 | `cat-file -e` 六路径全 OK | 真机验证 |
| 8 | **细节补充** | — | 端口规划、上传体限 64 MB、`.gitignore` 5 条、L5 验收 | 真机核查 |

---

## 15. v2 → v2.1 变更记录

| # | 类别 | v2 | v2.1 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | **裁决落地** | 监听 `192.168.1.103`，不绑 0.0.0.0 | **绑 `0.0.0.0`（局域网开放）**，认证从"可选"升为"必须"，新增 §6.5 认证与会话、CIDR 白名单、写接口双因子、失败退避 | D1 裁决；且实测 103 **无防火墙** |
| 2 | **新增能力** | 无（非目标明确"维持单 RTSP 源"） | **G7 视频源可配**（§5.9）：type/codec/decoder/transport/latency/输出分辨率 + ffprobe 前置探测 + 失败回滚 | D6 裁决 |
| 3 | **新增能力** | "Web 改 RTMP 地址"列为 Could | **G8 推流目标可配**（§5.10）：URL/码率/分辨率 + TCP 预检 + 双缓冲/先停后建两种切换策略 + `live/lite3` 互踢保护 | D6 裁决 |
| 4 | **缺陷修正** | 未提及 | **R11：`run_tracker_publish.py` 的 `if err: break` 会杀整个进程** → 改为降级 + 指数退避，三路故障隔离 | 真机读码（现状源码） |
| 5 | **缺陷修正** | 未提及 | **R10：`GStreamerWrapper.__init__` 用同步 `pull-sample`，源不可达永久阻塞** → 改用实测可用的 `try-pull-sample` + 首帧超时；`GetFrame` 同时消除忙等 | 真机实测 `try-pull-sample` 存在（id=26） |
| 6 | **事实修正** | "`conf` 经 `model.track` kwargs 逐次生效" | 实为 `YoloWrapper.__init__` 读一次 env、`Track()` 用 `self.conf` ⇒ **改属性即可，无需碰模型** | 真机读码 |
| 7 | **事实修正** | "必须 EOS→NULL 关闭" | 现状 `Stop()` 是裸 `set_state(NULL)`，EOS 是**待补改进项**，已给出 `eos_stop()` 实现 | 真机读码 |
| 8 | **新约束** | 未提 | **无软解**：`avdec_h264`/`openh264dec` 缺失 ⇒ `decoder` 仅 `hw`/`auto`；`ffprobe` 探明编码后再允许保存（R13） | 真机 `gst-inspect` 实测 |
| 9 | **误判澄清** | — | `gst-inspect --exists` 对 NV 插件误报；Python 注册表 **304 插件齐全**，管线 `parse_launch` 成功 ⇒ **不要加 `GST_PLUGIN_PATH`** | 真机脚本实测 |
| 10 | **架构补充** | env 与 config 双源未定规则 | 新增 §5.11 三层优先级 + 职责切分 + 迁移脚本 + `ctl mode` 弃用（R12） | 读 `run-yolo-publish.sh` 与 `ctl` 的 `mode` 实现 |
| 11 | **裁决落地** | 软删除/冷却/ROS1/类别清单为待决 Q2–Q8 | 全部落定（D2/D3/D4/D8），代码与验收同步更新 | 用户裁决 |
| 12 | **验收强化** | L0–L6 | 新增 **L7 安全 / L8 源切换 / L9 目标切换**；L3 增加"抓拍帧与推流帧一致"（验证 copy 语义） | 新能力同步 |
| 13 | **参数修正** | 抓拍冷却仅全局 | 全局 2000 ms + 按类别 1000 ms；`min_free_gb` 5G 可配 | D3 裁决 |
| 14 | **工期** | 14 人日（11–17） | **15 人日（12–18）**：P2 由 3d→4d、P1 由 2d→2.5d、P5 由 1.5d→2d | 新增源/目标可配与认证 |

---

## 附录 A：改造点清单

| 文件 | 位置 | 改动 | 风险 |
| --- | --- | --- | --- |
| `src/run_tracker_publish.py` | 主循环 | 阈值从 cfg 同步到 `yolo.conf`；抓拍入队（**先 copy**）；分路开关实时判断；**RTMP 错误不再 `break`**，改降级+退避；每 250 ms 写 `worker_state.json`；消除 `None` 帧忙等 | **高** |
| `src/GStreamerWrapper/GStreamerWrapper.py` | 全类 | 管线由 `build_source_pipeline(cfg)` 生成；`pull-sample`→**`try-pull-sample`**；首帧 `Event` + 超时；`GetFrame(timeout)`；`Stop()` 走 EOS→NULL；支持重建（`Reopen(cfg)`） | **高** |
| `src/RtmpPublisher/RtmpPublisher.py` | 全类 | 构造参数化（url/bitrate/尺寸/fps）；`eos_stop()`；bus error 回调驱动状态；支持"新建→验证→替换旧"与"先停后建"两种切换；`unref` 释放 | **高** |
| `src/RobotController/YoloWrapper/YoloWrapper.py` | `__init__`/`Track` | `conf` 改为从 cfg 取（保留 env fallback）；`classes` 可配 | 低 |
| `src/RobotController/ROSTransfer/ROS1Transfer.py` | 整个文件 | **删除**（D4，git 可恢复）；`TransferConstants.py` 同步清掉仅 ROS1 使用的常量 | 低 |
| `src/config_loader.py` | 新增 | mtime 轮询 + schema 校验 + 默认值合并 + 失败保持上一份 + 生成默认文件 | 低 |
| `src/snapshot_writer.py` | 新增 | 队列消费者、`UMat→ndarray`、配额与保留期清理、回收站清理 | 低 |
| `src/export_engine.py` | 新增 | TRT API 构建 + metadata 头 + 原子替换（§5.6.2） | 中 |
| `src/pipelines.py` | 新增 | `build_source_pipeline()`、`probe_rtsp()`、URL 校验 | 低 |
| `deploy/migrate-env-to-config.py` | 新增 | env → config 一次性迁移（幂等） | 低 |
| `deploy/scripts/run-yolo-publish.sh` | MODE 推导块 | 删除模式推导；不再 export 已迁移键；打印"配置以 config.json 为准" | 中 |
| `deploy/lite3-publish-ctl.sh` | `mode)` 分支 | 改为打印弃用提示，不再 `sed` 改 env | 低 |
| `console/server.py` | 新增 | 标准库 HTTP、REST、`email` multipart、token/CIDR/退避、限流、审计 | 中 |
| `console/static/index.html` | 新增 | 单文件前端（含登录页、源/目标卡片） | 低 |
| `console/systemd/lite3-yolo-console.service` | 新增 | 自启单元（`CPUAffinity=0-2`） | 低 |

## 附录 B：目录结构前后对比

```text
改前                              改后（+ 新增 / ~ 改造）
yolo8/
├── deploy/                       ├── console/            (+) 控制台 + token
│   └── yolo-publish.env.bak      │   ├── server.py
├── logs/                         │   ├── static/index.html
├── model/                        │   └── systemd/*.service
├── note/                         ├── config/             (+) yolo8.json (+ .bak-*)
└── src/                          ├── pic/                (+) YYYYMMDD/ + .trash/ + .thumbs/
    └── (仅 pyc)                  ├── model/uploads/      (+) onnx 暂存
                                  ├── deploy/             (~) 恢复 + 迁移脚本
                                  └── src/                (~) 改造 4 个 + 新增 4 个模块
```

## 附录 C：可复用资产（来自 M20 控制台经验）

1. 组件模式：`DeviceToggle`（`setX(目标值)`）、`SegmentedControl`、`CollapsibleSection`、状态徽标墙。
2. UI 铁律 ADR-020/021：composable 必须解构到顶层；拉流可见性 `flowWanted = active && pulled && !document.hidden`；`v-show` 不停流。
3. 部署脚本模式：`deploy/apply-dist.sh`（只换 dist、留 `.bak-<时间戳>`）。
4. 控制权归属 ADR-028：单 owner + 续约 + 安全指令豁免（本工程单用户，简化为会话即可）。
5. 验收方式：playwright 真机核对。
6. **后端改动后必须真机 `curl /healthz` 确认**（Py3.8 注解坑，本机新版 Python 测不出）。
7. **服务启停直接调 `lite3-publish-ctl.sh`**，不重写生命周期逻辑。
8. **探测优于猜测**：M20 推流丢帧最终靠"逐层归因 + 实测"定位；本工程同样以 `ffprobe`/`gst-inspect`/`parse_launch` 三件套先验。

## 附录 D：源/目标配置场景对照

| 场景 | `source` 关键项 | `stream` 关键项 | 备注 |
| --- | --- | --- | --- |
| 默认（120 摄像头） | `type=rtsp`，`rtsp_url=rtsp://192.168.1.120:8554/test`，`transport=udp` | `rtmp_url=rtmp://172.31.68.227:1936/live/lite3_yolo` | 与现网一致 |
| 120 换 IP | 改 `rtsp_url` 的 host | — | 保存前 ffprobe 会验证 |
| 弱网/丢帧 | `transport=tcp`，`latency_ms=500` | 略降 `rtmp_bitrate` | TCP 抗丢包，延迟略增 |
| 降延迟 | `latency_ms=100` | — | 默认 2000 ms 是延迟大头 |
| 本地回放调试 | `type=file`，`file_path=/home/test/yolo8/testdata/a.mp4` | `rtmp_sink=fakesink` | 不对外推流，纯验证 |
| 换推流服务器 | — | 改 `rtmp_url`（**不同 stream key**） | 双缓冲切换，可回滚 |
| 只发 ROS2 | — | `rtmp=false`，`ros2_image=true` | 分路独立 |

## 附录 E：管线与切换关键代码

**E.1 源管线**：见 §5.9.2 `build_source_pipeline()`。

**E.2 首帧等待**：见 §5.9.3 `_wait_first_sample()`。

**E.3 RTMP EOS 关闭**：见 §5.10.3 `eos_stop()`。

**E.4 双缓冲切换（不同流名）**

```python
def switch_rtmp(new_cfg):
    old = state.rtmp
    new = RtmpPublisher(url=new_cfg["rtmp_url"], bitrate=new_cfg["rtmp_bitrate"],
                        width=new_cfg["out_width"], height=new_cfg["out_height"],
                        fps=new_cfg["fps"])
    if not new.wait_healthy(timeout_s=3):          # bus 无 ERROR 且已 PAUSED/PLAYING
        new.eos_stop(); raise RuntimeError("new rtmp unhealthy")
    state.rtmp = new
    if old is not None:
        old.eos_stop()                             # 先建后停，失败可回滚
```

**E.5 认证判定**

```python
def authorize(self):
    ip = self.client_address[0]                    # 不信任 X-Forwarded-For
    if not ip_in_cidrs(ip, CFG["console"]["allowed_cidrs"]):
        audit("cidr_reject", ip); return 403
    if self.path in ("/healthz", "/api/auth/login"):
        return None
    if not sessions.valid(self.cookies.get("yolo8_s"), ip):
        return 401
    if self.command in ("POST", "PUT", "DELETE"):
        if not hmac.compare_digest(self.headers.get("X-Yolo-Token", ""), TOKEN):
            audit("token_reject", ip); return 401
    return None
```

---

## 16. P0 执行记录（2026-10-22 01:51–02:03，已验收通过）

> 本章为**实施记录**，非设计内容。所有操作均在 `/home/test/yolo8` 内，回退手段见下。

### 16.1 执行步骤与结果

| 步骤 | 命令/动作 | 结果 |
| --- | --- | --- |
| ① 备份 | `tar czf /home/test/yolo8_p0_backup_20261022.tar.gz -C /home/test yolo8`（368 个文件） | 49 MB，md5 `1d9746fc1d2de907936aa1914c037b8c`；另存文件清单 `/tmp/p0_manifest_before.txt` |
| ② 解除 S 标志 | `git ls-files -z -v yolo8 \| grep -z ^S \| cut -z -c3- \| xargs -0 git update-index --no-skip-worktree` | 34 → **0**；`git status` 随即暴露 37 项缺失（此前被掩盖） |
| ③ 恢复源码 | `git checkout -- yolo8/src yolo8/deploy yolo8/note yolo8/model` | 恢复 **387 个文件**，含 `note/双通路发布-踩坑记录.md`（20884 B）、`note/部署笔记.md`（24431 B） |
| ④ 完整性校验 | 逐文件 `cmp` 对 `git cat-file -p HEAD:<path>` | **ok=33 / bad=0**，字节级一致 |
| ⑤ 生成配置 | `python3 deploy/migrate-env-to-config.py`（先 `--dry-run`，再 `py_compile` 过 Py3.8 语法） | `config/yolo8.json` **1801 B / 0600**，schema 校验通过（conf=0.4、mode=rtmp、bitrate=1000000） |
| ⑥ env 分层 | `deploy/add-env-notice.py` 在 env 顶部插入说明 | 13 个键**全部保留生效**（避免 §5.11-5 所述的阈值静默回退）；备份 `.bak-p0-notice`、`.bak-migrate` |
| ⑦ 冒烟 | `deploy/p0-smoke.sh`（`setsid nohup` 后台，PID 落盘 `logs/p0-smoke.pid`） | 运行 **233.7 s**：`frames=5196 det_frames=715`，末段 **22.16 fps**，`rtmp_err=none`；RSS 2.6 GB、CPU 85%（与历史基线一致） |
| ⑧ 流验证 | `ffprobe rtmp://172.31.68.227:1936/live/lite3_yolo`；另 `gst-launch rtmpsrc ! fakesink` | **h264 / 640×360 / 30fps**，exit 0；RTMP TCP `ESTAB`（pid 18639 fd 264） |
| ⑨ 链路验证 | `python3 src/test/verify_headless.py` | **RESULT: PASS**（zidane.jpg 检出 2 人 conf≈0.83，噪点帧不崩） |
| ⑩ 停机 | `kill -TERM $(cat logs/p0-smoke.pid)` | 优雅退出 `stopping, frames=5196 ... elapsed=233.7s`，无残留进程 |

### 16.2 新增文件（本地源副本在 `lite3/docs/hosts/103-home-test-docs/deploy/`）

| 文件 | 作用 |
| --- | --- |
| `deploy/migrate-env-to-config.py` | env → `config/yolo8.json` 迁移；`--dry-run` / `--force`；幂等；内置 schema 校验（含 `live/lite3` 互踢保护、decoder 仅 hw/auto） |
| `deploy/add-env-notice.py` | env 顶部插入"配置分层说明"，幂等 |
| `deploy/p0-smoke.sh` | 冒烟启动包装：先落盘 PID 再 `exec`，保证 PID 一路保留到 python3（避免 `pkill -f` 自杀） |

### 16.3 踩坑记录（新增，供后续各期复用）

1. **`core.quotepath` 坑**：`git ls-files -v` 对中文路径输出**带引号与八进制转义**，直接管道回喂 `git update-index` 会报 `fatal: Unable to mark file`。正解：`git ls-files -z -v … | grep -z … | cut -z -c3- | xargs -0 …`，全程 NUL 分隔走原始字节。
2. **选项名拼写**：是 `--no-skip-worktree`，不是 `--no-skip-work-tree`（后者报 unknown option）。
3. **不先解 S 标志，`git checkout` 是 no-op**：`skip-work-tree` 的语义是"忽略工作树差异"，索引认为干净就不会写盘。必须先 `update-index --no-skip-worktree` 再 checkout。
4. **`pgrep -f run_tracker_publish.py` 会命中自身 SSH 命令**（坑 11.1 家族）——判断"有没有在跑"必须看 PID 文件或用 `ps -p <pid>`，不能靠 pgrep -f。
5. **`setsid … &` 之后 `$!` 是 setsid 的 PID，不是目标进程**：让包装脚本自己 `echo $$` 再 `exec`，PID 才可靠。
6. **后台作业 + ssh**：`cmd && setsid nohup x & sleep 4; …` 里的 `&` 会作用于整条 `&&` 链，导致 ssh 会话被 SIGTERM（输出仍可能拿到）。可接受，因为 setsid 已脱离会话；但更稳妥是把轮询拆成独立命令。
7. **本机命令行的 `:"` 组合在 SSH 传输中会被吃掉**（表现为远端 `syntax error near unexpected token '('`）。涉及 Python 单行含 `key:"` 的，一律改写为本地脚本 + scp。
8. **`ffprobe` 支持 rtmp/rtmps/rtmpt**（103 上已实测），可直接用于 RTMP 目标连通性与流参数验收；此前不确定，现已证实。

### 16.4 回退方式

```text
# 完全回退 P0（恢复源码 + 配置全部还原）
kill -TERM $(cat /home/test/yolo8/logs/p0-smoke.pid) 2>/dev/null
cd /home/test && git checkout -- yolo8    # 源码回到索引态（内容与本次恢复一致）
cp /home/test/yolo8/deploy/yolo-publish.env.bak-p0-notice /home/test/yolo8/deploy/yolo-publish.env
rm -f /home/test/yolo8/config/yolo8.json
# 需要更彻底的磁盘态还原时解包备份：
tar xzf /home/test/yolo8_p0_backup_20261022.tar.gz -C /home/test
```

### 16.5 P0 结论

**P0 验收全部通过**（§10 三条标准：`verify_headless.py` PASS、RTMP 可 ffprobe 拉取、`config/yolo8.json` 合法）。工程从"当前无法启动"变为"可运行、可冒烟、配置已分层"，具备进入 **P1（控制台骨架 + 认证）** 的条件。git 侧：`yolo8/src`、`yolo8/deploy`、`yolo8/note` 已恢复为 tracked 状态（不再带 S 标志），新增 3 个脚本与 `config/`、`pic/` 尚未加入 `.gitignore`（P5 处理），均未 commit，待用户审阅。

---

## 17. P1 执行记录（2026-10-22 02:00–04:45，已验收通过；重启验证待用户确认）

> 本章为**实施记录**，非设计内容。P1 范围：控制台骨架 + 认证（§10 分期表 P1 行）。

### 17.1 执行步骤与结果

| 步骤 | 命令/动作 | 结果 |
| --- | --- | --- |
| ① 令牌配置化 | `configlib.py` 增 `DEFAULT_TOKEN="jack1419"` + `DEFAULTS["console"]["token"]` + 校验（`^[\x21-\x7e]{1,128}\Z`）；`server.py` `TokenManager` 重写为配置驱动，删 `TOKEN_FILE` | 本地 py_compile + 边界单测（含尾部换行用例）通过；启动日志对弱默认值告警 |
| ② 真机配置写入 | sed 在 `"session_ttl_s": 43200,` 后插入 `"token": "jack1419"`；旧 `console/token` → `token.deprecated-20261022` | `config/yolo8.json` 1826 B / 0600 / 属主 ysc；备份 `yolo8.json.bak-token-20261022` |
| ③ 部署重启 | py_compile + `--check` → 重启（PID 36069） | 端到端：jack1419 登录 200、旧 32hex 令牌 401、`/api/config` 回显 `"token": "***"`、写接口旧令牌 401、审计 login ok/token_reject/login deny 齐全 |
| ④ UI 回归 | `ui-test.sh`（tabbit 真浏览器） | **38/38 PASS**（1m44s）：U5 sessionStorage 长度=8（动态 TOKLEN 断言）、U16 配置树 48 行、U36 rosbridge 真重启（PID 35143→37285，走双因子写路径）、徽标 `console v2.1.0-p1 · pid 36069 · 24MB · 2m 2s` |
| ⑤ A13 冲突修复 | 登录页标签原为"访问令牌（console/token…默认 jack1419）"，与 `p1-accept.sh` A13（grep 登录页找当前令牌值）**必然冲突** → 改为"访问令牌（见配置文件 config/yolo8.json 的 console.token 项）"；placeholder `32 位十六进制` → `输入访问令牌` | scp 上传即生效（静态文件每请求读盘 + `Cache-Control: no-store`，免重启）；md5 `25fc0f4b97d5760d926d50d4fa1a86c6` 两侧一致；HTTP 实测登录页不含令牌值 |
| ⑥ 审计轮转 | `mv logs/console-audit.log logs/console-audit.log.bak-token-20261022` | G 段为**全文件计数**，不清零会假 FAIL（见 §17.3-2）；AuditLog 每次写重新 open，自动重建无需重启 |
| ⑦ curl 验收 | 机器人侧 `bash p1-accept.sh`（来源 192.168.1.103 ∈ 白名单） | **53/53 PASS**：A19（免认证/拒绝/穿越/登录页要素）+ B7（登录/会话/Cookie）+ C6（读接口）+ D5（写接口双因子）+ E5（rosbridge×10 重启 + yolo 一轮真实启停）+ F3（无僵尸无残留）+ G6（审计聚合计数）+ H1（5 次失败锁 300s） |
| ⑧ 结构校验 | `python3 p1-validate.py`（读 ⑦ 落盘的 JSON 快照，不发 HTTP） | **47/47 PASS**，含新断言 `console.token 回显被脱敏为 ***`；`config_from_file=true` |
| ⑨ yolo 稳态 | `bash p1-yolo-steady.sh`（经 console API 启动 → 45s 冷启动 → 回流验证 → 停止） | PID 39034 存活，CPU 125%、RSS 2.6 GB、亲和 0-5；RTMP 回流 **h264 / 640×360 / 30fps**；推理 17.0ms；停止干净无残留。`Stream format not found, dropping the frame` 为 RTSP 源首帧前已知噪声 |
| ⑩ systemd 安装 | unit scp → `sudo cp` 到 `/etc/systemd/system/` → `daemon-reload` → `enable --now`（sudo 口令与车队一致） | `is-enabled=enabled` / `is-active=active`；`multi-user.target.wants` 符号链接已建（开机激活接线确认）；Main PID 39786；`taskset -pc` 实测亲和 **0-2**（避开 cpu5-7 实时线程）；`kill -9` 后 5s 自恢复（新 Main PID 40073）；console.log/console-audit.log append 写入正常 |
| ⑪ 未执行 | **整机重启验证开机自启** | 103 上 `transfer_ros2.service`（enabled）正跑 `jetson2motion`/`sensor_checker`，向机器狗运动控制器转发传感器数据；狗体状态未知（可能站立，有摔机风险）⇒ 不擅自重启。已建任务 #10，待用户确认狗体状态后执行 |

### 17.2 新增/变更文件（本地源副本 `lite3/docs/hosts/103-home-test-docs/console/`）

| 文件 | 变更 |
| --- | --- |
| `console/configlib.py` | `CONFIG_VERSION=2`；`DEFAULT_TOKEN`；`console.token` 默认值 + 校验规则 |
| `console/server.py` | `TokenManager` 配置驱动（删 `TOKEN_FILE` 与 32hex 生成逻辑）；启动日志令牌来源与弱默认值告警；`self.tokens = TokenManager(cfg["console"]["token"])` |
| `console/static/index.html` | 登录页标签去令牌明文（A13）；placeholder 中性化 |
| `console/get-token.sh` | 新增：PC 侧唯一取令牌入口（ssh 中继 → 读 config JSON），各测试脚本统一改用 |
| `console/p1-validate.py` | 令牌脱敏断言由"回显不含 token 键"改为"`console.token == ***`" |
| `console/p1-accept.sh` / `p1-yolo-steady.sh` | 令牌来源改配置驱动；accept v2 已含登录限流间隔与令牌桶节流修正 |
| `console/ui-test.sh` / `ui-test-tabbit.sh` / `ui-forensic*.sh` | 统一经 `get-token.sh` 取令牌；U5 断言改动态长度 |
| `console/systemd/lite3-yolo-console.service` | 相对 §5.8 规格的增量：`StartLimitIntervalSec=0`（禁 systemd 启动频率锁）、`UMask=0027`、`Documentation=`、不依赖 yolo-publish 的注释说明 |
| `deploy/migrate-env-to-config.py` | console 块补 `token` 键与注释 |
| 真机 `config/yolo8.json` | 插入 `console.token=jack1419`（0600） |
| 103 文档树 `.gitignore` | 新增 `.playwright-cli/`（317K 可再生产快照）；删除仓库根陈旧快照 `login.yaml` |

### 17.3 踩坑记录（P1 新增）

1. **静态页永远不得含令牌值**：`p1-accept.sh` A13 会 grep 登录页 HTML 找当前令牌值——登录页提示文案只能指路（"见配置文件 console.token 项"），不能复述值。
2. **审计 G 段是全文件计数**：跑 accept 前必须轮转 `console-audit.log`；且 **H 段会把 192.168.1.103 锁 300s**，故顺序必须是 accept（末尾含 H）→ validate（不登录）→ steady（复用 cookie，不登录）。
3. **登录锁定只作用于 `/api/auth/login`**（`server.py` L684 `ctx.backoff.check`）：持有效 Cookie 的会话请求在锁定期完全不受影响——据此确认 steady 脚本可安全接在 accept 之后。
4. **shell 代理陷阱**：本机 `http_proxy=127.0.0.1:58566`，curl 测局域网**必须 `--noproxy '*'`**，否则结果时通时断不可信（曾致误判"直连不通"）。
5. **网络拓扑结论（含一次自我勘误）**：console 绑 `0.0.0.0:8090`，正规局域网地址 `http://192.168.1.103:8090/`；PC 直连可行靠的是**静态路由 `192.168.1.0/24 → 192.168.2.1`（metric 56，非持久化，重启丢失）**；`srcbind-relay.py`（127.0.0.1:2222/8090 中继）已冗余但无害；console 视角来源 IP 恒显 `192.168.1.120`（120 对 192.168.2.x 做 SNAT），落在白名单内。
6. **`pgrep -f 'python3 -u server.py'` 会命中自身 ssh 包装命令**（坑 11.1 家族）：判存活看 `systemctl Main PID` 或 `ps -p <pid>`；且 `pgrep -f 'console/server.py'` 匹配不到进程（cmdline 是 `python3 -u server.py`，cwd 即 console 目录）。
7. **RejectThrottle 聚合语义**：窗口内首条拒绝**立即记**（无 `suppressed` 字段），其余只计数，后台线程每 30s 补一条带 `suppressed` 的汇总行——G2/G3/G4 断言的是"首条立即记=1"，不是总次数。
8. **登录限流 1 req/s 是设计行为**：测试脚本里相邻登录必须间隔 ≥1.3s，否则后者 429（v1 脚本 20/22 FAIL 皆源于此）。
9. **静态文件改动的部署方式**：`index.html` 每请求读盘 + `no-store` ⇒ scp 即生效，**不需要重启 console**（改 `.py` 才需要）。
10. **103 的 sudo**：口令与车队一致（`'`），`ysc` 为 `(ALL : ALL) ALL`；安装 unit 用 `printf "'\n" | sudo -S sh -c 'cp … && daemon-reload && enable --now'` 单次链路。

### 17.4 回退方式

```text
# 回退令牌配置化（一般不推荐：令牌已在用；仅在配置写坏时）
cp /home/test/yolo8/config/yolo8.json.bak-token-20261022 /home/test/yolo8/config/yolo8.json
# 卸载 systemd 托管，改回手工测试实例
sudo systemctl disable --now lite3-yolo-console.service
sudo rm /etc/systemd/system/lite3-yolo-console.service && sudo systemctl daemon-reload
cd /home/test/yolo8/console && setsid bash run-console-test.sh >> logs/console.log 2>&1 < /dev/null &
```

### 17.5 P1 结论

**P1 验收全部通过**：UI 38/38 + curl 53/53 + 结构 47/47 + yolo 稳态；console 已按 §5.8 安装为系统级单元并 `enabled`（开机自启接线就绪），崩溃 5s 自恢复，亲和 0-2。**唯一遗留**：整机重启后的开机自启实机验证——因 103 承载 `transfer_ros2.service`（机器狗传感器转发），重启需先确认狗体状态（任务 #10）。git 侧：`console/`、`deploy/` 全部未 commit，待用户审阅；`config/yolo8.json` 含访问令牌，**P5 必须将其加入 `.gitignore`**（§2 已记）。

---

## 18. P1.5 执行记录（2026-10-22 05:00–06:40，已验收通过）

> 本章为**实施记录**。范围来自用户新增需求：「可以远程订阅的话，控制台可以给出订阅的话题，还有能不能通过控制台查看当前的配置，以及修改配置，文本框或按钮」。两条决策经用户确认：**范围 = A（话题订阅卡）+ B（配置在线编辑）都做**；**生效策略 = 保存后自动重启生效**（改 yolo 相关配置立即自动重启 yolo，冷启动约 35s）。

### 18.0 先行声明：当前"生效"的准确语义（必读）

`config/yolo8.json` 是计划规定的**唯一运行期配置**，但 **worker 目前尚未消费它**——`deploy/scripts/run-yolo-publish.sh` 启动时只读 `deploy/yolo-publish.env`（P2 才把 worker 切到 config）。因此 P1.5 的"保存即生效"当前含义是：

- **文件态与管理面立即生效**：配置写入、备份、校验、回显、重启动作全部真实发生；
- **worker 行为要等 P2**：现在改 `detect.conf_threshold` 等，worker 行为不会变（它读 env）；自动重启是为 P2 预热——P2 接入后无需再改任何部署逻辑；
- 重启动作今天就是"无害空转"：行为不变、代价是 35s 中断；**yolo 未运行时不启动它**（跳过重启并明示）。

### 18.1 执行步骤与结果

| 步骤 | 命令/动作 | 结果 |
| --- | --- | --- |
| ① 写地基 | `configlib.py` 增 `backup_and_write()`（cp → `.bak-<ts>`、mtime 轮换保留 10 份、同秒连写追加 `-1/-2…` 后缀、atomic_write）与 `needs_restart(old,new)`（console 段变→console；六节任一变→yolo；簿记字段不触发） | 本地 + 真机单测 35/35（`p15-unit.py`，含同秒连写不互覆、live/lite3 互踢拒绝、env 解析、probe 降级路径） |
| ② 服务端 | `server.py` 增 `GET /api/topics`（`bash -c 'source /opt/ros/foxy/setup.bash; ros2 topic list -t'`，10s 超时；ws_url 取 env 文件 `ROSBRIDGE_PORT` + UDP 选路探 LAN IP）、`POST /api/config`（白名单六节 → deep_merge → validate（不过 400 不落盘）→ backup_and_write → `ctx.reload_config` → needs_restart → **yolo 运行中才自动重启**）、`POST /api/source/probe`（ffprobe）、`POST /api/stream/probe`（TCP connect）；`ConsoleContext` 增 `reload_config`/`list_topics` | py_compile + `--check` 通过；审计新事件 `config_write`/`config_restart`/`source_probe`/`stream_probe`；VERSION 保持 `2.1.0-p1`（ui-test U9 依赖） |
| ③ 前端 | `static/index.html`：新增话题订阅卡（ws 连接串 + 复制 + 话题表 + 刷新 + rosbridge 未运行提示）与「编辑配置」弹层（视频源/检测/抓拍/推流/其他五节表单，文本框/数字/滑块/复选框/下拉，两个保存前 probe 按钮）；保存走 `confirmDanger` → POST → needs_restart 含 yolo 时出冷启动横幅；编辑输入框全部建在 `#modal-root`（**不得进 `#cfgtree`**，U20 断言） | `node --check` 通过；静态改动 scp 即生效免重启 |
| ④ 真机部署 | 备份 `.bak-p15-<ts>` ×3 → scp → py_compile → `p15-unit.py` → `systemctl restart`（PID 40073→42118） | 真机单测 35/35；`/healthz` 200 |
| ⑤ 新功能验收 | `p15-feature.sh`（23 项）：话题/双 probe/配置写全路径 | **23/23 PASS**：T1 话题 25 个（yolo 运行中在发 ROS2）、ws_url `ws://192.168.1.103:9090/`；T2 ffprobe 实测 **h264 1280×720@30/1**；T3 RTMP TCP 5ms 可达；T4 五条拒绝路径全 400 且 md5 不变；T5 未运行→跳过重启/运行中→自动重启 **PID 42924→43048**；T6 幂等写 needs_restart=[]；T7 审计留痕 |
| ⑥ 回归四连 | 轮转审计 → `p1-accept.sh` → `p1-validate.py` → `ui-test.sh` → `p1-yolo-steady.sh`（**上机执行**，见坑 9） | accept **53/53**、validate **47/47**、ui-test **37/37**、yolo 稳态 **通过**（PID 48951、亲和 0-2、RTMP 回流 h264 640×360@30/1，见 §18.4） |

### 18.2 新增/变更文件（本地源副本 `lite3/docs/hosts/103-home-test-docs/console/`）

| 文件 | 变更 |
| --- | --- |
| `console/configlib.py` | 新增 `backup_and_write` / `needs_restart` / `YOLO_SECTIONS`；imports 增 `datetime`/`glob`/`shutil` |
| `console/server.py` | 四个新路由 + `lan_ip`/`read_env_port`/`probe_rtsp`/`probe_tcp` + `ConsoleContext.reload_config`/`list_topics` + 常量区（`WRITABLE_SECTIONS` 等 8 个） |
| `console/static/index.html` | 话题订阅卡 + 配置编辑弹层 + 冷启动横幅 + 相应 CSS；页首结构注释与配置卡 hint 更新 |
| `console/p15-unit.py` | **新增**：configlib/server 新函数单元测试（35 项，Py3.8 兼容，本地与真机同跑） |
| `console/p15-feature.sh` | **新增**：新功能 curl 验收（23 项） |
| `console/ui-test.sh` | URL `127.0.0.1:8090` → `192.168.1.103:8090`（srcbind-relay 已取消，见坑 6） |
| `console/get-token.sh` | `ssh -p 2222 ysc@127.0.0.1` → 直连 `ssh ysc@192.168.1.103` |
| `console/p1-accept.sh` | **内置审计轮转**（绝对路径 `/home/test/yolo8/logs/console-audit.log`，见坑 1） |

### 18.3 关键设计

1. **可写范围白名单**：`source/detect/snapshot/stream/model/pic_dir` 六节。`console` 段（bind/port/allowed_cidrs/session_ttl_s/token）**不在线可改**——改错会把自己锁在门外（D9，已补入 §13.1），UI 明示手改文件 + 重启 console。
2. **needs_restart 语义**：布尔节/整节替换均正确判定；`version`/`updated_at` 簿记字段不触发重启（T6 幂等写实证）。
3. **备份策略**：每次写前 `cp` 旧文件为 `.bak-<时间戳>`（0600），保留最近 10 份；同秒连写加后缀防覆盖（单测实证）。
4. **probe 定位**：保存前的"试连通"，不是监控。source 探真实流（ffprobe 拿 codec/宽高/fps），stream 只探 TCP（不校验鉴权/流名，响应里明示）。
5. **自动重启的安全护栏**：yolo 未运行 → 跳过并明示"下次启动生效"；运行中 → ctl restart（per-target 锁防并发）；写操作全程审计。

### 18.4 验收结果（全绿）

| 验收 | 结果 |
| --- | --- |
| `p15-unit.py`（本地 py3.13 + 真机 py3.8.10） | **35/35** |
| `p15-feature.sh`（新功能 23 项） | **23/23** |
| `p1-accept.sh`（curl 53 项，A19+B7+C6+D5+E5+F3+G6+H1） | **53/53** |
| `p1-validate.py`（结构 47 项） | **47/47** |
| `ui-test.sh`（tabbit 真浏览器） | **37/37**（P1 期为 38 项，srcbind-relay 取消后脚本演化为 37 项；含 U27b 飞行禁用时序、U36 rosbridge 真重启 PID 46310→48096、U20 配置树零输入框） |
| `p1-yolo-steady.sh`（冷启动 45s 稳态 + RTMP 回流） | **通过**（P1.5 后复跑）：经 console API 启动 PID 48951 → 45s 存活（CPU 106%、RSS 2.6 GB、亲和 0-2）→ **RTMP 回流 h264 640×360@30/1** → 推理 22.5ms、34.7s 处理 511 帧（63 帧有检测）→ 停止干净 |

### 18.5 踩坑记录（P1.5 新增）

1. **审计轮转路径坑（本轮实踩）**：审计日志在 `/home/test/yolo8/logs/console-audit.log`，**不在** `console/logs/` 下。在 console 目录用相对路径轮转会静默失败（mv 报错被 `2>/dev/null` 吞掉），G 段全文件计数把旧账算进来，G1/G2/G3/G4 全部翻倍假 FAIL。已在 `p1-accept.sh` 顶部内置绝对路径轮转。
2. **H 段锁 300s 与重跑时序**：accept 末尾会把 192.168.1.103 锁 5 分钟；**锁在内存**（`LoginBackoff`），接着重跑 accept 会全链 401——判据是 G5 `login` 计数为 0（登录根本没到达处理器，全是 429 `login_locked`）。解法：等锁自然过期，或重启 console 清内存态（本轮采用后者，重启后 probe 200 即恢复）。
3. **同秒备份撞名**：`.bak-<秒级时间戳>` 在同一秒的多次写入会互相覆盖，静默丢失前一份备份 ⇒ 追加 `-1/-2…` 后缀（单测专门覆盖）。
4. **`jpost()` 吞 `-o`（测试脚本家族坑）**：函数体只取 `$1/$2`，调用处写的 `-o file` 被丢弃，JSON 打到 stdout，后续 python 读文件全线 FileNotFoundError——**产品是对的、脚本是错的**，排查时先看 stdout 原文再改脚本。
5. **sudo 口令 `'` 与 ssh 单引号嵌套**：`ssh host 'printf "'\n" | sudo -S …'` 必然炸（引号提前终结）。正解：`Q=$(printf "\047")` 八进制取引号再 `printf "%s\n" "$Q" | sudo -S`。
6. **srcbind-relay 取消的连带影响**：用户取消了 PC 侧中继后台任务 ⇒ `ui-test.sh` 的 `http://127.0.0.1:8090` 与 `get-token.sh` 的 `ssh -p 2222` 同时失效。改直连后**实证**：PC 请求经 120 SNAT，console 视角来源 IP 恒为 `192.168.1.120` ∈ 白名单（auth_reject 审计行证实）；且 accept 的 H 段锁的是 `.103`，与浏览器登录路径（`.120`）**互不相干**——顺序 accept→validate→ui-test 依然成立。
7. **playwright-cli 代理劫持**：Chromium 会读 env 代理，跑 ui-test 前显式清空 `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy/ALL_PROXY/all_proxy`。
8. **单目标 status 的 JSON 形状**：`?target=yolo` 时 `services` **直接是状态对象**（不是 `{yolo:{…}}` 字典）；`?target=all` 才是按 target 键。测试脚本取 PID 要兼容两种形状。
9. **稳态脚本必须上机跑（2026-10-22 实踩）**：`p1-yolo-steady.sh` 读 `/home/test/yolo8/...` 本地路径 + 用本机 `ffprobe`，**只能在 103 上执行**。在本机（Windows）误跑的表现为：token 读取 FileNotFoundError、日志/pid 文件"不存在"、全链 `未授权或凭证无效`——极易误判为"线上配置被删"事故。排查先 `ls` 远端目录确认产品侧无恙。另：脚本原缺登录步骤（只有 `-b $JAR` 没有 login），已补 `POST /api/auth/login` 建会话（写接口双因子，Cookie + X-Yolo-Token 都要）。

### 18.6 回退方式

```text
# 1) 控制台三件套回退到 P1.5 前（console 需重启生效）
cp /home/test/yolo8/console/server.py.bak-p15-<ts>        /home/test/yolo8/console/server.py
cp /home/test/yolo8/console/configlib.py.bak-p15-<ts>     /home/test/yolo8/console/configlib.py
cp /home/test/yolo8/console/static/index.html.bak-p15-<ts> /home/test/yolo8/console/static/index.html
sudo systemctl restart lite3-yolo-console.service
# 2) 运行配置回退（在线改写坏时；.bak-* 为每次写前的自动备份，保留 10 份）
cp /home/test/yolo8/config/yolo8.json.bak-<ts> /home/test/yolo8/config/yolo8.json
# 3) 前端单独回退：index.html scp 即生效，不需要重启 console
```

### 18.7 结论与遗留

**P1.5 验收全部通过**：控制台从"只读管理面"升级为"可订阅话题 + 可在线改配置"，写路径带校验/备份/审计/自动重启全护栏。**遗留**：① worker 消费 `config/yolo8.json`（P2，§18.0 已声明当前语义）；② 整机重启验证开机自启（任务 #10，待用户确认狗体状态）；③ git 侧全部未 commit，且 `config/yolo8.json` 与 `.bak-*` 备份**均含访问令牌**，P5 的 `.gitignore` 必须同时覆盖两者（§12.12 已补，建议附脱敏模板 `yolo8.json.example`）。

---

## 19. P2 / P3 设计增补与排期确认（2026-10-22，**仅设计，代码待审后实施**）

> 触发：用户核对计划书时发现「按检测目标保存图片」与「控制台预览保存图片」两项看不到实现。
> 经核查确认：**这两项属 §10 分期表的 P3，设计已有（§5.4/§5.5）但代码零实现**（真机 `run_tracker_publish.py` 无抓拍挂点、`pic/` 目录不存在、`snapshot_writer.py` 不存在、server 无 `/api/pics*` 与 `/api/snapshot` 路由）。
> 用户裁决：**先补设计，审过再写代码**。本章只改文档，不碰任何代码。

### 19.1 完成度盘点（对照 §10）

| 期 | 状态 | 说明 |
| --- | --- | --- |
| P0 | ✅ 已完成 | §16（源码恢复 / env→config / 冒烟） |
| P1 | ✅ 已完成 | §17（骨架 + 认证 + 启停 + 配置只读树 + 日志） |
| P1.5 | ✅ 已完成（超范围追加） | §18（话题订阅 + 配置在线编辑 + 双 probe） |
| P2 | ✅ 已完成 | worker 消费 `config/yolo8.json`、源/目标热切换、RTMP 故障降级。**P3 前置**（D11） |
| P3 | ✅ 已完成（§20） | 抓拍（§5.4）+ 图片管理（§5.5）+ **时间轴预览（§5.5.1 本轮新增）** |
| P4 | ⏳ 待排 | onnx 上传 / engine 导出 / 重载 |
| P5 | ⏳ 待排 | 安全加固、`.gitignore`、24 h 长稳、L0–L10 |

### 19.2 本轮确认的三项决策

1. **执行方式**：先补设计，用户审过再写代码（本轮只动文档）。
2. **顺序**：**P2 → P3**——worker 先切 `config/yolo8.json`，抓拍参数才在线生效（D11）。
3. **预览形态**：**时间轴拖动 + 缩略图**（D10），按用户描述落地。

### 19.3 本轮设计增补清单

| 章节 | 增补内容 |
| --- | --- |
| **§5.5.1（新增）** | 抓拍时间轴预览：索引来源（文件名自带毫秒时间戳，不另建索引）、`/api/pics/timeline` 接口、**进度条=真实时间轴+吸附最近帧**、240 槽密度带、缩略图预取 ±3、**停止 150 ms 防抖**才拉原图、键盘逐帧、空态、删除后即时更新时间轴、安全沿用白名单+containment |
| §6.2 | 新增 `GET /api/pics/timeline?date=` 一行 |
| §7 | 「图片与日志」卡片明确拆出**抓拍浏览**子区，写明时间轴交互 |
| §10 | P3 行并入时间轴预览（工作量 2d → **2.5d**）；表后加「当前进度」块与 P2→P3 依赖说明 |
| §11 | 新增 **L10 抓拍时间轴预览** 验收项（吸附/密度带/防抖只拉 1 次原图/缓存命中/删后更新/空态/穿越拒绝）；P5 判据改为 L0–L10 |
| §13.1 | 新增 **D10**（时间轴交互形态）、**D11**（先 P2 后 P3） |
| §13.2 | Q10 澄清：时间轴预览是**离线回看**，与实时 MJPEG 无关，P3 要做 |

### 19.4 P3 开工前置（动手前必须满足）

- P2 已完成：worker 从 `config/yolo8.json` 读 `snapshot.*` 与 `detect.conf_threshold`；
- `pic/` 与 `pic/.thumbs/` 已进 `.gitignore`（§12 第 12 条）；
- 抓拍先以低阈值（0.1）跑 10 min 验证命名 / 双冷却 / **入队前 `frame.copy()`** 语义，确认无重复帧后再放量；
- 时间轴预览的验收必须有真图（≥50 张跨时段抓拍），不能靠空目录跑通就算过。

---

## 20. P3 执行记录（2026-10-22 07:40–09:10，已验收通过；git 未提交待审）

> 本章为**实施记录**。P3 范围：worker 侧抓拍（§5.4）+ console 图片管理 API（§5.5）+ 时间轴预览（§5.5.1）。
> 部署前已满足 §19.4 全部前置（P2 ✅ / `.gitignore` / 低阈值冒烟 / 真图验收）。

### 20.1 验收结果总览

| 验收项 | 结果 | 数据 |
| --- | --- | --- |
| 单测（worker 侧 `src/p3-unit.py`） | ✅ **43/43** | 真机 py3.8.10 双跑通过；含 T7 copy 语义变异验证、T16 pic_dir 回归 |
| 单测（console 侧 `console/p3-pics-unit.py`） | ✅ **46/46** | 真机 py3.8.10 通过；含 P24b mtime 兜底回归、P18–P22 穿越拒绝 |
| 冒烟终检（`console/p3-smoke-check.py`） | ✅ **9/9** | 阈值 0.1 + 全 80 类跑 10 min：**264+ 张**，`min_gap=2001ms`（全局冷却零违反）、0 dropped / 0 errors、0 重复帧、frame_no 分段严格递增 |
| L10 时间轴验收（`console/p3-l10.sh`，playwright 真机） | ✅ **35/35** | 吸附（精确命中/中点/端点全对）、密度带 240 槽与数据一致、连拖 100 次原图 **恰好 +1**、键盘 ±1/±10、删后即时更新、还原、空态、thumb 缓存、穿越 404 |
| 既有 UI 回归（`console/ui-test.sh`） | ✅ **37/37** | P3 改动无回归；U9 版本断言同步至 `2.1.0-p3` |

冒烟期间阈值/类别为临时值，**已恢复生产配置**（`conf_threshold=0.4`、`classes=[0]`，经 `/api/config` 在线改回，备份 `yolo8.json.bak-20261022-081159`）。

### 20.2 部署记录（本地源副本 `lite3/docs/hosts/103-home-test-docs/`）

| 文件 | 动作 | md5（本地=远端一致） |
| --- | --- | --- |
| `src/snapshot_writer.py` | 新增 | `3fb271b…` → 修复 pic_dir 后 `878b8091…` |
| `src/run_tracker_publish.py` | 改（4 处挂点） | `bfdc64f1…` |
| `console/server.py` | 改（VERSION `2.1.0-p3`，PicStore + 6 路由） | `aa67adee…` |
| `console/static/index.html` | 改（抓拍卡 + 时间轴 JS + 徽标） | `01c7d528…` → 修复刷新冲掉位置后 `def330a0…` |
| `console/get-token.sh` | 修（双平台取令牌） | 本地/远端同步 |
| `console/p3-l10.sh`、`console/p3-smoke-check.py`、`console/ui-test.sh` | 新增/改 | 均已 bash -n + 真机跑通 |

备份：`deploy/backup-p3-20261022-075402/`（覆盖前原件）。全部 LF 行尾、无 CR；真机 `py_compile` 过 Py3.8。

### 20.3 实施中发现并修复的三个真 bug

1. **pic_dir 双端解析不一致（部署级）**：worker 把 `../pic` 按**项目根**解析（→`/home/test/pic`），console 按 **src/** 解析（→`/home/test/yolo8/pic`），两侧注释都写「相对 src/」——浏览侧永远看不到抓拍。修复：worker 改为相对 src/；新增回归 **T16/T16b**（默认相对 src/ + 绝对路径透传）。
2. **目录 mtime 合并不刷新（缓存失效漏洞）**：实测本机文件系统「紧接着的连续创建」有 28/30 概率不刷新目录 mtime，`_scan` 只按 mtime 缓存会把刚写入的抓拍漏掉一个粒度窗口。修复：缓存键升级为 **(mtime, jpg 文件名清单)**——`listdir` 本就无条件执行，比对 names 零成本；新增回归 **P24b**（把缓存 mtime 抹成当前值，全平台确定性复现）。
3. **自动刷新冲掉用户浏览位置（UX）**：`picsAutoRefresh` 每 10s 重拉 timeline 后无条件 `picsGotoIdx(last)`，把用户正在看的中间帧弹回最新。修复：`picsLoad` 记住当前帧 name，重拉后**按 name 找回保持**，找不到（被删/跨日期）才回退末张。

### 20.4 测试脚本自身的坑（复用价值）

1. **`get-token.sh` 自助 ssh**：旧版无条件 `ssh ysc@192.168.1.103`，在 103 上跑 = ssh 回自己（103 无自身公钥）→ Permission denied → TOKEN 空 → 全链 401 假事故。修复：本机可读 config 时直读，否则 ssh。
2. **ui-test/L10 必须在 PC 跑**：playwright-cli 只装在 PC（`@playwright/cli@0.1.22`）；103 上没有。浏览器会话**跨 Bash 调用即回收**（ui-test 既有注释早已警告），必须单进程。
3. **playwright-cli eval 只收单表达式**：多语句（`a;b;0`）**静默不执行**（连 `### Result` 都不输出）；但**会 await Promise**——「即发即忘+轮询 window.__x」模式全废，必须链式返回。
4. **ev/evs 引号**：playwright 字符串返回值带双引号，`ev` 不剥、`evs` 剥。混用会导致：拼 URL 404（L9）、数字比较失败（L4）、**字符串相等判断假 PASS**（L6c 曾因引号不匹配恰好 =false 而"通过"）。
5. **采样竞争**：10s 自动刷新会在「取名字」与「点删除」之间冲掉 idx（L6 曾因此偶发失败）——关键段需临时禁用 `picsAutoRefresh`。
6. **写接口双因子**：页面 `api()` 自带 `X-Yolo-Token`，裸 `fetch` 不带 → 401（L7a）。
7. **Chromium 代理劫持**（计划书 §1248 旧坑复现）：PC 上跑前必须 unset 全套代理 env。

### 20.5 回退方式

```text
# 1) 代码四件套回退到 P3 前（worker 需重启；console 需重启；index.html 即传即生效）
cd /home/test/yolo8
cp deploy/backup-p3-20261022-075402/run_tracker_publish.py src/
cp deploy/backup-p3-20261022-075402/server.py console/
cp deploy/backup-p3-20261022-075402/index.html console/static/
rm -f src/snapshot_writer.py
bash deploy/lite3-publish-ctl.sh restart yolo
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console.service

# 2) 抓拍数据（pic/ 为新增目录，删除前确认无浏览需求；.trash 内 7 天自动清）
#    rm -rf /home/test/yolo8/pic   ← 会丢失冒烟期 264+ 张抓拍，一般不执行

# 3) 运行配置（detect 已在线改回 0.4/[0]，无需处理）
```

### 20.6 遗留

- git 全部未提交（P0–P3 累计改动），待用户审阅后统一 commit；
- `pic/`、`pic/.thumbs/`、`pic/.trash/` 已在 `.gitignore`（§12-12），但**抓拍 sidecar 与配置 `.bak-*` 均不含令牌**（P5 仍需复核 `.gitignore` 覆盖 `config/yolo8.json` 与 `.bak-*`）；
- P4（onnx 导出）/ P5（加固 + 长稳 + L0–L10 全量）未实施。

---

*本文档为 v2.1 完整版：§0–§15 为设计，§16–§18 为 P0/P1/P1.5 实施记录，§19 为 P2/P3 设计增补与排期确认，§20 为 P3 实施记录，§21 为 P4 实施记录（构建耗时见 §21.6）。后续各期实施结果按同样格式追加章节。*

## 21. P4 执行记录（2026-10-22 09:10–11:00，上传/重载/前端已验收；构建耗时见 §21.6）

### 21.1 范围与交付物

| 类型 | 文件（本地源副本 `lite3/docs/hosts/103-home-test-docs/`） | md5 |
| --- | --- | --- |
| 新增 | `src/export_engine.py`（onnx→engine，TRT API + 手写 metadata 头；inspect/verify 子命令） | `ec8d7ff2…` |
| 新增 | `src/p4-unit.py`（纯逻辑 38 项） | `dde73e3f…` |
| 新增 | `console/p4-unit.py`（multipart/头解析/路径/状态机 50 项） | `5b337b32…` |
| 新增 | `console/p4-accept.sh`（真机 L4/L5 + 重载闭环） | `c2d53904…` |
| 新增 | `console/p4-reload-check.sh`（不构建也能验重载链路） | `acd6cafc…` |
| 新增 | `console/p4-ui.sh`（playwright 前端核对 16 项） | `a13f5eb0…` |
| 新增 | `deploy/apply-p4.sh`（备份+scp+双侧 md5+py3.8 编译+去 CR） | `af8e22ce…` |
| 改动 | `console/server.py`（上传/导出/重载/信息四接口 + ExportManager） | `50d04d0a…` |
| 改动 | `console/static/index.html`（模型卡 + 徽标） | `0cb91583…` |
| 改动 | `src/RobotController/YoloWrapper/YoloWrapper.py`（engine 可配 + Reload + 读头取类数） | `9c0914b8…` |
| 改动 | `src/RobotController/RobotController.py`（透传 engine_path） | `7d9b9ad3…` |
| 改动 | `src/run_tracker_publish.py`（帧边界重载 + pending_reload 回写 + model 状态块） | `3a090061…` |

接口（全部实现）：`POST /api/model/upload`、`POST /api/model/export`、`GET /api/model/export/status`、
`POST /api/model/reload`、`GET /api/model/info`；`GET /api/state` 增 `model_export`，`worker_state` 增 `model`。

### 21.2 关键设计（实施定稿）

- **构建**：`trt.Builder` + `OnnxParser` + EXPLICIT_BATCH；FP16；`workspace` 默认 1024 MB；
  `builder_optimization_level` 默认 2；可选 `--no-cudnn`（只留 CUBLAS/CUBLAS_LT tactic）；
  输出目录 `.trt-timing-cache` 复用 profiling；`pack_engine` 写 4 B 小端 meta_len + JSON + plan，
  同目录 tmp + `os.replace` 原子替换。
- **自检（替换前）**：`trt.Runtime.deserialize_cuda_engine(plan)` + 头解析（5 个 key）。
  **不用 `AutoBackend`**：worker 常驻占着 GPU 时它会挂住（§21.3 坑 7）；也不用
  `YOLO(engine).names`（该属性在预测前恒为 None，§21.3 坑 1）。端到端加载由
  worker 重载后的首帧推理证明（L5 重载 + fps）。
- **重载（§5.6.4）**：console 只写 `model.engine` + `model.pending_reload=true`（走
  `backup_and_write`，留 10 份 `.bak-<ts>`）；worker 每帧检查，在帧边界 `YoloWrapper.Reload()`
  （**先建新实例再替换**，失败继续用旧模型），随后**由 worker 回写 pending_reload=false**
  （唯一清除方），并把 `engine/classes_total/reload_count/reload_error` 写进 `worker_state.model`。
- **类别钳制**：新 engine 类别数可能少于旧模型，`sync_detect` 用 `classes_total`（读 engine 头）
  裁掉越界 id，避免 ultralytics 取值错误。
- **上传校验四道**：体积（文件 ≤50 MB / 体 ≤64 MB）→ 扩展名 → 文本魔数（前 64 字节全可打印即拒）
  → `onnx.load`（子进程 inspect）。失败一律删残文件；上传目录 `model/uploads/<uuid>.onnx`（0600）。

### 21.3 实施中发现的真 bug / 硬坑

1. **`YOLO(engine).names` 在 ultralytics 8.1.0 恒为 None**：`YOLO.__init__` 只把字符串存进
   `self.model`，真正 AutoBackend 要到 `predict()` 才建。首版预加载用 `len(m.names)` 直接
   `TypeError`；worker 的 `classes_total` 也一直显示 0。修法：预加载改 `AutoBackend`；
   类别数改读 engine metadata 头（`read_engine_names`，零副作用、毫秒级）。
2. **CIDR 白名单把本机也挡了**：验收脚本首版打 `http://127.0.0.1:8090`，来源 IP 是
   `127.0.0.1` → 全链 403。改为 `http://192.168.1.103:8090`（来源 192.168.1.103 ∈ 白名单）。
3. **Windows 侧 Python 文本模式写 `.sh` 会转 CRLF**：`sed -i` 只在部署脚本 FILES 列表里做，
   单独 scp 的脚本漏了 → `set: -: invalid option`、`$'\r': command not found`。修：
   `apply-p4.sh` 的 FILES 加入 `console/p4-accept.sh`；本地 patch 脚本一律 `newline="\n"`。
4. **workspace 512 MB 反而更慢**：TRT 报 `Some tactics do not have sufficient workspace memory`，
   单层 tactic profiling 退化重试，yolov8n 在 NX 上 ≥16 min 仍未完成。1024 MB 仍是 11 min+。
5. **TRT 8.5 没有 `IProgressMonitor`**：构建期 10+ 分钟无任何输出，UI 会像卡死。加心跳线程
   每 30 s 打 `INFO building… 已 Ns`（console 环形日志 200 行，前端可见）。
6. **20W 功率模式是构建慢的根因之一**：`nvpmodel -q` = `MODE_20W_6CORE`；`tegrastats` 实测
   构建期 **CPU 6 核全 100%、GR3D_FREQ 0~5%** ⇒ 瓶颈是 CPU 侧的 tactic 编译（ptxas），
   不是 GPU 算力。worker 常驻推理还要抢一个核。切 MAXN 需用户决定（整机功耗/散热）。
7. **TRT 8.5.2.2 的 Python API 没有 `builder_optimization_level` / `max_num_tactics`**：
   `dir(IBuilderConfig)` 只有 `set_tactic_sources`。首版 `config.builder_optimization_level = N`
   抛 AttributeError 被 except 吞掉（日志有"沿用默认（3）"），因此 opt-level 1/2/3 的实测
   全是在默认 3 下跑的——这是"调了参数却没变快"的真因。可用的只有 `--no-cudnn`（限制
   tactic sources），实测收益有限（仍 11 min+）。
8. **重载是"懒加载"，`last_reload_s` 会显示 0.0**：`YOLO(path)` 构造只存字符串，真正的
   TRT 反序列化发生在**下一帧 `Track()`**；所以帧边界那次调用很快返回，卡顿体现在随后
   一两帧的间隔上（实测 fps 短暂掉到 0 再恢复）。`last_reload_s` 仅供排查参考，
   不能当作"重建耗时"。
9. **worker 占着 GPU 时 `AutoBackend` 会挂住**：`AutoBackend(engine, device=cuda:0)` 在
   worker 正常推理时 90 s 无任何输出、RSS 涨到 2 GB（多次复现），既拖慢导出又产生假失败。
   预加载因此改为 `deserialize_cuda_engine`（2 s 内完成）。
10. **`engine.serialize()` 返回 `IHostMemory`，既不能 `len()` 也不能 `bool()`**（P4 最隐蔽的一个，
    2026-10-23 做完整 fresh-build 验收时才暴露）。首版写的是
    ```python
    blob = engine.serialize()
    if not blob:            # ← 炸点：bool() 在 pybind 绑定类型上回退到 __len__
        raise RuntimeError(...)
    ```
    真机抛 `TypeError: object of type 'tensorrt.tensorrt.IHostMemory' has no len()`，
    `len(blob)` 同理。**后果极具误导性**：构建其实在 **1580 s（26 min）就成功了**
    （日志已走到 `PROGRESS 85 serialize`、`[BlockAssignment] ... 105 steps`、
    `Total Activation Memory: 9011712`），却卡在写盘前一步炸掉，
    表现为"导出失败、engine 文件不存在"。P4 之前三次"构建 11~17 min 未完成"的排查
    全被这个假象带偏，一直误判成"构建太慢"——**真正的瓶颈是慢，但失败原因是 bug**。
    修法：新增 `blob_to_bytes()`（bytes / bytearray / memoryview / bytes() 四路回退），
    `serialize()` 结果一律先转 bytes 再判空、再写盘。
11. **计时缓存原先在 serialize 之后才落盘**：序列化一失败，26 min 的 tactic 计时结果全部作废，
    重试又要从头搜一遍。改为**构建完成即落盘**（`_save_timing_cache` 提到 serialize 之前），
    并用 try/except 兜底——写缓存失败绝不能连累主流程。
12. **导出超时余量不足**：实测构建 1580 s，原 `EXPORT_TIMEOUT_S=1800` 只剩 220 s 余量，
    机器稍忙就会被判超时。放宽到 **2700 s**（45 min，≥1.7× 余量）；
    `p4-accept.sh` 轮询上限同步从 360×5 s 改到 540×5 s，与服务端对齐。
13. **单测盲区**：`src/p4-unit.py` 的 38 条里没有一条覆盖"serialize 结果转 bytes"这条路径——
    因为真机跑一次构建要 26 min，单测不可能真构建。补 6 条，用 `FakeHostMemory` 模拟。
    注意模拟必须**显式定义 `__bool__` 抛 TypeError** 才能还原真机行为：
    Python 对象在 `__bool__`/`__len__` 都未定义时 `bool()` 默认返回 **True**（不抛错），
    第一版模拟就因此漏判。→ 38/38 变 **44/44**。

### 21.4 验收结果（真机 103）

| 项 | 结果 |
| --- | --- |
| `src/p4-unit.py`（py3.8.10，含真机 arm.engine + yolov8n.onnx） | **38/38** |
| `console/p4-unit.py`（py3.8.10） | **50/50** |
| `p4-reload-check.sh`（复制 arm.engine→exports，切过去再切回） | **7/7**（reload_count 0→1，pending 清零，fps 16.2@构建中） |
| `p4-ui.sh`（playwright 真机） | **16/16**（卡片/kv/导出历史/徽标/按钮初态/workspace=1024） |
| `p4-accept.sh`（REUSE_ENGINE=exports/arm-copy.engine，跳过构建） | **32/32** |
| L4 上传：好 onnx（6.4 MB，classes=80，names 来自 onnx metadata） | ✅ |
| L4 坏文件：改扩展名 txt / 空文件 / 51 MB 超限 | ✅ 全拒（400/400/413），无残文件 |
| 类别清单不符（2 个 vs 80 类） | ✅ 400 不落盘 |
| 非法 engine 路径（`../../etc/passwd` / 不存在） | ✅ 400 / 404 |
| 认证：无 Cookie 401、写接口缺 `X-Yolo-Token` 401 | ✅ |
| **导出构建（fresh TRT build，未走 REUSE_ENGINE）** | ✅ **34/34，连跑两轮全绿**（2026-10-23 01:36 / 01:52） |
| fresh build 实测耗时 | **冷启动 1580 s（26 min）→ 温启动 130 s / 120 s**；产出 `yolov8n-*.engine` 8 260 403 字节（FP16 / 1 GB workspace / 80 类） |
| 导出完成后的完整链路 | ✅ 头解析 + 5 key + TRT 反序列化 + 重载闭环（`reload_count` 0→1，pending 清零，**重载后 fps 25.11**）+ 还原 arm.engine |

### 21.4.1 构建耗时为什么从 26 min 掉到 2 min

同一台机、同一个 onnx、同一套参数，冷启动 1580 s、之后两轮稳定 120~130 s。差在两处缓存：

1. **CUDA JIT 编译缓存**（`~/.nv/ComputeCache`）：第一次构建时 ptxas 要把大量 tactic kernel
   编译成 SASS，这在 **CPU** 上跑（与 §21.3 坑 6 的"6 核 100%、GPU 0~5%"完全吻合），
   编译产物落进 JIT 缓存后，后续构建直接命中。
2. **TRT 计时缓存** `model/exports/.trt-timing-cache`（697 KB）：tactic 实测结果，
   命中后跳过大部分 tactic profiling。

**运维结论**：`model/exports/.trt-timing-cache` 是**有价资产，别删**（本次清理测试产物时特意保留）。
它只对**同形状/同 opset 的同模型**有效；换模型（如 n→s）仍会有一次冷启动代价。
真需要更快时再考虑资源侧手段（停推理腾核 / 临时 MAXN），**代码侧已无提速空间**
（TRT 8.5 的 `min/avg_timing_iterations` 默认就是 1，`builder_optimization_level`、
`progress_monitor`、`max_timing_iterations` 在 8.5.2.2 的 Python API 里都不存在——已实测 `hasattr`）。

### 21.5 部署与回退

```bash
# 部署（PC 上执行；自动备份到 deploy/backup-p4-<ts>/ 并逐文件 md5 比对）
bash deploy/apply-p4.sh

# 生效：console 走 systemd；worker 走 PID 直管
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console.service
bash deploy/lite3-publish-ctl.sh restart yolo        # 约 35s 冷启动

# 回退（三步，互不牵连）
cp deploy/backup-p4-<ts>/console/server.py console/
cp deploy/backup-p4-<ts>/console/static/index.html console/static/
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console.service
cp deploy/backup-p4-<ts>/src/run_tracker_publish.py src/
cp deploy/backup-p4-<ts>/src/RobotController/YoloWrapper/YoloWrapper.py src/RobotController/YoloWrapper/
bash deploy/lite3-publish-ctl.sh restart yolo
# 数据面：model/exports/*.engine 与 model/uploads/ 可直接删；config 的 model.engine 改回
#   "../model/yolov8n_arm.engine" 且 pending_reload=false 即可
```

### 21.6 未闭环与风险

1. ~~**导出构建耗时（P4 唯一未闭环项）**~~ → **已闭环**（2026-10-23 完整 fresh-build 验收
   34/34 两轮全绿，见 §21.4）。
   **真正的失败原因不是"慢"，是 bug**：`engine.serialize()` 返回的 `IHostMemory` 不能
   `len()` / `bool()`，构建早在 1580 s 就成功了，却炸在写盘前一步（§21.3 坑 10）。
   之前三次"11~17 min 未完成"的排查全被这个假象带偏。
   **构建策略定稿**（按"不引入技术债 / 向后兼容 / 长时间运行稳定"三原则裁决）：
   - **不做**代码层自动切 `nvpmodel MAXN`——整机功耗与热稳定是运维决策，放进代码会留
     "忘了切回来"的债；
   - **不做**代码层自动 `stop/restart yolo`——worker 生命周期一旦由导出流程接管，
     就会引入状态机复杂度和"导出失败后 worker 没起来"的残留风险；
   - **接受"首次慢、之后快"为设计行为**：`EXPORT_TIMEOUT_S` 放宽到 2700 s（45 min，
     ≥1.7× 余量），保留 30 s 心跳 + 进度条，UI 明确写出"20~30 分钟"预期（纯文案，零逻辑）；
   - **需要更快时走运维手册**（人工执行，不改代码）：`ctl stop yolo` 腾核 → 导出 →
     `ctl start yolo`；极端情况再临时 `nvpmodel -m 0`，导完切回 20 W。
   - **保住 `.trt-timing-cache`**：这是把 26 min 变成 2 min 的关键资产（§21.4.1）。
2. **构建期间整机重启一次**（2026-10-22 10:28，构建进行到 3 min 时；journal 为易失存储，
   前一 boot 日志不可得，原因未定）。副作用：**意外验证了 console 开机自启**（systemd
   `enabled`，重启后 40 s 内 `/healthz` 200）——P1/P3 的「整机重启验证」遗留项由此关闭；
   worker 仍为 PID 直管，重启后不会自启（设计如此）。
3. ~~**PC 直连 103 的路由变了**~~ → **已闭环，裁决：不改默认白名单**（2026-10-23 复核）。
   根因是 PC 上那条**非持久化静态路由** `192.168.1.0/24 → 192.168.2.1` 丢了，于是流量改走
   默认网关 192.168.0.1，来源 IP 变成 `192.168.0.200` → CIDR 403。
   实测复核：路由重新加回后，`tracert 192.168.1.103` = `192.168.2.1 → 192.168.1.103`（两跳），
   **103 侧审计到的来源 IP 是 `192.168.1.120`**（120 对 `192.168.2.0/24` 做了 MASQUERADE），
   天然落在既有白名单 `192.168.1.0/24` 内，PC 从浏览器/API 登录均 200。
   **结论**：`console.allowed_cidrs` 保持 `['192.168.1.0/24']` 不变——不扩大暴露面（拒绝把
   `192.168.0.0/24` 办公网段列入），问题在网络层而不在鉴权层。
   运维要点（PC 重启/换网后若再次 403，先查这条路由）：
   ```powershell
   # Windows 管理员权限，加 -p 才是持久化（之前丢的就是没加 -p）
   route add 192.168.1.0 mask 255.255.255.0 192.168.2.1 -p
   ```
4. git 全部未提交（P0–P4 累计），待用户审阅后统一 commit；`config/yolo8.json` 与 `.bak-*`
   含令牌，P5 的 `.gitignore` 必须覆盖。

---

## 22. P4.5 执行记录（2026-10-23 02:00–03:30，存储治理 + 判活兜底）

> 编号说明：本轮是介于 P4（模型导出）与 P5（加固 + 长稳 + L0–L10 全量）之间的增量，
> 记为 **P4.5**；原 P5 编号与范围不变。
> 03:00 之后为 **P4.5b**：发现 purge 判活可被游离 worker 绕过，补兜底保护（§22.5.1）。

### 22.1 背景与三处泄漏

参照 `m20-ai-detect` 的 ADR-008（留存清理）与 ADR-011（数据清空）审计本项目，发现三处
只增不减的目录：

| 泄漏点 | 现状 | 对策 |
| --- | --- | --- |
| `pic/.trash/` | 有 `trash()` / `trash_list()` / restore，**没有清空接口**——软删除等于"换个地方永久保存" | `trash_keep_days` 到期清理 + purge 手动清空 |
| `logs/*.log`（4 个） | 裸追加，无 logrotate、无体积上限（实测 93 MB） | logrotate（daily / rotate 7 / compress）+ journald 限额 |
| `model/uploads/` `model/exports/` | 上传的 onnx 6.4 MB、导出的 engine 8.3 MB，用完仍留 | purge 按类清空，返回释放字节数 |

### 22.2 交付物（本地源副本 `lite3/docs/hosts/103-home-test-docs/`，md5 双侧一致）

| 文件 | md5 | 说明 |
| --- | --- | --- |
| `console/server.py` | `deb077db…` → `80f714d2…`（P4.5b） | 治理函数 + 两个 API + 周期线程；P4.5b 加 `worker_looks_alive()` 与 purge 409 拒绝分支 |
| `console/static/index.html` | `85ceab48…` | 「存储清理」卡（占用 / 勾选 / 清空） |
| `console/p5-unit.py` | `a08bc6e7…` → `2f183162…`（P4.5b） | 43 → 51 条纯函数单测（新增 T8 判活 8 条） |
| `console/p5-accept.sh` | `d8373eef…` | 真机验收 25 项 |
| `console/p5-ui.sh` | `ec75938b…` | 前端核对 17 项 |
| `deploy/lite3-yolo8.logrotate` | `e3b26d63…` | 日志轮换配置 |
| `deploy/lite3-yolo8-journald.conf` | `72eb3ad8…` | `SystemMaxUse=200M` / `MaxRetentionSec=7day` |
| `deploy/install-retention.sh` | `e7e40aec…` | 幂等安装 + `--check` |

（P4.5b 只改 `console/server.py` 与 `console/p5-unit.py` 两个文件；103 上旧版备份为
`console/server.py.bak-p45b-20261023`、`console/p5-unit.py.bak-p45b-20261023`。）

配置新增 `retention` 段（已写入 103 的 `config/yolo8.json`）：
`pic_max_mb=2048`、`pic_keep_days=30`、`trash_keep_days=7`、`prune_interval_s=600`；
**0 表示该维度不清理**（与 aiDetect 同语义）。

### 22.3 关键设计

1. **清理放在 console，不放在 worker**（本条有硬证据）：
   worker 不自启是既定设计（103 重启后只有 console 自启），而本轮验收期间确实出现了
   "worker 不在跑、状态文件停更 30+ 分钟"的时段（当时归因为"不明退出"，**后查明是
   `ctl stop` 的优雅退出 + purge 清空日志造成的误判，见坑 6**）。若清理挂在 worker 上，
   这类时段完全没人清理。console 是 systemd 常驻，只有它能保证清理持续执行。
2. **算法**：先按年龄、再按总量，**最旧优先**；单文件失败只记日志不中断
   （宁可漏删不可误删）——与 aiDetect `clean_saved` 同原则。体积上限只约束"在用图片"，
   `.trash` 单独按 `trash_keep_days` 治理。
3. **`.trt-timing-cache` 默认保护**：P4 实测它是把构建从 26 min 压到 2 min 的资产，
   误删代价是一次冷启动。purge 的 exports 类带 `keep_timing_cache`（默认 true）单独跳过它，
   页面文案写明"删了下次导出要回到 26 min"。
4. **日志用截断不用删除**：console/worker 是长驻进程持有 fd，unlink 只会让进程继续往
   已删 inode 写，磁盘一点不释放；`open(path,"wb")` 才是真释放。
5. **purge 三条铁律**（对齐 ADR-011）：目标白名单（值域不过 400 且不动文件）；
   涉及 pics/logs 时"原本在跑 → stop → 清 → start 恢复原状，原本没跑 → **绝不动服务**，
   状态无法确认 → 不碰服务直接清"；停止失败立即中止，此时一个文件都没删。
6. **判活兜底：宁可拒绝也不误清**（10-23 03:00 补，P4.5b）：`ctl` 判活只认 PID 文件，
   游离 worker（不经 `ctl start` 拉起）会被判成"未运行"，铁律 3 于是退化成
   "直接清"——等于在 worker 正写图时清空它。新增 `worker_looks_alive(state, stale_s=15)`
   （读 `logs/worker_state.json` 的 `_age_s`/`ts` + `worker.alive`），只在 purge 判活
   与 ctl 不一致时兜底：**返回 409 拒绝清理并提示先归一管理权**，绝不代用户 kill/start
   （避免误杀、避免起出第二个 worker）。审计记 `result:"reject"` + `worker_pid`。
7. **向后兼容**：`retention` 段缺失时全部回落默认（老 config 照常工作）；
   该段不在 `YOLO_SECTIONS` 里，在线改它 `needs_restart` 返回 `[]`
   ——实测改完 worker PID 不变（8434 未重启），不会误触发 35 s 冷启动。

### 22.4 踩坑

1. **logrotate 配了却不生效**：103 的 `logs/` 是 group-writable，logrotate 报
   `parent directory has insecure permissions` 并**跳过**该文件。必须加 `su <属主> <组>`。
   安装脚本按 `stat -c "%U %G"` 实际属主渲染这一行，并用 `logrotate --debug | grep ^error:`
   自检（现在 0 行）。
2. **`copytruncate` 是唯一选择**：console/worker 没有 SIGHUP 重开日志的逻辑，
   rename 那套会让进程继续写旧文件。
3. **部署脚本静默中止**：`apply-p4.sh` 备份时只建了 `src/` `console/` 子目录，
   没建 `deploy/` → `cp` 失败 → `set -e` 退出 → **后面的 scp 一行没跑**。
   靠 md5 比对才发现文件没上去。已补 `mkdir -p $BK/deploy`。
4. **purge 限流 10 s**：验收脚本连打 4 次拿到的全是 429。破坏性操作该严，
   但验收必须拉开间隔（脚本已改 `sleep 11`）。
5. **`p4-ui.sh` 的"导出记录非空"是脆弱断言**：它依赖"exports 里必须有 engine"这个
   外部数据，P5 清空 exports 后误报 FAIL。已改为有记录才校验行格式，否则 SKIP。
6. **"worker 不明原因退出"是误判（10-23 03:00 定案）**：连续两次看到 worker 死后无 OOM、
   无 Traceback，一度归因为"不明退出"。真相有两条，都出在诊断方法上：
   - ① **它是被 `lite3-publish-ctl.sh stop yolo` 优雅杀掉的**。日志最后一行是
     `stopping, frames=11822 det_frames=0 pushed=11788 elapsed=429.9s`——worker 收到
     SIGTERM 后的正常收尾统计，不是崩溃。而"死亡现场"的日志又被 purge 清空，
     于是证据链断掉，才显得"不明"。
   - ② **`ps -ef | grep yolo` 会漏判**：worker 是 `python3 -u run_tracker_publish.py`
     （`run-yolo-publish.sh` 用 `exec` 接管 PID），命令行里既没有 `yolo` 也没有
     `publish` 字样，只有 `grep -f run_tracker_publish` / `pgrep -af run_tracker_publish`
     才能匹配。用错关键字会得出"worker 没在跑"的错误结论。
   教训：**判断进程存活必须用真实进程名 + `ps -o lstart,etime` 对齐时间线**，
   并先确认日志是否被自己清空过。
7. **双 worker 抢占同一 rtmp key = 推流连环报错**：两个 worker 同时推
   `rtmp://…:1936/live/lite3_yolo`，SRS 会踢掉旧连接，于是看到
   `gst-resource-error-quark: Could not write to resource`，且
   `pipeline1→pipeline2→…→pipeline9` 一路递增（每次失败重建一条管线）。
   **杀掉多余 worker、只留一个，rtmp_state 立刻回到 `running`**。
   判据：`pushed_frames` 是否跟得上 `frames`（跟得上=推流正常）。
8. **`ctl` 判活只认 PID 文件，游离 worker 会让 purge 保护整段失效**：
   `lite3-publish-ctl.sh` 在 unit 未启用时走"进程直管"，判活靠 `logs/yolo.pid`。
   worker 若不经 `ctl start` 拉起（PID 文件缺失），`ctl status` 报"未运行"，
   purge 的"先停服再清理"就被跳过——**等于在 worker 正写 `pic/` 时直接清空它**。
   02:54 那次全量 purge 的 `service_restarted:false` 就是这么来的（当时 worker 16091
   其实活着）。修法见 §22.3 设计 7：判活兜底 + 拒绝而不是照清。
9. **`setsid nohup … &` 写在同一行里会被 shell 的 `&` 吞掉后续命令**：想"起一个后台
   进程再等一会儿"，务必写成独立脚本经 `ssh host 'bash -s' < 脚本` 下发；
   否则本地 SIGTERM 之后远程那条命令可能继续跑，**无意中起出第二个 worker**
   （03:11 与 03:16 就是这么出现双 worker 的）。
10. **worker 启动到第一次写 `worker_state.json` 要 ~2 min**（加载 engine + 打开 RTSP），
    期间 `/api/state` 里 worker 段显示的是上一个 worker 的旧数据。**不要用状态文件的
    新鲜度判断"新 worker 起没起来"**，要 `pgrep -af run_tracker_publish` + PID 文件。

### 22.5 验收结果（真机 103）

| 项 | 结果 |
| --- | --- |
| `console/p5-unit.py`（真机 py3.8.10 / 本地 py3.13 双跑） | **43/43** |
| `console/p5-accept.sh`（真机 API） | **25/25** |
| `console/p5-ui.sh`（playwright 真机） | **17/17** |
| P4 回归：`src/p4-unit.py` / `console/p4-unit.py` | **44/44** / **50/50** |
| P4 回归：`p4-accept.sh` fresh-build | **33/34**；唯一 FAIL 是 worker 已死导致，重启后 `p4-reload-check.sh` **7/7** |
| P4 回归：`p4-ui.sh` | **13 PASS + 1 SKIP**（0 FAIL） |
| 导出构建（P5 改动后复测） | ✅ **97.9 s**（温启动），日志新行正确显示"80 类 · 构建耗时 97.9s · workspace 1024MB · fp16=True" |
| 计时缓存保护 | ✅ purge exports 后 696 797 字节仍完好 |
| logrotate / journald | ✅ 均已安装，`logrotate --debug` 0 error |

最终状态：worker PID 16091 存活（fps 16.71、src/rtmp running）、console active、
config 指向 `yolov8n_arm.engine` 且 `pending_reload=false`、retention 已生效。

#### 22.5.1 追加：P4.5b 判活兜底（10-23 03:00–03:30）

动因：清理双 worker 时发现 02:54 那次全量 purge 的 `service_restarted:false`——
worker 16091 其实活着，只是没有 `logs/yolo.pid`，`ctl` 判活失效，**"先停服再清理"
整段被跳过**（坑 6/8）。若当时 pic/ 里是真实抓拍图，就被直接清空了。

| 项 | 结果 |
| --- | --- |
| `console/p5-unit.py` 新增 T8（8 条判活用例） | **51/51**（本地 py3.13 + 真机 py3.8.10 双跑） |
| `console/p5-accept.sh` 复跑（确认无回归） | **25/25** |
| 真机模拟"游离 worker"：purge pics | ✅ **HTTP 409**，错误含 PID 与归一指引；2 张测试图**一个没少** |
| 真机对照：purge uploads（不涉及 pics/logs） | ✅ 200 正常放行（保护不误伤） |
| 审计留痕 | ✅ `result:"reject"` + `reason:"unmanaged_worker"` + `worker_pid` |

清理双 worker 后的最终状态：**单 worker PID 21866**（`ctl` 管理，`logs/yolo.pid` 在），
`rtmp_state:"running"` 且 `pushed_frames` 与 `frames` 同步（12 fps，预热中）、
`ctl status yolo` 正常、console active。
**双 worker 抢占同一 rtmp key 是推流连环报错的真因**（坑 7），杀掉多余 worker 即恢复。

### 22.6 部署与回退

```bash
# 部署（自动备份到 deploy/backup-p4-<ts>/ 并逐文件 md5 比对）
bash deploy/apply-p4.sh
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console.service

# P4.5b 增量部署（只改 server.py + p5-unit.py，经 stdin 规避中文路径 scp 问题）
ssh lite3-f20-1-103 "cat > /home/test/yolo8/console/server.py"  < console/server.py
ssh lite3-f20-1-103 "cat > /home/test/yolo8/console/p5-unit.py" < console/p5-unit.py
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console.service
ssh lite3-f20-1-103 "cd /home/test/yolo8/console && python3 p5-unit.py"   # 期望 51/51

# 日志治理（幂等，可重复执行；--check 只看状态）
printf "\047\n" | sudo -S bash deploy/install-retention.sh
bash deploy/install-retention.sh --check

# 回退
#   1) 代码：cp deploy/backup-p4-<ts>/console/{server.py,static/index.html} console/...
#      → 重启 console；retention 段留着无害（老版本读不到它）
#   2) 日志治理：sudo rm -f /etc/logrotate.d/lite3-yolo8 \
#                       /etc/systemd/journald.conf.d/lite3-yolo8.conf
#      → sudo systemd restart systemd-journald
#   3) P4.5b：cp console/server.py.bak-p45b-20261023 console/server.py → 重启 console
```

**运维纪律（本轮新增，坑 6~10）**：

1. worker 只经 `deploy/lite3-publish-ctl.sh start yolo` 拉起，保证 `logs/yolo.pid` 存在
   ——游离启动会让 purge 判活失效（保护退化成"直接清"）。
2. 查 worker 用 `pgrep -af run_tracker_publish`（进程名里没有 `yolo` 字样）。
3. 同一时刻只允许一个 worker：双 worker 会互相踢 rtmp 连接（pipeline 编号递增）。
4. 起后台 worker 的脚本要独立文件经 `ssh 'bash -s' < 脚本` 下发，不要塞进
   带 `&` 的长命令行。

---

## 23. P4.6 执行记录（2026-10-24 02:00–02:30，控制台可用性改造）

> 动因（用户原话）：迁移前先把 Web 界面做一遍可用性优化——不只视觉，更要解决
> "有的按钮、有的进度条、有的文本框"的控件混用；卡片能折叠；常用数值能直接在页面上改。

### 23.1 控件语义规范（本轮定下的统一标准）

| 语义 | 控件 | 页面实例 |
|---|---|---|
| 布尔 | **开关 switch** | 抓拍启用、RTMP 启用、FP16、保留计时缓存、日志跟随 |
| 有范围的数值 | **滑块 + 数字框联动** | 检测置信度（0.05–0.95） |
| 无范围/精确数值 | **数字框 + 单位** | 留存天数、总量上限、每日配额、码率、workspace MB |
| 枚举 | 下拉 | 日志目标、日志行数 |
| 长文本 | 文本域 | 类别名清单 |
| 只读指标 | kv 文本（不假装可编辑） | 服务状态、PID、uptime |
| 危险操作 | danger 按钮 + 二次确认 | 清空所选、启停服务 |
| 耗时任务 | 进度条 + 阶段文案 + 可折叠日志 | 模型导出 |
| 结构导航 | **可折叠卡片 + 折叠后仍显示结论** | 全部 8 张卡 |

### 23.2 改动清单

| 改动 | 说明 |
|---|---|
| **卡片折叠** | 8 张卡全部可折叠；点标题栏切换；顶栏「全部折叠 / 全部展开」；状态存 localStorage，刷新后保持 |
| **折叠后不丢结论** | 每张卡标题右侧有摘要位：服务卡显示"运行中 / 未运行"，存储卡显示"合计 X"（有未保存改动时追加"未保存"） |
| **占用占比条** | 存储卡新增 5 行占比条；按"最大一类"归一（否则几十 KB 的小类永远看不见） |
| **留存策略内联编辑** | `pic_max_mb` / `pic_keep_days` / `trash_keep_days` / `prune_interval_s` 直接改，**不重启 yolo** |
| **快速设置内联编辑** | 检测置信度、抓拍开关 + 每日配额、RTMP 开关 + 码率 + 地址；**会重启 yolo（约 35s）**，弹二次确认 |
| **脏检测** | 改动才点亮保存按钮并显示"未保存"；有「还原」按钮 |
| **前端预校验** | 提交前按后端规则先兜一遍（阈值 0.05–0.95、配额非负整数、地址 `rtmps?://…`），别让用户等一个 400 |
| 组件化折叠 | `.icfg` 内嵌块（留存策略 / 快速设置）也可单独折叠 |

### 23.3 关键设计

1. **retention 段不触发重启，detect/snapshot/stream 会触发**——依据是 configlib 的
   `YOLO_SECTIONS = (source, detect, snapshot, stream, model, pic_dir)` 与 `needs_restart()`。
   所以两块内联编辑的提示语写得不一样，且快速设置必须二次确认。
2. **轮询回填不能打断输入**：状态 1s 轮询一次，若用户焦点正在某个输入框，则跳过该框的回填
   （否则光标被冲掉、值被改回去）。
3. **折叠用 JS 运行时增强**，不改动原有 DOM 层级：把 `h2` 之后的兄弟节点整体移进
   `.card-body`，`h2` 包进 `.card-head`。这样原有 id 与事件监听全部保留
   ——`p5-ui.sh` 17 项**零改动仍全绿**即证明。
4. **保留原只读文本**（`st-conf-days` 等 `<b>` 元素）不动，新编辑区是**增量**。
   避免破坏既有验收脚本，也保留"只读速览"与"可编辑"两种形态。
5. 点击标题栏时若命中 `button/input/select/textarea/label/a` 则**不折叠**，避免误触。

### 23.4 验收结果（真机 103）

| 项 | 结果 |
|---|---|
| `console/p46-ui.sh`（新增，playwright 真机） | **56/56** |
| `console/p5-ui.sh` 回归（P4.5 存储卡） | **17/17**（零改动） |
| JS 语法（`node --check`） | ✅ |
| 真实保存往返（留存间隔 600 → 660 → 600） | ✅ 值回填正确、产生 2 份配置备份、**worker PID 21866 未变**（证明 retention 不触发重启） |

### 23.5 踩坑

1. **断言写错比代码写错更常见**：首轮 52/53 的唯一 FAIL 是"取消计时缓存勾选后清空按钮仍可用"——
   实际按钮禁用才对（清空按钮的启用条件是"勾选了清空范围"，计时缓存只是选项不是范围）。
   改断言后 56/56。**遇到 FAIL 先怀疑断言**。
2. **Windows 下 `node --check` 找不到 Git Bash 的 `/tmp`**：要写到工作目录里的临时文件再检查。
3. **switch 的 input 不能用 `width:0`**：设成 38×20 + `opacity:0`，这样 playwright 仍能点到
   （playwright 只判 bounding box 非空与 visibility，不看 opacity）。
4. **占比条别按总量归一**：按"最大一类"归一，否则小类永远是 0 宽度。

### 23.6 回退

```bash
cp /home/test/yolo8/console/static/index.html.bak-p46-20261024 /home/test/yolo8/console/static/index.html
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console.service
```

> 本轮只改前端 `console/static/index.html`（+ 新增 `console/p46-ui.sh`），**后端未改动**。

---

## 24. P4.7 执行记录（2026-10-24 03:00–03:50，信息层级与布局评审）

> 本轮只改前端 `console/static/index.html`（+ 新增 `console/p47-ui.sh`，微调 `console/p46-ui.sh` 加一段归一化），**后端未改动**。
> 触发：用户要求"评审后台页面的信息层级和交互问题，包括各个卡片的长宽和布局"。

### 24.1 评审证据（先实测再改）

1280×720 视口下实测卡片尺寸，暴露出三个硬伤：

| 卡片 | 改造前实测 | 问题 |
|---|---|---|
| yolo / rosbridge / topics | 371×448 | 内容少却被拉伸，卡内 150~180px 空白 |
| config / model / storage | 371×**1232** | 是上面 2.75 倍，远超一屏，首屏全被重卡占满 |
| pics / log | 371×516 | 图片只有 371px 宽 |

根因：`.grid` 用 `auto-fit minmax(340px,1fr)`，默认 `align-items:stretch` 让同行等高，
而三张重卡高 1232px，把整行带到 1232px；且 8 张卡平铺不分主次、宽窄无差异。

### 24.2 改动清单

| # | 改动 | 解决什么 |
|---|---|---|
| 1 | 三列固定 `repeat(3,minmax(0,1fr))` + 响应式降为 2 列/1 列 | auto-fit 列数跳变、mono 长串撑破列 |
| 2 | 按信息层级拆 3 个分区：**运行概览** / **抓拍与日志** / **配置与维护** | 概览与深度操作不再平级 |
| 3 | 抓拍卡 `span2`（821px），日志卡 1 列（403px） | 图片要宽、日志窄列够读 |
| 4 | 同行等高（stretch）+ 卡内滚动区 `flex:1` 填满 + `max-height` 硬上限 | **既对齐又不空白、且滚动窗口真的能滚** |
| 5 | 重卡首访默认折叠（独立标志位） | 首屏就是一屏监控面板 |
| 6 | 页面级告警横幅 + "去启动"直达按钮（自动展开目标卡 + 滚动定位） | 原来 rosbridge 未运行的提示埋在话题卡里，滚过去就看不见 |
| 7 | 顶栏 sticky + 回到顶部按钮 | 分区后页面变长，折叠/退出始终可达 |
| 8 | `#app-view` 1180 → 1400 | 每列只有 370px 时配置树/日志都挤 |
| 9 | 清空范围加"自动/仅手动/logrotate"标注 | 用户问"这些的最大空间能配吗"，UI 没讲清 |
| 10 | 话题表两列均可收缩换行 | 长类型名把行挤出容器 |

### 24.3 关键设计

1. **滚动区必须同时有 `max-height`**：只写 `flex:1 1 auto` 不加上限，flex 会顺着内容无限长高
   （实测 logbox 被撑到 **3602px**、话题表 903px），grid 行高又被最高的卡带跑，滚动条永远不出现。
   `flex-grow` 负责"填满剩余不留空白"，`max-height` 负责"不超限、该滚就滚"，两者缺一不可。
2. **`.fill` 里不能写 `min-height:0`**：CSS Flexbox 规范规定 flex item 的自动最小尺寸
   （`min-height:auto`）只在其 `overflow` 为 `visible` 时才生效；既然有 `overflow:auto`，
   自动最小尺寸本就是 0。显式写 0 反而会盖掉各滚动区自己的 `min-height`
   （`.cfgtree` 200 / `.topics-table` 220 / `#logbox` 200 …），首轮验收就是这么 FAIL 的。
3. **分区类名不能用 `.sec`**：配置树渲染里已有 `.cfgtree .sec`（`renderConfig` 生成），
   撞车会让"每个配置小节"也吃到 `margin-bottom:22px`。故用 `.zone`。
4. **首访默认折叠不能用 `collapsedMap()` 判空**：用户全展开后 `saveCollapsed` 存的是空串，
   和"首次访问"无法区分，会导致每次刷新都被重新折叠。故用独立标志位
   `yolo8_card_defaults_done`。
5. **`p46-ui.sh` 加了一段归一化**：默认折叠改变了初始状态，测"点一下就折叠"前先统一展开。

### 24.4 关于"改了配置要不要手动重启"

机制上**不需要手动重启**：点「保存并重启 yolo」时 console 会自己调 `lite3-publish-ctl.sh restart yolo`。
原来的文案问题是标题写"（改了会自动重启 yolo，约 35s）"、按钮又叫"保存并重启 yolo"，
听起来像两个不同的重启时机。已统一为"（保存后自动重启 yolo 生效，约 35s，期间推流会断）"。

对照：**留存策略**段不在 `YOLO_SECTIONS`，改了立即生效、不重启 yolo —— 两块提示语因此不同，
这是有意为之，不是文案不一致。

### 24.5 关于"这些的最大空间能配吗"

| 清空项 | 自动清理 | 可配上限 | 说明 |
|---|---|---|---|
| 抓拍图片 | ✅ | `pic_max_mb` 2048MB + `pic_keep_days` 30 天 | 两个维度独立，0 = 不按该维度清理 |
| 回收站 | ✅ | `trash_keep_days` 7 天 | 补上"只进不出"的缺口 |
| 上传缓存 | ❌ | — | onnx 上传的临时副本，只能手动清 |
| 导出 engine | ❌ 且**不该有** | — | worker 正在用的 engine，删了直接断推理 |
| 日志 | logrotate | — | 每天轮转、留 7 份压缩档；UI 的"截断"是立即清 |

已在存储卡的清空范围逐项加标注（`自动` / `仅手动` / `logrotate`），不必再来问。

### 24.6 关于"推流 bps 要不要自己配"

**一般不用。** 默认 `rtmp_bitrate = 1000000`（1 Mbps），而当前输出只有 640×360@30fps，
1 Mbps 对它绰绰有余。校验范围 10 万~800 万 bps 是给更高分辨率留的余量。只有两种情况要动：

- 把 `out_width/out_height` 调大 → 按面积比例同步加码率；
- 推流卡顿 / 带宽紧张 → 调低（如 500000）。

### 24.7 验收结果（真机 103）

| 项 | 结果 |
|---|---|
| `console/p47-ui.sh`（新增） | **66/66** |
| `console/p46-ui.sh` 回归（P4.6 可用性） | **56/56**（零回归） |
| `console/p5-ui.sh` 回归（P4.5 存储卡） | **17/17**（零回归） |
| JS 语法（`node --check`） | ✅ |

改造后实测（1280×720）：

```
card-yolo=488  card-rosbridge=488  card-topics=488     ← 三卡像素级等高
card-pics=527  card-log=527                            ← 等高
topics-table: h=260  scrollH=901   [可滚动]
logbox:        h=380  scrollH=3600  [可滚动]
page=1509（原来重卡全展开时 >2400）
```

### 24.8 踩坑

1. **`flex-grow` 不等于"限高"**：`flex:1 1 auto` 只负责填满。滚动区缺 `max-height` 时
   flex 顺着内容长高，实测 logbox 3602px / 话题表 903px，滚动条一次都没出现过。
   **教训：滚动区 = `flex-grow`（填满）+ `max-height`（限高）+ `min-height`（保底），三件套。**
2. **`.fill` 的 `min-height:0` 会盖掉子元素 min-height**：规范上多余（overflow 非 visible 时
   自动最小尺寸本就是 0），写出来反而误事。
3. **类名撞车要查全仓库**：`.sec` 与 `.cfgtree .sec` 撞，`p47-ui.sh` 的"分区数 = 3"直接测出 11 个。
4. **断言要跟着设计走**：P4.7 第一版断言是 `align-items = start`，P4.7b 改成 stretch+fill 后
   必须同步改断言，否则测的是旧设计。

### 24.9 回退

```bash
cp /home/test/yolo8/console/static/index.html.bak-p47-20261024-030613 /home/test/yolo8/console/static/index.html
# 静态文件每次请求读盘，无需重启 console
```
