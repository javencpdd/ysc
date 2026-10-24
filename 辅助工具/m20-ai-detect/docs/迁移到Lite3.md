# 迁移到 Lite3（感知/导航主机 103）

> 目标：把 `m20-ai-detect`（采样器）+ Web 控制台装到 **Lite3**，用上它已有的相机流做 AI 检测。
> 本文只讲"怎么迁"，不讲"要不要迁"；迁移后 M20 上的部署**不受任何影响**（APP_ID 隔离）。
>
> 数据出处：2026-10-20 在 103/120 上实测（见 §7 原始输出），不是推断值。
> 命令脚本全部对应仓库里的 `deploy/preflight.sh`、`install.sh`、`install-local.sh`、
> `bootstrap.sh`、`console-bootstrap.sh`、`migrate-rename.sh`；改脚本请同步改本文。

---

## 0. 结论先行（四句话）

| 决策项 | 结论 | 一句话理由 |
|---|---|---|
| **部署在哪台机** | **103（`lite`，192.168.1.103）** | 有 ffmpeg、磁盘 42 G、不占运动控制 CPU、直连出网 AI 200 |
| **相机源用什么** | 复用 120 已有的 MediaMTX 流：`rtsp+tcp://192.168.1.120:8554/test` | 1280×720@30 已发布，103 抓帧实测通过（rtt 0.61 ms、0 丢包） |
| **身份（APP_ID）** | `lite3` | unit / env / helper / sudoers / journal 全部自动改名，不与 M20 撞 |
| **绝不要碰** | 120 上的 `rtsp_stream` / `rtmp-forward`；`device://` 本地相机 | 120 无 ffmpeg 且相机已被它的 gst 采集管线占着，重复开采集必冲突 |

> ⚠️ **`APP_ID` 是"平台/部署身份"，不是登录账户。** 账户是 `ysc`，但 ysc 走的是另一条路——`RUN_USER`
> （unit 的 `User=`），它**缺省取当前登录用户**（`identity.sh:123`），在 103 上用 ysc 登录部署就
> 自动是 ysc，**site.env 里不需要、也没有这一项**。把 `APP_ID` 写成 `ysc` 不会让服务以 ysc 运行
> （那是 `User=` 干的活），只会得到 `ysc-ai-detect.service`、`/etc/sudoers.d/ysc-ai-console` 这类
> 名字，控制台顶栏还会显示"ysc"——同机再迁一套 M20 上来时两者无法区分。详见 §4.7。

---

## 1. 主机与角色（实测）

| | **103（部署位）** | **120（相机源，不动它）** |
|---|---|---|
| 别名 / IP | `lite3-f20-1-103` = 192.168.1.103 | `lite3-f20-1-120` = 192.168.1.120（另 192.168.0.197 / 192.168.2.1 / 192.168.137.120） |
| 账户 | `ysc` | `ysc` |
| 硬件 | Jetson/Tegra，内核 5.10.120-tegra，aarch64 | RK3588 |
| CPU / 内存 | 6 核 / 6.7 G（可用 5.3 G） | 8 核 / 3.9 G（可用 3.1 G） |
| Python | **3.8.10 ✅** | 3.8.10 |
| ffmpeg | **4.2.7 ✅** | **❌ 未安装**（`command not found`） |
| 磁盘可用 | **42 G ✅**（117 G 盘，64%） | 8.8 G（28 G 盘，68%）— 偏紧 |
| systemd | 245（Ubuntu 20.04）✅ | 有 |
| 出网（AI 服务） | **HTTP 200 ✅** | HTTP 200 ✅ |
| 5050 端口 | **空闲 ✅** | 空闲 |
| 相机相关 | 无 | `/dev/video0`；8554(RTSP)/1935(RTMP)/8888(HLS) 在听，`/test/index.m3u8` = 200 |
| 现有职责 | 感知 / 导航 / ROS 桥接（`lite3-monitor*`、`lite3-ros-bridge*`） | 运动控制 + 相机采集 + RTMP 外推 |

---

## 2. 为什么部署位选 103 而不是 120

三条硬理由，任一都足以否定 120：

