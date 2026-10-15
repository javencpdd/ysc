# m20-ai-detect 使用手册

> 面向**使用者**的日常操作指南。开发/部署/架构背景见 `README.md` 与 `docs/ADR-*`。
> 系统当前状态：**已在 GOS（10.21.31.104）部署并常驻运行**，前视相机 1 fps 采集检测中；
> 可视化控制台同在 104 运行，浏览器开 **http://10.21.31.104:5050** 即用（见 §2）。

## 0. 三十秒上手

**方式 A：浏览器（推荐，什么都不会也能操作）**

```
打开 http://10.21.31.104:5050
```

页面能看到服务活没活、最近检测到什么、运行日志；改配置、启停服务、清理日志都在页面上点。

**方式 B：命令行（主机上的 `aiDetect` 命令）**

```bash
ssh m20pro-GOS.104            # 登上 GOS（唯一入口）
aiDetect status               # 一屏总览：服务/采集/自启/版本/积压/磁盘/最近检测
aiDetect up                   # 起控制台（网页 5050）——只起控制台，不开采集
aiDetect collect on           # 开采集（或直接点网页「采集开关」）；off 则停
aiDetect collect off          # 停采集：不再抽帧调 AI；网页仍可查历史数据
aiDetect reset                # 积压太多？清空 spool/ 并以实时为准
aiDetect log -n 50            # 最近 50 行日志（-f 跟踪、-g 关键词过滤）
```

> `aiDetect` 是随控制台一同装入的终端命令（`/usr/local/bin/aiDetect`）。若提示 command not found，先去 104 跑一次 `cd /home/djw/m20-ai-detect && bash deploy/console-bootstrap.sh` 装入；完整子命令见 §5。

> 注意：远端登录账户是 `user`，`~` 展开是 `/home/user`，**工程在 `/home/djw/m20-ai-detect`，一律用绝对路径**。
> 裸 `sudo` 无 TTY 时用 `printf "'\n" | sudo -S <命令>`（口令为半角单引号）——日常用 `aiDetect` 则不需要记这些。

## 1. 系统在做什么

AOS 相机（前视 video1）→ RTSP 内网流 → **GOS 上的采样器**（ffmpeg 常驻抽帧 1fps）→ 公网 AI 服务做 YOLOv8 目标检测 → 结果落四个地方：

| 出口 | 内容 | 保留策略 |
|---|---|---|
| `results/*.jsonl` | **权威数据**：每帧一行的结构化检测结果（含告警标记） | **永不删除**，按需手动归档 |
| `raw/<cam>/` | 原始帧 JPEG | 环形缓冲 200MB，超限删最旧 |
| `saved/<cam>/` | 条件留存的**成对证据**：标注结果图 .jpg + 原始响应 .json（含真实时间 `_saved_at`） | 按 `M20AI_SAVE_MODE` 条件写入（默认 off=不存）；**超上限/天数后从最旧自动清理**（默认上限 500MB，见 §2.5/§2.6） |
| `alerts/<cam>/` | 旧版告警图目录（已废弃，新逻辑走 `saved/`） | 通常为空 |

## 2. Web 控制台（推荐入口）

浏览器开 **`http://10.21.31.104:5050`**（机器人内网；AOS 没有入站 DNAT，外网访问不到，这是有意的边界）。

### 2.1 页面上有什么

