# ADR-004: 车队 PTP 时间基准与软件时钟偏移 —— 不跟车队较劲

- 日期：2026-10-15
- 状态：提议（代码已落地待部署验证；验证后转"已接受"）
- 影响面：`src/m20_ai_detect/config.py`（`ts_offset_sec`）、`detect.py`（`measure_clock_offset`）、`sampler.py`（`calibrate_clock` / `_now_pair` / v2 记录）、`cli.py`（`_check_clock` 偏移量语义）、两个 env 模板（`M20AI_TS_OFFSET_SEC`）、`docs/` 本文件
- 关联：ADR-003 第 3 条（chrony `makestep 1 -1`）的执行结论被本 ADR 修正——**chrony 路线在 GOS 上不可行**

## 背景

ADR-003 计划用 chrony 修 GOS 时钟（`makestep 1 -1` + 等 sources 上线后步进）。执行中发现时钟被一个**够不着的车队 PTP 主时钟**钉死，chrony 每次步进后 1~2 分钟内被拖回。2026-10-15 晚停止 chrony 止住拉锯，转向软件偏移方案。

### 证据链（2026-10-15 晚 / 10-16 复测，全部只读核实）

| # | 证据 | 命令 / 来源 | 结论 |
|---|---|---|---|
| 1 | `ptp4l -f /var/run/ptp/ptp4l_eth0.conf -i eth0 -m -q -s` | `ps aux`（PID 1248，root） | GOS 的 eth0 网卡跑在 **PTP 从模式**，上游有一个厂商 PGM 主时钟 |
| 2 | `phc2sys -s eth0 -w -z /var/run/ptp/ptp4l_eth0 -S 10.0 -m -q -l 6` | `ps aux`（PID 1835，root） | **系统时钟（CLOCK_REALTIME）被持续从网卡 PHC 同步**——这是时钟被拖回的直接机制 |
| 3 | journal 持续输出 `phc2sys: CLOCK_REALTIME phc offset -327 s2 freq -17795` 与 `ptp4l: master offset 20 s2` | `journalctl -u ptp_manage` | 两者都在活跃校正，拉锯是**进行时**而非历史 |
| 4 | `date` → `Thu 20 Jun 2024 23:57 CST` | 直接执行 | 系统时间钉在 2024-06-20，比真实时间慢约 846 天 |
| 5 | 实测偏移：AI 服务 Date 头 − 本机时钟 = **73100565.4 s（846.1 天）** | python3 urllib 打 `/api/v1/health`（10-16 复现，与 10-15 的 73100565 s 一致） | 偏移量级稳定可测；AI 服务 Date 头是**可达的标准时间源** |
| 6 | `ptp_manage.service` 位于 `/lib/systemd/system/`（厂商 unit），`Restart=always`、`RestartSec=5`、enabled | `systemctl cat ptp_manage` | **直接 kill ptp4l/phc2sys 会在 5 秒内被拉起**；这是厂商守护的跨主机行为（AOS 同样跑 `ptp4l -s`） |
| 7 | 此前 boot 的 journal 曾记录 `System clock was stepped by 73100573.871295 seconds`（chrony 步进记录） | 2026-10-15 排查记录；**当前 journal 已轮换，本轮不可复现实测** | chrony 确实步进过，但随后被 phc2sys 拖回 |
| 8 | chrony 当前 `inactive` | `systemctl is-active chrony` | 拉锯已止住（本 ADR 执行动作） |

### 为什么 chrony 路线不可行

- 修时钟 = 同时对抗 **phc2sys（秒级拖回）+ ptp_manage（5 秒重启）** 两层厂商机制，等于修改车队级行为；
- GOS 的时钟是**车队 PTP 域的从属节点**，车队其他成员（AOS 同样 `ptp4l -s`）默认共享这个 2024 基准——GOS 单独跳到真实时间，反而可能破坏依赖车队时间一致性的厂商组件（日志对齐、数据融合时间戳）；
- 收益（系统时钟正确）对本工程只有一处用处：JSONL 时间戳——而这一点用软件偏移即可拿到。