1. **120 没有 ffmpeg** —— 抽帧/抓帧全靠它，得先 `apt install ffmpeg`（28 G 盘只剩 8.8 G，且是现场机器）。
2. **120 是运动控制主机** —— 实时性敏感，把"每帧一次 HTTP 推理 + ffmpeg 常驻"叠上去风险不对等；103 是 Jetson 且本就跑感知类负载。
3. **120 磁盘 8.8 G** —— 本工程 `raw/ results/ saved/ spool/` 就长在项目根下，按 1 fps 单路跑，磁盘是持续消耗项。

代价（可接受）：103 要**跨机**拉 120 的 RTSP。实测 103→120 同在 `192.168.1.0/24`（eth1 LAN）：
`ping` 0% 丢包 / rtt 0.61 ms，`ffmpeg -rtsp_transport tcp` 抓帧成功（1280×720、30 fps）。
单路 1 fps 抽帧的带宽量级远低于这条链路的能力，跨机这一跳不成问题。

> **反过来的场景**：如果将来要在 Lite3 上跑"本地 USB 相机 + 本机检测"，那才是 120 的活儿——
> 但即便如此也**不要**用 `device:///dev/video0` 去抢 120 上已被 `rtsp_stream` 占用的相机，
> 正确做法是让 120 把第二路流也发到 MediaMTX，103 继续拉 RTSP（§5 第 4 条）。

---

## 3. 先决条件（部署前逐条确认）

| 项 | 要求 | Lite3 103 现状 | 怎么确认 |
|---|---|---|---|
| SSH 免密 | 开发机能 `ssh ysc@192.168.1.103` | ✅ 已密钥化（别名 `lite3-f20-1-103`） | `ssh -o BatchMode=yes lite3-f20-1-103 hostname` |
| Python | ≥ 3.6（零第三方依赖） | ✅ 3.8.10 | `python3 -V` |
| ffmpeg | 已安装 | ✅ 4.2.7 | `ffmpeg -version \| head -1` |
| 磁盘 | ≥ 5 G | ✅ 42 G | `df -h /home` |
| 相机源 | 103 能取到 1 帧 | ✅ 实测通过 | 见 §7 命令 ② |
| AI 服务 | 能访问 `M20AI_AI_BASE` | ✅ HTTP 200 | `curl -m 8 -o /dev/null -w '%{http_code}' http://jsxy.aihyzh.com:30881/` |
| 5050 端口 | 空闲 | ✅ | `ss -ltn \| grep :5050` |
| sudo | 装 unit / logrotate 需要 | ⚠️ **需要口令**（非免密） | `sudo -n true` |
| 旧部署 | 无冲突 | ✅ 无 unit、无同名目录 | `ls /etc/systemd/system \| grep ai-detect` |

关于 sudo：本机 ysc 账户**不是免密**（实测 `needpass`）。`bootstrap.sh` / `console-bootstrap.sh`
内置了非交互取口令的写法（与 M20 部署用的是同一套），正常跑即可；
**口令不在本文档记录**。若脚本卡在 sudo，手工执行一次确认口令可用再重跑。

---

## 4. 操作步骤

### 4.1 填 `deploy/site.env`（开发机，一次填好）

```bash
cd 辅助工具/m20-ai-detect
cp deploy/site.env.example deploy/site.env
```

按 Lite3 填（其余留空 = 用模板默认）：

```bash
# ---------- 部署身份（ADR-017：改名只改这一行）----------
APP_ID=lite3
M20AI_PLATFORM_NAME=Lite3 · 单目

# ---------- 目标机 ----------
DEPLOY_HOST=ysc@192.168.1.103
DEPLOY_DIR=/home/ysc/lite3-ai-detect

# ---------- 视频源（ADR-016：任意 N 路，设了即覆盖旧两槽位）----------
# main = 120 上 MediaMTX 已发布的相机流；aux 留 |off 占位，将来加相机不用改语法
M20AI_SOURCES=main=rtsp+tcp://192.168.1.120:8554/test|fps=1;aux=rtsp+tcp://192.168.1.120:8554/test2|off

# ---------- 采集与留存 ----------
M20AI_FPS=1
M20AI_SAVE_MODE=alert
M20AI_SPOOL_MAX_FILES=600

# ---------- 控制台 ----------
M20AIC_PORT=5050
```

要点：

- **`APP_ID=lite3`** 一改，unit 名（`lite3-ai-detect.service` / `lite3-ai-console.service`）、
  env 文件名（`lite3-ai-detect.env`）、helper、sudoers、logrotate、journal 标识**全部自动跟随**，
  手工不需要改任何东西（详见 `docs/ADR-017-身份与命名.md`）。
