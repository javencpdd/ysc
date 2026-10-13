# user-f20 网络与 Wi‑Fi 热点分析报告

## 结论

当前热点 `YSC-JYML-aw3bal-5G` 是 **NetworkManager 的 IPv4 shared/NAT 热点**，不是网桥：

```text
热点客户端 192.168.2.x
  -> p2p0 AP (192.168.2.1/24)
  -> NetworkManager dnsmasq + ip_forward + iptables MASQUERADE
  -> wlan0 STA (192.168.0.197/24)
  -> 192.168.0.1 / Tenda_FCFA20_5G / Internet
```

- 热点下行接口是 `p2p0`，上行接口是 `wlan0`。两者是同一 RTL8822CE 无线芯片的虚拟接口，属于 `phy#0`，没有 Linux bridge。
- `p2p0` 的 active profile `myap50G` 使用 `mode=ap` 和 `ipv4.method=shared`；NetworkManager 运行自己的 dnsmasq，并动态写入 DHCP、DNS、FORWARD、NAT 规则。
- IPv4 转发已持久开启；热点网段为 `192.168.2.0/24`，DHCP 实际池为 `192.168.2.10–192.168.2.254`，租期 1 小时。
- 主机目前经 `wlan0 -> 192.168.0.1` 的 metric 10 默认路由上网。这个 metric 10 是运行时临时项；在修正 eth1 的异常默认网关前，不可删除。
- `hostapd.service`、系统级 `dnsmasq.service`、`systemd-networkd` 未参与当前热点；启动它们或建立 bridge 都会破坏现有设计。

> 采集时间：2026-09-05 18:32–18:35（Asia/Shanghai）。  
> 通过 mcp-ssh-apply-patch 仅执行读取：接口、路由、DNS、NetworkManager、日志、iptables、sysctl、配置文件。未修改远端。密钥、客户端 MAC 和其他秘密已脱敏。

## 后续实际变更记录（2026-09-05 19:59）

在本报告初版完成后，操作方按建议从 Netplan 注释了 eth1 的自指 gateway4，并通过 netplan try 应用。该操作重新加载了 NetworkManager，导致 autoconnect=no 的 myap50G 暂时退回 p2p0 disconnected；profile 本身未丢失。随后仅重新激活既有 myap50G profile，热点恢复。

恢复验证结果：p2p0 为 AP、SSID 为 YSC-JYML-aw3bal-5G、地址为 192.168.2.1/24；NetworkManager dnsmasq 已重新监听；FORWARD 和 MASQUERADE 规则已恢复。当前默认路由只剩 wlan0 DHCP 路由：default via 192.168.0.1 dev wlan0 metric 600。eth1 的异常 metric 100 默认路由和临时 wlan0 metric 10 路由都已不存在。

因此，后续应用 Netplan 时必须把“重新激活 autoconnect=no 的热点 profile”视为标准验证/恢复步骤，而不是假定 p2p0 会自动恢复。

## 1. 接口、无线状态与地址

| 接口 | 地址/状态 | 当前职责 |
|---|---|---|
| `wlan0` | UP，`192.168.0.197/24` | 上游 Wi‑Fi STA，连接 `Tenda_FCFA20_5G`。 |
| `p2p0` | UP，`192.168.2.1/24` | AP，广播 `YSC-JYML-aw3bal-5G`。 |
| `eth1` | UP，`192.168.1.120/24`、`192.168.137.120/24` | 有线业务/备用网络。 |
| `eth0` | DOWN | 未使用。 |
| `can0–can4` | CAN | 与 IP 热点无关。 |

无线运行态：

```text
phy#0
  wlan0  type managed  SSID Tenda_FCFA20_5G       channel 44 / 5220 MHz
  p2p0   type AP       SSID YSC-JYML-aw3bal-5G    channel 44 / 5220 MHz
```

`myap50G` profile 保存的首选频道是 36，但实际两个接口都在频道 44。单芯片 AP/STA 并发必须共信道，实际频道受上游 STA 连接约束。强行只改热点频道、断开 wlan0 或更改接口分工，都可能使热点和上行同时失效。

`bridge link` 没有端口，未发现 bridge/VLAN：热点客户端不会取得 `192.168.0.x` 地址，必须经过三层路由与 NAT。

## 2. 路由、网关与 DNS

### 2.1 IPv4 路由

```text
default via 192.168.0.1 dev wlan0 metric 10
default via 192.168.137.120 dev eth1 metric 100
default via 192.168.0.1 dev wlan0 proto dhcp metric 600
192.168.0.0/24   dev wlan0
192.168.1.0/24   dev eth1
192.168.137.0/24 dev eth1
192.168.2.0/24   dev p2p0
```

