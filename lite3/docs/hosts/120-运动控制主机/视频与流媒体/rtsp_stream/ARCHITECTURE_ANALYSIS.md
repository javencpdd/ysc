# rtsp_stream 项目架构分析报告

> 分析日期：2026-09-04
> 分析对象：120 主机 `/home/ysc/rtsp_stream` 部署目录的本地归档副本（2026-09-04 分析；归档原位于桌面 `特种机器人/rtsp_stream`）

---

## 0. 先行定性（重要）

这不是一个「代码项目」。目录内**没有任何自研源代码、没有 `.git`、没有构建系统（CMake/Makefile/go.mod/package.json）**。

它的真实身份是一个**流媒体服务的部署运行目录（runtime deployment bundle）**：

- 两个第三方开源流媒体服务器的**预编译 aarch64 二进制**
- 3 个 Bash 启动脚本（唯一的"胶水代码"）
- 2 份配置文件（ini / yml）
- 2 份历史运行日志 + 一批 HLS 切片残留

因此以下的"模块划分"指的是**部署单元与运行实体的划分**，而非代码包的划分。

---

## 1. 主要功能、业务目标与技术栈

### 1.1 主要功能

| 功能 | 实现载体 |
|------|---------|
| 摄像头采集（V4L2，MJPEG 1280x720@30） | `gst-launch-1.0 v4l2src` |
| 硬件 H.264 编码（Rockchip MPP） | `mpph264enc` |
| RTSP 推流上云/上服务器 | `rtspclientsink` |
| 流媒体接入与转发 | MediaMTX / ZLMediaKit |
| 多协议分发（RTSP / RTMP / HLS / WebRTC / SRT） | 同上 |
| HLS 切片落盘与回放 | ZLMediaKit `www/live/<app>/<stream>/` |
| REST 管控 API + Web 管理台 + Swagger | ZLMediaKit `index/api/*` |

### 1.2 业务目标

从目录名 `特种机器人` 与流水线设计可以还原出业务意图：

> **为特种机器人（巡检/排爆/侦察类）提供一路低延迟、可远程观看的实时图传通道。**

关键诉求推演：

- **低延迟** → 选 RTSP 与 WebRTC 作为主路径，HLS 仅作兼容兜底
- **低功耗 / 弱算力** → 强制走 `mpph264enc` 硬件编码，避开 CPU 软编（x264）
- **多端可达** → 同时开放 RTSP（地面站/VLC）、WebRTC（浏览器零插件）、HLS（移动端）
- **内网直连** → 配置里普遍放行 `192.168.0.0/16`、`10.0.0.0/8`，无鉴权

### 1.3 技术栈

| 层次 | 技术 | 版本/证据 |
|------|------|----------|
| 硬件平台 | aarch64（Rockchip 系，RK3588 类） | ELF `e_machine=183`；`mpph264enc` 为 Rockchip MPP 插件 |
| 操作系统 | Linux（Debian/Ubuntu 系） | 脚本路径 `/home/ysc/`，`sudo` |
| 采集编码 | GStreamer 1.0 + `v4l2src` + Rockchip MPP | `push_video.sh` |
| 流媒体 A | **MediaMTX v1.4.2**（Go） | 二进制内 ldflags `internal/core.version=v1.4.2`；依赖 `gortsplib/v4`、`gohlslib` |
| 流媒体 B | **ZLMediaKit**（C++11） | git hash `87cb488`，2024-02-19，build 2024-02-26 |
| 传输协议 | RTSP/RTP/RTCP、RTMP、HTTP-FLV、HLS、WebRTC、SRT | 双方配置 |
| 前端 | 原生 HTML + Vue2 + ElementUI + ECharts + axios | `www/webassist/` |
| 前端播放器 | ZLMRTCClient.js（WebRTC SDK，272KB） | `www/ZLMRTCClient.js` |
| 接口文档 | Swagger UI + OpenAPI 3 | `www/swagger/` |
| 编排 | Bash（无 systemd / 无 supervisor / 无容器） | `start_stream.sh` |