- **`DEPLOY_DIR` 用 `lite3-ai-detect` 而不是 `m20-ai-detect`**：目录名不参与身份解析，
  但同机多身份时名字要能一眼分清；`M20AI_BASE_DIR` 会被强制等于 `DEPLOY_DIR`。
- **源地址写 `rtsp+tcp://`**：跨机走 TCP 更稳（弱网/NAT 后不丢包），代价约 1 帧缓冲时延；
  本工程适配层会自动加 `-rtsp_transport tcp`。
- 协议前缀 `rtsp+tcp://` 与 `rtsp://` 都是合法 scheme，解析后 `type` 由 scheme 推导，无需手填。

> `APP_ID` 该填 `lite3` **不是 `ysc`**：前者是平台身份（决定对外的所有名字），
> 后者是登录账户（决定进程以谁跑）。完整辨析见 §4.7。

### 4.7 两个"身份"不要混：`APP_ID` vs 运行账户

这是迁移时最容易填错的一项（已实测确认过分工，见 `deploy/identity.sh:120-128`）：

| | **`APP_ID`** | **`M20AI_RUN_USER`（运行账户）** |
|---|---|---|
| 含义 | 这个部署**是什么平台/是什么服务** | 进程**以哪个账户的身份运行** |
| 在哪填 | `site.env` 的 `APP_ID`，或老部署的 `M20AI_APP_ID` | 一般**不用填**；缺省 = 当前登录用户（`id -un`） |
| 决定什么 | unit 名、env 文件名、helper 路径、sudoers 路径、journal 标识、logrotate 名、控制台顶栏展示名 | unit 的 `User=` / `Group=`、数据目录属主 |
| Lite3 该填 | `lite3` | `ysc`（**自动**，因为你就是用 ysc 登录的） |
| 语义反例 | 机器换了、部署的人换了，它就**不该**跟着变 | 换成 `user` 登录部署，它就**该**跟着变 |

为什么不能拿账户名当 APP_ID：

1. **它根本不是干这个的**——unit 的 `User=` 由 `RUN_USER` 填，写 `APP_ID=ysc` 对"以谁运行"
   没有任何影响，只是白改一堆名字；
2. **它是多副本隔离键**——将来同机再迁一套 M20 上来（`m20` + `lite3` 两套并存），
   靠 `APP_ID` 区分 unit/env/sudoers，用用户名就分不出来了；
3. **展示名会露馅**——没有 `M20AI_PLATFORM_NAME` 时，控制台顶栏显示的就是 `APP_ID`，
   你会在 Lite3 的页面上看到"ysc"。

`APP_ID` 字符集 `^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`（`ysc` 合法，但语义是错的）。

### 4.2 先体检（可选但推荐）

```bash
./deploy/install.sh ysc@192.168.1.103 --check       # 只读：host/user/os/python/ffmpeg/磁盘/内存/5050
```

或把代码放上去后在目标机跑完整预检（7 组约 20 项，退出码 0 = 可装）：

```bash
ssh ysc@192.168.1.103
cd /home/ysc/lite3-ai-detect && bash deploy/preflight.sh --base /home/ysc/lite3-ai-detect
# 离线/相机没上电：加 --skip-network；严格模式（WARN 也算不过）：加 --strict
```

> ⚠️ 已知误报：preflight 第 1 组会把"运行账户不是 `user`"报成 WARN，并提示"unit 写死 User=user"。
> **该提示已过时**——unit 自 ADR-017 起由 `deploy/units/*.tmpl` 渲染，`User=` 取 `M20AI_RUN_USER`
> （缺省当前登录用户）。Lite3 上看到这条 WARN 可忽略，不必改任何文件。

### 4.3 推送代码（开发机）

```bash
./deploy/install.sh ysc@192.168.1.103 --no-restart
```

会做：本地跑 418 项测试 → 检查 pkill 禁词（`push_video`/`v4l2`/`gst-launch`）→ 检查 CRLF
→ 远端备份 → rsync 同步（自动排除 `spool/ raw/ results/ saved/ log/` 等数据目录）
→ 远端 `import` 自检。**首次部署必须 `--no-restart`**（unit 还没装，重启会失败）。

离线/只有文件夹时改走模式 B（目标机上跑）：

```bash
bash deploy/install-local.sh --from /home/ysc/lite3-ai-detect-new
```

### 4.4 首次引导（目标机 103）

