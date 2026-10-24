# 移植部署流程（换一台 Lite3 感知主机 103 / yolo8 工程）

> **三个直接回答**
>
> **① 能迁，但目标机必须与现有 103 同构。** 本工程的推理与编码深度绑定
> Jetson Xavier NX + JetPack R35.4.1（CUDA 11.4 / TensorRT 8.5.2.2 / `nvv4l2h264enc`）。
> 同型号机器狗的 103 → **照本流程走**；RK3588 的运动控制主机 120 → **不能迁**（见 §1.2）。
>
> **② 不是"复制 `/home/test/yolo8` 这个文件夹"。** 要打包的是**剔除运行产物后的代码与资产**
> （约 26~39 MB）。直接 `scp -r` 会带上 6.3 MB 日志、6.1 MB 抓拍图、12 个部署备份目录、
> 以及 x86 专用的 `yolov8n_amd.engine`。
>
> **③ 换机真正要改的只有五处**：`source.rtsp_url`、`stream.rtmp_url`（含 stream key）、
> `console.allowed_cidrs`、`console.token`、systemd 单元的绝对路径/用户/CPU 亲和。
> 其余全部随包走。
>
> 📌 本文是 yolo8 换机的**唯一权威文档**（对齐 M20 的 `note/移植部署流程.md`）。
> 事实来源：2026-10-23 真机（103）实测 + 2026-10-24 配置与依赖盘点；
> 凡标注「待现场验证」的，是同构但未在第二台车上跑过的项。

---

## 1. 前提：目标主机门槛

### 1.1 必须同构（硬门槛）

| 项 | 103 实测值 | 目标机要求 | 不一致的后果 |
|---|---|---|---|
| SoC | Jetson Xavier NX（aarch64，6 核，6 GiB） | 同型号 | — |
| 系统 / JetPack | Ubuntu 20.04.6 / `5.10.120-tegra` / **R35.4.1** | 同版本 | 差一代就要重导 engine |
| CUDA | 11.4.19 | 同 | engine 与 CUDA 运行时绑定 |
| TensorRT | **8.5.2.2**（libnvinfer8 `8.5.2-1+cuda11.4`） | 8.5.x | **跨版本 engine 加载失败**，必须重导出 |
| GStreamer | 1.16.3 + `nvv4l2h264enc` `rtmpsink` `rtspsrc` `v4l2src` `jpegdec` | 插件齐全 | 缺 `nvv4l2h264enc` → 只能软编码，帧率腰斩 |
| ROS | `/opt/ros/{foxy,noetic}` | foxy（ROS2 通路才需要） | 只推 RTMP 时 ROS 可缺 |
| Python | 3.8.10（**无 venv**，用系统 python3） | 3.8.x | 3.9+ 语法在真机会炸 |
| 磁盘 / swap | ≥5 GB 空闲（`snapshot.min_free_gb=5`）、建议 3 GB swap | 同 | 磁盘保护会主动停抓拍 |

> 一条命令体检（目标机上跑，只读）：
> ```bash
> cat /etc/nv_tegra_release; python3 -c "import tensorrt as t;print(t.__version__)"
> gst-inspect-1.0 nvv4l2h264enc >/dev/null && echo nvv4l2h264enc:OK || echo nvv4l2h264enc:MISSING
> ls /opt/ros; python3 --version; df -h / | tail -1; free -g | head -2
> ```

### 1.2 为什么 120（RK3588）不能迁

已实测 120 = **Rockchip RK3588**，Ubuntu 20.04.6，3.9 GiB 内存，28 GB eMMC（剩 8.7 GB）：
`nvidia-smi` 无、CUDA/TRT/nvinfer 包 **0 个**、无 `/opt/ros`；有的是 Rockchip MPP 1.5.0、
librga、NPU 工具（`npu_*`/`rknn_demo`）。要迁必须替换四层，等于重写：

| 层 | 103（Jetson） | 120（RK3588）需改成 |
|---|---|---|
| 模型 | `yolov8n_arm.engine`（TRT） | RKNN 转换 + 量化校准 |
| 推理 | ultralytics + pycuda | rknn-toolkit-lite2 + 自写 NMS |
| 编码 | `nvv4l2h264enc` | `mpph264enc`（MPP） |
| 实时性 | 感知主机独享 | **与运动控制抢 CPU/NPU**，遥测实时性风险 |

结论：**不在本流程范围内**。若确需，单独立项。

---

## 2. 为什么不能直接复制文件夹

