# rtmp_1012 —— 双相机 RTSP → RTMP 推流

把 196 主机（**M20 Pro 的 AOS 运控主机**，hostname `aos`）上的两路 RTSP 流转换成 RTMP，推送到外部服务器。

> ⚠️ 2026-10-14 更正：原写「机器狗感知主机」不准确 —— 196 是 M20 Pro 三主机中的 AOS（运控），Lite3 的感知主机是 `192.168.1.103`。

| 通道 | 源（本机 MediaMTX） | 目标（外部 SRS） | CPU 亲和 |
|---|---|---|---|
| `m20pro-f`（前视） | `rtsp://127.0.0.1:8554/video1` | `rtmp://172.31.68.227:1936/live/m20pro-f` | 0,1 |
| `m20pro-b`（后视） | `rtsp://127.0.0.1:8554/video2` | `rtmp://172.31.68.227:1936/live/m20pro-b` | 2,3 |

> ⚠️ **前后视映射需确认**：`video1`/`video2` 分别对应哪一路相机尚未物理核实。
> 若反了，把 `config.env` 里 `STREAM_F_SRC` / `STREAM_B_SRC` 两行对调即可。

> **当前状态：已改造为「纯 remux」模式，CPU 仅 0.14 核（两路合计）。**
> 相机侧已改为输出 H.264（见第 8 节），中继不再转码。
> 实测 197.6% → **13.9% 单核**，降了约 14 倍。改造可一键还原（`patch/revert_h265.sh`）。
> 服务仍保持「安装但不自启」，需要时 `sudo m20video up`。

---

## 1. 为什么不能照搬 120 主机的方案

120 主机（`192.168.1.120:~/rtsp_stream/`）用的是**纯 remux**：

```
rtspsrc → rtph264depay → h264parse → flvmux → rtmpsink     # 零转码，CPU ~0
```

**前提是源为 H.264。** 196 这套完全不同：

| | 120 主机 | 196 主机 |
|---|---|---|
| 相机编码 | `mpph264enc`（H.264） | `mpph265enc`（**H.265**） |
| GStreamer | — | **1.16.3** |
| `flvmux` 支持 | `video/x-h264` | 仅 `video/x-h264`（**无 HEVC**） |

H.265 进 `flvmux` 依赖 **GStreamer 1.24+ 的 Enhanced RTMP**，1.16.3 完全没有；
目标端 SRS v5.0.213 也不支持 Enhanced RTMP HEVC。
所以 196 上 **H.265 无法直接封装进 FLV/RTMP，必须转码成 H.264**。

实测确认源编码（RTSP `DESCRIBE` 返回）：
```
a=rtpmap:96 H265/90000
```