```bash
ssh ysc@192.168.1.103
cd /home/ysc/lite3-ai-detect && bash deploy/bootstrap.sh
```

会：检查 ffmpeg/python3 → 建 `spool/ raw/ results/ alerts/ log/ tmp/` → 生成 `lite3-ai-detect.env`
→ 按 `APP_ID=lite3` 渲染并安装 unit → `daemon-reload` → 装 logrotate → **跑 doctor 门禁**
（AI 服务 / 相机源 / 时钟 / 磁盘）。doctor 不全绿会停下并给排查指向，不会盲目起服务。

> 若 unit 的 `User=` 需要指定（当前登录用户即 ysc，一般不用）：
> `M20AI_RUN_USER=ysc bash deploy/bootstrap.sh`

### 4.5 装 Web 控制台

```bash
ssh ysc@192.168.1.103 'cd /home/ysc/lite3-ai-detect && bash deploy/console-bootstrap.sh'
```

会：生成 `lite3-ai-console.env`（5050）→ 装 root helper `/usr/local/sbin/lite3-ai-console-helper`
+ sudoers 白名单（`visudo -c` 校验）→ 装 `aiDetect` 命令 → 装 `lite3-ai-console.service`
→ 前台冒烟 5 秒（验 `/api/status` 与首页 200）→ 启动常驻。

### 4.6 追加平台 profile（可选）

`bootstrap.sh` 生成的 env 是通用默认值；把 Lite3 的平台片段追加进去更省事：

```bash
cd /home/ysc/lite3-ai-detect
# profile 里的示例 IP/路径仍要按现场改（本仓库那份写的是 192.168.2.103:8554/live，实测应为 192.168.1.120:8554/test）
grep -v '^M20AI_SOURCES=' deploy/profiles/lite3-single.env >> lite3-ai-detect.env
```

更推荐的做法：**部署后直接用控制台「视频源与采集」卡改**——增删改启停与手写 env 走同一条
校验路径（源名重复、全停用、地址含分隔符都在落盘前拦下），改完自动按 ADR-010 语义重启。

---

## 5. 验收清单

```bash
# ① 门禁（doctor 全绿）
ssh ysc@192.168.1.103 'cd /home/ysc/lite3-ai-detect && set -a && . ./lite3-ai-detect.env && set +a && PYTHONPATH=src python3 -m m20_ai_detect doctor'

# ② 服务状态
ssh ysc@192.168.1.103 'systemctl is-active lite3-ai-detect lite3-ai-console'

# ③ 取帧（未开采集时走即时抓帧，也应能出图）
ssh ysc@192.168.1.103 'curl -s "http://127.0.0.1:5050/api/snapshot?cam=main" | head -c 120'

# ④ 开采集 30 秒，看是否真落盘
ssh ysc@192.168.1.103 'curl -s -X POST http://127.0.0.1:5050/api/service -H "Content-Type: application/json" -d "{\"action\":\"start\"}"'
# 等 20 s：
ssh ysc@192.168.1.103 'ls -lt /home/ysc/lite3-ai-detect/raw/main | head -3; ls /home/ysc/lite3-ai-detect/spool/main | wc -l'
```

浏览器打开 `http://192.168.1.103:5050/`：指标卡有数、相机画面出图、日志有内容、
检测数据与留存卡对得上。

**关键观察点**：`/api/snapshot` 的 `source` 在采集运行时应为 `ring`（读本地帧，~60 ms）；
若长期是 `live`，说明采集没在正常落盘（先看 `journalctl -u lite3-ai-detect -n 30`）。

> Lite3 的 journald 是 **volatile**（`/var/log/journal` 不存在，`journald.conf` 里
> `#Storage=auto` 未改，重启即清）。跨重启的历史只能靠 rsyslog 落盘的 `/var/log/syslog*`；
> 实测 ysc 在 `adm` 组，可以直接读它（`sudo` 不是必需的）。
> **迁移后建议第一件事就是把 journal 开成持久化**（§6.2，一条命令），
> 否则"重启就好了"的故障永远没有证据可查。

---

## 6. Lite3 特有差异与坑（附可解决性评估）

> 2026-10-20 复核：10 条里**没有一条会阻塞迁移**（0 个必须解决）。
> 真正建议动手的只有第 7 条（journald 持久化，一条命令 5 分钟）；
> 第 3 条经实测**已经解决**，第 7 条的"ysc 不在 adm 组"经实测**不成立**。