---

## 2. 目录结构与模块划分

```
rtsp_stream/                         总大小 ≈ 1.4 GB
├── config.ini                  [配置] ZLMediaKit 运行时配置（已被程序自动改写）
├── mediamtx                    [二进制] MediaMTX 主程序，27 MB，aarch64
├── mediamtx.yml                [配置] MediaMTX 全量配置
├── start_server.sh             [脚本] 启动 MediaMTX（sudo ./mediamtx）
├── push_video.sh               [脚本] GStreamer 采集+硬编+RTSP 推流
├── start_stream.sh             [脚本] 总入口，串起上面两者
├── log/                        [数据] MediaServer 运行日志（从根目录启动时产生）
└── ZLMediaKit/                 [模块] ZLMediaKit 完整发行包 ≈ 1.4 GB
    ├── MediaServer             [二进制] 主服务，105 MB
    ├── config.ini              [配置] 官方原始模板（未被改写）
    ├── default.pem             [证书] 默认 SSL 自签证书
    ├── libmk_api.so            [库] C API 动态库，105 MB
    ├── libzlmediakit.a         [库] 核心静态库，240 MB
    ├── libzltoolkit.a          [库] 基础工具库，33 MB
    ├── libext-codec.a          [库] 外部编解码器（H264/H265/AAC 等）
    ├── libmov.a / libflv.a / libmpeg.a / libsrt.a / libjsoncpp.a
    ├── test_* / api_tester_*   [测试] 14 个官方压测与 API 样例程序
    ├── bom / tab               [工具] 官方打包/构建辅助产物
    ├── log/                    [数据] 运行日志
    └── www/                    [前端] HTTP 静态根目录，35 MB
        ├── ZLMRTCClient.js     WebRTC 客户端 SDK
        ├── readme/             默认欢迎页
        ├── swagger/            OpenAPI 文档站（47 个 API）
        ├── webrtc/             WebRTC 播放/推流/回环测试页
        ├── webassist/          Vue2 + ElementUI 管理台（含 ECharts 负载图表）
        └── live/test/          HLS 切片残留（27 个 .ts，约 25 MB）
```

### 2.1 核心文件职责

| 文件 | 职责 | 关键内容 |
|------|------|----------|
| `push_video.sh` | **采集端**。唯一的媒体生产入口 | 生效行：`v4l2src /dev/video0`(MJPEG 1280x720@30) → `jpegdec` → `videoconvert` → `mpph264enc` → `rtspclientsink location=rtsp://127.0.0.1:8554/test latency=10`。第 1 行为注释掉的历史版本，推的是 `rtsp://127.0.0.1/live/test`（ZLMediaKit 554） |
| `start_server.sh` | 启动 MediaMTX | 仅 `sudo ./mediamtx` 一行。用 sudo 是因为监听 8554/1935 等端口（>1024 其实不需要，属多余提权） |
| `start_stream.sh` | **总编排入口** | `cd /home/ysc/rtsp_stream` → 后台拉起 server → 后台拉起 push_video |
| `mediamtx.yml` | MediaMTX 配置 | RTSP :8554、HLS :8888、WebRTC :8889、SRT :8890、RTMP :1935；`api=no` `metrics=no` `pprof=no`；`paths: all_others:` 通配放行 |
| `config.ini`（根） | ZLMediaKit 运行时配置 | 被 MediaServer 自动改写过（secret、mediaServerId）。**缺 `[rtc]` 段** |
| `ZLMediaKit/config.ini` | ZLMediaKit 原始模板 | 含 `[rtc]` 段；`shell.port=0`、`sslport=0`（已关闭） |

### 2.2 两个流媒体模块的分工

