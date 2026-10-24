# rtmp_1012 —— 双相机 RTSP → RTMP 推流

把 196 主机（**M20 Pro 的 AOS 运控主机**，hostname `aos`）上的两路 RTSP 流转换成 RTMP，推送到外部服务器。

> ⚠️ 2026-10-14 更正：原写「机器狗感知主机」不准确 —— 196 是 M20 Pro 三主机中的 AOS（运控），Lite3 的感知主机是 `192.168.1.103`。

| 通道 | 源（本机 MediaMTX） | 目标（外部 SRS） | CPU 亲和 |
|---|---|---|---|
| `m20pro-f`（前视） | `rtsp://127.0.0.1:8554/video1` | `rtmp://172.31.68.227:1936/live/m20pro-f` | 0,1 |
| `m20pro-b`（后视） | `rtsp://127.0.0.1:8554/video2` | `rtmp://172.31.68.227:1936/live/m20pro-b` | 2,3 |

> ⚠️ **前后视映射需确认**：`video1`/`video2` 分别对应哪一路相机尚未物理核实。
> 若反了，把 `config.env` 里 `STREAM_F_SRC` / `STREAM_B_SRC` 两行对调即可。

> **当前状态（2026-10-19 01:2x 最新）：relay 已切回「纯 remux」模式（`TRANSCODE=false`）。**
> 相机侧输出 H.264（第 8 节），中继零转码直推，端到端延迟 ~100-150ms（与 Lite3 同构），
> relay CPU 从转码时的 93-94%/路 降至 ~4%/路。画质=相机源流（2Mbps/路）。
> 10-18 为修 WiFi 弱链路卡顿曾开启转码降压（`TRANSCODE=true`，见 §1.2），
> 10-19 链路恢复后关掉——转码的延迟代价（见 §1.3）大于收益。
> 服务已设为开机自启（10-17 实证双机重启自动恢复）。

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
> #### ★ 2026-10-18 02:3x relay 开启转码降压（修 RTMP 播出端卡顿）
>
> **症状**：本地 RTSP/HLS 拉流正常，服务器端看 RTMP 很卡、每次要刷新。
>
> **诊断结论**：M20 唯一出口是 p2p0 WiFi（连 Tenda 5G）。同位置对照实验 —— PC 走同一
> Tenda ping 服务器 max 11ms 纹丝不动；M20 ping 同目标 **max 74.9ms / mdev 12.4ms**
> （信号 -60dBm，比 PC 的 -28dBm 弱 32dB）。而双路相机实际码率 **4.83Mbps**（目标
> 2×2M，相机端 `qp-min=12` 在复杂场景下超配约 18%）把这条抖动链路顶到 TCP 反复重传
> 退避（实测 `rto:54.61s / cwnd:1 / retrans:8`，00:04 服务端还主动关闭过 video2）。
> 播放端缓冲有限 → 周期性欠载 → 卡；刷新只是重建缓冲。**本地 RTSP 走 127.0.0.1
> 回环不经过 WiFi，所以本地完全不卡**——这就是"本地正常、服务器端卡"的原因。
>
> **修法（不动厂商相机/mediamtx，本地画质不变，只压外推）**：`config.env` 设
> `TRANSCODE=true`，relay 管线变为：
> ```
> rtspsrc → rtph264depay → h264parse → mppvideodec(硬解)
>   → videorate 15fps → videoconvert I420
>   → mpph264enc(硬编 bps=1200000 bps-max=1500000 gop=15 qp-min=24 qp-max=45)
>   → h264parse → flvmux → rtmpsink
> ```
> 上线实测（02:34 重启后）：双路 gst 均含 `videorate framerate=15`+`mpph264enc bps=1200000`；
> **上行 604 → ~400-500 KB/s**；60s ESTAB 恒 2、Send-Q≈0、无管道重启；相机侧 PID 未变
> （厂商配置确实一行未动）；HLS 双 200。⚠️ **CPU ~85%/路**（`videoconvert` NV12→I420
> 无硬件转换，见 6.5；系统仍 48% 空闲）—— 若 0-3 核吃紧，降 `RELAY_FPS` 或只转一路。
> ⚠️ **`mpph264enc` 仅 root 可见**（`/dev/mpp_service` crw------- root）：user 身份
> `gst-inspect` 会误报"缺失"，别被骗；relay 以 root 跑所以能用。
> 回退：`TRANSCODE=false` + `sudo m20-video-ctl restart relay`。备份
> `*.bak-transcode-20261018-023400`。进一步降压可调 `RELAY_BPS`/`RELAY_FPS`/`RELAY_GOP`。
>
> #### ★ 2026-10-19 01:2x 关转码，回纯 remux（修推流延迟）
>
> **触发**：使用者反馈"M20 推流延迟比 Lite3 高"。逐项排查后确认**与算力无关**——
> 两台主机同为 **RK3588（8 核）**，Lite3 处理的源还更大（1280×720@30 vs M20 800×600@30）。
> 差异在管线：Lite3 外推是纯 remux（`rtspsrc→rtph264depay→h264parse→flvmux→rtmpsink`，
> 端到端 ~100-150ms），M20 当时开着转码。
>
> **转码管线的延迟构成**（分级缓冲估算，非播放端实测）：
>
> | 环节 | 延迟贡献 |
> |---|---|
> | `mppvideodec` 硬解 | 1-3 帧解码缓冲 |
> | `videorate` 30→15fps | 帧间隔 33→66ms，缓存 1-2 帧 |
> | `videoconvert` NV12→I420 | 单核 99.5%（6.5）——两路 relay 实测 93-94%/核；CPU 饱和时两个 `queue`（默认 `max-size-time=1s`）**堆积，这是延迟主因** |
> | `mpph264enc` 硬编 | 1-2 帧编码缓冲；`profile=high` 默认带 B 帧，播放端再多一层缓冲 |
> | 关键帧间隔 | `RELAY_GOP=15` 在 15fps 下 = **1.0s**（原 config.env 注释"0.5s"是按 30fps 误算，已修正；要 0.5s 应设 8） |
>
> 合计估算 300-600ms，与"体感明显迟于 Lite3"吻合。
>
> **链路已恢复**：`wifi-uplink-check.sh` 实测 mdev 2.6-9.1ms、0% 丢包、双路 cwnd≥97、
> 信号 -59dBm——10-18 转码针对的重传退避（rto 54s/cwnd 1）已消失，降压紧迫性不再。
>
> **动作**：`TRANSCODE=false` + `m20-video-ctl restart relay`。实测：
> 管线已为纯 remux（与 Lite3 同构）；relay CPU 93-94% → **3.5-4.8%**；双路 ESTAB、
> Send-Q≈0；上行 446KB/s ≈ 3.5Mbps（双路源流全速，remux 预期形态）。
> 备份 `config.env.bak-transcode-off-20261019-012425`（转码参数原样保留，`TRANSCODE=true`
> 即可整体恢复）。
>
> **何时再开转码**：`wifi-uplink-check.sh -q` 退出码 2（CRIT：丢包≥5% / mdev>15ms /
> rto>1s / cwnd<30）持续出现且播出端卡顿复现时。
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

