# m20-ai-detect — M20 Pro 视频流 AI 识别采样工作空间

把 M20 Pro 机器人（AOS 上的前后广角相机 RTSP 流）抽帧后送给外部 AI 识别服务
（`http://jsxy.aihyzh.com:30881`），结构化结果落 JSONL、原始帧进环形缓冲、命中告警规则留存证据帧。

- **部署位（ADR-001）**：GOS `10.21.31.104`，工作目录 `/home/djw/m20-ai-detect`
- **运行时（ADR-002）**：Python 3.8+ 标准库 + `ffmpeg`，**零第三方依赖**
- **可视化控制台（ADR-005）**：`webconsole/` 独立服务，浏览器 `http://10.21.31.104:5050`（内网）
- **响应留存与查看（ADR-006）**：`M20AI_SAVE_MODE` 四值条件触发，成对留存标注图 + 原始响应到 `saved/`；控制台可回看任一帧的完整响应
- **目标图片时间轴与留存清理（ADR-008）**：留存时写入真实时间 `_saved_at`，控制台"目标图片时间轴"卡片滑动时间条回看检出图；`saved/` 按总量上限/天数自动清理
- **单位语义与启动行为（ADR-010）**：数值字段**带不带单位都行**（体积裸数字=MB、时长裸数字=天，支持 K/M/G/T 与 s/m/h/d/w，非法单位明确报错）；**启动只起控制台**，采集默认关闭由网页「采集开关」或 `aiDetect collect on|off` 控制（`--all` 已移除）
- **关注目标与数据清空（ADR-011）**：网页「关注目标」卡可视化编辑"只保存哪些目标"（`alert` 模式 = 只存命中关注目标的帧，今日检出标签一键点选）；留存卡「清理数据」可一键清空 `saved/`/`results/`/`raw/`/`spool/`（停采集仅当运行中，清完恢复原状态，绝不拉起停着的采集）
- **相机画面（ADR-012）**：控制台「相机画面」卡实时看当前相机——采集运行中显示采样器**当前帧**（即检测器输入本身，零额外开销），未运行则从同一路 RTSP **即时抓帧**兜底；自动刷新 3 秒、页签隐藏自动暂停；**取不到实时帧时红色告警「视频源不可达」**（旧帧置暗 + 按采集状态给出排查指向，不误导为"画面卡住"）
- **界面中英适配（ADR-013）**：控制台顶栏**中文/EN 一键切换**（localStorage 记忆，默认中文）——静态界面 + JS 拼装文案 + 接口返回的 detail/notes/错误全部随语言切换，单测保证双语词典键集合一致、无漏译
- **留存卡按钮语义澄清（ADR-014）**：留存策略卡原有两个都叫「保存…（重启后生效）」的按钮（容量/时长 vs 留存条件）易被按错；已拆成 ①留存条件 / ②容量与时长 两节并各自紧贴自己的保存按钮，按钮文案点明维度、说明 note 写清"只管哪一段、与什么无关"，并有单测固化两按钮文案不可混淆
- **指标卡口径统一 + journal 归位（ADR-013 延伸，v0.8.2 / v0.8.6）**：顶栏第五项由「journal 占用」改为「**检测数据**」——显示 `raw+results+saved+spool` 合计与四项明细，与留存卡「清理数据」的占用**逐项对得上**（此前 journal 的 200 MB 与下方 KB 级数字并列，易被误读成"同一本账"）。整机 journal 大小移到「日志与数据留存策略」卡的 **journal 区**（它本来就在那里被 vacuum / `SystemMaxUse` 管理），并给出构成：`当前整机 journal ≈ 200.0 MB（含所有 systemd 单元；本服务 m20-ai-detect 仅 385 行 ≈ 26 KB，大头是厂商 rsdriver 等系统服务）`。⚠️ 两个事实：`journalctl --disk-usage` **会忽略 `-u` 等过滤器**（返回值必为整机合计），"本服务占多少"只能用 `journalctl -u X -o cat` 的文本量估算（`sysactions.journal_service_usage()`）
- **卡片折叠（ADR-015）**：每张卡片标题右侧一个 ▾ 按钮可折叠/展开，**顶栏「全部折叠 / 全部展开」**一键切换；折叠态**只剩「标题 + 状态徽标」一行**（说明文字、工具条按钮组、图片、状态行全部隐藏——用 `!important` 压过图片的 JS 行内 `style.display`，见 ADR-015 修订记录）；折叠状态按 `localStorage`（键 `m20ai-fold-<卡片键>`，**与语言无关**）记忆，刷新/换语言后保持；**折叠时自动暂停该卡片的后台轮询**（相机画面 3s / 运行日志 4s / 时间轴 15s / 最近检测 5s），展开即恢复——不再为一个看不见的卡片持续拉流
- **受限只读文件浏览（ADR-009）**：`/api/files` + `/api/file` 可在浏览器里浏览/预览/下载 `saved/`、`raw/`、`results/`、`spool/`、`log/` 五个数据目录；白名单 + 两级路径校验，大文本走 `tail` 读末尾
- **使用手册**：`USAGE.md`（日常查看/服务管理/配置调整/JSONL 读取，面向使用者）
- **上位方案文档**：`辅助工具/M20视频流AI检测-接入测试与实施方案.md`（架构/实测基线/验证步骤）

```
AOS 196 (相机)                GOS 104 (本工程)                     公网
/dev/video0 ─┐                                                    ┌─────────────────────┐
             ├─ MediaMTX 8554 ──RTSP──> ffmpeg 抽帧 ──> spool/ ──> │ jsxy.aihyzh.com      │
/dev/video2 ─┘  10.21.31.103         (1 fps, 常驻)    采样器消费    │ :30881  FastAPI      │
                                                          │        │ 33 项视觉能力        │
                                                          v        └─────────────────────┐
                                              results/*.jsonl (权威数据, 永不删)          │
                                              raw/<cam>/*.jpg   (环形缓冲, 200MB 上限)    │
                                              saved/<cam>/*     (条件留存: 图+响应, ADR-006)
```

