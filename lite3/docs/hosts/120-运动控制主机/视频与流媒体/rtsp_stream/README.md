# rtsp_stream 方案分析（120 主机）

> 2026-09-03 ~ 09-04 对 120 主机 `/home/ysc/rtsp_stream` 部署目录的分析归档。
> 与同级目录的三篇文档同源同项目，但角度不同：**本目录是"方案级"分析**（架构、协议迁移、公网改造），
> 同级文档是"主机现状级"文档（2026-09-05 之后的实测与运维记录）。阅读时先看同级 README，再按需进入本目录。

## 文件清单

| 文件 | 内容 | 结论 |
|---|---|---|
| `ARCHITECTURE_ANALYSIS.md` | 全项目架构分析：MediaMTX v1.4.2 + ZLMediaKit（git 87cb488）双服务器部署、数据流、架构模式、P0/P1/P2 问题清单与改进建议 | 部署运行目录（零自研源码）；一路源多协议扇出、零转码是核心设计；双服务器端口冲突（1935/8000）为 P0 |
| `SRS_RTMP_MIGRATION.md` | RTMP 推流到 SRS 的可行性与改造方案：协议差异（握手/分块/AMF0/时间戳）、三条路径对比、互调验证清单 | **路径 A 推荐**：ZLMediaKit `addStreamPusherProxy`（schema=rtmp）零代码转推，不影响现有 RTSP |
| `SRT_RTMP_4G_GUIDE.md` | 4G/5G 公网图传改造指南：协议选型、服务端配置、SRT latency 调优、排障表 | **SRT 回传 + WebRTC 播放**；RTMP 不放机器人→服务器段（TCP 队头阻塞）；4G 下机器人变纯客户端 |
| `push_video_4g.sh` | 4G 版推流脚本，`probe / srt / rtmp` 三模式，环境变量覆盖 SERVER_IP/STREAM_ID/BITRATE/SRT_LATENCY | rtmp 模式已修 Annex-B→AVCC 转换缺陷（缺 capsfilter 会导致 SRS 解不出画面） |

## 关键事实速查

| 项 | 值 |
|---|---|
| 部署路径 | `/home/ysc/rtsp_stream`（120 主机，hostname `ysc`） |
| 架构 | aarch64（RK3588 类），GStreamer + Rockchip MPP 硬编 H.264 1280×720@30 |
| 服务器 | MediaMTX v1.4.2（RTSP 接入）+ ZLMediaKit 87cb488（多协议分发，当前已退居遗留） |
| 局域网拓扑 | `v4l2src /dev/video0 → mpph264enc → rtsp://127.0.0.1:8554/test` |
| 公网推荐拓扑 | 机器人 SRT 推云端 :8890 → 云端 WebRTC/RTMP/HLS 分发 |

## 与其他文档的关系

- 启动脚本、`mediamtx.yml`、`config.ini` 等配置文件未在本目录重复归档；
  120 主机现行文件镜像见 `../../../../m20Pro/rtsp-rtmp/120/`（2026-09-21 版，m20video 项目的对照参考）。
- 主机现状与运维记录见同级 `实时流媒体服务分析.md`、`实时流媒体应用代码分析.md`、`实时流媒体转推流记录.md`。
- 2026-10-12 m20video 项目（m20 196 主机）参考了本方案的纯 remux 中继思路，见 `m20Pro/rtsp-rtmp/note/m20video-双相机RTMP推流项目.md`。

## 遗留风险（来自架构分析，供后续整改参考）

1. 双服务器端口冲突：1935（RTMP）、8000（RTP/WebRTC 默认）同时被抢；根 `config.ini` 缺 `[rtc]` 段。
2. `api.secret` 明文入库风险（本仓库已脱敏，主机配置仍需整改）。
3. 启动竞态：`start_stream.sh` 无健康检查；无进程守护；硬编码绝对路径。
4. ZLMediaKit 发布包含 1.4GB 测试产物（`test_*`、`.a` 静态库、过期 ts 切片），嵌入式存储应裁剪。
