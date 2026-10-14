# m20video —— 双相机 RTSP→RTMP 推流项目笔记

> 主机：`user@192.168.0.196`（`aos`，**M20 Pro 的 AOS 运控主机**，RK3588 级 SoC，Ubuntu 20.04 aarch64）
> ⚠️ 2026-10-14 更正：此处原写「Lite3 感知主机」有误 —— Lite3 的感知主机是 `192.168.1.103`（hostname `lite`），与 M20 的 196 不是同一台。
> 项目：`/home/user/rtmp_1012/`，本地镜像 `rtsp_rtmp/project/rtmp_1012/`
> 日期：2026-10-12
> 目标：把两路相机 RTSP 转成 RTMP，推到 `rtmp://172.31.68.227:1936/live/m20pro-f` 与 `m20pro-b`
> 参考：120 主机（`192.168.1.120:~/rtsp_stream/`）的 `rtmp_forward.sh` 方案

## 索引

| 文件 | 内容 |
|---|---|
| `../project/rtmp_1012/README.md` | 项目完整文档（使用、配置、踩坑） |
| 本文 | 决策过程、根因分析、与 120 方案的异同 |

---

## 一句话结论

已交付并验证：`/home/user/rtmp_1012/` 项目 + `m20video` 命令 + `m20video.service`。
**服务当前 `disabled` + `inactive`（按用户要求默认关闭，因为转码约占 2 个 CPU 核）。**
需要时 `sudo m20video up` 即可拉起，已实测画面、断线自愈、启停均正常。

---

## 1. 与 120 主机方案的异同

### 相同（直接借鉴）
- 架构：本机 RTSP（MediaMTX 托管）→ GStreamer → 外部 RTMP。
- `rtmp_forward.sh` 骨架、`parse_host_port()` / `probe_tcp()` / `dump_diagnostics()` /
  `log()` 的函数划分与命名。
- 每轮推流前 TCP 预探测，连续失败达阈值 → 写诊断快照 → 退出码 3。
- `gst-launch -e`（发 EOS 干净断流）、`flvmux streamable=true` + `rtmpsink ... live=1`。
- 诊断里用本机 mediamtx 的 HLS 端点自检源流。

### 必须不同（源编码差异）
| | 120 | 196 |
|---|---|---|
| 相机编码 | H.264（`mpph264enc`） | **H.265**（`mpph265enc`） |
| GStreamer | — | **1.16.3** |
| `flvmux` | 支持 `video/x-h264` | 仅 `video/x-h264`（**无 HEVC**） |

H.265 进 FLV 需要 **GStreamer 1.24+ 的 Enhanced RTMP**，1.16.3 没有；
目标端 SRS v5.0.213 也不支持 Enhanced RTMP HEVC。
→ **196 必须做 H.265→H.264 硬转码**，无法像 120 那样纯 remux。

### 新增（120 没有的）
- **看门狗**：补上用户笔记 §10.5 自己指出的盲区 —— `exit 3` 保护只在每轮
  `probe_tcp` 生效，`gst-launch` 一旦卡在黑洞连接里就既不退出也不被重启。
- **源流在线探测**：源不在线时跳过启动 gst，避免空转刷屏。
- **gst 重命名隔离**：规避上游 `restart.sh` 的 `pgrep -f "gst-launch" | kill -9`。
- 日志轮转、PID 文件、`m20video` CLI、systemd 单元、`SOURCE_CODEC` 开关。

---

## 2. 实测踩到的四个坑（都是实测，非推测）

### 2.1 `drop-on-latency` + `queue leaky` 会引发雪崩
三变体对照（各 2 分钟，同一源）：

| 变体 | 配置 | CPU | CRITICAL 数 |
|---|---|---|---|
| A | + `drop-on-latency=true` + `leaky=downstream` | 73.3% | **960,548** |
| B | **都不用** | **10.2%** | **24** |
| C | + 上述两者，去掉 `videoconvert` | 71.6% | 967,021 |

源流一断，A/C 就陷入 `gst_mini_object_unref: assertion 'object != NULL' failed`
报错风暴（每秒上万条），CPU 打满单核，**进程永不退出**。

