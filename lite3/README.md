# Lite3 笔记与主机运维资料

本仓库 `lite3` 是 [lite3Code](https://github.com/javencpdd/lite3Code) 的配套笔记库，也保存 Lite3 机器人 103（感知导航）与 120（运动控制）两台主机的审计和跨主机运维资料。`lite3Code` 是从 103 主机建立的代码仓库，包含 YOLO、监控面板、SCAN-Planner 等功能的源码、部署脚本和复现说明。本地通常分别位于 `/home/jack/lite3` 和 `/home/jack/lite3Code`。

**查实现与部署：先看 `lite3Code`；查环境、依赖关系、历史实测和操作风险：看本仓库。** 两库的主题对照、历史副本说明和同步约定见 [代码与笔记协作索引](docs/codebase-map.md)。本库文件或主机历史报告不能证明远端服务现在仍在运行。

## 主要内容

- 按主机整理 103/120 的系统、网络、ROS、视频、导航和脚本分析。
- 汇总跨主机职责、维护边界、故障记录与实施方案。
- 保留早期监控前端/后端原型和 103 文档副本，用于追溯；它们不等同于 `lite3Code` 当前版本。
- 提供连接前检查实际热点的 [Lite3 SSH 技能](script/lite3-robot-ssh/README.md)；仅在设备上电且网络满足条件时连接。

## 目录结构

> 本仓库根目录即 `lite3/`；本文档位于 `lite3/README.md`。

```text
lite3/
├── docs/                      # 文档入口
│   ├── codebase-map.md        # 两库主题映射与维护约定
│   ├── hosts/                 # 103、120 主机审计及 103 文档历史副本
│   ├── operations/            # 跨主机运维、巡检与检测方案
│   ├── scan-planner-note/     # SCAN-Planner 阶段性记录
│   ├── project/               # 项目规划与可行性评估
│   └── backup/                # 归档资料
├── lite3_robot_monitor/       # 早期监控应用与前端原型；非 103 部署权威版本
├── script/                    # 本地历史脚本与 lite3-robot-ssh 技能
├── 需要解决的通用问题/         # 跨主机待办与诊断资料（未纳入版本管理）
│   ├── 120主机热点信息/        # 120 热点网卡信息、wifi 诊断
│   ├── 日志/                  # 103/120 日志轮转存储说明
│   └── 新建用户/              # 在 103 上新建 ros1-slam 用户等记录
├── LICENSE
└── README.md                  # 本文件
```

文档索引见 [docs/README.md](docs/README.md)。`lite3Code` 的目录、运行依赖和部署步骤请看其 [README](https://github.com/javencpdd/lite3Code/blob/main/README.md) 与 `readme`；不要根据本库旧原型中的路径直接部署 103。

## 快速开始

阅读笔记无需安装依赖。两个仓库并列放置后，可以先核对代码版本，再选择笔记专题：

```bash
git -C /home/jack/lite3Code rev-parse --short HEAD
sed -n '1,200p' /home/jack/云深处/lite3/docs/codebase-map.md
sed -n '1,200p' /home/jack/云深处/lite3/docs/hosts/103-感知导航主机/README.md
```

实际修改 YOLO、监控面板或规划脚本时，在 `lite3Code` 中定位源码和部署说明；需要解释部署背景或风险时，再查本库对应笔记。120 侧内容以 [120 主机审计](docs/hosts/120-运动控制主机/README.md) 为入口，不应从 103 代码库推断其完整运行环境。

## 阅读顺序

1. [两库协作索引](docs/codebase-map.md)：确定代码、笔记和历史副本各在哪里。
2. [主机文档](docs/hosts/README.md)：分别了解 103 与 120 的环境和职责。
3. [跨主机维护](docs/operations/host-maintenance.md)：核对链路、配置来源和操作注意事项。
4. [SCAN-Planner 记录](docs/scan-planner-note/README.md)或[项目方案](docs/project/)：按专题查阶段性结论。

## 贡献与同步

1. 源码、可运行脚本、部署配置优先在 `lite3Code` 维护；本库记录关联代码路径、依据的 commit、主机与验证范围。涉及本库早期原型时，须明确说明是原型而非当前 103 部署版本。
2. 新笔记归入 `docs/hosts/`、`docs/operations/` 等对应专题，并更新目录 README；不要在根目录堆放业务文件。
3. 描述“当前状态”时注明采集时间、主机标识和只读实测依据。离线核对代码只能说明仓库内容，不能代替主机实测。
4. 不提交密码、私钥、Wi-Fi 密钥、客户数据或未经审计的机器人控制脚本。提交前运行 `git diff --check` 并检查相对链接。
5. 两库分别提交、分别遵守许可证；不能把 `lite3Code` 的 PolyForm 授权内容默认为本库的 MIT 内容。

## 许可证

本仓库采用 [MIT License](LICENSE)。`lite3Code` 的许可证独立，以其仓库中的 `LICENSE` 为准。
