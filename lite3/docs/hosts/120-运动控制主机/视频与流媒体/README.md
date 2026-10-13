# 视频与流媒体

本目录记录 120 主机的相机采集、MediaMTX、RTSP 协议和 RTMP 外部转发。

| 文件 | 内容 | 使用方式 |
| --- | --- | --- |
| [实时流媒体服务分析.md](实时流媒体服务分析.md) | `rtsp_stream.service`、MediaMTX、GStreamer 与本机 `/test` 流 | 排查摄像头、端口或本机 RTSP 流时阅读。 |
| [实时流媒体应用代码分析.md](实时流媒体应用代码分析.md) | RTSP 协议、MediaMTX 运行与配置细节 | 进行协议级诊断或调整服务器配置前阅读。 |
| [实时流媒体转推流记录.md](实时流媒体转推流记录.md) | 本机 RTSP 到外部 RTMP 的实现、验证和管理方式 | 管理 `rtmp-forward.service` 或排查外部推流时阅读。 |

不要在 `rtsp_stream.service` 运行时手工启动第二份 `mediamtx`；它会与现有实例争用 RTP/RTCP 端口。
