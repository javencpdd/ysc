# /home/test 上传 GitHub 审计清单

> 扫描对象：103 主机（192.168.1.103，hostname `lite`）`/home/test`
> 扫描时间：2026-09-23 02:16（只读扫描，**未做任何修改**）
> 总计：**919 MB / 3973 个文件**，目录下**没有任何 `.git` 仓库**，也没有任何 `LICENSE` 文件

---

## 一、结论先行

**可以传，但 87% 的体积是"水分"，且存在两条开源合规红线。**

- 919 MB 里约 **800 MB 是构建产物 / 数据集 / 模型权重**，本来就不该进 Git；
- 剔除后剩 **约 73 MB**，而这 73 MB 里又有 **65 MB 是第三方代码**（EGO-Planner 系仿真器 + Unitree 模型 + ultralytics）；
- **真正属于你自己的成果只有 2~3 MB**：部署脚本、踩坑笔记、监控项目；
- 密钥扫描 **零命中**（好消息），但 **28 个文件含内网 IP**；
- ⚠️ `ultralytics/` 是 **AGPL-3.0**，`scan_planner/src/simulator` 疑似 **GPLv3 系 + Unitree 资产**，直接整包开源会有许可传染风险。

**建议：不要建一个 `/home/test` 大仓库，拆成 3 个小仓库，只传自有代码 + 笔记。**

---

## 二、体积总览

| 一级目录 | 原始大小 | 剔除后 | 判定 |
|---|---:|---:|---|
| `scan_planner` | 414 MB | 66 MB | ⚠️ 体积全在 `build/`+`devel/`，`src/simulator` 是第三方 |
| `realsense_test` | 404 MB | 1.6 MB | 🔴 99.6% 是一个 `test.bag` |
| `yolo8` | 67 MB | 2.6 MB | ✅ 主力候选，但 `model/` 53 MB 要剔 |
| `monitor` | 34 MB | 1.5 MB | 🔴 与 `lite3_robot_monitor` 重复，建议弃 |
| `lite3_robot_monitor` | 1.5 MB | 1.5 MB | ✅ 保留 |
| `foxglove` | 128 KB | 120 KB | ✅ 保留 |
| `script` | 100 KB | 80 KB | ✅ 保留 |
| `net` | 16 KB | 16 KB | ✅ 保留 |
| `readme` | 4 KB | 4 KB | ✅ 保留 |
| **合计** | **919 MB** | **≈73 MB** | |

> "剔除后"= 排除 `build/ devel/ model/ logs/ __pycache__/ .venv/ *.bag` 之后的实测值。

## 三、体积 Top 20（实测 `du -ah | sort -hr`）

| # | 路径 | 大小 |
|---|---|---:|
| 1 | `realsense_test/test.bag` | **402 MB** 🔴 |
| 2 | `scan_planner/build` | 225 MB |
| 3 | `scan_planner/devel` | 120 MB |
| 4 | `scan_planner/src` | 66 MB |
| 5 | `yolo8/model` | 53 MB |
| 6 | `scan_planner/src/simulator/Utils/go2_description` | 51 MB |
| 7 | `scan_planner/build/planner/plan_manage/CMakeFiles` | 54 MB |
| 8 | `scan_planner/build/planner/traj_utils/...` | 46 MB |
| 9 | `yolo8/logs` | 9.9 MB |
| 10 | `yolo8/src/ultralytics` | 3.6 MB ⚠️ AGPL |
| 11 | `scan_planner/logs` | 3.6 MB |
| 12 | `realsense_test/rs-save-to-disk-output-Color.png` | 1.4 MB |
| 13 | `monitor/frontend` / `lite3_robot_monitor/frontend` | 各 1.2 MB |
| 14 | `monitor/backend` | 356 KB |
| 15 | `lite3_robot_monitor/backend` | 208 KB |
| 16 | `realsense_test/rs-save-to-disk-output-Depth.png` | 160 KB |
| 17 | `foxglove/foxglove_ws` | 120 KB |
| 18 | `scan_planner/note` | 92 KB ⭐ |
| 19 | `yolo8/deploy` | 84 KB ⭐ |
| 20 | `yolo8/note` | 52 KB ⭐ |

⭐ = 真正值得入库的"自有成果"。

## 四、超限文件（GitHub 硬限 100 MB/文件）

| 文件 | 大小 | 处理 |
|---|---:|---|
| `realsense_test/test.bag` | 402 MB | 🔴 **不入库**。要留存就丢 Release 附件（单附件限 2 GB）或干脆删掉 |

单文件 >100 MB 会被 GitHub **直接拒绝 push**，不是警告。其次 >50 MB 会触发警告。

## 五、敏感信息扫描结果

**密钥类：0 命中** ✅

严格正则（`gh[pousr]_xxxx20+`、`github_pat_`、`AKIA[16]`、`-----BEGIN PRIVATE KEY-----`、
`password/token/secret/api_key = "xxx"`）全目录扫描，**无任何命中**。
`find` 密钥文件只找到 1 个：`monitor/.venv/.../certifi/cacert.pem`（CA 根证书，无害）。

> 第一次扫描出的 40 条"命中"是误报——`ghp_` 匹配到了 glm 头文件里的 `highp_`，已用严格版排除。

**内网信息：28 个文件命中** ⚠️

| 类别 | 文件 |
|---|---|
| 笔记 | `scan_planner/note/*.md`(5)、`yolo8/note/双通路发布-踩坑记录.md` |
| 部署脚本 | `lite3_robot_monitor/deploy/{install,pack,deploy_103}.sh`、`deploy/README.md`、`scan_planner/scripts/env.sh` |
| 后端代码 | `monitor|lite3_robot_monitor/backend/{config,control_protocol,udp_sniffer}.py`、`tools/*.py` |
| 日志 | `scan_planner/logs/*`（6 个） |
| 其他 | `net/readme` |