| 区域 | 能做什么 |
|---|---|
| 状态总览 | 采样器/控制台两个服务的运行状态、磁盘占用、今日帧数/告警数、AI 服务健康与时钟偏移 |
| 采集开关 | 采集（采样器）的开启 / 停止 / 重启（等价于 `aiDetect collect`，**默认关闭**，ADR-010） |
| 相机画面 | **当前相机实时画面**（ADR-012）：采集运行中显示采样器**当前帧**（即检测器输入），未运行则从同一路 RTSP **即时抓帧**；自动刷新 3 秒、可手动刷新，多相机可切换。看画面时不用再跳别的系统 |
| 目标图片时间轴 | **滑动时间条回看检出图**（数据 = `saved/` 留存图，按真实时钟排序）；点图看完整响应；「跟随最新」自动跳到新图。见 §2.6 |
| 最近检测 | **今日真实检测记录**（读 JSONL 尾部）：每帧的时间、检出几个目标、`person 0.81` 这样的标签+分数、或「未检出任何目标」、告警徽标、已留存徽标。**点任一帧看完整响应**（见 §2.5） |
| 检测配置 | 检测能力下拉（AI 服务 33 项能力实时拉取）、抽帧帧率、环形缓冲、AI 服务地址、推理参数（obj/nms 双滑块）——**保存即写 env；采集运行中自动重启生效，停着的不拉起** |
| 相机与采集 | 前/后视相机开关与流地址（后视 `M20AI_SRC_B` 已预填） |
| 关注目标 | **「只保存检测到什么目标」的清单**（ADR-011）：分数阈值 `M20AI_ALERT_SCORE` + 标签集合 `M20AI_ALERT_LABELS`；带**今日检出标签**一键点选。命中即计入告警，且 `SAVE_MODE=alert` 时保存图片（见 §2.5） |
| 单帧检测 | 拖一张图进去 → 选能力 → 出检测结果、标注图与**原始响应 JSON**；勾选「保存这一帧」可把图+响应留存到 `saved/console/`。控制台侧能力，与采样器的实时检测互不影响 |
| 运行日志 | `journalctl -u m20-ai-detect` 的网页版：级别过滤（全部/告警/失败/启动/正常）+ 关键字搜索 + 自动刷新 + 按级别着色 |
| 数据文件（只读浏览） | 逐级点开 `saved/`、`raw/`、`results/`、`spool/`、`log/`；点文件即预览（图片直显、文本读末尾 N 行），每行提供下载直链。见 §2.7 |
| 留存策略 | journal 日志清理（vacuum）、journald 上限、ring 上限、results 保留天数（0=永不删）、**saved/ 图片上限 `SAVED_MAX_MB` 与保留天数 `SAVED_KEEP_DAYS`**、**响应留存条件 `SAVE_MODE`**、**清理数据**（勾选清空 `saved/`/`results/`/`raw/`/`spool/` 并显示当前占用；停采集仅当运行中、清完恢复原状态，ADR-011）、logrotate 手动轮转 |

### 2.2 和命令行是什么关系

**UI 与 CLI 同源**：页面上改的每一项，落的都是 `/home/djw/m20-ai-detect/m20-ai-detect.env` 这同一个文件；页面上的启停，走的是 systemd 的同一个 unit（终端里的 `aiDetect down/up/reset` 也一样，见 §5）。两边看到的状态永远一致，不存在"页面上改了没生效"。

控制台服务本身叫 `m20-ai-console`（也是 systemd 常驻），它自己的日志：

```bash
journalctl -u m20-ai-console -f
```

### 2.3 鉴权与边界

- **默认开放**（未设 TOKEN），内网谁都能开——机器人内网本就是可信环境；
- 若配了 `M20AIC_TOKEN`（在 `m20-ai-console.env` 里），页面右上角填入同一个值即可，API 调用需带 `X-Console-Token` 头；
- 写操作（启停/改配置/清理日志）在主机侧经 **sudoers 白名单**调 root helper 完成，`user` 拿不到裸 root；每次提权调用在系统日志留痕（GOS 无 rsyslog、走 journald：`journalctl -t m20-ai-console-helper -n 20`），可审计；
- 控制台**不监听外网**：改绑定地址需同时改 `m20-ai-console.env` 的 `M20AIC_BIND` 并重启 `m20-ai-console`。

### 2.4 控制台自己的管理

```bash
aiDetect status                  # 最省事：一眼看到服务与采集状态
aiDetect restart                 # 重启控制台（改过控制台代码/配置后）
aiDetect down                    # 停控制台（网页打不开，采集不受影响）

systemctl status m20-ai-console --no-pager     # 状态
# 停/起控制台（页面就打不开了，采样器不受影响，继续检测）
printf "'\n" | sudo -S systemctl restart m20-ai-console
```

卸载控制台（保留采样器）：