> ### ✅ 120 主机（Lite3）实际部署状态 · 2026-10-17 23:2x 最新复核（已更正＋双机重启自启实证）
> 上面的「纯 remux 直推 172.31.68.227:1936」概念正确，实际由 **1 个系统级 + 1 个用户级** 服务拼成：
>
> | 层级 | 服务 | 作用 | 状态 |
> |---|---|---|---|
> | 系统级 | `rtsp_stream.service`（`enabled`） | 起本地 MediaMTX（:8554/:1935）＋ 相机经 `push_video.sh` 发布到 `rtsp://127.0.0.1:8554/test` | active（相机→本地 RTSP） |
> | **系统级**（2026-10-17 23:3x 由用户级迁入） | **`rtmp-forward.service`（`enabled`）** | `ExecStart=/home/ysc/rtsp_stream/rtmp_forward.sh`：本地 RTSP → `rtmp://172.31.68.227:1936/live/lite3` | **active running（真正的外推）** |
>
> - **自启动确实存在**：`~/.config/systemd/user/rtmp-forward.service`（`WantedBy=default.target`，已 symlink 到 `default.target.wants/`），且 `loginctl` 显示 **`Linger=yes`** → **开机无需登录即自启**。用户重启后推流自动恢复已**实证**。
> - ⚠️ 此前"120 无自启动 / 需 `enable streaming.service`"是**错误结论**——当时只查了系统级 `/etc/systemd`，**漏了用户级单元**（`grep /etc/systemd` 返回空正是线索）。系统级 `streaming.service`（`/home/ysc/.zetton/streaming.sh`）是**无关的厂商服务**，disabled 属正常，与外推无关。
> - **为何会停（✅ 已修复 2026-10-17）**：原单元带 `RestartPreventExitStatus=3`+`SuccessExitStatus=3` → 上游抖动时 `rtmp_forward.sh` exit 3 → systemd **不再重启、永久停推**（同 M20 旧病），只能靠重启拉起。**现已去掉该豁免**，改为 `Restart=always` + **`RestartSec=30`** 退避（实测 `RestartUSec=30s`）：瞬断 30s 内自动重连自愈，上游真宕机也只每 30s 重试一次、不空转。
> - **看门狗（✅ 2026-10-17 23:3x 随外推一并改为系统级）**：现由**系统级** `rtmp-conn-guard.timer`（30s）触发 oneshot `rtmp-conn-guard.service`，
>   **显式传参** `ExecStart=/usr/local/sbin/rtmp-conn-guard.sh rtmp-forward.service`。
>   ⚠️ **必须显式传参**——脚本 `DEFAULT_SVC` 候选为 `m20video/rtsp_stream`，120 上无 `m20video` 会**误选 `rtsp_stream`**
>   （不产生 `:1936`）→ 看门狗失效且僵尸时重启错服务；候选表也已补入 `rtmp-forward` 作双保险。
>   原**用户级** `rtmp-conn-guard-user.{service,timer}` 已停用禁用。
> - **修复后实测**：`rtmp-forward.service` enabled+active；上游 ESTAB `cwnd:447`（健康非僵尸）；用户级看门狗首跑 `status=0/SUCCESS`、`badcount=0`。
>
> #### ★ 2026-10-17 23:2x 双机重启后实况复核（最新，覆盖上面旧数字）
>
> 两台主机**均刚重启**（M20 `up 3min` / Lite3 `up 5min`），推流服务**全部开机自启并推流成功**
> —— 双机自启动配置均正确，无需人工干预。
>
> **Lite3（120，hostname `ysc`）· 单路 1280×720@30**
>
> | 层级 | 服务 | 作用 | 实测 |
> |---|---|---|---|
> | 系统级 | `rtsp_stream.service` | 起 MediaMTX（:8554/:1935/:8888）＋ `v4l2src /dev/video0 → mpph264enc → rtspclientsink rtsp://127.0.0.1:8554/test` | active + **enabled** ✅ |
> | **系统级** | **`rtmp-forward.service`** | `/home/ysc/rtsp_stream/rtmp_forward.sh` → `rtspsrc 8554/test → flvmux → rtmpsink rtmp://172.31.68.227:1936/live/lite3` | active + **enabled** ✅ |
> | 系统级 timer | `rtmp-conn-guard.timer` | 30s 周期盯 `rtmp-forward` 僵尸连接（oneshot service，**必须显式传参**） | active + enabled ✅ |
> | 系统级 | `streaming.service` | 无关厂商服务 | inactive + disabled（正常） |
> | ~~用户级~~ | `rtmp-forward.service` / `rtmp-conn-guard-user.timer` | **2026-10-17 23:3x 已迁移为系统级并停用** | inactive + disabled ✅ 防双推 |
>
> - 外推进程：`gst-launch-1.0 -e rtspsrc ... latency=200 ! ... ! rtmpsink ... live=1`（pid 3732，User=ysc，系统级托管）。
> - 上游：`192.168.0.197:60788 → 172.31.68.227:1936` **ESTAB `cwnd:294`**（健康，非僵尸）。迁移后**单实例**，无重复推流。
>
> **M20 Pro（AOS 196，hostname `aos`）· 双路 800×600@30**
>
> | 层级 | 服务 / 进程 | 作用 | 实测 |
> |---|---|---|---|
> | 系统级 | **`m20video.service`** | `relay` 链：`rtspsrc 8554/video1\|video2 → rtph264depay → h264parse → flvmux → rtmpsink 1936/live/m20pro-f\|m20pro-b` | active + **enabled** ✅ |
> | 系统级 timer | `rtmp-conn-guard.timer` | 触发 oneshot `rtmp-conn-guard.service`，盯 `m20video` 僵尸连接 | active + enabled ✅ |
> | 系统级 timer | `m20-log-rotate.timer` | 60s 扫描轮转（10MB×5、`copytruncate`、单路隐含 ≤60MB） | active + enabled ✅ |
> | 系统级 timer | **`cam-guard.timer`** | 触发 oneshot `cam-guard.service`（`/usr/local/sbin/camera-liveness-guard.sh`）：清理"假死 gst 管道" | active ✅（23:21:43 Succeeded） |
> | 厂商进程（**非 systemd**） | `push_video.sh` + `mediamtx` | `local` 链：`v4l2src /dev/video0,2 → mpph264enc → rtspclientsink 8554/video1,2`；mediamtx 由脚本内 `sudo ./mediamtx` 拉起 | 5×bash + 2×gst ✅ |
> | 车侧 | `basic_server.service` | 相机/雷达/GPS 供电开关等 | active，但 **enabled=disabled**（由厂商 `start.service` 拉起）⚠️ |
>
> - ⚠️ **不要因为 `mediamtx.service` 是 inactive 就判故障** —— 196 上 MediaMTX **根本不由 systemd 管**，
>   是 `push_video.sh` 内部直接起的（进程 root 1121 在跑）。
> - 权威状态入口 `sudo m20-video-ctl status` 实测：
>   ```
>   local.processes=6  local.gst=2  local.hls_video1=200  local.hls_video2=200  local.ready=yes  local.stuck=no
>   relay.unit=active  relay.processes=4  relay.target=172.31.68.227:1936  relay.target_tcp=yes  relay.enabled=enabled
>   ```
> - 上游双路：`196:56604`、`196:56610` → `1936` **ESTAB，cwnd 97 / 70**（健康）。
>
> #### ★ 访问要点（易踩）
> - **Lite3(120) 首选经 PC 的 `WLAN 3` 网卡（192.168.2.57）连其热点 `YSC-JYML-aw3bal-5G` → `ssh ysc@192.168.2.1`**
>   （p2p0，~10ms 直连，最稳）；备选 `ssh ysc@192.168.0.197`（wlan0 上联 Tenda，绕一层）。
>   `192.168.1.120` 是 eth1 LAN（另带 `192.168.137.120`），需静态路由，当前不走。
> - **M20 经 PC 的 `WLAN` 网卡（192.168.0.200）连 Tenda → `ssh user@192.168.0.196`**。
>   双网卡分工：`WLAN` = Tenda / M20，`WLAN 3` = Lite3 自身 AP。
> - 管理用户级单元必须先 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`，否则 `systemctl --user` 失败。
> - 196 WiFi 抖动：SSH 超时先重试，别急着判故障。

## 2. 本项目的做法

`config.env` 的 `SOURCE_CODEC` 决定走哪条链：

### `SOURCE_CODEC=h264`（当前，相机侧已改造）
```
rtspsrc → rtph264depay → h264parse config-interval=-1 → flvmux → rtmpsink
```
**纯 remux，零转码**，与 120 主机方案完全一致。实测两路合计 **13.9% 单核 / 0.14 核**。

### `SOURCE_CODEC=h265`（源还是 H.265 时的兼容模式）
```
rtspsrc(H265, tcp) → rtph265depay → h265parse
  → mppvideodec          ← Rockchip VPU 硬解
  → videoconvert
  → video/x-raw,format=I420   ← ⚠ 必须是 I420，不能是 NV12（见 6.5）
  → mpph264enc           ← Rockchip VPU 硬编
  → h264parse → flvmux → rtmpsink
