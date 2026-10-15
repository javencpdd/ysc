# ADR-007: 终端运维命令 aiDetect（up/down/reset）

- 日期：2026-10-15
- 状态：已接受
- 影响面：`deploy/aiDetect`（新文件）、`deploy/m20-ai-console-helper`（新增 console-* 子命令）、`deploy/m20-ai-console.sudoers`（6→9 条）、`deploy/console-bootstrap.sh`（新增装入步骤）、`deploy/install.sh`（新增 bash -n 门禁）

## 背景

1. 服务的启停此前只有两条路：**网页控制台**（要浏览器、要能连内网 5050）或 **ssh 手敲 `sudo systemctl ...`**（sudo 有口令、非交互场景要 `printf "'\n" | sudo -S` 这种别扭写法）；
2. 2026-10-15 深夜 AI 服务间歇劣化事件里，"先把采样器停下来"这个最高频的运维动作反而最不顺——需要人工记忆 sudo 口令、service 名与正确写法；
3. 用户明确需求（原话）："该服务如何停止呢，能不能做一个终端命令控制，例如 aiDetect up/down/reset"。

已排除的选项：

- **在 sudoers 里直接放开 `systemctl start/stop/restart m20-ai-detect`**：把 root 能力直接铺给 `user`，破坏 ADR-005 确立的"单一提权入口（helper）"原则；
- **CLI 走控制台 HTTP API**：控制台自身也是被管理对象（如 `--all` 要停它），且控制台停止时 API 不可用（鸡生蛋）；
- **把 sudo 口令写进脚本/做成 NOPASSWD 全量 sudo**：凭证泄漏面扩大，直接否决。

## 决策

提供纯 bash 单文件命令 `deploy/aiDetect`（装入 `/usr/local/bin/aiDetect`，另留小写别名 `aidetect`），核心子命令与语义：

- `up / down / restart [--all]`——经**既有 sudoers 白名单 helper** 控制采样器（`--all` 连控制台一起）；
- `reset`——停采样器 → 删 `spool/*.jpg` → 起采样器，与网页「清空积压帧」同一操作语义（只清未推理的待办帧）；
- `status / log / doctor`——巡检三件套，零提权（纯本地读 + journalctl）。

配套改动：helper 新增 `console-start|console-stop|console-restart`（管理 `m20-ai-console.service` 自身），sudoers 白名单从 6 条扩到 9 条——仍全部为**精确完整命令行、无通配符**。

**2026-10-15 扩充（ADR-008）**：新增 `enable / disable [--all]` 子命令（开机自启开关，幂等）；
`status` 增显示"开机自启 采样器 X · 控制台 Y"；helper/sudoers 再扩 `svc-enable|disable`、
`console-enable|disable`（9→13 条）。背景：用户要求部署**默认不开机自启**（重启后手动
`aiDetect up --all`），两个 bootstrap 同步取消自动 `enable`。

## 依据

- 2026-10-15 本地打桩验证（stub 掉 systemctl/sudo/journalctl）：up/down/restart/reset/status/log 全流程、幂等（对已是目标态的服务不重复调用）、失败中止（停服务失败则不删帧）、helper 调用次序（stop→start 严格有序）均符合预期；
- 修复打桩中暴露的真实健壮性问题：`set -e + pipefail` 下 `hostname -I`／无条件 `find` 管道返回非零会杀死整个 status——已全部加 `|| true` 兜底并复测；
- 104 实测（2026-10-15）：`aiDetect status / down / up / reset / log / doctor / down --all / up --all` 端到端通过；helper 调用在系统日志留痕（GOS 无 rsyslog，落 journald：`journalctl -t m20-ai-console-helper`），控制台 spool 清空记 `journalctl -t m20-ai-console`；
- 提权面复核：新增 3 条白名单仅允许对 `m20-ai-console.service` 做 start/stop/restart，无参数注入面；`reset` 的删帧完全不提权（`spool/` 归 `user`，与网页端同一路径）。

## 后果

### 正面

- 服务管理从"记 sudo 口令 + 手敲长命令"降为三个词：`aiDetect down / up / reset`；
- `reset` 与网页按钮走**同一操作语义**（停→清→起），两条操作路径不会漂移；
- 全部服务动作仍只有 helper 一个 root 入口，`logger` 留痕可审计；提权模型未放宽（仍是精确命令行白名单）；
- `status` 一屏给出：服务状态/PID、版本、spool 积压及最老帧年龄、今日检测数、留存对数、磁盘、最近一条检测——巡检从"敲 5 条命令"变为"敲 1 条"。

### 负面 / 代价

- sudoers 白名单从 6 条增至 9 条（提权面轻微扩大，均为固定命令行）；
- 多一个需要随版本同步部署到 `/usr/local/bin` 的文件（补偿：`install.sh` 本地门禁已加 `bash -n` 语法检查 + LF 行尾检查覆盖 `deploy/aiDetect`）。

### 触发复审的条件

- 出现"多主机同管"或"从非 104 主机远程执行"的需求时——应改为集中化运维通道（SSH 编排等），而不是继续往 aiDetect 加子命令；
- 若将来出现需要交互确认的危险动作（如清空 `results/` 权威数据），**不得**直接加进本 CLI，须单独设计显式确认与二次校验。

---

## 修订记录 2026-10-16（ADR-010）：启动行为与参数面调整

用户要求"启动服务时只启动控制台，不自动启动采样器；采样器由控制台开关控制、默认关闭；不需要 `--all` 参数"。
据此修订本 ADR 的命令语义（提权模型不变，仍为 helper + 精确命令行白名单）：

| 命令 | 修订后语义 |
|---|---|
| `up` / `down` / `restart` | **只作用于控制台**（`m20-ai-console`） |
| `collect on\|off\|status\|restart` | **新增**：采集开关（`m20-ai-detect` 采样器），默认关闭 |
| `enable` / `disable` | **只作用于控制台**的开机自启；采集不设自启 |
| `reset` | 语义不变（内部临时停/起采样器以清空 spool/） |
| `--all` | **移除**；传参直接报错（不静默忽略） |

`status` 输出同步调整：控制台在前、采集在后，并单列"采集开关"与"开机自启"行。
usage 帮助文本、README §4.6、USAGE §0/§2.4/§5 已同步。详细动机与设计见 ADR-010。

## 修订记录 2026-10-16（ADR-011）：`reset` 不再拉起停着的采集

上一修订中 `reset` 被记为"语义不变（内部临时停/起采样器以清空 spool/）"——这个"无条件停→清→起"
会让**采集原本关着**的情况下被 `reset` 顺手启动，与 ADR-010"采集开关归用户"矛盾。
据 ADR-011 修正为**保持原状态**：

| 场景 | `reset` 行为 |
|---|---|
| 采集运行中 | 停采集 → 删 `spool/*.jpg` → 恢复启动（然后以实时 1 fps 消费） |
| 采集原本关闭 | 只删 `spool/*.jpg`，**不启动**（提示 `aiDetect collect on` 可开采集） |

网页端对应操作（「清理数据」勾选 `spool/`）同步为同一语义；README/USAGE 文案已同步。