---

## 1. 目录结构设计

```
m20-ai-detect/
├── USAGE.md                       # 使用手册：日常查看/服务管理/配置调整/JSONL 读取
├── pyproject.toml                 # 包元数据；dependencies = [] 刻意留空（见 ADR-002）
├── Makefile                       # 16 个常用目标：make help
├── .env.example                   # 开发机配置模板（三套部署位切换注释）
├── .gitignore                     # 忽略运行数据：spool/ raw/ results/ alerts/ saved/ log/ tmp/ .runtime/
├── .gitattributes                 # 全部文本固化 eol=lf（Windows 开发 → Linux 部署）
│
├── src/m20_ai_detect/             # 【唯一源码目录】src 布局，防止误 import 本地副本
│   ├── __init__.py                #   __version__，单处维护
│   ├── __main__.py                #   python3 -m m20_ai_detect 入口
│   ├── config.py                  #   M20AI_* 环境变量 → Config dataclass + validate()
│   ├── capture.py                 #   ffmpeg 常驻抽帧进程管理（按协议自动补 -rtsp_transport/-f flv）
│   ├── detect.py                  #   手工 multipart 编码 + HTTP 调用 + 结果图 base64 解码 + 剥离大图字段
│   ├── store.py                   #   七个数据目录 + JSONL 追加 + 环形缓冲 + 统计 + results 保留清理 + save_pair 留存
│   ├── snapshot.py                #   相机画面单帧快照（raw 最新帧优先 / ffmpeg 即时抓帧兜底，ADR-012）
│   ├── sampler.py                 #   主循环：spool → 推理 → 落库 → raw/；退避重试；每小时清理旧 results
│   └── cli.py                     #   run / doctor / stats / paths 四个子命令
│
├── webconsole/                    # 可视化控制台（独立服务，见 ADR-005）
│   ├── __init__.py                #   __version__ = 0.7.0（与 sampler 同号）
│   ├── __main__.py                #   python3 -m webconsole 入口（systemd ExecStart 调它）
│   ├── envfile.py                 #   env 文件读取/就地改写/整份校验（纯逻辑）
│   ├── i18n.py                    #   中英文案目录（X-Lang 请求头驱动，ADR-013）
│   ├── sysactions.py              #   systemctl/journalctl/helper 动作封装 + 值格式预校验
│   ├── logfilter.py               #   journal 行解析/级别分类/过滤（纯逻辑）
│   ├── server.py                  #   HTTP 壳：JSON API + 静态页 + 单帧检测 + 最近记录/响应详情 + 相机画面快照
│   └── static/index.html          #   单页前端（原生 JS，亮/暗双主题，token 可选）
│
├── tests/                         # unittest（非 pytest），249 项，含本地假 AI 服务端到端
│   ├── test_config.py             #   默认值/校验/禁用关键词/凭据打码/时钟偏移/保留天数/SAVE_MODE
│   ├── test_detect.py             #   multipart 结构/HTTP 错误/网络错误/Date 头/时钟测量
│   ├── test_store.py              #   JSONL/环形删最旧/告警帧/results 保留清理/save_pair 留存
│   ├── test_sampler.py            #   FakeDetector 驱动，失败保留帧/时钟校准/清理钩子/SAVE_MODE 触发矩阵
│   ├── test_cli.py                #   doctor 门禁（storage/时钟三态）
│   ├── test_integration.py        #   ThreadingHTTPServer 假 AI 服务，真 HTTP 全链路
│   ├── test_snapshot.py           #   相机画面：单帧抓拍命令/来源优先级/缓存/失败兜底（ADR-012）
│   └── test_webconsole.py         #   envfile/logfilter/sysactions 单测 + 控制台 HTTP 端到端 + 响应查看/单帧留存/时间轴/只读文件浏览/相机画面
│
├── deploy/
│   ├── m20-ai-detect.service      #   systemd unit（User=user / CPUAffinity=0-3 / MemoryMax=1G）
│   ├── m20-ai-detect.env.example  #   GOS 生产配置模板（可入库，不含密钥）
│   ├── bootstrap.sh               #   【104 上执行】首次部署：依赖检查/目录/unit/logrotate/doctor
│   ├── install.sh                 #   【开发机执行】测试→备份→同步→自检→重启→回滚指引
│   ├── m20-ai-console.service     #   控制台 unit（User=user / 0-3 小核 / MemoryMax=256M）
│   ├── m20-ai-console.env.example #   控制台自身配置（绑定/端口/token，可入库）
│   ├── m20-ai-console-helper      #   root 提权 helper（sudoers 白名单精确调用，参数二次校验）
│   ├── m20-ai-console.sudoers     #   sudoers 白名单（13 条精确命令，无通配符）
│   ├── aiDetect                   #   【104 上执行】终端运维命令（up/down/restart/enable/disable/reset/status/log，ADR-007）
│   └── console-bootstrap.sh       #   【104 上执行】控制台首次部署：env/helper/sudoers/aiDetect/unit/冒烟/启动
│
└── docs/
    ├── adr-template.md            #   架构决策记录模板
    ├── ADR-001-部署位选择.md       #   为什么是 GOS 104 而不是 196/106/227
    ├── ADR-002-运行时与依赖策略.md #   为什么零第三方依赖
    ├── ADR-003-GOS出公网路径.md    #   死网关/DNS/时钟三连修（2026-10-15 门禁发现）
    ├── ADR-004-车队PTP时间基准与软件时钟偏移.md # 为什么不动系统时钟、JSONL 时间戳怎么修正
    ├── ADR-005-可视化控制台.md     #   独立服务/零依赖/白名单提权/5050 安全边界
    ├── ADR-006-响应留存与查看.md   #   SAVE_MODE 四值条件/saved/ 成对留存/响应查看器
    ├── ADR-007-终端运维命令aiDetect.md # up/down/restart/enable/disable/reset；helper/sudoers 白名单 6→13 条
    ├── ADR-008-目标图片时间轴与留存清理.md # _saved_at 真实时间/saved/ 上限与天数清理/开机自启默认关闭
    ├── ADR-009-受限只读文件浏览.md   #   /api/files + /api/file：五目录白名单、两级路径校验、tail 读大文本
    ├── ADR-010-配置单位语义与启动行为.md # 裸数字=默认单位（体积MB/时长天）、up只起控制台、采集默认关闭
    ├── ADR-011-关注目标与数据清空.md # 关注目标=告警+alert 留存过滤（网页可编辑）；purge 清空 saved/results/raw/spool
    ├── ADR-012-相机画面预览.md      #   单帧快照：raw 最新帧优先 / ffmpeg 即时抓帧兜底；「相机画面」卡自动刷新
    ├── ADR-013-控制台界面中英适配.md #   X-Lang 请求头 + 前端 i18n JSON（217 键）；顶栏中文/EN 切换；词典一致性单测
    ├── ADR-014-留存卡按钮语义澄清.md #   ①留存条件 / ②容量与时长 分节；按钮文案点明维度；不可混淆单测
    └── ADR-015-卡片折叠.md          #   每卡 ▾ 折叠 + 顶栏全部折叠/展开；状态记 localStorage；折叠暂停轮询
```