原因：转码中继不是播放器。播放器可丢帧保实时；中继丢帧会破坏 H.265 解码链，
解码器产出无效 buffer 后整条管线崩坏。源在本机 loopback，本来就没有抖动需追帧。

> ⚠️ **用户笔记 §10.7 曾建议加 `queue leaky=downstream`，实测证明这条不能采纳。**

### 2.2 `rtmpsink` 远端断开后 gst 不退出
socket 变 `CLOSE-WAIT`，但进程仍存活、`ps` 看着正常，实际早已停推
（CPU 从 13% 掉到 6%，无 ESTAB）。→ 必须自己写看门狗。

### 2.3 上游相机服务会静默整树消失
两次遇到 `start_server.sh + push_video.sh` 整棵树消失（mediamtx 因被 init
收养而存活），源变 404。dmesg 对应 `uvcvideo: Failed to resubmit video URB (-1)`。
排查时**第一步永远先 `curl .../video1/index.m3u8` 确认源在线**。

### 2.4 `mpph264enc` 喂 NV12 会花屏（本次最耗时的一个坑）
现象：推出去是**绿紫横向条纹**。逐级抓帧定位：

| 测试 | 管线 | 结果 |
|---|---|---|
| A | `mppvideodec` → RGB → PNG | ✅ **硬解没问题** |
| B | `avdec_h265` 软解参照 | ✅ 干净 |
| C | `... → videoconvert → **NV12** → mpph264enc` | ❌ 花屏 |
| D | `... → videoconvert → **I420** → mpph264enc` | ✅ **正常** |
| E | `mppvideodec → **NV12** 直连 mpph264enc` | ❌ 花屏 |

→ `mpph264enc` 在 NV12 输入下输出错位（行步长错配），**必须用 I420**。

**代价**：`videoconvert` 做 NV12→I420 在这颗 ARM CPU 上极慢 ——
`mppvideodec ! videoconvert ! I420 ! fakesink` 单独就 **99.5% 单核**；
`n-threads=4` 反而更慢（225%）；换软解同样 101.9%；系统无 RGA 转换元素。
→ **两路合计约 2 个 CPU 核**，这是本服务默认关闭的直接原因。

---

## 3. 当前交付物

### 项目结构
```
/home/user/rtmp_1012/
├── config.env            # 全部配置
├── rtmp_forward.sh       # 单路推流器（重连循环 + 看门狗 + 源流探测）
├── run_all.sh            # 前台拉起两路（systemd 用）
├── start.sh / stop.sh / status.sh
├── m20video              # CLI（已装到 /usr/local/bin/m20video）
├── install_service.sh    # 安装/卸载
├── systemd/m20video.service
├── bin/rtmp-gst          # gst-launch-1.0 重命名副本（规避上游误杀）
├── logs/  run/
```

### m20video 命令
```bash
sudo m20video up | down | reset | status | doctor
sudo m20video log f|b
sudo m20video enable | disable          # 开机自启开关
```
非 root 会自动 `sudo` 提权。

### 服务状态（交付时）
- `systemctl is-enabled m20video.service` → **disabled**（按用户要求默认关闭）
- `systemctl is-active  m20video.service` → **inactive**
- 无残留 gst / 转发器进程；相机采集与雷达/感知栈均不受影响

### 已验证项
- 画面：从目标服务器回拉抓帧，`h264 / High / 800×600 / 30fps`，画面干净
- 启动：`m20video up` → 两路 ESTAB 到 `172.31.68.227:1936`
- 停止：`m20video down` → 服务 inactive，无残留进程，到目标连接归零
- 重启：`m20video reset` → MainPID 变化，连接恢复为 2
- 绑核：video1→0,1；video2→2,3（避开相机采集占用的 4,5,6,7）

---

## 4. 主机性能占用实测对比

采样方式：内核 cgroup `cpuacct.usage` 增量（m20video）+ `/proc/PID/stat` 增量（其它），
窗口 20s，同一时段内先后测量，8 核整机。

