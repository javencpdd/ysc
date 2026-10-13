# M20-pro 196 主机 RTSP / RTMP 代码分析笔记

> 分析对象：`user@192.168.0.196`（主机名 `aos`），Ubuntu 20.04.6 LTS，aarch64，`/opt/robot/os_type = CA9B_AOS`（Rockchip 平台）
> 代码位置：`/opt/robot/scripts/board_resources/rtsp_service/`
> 本地镜像：`../196/rtsp_service/`（仅文本资产；mediamtx / push_video 二进制与 lib/ 约 43MB 未入库，需要时从主机重新获取）
> 分析时间：2026-10-12；2026-10-14 只读复核并补取主机补丁备份

## 索引

| 文件 | 内容 |
|---|---|
| `RTSP服务架构分析.md` | 整体架构、数据流、进程模型、逐脚本解读、运行时实测状态 |
| `配置差异与风险清单.md` | 三套 RTSP 目标地址不一致、编码器参数分歧、潜在 Bug、安全建议 |
| `m20video-双相机RTMP推流项目.md` | 新建项目：与 120 方案异同、四个实测踩坑、交付物、H.264 改造、3000 服务管理 |
| `m20-GPS获取方式.md` | M20 机器狗 GPS 数据链路、四条获取途径、实测 NMEA 证据、`m20gps` 工具 |
| `196主机工程日志-20261012.md` | 当天工程日志全文（SSH 打通、协议逆向、PM2 停用、性能实测，已脱敏） |

---

## 已交付项目

`/home/user/rtmp_1012/`（196 主机）—— 双相机 RTSP→RTMP 推流，含 `m20video` 命令与 systemd 服务。
**当前默认关闭**（转码约占 2 个 CPU 核），需要时 `sudo m20video up`。
详见 `m20video-双相机RTMP推流项目.md` 与项目内 `README.md`。

已安装的 196 主机命令：
- `m20video` —— 推流服务：`up | down | reset | status | doctor | log`
- `m20web`   —— 3000 端口 Web 控制台：`off | on | status | log`
- `m20gps`   —— GPS 状态与数据：`status | watch | nmea | topic | log`

---

## 一句话结论

196 主机跑的是 **一套基于 MediaMTX v1.4.2 的本地 RTSP 中转服务**，由两条 Rockchip 硬编（H.265）的 GStreamer 管道各自把 USB 摄像头推到本机 `rtsp://127.0.0.1:8554/video1` 和 `/video2`。
**RTMP 实际上并未被任何代码使用** —— mediamtx 开了 `:1935` 端口，但既无推流端也无拉流端用它，它只是"顺带开放的输出协议"。
当前**没有接摄像头**（`/dev/video*` 不存在），两路监控进程卡死在无限等待设备的循环里，mediamtx 空转。

---

## 连接这台主机（已配好免密）

`~/.ssh/config` 里已有别名 `m20pro-f20-0-196`（User `user`），走公钥认证，**无需密码**（原始口令不入库，需要时查本地密码管理器）。

本机环境没有 `sshpass` / `plink`，无法直接在命令行给 ssh 喂密码，因此当年用 paramiko 完成了首次公钥投递：

```bash
ssh m20pro-f20-0-196            # 直接连
scp -r user@192.168.0.196:/opt/robot/scripts/board_resources/rtsp_service .
```

需要 root 的命令用 `sudo -S`（从 `SSHPASS` 环境变量喂入口令，不落盘）：

```bash
printf '%s\n' "$SSHPASS" | sudo -S <cmd>
```

辅助脚本 `../sshx.py` / `../s196.py` 是当时的 paramiko 免交互执行器（venv：
`C:\Users\19046\.workbuddy\binaries\python\envs\default`），有了密钥登录后就不需要了，保留备用。

> 网络提示：196 经 WiFi 接入时链路会间歇性丢包，scp/ssh 偶发 `Connection closed`，需带重试逻辑。

## 目录说明

- `../196/rtsp_service/` —— 主机代码镜像（仅文本；`push_video.sh` 为 2026-10-14 复核时的现行 H.264 补丁版，`push_video.sh.orig-h265` 为改造前原版）
- `../120/` —— 120 主机的同类方案（纯 remux 中继），作为对照
- `../project/rtmp_1012/` —— 交付项目的本地镜像（含主机补丁备份）
- `../tools/`、`../frames/` —— 现场诊断脚本与抓帧证据
- `note/` —— 本笔记

