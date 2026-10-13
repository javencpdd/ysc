# rtsp-rtmp — M20 196 主机流媒体链路资料

> 来源：`M20-pro/rtsp_rtmp/`（2026-10-12 现场工作镜像）+ 2026-10-14 主机只读复核补取。
> 覆盖三台主机的流媒体资产：**196（m20 AOS）现行方案**、**120（lite3 运动控制）参考方案**、以及 196 上交付的 `rtmp_1012` 项目。

## 目录结构

```
rtsp-rtmp/
├── README.md             ← 本文件
├── note/                 196 主机分析笔记与工程日志（6 篇）
├── tools/                现场诊断脚本（26 个，196/120 两主机通用）
├── sshx.py / s196.py     paramiko 免交互执行器（备用；密码走 SSHPASS 环境变量，不落盘）
├── 120/                  120 主机方案镜像（纯 remux 中继，2026-09-21 版）
├── 196/
│   └── rtsp_service/     196 主机相机侧代码镜像（仅文本资产）
├── project/
│   └── rtmp_1012/        交付项目本地镜像（m20video + m20gps + m20web + 协议客户端 + 补丁备份）
└── frames/               抓帧证据（9 张 PNG）
```

## note/ — 分析笔记与工程日志

| 文件 | 内容 |
|---|---|
| `README.md` | 笔记总索引、连接方式、一句话结论 |
| `RTSP服务架构分析.md` | 整体架构、数据流、进程模型、逐脚本解读、运行时实测状态 |
| `配置差异与风险清单.md` | 三套 RTSP 目标地址不一致、编码器参数分歧、潜在 Bug、安全建议 |
| `m20video-双相机RTMP推流项目.md` | 新建项目：与 120 方案异同、四个实测踩坑、交付物、H.264 改造、3000 服务管理 |
| `m20-GPS获取方式.md` | GPS 数据链路、四条获取途径、实测 NMEA 证据、`m20gps` 工具 |
| `196主机工程日志-20261012.md` | 当天工程流水账（SSH 打通、协议逆向、PM2 停用、性能实测，已脱敏；含 10-14 复核补记） |

## 196/rtsp_service/ — 相机侧代码镜像

主机位置 `/opt/robot/scripts/board_resources/rtsp_service/`。**仅收文本资产**；
`mediamtx`（27MB）、`push_video`（C++ 二进制）、`lib/`（OpenCV 16MB）未入库，需要时从主机获取。

| 文件 | 说明 |
|---|---|
| `push_video.sh` | **现行版**（2026-10-14 复核，md5 `b41fa9b3…`，601 行，H.264 补丁生效） |
| `push_video.sh.orig-h265` | 改造前原版（md5 `128191f3…`），一键回退用 |
| `mediamtx.yml` | MediaMTX 全量配置（RTSP 8554 / RTMP 1935 / HLS 8888 / WebRTC 8889 / SRT 8890） |
| `SM_USB_107X_*.json` | USB 相机 profile（×4，含 rc-mode/bps 码率参数） |
| `start_server.sh` / `start_push_video.sh` / `stop.sh` / `restart.sh` / `usb_ctl.sh` / `org_start_server.sh` | 服务脚本 |
| `org/` | 旧版备份（JSON ×4 + 两个脚本） |

## project/rtmp_1012/ — 交付项目镜像

196 主机 `/home/user/rtmp_1012/`：双相机 RTSP→RTMP 推流（H.264 补丁后退化为纯 remux，约 0.14 核/两路）。
默认 `inactive` + `disabled`，需要时 `sudo m20video up`。

| 文件 | 说明 |
|---|---|
| `README.md` / `config.env` | 项目文档与配置（源/目标/编码参数） |
| `m20video` / `start.sh` / `stop.sh` / `status.sh` / `run_all.sh` / `rtmp_forward.sh` / `install_service.sh` / `systemd/m20video.service` | 服务控制与部署 |
| `patch/apply_h264.sh` / `revert_h265.sh` / `restart_camera.sh` | 相机侧 H.264 补丁三件套（幂等、可回退） |
| `patch/m20gps` / `m20web` / `m20_dog_query.py` | GPS / Web 控制台 / 直连协议客户端（含协议逆向成果） |
| `patch/push_video.sh.orig` | 原始 H.265 备份（md5 `128191f3…`；主机另有两个内容相同的时间戳副本） |
| `patch/dump.pm2.orig` / `web3000_restore_notes.txt` | PM2 Web 控制台复原资产 |

## 120/ — 参考方案镜像

120 主机 `~/rtsp_stream/`（2026-09-21 版）：单路 RTSP→RTMP 纯 remux 中继，是 m20video 的对照原型。
方案级分析（架构/SRS 迁移/4G 改造）已归档到 `../../lite3/docs/hosts/120-运动控制主机/视频与流媒体/rtsp_stream/`。

## tools/ 与 frames/

- `tools/`：26 个现场诊断脚本（GPS 排查、性能对比、pipe 测试、3000 端口检查等），按文件名即可辨认用途。
- `frames/`：9 张抓帧证据（花屏定位、修复前后对比、最终 m20pro-f/b 画面）。

## 维护约定

1. 主机上的文件如有变更，重新镜像后更新本清单与 `note/README.md` 的"本地镜像"说明。
2. 任何密码/密钥一律脱敏：配置只提交 `*.example`，真实配置文件禁止入库。
3. 本目录与 `m20Pro/docs/`（官方文档）、`m20Pro/analysis/`（分析报告）共同构成 m20Pro 资料库，新增内容先归位再更新 `../README.md` 总索引。