| # | 差异 / 坑 | 可解决性 | 处理方案 | 迁移前必须？ |
|---|---|---|---|---|
| 1 | **120 无 ffmpeg** | ✅ 能解决，但**不必** | 部署位选 103（有 ffmpeg 4.2.7）已天然绕开。真要装：实测 apt 源可达 `Candidate: 7:4.2.7-0ubuntu0.1`，`sudo apt install -y ffmpeg` 即可（8.8 G 盘够） | ❌ 不必 |
| 2 | **相机在 120、算力在 103** | ✅ **已解决** | 跨机 RTSP 是架构选择而非缺陷：实测 0 % 丢包 / rtt 0.61 ms，单路 ~3.7 Mbps 常驻，LAN 无压力。源写 `rtsp+tcp://192.168.1.120:8554/test` | ❌ 不必 |
| 3 | **103 出网依赖 120 的 NAT** | ✅ **已解决**（实测三重保险） | 见 §6.1。仅剩开机瞬间的一个窗口期 | ❌ 不必 |
| 4 | **不要在 120 重复开采集** | ➖ 是约束不是缺陷 | 复用 RTSP 即可；将来加相机让 120 的 MediaMTX 多发一路 path，103 继续拉 RTSP | ❌ 不必 |
| 5 | **preflight 账户 WARN 误报** | ✅ 能解决（改 2 行判据） | 忽略即可（见 §4.2）；洁癖可修 `preflight.sh:67-68` | ❌ 不必（仅观感） |
| 6 | **sudo 非免密** | ✅ 能解决 | 保持现状即可——`bootstrap.sh` 内置非交互取口令。只有要做无人值守自动化时，才配 sudoers `NOPASSWD` **最小白名单**（不要全开） | ❌ 不必 |
| 7 | **journald 是 volatile** | ✅ 能解决（一条命令） | 见 §6.2。**建议做**：否则"重启就好了"的故障无证据可查 | ⭕ 建议 |
| 8 | **103 跑 ROS，怕抢资源** | ⚠️ 可缓解不可根除 | 默认 1 fps 负载极轻（抽帧 + 每帧一次 HTTP）。要提 `M20AI_FPS` 到 2 以上前，先实测 ROS 话题频率；必要时用 unit 的 `CPUAffinity` / `Nice` 限 | ❌ 当前不必 |
| 9 | **两套机器共用 AI 服务** | ✅ 能解决（配额/错峰） | M20 两路 + Lite3 一路 ≈ 3 req/s，量级极小；真到瓶颈再分能力 ID 或错峰 | ❌ 当前不必 |
| 10 | **pkill 禁词** | ✅ **已规避** | 复用 RTSP 流，命令行不含 `push_video`/`v4l2`/`gst-launch`；`install.sh` 有门禁兜底 | ❌ 不必 |

### 6.1 第 3 条：103 出网的 NAT —— 实测已经解决

2026-10-20 在 120 上实测，三重保险都在位：

```
$ sudo iptables -t nat -S POSTROUTING | grep 192.168.1
-A POSTROUTING -s 192.168.1.0/24 -o wlan0 -j MASQUERADE      # ① 运行中

$ grep -n 192.168.1.0/24 /home/ysc/host/host_start2.sh
17:iptables -t nat -A POSTROUTING -s 192.168.1.0/24 -o wlan0 -j MASQUERADE   # ② 开机由 host.service 恢复

$ grep -n 192.168.1.0/24 /etc/iptables/rules.v4
2:-A POSTROUTING -s 192.168.1.0/24 -o wlan0 -j MASQUERADE    # ③ rules.v4 留存
```

**残余风险只剩时序**：`host_start2.sh` 开头有等待 `p2p0` 的循环，规则在开机后
**延迟一段时间**才生效 → 这段窗口里 103 可能短暂不通（表现为 doctor 的 AI 项 FAIL）。

| 想做到什么程度 | 做法 |
|---|---|
| 现状（够用） | 什么都不做；AI 短暂不可达时本工程有 `M20AI_SPOOL_MAX_FILES=600` 上限保护，**最坏是检测停摆但有界**，不会写爆磁盘 |
| 想消除窗口期 | 装 `netfilter-persistent` 让 `rules.v4` 在 `netfilter-persistent.service`（`network-pre.target`）恢复，比 `host.service` 更早 |
| 想要可观测 | doctor 已经会报 AI 项；再想告警就盯 103 上 `spool/` 的增长速率 |