涉及 `192.168.x.x` 与 `172.31.68.227`（SRS 服务器）。**建议：私有仓库，或提交前统一替换为 `<HOST_IP>` / `<SRS_HOST>` 占位符。**

## 六、🔴 两条开源合规红线（最容易被忽略）

1. **`yolo8/src/ultralytics`（3.6 MB）= AGPL-3.0**
   Ultralytics 的 YOLOv8 是 AGPL 许可。把它整包放进你自己的公开仓库，
   意味着**你的仓库整体需以 AGPL-3.0 开源**。
   → 对策：不要提交 `ultralytics/` 源码，改用 `requirements.txt` 里的 `ultralytics==x.y.z` 依赖。

2. **`scan_planner/src/simulator`（65 MB）= 第三方 EGO-Planner 系 + Unitree 资产**
   目录结构（`bspline_opt / path_searching / plan_env / plan_manage / traj_utils` + `mockamap`）
   是典型 EGO-Planner/EGO-Swarm 布局；内含 `go2_description`（51 MB，Unitree Go2 模型网格）。
   → 对策：用 `git submodule` 指向上游仓库，**不要复制进自己的仓库**；
     `go2_description` 的 meshes 尤其别传（51 MB 纯二进制 + 第三方资产）。

> 目前 `/home/test` 下**没有任何 LICENSE 文件**，说明这些内容原本就是本地测试用的散文件，从未做过许可梳理。

## 七、重复项目：`monitor` vs `lite3_robot_monitor`

两者文件列表几乎完全相同，`lite3_robot_monitor` 只多出 `deploy/` 下 7 个文件：

```
deploy/deploy_103.sh  deploy/install.sh  deploy/pack.sh  deploy/README.md
deploy/lite3-monitor.service  deploy/lite3-monitor-rosdirect.service  deploy/lite3-ros-bridge.service
```

`monitor` 还带一个 `.venv`（含 27 个 `.whl`）。
→ **结论：`monitor` 是旧副本，只保留 `lite3_robot_monitor`**，省 32 MB。

## 八、建议的仓库划分（3 个，总入库量约 3 MB）

| 仓库 | 内容 | 预估体积 | 建议可见性 |
|---|---|---:|---|
| `lite3-robot-monitor` | `lite3_robot_monitor/`（backend + frontend + tools + deploy） | ~1.5 MB | 私有或公开均可 |
| `lite3-yolo-deploy` | `yolo8/{deploy,note,src 自写部分}` + `scripts/download_model.sh` | ~300 KB | 私有（含内网 IP） |
| `scan-planner-notes` | `scan_planner/{note,scripts}`（**只放你自己的笔记和脚本**） | ~100 KB | 公开（纯原创笔记，最有分享价值） |

**不入库**：`test.bag`、`build/`、`devel/`、`model/`、`logs/`、`__pycache__/`（9.4 MB/1015 个）、`.venv/`、`monitor/`、`scan_planner/src/`。

`yolo8/src` 里属于你自己的只有：`run_tracker_publish.py`(8K)、`RobotController/`(108K)、
`RtmpPublisher/`(24K)、`GStreamerWrapper/`(16K) —— 合计不到 160 KB。
`ultralytics/`、`hub_sdk/`、`test/`、`__pycache__/` 都应排除。

## 九、可直接用的 `.gitignore`

```gitignore
# 构建产物
build/ devel/ install/ logs/ *.log
__pycache__/ *.py[cod] .venv/ venv/ node_modules/

# 模型与权重（改用 scripts/download_model.sh 获取）
*.engine *.plan *.trt *.onnx *.pt *.pth

# 数据与大文件
*.bag *.pcd *.ply *.mp4 *.mkv core core.*

# 第三方代码（用 submodule / 包管理替代）
src/ultralytics/ src/hub_sdk/ scan_planner/src/simulator/

# 密钥
.env *.pem *.key id_rsa*
# 注意：deploy/yolo-publish.env 是配置文件，改名为 .env.example 后再入库
```

## 十、推送路径（103 直连 GitHub 443 超时）

**推荐方案 A**：103 打包 → scp 到 Windows 本机 → 本机 push

```bash
# 103 上
cd /home/test/yolo8 && git init -b main
cp .gitignore.example .gitignore   # 用上面的模板
git add -A && git add -A -n        # 先看 dry-run
git -c user.email=you@example.com -c user.name=you commit -m "init"
git bundle create /tmp/yolo8.bundle --all

# Windows Git Bash 上
scp ysc@192.168.1.103:/tmp/yolo8.bundle .
git clone yolo8.bundle yolo8 && cd yolo8
git remote set-url origin git@github.com:<user>/lite3-yolo-deploy.git
git push -u origin main
```

**方案 B**：103 上走代理 `export https_proxy=http://192.168.2.47:7897` 后直接 push（可行但慢，实测 clone 约 4m30s）。
**方案 C**：`gh-proxy.com` 镜像 —— 拉可以，push 不稳，不推荐。

## 十一、建议执行顺序

1. 先删/归档 `realsense_test/test.bag`（402 MB，本机留一份即可，无需上云）；
2. 决定 `scan_planner` 要不要开源 —— 若要，只提 `note/` + `scripts/`，`src/` 用 submodule；
3. 建私有仓库（因为 28 个文件含内网 IP），先传 `lite3-robot-monitor` 试水；
4. 传 `lite3-yolo-deploy`，补 `scripts/download_model.sh` + `.env.example`；
5. 最后处理 `scan_planner` 笔记（这个最适合公开，是纯原创经验）。
