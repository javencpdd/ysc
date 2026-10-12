# lite3 与 lite3Code 的协作索引

> 对照依据：2026-09-25 本地 `/home/jack/lite3Code` 的 `e9c5010` 提交及实际目录；本次未连接关机中的 Lite3，也未核验远端部署状态。代码库继续更新后，请重新核对本页。

## 仓库定位

- `/home/jack/lite3Code`：从 103 感知导航主机建立的功能复现与部署代码仓库。其公开地址为 [lite3Code](https://github.com/javencpdd/lite3Code)；模块入口以该仓库的 `README.md`、`readme` 和当前源码为准。
- `/home/jack/云深处/lite3`：配套笔记库，保存 103/120 主机审计、运行背景、风险、历史操作记录和跨主机方案。2026-10-12 起本库迁入 `/home/jack/云深处/` 工作区（与 `lidar/`、`m20Pro/` 并列）；本文中早期记录的本地路径按当时两仓库并列放在 `/home/jack/` 下编写，未逐一改写，以本行与工作区总索引 `~/云深处/README.md` 为准。
- 两库独立提交、独立授权。此笔记库采用 MIT；`lite3Code` 当前采用 PolyForm Noncommercial 1.0.0。不要因为有同名文件就把代码或许可证从一库直接覆盖到另一库。

## 主题对照

| 主题 | `lite3Code` 中的实现或操作入口 | `lite3` 中的笔记入口 |
| --- | --- | --- |
| 103 环境与整体复现 | `readme`、`note/00-环境基线.md`、`DRYRUN-变更预演清单.md` | [103 主机审计](hosts/103-感知导航主机/README.md)、[跨主机维护](operations/host-maintenance.md) |
| YOLO 视频检测、RTMP/ROS2 发布 | `yolo8/src/`、`yolo8/deploy/`、`note/01-yolo视频检测与推流.md` | [103 笔记副本](hosts/103-home-test-docs/README.md)、[视频与流媒体背景](hosts/120-运动控制主机/视频与流媒体/README.md) |
| 机器狗监控面板 | `lite3_robot_monitor/backend/`、`lite3_robot_monitor/deploy/`、`note/02-机器狗监控面板.md` | [本库监控原型](../lite3_robot_monitor/README.md)、[103 笔记副本](hosts/103-home-test-docs/README.md) |
| SCAN-Planner | `scan_planner/scripts/`、`scan_planner/note/`、`note/03-SCAN-Planner规划器.md` | [SCAN-Planner 实施记录](scan-planner-note/README.md)、[分层避障方案](operations/hierarchical-avoidance-3d-upgrade.md) |
| Foxglove / rosbridge | `foxglove/`、`note/04-Foxglove可视化与rosbridge.md` | [无图形界面远程运维方案](operations/headless-remote-ops.md) |
| 103 网络与出网 | `net/`、`note/05-网络与出网配置.md` | [103 主机审计](hosts/103-感知导航主机/README.md)、[跨主机维护](operations/host-maintenance.md) |
| RealSense 与零散测试 | `realsense_test/`、`script/`、`note/06-零散测试脚本.md` | [103 主机审计](hosts/103-感知导航主机/README.md)、`script/` 中的本地历史脚本 |
| 120 运动、热点与视频服务 | `lite3Code` 不作为 120 主机完整源码清单 | [120 主机审计](hosts/120-运动控制主机/README.md) |

这里的“实现入口”表示代码仓库内的实际目录，不表示远端服务现在仍在运行。部署命令和依赖以 `lite3Code` 当前文件为准，运行状态必须在主机上重新核验。代码仓库没有收录的 120 侧模块，不应凭 103 的仓库推断。

## 历史副本与版本差异

- `lite3/docs/hosts/103-home-test-docs/` 是 103 侧文档的历史副本，不与 `lite3Code/note/` 自动同步。两者已有部分文件不同；编辑前先比较，不能把副本当作最新部署说明。
- `lite3/lite3_robot_monitor/` 保留早期监控应用及前端原型；`lite3Code/lite3_robot_monitor/` 包含 103 侧后端、部署脚本和工具。两边并非完全相同：本库原型有 `frontend/`，但没有当前代码库的 `deploy/`。部署 103 时先看代码库，不能照搬本库旧 README 中不存在的路径。
- `lite3/docs/scan-planner-note/` 保存阶段性评估与执行记录；可运行脚本以 `lite3Code/scan_planner/scripts/` 为准。

## 推荐维护流程

1. 在 `lite3Code` 中定位当前源码、配置与部署脚本，并记录所依据的 commit：`git -C /home/jack/lite3Code rev-parse --short HEAD`。
2. 若要描述当前主机状态，先记录主机名、采集时间和只读实测依据；代码仓库或历史笔记均不能代替在线状态。
3. 在 `lite3` 的对应主机/专题笔记中写明“代码路径、commit、适用主机、验证范围和未验证项”。只记录实现细节或风险，不重复维护整份源码。
4. 功能或部署步骤发生变化时，先更新 `lite3Code` 的源码及模块说明，再同步本库的关联笔记和索引；两库分别检查链接、差异与许可证。

Lite3 关机或未连接热点时，可以核对本地两个仓库，但不要把本地文件检查写成“远端已部署并运行”。