```
实测两路合计 **197.6% 单核 / 1.98 核**。摄像机改为 H.265 前用的就是这条。

### 继承自 120 方案的优点
- **TCP 预探测**：每轮推流前先探测 `172.31.68.227:1936`，网络断了立刻失败重试，
  而不是让 `gst-launch` 卡在 TCP 超时里。
- **连续失败诊断快照**：连续 3 次探测失败 → 写诊断（`ip route`/网卡/TCP 会话/源流自检）
  → 以退出码 **3** 退出。保留了 120 的语义，可用 systemd drop-in 加
  `RestartPreventExitStatus=3` 复现「网络长期不可用则不再重启」。
- **`gst-launch -e`**：收到 TERM 时发 EOS，让 RTMP 端干净断流。
- **`flvmux streamable=true` + `rtmpsink location=... live=1`**，与 120 一致。

### 相比 120 方案的改进
- **看门狗**（见 6.2）—— 直接补上你自己笔记 §10.5 里指出的那个盲区。
- **源流在线探测**：源不在线时跳过启动 gst，不空转刷屏。
- **两路独立进程**，一路故障不影响另一路。
- **`gst` 重命名隔离**（见 6.4）—— 避免被上游相机服务的 `pkill` 误杀。
- **日志落文件 + 轮转**、PID 文件、`m20video` 命令行、systemd 单元。
- **`SOURCE_CODEC` 开关**：源换成 H.264 后一行退回零转码 remux。

## 3. 文件说明

```
/home/user/rtmp_1012/
├── config.env            # 全部配置（源/目标/编码/CPU/重连/看门狗/隔离）
├── rtmp_forward.sh       # 核心：单路推流器（自带重连循环 + 看门狗）
├── run_all.sh            # 前台拉起两路（供 systemd 使用）
├── start.sh / stop.sh    # 手动启停（不走 systemd 时用）
├── status.sh             # 状态 / CPU / 绑核
├── m20video              # 命令行入口 → /usr/local/bin/m20video
├── install_service.sh    # 安装 / 卸载 systemd 服务
├── systemd/
│   └── m20video.service
├── patch/                # 相机侧 H.264 改造（可一键还原，见第 8 节）
│   ├── push_video.sh.orig        # 原始脚本备份（md5 128191f3…）
│   ├── apply_h264.sh             # 应用改造
│   ├── revert_h265.sh            # 还原为 H.265
│   └── restart_camera.sh         # 重启相机服务（精确匹配，不误杀）
├── bin/rtmp-gst          # gst-launch-1.0 的重命名副本（见 6.4）
├── logs/                 # forward-f.log / forward-b.log
└── run/                  # PID 文件
```

## 4. 使用

### 命令行（推荐）

```bash
sudo m20video up        # 启动推流
sudo m20video down      # 停止推流
sudo m20video reset     # 重启推流
sudo m20video status    # 状态（含 CPU / 绑核 / 连接）
sudo m20video doctor    # 一键体检：源流 / 目标网络 / 进程 / 连接 / 最近错误
sudo m20video log f     # 跟踪前视日志（f 或 b）
sudo m20video enable    # 打开开机自启
sudo m20video disable   # 关闭开机自启
```

> `m20video` 非 root 运行时会自动 `sudo` 提权（会提示输入密码）。
> 想免密码可在 `/etc/sudoers.d/` 加一行：
> `user ALL=(root) NOPASSWD: /usr/local/bin/m20video`

### 安装 / 卸载

```bash
cd /home/user/rtmp_1012
sudo ./install_service.sh              # 装好，但不自启、不启动（默认，省 CPU）
sudo ./install_service.sh --autostart  # 装好并设为开机自启
sudo ./install_service.sh start        # 装好后立即启动一次
sudo ./install_service.sh uninstall    # 卸载服务与命令
```

### 不走 systemd

```bash
sudo ./start.sh     # 启动两路
./status.sh         # 看状态
sudo ./stop.sh      # 停止两路
```

## 5. 配置要点（`config.env`）

| 项 | 说明 |
|---|---|
| `SOURCE_CODEC` | **`h264`（当前）** = 纯 remux；`h265` = 硬转码（兼容旧源） |
| `PIX_FMT` | 仅 `h265` 模式生效，送进 `mpph264enc` 的色度格式，**必须 I420/YV12，不能 NV12**（见 6.5） |
| `BPS` / `BPS_MAX` | 目标/峰值码率，默认 2M / 2.5M |
| `GOP` | 关键帧间隔，默认 30。**不要设成 2**，会显著抬升码率 |
| `QP_MIN` / `QP_MAX` | 画质上下限，默认 12 / 45 |
| `CPU_F` / `CPU_B` | 绑核，默认避开相机采集占用的 4,5,6,7 |
| `LATENCY` | rtspsrc 抖动缓冲，默认 100ms（源在 loopback，抖动极小） |
| `WATCHDOG_*` | 看门狗周期/阈值/宽限期 |
| `CHECK_SOURCE` | 推流前是否探测源流在线 |
| `GST_BIN` | 隔离用的 gst 副本路径（见 6.4） |

改完配置：`sudo m20video reset`

## 6. 实测踩坑记录（全部为实测，非推测）

### 6.1 `drop-on-latency` / `queue leaky` 绝对不要加

最初照「低延迟」常规思路给管道加了 `rtspsrc drop-on-latency=true` 和
`queue ... leaky=downstream`。结果：**源流一断，管线就陷入 CRITICAL 报错风暴。**

三变体对照（同一源、同参数、各 2 分钟）：

| 变体 | 配置 | CPU | CRITICAL 数 |
|---|---|---|---|
| A | + `drop-on-latency` + `leaky` | 73.3% | **960,548** |
| B | **都不用**（现方案） | **10.2%** | **24** |
| C | + `drop-on-latency` + `leaky`，去 `videoconvert` | 71.6% | 967,021 |

报错形如 `gst_mini_object_unref: assertion 'mini_object != NULL' failed`，每秒上万条，
CPU 被单核打满，且**进程永不退出**。

原因：这是**转码中继**，不是播放器。播放器可丢帧保实时，中继丢帧就破坏 H.265
解码链，解码器产出无效 buffer 后整条管线崩坏。源在本机 loopback，本无抖动需追帧。

> 你笔记 §10.7 建议过 `queue leaky=downstream` —— **实测证明这条会引发雪崩，不要采纳**。

### 6.2 `rtmpsink` 远端断开后不会让 gst 退出（你笔记 §10.5 的盲区）

目标把连接关掉后 socket 变 `CLOSE-WAIT`，但 `gst-launch` **进程依然存活**、
`ps` 看着一切正常，实际一帧都没在推（CPU 从 13% 掉到 6%，无 ESTAB）。
120 靠 systemd 重启兜底，但进程不退出时 systemd 也不会重启。

**本项目对策：内置看门狗**。每 5 秒检查 gst 到目标 `host:port` 的 TCP 状态：
不是 `ESTAB`（CLOSE-WAIT/FIN-WAIT/不存在）或发送队列积压超 `STALL_SENDQ` → 计一次异常；
连续 2 次异常即判定失效，主动 kill 并重启管道。

### 6.3 上游相机服务会静默整树消失

实测两次遇到 `/opt/robot/scripts/board_resources/rtsp_service/` 的
`start_server.sh + push_video.sh` 整棵树消失（只剩 mediamtx 因被 init 收养而存活），
此时 `rtsp://127.0.0.1:8554/video1` 返回 404，两路转发器全部失去源。
dmesg 里对应 `uvcvideo: Failed to resubmit video URB (-1)`。

