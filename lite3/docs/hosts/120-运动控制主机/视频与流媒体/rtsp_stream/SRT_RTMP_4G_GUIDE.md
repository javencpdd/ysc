# 4G/5G 公网图传改造指南

> 适用：`rtsp_stream` 项目（RK3588 + Rockchip MPP 硬编）
> 目标：把原本的局域网 RTSP 图传，改造成跑在 4G/5G 公网的远程图传
> 日期：2026-09-04

---

## 1. 先纠正一件事：RTMP 不是公网图传的好选择

原始问题是"能不能改成 RTMP"。能做，但在 4G/5G 下**不建议作为主链路**。

原因是物理性的，不是配置能救的：

| 协议 | 承载 | 4G/5G 丢包 1%~5% 时的行为 | 实测延迟 |
|------|------|--------------------------|---------|
| **SRT** | UDP + 选择性重传（ARQ） | 只重传丢的那个包，播放端几乎无感 | **200~500ms** |
| RTMP | TCP | 队头阻塞：丢一个包，后面所有数据都要等它重传完才能交付 | 1~3s，恶化时 10s+ |
| WebRTC | UDP + NACK/TWCC | 重传 + 自动降码率，最稳 | 100~500ms |
| HLS | TCP 分片 | 等整片下载完 | 5~20s |

**结论**：SRT 回传 + WebRTC 播放 = 业界无人机/机器人图传的标准组合。RTMP 保留给"必须对接只认 RTMP 的下游（如 CDN、录像平台）"的场景。

好消息：**你的两个服务器都已经编译好 SRT，不需要重新编译任何东西。**
- MediaMTX：`mediamtx.yml` 里 `srt: yes` / `srtAddress: :8890` 已经开着
- ZLMediaKit：编了 17MB 的 `libsrt.a`，配置里有 `[srt]` 段

---

## 2. 架构变化（重要）

局域网版和 4G 版的拓扑**不一样**，不是简单换个协议：

### 原来（局域网）
```
机器人: 摄像头→硬编→RTSP推本地 mediamtx:8554 → 客户端直连机器人
                    ↑ 机器人自己就是服务器
```

### 4G 版（公网）
```
机器人: 摄像头→硬编→SRT推公网服务器:8890    ← 机器人主动外连，穿透 NAT
                          ↓
              公网服务器 (MediaMTX/ZLMediaKit)
                          ↓
         ┌────────────────┼────────────────┐
       WebRTC            RTMP            HLS
     (监控台亚秒级)   (录像/CDN 转推)   (移动端兼容)
                    ↑ 机器人变成纯客户端，服务器在云端
```

**直接后果**：4G 推流场景下，**机器人端不需要跑 `start_server.sh`（本地 mediamtx）了**。只有需要"断网时本地录像兜底"才保留。

---

## 3. 前提条件

1. **一台有公网 IP 的服务器**（云主机即可，2 核 4G 足够转 1~2 路）
2. 服务器放行 UDP `8890`（SRT）与 TCP `1935`（RTMP，可选）、`8889`（WebRTC）
3. 机器人端 GStreamer 装了 `gst-plugins-bad`（提供 `srtsink` / `rtmpsink` / `mpegtsmux`）

第 3 条先验证，这是最容易卡住的地方：

```bash
./push_video_4g.sh probe
```

若 `srtsink` 缺失：
```bash
sudo apt install gstreamer1.0-plugins-bad
```

---

## 4. 端侧（机器人）使用

### 4.1 首次：插件自检
```bash
chmod +x push_video_4g.sh
./push_video_4g.sh probe
```

### 4.2 SRT 推流（推荐）
```bash
SERVER_IP=你的公网IP STREAM_ID=robot01 ./push_video_4g.sh srt
```

### 4.3 RTMP 推流（备选）
```bash
SERVER_IP=你的公网IP STREAM_ID=robot01 ./push_video_4g.sh rtmp
```

### 4.4 弱网降规格
信号差时降分辨率和码率，比死守 720p 更有用：
```bash
BITRATE=800000 WIDTH=640 HEIGHT=480 FPS=25 ./push_video_4g.sh srt
```

---

## 5. 服务端配置

### 5.1 MediaMTX（推荐，配置最简）

确认 `mediamtx.yml` 中：
```yaml
srt: yes
srtAddress: :8890
webrtc: yes
webrtcAddress: :8889
```

拉起后播放地址：
- WebRTC：`http://<服务器IP>:8889/robot01`
- RTSP：`rtsp://<服务器IP>:8554/robot01`
- HLS：`http://<服务器IP>:8888/robot01`

如果要鉴权，在 `pathDefaults` 或具体 path 下加 `srtPublishPassphrase`，并在端侧 `streamid` 中携带。