### 6.2 第 7 条：journald 持久化（唯一建议动手的一条）

```bash
# 103 上执行（改完对 M20 无任何影响）
printf "\047\n" | sudo -S mkdir -p /var/log/journal
printf "\047\n" | sudo -S systemd-tmpfiles --create --prefix /var/log/journal
printf "\047\n" | sudo -S systemctl restart systemd-journald
# 顺手限住体积，别让它无限涨
printf "\047\n" | sudo -S sed -i 's/^#\?SystemMaxUse=.*/SystemMaxUse=200M/' /etc/systemd/journald.conf
printf "\047\n" | sudo -S systemctl restart systemd-journald
journalctl --disk-usage          # 确认生效
```

验证：`ls -d /var/log/journal` 存在 + `journalctl --list-boots` 能列出多次启动，即为持久化成功。

**关于"读日志要 sudo"**：实测 103 与 120 的 `ysc` **都在 `adm` 组**
（`id -nG ysc` 含 `adm`），`/var/log/syslog` 是 `-rw-r----- 1 syslog adm`
—— 所以**直接 `cat` 就能读，不必 `sudo`**。
（早期笔记里"ysc 不在 adm 组"的说法在两台机上均已不成立，以实测为准。）

---

## 7. 回滚

`install.sh` 每次会在远端留备份：

```bash
ssh ysc@192.168.1.103 'ls -lt /home/ysc/lite3-ai-detect/.backup | head'
ssh ysc@192.168.1.103 'cd /home/ysc/lite3-ai-detect && tar xzf .backup/code-<TS>.tar.gz && sudo systemctl restart lite3-ai-detect'
# env 回滚：cp .backup/env-<TS> lite3-ai-detect.env && sudo systemctl restart lite3-ai-detect
```

彻底撤掉（不保留身份）：

```bash
sudo systemctl stop lite3-ai-detect lite3-ai-console
sudo systemctl disable lite3-ai-detect lite3-ai-console
sudo rm -f /etc/systemd/system/lite3-ai-detect.service /etc/systemd/system/lite3-ai-console.service \
            /usr/local/sbin/lite3-ai-console-helper /etc/sudoers.d/lite3-ai-console \
            /etc/logrotate.d/lite3-ai-detect
sudo systemctl daemon-reload
# 数据目录确认不要了再删：/home/ysc/lite3-ai-detect/{raw,results,saved,spool}
```

**开机自启**：默认**不 enable**（ADR-008 语义，重启后手动起）。要自启：
`sudo systemctl enable lite3-ai-detect lite3-ai-console`。

---

## 8. 附录：实测原始输出（2026-10-20）

**① 103 主机条件**

```
ysc / lite
Python 3.8.10
ffmpeg version 4.2.7-0ubuntu0.1
/dev/mmcblk1p1  117G   71G   42G  64% /
Mem: 6854 MB（可用 5351 MB），nproc 6
8554/1935/5050/8888 均未监听
AI_http=200
sudo: needpass    systemd 245    /home/ysc 可写    无旧部署
```

**② 103 → 120 相机流（成败关键，已通过）**

```
$ ping -c 2 -W 2 192.168.1.120
2 packets transmitted, 2 received, 0% packet loss, rtt 0.594/0.610/0.627 ms

$ timeout 25 ffmpeg -nostdin -rtsp_transport tcp -i rtsp://192.168.1.120:8554/test -frames:v 1 -f null -
Stream #0:0: Video: ..., yuv420p, 1280x720, 30 fps
frame=    1 fps=0.0 q=-0.0 Lsize=N/A
```

> 抓帧命令**必须带 `-nostdin` 且 stdin 指向 `/dev/null`**：否则 ffmpeg 进入交互命令模式，
> 一直等输入直到被 timeout 杀掉，会出现"明明能抓到帧却报相机不可达"的假故障。

**③ 120 主机条件**

```
Python 3.8.10     ffmpeg: command not found     nproc 8     Mem 3902 MB
/dev/root  28G  18G  8.8G  68% /
ss -ltn: 8554 / 1935 / 8888 LISTEN
curl http://127.0.0.1:8888/test/index.m3u8 → 200（BANDWIDTH=3683624, 1280x720, 30fps）
/dev/video0 / /dev/video1 存在
```