| 目录/文件 | 直接拷会怎样 |
|---|---|
| `logs/`（6.3 MB） | 运行产物，还可能带着上一台车的排障噪声 |
| `pic/`（6.1 MB） | 抓拍图与 `.trash`，新机上毫无意义 |
| `deploy/backup-p4-*` ×12 | 历次部署备份，纯垃圾 |
| `model/yolov8n_amd.engine`（22.7 MB） | **x86 专用**，aarch64 上加载失败 |
| `model/exports/.trt-timing-cache` | 与**具体 GPU + TRT 版本**绑定，换机可能失配；带去不如让它重建 |
| `__pycache__/` | 版本相关字节码 |
| `*.bak-*`、`yolo-publish.env.bak-*` | 历史备份 |
| `.git/` | 体积大，且历史上含过令牌 |

---

## 3. 打包清单

```bash
# 在 103 上执行（只读操作，产出在 /tmp）
cd /home/test/yolo8
tar czf /tmp/yolo8.tgz \
  --exclude='logs/*' --exclude='pic/*' \
  --exclude='deploy/backup-*' --exclude='__pycache__' \
  --exclude='model/yolov8n_amd.engine' --exclude='model/exports/*' \
  --exclude='*.bak-*' --exclude='.git' \
  src console deploy config note
```

| 收进包 | 体积 | 说明 |
|---|---|---|
| `src/` | 4.3 MB | 推理与发布源码，**含 vendored `ultralytics/`**（不靠 pip 装） |
| `model/yolov8n_arm.engine` | 19.9 MB | **aarch64 引擎，换机后直接可用（同 TRT 版本）** |
| `model/yolov8n.pt` + `.onnx` | 12.9 MB | 建议带：TRT 版本不一致时现地重导 engine 的原料 |
| `console/` | 776 KB | Web 控制台（纯 Python 零依赖） |
| `deploy/`（去备份后） | ~0.3 MB | ctl 脚本、`systemd/` 单元模板、`install-retention.sh` |
| `config/` | 48 KB | **含 console 令牌，换机必改** |
| `note/` | 788 KB | 排障靠它，尤其本文与计划书 v2 §22 |

体积参考：**约 38 MB（带 pt/onnx）或 25 MB（只带 engine）**。
> 若已确认目标机 TRT 与 103 完全一致（`8.5.2.2`），可以只带 engine，包更小；
> 拿不准就带 pt/onnx，现场重导（冷启 ~26 min / 命中计时缓存 ~2 min）。

---

## 4. 路径与运行用户（照 M20 已踩实的三条铁律）

| 要求 | 原因 | 违反后果（M20 实测） |
|---|---|---|
| **绝对路径** | 写进 systemd 单元 | 相对路径 → 服务起不来 |
| **不含空格** | systemd 按空白拆词 | `status=203/EXEC` |
| **不含 `#` `&`** | 部署脚本用 `sed` 全局替换路径 | `#` → sed rc=1 单元被写空；`&` → 路径被展开错乱 |
| **不放在 `/tmp`** | 重启/清理脚本会带走 | 重启后服务消失 |
| **保持 `/home/<运行用户>/yolo8`** | systemd `User=` 由父目录名推断 | 降级成跑 sudo 的人；用 root 直接跑会**以 root 运行** |

推荐沿用 **`/home/test/yolo8` + 用户 `ysc`**（与 103 完全一致）——这样单元里的
`WorkingDirectory`、`EnvironmentFile`、`StandardOutput`、`User=` **一个字都不用改**，
换机风险最小。若目标机账号不同（如 `jack`），则 `/home/jack/yolo8` + 全局替换。

装完必核：
```bash
systemctl show lite3-yolo-console -p User --value      # 必须是普通用户，不能是 root
systemctl show lite3-yolo-console -p ExecStart --value
```

---

## 5. 换机必改清单（★这是换机真正的工作量）

### 5.1 配置层：`config/yolo8.json`

| 字段 | 103 现值 | 新机该填什么 | 不改的后果 |
|---|---|---|---|
| `source.rtsp_url` | `rtsp://192.168.1.120:8554/test` | **新机器狗自己那台 120** 的 MediaMTX | 拉不到流 → worker 反复重连、无帧可推 |
| `stream.rtmp_url` | `rtmp://172.31.68.227:1936/live/lite3_yolo` | 同服务器但**换 stream key**，如 `lite3_yolo_2` | ★**与 103 抢同一个 key，SRS 互踢**（2026-10-23 已实测：`Could not write to resource` + pipeline 递增重建） |
| `console.allowed_cidrs` | `["192.168.1.0/24"]` | 新机所在网段 | 访问被 403 |
| `console.token` | `***已脱敏***`（弱默认值） | **必须换强令牌** | 两台车共用弱口令，等于门户大开 |
| `snapshot.min_free_gb` | 5 | 按新机磁盘调 | 磁盘不足时抓拍被禁 |
| `model.engine` / `pic_dir` | `../model/…`、`../pic`（相对 `src/`） | **不改** | 相对路径随安装目录走 |