### 运行时数据目录（部署后由 `Store` 自动创建，已 gitignore）

| 目录 | 内容 | 清理策略 |
|---|---|---|
| `spool/<cam>/` | ffmpeg 写出的待推理 JPEG 帧 | 推理成功后移走，天然自清 |
| `results/` | `YYYYMMDD.jsonl`，**权威数据**（~600 B/帧） | **永不删除**，按需归档 |
| `raw/<cam>/` | 已推理原始帧（复核/复绘证据，~40–80 KB/帧） | 环形缓冲，超 `M20AI_RING_MAX_MB`（默认 200 MB）删最旧 |
| `saved/<cam>/` | 条件留存的**成对证据**：`<帧名>.jpg`（AI 标注结果图 ~120 KB）+ 同名 `.json`（原始响应，已剥离 base64 大图，~2 KB） | 按 `M20AI_SAVE_MODE` 条件写入，**无自动清理**（量由条件控制）；控制台「响应详情」直读 |
| `alerts/<cam>/` | 旧版告警图目录（`SAVE_RESULT_IMAGE` 时代），新逻辑统一走 `saved/` | 手动清理；通常为空 |
| `log/` | 文件日志（stdout 同时进 journal） | logrotate 保留 7 天 |
| `tmp/` | doctor 探针、console-*.req 等临时文件 | 手动清理 |

---

## 2. 环境与依赖配置

### 2.1 目标机（GOS 104）要求

| 组件 | 版本 | 安装 |
|---|---|---|
| Python | ≥ 3.6（实测 3.8） | Ubuntu 20.04 自带 `python3`，**无需 venv/pip** |
| ffmpeg | 任意较新版本 | `apt install ffmpeg`（bootstrap.sh 自动装） |
| 系统 | systemd + logrotate | Ubuntu 20.04 自带 |

**刻意不装**：requests / pytest / pydantic / psutil——理由与代价见 `docs/ADR-002`。

### 2.2 开发机（Windows / Git Bash）要求

- Python 3.8+（本机 3.13/3.14 均可，代码不用 3.9+ 语法）
- `make` + `rsync` + `ssh`（Git Bash 自带或 MSYS2 补充）
- `~/.ssh/config` 有 `m20pro-GOS.104` 别名且**公钥已投递**（见 §7.1）

### 2.3 配置注入：全部走 `M20AI_*` 环境变量

三层配置，优先级从低到高：

1. **代码默认值**（`config.py` dataclass field）——只放"换任何机器都不变"的值；
2. **`m20-ai-detect.env`**（由 `deploy/m20-ai-detect.env.example` 复制，**不入库**）——systemd 经 `EnvironmentFile=` 加载，本机私密；
3. **shell 环境变量**——临时调试覆盖，如 `M20AI_FPS=0.2 make run`。

常用变量（完整列表见 `deploy/m20-ai-detect.env.example` 注释）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `M20AI_BASE_DIR` | `/home/djw/m20-ai-detect` | **改它必须同步改 unit 的 `ReadWritePaths`** |
| `M20AI_AI_BASE` | `http://jsxy.aihyzh.com:30881` | AI 服务地址；含 `@` 时日志自动打码 |
| `M20AI_CAP_ID` | `ai-04-yolov8-object-detection` | 33 项能力之一 |
| `M20AI_ENABLE_F/_B`、`M20AI_SRC_F/_B` | 前视开/后视关 | **换部署位只改这里**，不动代码 |
| `M20AI_FPS` | `1` | 每秒抽帧数；2 Mbps 流下 1 fps 足够 |
| `M20AI_RING_MAX_MB` | `200` | raw/ 环形缓冲上限（**默认单位 MB**，≥10；可写 `200M`/`1G`） |
| `M20AI_SAVE_MODE` | `off` | 响应留存条件（ADR-006）：`off`=只写 JSONL；`alert`=只存出现「关注目标」的帧（见下行，ADR-011）；`any`=检出任意目标；`all`=每帧。触发时成对落 `saved/<cam>/`（标注图 + 原始响应），JSONL 记 `saved_image`/`resp_path` |
| `M20AI_SAVE_RESULT_IMAGE` | `false` | **旧开关**：`true` 等价于 `SAVE_MODE=alert`（显式设了 SAVE_MODE 则以它为准） |
| `M20AI_SAVED_MAX_MB` / `M20AI_SAVED_KEEP_DAYS` | `500` / `0` | saved/ 留存清理（ADR-008）：总量上限（**默认单位 MB**）/ 保留时长（**默认单位天**）；`0` = 不按该维度清理，采样器每 10 分钟检查一次，从最旧的成对文件开始删。**带单位写法见 ADR-010**（`1G` / `7d` / `24h` 均可） |
| `M20AI_ALERT_LABELS` / `M20AI_ALERT_SCORE` | `person,fire,smoke` / `0.60` | **关注目标**（ADR-011）：命中任一标签（且分数达标）的帧 ① JSONL 写 `alert:true` 计入告警；② `SAVE_MODE=alert` 时保存图片。网页「关注目标」卡可直接编辑（含今日检出标签点选）；清单为空 = alert 模式不保存任何图片 |
| `M20AI_TS_OFFSET_SEC` | `0`（= 启动时自动测量） | 车队 PTP 把系统时钟钉在 2024，偏移量修正 JSONL 时间戳；非 0 = 手动钉值，见 ADR-004 |

