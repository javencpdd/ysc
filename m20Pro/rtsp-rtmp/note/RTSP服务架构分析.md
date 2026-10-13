# RTSP 服务架构分析（192.168.0.196 / aos）

## 1. 整体架构

```
┌─────────────── 192.168.0.196 (aos, RK3588-class, 8 核) ───────────────┐
│                                                                       │
│  /opt/robot/scripts/start.sh  (整机启动入口，无 systemd 托管)          │
│        └─► rtsp_service/start_server.sh                               │
│               ├─► sudo ./mediamtx          (MediaMTX v1.4.2, 服务端)   │
│               │      监听 8554 / 1935 / 8888 / 8889                    │
│               ├─► wait_time_sync()         等待 PTP/NTP 校时 (≤60s)    │
│               └─► push_video.sh            (推流端编排)                │
│                      ├─ stream_monitor video1  (CPU 4,5)  子 shell     │
│                      │     └─ gst-launch … rtspclientsink → :8554/video1│
│                      └─ stream_monitor video2  (CPU 6,7)  子 shell     │
│                            └─ gst-launch … rtspclientsink → :8554/video2│
│                                                                       │
│  ── 备选链路（当前未启用）──                                           │
│  start_push_video.sh  └─► ./push_video <config.json>                  │
│                             C++ 二进制：OpenCV 采集 + 去畸变 + appsrc   │
│                             目标 rtsp://192.168.0.198:8554/video1      │
└───────────────────────────────────────────────────────────────────────┘
```

**关键点：这是一个"本机自环"设计。** 推流端用 `rtspclientsink` 推给同机的 mediamtx，外部拉流者再从 mediamtx 拉。好处是解耦（摄像头重连不影响拉流地址），代价是多一跳转发。

## 2. 服务端：MediaMTX v1.4.2

配置文件 `mediamtx.yml`（22KB，绝大部分是注释）。实测使能情况：

| 协议 | 配置项 | 地址 | 实测端口 | 说明 |
|---|---|---|---|---|
| RTSP | `rtsp: yes` | `:8554` | **OPEN** | 主力协议，`protocols: [udp, multicast, tcp]` |
| RTMP | `rtmp: yes` | `:1935` | **OPEN** | **无人使用** |
| HLS | `hls: yes` | `:8888` | **OPEN** | lowLatency 变体，1s 分片 |
| WebRTC | `webrtc: yes` | `:8889` | **OPEN** | 低延迟网页拉流可选 |
| SRT | `srt: yes` | `:8890` | **closed** | 配置写了 yes 但没起来（该版本可能未编译 SRT） |
| API | `api: no` | `127.0.0.1:9997` | closed | **调试时强烈建议打开** |
| Metrics | `metrics: no` | `127.0.0.1:9998` | closed | — |

- **paths 段是空的**：只有一个 `all_others:` 且内部无内容，继承 `pathDefaults`。
- `pathDefaults.source: publisher` → 路径必须由推流端（publisher）建立，无人推时拉流会失败。
- `maxReaders: 0`（不限读者数）、`record: no`（不录像）。
- 超时：`readTimeout/writeTimeout: 10s`，`writeQueueSize: 512`。

## 3. 推流端：push_video.sh（当前生效版本，601 行）

这是被 `start_server.sh` 实际调用的版本，`org/push_video.sh`（38 行）是旧版备份。新版是一次完整重写，主要增强：

### 3.1 设备型号自适应
`detect_device_profile()` 用 `v4l2-ctl --info` 的 Card name 精确匹配，回退到 `lsusb` 全局匹配：

| 型号 | 分辨率 | 帧率 | 编码器参数 | CPU 亲和 |
|---|---|---|---|---|
| `SM_USB_107X` | **800×600** | 30 | `gop=2 header-mode=each-idr` | v1=4,5 / v2=6,7 |
| 未知（默认） | 1280×720 | 30 | `rc-mode=0 bps=1800000 bps-max=2000000 qp-min=12 qp-max=45` | v1=4,5 / v2=6,7 |

> ⚠️ **SM_USB_107X profile 缺码率参数**（详见风险清单），且分辨率 800×600 与 JSON 配置里的 1280×720 冲突。

### 3.2 设备漂移检测（最有价值的部分）
不是靠 `/dev/videoN` 编号，而是用 `udevadm info --query=path` 取**稳定 USB 物理路径**做绑定：

1. 首次分配时记录 `USB_PATH1/2`；
2. 重连时先按 USB 路径精确查找；
3. 等待 ≥15s 仍找不到 → 回退用 v4l2 设备名（`find_device_by_name`）匹配，命中则判定为**路径漂移**并更新绑定。

这解决了多 USB 摄像头插拔后 `/dev/video0`、`/dev/video2` 编号互换的经典问题。

### 3.3 每路独立监控 + 自愈
`stream_monitor()` 每路一个独立子 shell，互不干扰：

- **健康检查**：每 3s（`HEALTH_CHECK_INTERVAL`）检查 `_is_stream_alive()` —— 不只查 leader PID 存活，还校验 `gst-launch` 子进程及 `/proc/PID/cmdline`。
- **断联判定**：设备节点连续消失 3 次（`DEV_MISSING_THRESHOLD`，约 9s）才判定断联，避免抖动误判。
- **进程树清理**：`_kill_gst()` 先取 `pgrep -P` 子进程列表 → TERM leader → 等 2s → KILL → 按 `device=$dev` 模式补杀残留。**这是关键**（sudo 包装会导致 PID 追踪失效，脚本特意注释说明了不用 sudo）。
- **指数退避**：2→4→8→16→30s 封顶；连续稳定 5 次（`STABLE_THRESHOLD`）重置重试计数。
- **父进程兜底**：主循环监控两个 monitor PID，异常退出即重启。