> 改 `allowed_cidrs` / `token` 要重启 console；改 `rtsp_url` / `rtmp_url` / 阈值等
> **在线改即可**（`retention` 与运行期键不在 `YOLO_SECTIONS`，不触发 worker 重启）。

### 5.2 单元层（仅当路径或用户变化时）

| 位置 | 103 现值 | 说明 |
|---|---|---|
| `lite3-yolo-publish.service` | `User=ysc`、`WorkingDirectory=/home/test/yolo8/src`、`EnvironmentFile=…/yolo-publish.env`、`ExecStart=/home/test/yolo8/deploy/scripts/run-yolo-publish.sh` | 全绝对路径，全局替换 |
| `lite3-yolo-console.service` | `User=ysc`、`CPUAffinity=0-2`、`WorkingDirectory=/home/test/yolo8/console` | **CPUAffinity 要按目标机重估**：103 的 cpu5-7 跑着 SCHED_FIFO 实时线程（hsLidar prio54 / lio prio64）。新机若也跑这些，保留 `0-2`；若干净，可放宽到 `0-5` |
| `Restart=always` + `RestartSec=5` | worker 冷启动约 35 s | **别把 RestartSec 调小** |
| `TimeoutStopSec=20` | 释放 RTMP/RTSP 线程 | 再短会留僵尸推流 |

### 5.3 环境层（重装的）

| 项 | 命令 | 备注 |
|---|---|---|
| 日志轮换 | `deploy/install-retention.sh`（幂等，`--check` 只看状态） | **logrotate 的 `su` 行按目标机属主渲染**；`logs/` 是 group-writable，不加 `su` 会被静默跳过 |
| journald 限额 | 同上（写 `SystemMaxUse=200M` / `MaxRetentionSec=7day`） | 103 的 journal 是 volatile，限的是内存 |
| Python 依赖 | `python3 -m pip install -U -i https://pypi.tuna.tsinghua.edu.cn/simple pycuda` 等 | 外网只通国内，必须挂清华源；ultralytics 已 vendored，不用装 |

---

## 6. 完整流程（阶段 0 → 7）

### 阶段 0 · 预检（只读，不做任何更改）

在**目标机**上跑 §1.1 的体检命令，逐条比对。任一硬门槛不满足 → **停手**。

同时确认三件事（决定 §7 走哪条路）：
1. 新机器狗的 103 是 `192.168.1.103` 吗？（是否与现有 103 同网段）
2. **两台车会同时上电吗？**
3. PC 到新 103 的通路怎么走？（103 无直连时需 `ProxyJump ysc@192.168.2.1`；
   PC 侧必须有 `192.168.1.0/24 → 192.168.2.1` 的**持久化**静态路由 `route add … -p`）

### 阶段 1 · 打包（103 上）

```bash
cd /home/test/yolo8
tar czf /tmp/yolo8.tgz --exclude=…（见 §3） src console deploy config note
md5sum /tmp/yolo8.tgz
```

### 阶段 2 · 传送

```bash
# 有 SSH 通路
scp /tmp/yolo8.tgz ysc@<新103>:/tmp/
# 无通路：U 盘 / 跳板机中转（模式 B）
```

### 阶段 3 · 解包与安装目录

```bash
mkdir -p /tmp/pkg && tar xzf /tmp/yolo8.tgz -C /tmp/pkg   # 中转站，装完即删
sudo rsync -a /tmp/pkg/ /home/test/yolo8/                 # 安装目录
sudo chown -R ysc:ysc /home/test/yolo8
mkdir -p /home/test/yolo8/{logs,pic,model/exports,model/uploads}
```

> **不要把 `/tmp/pkg` 当安装目录**（`/tmp` 会被清理，且没有"干净重装"这个动作）。

### 阶段 4 · 装依赖与日志治理

```bash
python3 -m pip install -U -i https://pypi.tuna.tsinghua.edu.cn/simple pycuda numpy opencv-python
bash /home/test/yolo8/deploy/install-retention.sh --check
printf "\047\n" | sudo -S bash /home/test/yolo8/deploy/install-retention.sh
```

### 阶段 5 · 安装 systemd 单元