**排障第一步永远先确认源流在线**：

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8888/video1/index.m3u8
# 200 = 在线；404 = 上游推流端没了
```

本项目已内置源流探测：源不在线时跳过启动 gst 并周期重试，不刷屏空转。

### 6.4 上游服务会无差别杀掉所有 `gst-launch`

机器人的应用管理守护进程 `basic_server`（`/opt/robot/share/basic_server/bin/`）
在检测到相机流异常时会调用 `rtsp_service/restart.sh`，而该脚本里有：

```bash
pids=$(pgrep -f "gst-launch" 2>/dev/null)
[ -n "$pids" ] && kill -9 $pids        # ← 按名字杀，不分是谁的进程
```

**这会把本转发器的 gst 管道一起 SIGKILL 掉**，表现为推流每隔几分钟断一次。

对策（`config.env` 第 8 节）：把 `gst-launch-1.0` 复制成 `bin/rtmp-gst` 再调用，
argv[0] 不含 `gst-launch` 就匹配不到。`start.sh` 会自动创建并**校验非空且可运行**
（0 字节文件同样满足 `-x`，会让 gst 静默退出——实测踩过）。

> ⚠️ 操作这台机器时**命令行里不要出现 `push_video` 或 `v4l2` 字样**，
> 否则 `restart.sh` / `stop.sh` 里的 `pkill -f` 会把你自己那条命令也杀掉。
> 这类操作请写进脚本文件再运行。

### 6.5 `mpph264enc` 喂 NV12 会花屏 —— 必须用 I420

现象：推出去的画面是**绿紫横向条纹**（行步长错位）。逐级抓帧定位：

| 测试 | 管线 | 结果 |
|---|---|---|
| A | `mppvideodec` → RGB → PNG | ✅ 干净（**硬解没问题**） |
| B | `avdec_h265` 软解 → PNG | ✅ 干净 |
| C | `mppvideodec → videoconvert → **NV12** → mpph264enc` | ❌ 花屏 |
| D | `mppvideodec → videoconvert → **I420** → mpph264enc` | ✅ 正常 |
| E | `mppvideodec → **NV12** 直连 mpph264enc` | ❌ 花屏 |

即 **`mpph264enc` 在 NV12 输入下输出错位**（无论 NV12 来自 `videoconvert`
还是解码器原生）。换 I420 完全正常。

**代价**：`videoconvert` 做 NV12→I420 在本机 ARM CPU 上很贵 ——
`mppvideodec ! videoconvert ! I420 ! fakesink` 单这一级就 **99.5% 单核**；
`videoconvert n-threads=4` 反而更慢（225%）。换软解也一样（101.9%）。
系统里没有 RGA 硬件色彩转换元素（无 `rgaconvert`/`rkximageconvert`）。

**所以两路转码合计约 2 个 CPU 核**，这也是当时把本服务默认关闭的原因。

> **现状**：相机制式已改为 H.264（第 8 节），中继走纯 remux，本条已不再是瓶颈。
> 但**若你在相机侧用到 `mpph264enc`，仍然必须强制 I420** —— 相机侧脚本里
> 也加了 `video/x-raw,format=I420`，原因相同。
> 只有在 `SOURCE_CODEC=h265`（回退模式）时，本中继才会重新背上这 ~2 核开销。

## 7. 依赖与前提

- 必须以 **root** 运行：`/dev/mpp_service`、`/dev/rga` 权限为 `root:root 600`。
- 依赖本机已有 RTSP 服务
  `/opt/robot/scripts/board_resources/rtsp_service/`（mediamtx + push_video.sh），
  提供 `rtsp://127.0.0.1:8554/video1|video2`。**本项目不碰相机，也不改那套服务。**
