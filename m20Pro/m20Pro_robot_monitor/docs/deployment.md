# 部署（deployment）

> 目标主机：**AOS 192.168.0.196**（SSH 别名 `m20pro-f20-0-196`，账号 `user`）· 安装目录：**`/home/djw/monitor`**
> 相关：[QUICKSTART.md](../QUICKSTART.md)（10 分钟版）· 计划书 §15（完整部署方案）

---

## 1. 部署拓扑与位置选型

**为什么是 196（AOS）**：监控协议服务端（`basic_server`）与相机推流（MediaMTX）**都在 AOS 本机**——后端驻同机后，回环直达（`127.0.0.1:30000` / `127.0.0.1:8554`），LAN 只暴露 Web 端口。

```
PC（写码/构建/打包）                AOS 196（运行）                   机器人本体
────────────────────              ──────────────────               ──────────
frontend/ npm run build           /home/djw/monitor/                basic_server :30000
deploy/pack.sh ──scp──►           ├ backend/  ← venv/bin/python -m uvicorn
                                  ├ frontend/dist/  ← 静态托管
                                  ├ hls/  ← ffmpeg 切片产物
                                  └ venv/  ← aarch64，196 本地创建
                                  systemd: m20pro-console.service
浏览器 ◄── http://192.168.0.196:8080/ ──┘
```

| 部署位 | 结论 | 理由 |
| --- | --- | --- |
| **196（AOS）** | ✅ **选定** | 监控协议 + MediaMTX 同机；唯一有 WiFi 的 M20 主机，LAN 直达 |
| 104（GOS）/ 106（NOS） | ✗ | 需跨主机拉流/转发，多一跳且引入新故障面 |
| PC | ✗ | 数据源在机器人侧，PC 不常在线 |

---

## 2. 交付链路

### 2.1 首次安装（三步）

```bash
# ① PC：构建 + 打包
cd frontend && npm run build && cd ..
bash deploy/pack.sh                              # → m20pro-console-deploy.tar.gz（不含 node_modules/venv/capture）

# ② PC：上传（196 经 WiFi 会间歇丢包，失败重试即可）
scp m20pro-console-deploy.tar.gz m20pro-f20-0-196:/tmp/

# ③ 196：解压 + 安装
ssh m20pro-f20-0-196
cd /tmp && tar xzf m20pro-console-deploy.tar.gz
sudo bash m20pro_console/deploy/install.sh /home/djw/monitor
```

包内含：`backend/`、`frontend/dist/`、`deploy/`、`tools/`、`note/`、`requirements.txt`、`config.example.toml`。

### 2.2 日常迭代（不重装）

```bash
# PC（若本机有 rsync / WSL / Linux）
bash deploy/deploy_196.sh                 # rsync backend + frontend/dist → systemctl restart

# PC（Windows Git Bash 无 rsync 时的替代：tar + scp）
tar czf /tmp/m20-dist.tar.gz -C frontend dist && scp /tmp/m20-dist.tar.gz m20pro-f20-0-196:/tmp/
ssh m20pro-f20-0-196 "cd /home/djw/monitor/frontend && rm -rf dist.old && mv dist dist.old && \
  tar xzf /tmp/m20-dist.tar.gz -C . && rm -rf dist.old"
# 仅后端变更时：
ssh m20pro-f20-0-196 "printf \"'\n\" | sudo -S systemctl restart m20pro-console"
```

> 前端静态资源由 FastAPI `StaticFiles` **按请求读盘**——替换 `dist/` 后无需重启。
> 后端代码变更必须重启服务。配置为启动时读取，改配置也必须重启。

### 2.3 何时必须重跑 `install.sh`

| 情况 | 原因 |
| --- | --- |
| 改了 `requirements.txt` | 需重装依赖 |
| 改了 `deploy/m20pro-console.service` | 需重生成 systemd 单元 |
| 换安装目录 / 首次安装 | — |

---

## 3. `install.sh` 做了什么（逐步）