```bash
sudo cp /home/test/yolo8/deploy/systemd/lite3-yolo-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lite3-yolo-console          # ★ 管理面自启
# lite3-yolo-publish 保持 disabled（worker 不自启是既定设计）
# lite3-yolo-rosbridge 保持 disabled（只有 dual 模式才需要）
sudo systemctl start lite3-yolo-console
```

### 阶段 6 · 改配置（★§5.1 五项）

改完 `config/yolo8.json` 后 **重启 console**；`rtsp_url`/`rtmp_url` 的生效看 worker 是否已消费 config
（P2 之后运行期配置以 config 为唯一来源，改完下次启动生效）。

### 阶段 7 · 起 worker 与验收

```bash
cd /home/test/yolo8
deploy/lite3-publish-ctl.sh start yolo        # ★ 必须走 ctl，让 logs/yolo.pid 存在
```

> **只起一个 worker**：`pgrep -af run_tracker_publish` 必须只有一行。
> 起后台 worker 的脚本要独立文件经 `ssh 'bash -s' < 脚本` 下发——
> 把 `setsid nohup … &` 塞进带 `&` 的长命令行会被 shell 吞掉后续命令，
> 本地 SIGTERM 后远程仍在跑，**会起出第二个 worker**（2026-10-23 踩过）。

见 §8 验收清单。

---

## 7. ★ 双机并存：现有 103 仍在线时的唯一性冲突

用户已确认"这台的部署也依旧保持着"，所以必须处理两台同时存在的冲突：

| 冲突项 | 分时上电（同一时刻只有一台） | 同时上电 |
|---|---|---|
| **IP** | 无冲突（两套都用 192.168.1.0/24，但不同时在线） | ❌ **必然冲突**：两套的 103 都是 `.103`、120 都是 `.120`。必须改其中一套的网段（103/120 静态 IP + 120 的 DHCP 与热点 + console 白名单） |
| **RTMP stream key** | 建议仍改（防误连） | ❌ **必须改**：同名 key 会被 SRS 互踢（已实测） |
| **console 白名单** | 沿用 `192.168.1.0/24` | 按新网段改 `allowed_cidrs` |
| **PC 侧路由** | 现有路由即可 | 需新增到新网段的路由；注意**加 `-p` 持久化** |
| **控制台辨识** | 靠 IP 区分 | 建议改端口或令牌，避免登错车 |

**建议做法**：给第二台车的 stream key 与 console token 各加后缀（如 `lite3_yolo_2`、独立强令牌），
这样无论分时还是并行都安全；IP 网段只在确认"会同时上电"时才动。

---

## 8. 验收清单

```bash
# 1) 单元与用户
systemctl is-active lite3-yolo-console                 # active
systemctl show lite3-yolo-console -p User --value      # 普通用户，非 root
systemctl is-enabled lite3-yolo-console                # enabled

# 2) worker（只应有一个）
pgrep -af run_tracker_publish                          # 1 行
cat logs/yolo.pid                                      # 与上面 PID 一致
deploy/lite3-publish-ctl.sh status yolo                # 进程运行

# 3) 推流健康（★最有说服力的一条）
python3 -c "
import json;d=json.load(open('logs/worker_state.json'))
print(d['stream']['rtmp_state'], d['worker']['frames'], d['stream']['pushed_frames'])"
#   期望：rtmp_state=running，pushed_frames 与 frames 同步（差值 < 几十帧）
#   ⚠ worker 启动到首次写 worker_state.json 要 ~2 min，别用状态新鲜度判断起没起来

# 4) 接口层
cd console && python3 p5-unit.py                       # 期望 51/51（真机 py3.8）
bash p5-accept.sh                                      # 期望 25/25
#   注：p5-accept 需登录拿 Cookie，走的 LAN IP（127.0.0.1 不在白名单）

# 5) 日志治理
bash /home/test/yolo8/deploy/install-retention.sh --check
logrotate --debug /etc/logrotate.d/lite3-yolo8 2>&1 | grep -c '^error:'   # 0

# 6) 面板抽检
#   占用卡有数 / 抓拍能出图 / 改阈值在线生效 / purge 的 409 判活保护（游离 worker 时应拒绝）
```

---

## 9. 回滚

```bash
# 应用层回滚：重放上一个包
sudo rsync -a --delete /tmp/pkg-prev/ /home/test/yolo8/
sudo systemctl restart lite3-yolo-console

# 彻底卸载
sudo systemctl disable --now lite3-yolo-console lite3-yolo-publish lite3-yolo-rosbridge
sudo rm -f /etc/systemd/system/lite3-yolo-*.service && sudo systemctl daemon-reload
sudo rm -f /etc/logrotate.d/lite3-yolo8 /etc/systemd/journald.conf.d/lite3-yolo8.conf
sudo rm -rf /home/test/yolo8
```