当前出站优先走 wlan0 metric 10，热点 NAT 因而经 `192.168.0.1` 上网。wlan0 的 DHCP profile 自身路由 metric 为 600；metric 10 是额外运行态修复项。

`/etc/netplan/config.yaml:4-12` 含：

```yaml
eth1:
  addresses: [192.168.1.120/24, 192.168.137.120/24]
  gateway4: 192.168.137.120
  nameservers:
    addresses: [223.5.5.5]
```

eth1 的 gateway4 等于本机 eth1 地址，生成了 metric 100 默认路由，不能视为可用上游。若删除 wlan0 metric 10，内核将优先选择此 metric 100 路由，而不是 wlan0 DHCP metric 600，主机和热点客户端都可能失网。

### 2.2 DNS

- `wlan0` DHCP DNS：`192.168.0.1`，搜索域 `www.tendawifi.com`。
- `eth1` 静态 DNS：`223.5.5.5`。
- `systemd-resolved` active；`/etc/resolv.conf` 由 NetworkManager 生成。
- NetworkManager 设置 `dns=systemd-resolved`。

热点 DNS 链路为：

```text
热点客户端 -> 192.168.2.1:53 (NM 子进程 dnsmasq)
           -> 127.0.0.53 (systemd-resolved)
           -> 当前上游 DNS（优先由 wlan0 / eth1 路由与优先级共同决定）
```

不要直接编辑 `/etc/resolv.conf`，NetworkManager 会覆盖它。若要固定热点 DNS 上游，先修正 eth1 默认路由，再通过 NetworkManager 的 DNS priority/never-default/route metric 调整。

### 2.3 IPv6

wlan0 有上游 IPv6 connectivity，但 `net.ipv6.conf.all.forwarding=0`；本次只验证 IPv4 NAT。热点客户端 IPv6 出网不应视为已配置。

## 3. 热点的真实控制面

### 3.1 NetworkManager profile

权威热点 keyfile：`/etc/NetworkManager/system-connections/myap50G.nmconnection`（0600，root 所有）。

```ini
[connection]
id=myap50G
type=wifi
interface-name=p2p0
autoconnect=false

[wifi]
ssid=YSC-JYML-aw3bal-5G
mode=ap
band=a
channel=36

[wifi-security]
key-mgmt=wpa-psk
psk=<redacted>

[ipv4]
address1=192.168.2.1/24
method=shared
```

上游 keyfile：`/etc/NetworkManager/system-connections/Tenda_FCFA20_5G.nmconnection`：

```ini
[connection]
id=Tenda_FCFA20_5G
interface-name=wlan0
autoconnect=true
[wifi]
mode=infrastructure
ssid=Tenda_FCFA20_5G
[ipv4]
method=auto
```

`interface-name=p2p0`、`mode=ap`、`address1=192.168.2.1/24` 与 `method=shared` 是热点核心配置。将 shared 改成 manual/auto/disabled，或迁移到 wlan0，会失去当前 DHCP/NAT 链路。

### 3.2 DHCP 与 DNS 服务

当前 dnsmasq 不是 `dnsmasq.service`，而是 NetworkManager 派生子进程：

```text
listen-address=192.168.2.1
dhcp-range=192.168.2.10,192.168.2.254,60m
dhcp-lease-max=50
leasefile=/var/lib/NetworkManager/dnsmasq-p2p0.leases
conf-dir=/etc/NetworkManager/dnsmasq-shared.d
```

采集时 lease 文件有 1 条租约；`dnsmasq-shared.d` 为空。`/home/ysc/host/dhcpd2.conf`、`/home/ysc/master/dhcpd.conf` 等旧 dhcpd 文件不被当前进程引用，地址池也不同，不能当成当前 DHCP 配置。

### 3.3 NAT、转发与实际规则

持久转发来源：

```text
/etc/sysctl.conf:28                 net.ipv4.ip_forward=1
/etc/sysctl.d/99-sysctl.conf:28     net.ipv4.ip_forward=1
```

当前使用 `iptables v1.8.4 (legacy)`；`nft` 命令未安装，IPv6 iptables 表也不可用。热点必需的活动规则：

```iptables
-A INPUT -i p2p0 -p udp --dport 67 -j ACCEPT
-A INPUT -i p2p0 -p udp --dport 53 -j ACCEPT
-A FORWARD -s 192.168.2.0/24 -i p2p0 -j ACCEPT
-A FORWARD -d 192.168.2.0/24 -o p2p0 \
  -m state --state RELATED,ESTABLISHED -j ACCEPT
-A POSTROUTING -s 192.168.2.0/24 ! -d 192.168.2.0/24 -j MASQUERADE
```

NetworkManager journal 记录了激活 myap50G 时插入 DHCP/DNS/FORWARD 规则并启动 dnsmasq，且相关规则计数器已增长。这是 NetworkManager shared 的动态规则，不应手工 flush。