**配置自检**：`Config.validate()` 在启动时拦截非法值（FPS 越界、JPEG_Q 越界、相机名重复、源地址含 `push_video`/`v4l2`/`gst-launch` 关键词——后者会被机器人侧 `restart.sh` 的 `pkill` 误杀，见 MEMORY.md 命名禁忌）。

---

## 3. 版本管理

### 3.1 单仓库单版本号

- 版本号唯一来源：`src/m20_ai_detect/__init__.py` 的 `__version__`（当前 `0.8.6`；`webconsole/__init__.py` 同步同号）。
- `pyproject.toml` 不重复写版本；`python3 -m m20_ai_detect --version` 可直接核对远端部署的是哪一版。
- 版本语义：`0.x` 期表示接口（JSONL 字段、CLI 子命令）仍可能调；`1.0` 锁定 JSONL `v` 字段 schema。

### 3.2 Git 工作流（轻量，适配个人/小团队）

```
main（稳定，随时可部署）
 └── dev（日常开发；make deploy 默认从这走）
```

- **提交粒度**：一个可回滚单元一次提交；`install.sh` 的回滚依赖"某一提交 = 某一可运行状态"。
- **提交信息**：`类型: 摘要`，类型取 `feat/fix/refactor/test/docs/deploy/chore`。
- **`docs/ADR-*` 是契约**：改部署位、改依赖策略、改 JSONL schema，必须先写/改 ADR 再改码——ADR 记录"为什么"，代码记录"是什么"。
- **禁止入库**：`m20-ai-detect.env`、任何含口令/Token 的文件、`spool/raw/results/alerts` 运行数据。`.gitignore` 已覆盖，新增敏感文件请同时更新它。
- **行尾**：`.gitattributes` 固化 LF；Windows 检出若变 CRLF，脚本上主机会报 `bad interpreter`——`install.sh` 第 1 步有 `file` 检查兜底。

### 3.3 远端与本地的对应关系

远端 `~/.backup/` 由 `install.sh` 每次部署前自动打 tar（代码 + env），本地 Git 管历史，**两层互补**：Git 管"哪个版本"，`.backup` 管"部署前一刻的现场"。

---

## 4. 构建与运行方式

### 4.1 "构建" = 不存在

无编译、无打包、无 venv。`make deploy`（内部调 `deploy/install.sh`）即全部"构建"：

```bash
# 开发机（Windows Git Bash / WSL / Linux）
make test                     # 41 项测试，部署前必过
make deploy                   # 测试→远端备份→rsync→远端 import 自检→重启
make deploy-doctor            # 只在远端跑 doctor，不动代码
make logs                     # 远端 journalctl -u m20-ai-detect -n 80
make stop                     # 停远端服务（不影响机器人推流）
```

换主机：`HOST=m20pro-NOS.106 make deploy`（NOS 上同样可达相机流；配合改 env 里的 `M20AI_SRC_*` 即可，代码零改动）。

### 4.2 首次部署（104 上一鱼次）

```bash
# ① 开发机：只同步代码，不重启（此时 unit 还没装）
NO_RESTART=1 make deploy

# ② 登 104：初始化 + 门禁 + 启动
ssh m20pro-GOS.104
cd ~/m20-ai-detect
bash deploy/bootstrap.sh          # 装依赖/建目录/装 unit/logrotate/跑 doctor
sudo systemctl start m20-ai-detect
journalctl -u m20-ai-detect -f     # 看到 "start cap=..." 即常驻成功
```

### 4.3 日常调试（前台跑，不经 systemd）

```bash
# 开发机本地：用假源跑不起来没关系，主要看 paths/stats
make run        # 前台运行；Ctrl-C 停
make paths      # 打印六个数据目录实际位置
make stats      # 各目录占用 + 已有 JSONL 清单

# 104 上手动前台（临时改配置调试，勿与 systemd 同时跑）
ssh m20pro-GOS.104 "cd ~/m20-ai-detect && set -a && . ./m20-ai-detect.env && set +a && \
  PYTHONPATH=src python3 -m m20_ai_detect run"
```

### 4.4 上线门禁：`doctor`（对应方案 V0″）

启动前一次性验完六项，任一 FAIL 退出码非 0，**bootstrap.sh 会拦着不启动服务**：

| 检查项 | 验什么 | 不过的典型原因 |
|---|---|---|
| `ffmpeg` | 可执行且能出版本号 | 没装 / `M20AI_FFMPEG_BIN` 指错 |
| `ai_health` | AI 服务 `/api/v1/health` 200 且能力就绪 | **GOS 无公网出口**：默认网关 10.21.31.99 已 ARP 死，需经 AOS 中转（见 ADR-003）；或 DNS 上行 8.8.8.8 被上游封 |
| `clock` | 偏移量语义（ADR-004）：未配置 `M20AI_TS_OFFSET_SEC` → PASS 并打印实测偏移；已配置 → 实测与配置偏差 >2 s 判 WARN | 系统时钟被车队 PTP 钉在 2024 **不是故障**；只有"钉值漂移"才告警 |
| `source:<cam>` | 每路源真抽一帧 + 量冷启动耗时 | AOS MediaMTX 没起 / 内网不通 |
| `storage` | BASE_DIR 可写 + 磁盘余量 | 家目录不存在 / eMMC 将满 |