- systemd 单元 `m20video.service`，默认 `disabled`。

## 8. 相机侧 H.264 改造（已实施，可一键还原）

**做了什么事**：把相机侧 `push_video.sh` 从 H.265 改成 H.264，
使中继从「硬转码」退化为「纯 remux」。

### 实测效果

| 指标 | 改造前（H.265 转码） | 改造后（H.264 纯 remux） | 变化 |
|---|---|---|---|
| m20video CPU | 197.6% 单核（1.98 核） | **13.9% 单核（0.14 核）** | **↓ 14.2 倍** |
| m20video 内存 | 29.9 MB | **14.3 MB** | ↓ 约一半 |
| 相机侧 CPU | 13.3% 单核 | 15.8% 单核 | ↑ 约 2.5 个百分点 |
| 系统总线 CPU | 43.7% | **14.9%** | ↓ 约 29 个百分点 |

净收益：**省下约 1.84 个 CPU 核**，代价是相机侧多 0.025 核。

### 改了什么（仅 3 处，都在 `push_video.sh`）

```diff
- ! jpegdec ! videoconvert ! mpph265enc $DEV_ENCODER_PARAMS ! h265parse config-interval=-1 !
+ ! jpegdec ! videoconvert ! video/x-raw,format=I420 ! mpph264enc $DEV_ENCODER_PARAMS ! h264parse config-interval=-1 !

- DEV_ENCODER_PARAMS="gop=2 header-mode=each-idr"
+ DEV_ENCODER_PARAMS="rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"
```

