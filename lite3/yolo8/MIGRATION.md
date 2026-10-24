# yolo8 换机迁移包（Lite3 感知主机 103）

> 本目录是**从 103（`/home/test/yolo8`）剥离运行产物后的代码与资产**，用于部署到另一台
> 同构 Lite3 感知主机。**不要**把它当成 103 的实时工作副本——它没有 logs/pic，也没有
> `deploy/backup-*` 备份。
>
> **权威流程文档：[`note/23-yolo8移植部署流程.md`](note/23-yolo8移植部署流程.md)**
> （换机真正要改什么、阶段 0→7、双机并存冲突、验收清单、常见坑都在里面）。
> 本文件只是**首页速查**。

---

## 0. 硬门槛：目标机必须与 103 同构

| 项 | 要求 | 不一致的后果 |
|---|---|---|
| SoC | Jetson Xavier NX（aarch64，6 核，6 GiB） | — |
| 系统 / JetPack | Ubuntu 20.04.6 / kernel `5.10.120-tegra` / **R35.4.1** | 差一代要重导 engine |
| CUDA / TensorRT | 11.4.19 / **8.5.2.2** | **跨版本 engine 加载失败**，必须重导出 |
| GStreamer | 1.16.3 + `nvv4l2h264enc` `rtmpsink` `rtspsrc` `v4l2src` `jpegdec` | 缺 `nvv4l2h264enc` → 软编码，帧率腰斩 |
| ROS | `/opt/ros/foxy`（ROS2 通路才需要） | 只推 RTMP 时可缺 |
| Python | 3.8.10（**无 venv**，系统 python3） | 3.9+ 语法在真机会炸 |
| 磁盘 / swap | ≥5 GB 空闲、建议 3 GB swap | 磁盘保护会主动停抓拍 |

目标机体检（只读）：

```bash
cat /etc/nv_tegra_release
python3 -c "import tensorrt as t;print(t.__version__)"
gst-inspect-1.0 nvv4l2h264enc >/dev/null && echo nvv4l2h264enc:OK || echo nvv4l2h264enc:MISSING
ls /opt/ros; python3 --version; df -h / | tail -1; free -g | head -2
```

**RK3588 的运动控制主机（120）不能迁**：无 CUDA/TRT/ROS，要替换模型、推理、编码三层，等于重写。详见流程文档 §1.2。

---

## 1. 目录内容

| 目录 | 体积 | 说明 |
|---|---|---|
| `src/` | 4.3 MB | 推理与发布源码，**含 vendored `ultralytics/`**（不靠 pip 装） |
| `console/` | 0.8 MB | Web 控制台（纯 Python 零依赖），含 P4.7 改造后的界面 |
| `deploy/` | 0.3 MB | ctl 脚本、`systemd/` 单元模板、`install-retention.sh`、`make-migration-bundle.sh` |
| `config/` | 2 KB | `yolo8.json`，**已脱敏，换机必改** |
| `note/` | 0.8 MB | 排障文档，尤其 `23-*`（换机）与 `08-*`（控制台改造计划书 v2） |
| `model/` | 32 MB | `yolov8n_arm.engine`（aarch64，同 TRT 版本可直接用）+ `.pt`/`.onnx`（版本不符时现地重导的原料） |

**未包含**（有意排除，见流程文档 §2）：`logs/` `pic/` `deploy/backup-*` `__pycache__/`
`*.bak-*` `.git/` `*.pyc`、`model/yolov8n_amd.engine`（x86 专用）、`model/exports/`
（`.trt-timing-cache` 与具体 GPU+TRT 版本绑定，换机可能失配，带去不如让它重建）、`model/uploads/`。

---

## 2. ★ 换机真正要改的（只有这些）

### 2.1 配置层 `config/yolo8.json`

| 字段 | 现值 | 改成什么 | 不改的后果 |
|---|---|---|---|
| `source.rtsp_url` | `rtsp://192.168.1.120:8554/test` | **新机器狗自己那台 120** 的 MediaMTX | 拉不到流，worker 反复重连 |
| `stream.rtmp_url` | `rtmp://172.31.68.227:1936/live/lite3_yolo` | 同服务器但**换 stream key**，如 `lite3_yolo_2` | ★**与 103 抢同一个 key，SRS 互踢**（已实测：`Could not write to resource` + pipeline 递增重建） |
| `console.allowed_cidrs` | `["192.168.1.0/24"]` | 新机所在网段 | 访问 403 |
| `console.token` | `CHANGE_ME_ON_TARGET_HOST`（**占位符**） | **必须设强令牌** | 两台车共用弱口令 |
| `snapshot.min_free_gb` | 5 | 按新机磁盘调 | 磁盘不足时抓拍被禁 |
| `model.engine` / `pic_dir` | `../model/…`、`../pic` | **不改**（相对 `src/`，随安装目录走） | — |