```bash
printf "'\n" | sudo -S systemctl disable --now m20-ai-console
printf "'\n" | sudo -S rm /etc/systemd/system/m20-ai-console.service
printf "'\n" | sudo -S rm /etc/sudoers.d/m20-ai-console /usr/local/sbin/m20-ai-console-helper /usr/local/bin/aiDetect /usr/local/bin/aidetect
printf "'\n" | sudo -S systemctl daemon-reload
```

设计细节（为什么独立服务、为什么零依赖、白名单清单）见 **`docs/ADR-005-可视化控制台.md`**。

### 2.5 看某一帧的完整响应（ADR-006）

点「最近检测」里任一帧，弹出响应详情：

- **解析结果**：检出了几个目标、每个的 `label + score`；没有目标时明确显示「未检出任何目标」；
- **原始响应 JSON**：AI 接口实际返回的内容（已剥离占体积 94% 的 base64 大图字段，改留 jpg 路径引用）；
- **结果图**：AI 返回的标注图（留存过才有；重新检测会实时拿一张新的）；
- **来源标注**：`已留存（saved/ 直读）` 或 `重新检测（实时调 AI 服务）`。

两种情况：

1. **该帧留存过**（`SAVE_MODE` 触发过，见 §6 配置表）→ 直接读 `saved/<cam>/` 里的json+jpg，秒开；
2. **没留存** → 点「重新检测」按钮：用 `raw/` 环形缓冲里的**原帧**重新调一次 AI 服务
   （约 0.25s，一次真实公网调用）。原帧最多保留近几小时（200MB 环形），被覆盖后会提示取不到。

想让某些帧自动留存（不用每次手点重新检测）：在「留存策略」卡把 **`SAVE_MODE`** 从 `off` 改成：

| 值 | 什么时候存（图 + 响应对，落 `saved/<cam>/`） | 磁盘参考（1 路 1fps 实测） |
|---|---|---|
| `off` | 不存（默认，只写 JSONL） | 0 |
| `alert` | **只存出现「关注目标」的帧**（清单在「关注目标」卡：标签集合 + 分数阈值） | ≈0.3 GB/天量级（命中率 3.4%） |
| `any` | 检出任意目标就存（含误检——会把椅子等认成目标） | ≈7 GB/天量级（检出率 96%，几乎逐帧） |
| `all` | 每帧都存 | 略高于 any |

> **"我只想保存检测到人的图片"怎么设**：到「关注目标」卡把清单填成 `person`（或点「今日检出」里的 person 标签一键加入）→ 留存条件选 `alert` → 点「保存并应用」——之后只有检出人的帧会落 `saved/`。
> 清单为空 = 一张都不保存（alert 模式）。清单和阈值可在网页随时改，改动保存后采集运行中会自动重启生效。

单对（jpg + json）≈ 0.1 MB；日增量 ≈ `0.1 MB × 相机数 × fps × 检出率`。
改完点「保存留存条件」并等采样器重启生效。**`saved/` 会自动清理**（ADR-008）：超过
`SAVED_MAX_MB`（默认 500）或 `SAVED_KEEP_DAYS` 后，从**最旧**的成对文件开始删——
上限 = 时间轴可回看的窗口长度：500MB 在 any 模式 ≈ 最近 1~2 小时、alert 模式 ≈ 1~2 天，
需要更长的窗口就在留存策略卡调大（注意磁盘余量）。

想**清空已有数据重新开始**：在留存策略卡的「**清理数据**」块勾选 `saved/`（图片+响应）、`results/`（检测记录）、`raw/`（原始帧）、`spool/`（积压帧）中要清的类别，点「清空所选数据」。流程为**停采集（仅当运行中）→ 删除所选 → 恢复采集原状态**（采集原本关着不会因此被启动）；`results/` 是权威数据，清掉后「最近检测」和今日统计会归零，且不可恢复。

### 2.6 目标图片时间轴：滑动时间条回看检出图（ADR-008）

页面上部新增「**目标图片时间轴**」卡片（`SAVE_MODE=off` 时为空态并给出开启指引）：

- **数据是什么**：`saved/<cam>/` 里的成对留存图，按**真实时钟**排序——时间是留存时写入的
  `_saved_at`（经 ADR-004 偏移修正），不是文件名里相机时钟的 2024 时间；