## 决策

**不跟车队较劲。GOS 保持车队时间基准（零风险、不动厂商机制），采样器启动时自动测量偏移量，把 JSONL 时间戳修正为真实时间。**

1. **偏移量来源**：AI 服务（`jsxy.aihyzh.com:30881`）`/api/v1/health` 的 `Date` 响应头——GOS 出公网修复（ADR-003）后实测可达（200 / 52 ms）。
2. **测量时机**：采样器 `run()` 启动时测量一次（`Sampler.calibrate_clock()`），全程复用；测量失败退化为 0（本机时间）并记日志，**不阻断运行**。
3. **配置 escape**：`M20AI_TS_OFFSET_SEC=0`（默认）= 启动自动测量；非 0 = 手动钉值，`doctor` 在实测偏差 >2 s 时判 WARN 提醒更新。选自动而非钉死的原因：phc2sys 持续步进使偏移量有秒级~十秒级波动（证据 3），钉值必然漂。
4. **JSONL schema 升 v=2**：`ts`（偏移修正后的真实时间）+ `ts_host`（本机原值，语义不变）+ `ts_offset_sec`（本次生效的偏移量）。保留 `ts_host` 是为了可对账、可回退——任何下游按 `ts_host` 处理的逻辑不受影响。

### 语义边界（如实声明）

修正后的 `ts` 精度 = AI 服务自身时钟的精度。该服务时钟与真实时间同代（2026-10 量级），但可能差数小时；相对 846 天的系统偏差，这是三个数量级的改善。下游若需要纳秒级/严格 ISO 对齐，应另行接入标准 NTP（见"触发复审的条件"）。

## 后果

### 正面

- **零系统风险**：不碰 ptp4l / phc2sys / ptp_manage / chrony 中任何一个，厂商机制原样；
- JSONL 时间戳可用（`ts` 为真实时间量级），告警、时序分析、与 PC 侧其他数据源对齐都不再被 2024 基准坑；
- AI 服务不可达时优雅退化为本机时间，采集不中断；
- `doctor` 的 clock 门禁从"必然 FAIL 846 天"改为偏移量语义（未配置 PASS 并打印实测偏移），门禁恢复可用。

### 负面 / 代价

- **依赖 AI 服务可达**才有真实时间戳；AOS WiFi 掉线期间（已知慢性问题）新记录退化为 2024 基准时间（`ts_host` 可识别）；
- 偏移量每次启动重测，若 AI 服务 Date 头异常（服务端时钟被篡改/异常），修正会引入错误——缓解：`ts_offset_sec` 与 `ts_host` 都在记录里，可事后审计；
- 系统时钟本身仍停在 2024：`journalctl`、`/var/log`、其他厂商组件的日志时间依旧是错的，**本方案只拯救本工程的 JSONL**。

### 脱险出口（若将来必须拥有真实系统时钟）

`systemctl stop ptp_manage && systemctl mask ptp_manage`（先停 phc2sys 拖回，再防 5 秒重启）→ 恢复 chrony（`makestep 1 -1` 已配置）→ 验证 chrony 能压住时钟。**执行前必须评估对车队其他成员的影响**（GOS 脱离 PTP 域后，依赖它的厂商组件行为未知）。本 ADR 不推荐默认走这条路。

### 触发复审的条件

1. 厂商提供可配置的 PTP 主时钟或修正基准 → 重估 chrony 路线。
2. 需要严格时间对齐（如多机数据融合要求同一时基）→ 升级到标准 NTP 服务，脱离 AI 服务 Date 头方案。
3. AI 服务地址变更或 Date 头不可用 → 更换标准时间源（如 192.168.0.1 若提供 NTP，或 PC 侧时钟服务）。