```bash
make doctor                      # 本地（开发机无相机源会 FAIL source 项，属预期）
make deploy-doctor               # 远端真实环境跑，这才是门禁
```

---

### 4.5 可视化控制台（ADR-005）

浏览器打开 **`http://10.21.31.104:5050`**（GOS 内网），零依赖单页：状态总览、服务启停、**中英切换（顶栏 中文/EN，ADR-013）**、**相机画面（采集运行中=采样器当前帧、未运行=即时抓帧，ADR-012）**、**目标图片时间轴（滑动时间条回看检出图，ADR-008）**、**数据文件只读浏览（五个数据目录，ADR-009）**、日志查看（级别过滤/搜索/自动刷新/着色）、检测能力与参数编辑（保存即写 env；采集运行中自动重启生效，停着的不拉起）、单帧检测（上传图→AI→结果图）、相机/采集配置、**关注目标（告警 + alert 留存过滤，今日检出标签一键点选，ADR-011）**、留存策略（两区：①留存条件 `SAVE_MODE`／②容量与时长 ring·results·saved 上限与天数，各配自己的保存按钮，ADR-014；另有 journal 清理/logrotate）、**数据清理（勾选清空 saved/results/raw/spool；停采集仅当运行中、清完恢复原状态，ADR-011）**。

**只读文件浏览（ADR-009）**：控制台"数据文件（只读浏览）"卡片可逐级点开 `saved/`、`raw/`、`results/`、`spool/`、`log/`，点文件即预览（图片直接显示，文本读末尾 N 行），并提供下载直链。也可直接调接口：

```
GET /api/files?dir=&n=&match=          # 列目录（dir 空=根，只列白名单根）
GET /api/file?path=&tail=&dl=1         # 读单文件（tail=末尾行数，dl=1 触发下载）
```

安全边界：白名单根 `FILE_ROOTS = ("saved","raw","results","spool","log")`，路径逐段校验（禁 `..`、禁绝对路径、首段必须在白名单内）+ `realpath` 前缀比对（防符号链接越界）；整读上限 32 MB，超过必须改用 `tail`。工程代码与 env 一律不可达（已由单测固化）。

**相机画面（ADR-012）**：控制台"相机画面"卡显示当前相机一帧并每 3 秒自动刷新（页签隐藏自动暂停）。接口 `GET /api/snapshot?cam=front`（返回 base64 JPEG + 来源标注）：采集运行中直接取 `raw/` 最新帧——**就是检测器刚处理过的画面**、零额外开销；采集未运行则用 `ffmpeg` 从同一路 RTSP 即时抓帧（成功 1.5 s / 失败 3 s 短缓存防连击、8 s 超时、抓完即退）；**抓帧也失败时兜底显示环形缓冲最近一帧，但明确标红「⚠ 视频源不可达」**（旧帧置暗 40%、列出 RTSP 源与帧龄、按采集开关状态给出排查指向，2026-10-17 修订——起因见 ADR-012 修订记录：USB 相机掉线后"定格旧帧"曾被误当"画面卡住"）。

**UI 与 CLI 同源**：页面所有读写最终都落在同一份 `m20-ai-detect.env` 上，控制台服务 `m20-ai-console`（`webconsole/`，User=user、CPUAffinity=0-3、MemoryMax=256M）只做壳，不另存配置。

```bash
make deploy-console              # 一键部署（install.sh → console-bootstrap.sh）
```

`console-bootstrap.sh` 依次做：生成 `m20-ai-console.env`（600）→ 装 root helper `/usr/local/sbin/m20-ai-console-helper` + sudoers 白名单（`visudo -c` 校验）→ 装 `aiDetect` 终端命令 → 装 unit（**不再自动 enable**，开机自启默认关闭）→ 前台冒烟（curl `/api/status` + 首页）→ 启动并断言 `is-active`。

| 项 | 值 |
|---|---|
| 端口 | 默认 5050，`M20AIC_PORT` 可改（env.example 已注释） |
| 绑定 | `0.0.0.0`=机器人内网可达；AOS 无入站 DNAT，**外网到不了**；要更严可改 `M20AIC_BIND=127.0.0.1` |
| 鉴权 | 默认开放（无 TOKEN）；设了 `M20AIC_TOKEN` 后页面右上角填同一个值，API 需 `X-Console-Token` 头 |
| 提权模型 | **读**（is-active/journalctl）不提权——`user` 在 `adm` 组；**写**（启停/自启开关/vacuum/改配置）走 sudoers 精确白名单（13 条完整命令行、无通配符）调 helper，helper 内二次校验参数 |
| 单帧检测 | 控制台侧能力（`POST /api/detect`）：换 `cap_id` 调 AI 服务、默认带回 base64 结果图；与采样器的实时检测**互不影响**（不同进程） |
| 日志 | `journalctl -u m20-ai-console -f`；unit **刻意不加** `NoNewPrivileges` 等硬化（见 §5.2 末行），否则 sudo 调 helper 直接失效 |

设计权衡、白名单清单、为何不用 Flask/Node 见 **`docs/ADR-005-可视化控制台.md`**；面向使用者的操作手册见 **`USAGE.md`**。

### 4.6 终端命令 `aiDetect`（ADR-007）

浏览器不在手边时，主机上的 `aiDetect` 覆盖全部日常运维（随 `console-bootstrap.sh` 装入到 `/usr/local/bin/aiDetect`，另有小写别名 `aidetect`）：