- **怎么用**：拖动时间条（**左 = 更早，右 = 更新**）即换图；数据已整包加载，**拖动不发请求**；
  勾选「跟随最新」时新图到达会自动跳到最右，**手动拖动会自动暂停跟随**（避免被拽走）；
- **点图**：直接打开该帧完整响应详情（saved 直读），和「最近检测」点帧是同一个面板；
- **多相机**：多路相机时出现「全部 / front / back」筛选；
- **窗口大小**：= 当前留存集合（受 `SAVED_MAX_MB`/`SAVED_KEEP_DAYS` 约束，见 §2.5）；
  卡片头部显示 `saved/ 共 N 张`，时间条两端显示覆盖区间的起止时间；
- **注意**：时间轴**只读** `saved/`——`raw/` 环形缓冲只有约 3 分钟（200MB@1fps），
  不能作为回看数据源；「最近检测」卡里的「重新检测」按钮才用 `raw/` 原帧。

### 2.7 数据文件只读浏览（ADR-009）

页面「**数据文件（只读浏览）**」卡片可以直接在浏览器里翻这五个数据目录，不必再 SSH：

| 目录 | 里面是什么 |
|---|---|
| `saved/<cam>/` | 标注结果图 `.jpg` + 原始响应 `.json` 成对 |
| `raw/<cam>/` | 原始 JPEG 帧（200MB 环形缓冲） |
| `results/` | `YYYYMMDD.jsonl` 结构化检测记录（权威数据，不自动删） |
| `spool/<cam>/` | 待推理帧 |
| `log/` | 采样器日志 |

**怎么用**

- 点目录名下钻，点「↑ 上一级」返回；名称过滤框可按子串筛选（如输 `jsonl`）；
- 点文件即预览：**图片直接显示**，**文本显示末尾 N 行**（默认 200，可在输入框调 1–5000）；
- 每行右侧「下载」是直链，浏览器另存即可。

**也可以直接调接口**（适合脚本取数）：

```
GET /api/files?dir=saved/front&n=500        # 列目录
GET /api/files?dir=results&match=jsonl      # 名称过滤
GET /api/file?path=saved/front/front_20261016_011342.jpg      # 读图
GET /api/file?path=results/20261016.jsonl&tail=50             # 读 JSONL 末尾 50 行
GET /api/file?path=results/20261016.jsonl&dl=1                # 整个文件另存
```

**边界（重要）**

- **只能进这五个目录**。传入 `src/`、`../m20-ai-detect.env`、`/etc/passwd` 等一律返回 400——
  路径逐段校验 + `realpath` 前缀比对，工程代码与 env 文件读不到；
- 单个文件**超过 32 MB 不支持整读**，会返回 413 并提示改用 `tail=N`；
- 全程只读：没有任何写/删/改接口。

## 3. 日常查看

> 本节命令假设已在工程目录：`cd /home/djw/m20-ai-detect`。

### 2.1 服务状态与日志

```bash
systemctl status m20-ai-detect --no-pager    # 状态 + 最近日志 + 资源占用
journalctl -u m20-ai-detect -f               # 实时跟随日志（Ctrl-C 退出）
journalctl -u m20-ai-detect --since "1 hour ago" --no-pager
```

日志里这几行是正常心跳：`clock offset ... (auto-measured)`（启动测时钟偏移）、`start cap=...`（常驻成功）、`spawn capture cam=front`（抽帧进程拉起）。

### 2.2 看检测结果

```bash
ls -lt results/                             # 数据文件按时间排（文件名是本机日期，见 §4.3）
tail -3 "$(ls -t results/*.jsonl | head -1)"                    # 最新 3 条原文
grep -c '"alert": true' results/*.jsonl                         # 历史告警总数
grep '"alert": true' "$(ls -t results/*.jsonl | head -1)" | tail -3   # 最近 3 条告警
```

### 2.3 看磁盘

```bash
cd /home/djw/m20-ai-detect && PYTHONPATH=src python3 -m m20_ai_detect stats
# 输出各目录占用 + 已有 JSONL 清单；1 fps 全年约 50 MB/路，raw/ 200MB 封顶
```

## 4. JSONL 数据怎么读（v=2 schema）