| 步骤 | 行为 | 防的坑 |
| --- | --- | --- |
| [1/6] 目录与文件 | `copy_dir()`（`rsync -a --delete` 或 `cp -r src/. dst/`）复制 backend / dist / tools / note | **`cp -r src dst/` 在目标已存在时会嵌套成 `dst/backend/backend`**，导致"改了不生效"（实测踩过，骗过两轮） |
| [2/6] 虚拟环境 | 三层降级：`python3 -m venv` → `apt install python3.8-venv python3-pip` → `pip install --user virtualenv` | 196 **缺 ensurepip**，裸 `python3 -m venv` 必失败 |
| [3/6] 依赖 | `pip install -r requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com` | 196 时钟慢 846 天 → **HTTPS/TLS 全废**；清华 http 返回 403，阿里可用 |
| [4/6] 权限 | `chown -R $RUN_USER:$RUN_USER $INSTALL_DIR` | 服务以非 root 运行 |
| [5/6] systemd | `sed` 替换单元中的路径字面量与 `User=`/`Group=` → `/etc/systemd/system/m20pro-console.service` + `daemon-reload` + `enable` | 支持装到非默认目录 |
| [6/6] 启动验证 | `restart` + 5s 后 `is-active` + `/health` | 失败即打印 journal 尾部 |

**运行用户（`RUN_USER`）探测逻辑**：取安装目录属主（`/home/djw/monitor` → `djw`）；**该用户不存在则降级为 `sudo` 调用者（`user`）并 warn**。
> 196 现状：**`djw` 账户不存在**，服务实际以 `user` 运行（功能无差异）。将来创建 `djw` 后：`chown -R djw:djw /home/djw/monitor` + 改单元 `User=`/`Group=` + `daemon-reload` + `restart`。

---

## 4. systemd 单元（`deploy/m20pro-console.service`）

关键字段逐条说明：

| 字段 | 值 | 说明 |
| --- | --- | --- |
| `WorkingDirectory` | `/home/djw/monitor/backend` | uvicorn 以 `main:app` 相对导入 |
| `User` / `Group` | `user`（安装时自动探测写入） | 非 root |
| `ExecStart` | `venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080` | 单进程 |
| `M20__DATA_SOURCE` | `udp` | 真机模式（mock 用于演练） |
| `M20_ROBOT__TARGET_IP/PORT` | `127.0.0.1` / `30000` | 回环直达 basic_server（实测其监听 0.0.0.0） |
| `M20_SERVICE__PORT` | `8080` | 已避让 196 全部冲突端口（C5 清单） |
| `M20_CONTROL__ENABLED` | **`false`** | L0 只监默认（安全设计） |
| `M20_VIDEO__ENABLED` | `true` | 196 部署开启视频代理 |
| `M20_VIDEO__RTSP_URL` | `rtsp://127.0.0.1:8554/video1` | 196 本机 MediaMTX |
| `M20_VIDEO__HLS_DIR` | `/home/djw/monitor/hls` | 切片产物（有界自动删除） |
| `Restart` / `RestartSec` | `on-failure` / `3` | 崩溃自愈 |
| `KillSignal` / `TimeoutStopSec` | `SIGTERM` / `10` | 优雅停机：看门狗补零位 → 关控制 → 停数据源 |
| 日志 | `journal`（`SyslogIdentifier=m20pro-console`） | `journalctl -u m20pro-console` |

**修改配置的推荐方式**（不会被重装覆盖）：

```bash
sudo systemctl edit m20pro-console     # 写 [Service] 段 drop-in
# 例：Environment=M20_CONTROL__ENABLED=true
sudo systemctl daemon-reload && sudo systemctl restart m20pro-console
```

---

## 5. 196 环境已知坑（全部实测，脚本已内置规避）