| 命令 | 作用 |
|---|---|
| `aiDetect up` / `down` / `restart` | 启动 / 停止 / 重启**控制台**（网页入口 5050） |
| `aiDetect collect on\|off\|status\|restart` | **采集开关**：采样器启停（**默认关闭**，ADR-010） |
| `aiDetect enable` / `disable` | **控制台**开机自启开关（部署默认关闭；采集不设自启） |
| `aiDetect reset` | 清空积压帧（spool/）：停采集（仅当运行中）→ 清 → 恢复原状态；采集原本关着不会被拉起（= 网页「清理数据」勾 spool 同款语义） |
| `aiDetect status` | 服务/采集/自启/版本/积压/磁盘/最近检测一屏总览 |
| `aiDetect log [-n N] [-f] [-g 词] [--console]` | 看日志（默认采样器；`-f` 跟踪、`-g` 过滤） |
| `aiDetect doctor` | 上线门禁检查（等价 `make deploy-doctor`） |

> **启动行为（ADR-010）**：`up/down/restart/enable/disable` 只作用于控制台；采集另由 `collect` 或网页「采集开关」控制，默认关闭。旧的 `--all` 参数已移除（传参会直接报错，不会静默忽略）。

提权模型不变：服务动作经 sudoers 白名单调 helper（NOPASSWD、精确命令行，无任何自由参数）；删 `spool/` 帧不提权（文件归 `user`）。脚本本体 `deploy/aiDetect` 为纯 bash 单文件、零依赖；`install.sh` 本地门禁已加入 `bash -n` 语法检查与 LF 行尾检查。

---

## 5. 权限管理

### 5.1 主机侧（GOS 104）

| 对象 | 属主 | 权限 | 理由 |
|---|---|---|---|
| `~/m20-ai-detect/` | `user:user` | `750` | 家目录私有，禁止他人读检测数据 |
| `m20-ai-detect.env` | `user:user` | `600` | 未来可能带 AI 服务凭据 |
| `m20-ai-console.env` | `user:user` | `600` | 同上（TOKEN 类敏感值） |
| `spool/raw/results/alerts/log/tmp/` | `user:user` | 默认 `755`（umask 022） | 服务以 `user` 跑，无需放宽 |
| `/etc/systemd/system/m20-ai-detect.service` | `root:root` | `644` | 只有装 unit 需要 sudo |
| `/etc/systemd/system/m20-ai-console.service` | `root:root` | `644` | 同上 |
| `/usr/local/sbin/m20-ai-console-helper` | `root:root` | `750` | **运行期唯一的 root 入口**，`user` 不可读不可改 |
| `/etc/sudoers.d/m20-ai-console` | `root:root` | `440` | 白名单：`user` 仅能以完整固定命令行调 helper 的 13 个子命令 |

**全程只用到 sudo 的时机**：bootstrap.sh 装 unit + logrotate；console-bootstrap.sh 装 helper + sudoers + aiDetect + unit。运行期零裸 sudo——检测服务不碰任何系统路径；控制台与 `aiDetect` 的写操作只能经白名单 helper（svc-start/stop/restart/enable/disable、console-start/stop/restart/enable/disable、journal-vacuum、journald-limits、logrotate-rotate），参数经 `tmp/console-<sub>.req` 文件传递并由 helper 二次校验，每次调用 `logger` 留痕可审计。

### 5.2 systemd 沙箱（unit 内已固化）

| 指令 | 作用 |
|---|---|
| `User=user` + `ProtectHome=read-only` + `ReadWritePaths=/home/djw/m20-ai-detect` | 全盘只读，仅工作空间可写 |
| `NoNewPrivileges=true` | 禁 setuid 提权 |
| `ProtectKernelTunables/Modules/ControlGroups=true` | 禁改内核参数/加载模块 |
| `RestrictSUIDSGID` + `RestrictRealtime` + `LockPersonality` | 禁 SUID、禁实时调度、禁人格伪装 |
| `CPUAffinity=0-3` | GOS 的 4 个 A76 大核被 `isolcpus` 隔离给厂商任务，本服务显式只用 4 个 A55 小核，不与实时任务争抢 |
| `MemoryMax=1G` + `Nice=5` | 采样器本身很轻（ffmpeg 抽帧 + 每帧一次 HTTP），1 G 富余 |
| `Restart=always` + `RestartSec=5` | 崩溃自愈；但**不依赖机器人任何服务**，AOS 挂了只是没帧 |

**控制台 unit 的刻意差异**：`m20-ai-console.service` 只保留 `User=user` + `CPUAffinity=0-3` + `MemoryMax=256M` + `ReadWritePaths`，**不设** `NoNewPrivileges/ProtectSystem/ProtectHome` 等硬化——因为它必须经 `sudo` 调 root helper 才能做写操作，`NoNewPrivileges=true` 会直接禁掉 sudo 的 setuid，写功能全灭。补偿手段是 sudoers 白名单收窄到 13 条完整命令行（§5.1），以"最小提权面"换"功能可用"。

### 5.3 SSH 访问链

```
开发机 --(公钥, 22)--> GOS 104
开发机 --(公钥, 22)--> AOS 196 --(内网)--> NOS/GOS   # 兜底路径
```

- 公钥投递是**唯一需要人工口令的步骤**（PC 公钥目前只写进了 AOS 的 `authorized_keys`）：
  ```bash
  cat ~/.ssh/id_rsa.pub | ssh m20pro-GOS.104 \
    "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
  # NOS 同（如未来要部署到 106）
  ```
- 投递前可用 `m20Pro/scripts/m20ssh`（AOS 上的 sshpass 跳板）过渡，但不进自动化流程——口令不该出现在脚本里。

---

## 6. 数据与可靠性设计（运行方式的行为面）