每帧一行 JSON。**下游分析脚本按 `v` 字段分支解析**（v1 无时钟三字段）。

| 字段 | 含义 |
|---|---|
| `v` | schema 版本，当前 `2` |
| `ts` | **偏移修正后的真实时间**（ISO 8601 毫秒）——分析请用这个 |
| `ts_host` | 本机系统时钟原值（被车队 PTP 钉在 2024，见 ADR-004） |
| `ts_offset_sec` | 本次生效的时钟偏移量（秒）；`ts = ts_host + 偏移` |
| `host` / `cam` / `cap` | 主机名 / 相机名（front）/ 能力 ID |
| `frame` / `frame_sha1` / `frame_bytes` | 帧文件名 / 内容 SHA1 / 字节数 |
| `http` / `elapsed_ms` / `e2e_ms` | HTTP 状态 / 服务端推理耗时 / 端到端耗时（ms） |
| `device` / `provider` / `params` | 推理设备 / 执行提供方 / 生效的推理参数 |
| `n_items` / `items` | 目标数 / 目标列表（`label/class_id/score/box/box_norm`） |
| `alert` | 命中告警规则才有此字段（`true`） |
| `result_image_saved` / `saved_image` / `resp_path` | 仅 `SAVE_MODE` 触发才有：是否存了图 / 图路径（`saved/<cam>/x.jpg`）/ 原始响应 JSON 路径（ADR-006） |
| `event` / `error` | 仅 `detect_fail` 行有：事件名 / 错误摘要 |

读取示例（统计今日告警与标签分布，在工程目录下执行）：

```bash
python3 - <<'EOF'
import json, glob, collections
f = sorted(glob.glob("results/*.jsonl"))[-1]
alerts, labels = 0, collections.Counter()
for line in open(f, encoding="utf-8"):
    r = json.loads(line)
    if r.get("alert"):
        alerts += 1
    for it in r.get("items", []):
        labels[it["label"]] += 1
print(f, "帧数行:", sum(1 for _ in open(f)), "告警:", alerts)
print("标签分布:", dict(labels))
EOF
```

### 4.3 两个坑

1. **文件名是本机日期**：`20240621.jsonl` 是此前系统时钟钉在 2024 时写的；2026-10-16 起时钟已修正，新文件名为真实日期（如 `20261016.jsonl`）。别用 `date +%Y%m%d` 猜历史文件名，用 `ls -t results/*.jsonl | head -1` 取最新；
2. `ts` 与 `ts_host` 的差值 = 该记录写入时的时钟偏移（`ts_offset_sec` 字段）：2024 时段差值约 846 天（ADR-004 软件偏移）；**2026-10-16 起系统时钟已修正，差值 ≈ 0**——两种情况都是正常的，看字段值即可判断。

## 5. 服务管理

**日常一律用 `aiDetect`（终端命令，免密、不用记 systemctl）**：

```bash
aiDetect collect off     # 暂停采集——数据与代码原样保留，随时恢复；机器人动作不受影响
aiDetect collect on      # 恢复采集
aiDetect restart         # 重启控制台
aiDetect collect restart # 重启采样器（ssh 手改 env 后需要；网页改配置则自动重启）
aiDetect reset           # 清空 spool/ 积压帧：停采集仅当运行中，清完恢复原状态（采集关着不会启动）
aiDetect status          # 巡检：服务/采集/自启/版本/积压/磁盘/最近检测
aiDetect log -n 100      # 日志（默认采样器；--console 看控制台）

aiDetect up              # 起控制台（网页入口 5050）
aiDetect down            # 停控制台（网页将不可用，需终端恢复）
aiDetect disable         # 关控制台开机自启；enable 开（默认关闭，见下）
```

所有服务动作与自启开关都经 sudoers 白名单免密执行（`/etc/sudoers.d/m20-ai-console`）；`reset` 与网页「清理数据」勾选 `spool/` 是同一操作语义。

> **启动行为（ADR-010，2026-10-16 起）**：`up/down/restart/enable/disable` **只作用于控制台**；
> **采集（采样器）默认关闭**，由网页「采集开关」或 `aiDetect collect on|off` 控制。
> `--all` 参数已移除（传参会直接报错，不会静默忽略）。
> 机器人重启后：`aiDetect up` 开网页 → 按需 `aiDetect collect on`（或点网页按钮）。
> 控制台开机自启想开回来的话：`aiDetect enable`。