### 3.4 GStreamer 管道
```
taskset -c <CPU> gst-launch-1.0 \
  v4l2src device=/dev/videoN \
  ! image/jpeg, width=W, height=H, framerate=F/1 \
  ! jpegdec ! videoconvert \
  ! mpph265enc <ENCODER_PARAMS> \
  ! h265parse config-interval=-1 \
  ! rtspclientsink location=rtsp://127.0.0.1:8554/<video1|video2> latency=10
```
- 摄像头直接出 **MJPEG**，省去 Raw 采集带宽；`jpegdec` 解码后走 Rockchip **MPP 硬编 H.265**。
- `h265parse config-interval=-1` 保证每个 IDR 前都带 SPS/PPS（旧版缺失此项，是个改进）。
- `latency=10` 低延迟模式。
- `taskset` 绑核：video1→核 4,5；video2→核 6,7，与算法/主控核隔离。

## 4. 备选链路：push_video（C++ 二进制，203KB）

**已不被主流程调用**（`start_server.sh` 直接调 `push_video.sh`），只有 `start_push_video.sh` 会用它，而后者无人调用。

`ldd` 结果揭示了它的职责：
```
libgstapp-1.0.so.0        → GStreamer appsrc 喂数据
libgstreamer-1.0.so.0
libopencv_videoio.so.4.2  → cv::VideoCapture 采集
libopencv_calib3d.so.4.2  → cv::undistort / initUndistortRectifyMap 去畸变
libopencv_imgproc.so.4.2
libopencv_core.so.4.2
```

所以它的工作方式是：**OpenCV 采集 → 按 JSON 里的 `camera_matrix` + `distortion_coefficients` 做畸变校正 → appsrc 推入 GStreamer → mpph265enc → rtspclientsink**。

配套 `SM_USB_107X_{0..3}.json` 定义分辨率、RTSP 目标、完整 pipeline_template 和相机内参。仓库根目录的 `lib/` 里打包了 OpenCV 4.13 运行库（与系统装的 4.2 并存，注意版本差异）。

> **定位：这是一条"带视觉预处理"的链路**，用于需要去畸变的下游算法；而 `push_video.sh` 那条是无预处理的直推链路。两者目标地址也不同（详见风险清单）。

## 5. 辅助脚本

| 脚本 | 作用 | 备注 |
|---|---|---|
| `start_server.sh` | 主入口；判 os_type；起 mediamtx；等 PTP 同步；调 push_video.sh | CA9B_VOS/GOS/NOS 三种固件直接退出，AOS 才继续 |
| `restart.sh` | `pkill -f push_video` → 杀 gst 残留 → 重新调 `start_server.sh` | 手动运维用；会连带重启 mediamtx |
| `stop.sh` | `pkill -f v4l2` + `pkill -f push_video` | **不杀 mediamtx**，只停推流 |
| `usb_ctl.sh` | GPIO 125 控制 USB  Hub 供电 enable/disable | 可用于硬复位摄像头；当前在 start 流程里**被注释掉了** |
| `wait_time_sync()` | 轮询 `timedatectl` NTPSynchronized，或 `date +%Y ≥ 2025` 兜底 | 超时 60s（`PTP_SYNC_TIMEOUT`）后仍继续启动 |
| `start.sh`（上级） | 整机启动：`ldconfig.sh` → `wifi/host_start.sh` → `start_server.sh` → 日志清理 | 后台 `&` 串行拉起，**无崩溃自动重启** |

## 6. 运行时实测状态（2026-10-12 06:35）

```
进程树：
  1026  start_server.sh
  1041   └─ sudo ./mediamtx
  1094   |    └─ ./mediamtx              ← 已运行 23 分钟，正常
  1578   └─ push_video.sh                ← 父监控
  1905      ├─ push_video.sh (video1 monitor)
  7473      │    └─ push_video.sh        ← 卡在 $(wait_for_usb_device) 子 shell
  30626     │         └─ sleep 1         ← 无限等待
  1907      └─ push_video.sh (video2 monitor)
  7478           └─ push_video.sh        ← 同上
  30576              └─ sleep 1
  30550   └─ sleep 3                     ← 父的主循环中
```

- ✅ mediamtx 正常运行，`8554 / 1935 / 8888 / 8889` 均 LISTEN。
- ❌ **没有任何 gst-launch 进程** —— 两路 monitor 全卡在等设备的死循环里。
- ❌ 根因：`ls -la /dev/video*` → `No such file or directory`；`lsusb` 只有 Root Hub、Realtek 无线网卡、ICS 有线网卡，**无摄像头设备**。
- `lsusb` 中不存在 `SM_USB_107X` 关键字 → 若此时启动，会走 Default profile（1280×720 + `rc-mode=0` 那套参数）。

**结论：服务框架健康，硬件未接。插上摄像头后 `wait_for_usb_device` 会自动检出并起流，无需重启服务。**