| 服务 | CPU（%单核） | 占整机 | 折合核数 | 内存 RSS | 进程/线程 |
|---|---|---|---|---|---|
| **m20video 两路推流**（196，H.265→H.264 转码） | **197.6%** | 24.7% | **1.98 核** | 29.9 MB | 9 / 37 |
| **3000 端口服务**（`node /home/tank/m20/server.js` + PM2） | **5.4%** | 0.7% | 0.05 核 | **283 MB** | 2 / 204 |
| 120 主机中继（单路，**纯 remux** 参照） | 12.8% | 1.6% | 0.13 核 | 22.3 MB | — |

系统总线 CPU：只有 3000 服务时 19.2% → 加上 m20video 后 43.7%（+24.5 个百分点）。

### 结论
- **CPU：m20video 是 3000 端口服务的约 37 倍**（197.6% vs 5.4%），是主机上最大的单一新增负载。
- **内存：反过来，3000 端口服务是 m20video 的约 9.5 倍**（283MB vs 29.9MB），
  且带 204 个线程 —— 典型 Node.js + PM2 形态（常驻但不怎么吃 CPU）。
- **120 的纯 remux 中继单路只要 0.13 核**，而 196 的转码单路要 0.99 核 ——
  **约 7.6 倍**。差距全部来自 `videoconvert` 的 NV12→I420（95%/路，见 2.4）。
- 注意两者的活儿本来就不同：196 是 800×600 转码，120 是 1280×720 直通，
  分母不同 —— 但即使按分辨率折算，转码的代价仍高出一个数量级。

### 由此得出的行动建议
把相机侧 `push_video.sh` 从 `mpph265enc` 换成 `mpph264enc`（见第 5 节），
让中继退回纯 remux，预期 CPU 从 **1.98 核 → 约 0.26 核**（对齐 120 的 0.13 核/路）。
这件事的收益比"关不关服务"大得多 —— 关掉只是省下这 2 核，改掉是省下 1.7 核还能一直开着。

## 5. 相机侧 H.264 改造（已实施并实测）

2026-10-12 已按上述建议完成改造。**实测结果超出预期：**

| 指标 | 改造前（H.265 转码） | 改造后（H.264 纯 remux） | 变化 |
|---|---|---|---|
| m20video CPU | 197.6% 单核（1.98 核） | **13.9% 单核（0.139 核）** | **↓ 14.2 倍** |
| m20video 内存 | 29.9 MB | **14.3 MB** | ↓ 约一半 |
| 相机侧 CPU | 13.3% 单核 | 15.8% 单核 | ↑ 约 2.5 个百分点 |
| 系统总线 CPU | 43.7% | **14.9%** | ↓ 约 29 个百分点 |

**净收益 ≈ 省下 1.84 个 CPU 核**，代价是相机侧多 0.025 核。
中继管道变为：`rtspsrc → rtph264depay → h264parse → flvmux → rtmpsink`（零转码）。

### 改了 3 处（都在 `push_video.sh`）
```diff
- ! jpegdec ! videoconvert ! mpph265enc $DEV_ENCODER_PARAMS ! h265parse config-interval=-1 !
+ ! jpegdec ! videoconvert ! video/x-raw,format=I420 ! mpph264enc $DEV_ENCODER_PARAMS ! h264parse config-interval=-1 !

- DEV_ENCODER_PARAMS="gop=2 header-mode=each-idr"
+ DEV_ENCODER_PARAMS="rc-mode=1 bps=2000000 bps-max=2500000 gop=30 qp-min=12 qp-max=45 header-mode=each-idr"
```
- **必须加 `video/x-raw,format=I420`**：`mpph264enc` 在 NV12 输入下会花屏（见 2.4），
  相机侧用的是同一个编码器，所以同样要强制 I420。
- 原 `gop=2` 且无码率控制 → 改 `gop=30` + 2Mbps CBR，码率可控。

### 可复原设计（用户要求"提前准备好复原脚本"）
`patch/` 目录内含完整双向脚本，均已部署到 `/home/user/rtmp_1012/patch/`：