| 维度 | MediaMTX（Go） | ZLMediaKit（C++） |
|------|---------------|------------------|
| 定位 | 轻量、单一职责的**接入网关** | 重型、全能的**媒体服务器** |
| 二进制体积 | 27 MB | 105 MB（+1.3 GB 静态库） |
| 强项 | 部署极简、WebRTC/SRT 现代协议、配置清晰 | 协议最全、REST API 丰富（47 个）、录制/截图/转推/国标 RTP |
| 在本项目角色 | **RTSP 接入入口**（脚本实际指向它） | **多协议分发与管控中枢**（日志显示实际在跑） |
| 可观测性 | API/metrics/pprof **全部关闭** | HTTP API + Web 管理台 + Swagger |
| 鉴权 | `authMethods: [basic]` 但**未配任何用户** | `hook.enable=0`，`allow_ip_range` 全内网放行 |

---

## 3. 依赖关系、调用关系与数据流向

### 3.1 依赖方向

```
start_stream.sh
    ├──> start_server.sh ──> mediamtx 二进制 ──(读)──> mediamtx.yml
    └──> push_video.sh  ──> gst-launch-1.0 ──(依赖)──> v4l2 驱动 / Rockchip MPP
                                                    └─(网络)─> MediaMTX :8554

MediaServer ──(读)──> ./config.ini（相对路径，取决于 CWD！）
           ──(读)──> ./default.pem（同样取决于 CWD）
           ──(写)──> ./www/live/<app>/<stream>/  HLS ts 切片
           ──(写)──> ./log/YYYY-MM-DD_00.log
```

**关键依赖陷阱**：`MediaServer` 用相对路径读 `./config.ini` 与 `./default.pem`。
- 在 `/home/ysc/rtsp_stream` 下启动 → 读根目录 `config.ini`（无 `[rtc]` 段），且**找不到 `default.pem`**（日志证实 SSL 加载失败）
- 在 `/home/ysc/rtsp_stream/ZLMediaKit` 下启动 → 读子目录 `config.ini`，SSL 正常

### 3.2 调用关系

两条拓扑都实际运行过（由脚本注释状态 + 日志交叉验证）：

- **拓扑 A（脚本当前生效）**：`gst → MediaMTX:8554/test`
- **拓扑 B（历史 / 日志主证据）**：`gst → ZLMediaKit:554/live/test`，或 `MediaMTX ⇢（拉流代理）⇢ ZLMediaKit`

日志佐证（ZLMediaKit）：
```
11:25:29  RTSP播放器(__defaultVhost__/test/) 断开: rtsp推流url非法,最少确保两级rtsp url
11:25:58  stream: rtsp://127.0.0.1/live/test, codec info: mpeg4-generic[8000/1/16] H264[1280/720/30]
11:25:58  媒体注册 fmp4:// / rtmp:// / ts:// / rtsp:// __defaultVhost__/live/test
11:26:01  媒体注册 hls://__defaultVhost__/live/test
12:36:10  RTSP播放器(192.168.2.19:58236) 断开，耗时 39s   ← 局域网地面站拉流
12:36:10  RTSP推流器(127.0.0.1:44844) 断开，耗时 60s      ← 本机代理推入
```
注意 `mpeg4-generic[8000/1/16]` 这条静音音轨是 ZLMediaKit 因 `add_mute_audio=1` 自动补的，摄像头本身只有视频。

### 3.3 数据流向

```
[光信号] → 摄像头 USB/MIPI → V4L2 驱动 (MJPEG 1280x720@30)
   → v4l2src → jpegdec (MJPEG→YUV) → videoconvert → mpph264enc (YUV→H.264, 硬件)
   → rtspclientsink → RTSP ANNOUNCE/SETUP/RECORD → :8554/test  (MediaMTX)
   → MediaSource 注册 → RTP/RTMP/HLS/WebRTC 多协议复用
   → ZLMediaKit MultiMediaSourceMuxer（一路源 → 五路封装：rtsp/rtmp/ts/fmp4/hls）
   → 落盘 www/live/test/YYYY-MM-DD/HH/*.ts（约 900KB~1.4MB/3s ≈ 2.4~3.8 Mbps）
   → 播放端：RTSP 地面站（192.168.2.19）/ 浏览器 WebRTC / VLC / 移动端 HLS
```