| 坑 | 现象 | 规避 |
| --- | --- | --- |
| **时钟慢 ~846 天** | 任何 HTTPS/TLS 失败；pip 默认源不通；`ls` 显示 2024 年时间戳 | 装依赖走 http 镜像（内置）；控制台自身用 monotonic，不依赖时钟 |
| **缺 ensurepip** | `python3 -m venv` 失败 | 三层降级（内置） |
| **WiFi 间歇丢包** | scp/ssh 偶发中断 | 重试即可；rsync 带 `-z` |
| **CRLF** | Windows 编辑的 `.sh` 报 `bad interpreter` | `.gitattributes` 固化 LF；上传后必要时 `sed -i 's/\r$//'` |
| **`cp -r` 嵌套** | "改了不生效" | `copy_dir()`（内置） |
| **静态挂载顺序** | `/hls/*` 被 `/` catch-all 吃掉 → HLS 404 | `main.py` 先挂 `/hls` 后挂 `/`（代码已修） |
| **打包静默失败** | 输出重定向时失败不易察觉 → 传了旧包 | 打包后核对包内文件（流程约定） |
| **`install.sh` 无输出退出码 127** | `set -e` 下调用了未定义函数 | 日志函数定义提前到变量区之前（代码已修） |
| `/userdata` 挂载 | 与 `/` 同容量（18G overlayroot，均余 14G） | 最终按用户指定装 `/home/djw/monitor`（在 `/` 分区） |

---

## 6. 安装路径迁移记录（2026-10-15）

| 阶段 | 路径 | 状态 |
| --- | --- | --- |
| 首装 | `/userdata/m20pro-console` | 已删除（26MB，审计确认无独有文件、服务单元 0 引用） |
| **最终（用户指定）** | **`/home/djw/monitor`** | ✅ 当前运行；迁移后复验 13/13 |

删除旧目录的正确姿势（`/userdata` 属主 root：普通权限只能删内容，顶层条目需 sudo）：

```bash
rm -rf /userdata/m20pro-console            # 删除内容（属主 user 可删）
printf "'\n" | sudo -S rmdir /userdata/m20pro-console   # 移除空目录（需 root）
```

---

## 7. 部署产物布局（196 现状）

```
/home/djw/monitor/
├── backend/                 # 后端源码（WorkingDirectory）
├── frontend/dist/           # 前端构建产物（静态托管）
├── hls/                     # ffmpeg HLS 切片（live.m3u8 + seg_N.ts，自动滚动删除）
├── tools/                   # probe_asdu / verify_deploy / analyze_capture
├── note/                    # 计划书（含全部部署知识）
├── venv/                    # aarch64 虚拟环境（不可从 Windows 拷贝）
├── requirements.txt
└── config.example.toml
```

---

## 8. 升级与回滚

**升级**：重跑一次完整「构建 → 打包 → 安装」即可（`copy_dir` 幂等覆盖；`hls/` 与 `venv/` 不受影响）。

**回滚**：
- 前端：`mv dist dist.new && mv dist.old dist`（如果做了备份）——或直接用旧 `dist` 重传；
- 后端：代码在 Git，`git checkout <旧版本>` 后重传 `backend/` + `restart`；
- 服务不可用但需要保命监控：`M20__DATA_SOURCE=mock` 起服务让页面可用（数据是模拟的，会明确标注）。

**手动重启/停用**：

```bash
sudo systemctl restart m20pro-console
sudo systemctl stop m20pro-console && sudo systemctl disable m20pro-console   # 彻底停用
```

---

## 9. 部署验收（`tools/verify_deploy.py`）

```bash
python3 /home/djw/monitor/tools/verify_deploy.py                 # 196 本地
python3 tools/verify_deploy.py --base http://192.168.0.196:8080  # 从 PC 跨网验证
```

13 项检查（2026-10-15 全绿）：

| # | 检查 | 通过标准 |
| --- | --- | --- |
| 1 | `/health` | 200 且 `connected=true`、`data_source=udp` |
| 2 | `/ready` | `degraded=false` |
| 3 | 快照 `schema_version` | `1.0` |
| 4 | 链路 `connected` | `true` |
| 5–9 | 5 个 topic（basic/motion/device/fault/nav） | 存在且非 stale |
| 10 | 视频代理 | `running=true` 且 `available=true` |
| 11 | 前端根路径 | 200 |
| 12 | HLS 播放列表 | 200 |
| 13 | LAN 可达（从 PC） | 页面 200 |

> ⚠️ 视频两项的前提是**机器人已唤醒**（相机随车供电）。机器人休眠时这 2 项会红，其余仍应全绿——这是预期行为，不是部署失败。