改 `allowed_cidrs` / `token` 要**重启 console**；改 `rtsp_url` / `rtmp_url` / 阈值在线改即可。

### 2.2 单元层（仅当路径或用户变化时）

`deploy/systemd/lite3-yolo-*.service` 里全是绝对路径，路径变了就全局替换。
两处要特别注意：

- `lite3-yolo-console.service` 的 `CPUAffinity=0-2`：103 的 cpu5-7 跑着 SCHED_FIFO 实时线程
  （hsLidar prio54 / lio prio64）。新机若也跑这些，保留 `0-2`；若干净，可放宽到 `0-5`。
- `Restart=always` + `RestartSec=5`：worker 冷启动约 35 s，**别把 RestartSec 调小**。

### 2.3 安装位置铁律

绝对路径、不含空格、不含 `#` `&`、不放 `/tmp`、保持 `/home/<运行用户>/yolo8`。
**推荐沿用 `/home/test/yolo8` + 用户 `ysc`**，这样单元里的 `WorkingDirectory`、
`EnvironmentFile`、`StandardOutput`、`User=` 一个字都不用改。

---

## 3. 快速开始

```bash
# ① 目标机预检（见本文 §0），任一硬门槛不满足就停手

# ② 传包
scp yolo8-migration-*.tgz ysc@<新103>:/tmp/

# ③ 解包到中转站，再装到目标目录
mkdir -p /tmp/pkg && tar xzf /tmp/yolo8-migration-*.tgz -C /tmp/pkg
sudo rsync -a /tmp/pkg/ /home/test/yolo8/
sudo chown -R ysc:ysc /home/test/yolo8
mkdir -p /home/test/yolo8/{logs,pic,model/exports,model/uploads}
#    注意：不要把 /tmp/pkg 当安装目录（/tmp 会被清理）

# ④ 依赖与日志治理
python3 -m pip install -U -i https://pypi.tuna.tsinghua.edu.cn/simple pycuda numpy opencv-python
bash /home/test/yolo8/deploy/install-retention.sh --check
printf "\047\n" | sudo -S bash /home/test/yolo8/deploy/install-retention.sh

# ⑤ 装单元（console 自启；publish 保持 disabled——worker 不自启是既定设计）
sudo cp /home/test/yolo8/deploy/systemd/lite3-yolo-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lite3-yolo-console

# ⑥ 改配置（本文 §2.1），改完重启 console
# ⑦ 起 worker（必须走 ctl，让 logs/yolo.pid 存在）
cd /home/test/yolo8 && deploy/lite3-publish-ctl.sh start yolo
pgrep -af run_tracker_publish        # 必须只有 1 行
```

详细阶段、双机并存冲突、验收清单、回滚、常见坑 → **流程文档 §6~§10**。

---

## 4. 重新打包

源机（103）上一条命令：

```bash
bash /home/test/yolo8/deploy/make-migration-bundle.sh /tmp
```

脚本内置排除清单自检（包内出现 `backup-`/`.bak-`/`__pycache__`/`amd.engine` 等即报错退出），
并在打包前扫描已知令牌明文。

---

## 5. 脱敏与安全说明

本迁移包已做以下脱敏，**与 103 上的原文有意不同**：

| 位置 | 处理 |
|---|---|
| `config/yolo8.json` 的 `console.token` | 已替换为占位符 `CHANGE_ME_ON_TARGET_HOST` |
| `console/configlib.py` 的 `DEFAULT_TOKEN` | 已替换为同一占位符（仍是合法可打印 ASCII，不影响校验逻辑） |
| `console/server.py`、`configlib.py` 注释里的默认令牌 | 已改为指向 `DEFAULT_TOKEN` |
| `note/*.md` 里的令牌明文与旧令牌哈希 | 已替换为 `***已脱敏***` |
| `console/token.deprecated-20261022`（旧令牌残留文件） | 已删除 |

**仍需注意**：

- `src/hub_sdk/config.py` 内有一个 Firebase Web API Key（`AIzaSy…`）。这是 vendored
  Ultralytics Hub SDK 自带的**第三方客户端公开凭据**（Firebase Web Key 按设计公开，
  非本项目私有密钥），本包未改动。若要公开上传仓库，请自行评估。
- 目标机部署后，**第一件事就是改 `console.token`**。
- 本包不含 `.git`，也不含任何 `.bak-*` 备份。

---

## 6. 迁移包本身的校验

```bash
tar tzf yolo8-migration-*.tgz | wc -l          # 条目数
tar tzf yolo8-migration-*.tgz | grep -cE 'backup-|\.bak-|__pycache__|amd\.engine|/logs/|/pic/|exports/|uploads/'   # 必须为 0
grep -rc 'jack1[4]19\|1761f47[d]560a' . 2>/dev/null | grep -v ':0'   # 必须为空
```

---

本内容由 AI 生成，请核实后使用。