**一路源、多协议扇出**是核心数据流特征：编码只发生一次（硬件），之后全是**封装层转换（remux）**，不二次转码 —— 这是低延迟与低功耗的关键。

---

## 4. 架构模式、设计原则与改进建议

### 4.1 架构模式

| 模式 | 体现 |
|------|------|
| **管道-过滤器（Pipes & Filters）** | GStreamer 的 `!` 链式管道，每级只做单一变换 |
| **Broker / 中介者模式** | MediaServer 作为媒体源的唯一注册中心（`MediaSource.cpp:517 emitEvent`），生产者与消费者完全解耦 |
| **扇出（Fan-out / 一源多封装）** | `MultiMediaSourceMuxer`：一路 RTSP 输入 → 5 路协议输出，零转码 |
| **配置驱动 + 约定优于配置** | 全部行为由 ini/yml 决定，无代码改动 |
| **前后端分离 + API 优先** | Swagger/OpenAPI 3 先行，Web 管理台与第三方系统共用同一套 REST |
| **Sidecar 式双服务器** | MediaMTX 与 ZLMediaKit 并列部署，各司其职（但也带来冲突） |

### 4.2 设计原则（原作者隐式遵循的）

1. **零转码优先** —— 只 remux 不 re-encode，把 CPU 占用压到最低，契合嵌入式场景
2. **能用硬件就用硬件** —— `mpph264enc` 而非 `x264enc`
3. **协议冗余覆盖** —— 不确定客户端能力就全开，四协议并存
4. **内网信任模型** —— 靠网络隔离而非鉴权换取零配置体验

### 4.3 已识别的问题

#### P0 — 端口冲突（双服务器同时启动必然打架）

| 端口 | ZLMediaKit | MediaMTX | 冲突 |
|------|-----------|----------|------|
| 1935/TCP | `rtmp.port=1935` | `rtmpAddress: :1935` | **是** |
| 8000/UDP+TCP | 缺 `[rtc]` 段 → 默认 8000 | `rtpAddress: :8000` | **是** |
| 9000/TCP | `shell.port=9000` **与 `srt.port=9000` 自身也冲突** | — | **内部冲突** |
| 443 / 332 / 80 / 554 | 需 root | — | 仅权限问题 |

#### P1 — 安全

1. **`api.secret` 明文硬编码**在 `config.ini`（32 位十六进制，已脱敏），任何人拿到配置即可调用全部 47 个管控 API（含 `kick_session`、`deleteRecordDirectory`、`setServerConfig`）
2. **零鉴权**：`hook.enable=0`、`allow_ip_range` 放行全部私网段、MediaMTX `authMethods: [basic]` 却未配置任何用户
3. **`sudo` 多余提权**：`start_server.sh` 用 sudo 启动 MediaMTX 监听 8554（>1024 无需 root），且 `push_video.sh` 也 sudo —— 一旦 GStreamer 插件被污染即以 root 执行
4. `apiDebug=1` 与 `dirMenu=1` 在生产环境暴露目录结构

#### P2 — 工程化缺失

1. **启动竞态**：`start_stream.sh` 先起 server 再立刻起推流，**无 sleep、无健康检查**，推流端会在 RTSP 服务就绪前连接失败
2. **无进程守护**：脚本用 `&` 后台化，进程挂掉不会自愈；无 systemd unit、无 supervisor、无容器化
3. **硬编码绝对路径**：`cd /home/ysc/rtsp_stream`，换机器/换用户即失效
4. **无日志轮转**：`log/YYYY-MM-DD_00.log` 与 HLS 切片只增不减，`segKeep=0` 意味着 ts 永不清理
5. **1.4 GB 测试产物未裁剪**：14 个 `test_*` 压测程序 + 数百 MB 静态库 + 25 MB 过期 ts 切片，对嵌入式存储是负担
6. **CWD 敏感**：配置文件与证书用相对路径，从不同目录启动行为不一致（日志已复现 SSL 失败）