### 5.2 ZLMediaKit（若选它做服务端）

**注意一个坑**：根目录 `config.ini` 里 `[srt] port=9000` 与 `[shell] port=9000` **撞车**。必须改掉其中一个：

```ini
[shell]
port=0          ; 直接关闭调试 shell，生产环境本就该关

[srt]
port=9000       ; SRT 用 9000
timeoutSec=5
```

同时根目录 `config.ini` 缺 `[rtc]` 段，WebRTC 会走默认 8000，与 MediaMTX 的 `rtpAddress: :8000` 冲突。补一段：

```ini
[rtc]
port=8001
tcpPort=8001
timeoutSec=15
```

---

## 6. 参数调优

### 6.1 SRT `latency`（最关键）

这是 SRT 唯一需要认真调的旋钮，单位是毫秒。它决定了"最多愿意等多少毫秒来等重传"。

| 场景 | 建议值 | 说明 |
|------|-------|------|
| 有线 / 专网 | 100 | 几乎无丢包，追求极限低延迟 |
| 5G 信号良好 | 150~200 | 主流推荐起点 |
| 4G 一般 | **300** | 脚本默认值，抖动容错足够 |
| 4G 边缘 / 高铁移动 | 500~800 | 宁可延迟换流畅 |

调法：从 300 开始，若画面卡顿就往上加；若流畅但延迟高就往下减。**不要一次跳太多，每次 ±100 观察几分钟。**

### 6.2 编码参数

| 参数 | 建议 | 理由 |
|------|------|------|
| `bps` | 4G 用 1000000~1500000 | 4G 上行实测常只有 2~8 Mbps，务必留 40% 余量 |
| `gop` | 25~30（约 1 秒一个 I 帧） | I 帧越密，丢包后画面恢复越快 |
| `config-interval` | 1 | 每个 IDR 前插 SPS/PPS，客户端可随时中途加入 |
| B 帧 | 保持关闭（MPP 默认无 B 帧） | B 帧会引入额外依赖延迟 |

查看 `mpph264enc` 完整属性：
```bash
gst-inspect-1.0 mpph264enc
```

### 6.3 断线重连

`srtsink` 断线后 GStreamer 进程会退出，**脚本本身不自带重连**。生产环境务必用 systemd 守护：

```ini
[Unit]
Description=Robot Video Uplink
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=SERVER_IP=你的公网IP
Environment=STREAM_ID=robot01
ExecStart=/home/ysc/rtsp_stream/push_video_4g.sh srt
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

4G 拨号慢于系统启动，所以 `After=network-online.target` 是必须的，否则开机时会因无网络而反复重启。

---

## 7. 验证与排障

### 7.1 服务端是否收到流
```bash
# MediaMTX
curl -s http://127.0.0.1:9997/v3/paths/list     # 需先开 api: yes

# ZLMediaKit
curl -s http://127.0.0.1/index/api/getMediaList
```

### 7.2 本地快速验证（不依赖服务器）
起一个 SRT 监听端，用 ffplay 直接看：
```bash
ffplay -fflags nobuffer -flags low_delay srt://0.0.0.0:8890?mode=listener
```

### 7.3 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `srtsink` 找不到 | 缺 gst-plugins-bad | `sudo apt install gstreamer1.0-plugins-bad` |
| 连不上服务器 | 防火墙未放行 UDP 8890 | 检查云主机安全组 + `iptables` |
| 连上了但无画面 | 服务器 path 未匹配 | 检查 `streamid` 格式是否为 `publish:/<id>` |
| 画面频繁花屏 | SRT latency 太小或码率超带宽 | latency 加到 500，码率降到 800k |
| 延迟持续增大 | 码率超过实际可用上行带宽 | 降码率；SRT 无法突破物理带宽上限 |
| 开机后反复重启 | 4G 拨号未完成 | unit 里加 `After=network-online.target` |
| 脚本在 Windows 编辑后报 `bad interpreter` | CRLF 换行 | `sed -i 's/\r$//' push_video_4g.sh` |

---

## 8. 决策建议

| 你的情况 | 建议 |
|---------|------|
| 追求最低延迟、能接受服务端配 ICE | SRT 回传 + **WebRTC** 播放 |
| 要录像、要对接 CDN、下游只认 RTMP | SRT 回传，服务端转 RTMP；**不要让 RTMP 直接跑在 4G 上** |
| 只要能看、延迟不敏感 | SRT 回传 + HLS 播放，移动端兼容性最好 |
| 关键任务，链路不能断 | 4G + 5G 双模 bonding（成本高，需额外硬件/软件） |

**一句话总结**：把 RTMP 放在"机器人 → 服务器"这一段是错的位置。让它留在服务器端做下游分发，公网上行这一段交给 SRT。
