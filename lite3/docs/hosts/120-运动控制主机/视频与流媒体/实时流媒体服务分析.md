# `/home/ysc/rtsp_stream` 深度分析

> 范围：启动脚本、当前 MediaMTX 配置、服务关系及媒体链路。媒体服务器及 ZLMediaKit 二进制/库不递归分析。

## 1. 结论与运行入口

`rtsp_stream` 是当前活动的视频发布模块。`rtsp_stream.service` 已 enabled 且 active，入口是：

```text
rtsp_stream.service
  -> /home/ysc/rtsp_stream/start_stream.sh
      ├─ start_server.sh -> sudo ./mediamtx
      └─ push_video.sh  -> sudo gst-launch-1.0 ... rtspclientsink
```

运行中的 MediaMTX 版本为 `v1.4.2`。视频链路从 `/dev/video0` 采集 1280×720、30 fps 的 MJPEG，解码和色彩转换后经 Rockchip MPP H.264 编码，发布到本机 `rtsp://127.0.0.1:8554/test`；`track` 服务消费该流。

## 2. 目录与未展开内容

| 位置 | 整体用途 | 跳过原因 | 项目定位 |
| --- | --- | --- | --- |
| `mediamtx` | MediaMTX v1.4.2 预编译媒体服务器 | 第三方可执行制品，不反编译 | 当前活动 RTSP/RTMP/HLS/WebRTC/SRT 服务端 |
| `mediamtx.yml` | MediaMTX 主配置 | 配置文件，读取关键服务项 | 当前活动服务器配置 |
| `ZLMediaKit/` | ZLMediaKit 二进制、静态/动态库、测试程序、Web 资产 | 第三方媒体服务器发行物，不逐文件展开 | 备用/历史媒体服务器方案，非当前 active 入口 |
| `log/`、`ZLMediaKit/log/` | 媒体运行日志 | 自动生成运行产物，不逐日志展开 | 排障记录 |
| `config.ini`、`ZLMediaKit/config.ini` | 历史/备用服务器配置 | 未由当前启动脚本引用，不深读 | 备用配置资产 |

## 3. 脚本清单与执行流程

| 脚本 | 参数/场景 | 执行流程 | 依赖/下游 |
| --- | --- | --- | --- |
| `start_stream.sh` | `rtsp_stream.service` 入口，无参数 | `cd /home/ysc/rtsp_stream`，后台启动服务器和推流脚本 | `start_server.sh`、`push_video.sh` |
| `start_server.sh` | 由 `start_stream.sh` 调用 | 以 sudo 执行本目录 `mediamtx` | 读取默认同目录 `mediamtx.yml` |
| `push_video.sh` | 由 `start_stream.sh` 调用 | GStreamer 从 `/dev/video0` 采集 MJPEG，`jpegdec -> videoconvert -> mpph264enc -> rtspclientsink` | V4L2、GStreamer、Rockchip MPP、MediaMTX `:8554/test` |

## 4. 关键配置与上下游依赖

| 配置/接口 | 当前值或行为 | 作用 |
| --- | --- | --- |
| `rtsp: yes`，`rtspAddress: :8554` | RTSP 服务监听所有地址 | 发布和读取 `/test` 流 |
| `protocols: [udp, multicast, tcp]` | 三种 RTSP 传输均允许 | 客户端可协商 UDP、多播或 TCP interleaved |
| `rtmpAddress: :1935` | RTMP 开启 | 附加媒体入口/出口 |
| `hlsAddress: :8888` | HLS 开启 | Web/HLS 播放入口 |
| `webrtcAddress: :8889`、本地 UDP `:8189` | WebRTC 开启 | 低延迟浏览器播放能力 |
| `srtAddress: :8890` | SRT 开启 | SRT 传输能力 |
| `paths.all_others` | 未定义专用 path | 所有未命中路径采用通用规则，因此 `/test` 可动态发布 |
| `track/config.json` | RTSP URI 指向 `rtsp://127.0.0.1:8554/test` | `track` 的视频上游依赖 |

`authMethods: [basic]` 仅说明允许的认证方式；是否要求认证仍取决于完整用户/路径配置，不能只凭该项断言外部访问一定需要认证。

## 5. 风险与维护建议

1. `start_stream.sh` 仅把两个子进程置于后台，systemd `Type=forking` 又不跟踪具体 PID；子进程单独退出时，service 状态未必能精确反映推流健康度。
2. 摄像头设备、分辨率、帧率、编码器、RTSP 路径都硬编码在 `push_video.sh`。设备枚举变化、相机格式变化或编码插件缺失会使推流失败。
3. 脚本在 systemd root 上下文中仍显式使用 `sudo`；这会增加环境和故障诊断的不确定性，应在维护时统一执行身份策略。
4. RTSP、RTMP、HLS、WebRTC、SRT 多个端口均开启；若热点或外部网卡可达，应依据实际需要收敛监听面和访问控制。
5. 不要同时启用 `.zetton/streaming.sh` 的备用 MediaMTX 与本目录服务；两者可能争用相机、端口或视频处理资源。