---

## 10. 常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| engine 加载失败 / worker 起不来 | 目标机 TRT 版本 ≠ 8.5.2.2 | 用包里的 `yolov8n.pt/onnx` 现地重导（先删 `.trt-timing-cache`） |
| `Could not write to resource` + pipeline 递增 | **两个 worker 抢同一个 rtmp key** | 只留一个 worker；换 stream key |
| worker"莫名退出" | 多半是**被 `ctl stop` 优雅杀掉**（日志尾行 `stopping, frames=… elapsed=…`），而现场日志又被 purge 清空 | 用 `pgrep -af run_tracker_publish` 判活，**不要用 `grep yolo`**（进程名是 `python3 -u run_tracker_publish.py`） |
| purge 在 worker 写图时清空数据 | worker 游离启动（无 `logs/yolo.pid`）导致判活失效 | 一律走 `ctl start`；新代码已加 409 拒绝保护 |
| console 403 | `allowed_cidrs` 没改，或 PC 丢了静态路由 | 改白名单；路由要 `route add … -p` 持久化 |
| 服务 `status=203/EXEC` | 安装路径含空格 / `#` / `&` | 换路径重装 |
| 服务以 root 运行 | 用 root 直跑 sudo，`SUDO_USER` 为空 | `useradd` 后重装，或改单元 `User=` |
| 抓拍被禁 | 磁盘低于 `min_free_gb=5` | 清理或调阈值 |
| pip 装不上 | 外网只通国内 | 挂清华源 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| logrotate 不生效 | `logs/` 是 group-writable 却没写 `su` | `install-retention.sh` 会按 `stat -c "%U %G"` 渲染 |

---

## 11. 一页速查

```bash
# ── 源机 103：打包 ─────────────────────────────────────
cd /home/test/yolo8
tar czf /tmp/yolo8.tgz --exclude='logs/*' --exclude='pic/*' \
  --exclude='deploy/backup-*' --exclude='__pycache__' \
  --exclude='model/yolov8n_amd.engine' --exclude='model/exports/*' \
  --exclude='*.bak-*' --exclude='.git' src console deploy config note

# ── 目标机：装 ─────────────────────────────────────────
mkdir -p /tmp/pkg && tar xzf /tmp/yolo8.tgz -C /tmp/pkg
sudo rsync -a /tmp/pkg/ /home/test/yolo8/ && sudo chown -R ysc:ysc /home/test/yolo8
mkdir -p /home/test/yolo8/{logs,pic,model/exports,model/uploads}
printf "\047\n" | sudo -S bash /home/test/yolo8/deploy/install-retention.sh
sudo cp /home/test/yolo8/deploy/systemd/lite3-yolo-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lite3-yolo-console

# ── ★ 改配置（换机必改四项）─────────────────────────────
#   config/yolo8.json: source.rtsp_url / stream.rtmp_url(key 换!) /
#                      console.allowed_cidrs / console.token(换强令牌)
printf "\047\n" | sudo -S systemctl restart lite3-yolo-console

# ── 起 worker（只起一个！）──────────────────────────────
cd /home/test/yolo8 && deploy/lite3-publish-ctl.sh start yolo
pgrep -af run_tracker_publish          # 必须只有 1 行

# ── 验收 ────────────────────────────────────────────────
python3 console/p5-unit.py             # 51/51
bash console/p5-accept.sh              # 25/25
```

> sudo 口令在 Lite3 上是**半角单引号** `'`；非交互场景用 `printf "\047\n" | sudo -S …`。

---

## 12. 未闭环（换机前请知悉）

| 项 | 状态 |
|---|---|
| 第二台车端到端 | **未验证**。本流程所有事实来自 103 单台实测 + 配置盘点，同构推理成立，但"另一台从未装过的车"需现场跑一遍 |
| 两台车同时上电的 IP 冲突处理 | 只给了策略，**未实测**（取决于现场是否会同时开机） |
| `yolov8n_arm.engine` 跨 JetPack 小版本 | 未验证；建议现场先试加载，失败再用 pt/onnx 重导 |
| console token 硬编码在 config 且改后需重启 | 已知限制；换机时一并换强令牌 |
| 103 的 git 改动全部未提交 | 打包建议以**磁盘实际内容**为准，不要以本地镜像为准（镜像可能滞后） |