`config.env` 的 `SOURCE_CODEC` + `TRANSCODE` 决定走哪条链：

### `SOURCE_CODEC=h264` + `TRANSCODE=false`（**当前**，纯 remux）
```
rtspsrc → rtph264depay → h264parse config-interval=-1 → flvmux → rtmpsink
```
CPU ~0，画质=源。链路质量好时用这个。

### `SOURCE_CODEC=h264` + `TRANSCODE=true`（转码降压，10-19 已关，见 §1.3）
```
rtspsrc → rtph264depay → h264parse → mppvideodec(硬解)
  → videorate 15fps → videoconvert I420
  → mpph264enc(硬编 bps=1200000 bps-max=1500000 gop=15 qp-min=24 qp-max=45)
  → h264parse → flvmux → rtmpsink
```
解码后降帧率+重编码再推。**厂商相机/mediamtx 一行不动，本地 RTSP/HLS 画质不变，
只压外推**。用于出口为弱 WiFi 链路的场景（背景见 §1.1）。CPU ~85%/路（0-3 核）。

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
├── wifi-uplink-check.sh  # 出口 WiFi 链路 vs 推流需求适配性检测（见第 11 节）
├── install_service.sh    # 安装 / 卸载 systemd 服务
├── systemd/
│   └── m20video.service
├── lib/
│   └── m20-log.sh           # 日志轮转库（10MB×5、copytruncate、flock）
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
| `SOURCE_CODEC` | `h264`（当前，相机侧已改造）；`h265` = 硬转码（兼容旧源） |
| `TRANSCODE` | **`false`（当前，10-19 切回）** = 纯 remux；`true` = h264 源也解码重编码再推（降压/降帧，延迟 +300-500ms，见 §1.3） |
| `RELAY_BPS` / `RELAY_BPS_MAX` | 仅 `TRANSCODE=true` 生效：外推目标/峰值码率，默认 1.2M / 1.5M |
| `RELAY_FPS` | 仅 `TRANSCODE=true` 生效：外推帧率，默认 15（源 30fps 减半） |
| `RELAY_GOP` | 仅 `TRANSCODE=true` 生效：外推关键帧间隔，默认 15（**15fps 下 = 1.0s**；要 0.5s 应设 8） |
| `RELAY_QP_MIN` / `RELAY_QP_MAX` | 仅 `TRANSCODE=true` 生效：外推画质上下限，默认 24 / 45 |
| `PIX_FMT` | 送进 `mpph264enc` 的色度格式，**必须 I420/YV12，不能 NV12**（见 6.5） |
| `BPS` / `BPS_MAX` | 仅 `SOURCE_CODEC=h265` 模式生效（相机侧 2M/2.5M，relay 不跟它走） |
| `GOP` | 仅 `SOURCE_CODEC=h265` 模式生效。**不要设成 2**，会显著抬升码率 |
| `QP_MIN` / `QP_MAX` | 仅 `SOURCE_CODEC=h265` 模式生效，默认 12 / 45 |
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

### ★ 2026-10-19 相机侧调查：帧率不如 Lite3 的完整归因