**没有 `aiDetect` 时的原始命令**（等效操作，但每次都要 sudo，日常不建议用）：

```bash
# 控制台：开机自启开关（等价 aiDetect enable / disable；部署默认关闭）
printf "'\n" | sudo -S systemctl enable m20-ai-console
printf "'\n" | sudo -S systemctl disable m20-ai-console

# 采集：运行期启停（等价 aiDetect collect on / off）与改 env 后的重启
printf "'\n" | sudo -S systemctl start m20-ai-detect
printf "'\n" | sudo -S systemctl stop m20-ai-detect
printf "'\n" | sudo -S systemctl restart m20-ai-detect
# ⚠️ 别给 m20-ai-detect 设开机自启——这是设计使然（ADR-010）：
# 机器人重启后无人看管的采集会持续写盘（any 模式 ≈ 7 GB/天）。
```

**改配置的两条路，落的是同一个文件**：`/home/djw/m20-ai-detect/m20-ai-detect.env`（权限 600）。网页上改（§2）会自动写这个文件并重启采样器；ssh 手动编辑则需自己 `systemctl restart`（systemd 不重读 EnvironmentFile），然后 `journalctl -u m20-ai-detect -n 10` 确认新配置生效。改完请把改动回写到仓库模板 `deploy/m20-ai-detect.env.example` 并提交（防主机重建后丢失）。

**卸载**（停用 + 移除 unit；工作空间删不删可选）：

```bash
printf "'\n" | sudo -S systemctl disable --now m20-ai-detect
printf "'\n" | sudo -S rm /etc/systemd/system/m20-ai-detect.service
printf "'\n" | sudo -S systemctl daemon-reload
# 保留数据则不删 /home/djw/m20-ai-detect；确认不要了再删（results/ 是权威数据，删前先归档）
```

## 6. 常用配置调整（命令行改 env 后重启生效；网页保存则自动重启）

| 想做什么 | 改哪个变量 | 示例 |
|---|---|---|
| 抽帧更快/更慢 | `M20AI_FPS` | `2`（每秒 2 帧） |
| 开启后视相机 | `M20AI_ENABLE_B=1`（`M20AI_SRC_B` 已预填 video2） | 前后映射见 `m20Pro_robot_monitor` 取证结论 |
| 换检测能力 | `M20AI_CAP_ID` | 33 项能力之一，ID 见 AI 服务 `/api/v1/health` |
| 关注目标（告警 + 按目标保存图） | `M20AI_ALERT_SCORE` / `M20AI_ALERT_LABELS` | `0.5` / `person,fire,smoke`；网页「关注目标」卡可编辑（含今日检出点选）；`SAVE_MODE=alert` 时命中才存图，见 §2.5 |
| 留存告警结果图 | `M20AI_SAVE_RESULT_IMAGE=true` | 每张 ~120KB，落 `alerts/` |
| 加大环形缓冲 | `M20AI_RING_MAX_MB` | `500` 或 `500M` / `1G`（见下方"单位写法"） |
| 调推理参数 | `M20AI_PARAMS_JSON`（**必须单引号包裹**） | `'{"obj_thresh":0.25}'` |
| 响应留存条件 | `M20AI_SAVE_MODE` | `off`（默认）/ `alert` / `any` / `all`，含义与磁盘参考见 §2.5 |
| saved/ 容量与天数 | `M20AI_SAVED_MAX_MB` / `M20AI_SAVED_KEEP_DAYS` | `500` 或 `1G` / `0` 或 `7d`（0 = 不按该维度清理）；超限从最旧成对删，见 §2.5/§2.6 |
| 手动钉时钟偏移 | `M20AI_TS_OFFSET_SEC` | 默认 `0`=启动自动测量，一般不用动（ADR-004） |

### 6.1 单位写法（ADR-010）：带不带单位都行