另有历史脚本追加的规则：

```iptables
-A POSTROUTING -s 192.168.2.0/24 -o eth1 -j MASQUERADE
-A POSTROUTING -s 192.168.137.0/24 -o wlan0 -j MASQUERADE
```

它们来自 `/home/ysc/host/host_start.sh:15-16`；第一条被通用 shared MASQUERADE 覆盖，第二条服务另一网段。它们可能仍有业务依赖，不能仅因表面冗余而删除。

## 4. 配置来源和启动依赖

```text
/etc/netplan/config.yaml
  -> renderer: NetworkManager
  -> netplan-eth0 / netplan-eth1

/etc/NetworkManager/NetworkManager.conf
  -> plugins=ifupdown,keyfile; dns=systemd-resolved
  -> Tenda_FCFA20_5G.nmconnection -> wlan0 上行
  -> myap50G.nmconnection           -> p2p0 AP/shared
       -> NM dnsmasq + iptables dynamic rules + lease file

/lib/systemd/system/host.service
  -> /home/ysc/host/host_start.sh
     -> 追加两条历史 NAT
     -> /home/ysc/host/ap_start.sh start 5G
     -> 用 nmcli 删除/创建/激活 myap50G
```

`/lib/systemd/system/host.service:1-10`：

```ini
[Unit]
After=network.target
[Service]
Type=simple
ExecStart=/home/ysc/host/host_start.sh
[Install]
WantedBy=network.target
```

host.service 是 enabled 但 inactive，因为它成功执行引导脚本后正常退出；热点随后由 NetworkManager/dnsmasq 常驻。inactive 不表示 AP 已停止。该 unit 无 Restart=，且只 After=network.target，不显式等待 NetworkManager fully ready，因此开机时序失败不会自动重试。

`/home/ysc/host/ap_start.sh:30-39` 通过 nmcli 创建热点；`host_start.sh:15-17` 使用 `iptables -A` 后调用该脚本。重复运行会累加历史 NAT 规则，并删除/重建同名 myap profile，导致热点客户端掉线。

未参与当前热点：

| 服务/配置 | 实际状态 | 结论 |
|---|---|---|
| hostapd.service | disabled / inactive；`/etc/default/hostapd` 指向的配置文件不存在 | 历史安装，不能同 NetworkManager 抢 p2p0。 |
| dnsmasq.service | inactive | 当前 dnsmasq 由 NetworkManager 启动。 |
| systemd-networkd | disabled / inactive | Netplan renderer 是 NetworkManager。 |
| nftables/firewalld | inactive；nft 不存在 | 当前规则仅 iptables legacy。 |

## 5. 热点上网的逐跳逻辑

1. 客户端加入 SSID，从 p2p0 dnsmasq 获得 `192.168.2.10–254/24`、网关 `192.168.2.1`、DNS。
2. DHCP（UDP 67）和 DNS（UDP/TCP 53）由 p2p0 INPUT 规则到达主机。
3. 客户端把外网包交给 `192.168.2.1`。
4. `ip_forward=1` 和 FORWARD 规则允许该流量。
5. 路由按当前 metric 10 选 wlan0，经 `192.168.0.1` 出去。
6. POSTROUTING 的 MASQUERADE 将源 `192.168.2.x` 伪装为当前出口地址（现为 `192.168.0.197`）。
7. 返回流量由 conntrack 匹配为 ESTABLISHED/RELATED，经 p2p0 返回客户端。

## 6. 修改风险边界

| 项目 | 判断 | 原因 |
|---|---|---|
| 导出/读取 profile、规则、日志 | 安全 | 只读。 |
| 在 dnsmasq-shared.d 增加非冲突 DNS 选项 | 有条件 | 错误选项可致 dnsmasq/DHCP 启动失败；需备份和维护窗口。 |
| 修改 SSID / WPA 密钥 | 有条件 | 需重新激活 AP，客户端必掉线后重连。 |
| 改热点子网/DHCP 范围 | 高风险 | 同步影响 profile、客户端静态配置、机器人配置、历史 NAT。 |
| 修正 eth1 gateway4 | 有条件、建议做 | 可去除异常默认路由；必须先保留 wlan0 有效出口和 OOB 回退。 |
| 调整 wlan0 route metric/DNS priority | 有条件 | 会影响主机和所有热点客户端出口。 |
| 改 p2p0/wlan0 角色、频道、频段 | 高风险 | 单一 phy 的并发 AP/STA 会同时受影响。 |
| p2p0 与 wlan0 建桥 | 禁止 | 当前是 NAT 设计；STA 普通桥接也常不受支持。 |
| 把 ipv4.method 从 shared 改走 | 禁止 | 失去 NM 管理的 DHCP、NAT、转发规则。 |
| 关闭 ip_forward 或 flush iptables | 禁止 | 热点可关联但无法 DHCP/DNS/上网。 |
| 启动 hostapd 或 dnsmasq.service | 禁止 | 会抢无线接口或端口 53/67。 |
| 先删除 wlan0 metric 10 路由 | 禁止 | eth1 metric 100 自指 gateway 会抢占出口。 |
| 直接编辑 /etc/resolv.conf | 无效 | NetworkManager 会重写。 |