两处说明：
- **必须加 `video/x-raw,format=I420`**：`mpph264enc` 在 NV12 输入下会花屏（见 6.5），
  相机侧同样是这个编码器，所以同样要强制 I420。
- 原来 `gop=2` 且无码率控制，改为 `gop=30` + 2Mbps CBR，码率可控且更省带宽。

### 如何还原

```bash
sudo bash /home/user/rtmp_1012/patch/revert_h265.sh
```

还原脚本做四件事：① 用备份整文件覆盖（备份丢失时回退到反向 sed）；
② 校验 md5 与原始一致；③ 把 `config.env` 的 `SOURCE_CODEC` 改回 `h265`；
④ 重启相机服务与推流服务。**幂等，可反复执行。**

原始脚本备份：`patch/push_video.sh.orig`，**md5 `128191f3fecc7f4b1017ae57fc075c77`**。

### 重新应用（若被 OTA 还原）

```bash
sudo bash /home/user/rtmp_1012/patch/apply_h264.sh
```
脚本会先做状态判断：已是 H.264 则跳过；文件被外部改过则中止并提示，不会盲改。

### 风险提示

- 修改的是**打包文件**（`boardresources` 包），OTA/重装可能被还原 → 重跑 `apply_h264.sh` 即可。
- 本机 RTSP 流编码由 H.265 变 H.264，同画质码率约高 40%（800×600@30 场景影响很小）；
  若有其他消费端强依赖 H.265，需同步确认或改用 `revert_h265.sh` 回到转码模式。

