# ADR-003: GOS 出公网路径 —— 经 AOS 中转（修复死网关 + DNS + 时钟）

- 日期：2026-10-15
- 状态：提议（待执行验证后转"已接受"）
- 影响面：AOS 196 的 iptables FORWARD 链、GOS 104 的 `/etc/netplan/config.yaml` 与 `/etc/chrony/chrony.conf`、`deploy/m20-ai-detect.service`（User=user）、`deploy/bootstrap.sh` 用户校验

## 背景

2026-10-15 公钥投递后首次上机门禁核查（V0″），推翻了 ADR-001 中"GOS 具备出公网条件"的假设。实测证据链：

| 检查 | 结果 | 结论 |
|---|---|---|
| GOS `ip neigh` 中 10.21.31.99 | `INCOMPLETE`（ARP 无应答） | **默认网关二层即死** |
| GOS `curl` AI 服务 | `No route to host`（网关 ARP 失败） | 零互联网出口 |
| GOS `getent hosts jsxy.aihyzh.com` | 超时 | DNS 不通（上行 8.8.8.8 不可达） |
| GOS `chronyc sources` | `Number of sources = 0` | chrony 从未同步（pool 域名解析不了） |
| GOS `date` | 2024-06-20（真实 2026-10-15） | **时钟慢约 846 天**，与 196 同款慢性病 |
| AOS `curl` AI 服务 | **HTTP 200，connect 45 ms** | AOS 出口完好，中转方案成立 |
| AOS ping 8.8.8.8 / UDP 53 查询 | 超时 | 上游（腾达）封 8.8.8.8 |
| AOS `resolvectl` | Current DNS = **192.168.0.1**（p2p0/腾达） | 唯一实测可用的解析器 |
| GOS `/home/djw` | root 所有 + ACL `user:user:rwx` | 工作空间路径可用，但账户须用 `user` |
| GOS `id djw` | no such user | unit 的 `User=djw` 必须改为 `user` |

AOS 现状（只读核实）：`POSTROUTING -s 10.21.31.0/24 -o p2p0 -j MASQUERADE` 在位（计数 0，从未被 GOS 用过）；FORWARD 仅有 `eth2→p2p0 state RELATED,ESTABLISHED` 与 `p2p0→eth2 ACCEPT`，**GOS 主动外联的 NEW 连接会被 policy DROP**。

## 决策

三处修改，全部可逆、全部持久化：

1. **AOS 放行内网主动外联**：
   `iptables -I FORWARD 1 -i eth2 -o p2p0 -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT` + `netfilter-persistent save`。
2. **GOS 默认网关改指 AOS、DNS 改用腾达路由器**（编辑 `/etc/netplan/config.yaml`，先备份）：
   - `eth0.gateway4: 10.21.31.99 → 10.21.31.103`
   - `eth0.nameservers.addresses: [8.8.8.8] → [192.168.0.1]`
   - `netplan apply` 生效。`.99 已 ARP 死，改网关无可失之物`；192.168.0.1 与 AI 服务流量都经已有的 `192.168.0.0/24 via 10.21.31.103` 路由 + 新 FORWARD 规则出 p2p0。
3. **GOS 时钟修复**（沿用 196 的已验证方案）：
   `/etc/chrony/chrony.conf` 设 `makestep 1 -1` → `systemctl restart chrony` → 待 sources 上线后 `chronyc makestep` → `hwclock --systohc` 固化 RTC。

## 依据

- AOS→AI 服务 200/45 ms 实测（2026-10-15），证明"GOS→AOS→p2p0→公网"链路可用；MASQUERADE 规则已覆盖 GOS 源地址。
- 192.168.0.1 是 AOS 当前在用的解析器（resolvectl 实证），且 GOS 到 192.168.0.0/24 的路由早在 2026-10-14 就已建好并持久化（`m20-pc-route.service`）。
- 8.8.8.8 从 AOS UDP 53 都超时，保留它没有任何意义；换成实测可用的 192.168.0.1。
- chrony `sources=0` 是 DNS 不通的次生结果；DNS 修好后 pool 自动解析，无需手配 NTP 服务器。

## 后果

### 正面

- 一处路由修改同时治好三个症状：AI 服务可达、DNS 可解析、chrony 可同步（时钟归位）。
- 不新增监听端口、不在 AOS 装任何软件；对机器人业务零影响（GOS 本就无出口可用）。

### 负面 / 代价

- **GOS 的全部公网依赖收拢到 AOS 的 WiFi STA（p2p0）**：AOS 重启后若 iptables 规则丢失（已 netfilter-persistent 持久化）或腾达断网，GOS 立即失去出口。`doctor` 的 `ai_health`/`clock` 两项会 FAIL 报警。
- **DNS 依赖腾达路由器 192.168.0.1**：换路由器/改 LAN 口配置会导致解析失败。缓解：可后续在 resolved.conf 加备用解析器（如 223.5.5.5，需先验证可达）。
- 时钟修好后若 RTC 电池/晶振异常仍可能慢，`hwclock --systohc` 只固化当下，长期靠 chrony 持续校正。

### 触发复审的条件

1. 腾达更换或 192.168.0.1 不再提供 DNS → 换解析器并重测。
2. AOS 的 p2p0 STA 频繁掉线 → 评估给 GOS 争取独立出口（厂商侧申请）或迁部署位到 227。
3. 厂商修复 10.21.31.99 网关 → 评估切回默认网关，移除本 ADR 的临时措施。