## 7. 建议调整方案（不在本次执行）

### A. 优先解决默认路由持久化

目标是维持 wlan0 为热点上行，去除 eth1 的自指 gateway 和临时 metric 10 依赖。

1. 准备串口/本地控制台或热点内备用客户端，不能只依赖 wlan0 SSH。
2. 备份 `/etc/netplan/config.yaml`、两个 active nmconnection keyfile、`/etc/sysctl.conf`、`host_start.sh`，并保存 `ip route`、`resolvectl status`、`iptables-save`、`nmcli connection show` 基线。
3. 确认 eth1 的真实用途：仅本地 LAN 时移除 gateway4；有真实上游时替换为真实网关。
4. 通过 wlan0 的 NetworkManager profile 设置明确且持久的 route metric，再应用 Netplan/NM。
5. 立即检查 `ip route get 1.1.1.1` 仍经 wlan0，然后验证热点客户端。
6. 只有在 eth1 已修正、wlan0 metric 已持久化后，才评估删除临时 metric 10 路由。

### B. 改 SSID 或密码

只改 `myap50G` profile 的无线字段，不动 p2p0、shared、地址或 NAT。维护窗口中备份 keyfile，修改并重新激活同一 profile；随后确认 p2p0 AP、`192.168.2.1/24`、dnsmasq 和客户端 DHCP/DNS/外网。不要为小改动执行旧 `ap_start.sh`，该脚本会删除并重建 profile。

### C. 改子网/DHCP

必须同步审核：

- `myap50G` 的 `ipv4.addresses`；
- 应用/机器人对 `192.168.2.1` 的引用；
- `host_start.sh` 中的历史 NAT 源网段；
- 静态客户端地址、白名单与路由。

只修改历史 `dhcpd.conf` 无效，因为当前 DHCP 是 NetworkManager dnsmasq。应在离线副本规划、无客户端维护窗口、具备本地控制台时完成。

## 8. 验证与回滚

修改前保存：

```bash
nmcli device status
nmcli connection show --active
iw dev
ip -4 address show; ip route
resolvectl status
sysctl net.ipv4.ip_forward
sudo iptables -L -n -v
sudo iptables -t nat -S
```

热点客户端验证：

1. 关联 SSID；
2. 获取 `192.168.2.10–254/24`，网关 `192.168.2.1`；
3. Ping 网关；
4. 经 `192.168.2.1` DNS 查询域名；
5. 访问公网 IP 与 HTTPS 域名。

主机验证：

```bash
nmcli -f GENERAL,IP4 device show p2p0
ps -ef | grep '[d]nsmasq.*p2p0'
sudo iptables -L FORWARD -n -v
sudo iptables -t nat -L POSTROUTING -n -v
ip route get 1.1.1.1
```

FORWARD/NAT 计数器应增长，最后一条应显示 wlan0 有效下一跳。

回滚只恢复本次变更的单个 profile 或 Netplan 文件；禁止全局 flush iptables、删除所有 NetworkManager profile 或盲目重启整机。若上行异常，先恢复 wlan0 已知有效默认路由；若 AP 异常，恢复 myap50G 备份后重新激活。

## 9. 关键证据位置

| 位置 | 作用 |
|---|---|
| `/etc/netplan/config.yaml` | eth0/eth1 来源，renderer 为 NetworkManager。 |
| `/etc/NetworkManager/NetworkManager.conf` | 全局插件与 DNS 控制面。 |
| `/etc/NetworkManager/system-connections/myap50G.nmconnection` | 当前热点权威配置。 |
| `/etc/NetworkManager/system-connections/Tenda_FCFA20_5G.nmconnection` | 当前 wlan0 上行配置。 |
| `/etc/NetworkManager/dnsmasq-shared.d/` | shared dnsmasq 扩展目录，当前为空。 |
| `/var/lib/NetworkManager/dnsmasq-p2p0.leases` | 热点 DHCP 租约。 |
| `/etc/sysctl.conf`、`/etc/sysctl.d/99-sysctl.conf` | IPv4 forwarding 持久来源。 |
| `/lib/systemd/system/host.service` | 开机热点引导。 |
| `/home/ysc/host/host_start.sh` | 历史 NAT 与热点脚本入口。 |
| `/home/ysc/host/ap_start.sh` | 用 nmcli 创建热点；含敏感密钥，勿随意执行。 |