## 9. 机器狗 Web 控制台（3000 端口）的管理

3000 端口跑的是机器狗自带的 **Node Web 控制台**，与 m20video 无依赖关系，
但**两者都会操作相机**，因此放在这里一起管理。

### 它是什么
| 项 | 值 |
|---|---|
| 进程 | `node /home/tank/m20/server.js` |
| 端口 | 3000（HTTP） |
| PM2 应用名 | `m20`（PM2_HOME=`/root/.pm2`，仅此一个应用） |
| 开机自启 | `pm2-root.service`（enabled）→ `pm2 resurrect` 读 `/root/.pm2/dump.pm2` |
| 作用 | 相机控制网页；`config.json` 里 `startScript` / `stopScript` 指向 `rtsp_service/start_push_video.sh` 与 `stop.sh` |

### 命令
```bash
sudo m20web off      # 停止并禁止开机自启（当前状态）
sudo m20web on       # 启动并恢复开机自启
sudo m20web status   # 查看状态（端口/进程/PM2 列表/dump 自启条目）
sudo m20web log      # 跟踪日志
```

### 为什么建议保持关闭
它的"启动相机"走的是 `start_push_video.sh`（`push_video` C++ 二进制 + `SM_USB_107X_*.json`），
与机器人自带 `push_video.sh` **争抢摄像头设备**。不使用时关掉反而更稳。

### 关闭方式与踩到的坑
用 surgical 方式：`pm2 stop m20` → `pm2 delete m20` → **`pm2 save --force`**，
保留 `pm2-root.service` 不动（dump 里没有条目，开机 resurrect 自然拉不起来）。

> ⚠️ **必须加 `--force`**：PM2 在进程列表为空时会跳过保存
> （`[PM2][WARN] PM2 is not managing any process, skipping save`），
> 此时 `dump.pm2` 仍保留旧条目，**开机照样会把它拉起来**。只发 `pm2 save` 是不够的。

### 复原
- 备份：`patch/dump.pm2.orig`（md5 `5e6ff85761a9e54efcdbccc55ef95d89`）
- 说明：`patch/web3000_restore_notes.txt`（含精确启动参数，备份丢了也能手工恢复）
- 一键：`sudo m20web on` —— 已实测可用（启动后端口 3000 监听、HTTP 200、dump 恢复自启条目）

### 安全性确认
`server.js` 里**没有任何 SIGTERM/SIGINT/SIGHUP 处理器**，
所以 `pm2 stop/delete` 不会触发 `stopScript`，**不会连带停掉相机**。
已实测：停用前后 video1/video2 源流一直在线。

## 10. 排障速查

| 现象 | 排查 |
|---|---|
| `m20video doctor` 里源流"不在线" | 上游相机服务挂了，见 6.3 |
| 日志 "目标网络探测失败" | `ping 172.31.68.227`；看日志里的诊断快照 |
| 日志 "推流进程退出" 反复出现 | 源流抖动，或上游 `restart.sh` 误杀（已用 6.4 隔离） |
| 日志 "看门狗: 判定推流已失效" | 目标把连接断了，正常自愈；频繁出现要查目标服务器 |
| 画面花屏/绿紫条纹 | 检查 `PIX_FMT` 是否被改成 NV12，见 6.5 |
| 远端拉不到流 | 确认推的是 `rtmp://...:1936/live/m20pro-f`（**1936 不是默认端口**） |
| 想复现 120 的"网络长期不可用则停推" | 加 drop-in：`RestartPreventExitStatus=3` |