| 文件 | 作用 |
|---|---|
| `push_video.sh.orig` | 原始脚本整文件备份，**md5 `128191f3fecc7f4b1017ae57fc075c77`** |
| `apply_h264.sh` | 应用改造。先判状态：已是 H.264 则跳过；文件被外部改过则中止（不盲改） |
| `revert_h265.sh` | 一键还原。优先用备份整文件覆盖并校验 md5；备份丢失则回退反向 sed。同时把 `SOURCE_CODEC` 改回 `h265` 并重启两个服务 |
| `restart_camera.sh` | 重启相机服务。**精确匹配**，只动相机侧，不误杀其它 gst（官方 `restart.sh` 会 `pgrep -f gst-launch \| kill -9` 无差别杀） |

还原命令：`sudo bash /home/user/rtmp_1012/patch/revert_h265.sh`

### 风险
- 改的是打包文件（`boardresources`），**OTA/重装可能被还原** → 重跑 `apply_h264.sh` 即可（幂等）。
- 本机 RTSP 流编码由 H.265 变 H.264，同画质码率约高 40%（800×600@30 影响很小）；
  若有其他消费端强依赖 H.265，需 `revert_h265.sh` 回到转码模式。

## 6. 机器狗 Web 控制台（3000 端口）的停用

用户要求"3000 端口的服务也默认关闭、不要开机自启"。

### 它是什么
| 项 | 值 |
|---|---|
| 进程 | `node /home/tank/m20/server.js` |
| 端口 | 3000（HTTP，返回 200） |
| PM2 应用名 | **`m20`**（PM2_HOME=`/root/.pm2`，仅此一个应用） |
| 开机自启 | `pm2-root.service`（enabled）→ `pm2 resurrect` 读 `/root/.pm2/dump.pm2` |
| 作用 | 相机控制网页。`config.json` 里 `startScript`/`stopScript` 指向 `rtsp_service/start_push_video.sh` 与 `stop.sh` |

**为什么关掉更稳**：它的"启动相机"走 `start_push_video.sh`（`push_video` C++ 二进制 +
`SM_USB_107X_*.json`），与机器人自带 `push_video.sh` **争抢摄像头设备**。

### 安全性确认
`server.js` 里**没有任何 SIGTERM/SIGINT/SIGHUP 处理器**（已 grep 确认），
所以 `pm2 stop/delete` 不会触发 `stopScript`，**不会连带停相机**。
实测停用前后 video1/video2 源流一直 200。

### 踩到的坑：`pm2 save` 会静默跳过
```
[PM2][WARN] PM2 is not managing any process, skipping save...
[PM2][WARN] To force saving use: pm2 save --force
```
**列表为空时 `pm2 save` 直接跳过**，`dump.pm2` 仍保留旧条目 → 开机 `pm2 resurrect`
照样会把它拉起来。**必须用 `pm2 save --force`。**

### 交付
新增 `m20web` 命令（`/usr/local/bin/m20web`，源码 `rtmp_1012/patch/m20web`）：
```bash
sudo m20web off | on | status | log
```
复原材料：`patch/dump.pm2.orig`（md5 `5e6ff85761a9e54efcdbccc55ef95d89`）
+ `patch/web3000_restore_notes.txt`（精确启动参数，备份丢了也能手工恢复）。
**已实测 `on`（端口 3000 监听、HTTP 200、dump 恢复自启）→ `off`（dump 清空）闭环可用。**

## 7. 操作这台机器的注意事项

- **命令行里不要出现 `push_video` 或 `v4l2` 字样**，否则上游
  `restart.sh` / `stop.sh` 的 `pkill -f` 会连你自己这条命令一起杀。
  这类操作请写进脚本文件再执行。
- 判断"196 是否掉线"看 ARP 表或直接测 22 端口；`ping 网关不通`不能作为依据
  （Tenda 路由器屏蔽 ICMP）。
- 重启整机后 `m20video` 项目与服务单元都在（位于 `/home/user` 与 `/etc/systemd`），
  但若未 `enable` 需手动 `m20video up`。