- **权威数据是 JSONL**：每帧一行，schema `v=2`，含 `ts/ts_host/ts_offset_sec/host/cam/cap/frame/frame_sha1/http/elapsed_ms/e2e_ms/n_items/items/alert`（`ts` 为偏移修正后的真实时间，`ts_host` 为本机原值，见 ADR-004）；条件留存时另有 `result_image_saved/saved_image/resp_path`（ADR-006）。600 B/帧，1 fps ≈ 50 MB/年/路，**永不删**。
- **原始帧是环形缓冲**：`raw/` 超 200 MB 删最旧（mtime 排序）。
- **响应留存（ADR-006）**：`M20AI_SAVE_MODE=off|alert|any|all` 控制"什么时候值得留证据"——触发时把 AI 标注结果图（~120 KB）与原始响应（剥掉占体积 94% 的 base64 大图、改留 jpg 路径引用，~2 KB）成对写 `saved/<cam>/`，JSONL 同步记 `saved_image`/`resp_path`。默认 `off`，行为与 0.3.x 完全一致。控制台「最近检测」点任一帧可看完整响应：已留存直读 `saved/`，未留存可用 `raw/` 原帧**重新检测**（一次真实 API 调用）。
- **留存清理与时间轴（ADR-008）**：留存 JSON 写入时带 `_saved_at`（真实时钟，ADR-004 修正）与 `_alert`，控制台"目标图片时间轴"卡片据此**滑动时间条回看检出图**；`saved/` 按 `M20AI_SAVED_MAX_MB`（默认 500）/`M20AI_SAVED_KEEP_DAYS`（默认 0）从最旧成对清理（采样器每 10 分钟检查）。磁盘参考（2026-10-16 实测：单对 ≈0.1 MB、检出率 96.2%）：`any` ≈ 7 GB/天（500 MB ≈ 最近 1~2 小时）、`alert` ≈ 0.3 GB/天（500 MB ≈ 1~2 天）——上限、磁盘占用、可回看时长三者联动。
- **留存过滤与数据清空（ADR-011）**：`SAVE_MODE=alert` 的"过滤清单"就是**关注目标**（`M20AI_ALERT_LABELS`/`M20AI_ALERT_SCORE`）——想"只保存检测到人的图片"，在网页「关注目标」卡设置（含今日检出标签一键点选）即可，保存后采集运行中会自动重启生效。网页「清理数据」块或 `POST /api/retention {"purge":[...]}` 可整体清空 `saved/`（图片+响应）/`results/`（仅 `*.jsonl`）/`raw/`/`spool/`：停采集**仅当运行中**、清完恢复原状态，**不会拉起停着的采集**（ADR-010）；`results/` 属权威数据，手动清空不可恢复。
- **相机画面（ADR-012）**：控制台「相机画面」卡看当前相机——采集运行中 = `raw/` 最新一页（检测器输入本身，不额外拉流）；未运行 = `ffmpeg` 单次抓帧（同一路 RTSP，1.5 s 短缓存 / 8 s 超时）；再失败兜底显示最近一帧并标"已定格"。`GET /api/snapshot?cam=front`。
- **留存卡按钮语义澄清（ADR-014）**：留存策略卡拆为 ①留存条件（`SAVE_MODE`，只管 `saved/` 准入）与 ②容量与时长（`RING_MAX_MB`/`RESULTS_KEEP_DAYS`/`SAVED_MAX_MB`/`SAVED_KEEP_DAYS`）两节，各自按钮紧贴参数；按钮文案点明维度，note 写明"只管哪段、与什么无关"（破除"改 SAVE_MODE 能省 raw 盘"的误解），单测固化两按钮文案不可混淆。
- **AI 服务不可用**：指数退避（1→30 s），帧留在 `spool/` 不丢，同时写 `detect_fail` 事件行——恢复后自动续跑。
- **相机源断了**：`Capture.ensure_running()` 每轮重启抽帧进程；持续断流超 `M20AI_SOURCE_DOWN_SEC` 写心跳行，便于事后区分"没目标"和"没画面"。
- **时钟（ADR-004）**：车队 PTP 主时钟（`phc2sys` 从网卡 PHC 同步系统时钟）此前把本机钉在 2024-06-20（实测偏移 ~846 天），**不跟车队较劲**——采样器启动时向 AI 服务 `Date` 头自动测量偏移，JSONL 写修正后的 `ts` + 本机原值 `ts_host`；`M20AI_TS_OFFSET_SEC=0` 即自动测量，非 0 为手动钉值。**2026-10-16 核查：系统时钟已被修正**（chrony 同步 time.nju.edu.cn、偏差 <1ms、自动测量偏移 = 0），`ts == ts_host` 均为真实时间；机制保留作保险——若 PTP 再拖拽，自动测量会自动回到 ~846 天偏移。

### 6.1 主机侧运维：rsdriver（雷达驱动）日志限流（2026-10-17）

控制台「日志与数据留存策略」卡的 journal 区会显示整机 journal 占用——**其中 94.7% 来自厂商雷达驱动 `rsdriver.service`**（实测 40 行/秒 ≈ 345 万行/天 ≈ 295 MB/天，内容为 `recvLidar/recvImu msg_lidar is null`、`Exception ERRCODE_MSOPTIMEOUT`，且 `voltage/temp/timestamp` 均为 0）。已加 systemd drop-in 限流（**不屏蔽**，保留可见性）：

```ini
# /etc/systemd/system/rsdriver.service.d/10-log-ratelimit.conf
[Service]
LogRateLimitIntervalSec=60s
LogRateLimitBurst=30
```

- 效果（实测）：40 行/秒 → 约 1.4 行/秒（**降 96.5%**），journal 增速 295 MB/天 → 约 10 MB/天；
- 超出的日志由 journald 记一条 `Suppressed N messages from rsdriver.service`，错误仍可见；
- **还原**：删除该 drop-in → `systemctl daemon-reload` → `systemctl restart rsdriver`（`sudo` 口令为半角单引号 `'`）；
- ⚠️ **这些日志本身是雷达异常的信号**（数据全 0 / 收不到消息），限流只治"刷屏"，**雷达本身是否正常需另行排查**（M20 Pro 可在 AOS 控制台看「雷达供电 Front/Back」）。

---

## 7. 后续协作开发建议

### 7.1 立即事项（按依赖顺序，2026-10-15 更新）

