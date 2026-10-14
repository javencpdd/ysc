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
aiDetect status               # 一屏总览：服务/版本/积压/磁盘/最近检测
aiDetect reset                # 积压太多？清空 spool/ 并以实时为准
aiDetect down                 # 停采样器（机器人动作不受影响）
aiDetect up                   # 再起来
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
| `saved/<cam>/` | 条件留存的**成对证据**：标注结果图 .jpg + 原始响应 .json | 按 `M20AI_SAVE_MODE` 条件写入（默认 off=不存），**无自动清理**，见 §2.5 |
| `alerts/<cam>/` | 旧版告警图目录（已废弃，新逻辑走 `saved/`） | 通常为空 |

## 2. Web 控制台（推荐入口）

浏览器开 **`http://10.21.31.104:5050`**（机器人内网；AOS 没有入站 DNAT，外网访问不到，这是有意的边界）。

### 2.1 页面上有什么

| 区域 | 能做什么 |
|---|---|
| 状态总览 | 采样器/控制台两个服务的运行状态、磁盘占用、今日帧数/告警数、AI 服务健康与时钟偏移 |
| 服务控制 | 启动 / 停止 / 重启采样器（等价于 §5 的 `aiDetect` 命令，不用记 sudo 口令） |
| 最近检测 | **今日真实检测记录**（读 JSONL 尾部）：每帧的时间、检出几个目标、`person 0.81` 这样的标签+分数、或「未检出任何目标」、告警徽标、已留存徽标。**点任一帧看完整响应**（见 §2.5） |
| 检测配置 | 检测能力下拉（AI 服务 33 项能力实时拉取）、抽帧帧率、环形缓冲、AI 服务地址、推理参数（obj/nms 双滑块）——**保存即写 env 并自动重启采样器** |
| 相机与采集 | 前/后视相机开关与流地址（后视 `M20AI_SRC_B` 已预填） |
| 告警规则 | 分数阈值 `M20AI_ALERT_SCORE`、标签集合 `M20AI_ALERT_LABELS` |
| 单帧检测 | 拖一张图进去 → 选能力 → 出检测结果、标注图与**原始响应 JSON**；勾选「保存这一帧」可把图+响应留存到 `saved/console/`。控制台侧能力，与采样器的实时检测互不影响 |
| 运行日志 | `journalctl -u m20-ai-detect` 的网页版：级别过滤（全部/告警/失败/启动/正常）+ 关键字搜索 + 自动刷新 + 按级别着色 |
| 留存策略 | journal 日志清理（vacuum）、journald 上限、ring 上限、results 保留天数（0=永不删）、**响应留存条件 `SAVE_MODE`**、**清空积压帧**（停采集 → 删 `spool/` 陈旧帧 → 重启采集，以实时为主）、logrotate 手动轮转 |

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
aiDetect status                  # 最省事：一眼看到两个服务的状态
aiDetect restart --all           # 重启采样器 + 控制台（改过控制台代码/配置后）
aiDetect down --all / up --all   # 全部停 / 起

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

| 值 | 什么时候存（图 + 响应对，落 `saved/<cam>/`） | 磁盘参考（1fps） |
|---|---|---|
| `off` | 不存（默认，只写 JSONL） | 0 |
| `alert` | 命中告警规则才存 | 通常 KB 级/天 |
| `any` | 检出任意目标就存 | ≈20MB/天 |
| `all` | 每帧都存 | ≈100MB/天 |

改完点「保存留存条件」并等采样器重启生效。`saved/` **不会自动清理**——选什么条件就等于选什么磁盘增速，偶尔用 `stats` 或状态卡看一眼占用。

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

1. **文件名是本机日期**（如 `20240621.jsonl`，因系统时钟在 2024）——别用 `date +%Y%m%d` 猜文件名，用 `ls -t results/*.jsonl | head -1` 取最新；
2. `ts` 与 `ts_host` 差约 846 天是**正常的**（ADR-004 软件偏移），不是数据错误。

## 5. 服务管理

**日常一律用 `aiDetect`（终端命令，免密、不用记 systemctl）**：

```bash
aiDetect down            # 暂停采样——数据与代码原样保留，随时恢复；机器人动作不受影响
aiDetect up              # 恢复
aiDetect restart         # 重启（ssh 手改 env 后需要；网页改配置则自动重启）
aiDetect reset           # 清空 spool/ 积压帧并重启（AI 服务劣化后"以实时为主"，见 §2.5）
aiDetect status          # 巡检：服务/版本/积压/磁盘/最近检测
aiDetect log -n 100      # 日志（默认采样器；--console 看控制台）

aiDetect down --all      # 连控制台服务一起停（网页将不可用，需终端恢复）
aiDetect up --all        # 连控制台一起起
```

所有服务动作都经 sudoers 白名单免密执行（`/etc/sudoers.d/m20-ai-console`）；`reset` 与网页「清空积压帧」是同一操作语义。

**没有 `aiDetect` 时的原始命令**（或想设置"开机不自启"时）：

```bash
# 暂停（开机也不再自启）——数据与代码原样保留，随时恢复
printf "'\n" | sudo -S systemctl stop m20-ai-detect
printf "'\n" | sudo -S systemctl disable m20-ai-detect
# 恢复
printf "'\n" | sudo -S systemctl enable --now m20-ai-detect

# 重启（改了配置后必须做，systemd 不重读 EnvironmentFile）
printf "'\n" | sudo -S systemctl restart m20-ai-detect
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
| 调告警灵敏度 | `M20AI_ALERT_SCORE` / `M20AI_ALERT_LABELS` | `0.5` / `person,fire,smoke` |
| 留存告警结果图 | `M20AI_SAVE_RESULT_IMAGE=true` | 每张 ~120KB，落 `alerts/` |
| 加大环形缓冲 | `M20AI_RING_MAX_MB` | `500` |
| 调推理参数 | `M20AI_PARAMS_JSON`（**必须单引号包裹**） | `'{"obj_thresh":0.25}'` |
| 响应留存条件 | `M20AI_SAVE_MODE` | `off`（默认）/ `alert` / `any` / `all`，含义与磁盘参考见 §2.5 |
| 手动钉时钟偏移 | `M20AI_TS_OFFSET_SEC` | 默认 `0`=启动自动测量，一般不用动（ADR-004） |

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
| `docs/ADR-007` | 终端命令 aiDetect（up/down/reset；helper/sudoers 白名单 6→9 条） |