| 字段类型 | 涉及字段 | 裸数字默认单位 | 可写写法（不分大小写） |
|---|---|---|---|
| **体积** | `M20AI_RING_MAX_MB`、`M20AI_SAVED_MAX_MB`、journal 的 size / `SystemMaxUse` | **MB**（`200` = 200MB） | `200`、`200M`、`1G`、`512K`（K/M/G/T） |
| **时长** | `M20AI_SAVED_KEEP_DAYS`、`M20AI_RESULTS_KEEP_DAYS`、journal 的 time / `MaxRetentionSec` | **天**（`7` = 7 天） | `7`、`7d`、`24h`、`30m`、`2w`（s/m/h/d/w） |
| **份数** | logrotate `rotate` | 份（整数） | `7` —— **不加单位后缀**，范围 1–365 |

> ⚠️ **为什么必须明确这点**：systemd 自己的规则是——体积必须带后缀、**时长裸数字是「秒」**。
> 所以填 `7` 若直接透给 systemd 会变成 **7 秒**（日志被瞬间清空）。本项目在写入前统一按上表归一化：
> 体积裸数字补 `M`，时长裸数字补 `d`，写进 systemd 的值永远带单位，不会误伤。
>
> 填错单位会明确报错并列出合法写法，例如：
> `M20AI_SAVED_MAX_MB='1x' 的单位 'x' 无法识别。合法单位：k/m/g/t（或裸数字）；裸数字按 MB 解释`

## 7. 自检与排障

**什么时候跑 doctor**：服务异常、AI 服务/相机动过、GOS 重启后，各跑一次。

```bash
cd /home/djw/m20-ai-detect && set -a && . ./m20-ai-detect.env && set +a \
  && PYTHONPATH=src python3 -m m20_ai_detect doctor
```

五项全 PASS 即健康。clock 项显示“慢 73100565.4 s”是**正常的**（偏移量语义，ADR-004）；只有钉值漂移才 WARN。

常见现象速查（死网关/封 DNS、phc2sys 拖时钟、`ts` 是 2024、unit 起不来等）见 **README §7.4 已知坑速查表**；架构决策背景见 ADR-001~004。

## 8. 两种使用方式

1. **自己上手**：浏览器开 http://10.21.31.104:5050（推荐）；或按本文档 ssh 到 104 操作（命令都可直接复制）；
2. **让我代劳**：直接在对话里说“看下最新检测结果 / 停掉服务 / 把 FPS 改成 2”，我来执行并汇报。

## 9. 文档索引

| 文档 | 回答什么 |
|---|---|
| `USAGE.md`（本文件） | 怎么用 |
| `README.md` | 是什么、怎么开发协作、目录/环境/版本/权限六大块 |
| `docs/ADR-001` | 为什么部署在 GOS 104（含 227 降级修订记录） |
| `docs/ADR-002` | 为什么零第三方依赖 |
| `docs/ADR-003` | GOS 出公网路径（死网关/DNS/FORWARD 三修） |
| `docs/ADR-004` | 车队 PTP 钉 2024 与软件时钟偏移 |
| `docs/ADR-005` | 可视化控制台设计（5050/白名单提权/同源配置） |
| `docs/ADR-006` | 响应留存与查看（SAVE_MODE 四值/saved/ 成对留存/重新检测） |
| `docs/ADR-007` | 终端命令 aiDetect（up/down/restart/enable/disable/reset；helper/sudoers 白名单 6→13 条） |
| `docs/ADR-008` | 目标图片时间轴与留存清理（`_saved_at` 真实时间/saved/ 上限与天数/开机自启默认关闭） |
| `docs/ADR-009` | 受限只读文件浏览（`/api/files`+`/api/file`：五目录白名单、两级路径校验、tail 读大文本） |
| `docs/ADR-010` | 配置单位语义与启动行为（裸数字=默认单位：体积 MB／时长天；`up` 只起控制台，采集默认关闭，`--all` 移除） |
| `docs/ADR-011` | 关注目标与数据清空（alert=只存命中关注目标的帧、今日检出标签点选；清理数据 stop→purge→恢复原状态，绝不拉起停着的采集） |
| `docs/ADR-012` | 相机画面预览（raw 最新帧优先 + ffmpeg 即时抓帧兜底；「相机画面」卡 3 秒自动刷新） |