1. ~~公钥投递~~ **已完成**（2026-10-15，askpass 一次性投递，之后全程免密）；
2. **先修出口再部署**（ADR-003）：门禁实测发现 GOS 默认网关 10.21.31.99 已 ARP 死、DNS 上行 8.8.8.8 被上游封、时钟慢约 846 天——前两项已按 ADR-003 修复（AOS 开 FORWARD / GOS 网关改指 AOS + DNS 改 192.168.0.1）；**时钟项已按 ADR-004 改为软件偏移方案**（chrony 被 `phc2sys` 每秒拖回，硬修不可行，已停 chrony 止住拉锯），每步可逆；
3. 出口修好后：`NO_RESTART=1 make deploy` → 104 上 `bash deploy/bootstrap.sh` → doctor 全绿；
4. doctor 绿了再 `sudo systemctl start`，观察 `journalctl -f` 与 `results/*.jsonl` 开始增长；
5. 跑 24 h 后用 `make stats` 核对磁盘增速，按实际调 `M20AI_RING_MAX_MB`。

### 7.2 多人/多机协作约定

- **代码唯一源**：本仓库；104 上的 `~/m20-ai-detect` 是"部署产物"，允许直接改的是**只有 `m20-ai-detect.env`**，且改动要回写到 `deploy/m20-ai-detect.env.example` 并提交。
- **禁止在 104 上直接改 `src/`**：会被下次 `rsync --delete` 覆盖且无痕。确需热修：开发机改 → 测试 → deploy。
- **新成员上手路径**：读本 README → `make test` 绿 → `make deploy-doctor` → 读 `docs/ADR-001/002` → 领一个子任务。
- **变更 JSONL schema**：先 bump `record["v"]` 并在 ADR 记录迁移策略；消费者（下游分析脚本）按 `v` 分支解析。

### 7.3 可预见的演进方向（触发即建 ADR）

| 方向 | 触发条件 | 提示 |
|---|---|---|
| 双相机 + 多能力 | 后视 `M20AI_ENABLE_B=1`；换 `M20AI_CAP_ID` | 代码已支持，纯配置 |
| 迁 SRS 汇聚点（227） | 多路统一检测 / 跨源对账 / GOS 灾备 / 外部消费（2026-10-15 已降级为远期备选，见 ADR-001 修订记录；单纯账号获批不构成迁移理由） | 改 `M20AI_SRC_*` 为 `rtmp://127.0.0.1:1936/live/m20pro-f` + `M20AI_FFMPEG_EXTRA=-fflags nobuffer -rw_timeout 10000000` |
| 告警外发 | 需要实时通知 | 当前只落盘；外发（邮件/企业微信）建议独立小模块，别塞进采样主循环 |
| 本地推理替代公网服务 | AI 服务延迟/可用性不达标 | NOS 负载 0.12 是候选；但 RK3588 无 NPU，YOLOv8 需实测帧率后再议 |
| 批量回放分析 | 需要补跑历史 | `raw/` 帧还在；写个一次性脚本读盘重放即可，别改主循环 |
| 留存条件细化 / 时间轴进阶 | 按标签分条件存（如只存 person 不存 chair）；时间轴分桶（稀疏历史 + 密集近期）；pin/收藏不被清理 | ADR-008 已把"按年龄/总量清理 + 时间轴"落地；`Sampler._should_save()` 与 `Store.clean_saved()` 是两个单点，加值分别只动这两处 |

### 7.4 已知坑速查

| 现象 | 原因 | 处理 |
|---|---|---|
| doctor `ai_health` FAIL | GOS 无出口：网关 .99 ARP 死 / DNS 上行 8.8.8.8 被上游封 | 按 ADR-003：AOS 开 FORWARD + GOS 网关改指 10.21.31.103 + DNS 改 192.168.0.1 |
| doctor `clock` WARN（钉值漂移） | `M20AI_TS_OFFSET_SEC` 钉值与实测偏差 >2 s（`phc2sys` 持续步进导致） | 更新 env 里的钉值，或直接设 0 改回自动测量（ADR-004） |
| JSONL `ts` 是 2024 年 | 时钟自动测量失败（AI 服务不可达），退化为本机时间 | 查 `ai_health`；恢复后重启服务即重测。`ts_host` 可用来识别这批记录 |
| 系统时间被神秘拖回（如手动 `date -s` 后分钟级复原） | `phc2sys -s eth0` 从网卡 PHC 同步 CLOCK_REALTIME，PHC 被车队 ptp4l 钉在 2024；`ptp_manage`（`Restart=always`）5 秒内重启被杀进程 | 别跟它较劲，走 ADR-004 软件偏移；必须修系统时钟的脱险出口见 ADR-004 |
| `source:*` FAIL | AOS MediaMTX 8554 没起 | 登 196 查 `start.service`；与本工程无关 |
| 服务起不来、journal 报 `status=203/EXEC` | unit 里 `ExecStart` 路径错 | `ReadWritePaths`/`ExecStart` 都用绝对路径 |
| 服务起不来、报用户相关错误 | GOS 无 `djw` 账户（2026-10-15 核实） | unit 已用 `User=user`；`/home/djw` 靠 ACL 授权 user 读写 |
| 改了 env 不生效 | systemd 不重读 `EnvironmentFile` | `sudo systemctl restart m20-ai-detect` |
| 帧积压 spool 不消化 | AI 服务挂了在退避 | `journalctl -u m20-ai-detect \| grep detect` |

---

## 附：一页速查

```bash
make help            # 所有目标
make test            # 41 项测试
make deploy          # 全套部署（测试+备份+同步+重启）
make deploy-doctor   # 远端门禁
make logs / stop / stats / paths / clean
python3 -m m20_ai_detect --version   # 核对远端版本
```

相关文档：`辅助工具/M20视频流AI检测-接入测试与实施方案.md`（架构与实测基线）、
`m20Pro/rtsp-rtmp/note/`（MediaMTX 与推流链路）、`m20Pro/analysis/`（三主机硬件巡检）。