### 4.4 扩展点与改进建议

#### 立即可做（低成本、高收益）

1. **消解端口冲突**：给 MediaMTX 与 ZLMediaKit 划分端口段，或在根 `config.ini` 补上 `[rtc]` 段并改 `port=8001`；把 `shell.port` 与 `srt.port` 分开
2. **明确主链路**：目前两套服务器职责重叠。建议二选一 —— 若要 Web 管理台/录制/截图/国标 RTP，就**只用 ZLMediaKit**（MediaMTX 降级为可选）；只要轻量转发就**只用 MediaMTX**，删掉 1.4 GB 的 ZLMediaKit，存储与维护成本骤降
3. **修复启动竞态**：`start_stream.sh` 里加端口探测循环等待 8554 就绪再推流
4. **清理发布包**：删除 `test_*`、`api_tester_*`、`.a` 静态库（只留 `libmk_api.so` + `MediaServer`）、`www/live/test/` 残留切片，体积可压到 150 MB 以内

#### 中期加固

5. **鉴权落地**：ZLMediaKit 开 `hook.enable=1` 接 `on_play` / `on_publish` 回调做令牌校验；MediaMTX 在 `pathDefaults` 配 `publishUser/publishPass`、`readUser/readPass`
6. **secret 外置**：`api.secret` 走环境变量注入，配置里只留占位符
7. **进程守护**：写 systemd unit（`After=network-online.target` + `Restart=always`），或容器化（`docker-compose` + `network_mode: host`，WebRTC 需要真实端口）
8. **日志与磁盘治理**：配 logrotate；`hls.segKeep` 设非零；加定时清理 `www/live/`

#### 业务扩展点

9. **多摄像头 / 多路图传**：当前只采集 `/dev/video0`。可扩展为按 `device=/dev/videoN` 起多条 pipeline 推不同 stream id（`robot/cam_front`、`robot/cam_rear`），ZLMediaKit 的 vhost + app/stream 两级模型天然支持
10. **边缘 AI 叠加**：在 GStreamer 管道里插入 `nvinfer`/`rknn` 推理插件（RK3588 有 NPU），做目标检测后再推流，或叠加 OSD 叠加层
11. **双向对讲 / 反向控制**：利用 ZLMediaKit 的 WebRTC DataChannel（`broadcastMessage` API 已就绪）下发机器人控制指令，把图传升级为"图传 + 遥操"
12. **弱网自适应**：MediaMTX 与 ZLMediaKit 均支持 WebRTC 的 REMB/TWCC 拥塞控制（`rembBitRate`、`start_bitrate`、`max_bitrate` 目前全为 0 即未启用），在无线链路下应打开
13. **断线续推与本地录像**：`record` 目前全关（`enable_mp4=0`、MediaMTX `record: no`）。野外作业建议开启本地录制作为链路中断时的兜底

---

## 附：关键事实速查

| 项 | 值 |
|----|----|
| CPU 架构 | aarch64（ELF e_machine=183） |
| MediaMTX 版本 | v1.4.2 |
| ZLMediaKit 版本 | git 87cb488（2024-02-19）/ build 2024-02-26 |
| 视频参数 | H.264 1280x720@30，约 2.4~3.8 Mbps |
| 音频 | 无（ZLMediaKit 补静音 AAC 轨） |
| REST API 数量 | 47 |
| 目录总体积 | ≈ 1.4 GB（ZLMediaKit 占 1.4 GB） |
| 源码/构建系统 | 无 |
| 版本控制 | 无 `.git` |