> ### ⚠️⚠️ 本节结论**已被彻底推翻**，保留仅为记录调查过程
>
> 下面写的"13~24fps 是硬件上限、软件无解、终极方案是换相机"**全部是错的**。
> usbmon 取证证明：相机严格 **30.0fps** 出帧、驱动也正常交付，丢帧发生在
> **GStreamer 管线反压**与**绑核撞 SCHED_FIFO 实时线程**。
> 修复后两路实测 **30.2 / 30.3fps、p95=p99=36ms、零 >150ms 卡顿**，已与 Lite3 同级，
> **换相机不再必要**。正确结论见本节后续
>「[★★ 决定性归因](#-决定性归因根因是gstreamer-反压--绑核撞车不是相机)」与
>「[★★★ 曝光真相](#-曝光真相两颗相机的-exposure_absolute-行为完全不同)」，
> 系统化的排查方法见 **§12**。

**缘起（当时的判断，其中有对有错）**：使用者反馈"M20 推流效果不如 Lite3，怀疑
Lite3 算力更高"。当时确认**与算力/relay 管线无关**（两台同为 RK3588；M20 外推已回
纯 remux，CPU 仅 ~4%/路）——**这部分是对的**；但把差距归到"相机硬件"是错的。

| 维度 | M20 | Lite3 | 当时的结论 | 现结论 |
|---|---|---|---|---|
| 相机 | Realtek SM_USB_107X ×2 | Sunplus LRCP F1080P | 不同款 → 差距根源 | 不是根源 |
| 实际帧率 | 13–24fps | 30.7fps | **硬件上限，软件无解** | ❌ **管线/绑核可解，已修到 30fps** |
| 分辨率 | 800×600 | 1280×720 | 画质差距 | 属实（可选升级） |
| 码率 | 0.9–1.5Mbps | 3.85Mbps | 画质差距 | 属实 |
| GOP | 1.5s → ~0.9–1.6s | 1.0s | 已优化 | 属实（现 0.67s） |

**当时的关键证据（解释错了）**：`jpegdec+mpph264enc` 只占 5.7% CPU/路（Lite3 占 37%
却跑满 30fps）。当时推断"管线负载轻 = 上游送不进帧"，**这个推理有漏洞**——
管线 CPU 低恰恰是因为**它在等下游（反压）**，不是"没活干"。
四种分辨率实测（均关 AE 后）都是同一节拍：

| 模式 | video1 | video2 |
|---|---|---|
| 800×600 | 16.6fps | 20.8fps |
| 640×480 | 16.6fps | 22.0fps |
| 848×480 | 19.2fps | 20.5fps |
| 1280×720 | 13.0fps | 23.7fps |

"所有分辨率都是同一节拍"这个现象**仍然有效**，但它证明的是**丢帧与数据量无关**
（否则 720p 应该更差），而不是"硬件固件特性"。真正原因见后续小节。

**已实施的相机侧改动**（`push_video.sh`，root 重启生效）：

> ⚠️ 下列 1、2 是**当时**的实施内容，其中曝光部分已被后续彻底改写
> （见「[★★★ 曝光真相](#-曝光真相两颗相机的-exposure_absolute-行为完全不同)」：
> 现为**分路配置**，video1 用 `exposure_auto=3`）。完整现状见 §12.3。

1. **关自动曝光**（当时）：`exposure_auto=1, exposure_absolute=166`。
   背景：AE=3 在弱光下曝光 32–168ms 动态抖动。关 AE 后帧率无质变
   （这一点后来被证实——**曝光确实与帧率无关**），"亮度稳定性提升"则**部分成立**：
   后相机该控件本就无效（走固件 AE），只有前相机会响应手动值，而手动 220 反而造成
   **21.6% 像素过曝**。现已改为分路：前相机自动、后相机保持手动值（无效但无害）。
2. **GOP 30 → 20**：**仍然有效并保留**。当时按 ~20fps 算得关键帧 ~1.0s；
   修复后实际 30fps，gop=20 = **0.67s**，优于 Lite3 的 1.0s。

**⚠ 重要操作变更：相机服务必须以 root 重启**。2026-10-18 23:59 机器重启后，
厂商 `start_server.sh` 以 root 接管相机（`/dev/video0` 为 `root:video 600`，
user 无权访问）。user 身份跑 `restart_camera.sh` 会**静默失败**（kill 全部 EPERM，
新树永远等不到设备）。正确姿势：`printf "'\n" | sudo -S bash patch/restart_camera.sh`。

**备份与回退**（都在 196 上）：

| 文件（196 上） | 内容 | 对应现状 |
|---|---|---|
| `.bak-ae-off-20261019-015621` | 原始版（H.264 改造 + gop=30，无曝光控制） | 可回退 |
| `.bak-gop30-20261019-021825` | 曝光版（AE 固定 + gop=30） | 可回退 |
| `.bak-noqueue-20261019-232000` | 加 queue 解反压**之前** | 回退即复现丢帧 |
| `.bak-affinity-20261019-233101` | video2 改绑核（6,7→0,1,2,3）**之前** | 回退 video2 掉到 21~27fps |
| `.bak-expprofile-<HHMMSS>` | 曝光分路配置**之前**（两路同 auto=1,220） | 回退前相机恢复 21.6% 过曝 |
| 本地 `patch/push_video.sh.current-h264` | **当前运行版**（md5 `db282b46…`） | 含改动 1–6 |

一键回退任意版本：`sudo cp <备份> /opt/robot/scripts/board_resources/rtsp_service/push_video.sh`
+ root 重启相机。**改前必读**：命令行禁含 `v4l2`/`push_video`/`gst-launch` 字样（会被
上游 pkill 误伤），一律"本地写文件 → scp → root 执行脚本"；脚本替换用
`install` + `mv`（换 inode），不要 `cp` 覆盖运行中的文件。

#### ★ 2026-10-19 02:41 补充：三路同条件对比实验（前/后相机 + Lite3 参照系）

起因：使用者反馈"改完还是卡 + 画面变模糊"。做同条件帧间隔对比
（M20 本机拉 HLS 22s，ffprobe PTS 分析；Lite3 分片经 PC 下载后同法分析——
**M20 与 Lite3 网络不相通**，ping 100% 丢包，Tenda 无跨网段路由）：

| 指标 | video1(前/Bus002) | video2(后/Bus007) | Lite3 |
|---|---|---|---|
| 平均帧率 | 14.2fps | **21.2fps** | **30.1fps** |
| p50 / p95 / p99 | 36 / 200 / 332ms | 32 / 100 / 168ms | 32 / 36 / 36ms |
| >100ms 丢帧 | 64 次(2.9/s) | 36 次(1.6/s) | **0** |
| >150ms 严重卡顿 | 29 次(1.3/s) | 9 次(0.4/s) | **0** |

三条结论：

1. **后相机(video2)全面优于前相机**（帧率 +49%、p99 减半、严重卡顿 29→9 次），
   坐实 Bus 002 的 USB 竞争拖累 video1；
2. M20 p50 仅 32–36ms（≈30fps 水平）但周期性趴窝，Lite3 p95=p99=36ms 零丢帧
   ⇒ 再次坐实"固件周期性 stall"归因，**换 F1080P 是唯一解**；
3. **「模糊」与本次改动无关**：baseline 与 current 分辨率(800×600)/码率(2M CBR)
   完全相同（唯一差别 gop=30→20 不影响清晰度）。模糊 = 低分辨率 + 固定曝光 166
   暗光偏暗 + 2M 码率三者固有。传输层次因：PC→M20 WiFi 实测 5% 丢包（均值 7ms）。

工具：`tools/compare_streams.sh`（三路对比）、`tools/fetch_lite3_segments.py`（Lite3 分片抓取）。

#### ★ 2026-10-19 02:47 混合分辨率实验（03:15 已回退，前后配置统一）

> ⚠️ **已回退**：03:15 使用者要求"前后摄像头配置统一"，video2 已回退到与
> video1 一致（800×600@2M）。以下保留实验记录，重启启用只需在
> `build_pipeline` 内恢复 video2 覆盖 if 块（脚本头部注释有说明）。

承接对比实验的使用者反馈（"还是卡 + 画面变模糊"），曾两项改动一次重启落地
（混合分辨率版 md5 `0ae0b167…`，root 重启生效）：

1. **曝光标定终值 220**（22ms）：166(16.6ms) 偏暗 → 300(30ms) 过亮 → 220 中间偏暗侧
   （过曝丢细节比欠曝难救；22ms 仍小于固件最小帧节拍 32ms 不挤压帧率）。
   针对暗光下"暗+噪点"观感发糊。仍偏暗可加大（260/300），偏亮减小（180）；
2. **video2 单独上 1280×720 + bps 3.2M**（`build_pipeline` 内按 stream_name
   覆盖；video1 维持 800×600@2M）：720p 像素量是 600p 的 1.92 倍，2M 会糊；
   relay 上行走 p2p0 WiFi（`ip route get 172.31.68.227` 证实），故保守取
   3.2M 而非 Lite3 的 3.85M。回退：删掉 build_pipeline 内 video2 覆盖 if 块。

**验证（02:51 同方法，改动前→后）**：

| 指标 | video1 | video2 |
|---|---|---|
| 平均帧率 | 14.2 → 16.7fps ↑ | 21.2 → 21.6fps ≈ |
| >150ms 严重卡顿 | 29 → 23 次 ↓ | 9 → **4 次（-56%）** ↓ |
| 分辨率/实际码率 | 800×600 / 1.5M | 800×600/1.56M → **1280×720 / 2.5M** ↑↑ |
| GOP | ~1.2s（帧率低所致） | **~0.93s** ✓ |

video2 帧率不降、严重卡顿大降、清晰度码率双升；曝光调整无帧率损失
（220 抽检 video2 达 23.8fps）。
备份：196 `/home/user/push_video.sh.bak-pre-mixed720p-20261019-025000`（720p+曝光300）、
`/home/user/push_video.sh.bak-exp300-20261019-030700`（720p+曝光300→220 前）、
`/home/user/push_video.sh.bak-v2-720p-exp220-20261019-031500`（720p+曝光220，
统一回退前的最后一版）。
**当前运行版**：两路统一 800×600@2M + 曝光 220 + gop 20（md5 `287c0b81…`，已被下节取代）。
**注意：M20↔Lite3 网络不通是常态**（ping 100% 丢包），compare_streams.sh 的
Lite3 路必然超时，参照系数据需经 PC 抓分片（fetch_lite3_segments.py）。

#### ★★ 2026-10-19 23:2x 决定性归因：根因是「GStreamer 反压 + 绑核撞车」，**不是相机**

> **本节推翻了此前"SM_USB_107X 相机遇帧率硬件上限、软件无解"的结论。**
> 两路现已双双达到 Lite3 水平：**30.2fps / p50=32ms / p95=p99=36ms / 零 >150ms 卡顿**。

##### 一、取证：相机和驱动都是完美的

用 `usbmon`（Bus002/Bus007 各抓 22s）+ UVC payload header 解析（`tools/usbmon_probe*.sh`、
`uvc_hdr_analyze.sh`、`uvc_fid_seg*.sh`）：

| 取证项 | 结果 | 含义 |
|---|---|---|
| usbmon URB 类型 | 5499 条全为 `Zi`（isoc），每 4ms 有 2–4KB | USB 数据流**完全连续**，无低载荷期 |
| UVC header | `bHeaderLength=12`、`ERR=0` | 无错误包、无固件报错 |
| **FID 分段** | **660 段/22s = 30.0 段/s，每段 32ms，100% 落 0–40ms 桶** | **相机严格 30fps 出帧，固件无 stall** |
| `uvcvideo/stats` | `errors=0 invalid=0`，两路各 **+150 帧/5s = 30fps** | 驱动正常交付 |
| GStreamer 实际输出 | **仅 13.8fps** | **丢帧发生在管线内部** |

结论：此前"MCU 周期性 stall / 两个相机不同步"的假设**全部不成立**。

##### 二、修复 1：加 queue 解反压（video1 就此达标）

原管线无 queue，是一条**全同步链**：`rtspclientsink → mediamtx` 任一环节阻塞，
反压会一路顶回 `v4l2src`，V4L2 缓冲耗尽即丢帧。在 `v4l2src` 后、`jpegdec` 后各插
一个 `queue max-size-buffers=3`（≈100ms 上限）解耦后：

- **video1：14.2fps → 30.0fps，p99=36ms，零卡顿**（一次性到位）

##### 三、修复 2：video2 绑核 —— 撞上了导航栈（本次最关键发现）

加 queue 后 video2 仍只有 21–27fps。逐层排除：

1. **单跑 video2**（`SIGSTOP` 冻结 video1）→ 25.6fps ⇒ 与两路争抢无关；
2. **驱动层** → 30fps、errors=0 ⇒ 相机/驱动仍正常；
3. **在线 taskset 迁移实验**（每档 15s，`tools/experiment_affinity.sh`）：

| video2 绑核 | irq122 | fps | p99 | >150ms |
|---|---|---|---|---|
| cpu6-7（原配置） | cpu6 | 27.6 | 164ms | 5 |
| cpu4-5 | cpu6 | 30.1 | 36ms | 1 |
| **cpu0-3** | cpu6 | **30.4** | **36ms** | **0** ★ |
| cpu6-7 | cpu0-2 | 23.5 | 326ms | 11 |
| video1 改绑 cpu6-7 | cpu5 | **22.4** | 400ms | 19 |

4. **关键判据**：把 irq122 移走后 video1 在 cpu6-7 仍暴跌到 22.4fps ⇒ 与 USB 中断
   亲和性**无关**；且 irq122 恢复默认 `0-7` 后双路仍 30.2fps 零卡顿 ⇒ **中断调优不需要**
   （此前"irq→cpu6 使 video2 改善到 26.2fps"是**测量噪声**，已作废）；
5. **揪出占用者**（扫 `/proc/*/status` 的 `Cpus_allowed_list`）：

   ```
   hsLidar          cpu=6-7    激光雷达点云
   height_map_nav   cpu=4-7    高程图导航
   lio_ddsnode      cpu=5-7    LIO 建图
   ```

   ⇒ **M20 的导航栈常驻占用大核 cpu6-7，而厂商原配置恰好把 video2 分给 cpu6-7**，
   属**出厂级资源冲突**。这不是相机问题，换相机也解决不了。

##### 四、最终配置与实测

```bash
DEV_AFFINITY_V1="4,5"       # video1：大核，与 lio/height_map 分时
DEV_AFFINITY_V2="0,1,2,3"   # video2：小核独占（原为 6,7，被导航栈占用）
```

| 路 | 帧率 | p50 | p95 | p99 | max | >150ms | 对比 Lite3 |
|---|---|---|---|---|---|---|---|
| video1 | 30.2fps | 32ms | 36ms | 36ms | 37ms | **0** | ✅ 等同（Lite3 30.1/36/36） |
| video2 | 30.2fps | 32ms | 36ms | 36ms | 40ms | **0** | ✅ 等同 |

HLS 双路 200、外推 1936 各 1 条连接正常。**当前运行版 md5 `986c2ced…`**。
备份：`/home/user/push_video.sh.bak-noqueue-20261019-232000`（加 queue 前）、
`.bak-affinity-20261019-233101`（改绑核前）。
回退：删两处 queue 片段；`DEV_AFFINITY_V2` 与 `DEFAULT_AFFINITY_V2` 改回 `"6,7"`。
新增工具：`tools/measure_two.sh`（单/双路帧率抖动测量）、`rebind_gst.sh`（在线迁核）、
`experiment_affinity.sh`、`exp_layout_c.sh`。

#### ★★★ 2026-10-20 曝光真相：**两颗相机的 `exposure_absolute` 行为完全不同**

> 推翻本节此前"曝光标定 166→300→220"整条链；
> 也推翻本文档早期版本写下的"exposure_absolute 是摆设"——**那只对后相机成立**。

**先说一个必须记住的坑**：UVC 每颗相机在系统里占**两个节点**，
**偶数=采集节点（video0/video2）、奇数=metadata 节点（video1/video3）**。
在 metadata 节点上下发 ctrl **完全不影响画面**（本节初测就栽在这里，
一度误判"前相机所有控件全失效"）。**设控件必须打采集节点。**

测法：直接对采集节点下发 ctrl，再从 RTSP 截帧算画面指标
（`scale=64:48,format=gray → rawvideo → 均值/饱和率`；工具 `v0_full.sh`、`v0_tune.sh`、
`exp_extreme.sh`、`bright_test.sh`）。

**① video2（后相机）—— `exposure_absolute` 无效**：

| 设置 | 读回 | 亮度 |
|---|---|---|
| `=3`（0.3ms） | 3 | 139.5 |
| `=300` | 300 | 139.8 |
| `=2047`（204.7ms） | 2047 | 139.8 |
| `exposure_auto=3` | — | **136.6** |

680 倍曝光跨度亮度零变化 ⇒ 该路固件不采用此控件，实际一直由 **固件 AE** 决定
（所以后相机画面正常、有层次）。`brightness/gamma` 在该路**有效**（brightness −64→64
亮度 36.4→189.6；gamma 100→300 亮度 102→251）。

**② video1（前相机）—— `exposure_absolute` 完全有效，且 220 就是过曝元凶**：

| exposure | 亮度 | 饱和(≥250) | 暗部(≤20) |
|---|---|---|---|
| 3 | 0.0 | 100% 全黑 | — |
| 100 | 152.8 | 0.2% | 3.0% |
| **220（原值）** | **201.7** | **21.6%** ❌ | 0.0% |
| 600 | 233.2 | 64.4% | — |
| 2047 | 248.7 | 84.6% | — |
| 手动 130 | 168.2 | 1.2% | 3.9% |
| **`auto=3`（现用）** | **132.9** | **0.0%** ✅ | 8.0% |

⇒ **"前后不一致"的真正病因**：两路参数表面完全相同（都是 `auto=1, 220`），
但**工作模式相反**——前相机是"手动 22ms 硬拍白墙"→ 21.6% 像素打爆、白墙一片死白；
后相机是"固件 AE 自动"→ 正常。**换相机不能解决问题，改曝光模式才能。**

**③ 修改（2026-10-20，脚本 `build_pipeline` 内按 `stream_name` 分路下发）**：

```bash
local exp_ctl="controls,exposure_auto=1,exposure_absolute=220"   # video2 保持
if [ "$stream_name" = "video1" ]; then
    exp_ctl="controls,exposure_auto=3"                            # video1 改自动曝光
fi
```

**效果（实测）**：前相机亮度 201.7→**132.9**、饱和 21.6%→**0.0%**、暗部 0%→8.0%
（白墙接缝/隔板边框/机身结构全部恢复细节）；后相机不变（102.3）；
两路亮度差由 **99 → 30.6**；帧率 **30.2 / 30.3fps、p99=36ms、零卡顿**（完全不受影响）。

**④ 连带结论**：
1. **AE 对推流帧率零影响**（`auto=1` 与 `auto=3` 均 30.3fps、p99=36ms）。此前
   "关 AE 是为了救帧率"不成立——真正救帧率的是 queue 与绑核。
2. 前相机保留手动曝光的唯一用法是**精确定值**（如 130 → 亮度 168、饱和 1.2%）；
   用 AE 则自适应光照，但亮度会随场景浮动。
3. 仍存在的差异是**物理的**：前相机装在本体前端拍到自己机身、视野 1–2m；
   后相机朝后、视野 8–10m。这部分改不了，除非动安装。

#### ★ 2026-10-20 播放端：SRS 上"必须刷新才同步最新画面"

先核对流名——**SRS 上实际只有 `m20pro-f` / `m20pro-b`**（relay 用
`rtmp_forward.sh f|b` 推），而 `m20pro-0` / `m20pro-1` **不存在**：

```
GET /live/m20pro-f.flv → 200，4s 下载 ~1MB（≈2Mbps，与 SRS 计一致）
GET /live/m20pro-0.flv → 000（无响应/连接失败）
```

SRS API（`http://172.31.68.227:1985/api/v1/streams/`）显示 f/b 均
`publish.active=true`、800×600 H.264、recv≈send≈2Mbps、`rob_bag` 无、clients=2。

**流本身是健康的**（直接 RTMP 拉流实测）：

```
570 帧 / 19.03 秒 = 29.95fps，帧间隔 28–36ms 连续，关键帧 29 个（GOP≈1.9s）
```

> 注意 SRS API 的 `frames` 字段会按客户端数累加（3 个客户端时显示 ~90fps），
> **不能当作真实帧率**，判断帧率必须拉流数帧。

⇒ "要刷新才同步"属于**播放端**行为，不是推流缺陷：URL 填了不存在的流名时，
flv.js 会停在最后一帧；即使流名正确，flv.js 默认不开启追帧
（`liveBufferLatencyChasing`），长时间播放会累积延迟。对策按优先级：
① 用 `m20pro-f` / `m20pro-b`；② 改 **WebRTC** 播放（SRS 已开，`nest`/`uav` 的 tcUrl
即 `webrtc://172.31.68.227/live`），延迟 <500ms；③ 用 VLC/ffplay 交叉验证是播放器还是流。
链路侧已排除：`ping 172.31.68.227` 0% 丢包、5.6ms，relay 日志无重连。

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
| **本地 RTSP 不卡但服务器端 RTMP 卡、要刷新** | 出口 WiFi 弱链路 + 码率超配：先跑 `wifi-uplink-check.sh`（§11）；确为链路 CRIT 且卡顿复现时开 `TRANSCODE=true`（见 §1.2/§1.3） |
| **服务器端 RTMP 延迟明显高于 Lite3** | 确认 `TRANSCODE=false`（转码管线 +300-500ms，见 §1.3） |
| 想复现 120 的"网络长期不可用则停推" | 加 drop-in：`RestartPreventExitStatus=3` |

## 11. 出口 WiFi 链路检测（`wifi-uplink-check.sh`）

**背景**：M20 唯一出口是 p2p0 WiFi，relay 外推 + 本地观看端（RTSP 8554 / HLS 8888 / WHEP 8889）
共用这一条上行。链路损伤时表现为"本地 RTSP 不卡、服务器端 RTMP 卡"（本地走回环不受影响）。

```bash
./wifi-uplink-check.sh      # 常规：结论 + 明细
./wifi-uplink-check.sh -v   # 详细：含 ping 逐包、每个观看端地址
./wifi-uplink-check.sh -q   # 安静：只输出一行结论（适合 cron/看门狗）
```

无需 root。退出码 0=OK / 1=WARN / 2=CRITICAL，可直接被脚本消费。

**检测项与阈值**（全部为 2026-10-18 实测标定）：

| 项 | 健康 | WARN | CRITICAL |
|---|---|---|---|
| 信号强度 | ≥ -50 dBm | -50 ~ -65 | < -65 |
| RTT 抖动 mdev（ping 服务器） | < 5ms | 5 ~ 15ms | > 15ms（卡顿时实测 12.4~38ms；同位置 PC 1~2ms） |
| ping 丢包 | 0 | < 5% | ≥ 5%（实测最差 60%） |
| 外推 TCP（1936 ESTAB） | cwnd≥30 无重传 | cwnd<30 或有重传累计 | rto>1s（卡顿时实测 54s） |

**观看端带宽代价**：每个本地观看端看的是相机端**源流**（~2 Mbps/路），与当前纯 remux
外推同价——1 个本地观看端 ≈ 1 路外推的出口代价（10-18 转码期间外推仅 1.2Mbps、
观看端贵一倍，10-19 关转码后该差异消失）。脚本会自动清点 RTSP/HLS/WHEP 三类终端
（排除回环，relay 自拉流不算观看端）。

**损伤定位法**（脚本之外，手工）：分别 ping **网关**和**目标服务器**——
若网关就丢包而 PC 同路径 0%，是 M20 的 WiFi 物理链路问题（信号/位置/干扰），
改配置无解，必须物理改善（挪近/天线/有线上联/换信道）。

---

## 12. 推流排查笔记：问题 → 证据 → 根因 → 方案（2026-10-19~20 复盘）

> **这一节是方法论索引**。§8 按时间线记录了全部原始数据，本节讲"下次遇到同类问题该怎么查"。
> 同期另有一份跨主机精简版：`lite3/docs/hosts/120-运动控制主机/视频与流媒体/实时流媒体转推流记录.md` §11。

### 12.1 六层归因模型（先定位层，再动手改）

```
① 相机 → ② 采集/编码 → ③ 源站(mediamtx) → ④ 中继(relay) → ⑤ 网络 → ⑥ 播放端
```

**判别法（本次最实用的一条）**：

| 现象 | 含义 | 指向 |
|---|---|---|
| p50 正常、p95/p99 爆炸 | 源头**缺帧**（某些帧从未生产/被丢） | ①②③ |
| p50 **整体**变差 | 传输**掉帧**（路上丢的） | ④⑤⑥ |
| 本地 RTSP 流畅、远端卡 | 出口链路或播放端 | ⑤⑥ |
| 各分辨率都是同一抖动节拍 | 与数据量无关 | ②（管线）而非① |

**剥离手法**：逐层拉流数帧（每层的 fps 都测一遍），**第一个出现帧率下降的层就是病灶**。
本次就是靠这个发现：相机 30fps → 驱动 30fps → **GStreamer 输出 13.8fps**，一步定位到 ②。

### 12.2 工具箱

| 工具 / 路径 | 测什么 | 关键读法 |
|---|---|---|
| `tools/measure_two.sh` | 单/双路 fps + p50/p95/p99 + >150ms 计数 | 判"源卡/路卡"第一步 |
| `/sys/kernel/debug/usb/uvcvideo/<x-x-x>/stats` | 驱动交付帧数、`errors`/`invalid` | 两次采样算增量；`errors=0` 说明 USB 干净 |
| `usbmon` + `tools/uvc_fid_seg*.sh` | 相机真实出帧（FID 分段） | 段数/秒=真实 fps；每段时长应≈33ms |
| `/proc/<pid>/task/*/sched` | **SCHED_FIFO 抢占** | `policy=2` 即实时线程，会抢普通进程 |
| `/proc/*/status` 的 `Cpus_allowed_list` | 谁占了哪些核 | 扫全系统找"我的核被谁占了" |
| `tools/cam_compare.sh` | 两路三层配置对比（硬件/控件/推流参数） | 判"配置是否真的统一" |
| `tools/v0_full.sh` / `v0_tune.sh` | 曝光控件有效性 + 细调 | 亮度/饱和率/暗部三项一起看 |
| `tools/srs_probe.sh` | 从 SRS 拉流数**真实**帧率 | 比 SRS API 的 `frames` 可信 |
| SRS API `:1985/api/v1/streams/` | 流是否存在、码率、客户端数 | ⚠️ **`frames` 会按客户端数累加，不能当帧率** |

### 12.3 本次改动总表（当前运行版 md5 `db282b46…`）

| # | 改动 | 效果 | 回退 |
|---|---|---|---|
| 1 | 曝光分路：video1 `auto=3` / video2 `auto=1,220` | 前相机过曝 21.6%→0%，亮度差 99→30.6 | `.bak-expprofile-*` |
| 2 | `gop 30→20` | 关键帧 1.0s→0.67s | 改回 30 |
| 3 | 两处 `queue max-size-buffers=3` | **video1 14.2→30.0fps**（解反压） | `.bak-noqueue-*` |
| 4 | video2 绑核 `6,7 → 0,1,2,3` | **video2 21~27→30.3fps**（避开 RT 线程） | `.bak-affinity-*` |
| 5 | 关闭转码回纯 remux（10-19 早些时候） | 外推延迟 −300~600ms，CPU 93%→4% | `config.env.bak-transcode-off-*` |
| — | 换相机 Sunplus F1080P | **已判定不必要**（问题不在相机） | — |

### 12.4 四个真实根因（症状 → 证据 → 根因 → 方案）

**① GStreamer 反压**（最核心）
- 症状：相机 30fps、驱动 30fps，GStreamer 只输出 13.8fps
- 证据：`uvcvideo/stats` errors=0；usbmon FID 660 段/22s=30.0fps；管线 CPU 仅 5.7%
- 根因：无 queue 的全同步链，`rtspclientsink→mediamtx` 一阻塞就反压回 `v4l2src`，V4L2 缓冲耗尽丢帧。**"管线 CPU 低"是它在等下游，不是没活干**
- 方案：`v4l2src` 后、`jpegdec` 后各插 `queue max-size-buffers=3`

**② 绑核撞上 SCHED_FIFO 实时线程**
- 症状：加 queue 后 video1 满 30fps，video2 仍 21~27fps
- 证据：`hsLidar` policy=2/prio=54 绑 cpu6-7、`lio_ddsnode` policy=2/prio=64 绑 cpu5-7；而 **cpu6-7 实测 busy 仅 1.5%**
- 根因：不是"核被占满"，是**实时线程周期性唤醒无条件抢占**普通优先级的 gst（2 秒采样根本抓不到）
- 方案：video2 迁到 cpu0-3（该簇无任何 RT 线程）→ 30.3fps

**③ 两路曝光工作模式相反**
- 症状：前后画面观感差很多，前相机白墙一片死白
- 证据：前相机 `exposure_absolute` 完全有效（220→饱和 21.6%）；后相机完全无效（3~2047 亮度恒定）
- 根因：两路参数都是 `auto=1,220`，但一个是"手动硬拍"、一个是"固件 AE"，**模式相反**
- 方案：按 `stream_name` 分路下发

**④ 播放端（非推流缺陷）**
- 症状：SRS 上"要刷新才同步最新画面"
- 证据：填的 `m20pro-0/1` **HTTP 000 不存在**（实际是 `m20pro-f/b`）；同时流本身 29.95fps 健康、链路 0% 丢包
- 根因：流名错 + flv.js 未开追帧导致延迟累积
- 方案：改用正确流名 / 换 WebRTC / VLC 交叉验证

### 12.5 被推翻的假设（别再走一遍）

| 曾以为 | 真相 |
|---|---|
| 相机硬件帧率上限、软件无解、要换相机 | 相机 30fps 完美，问题在管线与绑核，**已修好** |
| MCU 固件周期性 stall | usbmon 证明 FID 严格 30fps、零空洞、ERR=0 |
| 改 USB 中断亲和性能改善（26.2fps） | **测量噪声**；irq 恢复默认后双路仍 30.2fps |
| `exposure_absolute` 是摆设 | **只对后相机成立**，前相机完全有效（这点是关键分叉） |
| 关 AE 是为了救帧率 | AE 对帧率**零影响**，救帧率的是 queue + 绑核 |
| SRS 显示 90fps = 推了 3 倍 | 是 `frames` 按客户端数累加；实拉 29.95fps |
| 前后相机配置没统一 | 配置 100% 一致（连序列号都相同），差异在工作模式与安装位置 |

### 12.6 可复用铁律（下次开工前先看）

1. **先分层定位再改**，不要凭直觉换硬件。
2. **CPU 占用低 ≠ 没影响** —— 一定要查 `/proc/<pid>/task/*/sched` 的 `policy`（0=OTHER，2=FIFO）。
3. **单次测量可能是噪声**：帧率差异 2~3fps 要复测 2 轮再下结论。
4. **UVC 设控件必须打采集节点**：偶数 `video0/video2` 是采集，奇数 `video1/video3` 是 metadata，打错了完全不影响画面。
5. **在线改 ctrl 不等于生效**：部分控件要重启推流才应用，改完必须复测确认。
6. **相机服务必须 root 重启**（厂商以 root 接管 `/dev/video*`，user 跑会静默失败）。
7. **命令行禁含** `v4l2` / `push_video` / `gst-launch`（会被上游 pkill 误伤），一律"本地写文件 → scp → 执行脚本"。
8. **改前备份 + md5 双份核对**（本地 `patch/` 与 196 `/opt/robot/...`），脚本用 `install`+`mv` 换 inode 替换。
9. **不要 `SIGSTOP` 推流进程做实验** —— mediamtx 会踢 publisher，`SIGCONT` 后 gst 不自恢复，只能 root 重启。
10. **判断帧率必须拉流数帧**，别信服务端计数器。
