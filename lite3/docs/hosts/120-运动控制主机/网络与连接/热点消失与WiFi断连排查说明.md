# 120主机 热点消失 + 已连接WiFi断连 排查说明

| 项目 | 内容 |
| --- | --- |
| 适用对象 | 现场运维人员 |
| 故障主机 | 120 运动控制主机（hostname `ysc`） |
| 主机地址 | `192.168.1.120`（eth1）/ `192.168.0.197`（wlan0）/ `192.168.137.120`（eth1） |
| 文档性质 | 可直接下发现场执行 |
| 编写依据 | 2026-09-23 对 120 主机实测采集（非文档推断） |

> **执行约定**：文中所有命令均需在 120 主机上执行。涉及 `/var/log/` 下日志读取、NetworkManager 操作的命令需要 `sudo`，请以现场授权方式提权。

---

## 1. 故障现象

### 1.1 现象描述

120 主机在正常带电运行过程中，无明显操作触发，出现以下**同时发生**的异常：

| 序号 | 现象 | 具体表现 |
| --- | --- | --- |
| P1 | **自身热点信息消失** | 主机对外广播的无线热点（SSID）从周边设备的 WiFi 列表中消失；已接入热点的客户端被踢出；`p2p0` 接口上的 AP 功能失效 |
| P2 | **已连接 WiFi 断开** | 主机作为客户端（Station）上联的路由器 WiFi 同时断开；`wlan0` 失去关联，上联网络中断 |
| P3 | **并发性** | P1 与 P2 **同时出现**，不是先后独立事件 |
| P4 | **唯一恢复手段是重启** | 现场尝试"重新开启热点""重新连接 WiFi"均无效，**只有重启主机**才能同时恢复两者 |

### 1.2 现象的关键特征（定位方向）

- **P1+P2 同时失效且必须重启才能恢复** —— 这是本次故障最重要的线索。
  两个逻辑上独立的网络功能（AP 热点 / STA 上网）同时死亡，且软件层重开无效，
  强烈指向 **同一块物理无线芯片的底层状态机崩溃**（而非单个服务异常）。
- 因为软件层重开无效 → 说明故障点在 NetworkManager 之下，位于驱动 / 固件 / 硬件层。

---

## 2. 现场已确认的环境基线（2026-09-23 实测）

以下内容为实测采集，作为后续所有分析与验证的基准。**如现场与此不符，请先以现场为准并回填第 6 节。**

### 2.1 硬件与系统

| 项目 | 实测值 |
| --- | --- |
| SoC 平台 | Rockchip RK3588（aarch64） |
| 操作系统 | Ubuntu 20.04.6 LTS |
| 内核 | `5.10.198` |
| CPU / 内存 | 8 核 / 3.8 GiB（**Swap = 0**） |
| 磁盘 | 28 GiB，已用 15 GiB（56%） |
| 无线网卡 | **Realtek RTL8822CE 802.11ac PCIe**（`0002:21:00.0`） |
| 蓝牙 | Realtek `0bda:c822`（与 WiFi 同芯片，USB 总线） |
| 系统温度 | 约 44 ℃（正常范围） |

### 2.2 无线驱动（关键）

| 项目 | 实测值 |
| --- | --- |
| 内核驱动名 | `rtl88x2ce` |
| 已加载模块 | `8822ce`（约 3.1 MB 单体模块） |
| 驱动版本 | `5.14.0.3-23-gb2fec2a9d.20230207`（**2023-02 的厂商 out-of-tree 驱动**） |
| HALMAC 固件版本 | `1.6.6.26` |
| 启动固定报错 | `RTW: ERROR [HALMAC][ERR]Dump efuse in suspend` |

> ⚠️ 该驱动为 **Realtek 厂商提供的树外（out-of-tree）驱动**，非内核主线 `rtw88`。
> 此类驱动的已知共性问题是并发模式不稳定、模块无法干净卸载（`rmmod` 常失败或卡死），
> **这直接解释了"为什么只有重启才能恢复"**。

### 2.3 无线接口与运行状态（关键）

120 主机**只有一块无线芯片**（`phy#0`），却同时承担两个角色：

| 接口 | 角色 | 类型 | 当前运行信道 | IP |
| --- | --- | --- | --- | --- |
| `wlan0` | 上联网卡（Station） | managed | **`channel 13`（2472 MHz，2.4 GHz）** | `192.168.0.197/24` |
| `p2p0` | 对外热点（AP） | **AP** | **`channel 13`（2472 MHz，2.4 GHz）** | `192.168.2.1/24` |

- 上联 SSID：`Tenda_FCFA20`，信号 `-40 dBm`（良好）
- 热点连接配置：`myap50G`，SSID `YSC-JYML-aw3bal-5G`，AP 网段 `192.168.2.0/24`
- 热点由 **NetworkManager 内置共享** 提供（伴随 `dnsmasq` 监听 `192.168.2.1`），**非独立 hostapd**
- 网络管理服务：NetworkManager `1.22.10` + `wpa_supplicant` + `dnsmasq`

### 2.4 🔴 已确认的配置冲突（重要发现）

热点配置文件 `myap50G` 中的设置与**实际运行状态不一致**：

| 配置项 | 期望值（配置里写的） | 实际运行值 | 结论 |
| --- | --- | --- | --- |
| `802-11-wireless.band` | `a`（5 GHz） | **2.4 GHz** | ❌ 未生效 |
| `802-11-wireless.channel` | `36`（5 GHz 信道） | **13**（2472 MHz） | ❌ 未生效 |

日志中可直接看到 AP 被强制跟随 Station 切信道：

```
wlan0: CTRL-EVENT-STARTED-CHANNEL-SWITCH freq=2472 ... cf1=2472
p2p0:  CTRL-EVENT-CHANNEL-SWITCH       freq=2472 ... cf1=2472   ← AP 被强行拖到 2.4G
```

**结论**：运维以为是"5G 热点"（配置名 `myap50G`、SSID 带 `-5G` 后缀），
但**实际因为并发模式限制被压在 2.4 GHz 信道 13 上**。这是一个已被证实的配置与事实偏差。

### 2.5 其他已确认事实

| 项目 | 状态 | 影响 |
| --- | --- | --- |
| `wlan0` 省电模式 | **Power save: on** | ⚠️ 省电会导致漏收 beacon，是无线断连的常见诱因 |
| `p2p0` 省电模式 | Power save: off | 正常 |
| Swap | **0（未配置）** | ⚠️ 3.8 GiB 内存无交换，内存紧张时无缓冲 |
| OOM 记录 | 未发现 `oom-kill` | 暂不支持"内存耗尽"假设 |
| 主机温度 | 44 ℃ | 暂不支持"过热"假设 |
| 重启频次 | 9/19–9/23 约 **20 次重启** | 与"重启才能恢复"高度吻合 |

---

## 3. 可能原因分析

> 图例：**【已证实】**= 有本次实测证据支撑；**【待验证假设】**= 符合机理但尚未取得直接证据，需现场复现确认。

### 3.1 硬件维度

| 编号 | 原因 | 典型特征 | 判断依据 | 结论 |
| --- | --- | --- | --- | --- |
| H1 | RTL8822CE 芯片本体不稳定 / 虚焊 / 接触不良 | 故障随**震动、移动、温差**出现；静置不复发 | 机器人行走/颠簸时高发，静置时从不发生 → 指向硬件 | **【待验证假设】** |
| H2 | PCIe 链路异常（AER 报错、链路降速） | 日志出现 `pcie` / `AER` / `link down` | `dmesg \| grep -i "pcie\|AER"` | **【待验证假设】** |
| H3 | 天线脱落 / 馈线松动 | 信号强度突然大幅下降（如 -40 dBm → -85 dBm） | 对比故障前后 `iw dev wlan0 link` 的 signal | **【待验证假设】** |

> H1 对"机器狗"这类运动平台尤其值得重视：RK3588 板卡上的 M.2/PCIe 无线模块在长期震动下
> 接触不良是典型故障模式。请重点回填第 6 节"是否与运动相关"。

### 3.2 驱动 / 固件维度（★ 最高优先级）

| 编号 | 原因 | 典型特征 | 判断依据 | 结论 |
| --- | --- | --- | --- | --- |
| D1 | 厂商 out-of-tree 驱动 `rtl88x2ce` v5.14.0.3（2023-02）自身缺陷 | 驱动状态机卡死；**软件层重启网络无效，必须重启机器** | 已确认使用该老版本驱动；故障表现（P4）完全吻合 | **【已证实：构成 P4 的必要条件】** |
| D2 | 驱动模块无法干净卸载，导致无法只重启无线 | `rmmod 8822ce` 报错或卡死 | 现场实测 `modprobe -r 8822ce` 是否成功 | **【待验证假设】** |
| D3 | HALMAC 固件报错：`[HALMAC][ERR]Dump efuse in suspend` | 每次开机固定出现 | 已实测到，各次启动均有 | **【已证实：存在该报错】**（是否与断连构成因果待验证） |
| D4 | 驱动 hw port 互换导致接口互踢 | 日志出现 `wlan0 - hw_port : 0,will switch to port-1` | 已实测到该记录 | **【已证实：存在该行为】** |
| D5 | 驱动能力缺失：`ERROR Don't support dynamic SMPS` | 反复打印，伴随时延抖动 | 已实测到大量该记录 | **【已证实：存在该报错】** |
| D6 | 固件版本过旧（HALMAC 1.6.6.26） | 与驱动版本不匹配 | 需厂商确认配套固件版本 | **【待验证假设】** |

### 3.3 系统网络服务维度

| 编号 | 原因 | 典型特征 | 判断依据 | 结论 |
| --- | --- | --- | --- | --- |
| S1 | NetworkManager 1.22.10 自身缺陷 | NM 进程崩溃重启；日志有 `NetworkManager` 重启记录 | 检查 NM 进程 PID 是否变化、是否有 core | **【待验证假设】** |
| S2 | `wpa_supplicant` 异常退出或僵死 | 日志有 supplicant 退出；接口失去认证 | `grep wpa_supplicant /var/log/syslog` | **【待验证假设】** |
| S3 | `dnsmasq` 挂掉导致热点"看起来消失" | **AP 仍在广播，但客户端拿不到 IP** | 现场观察：设备能否搜到 SSID（能搜到 → 是 S3 不是 P1） | **【待验证假设：重要，需与 P1 区分】** |
| S4 | 无看门狗自愈机制，异常后无人拉起 | 故障后一直坏着，直到人工重启 | `/etc/cron.d` 无相关任务 | **【已证实：无自愈机制】** |

> 区分 S3 与 D1 对现场很关键：
> - **能搜到 SSID 但连不上** → 多半是 `dnsmasq` / DHCP 问题（S3），软件层可修，无需重启。
> - **完全搜不到 SSID** → 物理层已死，指向驱动/硬件（D1/H1）。

### 3.4 资源占用维度

| 编号 | 原因 | 典型特征 | 判断依据 | 结论 |
| --- | --- | --- | --- | --- |
| R1 | 内存不足触发异常（**无 Swap 放大风险**） | 故障前有内存吃紧；`oom-kill` 记录 | 已实测：**无 OOM 记录**、可用内存 3.0 GiB | **【暂不支持，待故障时刻数据确认】** |
| R2 | CPU 长时间饱和导致 beacon 发送延迟 | 故障前负载持续高位 | 采集 `load average` 与中断统计 | **【待验证假设】** |
| R3 | 中断风暴 / 软中断集中在单核 | 某核 `si` 异常高 | `mpstat -P ALL 1` | **【待验证假设】** |

### 3.5 信道与配置冲突维度（★ 高优先级）

| 编号 | 原因 | 典型特征 | 判断依据 | 结论 |
| --- | --- | --- | --- | --- |
| C1 | **单射频并发 AP+STA，AP 信道被 STA 强制绑定** | 改热点信道不生效；STA 一断，AP 跟着遭殃 | `iw dev` 显示 wlan0/p2p0 同属 `phy#0` 且同信道；日志有 `p2p0: CTRL-EVENT-CHANNEL-SWITCH` | **【已证实】** |
| C2 | **配置为 5G/ch36，实际跑 2.4G/ch13** | 现场以为是 5G 热点，实测跑在 2.4G | 配置 `band=a, channel=36` vs 实测 `channel 13` | **【已证实：配置与实际不符】** |
| C3 | 2.4 GHz 信道拥挤 / 同频干扰导致 AP 停摆 | 2.4G 环境 AP 多、蓝牙与 WiFi 同芯片互扰 | 现场扫描周边 AP 数量与信道占用 | **【待验证假设：值得重视】** |
| C4 | `wlan0` 省电模式开启 | 长时间后漏收 beacon 被 AP 踢下线 | `iw wlan0 get power_save` = **on** | **【已证实：省电已开启】** |
| C5 | 上联路由器踢设备 / DHCP 租约异常 | 只有上网断，热点正常 | 与本次"两者同时断"不符 | **【不支持】** |

> **C1+C2 的组合机理**（本次故障最可能的软件层诱因）：
> 一块 RTL8822CE 同时做 AP 和 STA，**物理上只能工作在一个信道**。
> Station（`wlan0`）连上 2.4G 的 `Tenda_FCFA20` 后，AP（`p2p0`）被强制拖到同一信道 13。
> 一旦上联 WiFi 因省电/干扰发生重连或漫游，就会触发**整块芯片的信道切换**，
> 在 `rtl88x2ce` 这类老驱动上极易卡死，表现为 **AP 与 STA 同时全灭**，且软件层无法恢复。

### 3.6 供电与环境维度

| 编号 | 原因 | 典型特征 | 判断依据 | 结论 |
| --- | --- | --- | --- | --- |
| E1 | 电池供电跌落导致 PCIe 无线模块掉电 | 故障集中在低电量 / 大电流动作（急停、起跳）时 | 记录故障时刻电量与动作 | **【待验证假设：运动平台需重点关注】** |
| E2 | 过热降频 / 保护 | 温度 > 80 ℃ | 实测 44 ℃ | **【暂不支持】** |
| E3 | 强电磁干扰（电机、电调） | 电机高负载时高发 | 记录故障与电机负载的关联 | **【待验证假设】** |

### 3.7 原因优先级汇总

| 优先级 | 编号 | 一句话结论 |
| --- | --- | --- |
| ★★★ | D1 + C1 + C2 | 老版本厂商驱动 + 单射频并发 AP/STA + 信道被强制绑定 → 最可能根因 |
| ★★★ | C4 | `wlan0` 省电开启，是断连的明确诱因 |
| ★★ | H1 / E1 | 运动平台的硬件接触与供电跌落，需现场回填 |
| ★★ | S3 | 需先排除"其实是 DHCP 挂了"这一伪热点消失 |
| ★ | D3/D5、S1/S2、R1/R2、C3、E2/E3 | 次要或尚无证据，保持观察 |

---

## 4. 日志排查方法

### 4.1 ⚠️ 首要前提：本机重启会丢失 journal 日志（已确认）

**这是本次排查最大的坑，务必先处理。**

| 检查项 | 实测结果 |
| --- | --- |
| `/var/log/journal` 目录 | **不存在** |
| journald `Storage` 配置 | 未显式配置 → 默认 `auto` → 因目录不存在而退化为 **volatile（`/run/log/journal`，内存盘）** |
| 后果 | **`journalctl` 的内容在每次重启后全部清空** |
| 恶性循环 | 故障 → **重启恢复** → 现场证据被重启本身销毁 → 永远查不到 |

**可用的历史证据只剩 rsyslog 落盘的这批文件**（实测存在且跨重启保留）：

```
/var/log/syslog      ← 综合日志（最关键）
/var/log/syslog.1 … .7.gz
/var/log/kern.log    ← 内核日志（无线驱动 RTW 报错在此）
/var/log/kern.log.1 … .2.gz
/var/log/dmesg, dmesg.0 … .4.gz
/var/log/auth.log
```

> **权限提醒（已实测）**：`ysc` 用户**不在 `adm` 组**，直接 `cat /var/log/syslog` 会被拒绝（权限 `640 root:adm`）。
> 现场必须用 `sudo` 读取，或把 `ysc` 加入 `adm` 组（见 4.6.5）。

### 4.2 应采集的信息清单

| 类别 | 内容 | 用途 |
| --- | --- | --- |
| ① 故障时间点 | 精确到分钟的发生时刻（现场记录） | 一切比对的时间锚点 |
| ② 系统日志 | `/var/log/syslog*` | NM、wpa_supplicant、dnsmasq 行为 |
| ③ 内核日志 | `/var/log/kern.log*`、`dmesg*` | 驱动 `RTW` 报错、PCIe、OOM |
| ④ 无线状态 | `iw dev` / `iw link` / `nmcli` 输出 | 信道、角色、连接质量 |
| ⑤ 服务状态 | `systemctl status NetworkManager`、`ss -tlnp` | 服务存活 |
| ⑥ 资源快照 | `free` / `uptime` / 温度 / 电量 | 排除资源与供电 |
| ⑦ 周边无线环境 | `iw dev wlan0 scan` 的信道占用 | 判断干扰 |

### 4.3 采集步骤

> **强烈建议：先按 4.6 打开滚动日志，再等下一次复现。** 否则重启后依旧无据可查。

#### 步骤 1：锁定故障时间点

```bash
# 查看重启历史，确认"重启恢复"发生的时间
sudo last -x reboot | head -20
```

每一次重启记录，通常就对应一次故障发生。**重启时刻往前推 5～30 分钟**就是重点排查窗口。

#### 步骤 2：提取无线相关日志（跨重启，含已轮转的 .gz）

```bash
# 内核驱动层（RTW 报错、deauth、硬件错误）
sudo zgrep -ahE "RTW|rtl88|8822ce|wlan0|p2p0|cfg80211|mac80211" \
     /var/log/kern.log /var/log/kern.log.1 /var/log/kern.log.2.gz | tail -100

# 认证与断链层（wpa_supplicant / NetworkManager）
sudo zgrep -ahE "wpa_supplicant|NetworkManager|dnsmasq" \
     /var/log/syslog /var/log/syslog.1 /var/log/syslog.2.gz | tail -100
```

> `zgrep` 可同时读明文与 `.gz`；`-a` 避免二进制匹配提示；`-h` 去掉文件名前缀便于排序。

#### 步骤 3：导出当前无线状态快照

```bash
{
  echo "===== $(date '+%F %T') ====="
  echo "--- iw dev ---";        sudo iw dev
  echo "--- wlan0 link ---";    sudo iw dev wlan0 link
  echo "--- p2p0 info ---";     sudo iw dev p2p0 info
  echo "--- nmcli device ---";  sudo nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev status
  echo "--- power save ---";    sudo iw wlan0 get power_save; sudo iw p2p0 get power_save
  echo "--- resource ---";      free -h; uptime
  echo "--- AP 客户端 ---";      sudo iw dev p2p0 station dump
} 2>&1 | tee /home/ysc/wifi_snapshot_$(date '+%m%d_%H%M').txt
```

#### 步骤 4：服务与资源核查

```bash
sudo systemctl status NetworkManager --no-pager -l
sudo ss -tlnp | grep -E ":53|:67|:68"      # dnsmasq 是否还在监听
sudo zgrep -aiE "oom-kill|out of memory" /var/log/syslog /var/log/syslog.1
for f in /sys/class/thermal/thermal_zone*/temp; do echo "$f $(cat $f)"; done
```

### 4.4 关键过滤关键字表

| 关键字（正则） | 含义 | 出现即说明什么 |
| --- | --- | --- |
| `RTW: ERROR` | Realtek 驱动报错 | 驱动内部异常 |
| `HALMAC][ERR` | 固件/HALMAC 层错误 | 固件或硬件状态异常（本机开机必现） |
| `Dump efuse in suspend` | efuse 读取失败 | 硬件信息读取异常（本机开机必现） |
| `Don't support dynamic SMPS` | 驱动能力缺失 | 一般非致命，但频繁出现说明驱动老旧 |
| `OnDeAuth(p2p0)` | **AP 侧有客户端被去认证** | 客户端被踢，热点不稳定 |
| `AP-STA-DISCONNECTED` | AP 上客户端断连 | 同上 |
| `CTRL-EVENT-CHANNEL-SWITCH` | **发生信道切换** | ★ 并发模式信道被强拖的直接证据 |
| `CTRL-EVENT-STARTED-CHANNEL-SWITCH` | Station 主动切信道 | 触发源，通常来自 wlan0 |
| `CTRL-EVENT-DISCONNECTED` | Station 断连 | 上联 WiFi 掉了 |
| `beacon loss` | 收不到信标帧 | 干扰 / 距离 / 省电导致 |
| `reason=1` | 去认证原因"未指定" | 本机大量出现，多为驱动/资源问题而非主动踢人 |
| `reason=3` | Deauth：发送方正在离开 | 对端 AP 主动断开 |
| `reason=4` | Deauth：不活动超时 | 省电/空闲被踢，与 C4 相关 |
| `hw port.*switch to port` | 驱动 hw port 互换 | ★ 并发模式内部端口切换，风险点 |
| `fw_state=` | 固件状态字 | 状态异常时可对照 |
| `oom-kill` / `Out of memory` | 内存耗尽杀进程 | 资源类原因 |
| `pcie` / `AER` / `link down` | PCIe 链路错误 | 硬件连接类（H2） |

### 4.5 时间点比对与定位思路

**核心方法：以"重启时刻"为锚点，向前回溯。**

1. **取锚点**：`sudo last -x reboot` 得到重启时间 `T`（通常 = 故障后人工重启的时刻）。
2. **开窗**：重点查看 `T-30min ~ T` 区间的日志。
3. **找第一条异常**：在该窗口内按时间正序找**最先出现**的 `RTW: ERROR` / `CTRL-EVENT-DISCONNECTED` / `CHANNEL-SWITCH`。
4. **判定因果链**（对照下表）：

| 首先出现的现象 | 指向原因 | 结论编号 |
| --- | --- | --- |
| `wlan0 CTRL-EVENT-DISCONNECTED` → 随后 `p2p0 CHANNEL-SWITCH` → AP 消失 | Station 先断，拖垮 AP | C1 / C4 / D1 |
| `p2p0` deauth 风暴 → 随后 wlan0 也断 | AP 侧先崩 | D1 / S3 / C3 |
| 两者**同一秒**同时消失，无任何前置事件 | 芯片/驱动整体掉线 | D1 / H1 / E1 |
| `PCIE`/`AER` 报错后两者同时消失 | 硬件链路掉线 | H1 / H2 / E1 |
| 只有 `dnsmasq` 退出，AP 仍在广播 | DHCP 挂了（伪故障） | S3 |

5. **交叉验证**：把日志时刻与现场记录（是否在行走、电量、是否有大电流动作）对比，验证 H1/E1/E3。

### 4.6 滚动保存日志方案（★ 强烈建议立即部署）

> 目标：**让下一次故障在重启后依然可查**，并自动留存故障前后证据。

#### 4.6.1 开启 journald 持久化（根治"重启丢日志"）

```bash
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo systemctl restart systemd-journald
```

随后写入配置（建议用 drop-in，不改动主配置文件）：

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/10-persistent.conf >/dev/null <<'EOF'
[Journal]
Storage=persistent
Compress=yes
SystemMaxUse=1G
SystemKeepFree=2G
MaxRetentionSec=30day
RateLimitIntervalSec=0
RateLimitBurst=0
EOF
sudo systemctl restart systemd-journald
```

**验证：**

```bash
# 应能列出多次启动（不再是 "No journal files"）
sudo journalctl --list-boots
# Storage 应为 persistent
sudo journalctl --header 2>/dev/null | head -3
ls -ld /var/log/journal
```

> `RateLimitIntervalSec=0` 很重要：默认速率限制会在驱动疯狂刷 `RTW: ERROR` 时**丢弃最关键的报错**。

#### 4.6.2 部署无线状态巡检 + 断连自动抓证（看门狗）

每分钟采样一次无线状态；一旦检测到 AP 或 STA 异常，立即把前后证据写入独立日志文件。

创建脚本 `/usr/local/sbin/wifi_watchdog.sh`：

```bash
#!/bin/bash
# 120主机 无线状态巡检与断连抓证
LOGDIR=/var/log/wifi_watchdog
mkdir -p "$LOGDIR"
LOG="$LOGDIR/wifi_watch.log"
TS=$(date '+%F %T')

AP_IF=p2p0
STA_IF=wlan0

# --- 状态采集 ---
ap_state=$(iw dev "$AP_IF" info 2>/dev/null | awk '/type AP/{print "AP_UP"}')
ap_chan=$(iw dev "$AP_IF" info 2>/dev/null | grep -oE 'channel [0-9]+' | head -1)
sta_link=$(iw dev "$STA_IF" link 2>/dev/null | grep -c 'Connected to')
ap_sta_num=$(iw dev "$AP_IF" station dump 2>/dev/null | grep -c '^Station')

echo "$TS ap=${ap_state:-AP_DOWN} ${ap_chan} ap_clients=$ap_sta_num sta_connected=$sta_link \
mem_avail=$(awk '/MemAvailable/{printf "%dMiB",$2/1024}' /proc/meminfo) \
load=$(cut -d' ' -f1 /proc/loadavg) \
temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)" >> "$LOG"

# --- 异常判定：AP 消失 或 STA 断连 ---
if [ -z "$ap_state" ] || [ "$sta_link" -eq 0 ]; then
    INC="$LOGDIR/incident_$(date '+%Y%m%d_%H%M%S').log"
    {
        echo "===== 无线异常事件 $TS ====="
        echo "ap_state=${ap_state:-AP_DOWN} sta_connected=$sta_link"
        echo "--- iw dev ---";        iw dev
        echo "--- iw link ---";       iw dev "$STA_IF" link
        echo "--- nmcli dev ---";     nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev status
        echo "--- 近10分钟内核日志 ---"; journalctl -k --since "10 min ago" --no-pager 2>/dev/null | grep -iE "RTW|HALMAC|8822ce|wlan0|p2p0" | tail -40
        echo "--- 近10分钟系统日志 ---"; journalctl --since "10 min ago" --no-pager 2>/dev/null | grep -iE "wpa_supplicant|NetworkManager|dnsmasq" | tail -40
        echo "--- 资源 ---";           free -h; uptime
        echo "--- dnsmasq ---";        ps aux | grep -E "[d]nsmasq"
    } >> "$INC" 2>&1
    logger -t wifi_watchdog "WIFI_INCIDENT captured: $INC"
fi
```

部署：

```bash
sudo install -m 755 /dev/stdin /usr/local/sbin/wifi_watchdog.sh < /path/to/wifi_watchdog.sh   # 或先 scp 上去
sudo chmod +x /usr/local/sbin/wifi_watchdog.sh
sudo bash -n /usr/local/sbin/wifi_watchdog.sh   # 语法检查，无输出即通过
```

配套 systemd timer（比 cron 更可靠，重启后自动恢复）：

```bash
sudo tee /etc/systemd/system/wifi-watchdog.service >/dev/null <<'EOF'
[Unit]
Description=WiFi watchdog sample
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/wifi_watchdog.sh
EOF

sudo tee /etc/systemd/system/wifi-watchdog.timer >/dev/null <<'EOF'
[Unit]
Description=Run WiFi watchdog every minute
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Persistent=true
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now wifi-watchdog.timer
```

**验证：**

```bash
systemctl status wifi-watchdog.timer --no-pager
sleep 70
sudo tail -5 /var/log/wifi_watchdog/wifi_watch.log
```

#### 4.6.3 配置日志轮转（防止撑满 28G 磁盘）

```bash
sudo tee /etc/logrotate.d/wifi_watchdog >/dev/null <<'EOF'
/var/log/wifi_watchdog/wifi_watch.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
sudo logrotate -d /etc/logrotate.d/wifi_watchdog   # 干跑校验
```

> **注意：只让 logrotate 管 `wifi_watch.log` 这一个文件，不要写 `*.log`。**
> `incident_*.log` 是动态新增的（每次故障一个），若被 logrotate 的 glob 命中，
> 每个文件都会各自产生 `.1.gz` ~ `.14.gz` 副本，文件数量成倍膨胀。
> **incident 文件由脚本自身清理**（见下节）。

同时确认 rsyslog 的轮转保留足够长：

```bash
grep -E "rotate|daily|weekly" /etc/logrotate.d/rsyslog
```

建议将 `rotate` 提高到 `14` 以上，确保能覆盖两周内的故障。

#### 4.6.4 看门狗日志的滚动与体积控制（脚本内置）

`wifi_watchdog.sh` 自身带**三重体积保护**，无需额外配置即可防止撑满磁盘
（120 主机根分区仅 28 GiB，已用 56%，此项必须保证）：

| 层级 | 机制 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 1 | 主日志按大小轮转 | 10 MB → gzip | `wifi_watch.log` 超限即归档压缩 |
| 2 | 归档保留期 | 7 天 | 超过 7 天的 `.gz` 自动删除 |
| 3 | 目录总量上限 | 50 MB | 超限时从**最旧的** `incident_*` 开始删 |
| 4 | 抓证节流 | 5 分钟 | 持续故障期间**不再每分钟生成新档案**，只往现有档案追加一行 |

> **第 4 条最关键**：早期版本每分钟都会新建一个 `incident_*.log`（每个 15–40 KB）。
> 若热点持续中断一小时就是 60 个文件，一整天可达 1400+ 个、约 50 MB。
> 现在同一故障每 5 分钟才做一次完整抓证，其余只追加状态行，
> **既能看清故障持续时长，又不会产生大量重复档案**。

参数可在脚本头部按需调整：

```bash
RETENTION_DAYS=7          # 归档保留天数
INCIDENT_COOLDOWN=300     # 完整抓证间隔（秒）
MAX_DIR_MB=50             # 目录体积上限（MB）
LOG_ROTATE_BYTES=10485760 # 主日志轮转阈值（字节）
```

**验证：**

```bash
# 查看当前占用
du -sh /var/log/wifi_watchdog
ls -1 /var/log/wifi_watchdog | wc -l

# 人为压测：临时把阈值调小后连续运行，观察是否触发轮转与清理
sudo logrotate -f /etc/logrotate.d/wifi_watchdog
du -sh /var/log/wifi_watchdog
```

#### 4.6.5 让运维账号可直接读日志（免 sudo）

```bash
sudo usermod -aG adm ysc
# 重新登录后生效
```

#### 4.6.6 滚动保存方案验收标准

| 验收项 | 标准 |
| --- | --- |
| `journalctl --list-boots` | 能列出 **多次**启动记录 |
| 重启一次后老日志仍在 | `journalctl -b -1` 可读取上一次启动日志 |
| `wifi_watch.log` | 每分钟新增一行 |
| 人为触发断连 | 自动生成 `incident_*.log` 且内容完整 |
| 磁盘占用 | `/var/log` 总量稳定不持续增长 |

---

## 5. 解决方案

> 图例：**【临时】**= 快速恢复业务；**【根治】**= 消除根因。

### 5.1 总览

| 原因编号 | 临时恢复手段 | 长期根治方案 |
| --- | --- | --- |
| D1 驱动缺陷 | 重启主机；或尝试重载驱动模块 | 升级/替换驱动；必要时换无线网卡 |
| C1 并发 AP+STA | 重启；临时关掉其中一个角色 | 拆分角色：AP 与 STA 物理分离（双网卡） |
| C2 信道被强绑 | 重启 | 显式固定信道；或改用独立 AP 网卡开 5G |
| C4 省电开启 | 立即关闭省电 | 固化到 NM 配置，重启后仍生效 |
| S3 dnsmasq 挂 | 重启 dnsmasq / 重开热点 | 加自愈看门狗 |
| H1 硬件接触 | 重新插拔/压紧模块 | 更换模块或加固 |
| E1 供电跌落 | 检查电量与供电 | 改善供电/加电容 |
| 无自愈 | — | 部署无线自愈看门狗 |

### 5.2 针对驱动/固件原因（D1~D6）★★★

**【临时】**
1. 重启主机（当前唯一可靠手段）。
2. 可尝试不重启而重载驱动（**成功率不高，因该驱动常无法干净卸载**）：
   ```bash
   sudo nmcli con down myap50G
   sudo nmcli con down Tenda_FCFA20
   sudo modprobe -r 8822ce && sudo modprobe 8822ce
   ```
   > ⚠️ **风险提醒**：`modprobe -r` 可能失败或卡死，且会短暂中断全部网络。
   > 若通过 SSH 远程操作，务必确保有 eth1 有线通道兜底，**否则会把自己锁在机器外面**。
   > 若命令卡住超过 30 秒，不要强行中断，改用重启。

**【根治】**
1. 向 RK3588 板卡/无线模块供应商索取 **RTL8822CE 的更新版驱动与配套固件**，目标版本高于 `5.14.0.3`（2023-02）。
2. 评估切换到内核主线 `rtw88_8822ce` 驱动（主线维护更好、并发模式更稳），需实测验证吞吐与稳定性。
3. 若驱动问题无法解决，**更换为 Linux 支持更好的无线模块**（如 Intel AX200/AX210，主线 `iwlwifi` 驱动成熟，并发模式稳定）。

**验证方法：**
```bash
modinfo 8822ce | grep -E "^version"        # 确认新版本
sudo dmesg | grep -iE "RTW|HALMAC"         # 开机报错是否减少/消失
sudo iw dev                                 # 两接口均正常
```

### 5.3 针对信道与配置冲突（C1、C2）★★★

**【临时】**
1. 重启恢复后，确认两者实际信道：
   ```bash
   sudo iw dev p2p0 info | grep channel
   sudo iw dev wlan0 link | grep freq
   ```
2. 若确需优先保障热点，可临时关闭上联 WiFi（`sudo nmcli con down Tenda_FCFA20`），
   让 AP 独占射频。**这可作为判断依据**：若关掉 STA 后热点再也不消失，即确证 C1。

**【根治】**
1. **方案 A（推荐）：物理拆分角色。** 增加一块独立无线网卡（USB 或第二路 PCIe），
   让 `p2p0` 热点与 `wlan0` 上联各用一块，**彻底消除单射频并发冲突**，
   同时热点可真正跑在 5 GHz 信道 36 上。
2. **方案 B：显式固定信道，消除配置与实际不一致。** 把上联与热点固定在同一 2.4G 信道，
   减少运行时信道切换：
   ```bash
   sudo nmcli con modify Tenda_FCFA20 802-11-wireless.band bg
   sudo nmcli con modify myap50G 802-11-wireless.band bg
   sudo nmcli con modify myap50G 802-11-wireless.channel 13
   sudo nmcli con up myap50G
   ```
   > 注意：并发模式下 AP 信道**仍会被 STA 强制跟随**，此方案只能减少抖动，不能根除。
3. **方案 C：改用独立 hostapd 管理热点**，脱离 NetworkManager 的共享模式，
   便于独立控制信道、开启 beacon 看门狗、单独重启 AP 而不影响 STA。

**验证方法：**
```bash
sudo iw dev p2p0 info | grep channel        # 应等于期望信道
sudo iw dev wlan0 link | grep freq
# 连续观察 24h，确认无 CTRL-EVENT-CHANNEL-SWITCH
sudo zgrep -c "CHANNEL-SWITCH" /var/log/syslog /var/log/syslog.1
```

### 5.4 针对省电模式（C4）★★★

**【临时】立即执行（无需重启）：**
```bash
sudo iw dev wlan0 set power_save off
sudo iw dev p2p0  set power_save off
```

**【根治】固化到 NetworkManager，重启后仍生效：**
```bash
sudo nmcli con modify Tenda_FCFA20 802-11-wireless.powersave 2
sudo nmcli con modify myap50G      802-11-wireless.powersave 2
```

或写入全局配置（对所有无线连接生效）：
```bash
sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf >/dev/null <<'EOF'
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager
```

**验证方法：**
```bash
sudo iw wlan0 get power_save   # 期望 Power save: off
sudo iw p2p0  get power_save   # 期望 Power save: off
```

> 建议此项**立即执行**，风险低、收益明确。

### 5.5 针对网络服务（S1~S4）

**【临时】**
```bash
# 只重启热点（AP 仍在物理层正常时有效）
sudo nmcli con down myap50G && sudo nmcli con up myap50G

# 只重启上联 WiFi
sudo nmcli con down Tenda_FCFA20 && sudo nmcli con up Tenda_FCFA20

# 若只是 DHCP 异常
sudo systemctl restart NetworkManager
```

**【根治】部署自愈看门狗**，在检测到异常时自动恢复，避免长时间失联。

`scripts/wifi_watchdog.sh` **已内置**该自愈逻辑（异常分支中自动执行，无需再手工追加）：

```bash
# 先尝试软件层自愈
nmcli con up "$AP_CON"  >/dev/null 2>&1
nmcli con up "$STA_CON" >/dev/null 2>&1
sleep 15
# 复检：仍异常则标记需人工重启
if [ -z "$(iw dev "$AP_IF" info 2>/dev/null | grep 'type AP')" ] \
   || [ "$(iw dev "$STA_IF" link 2>/dev/null | grep -c 'Connected to')" -eq 0 ]; then
    echo "$TS SOFT_RECOVERY_FAILED 软件层自愈无效，需人工重启" >> "$TARGET"
    logger -t wifi_watchdog "SOFT_RECOVERY_FAILED: 软件层自愈无效，需人工重启"
else
    echo "$TS SOFT_RECOVERY_OK" >> "$TARGET"
    logger -t wifi_watchdog "SOFT_RECOVERY_OK"
fi
```

> **这条日志本身是重要判据**：若每次故障都记录 `SOFT_RECOVERY_FAILED`，
> 说明软件层重开始终无效，反过来印证故障点在**驱动 / 固件 / 硬件层**（D1、H1、E1），
> 而不是 NetworkManager 配置问题。

### 5.6 针对硬件与供电（H1、H2、E1）

**【临时】**
- 检查无线模块是否插紧、天线馈线是否脱落。
- 检查供电电压与电量，避开低电量场景。

**【根治】**
- 对模块做加固（点胶 / 压紧 / 加支撑），或改用板载焊接方案。
- 若确认模块损坏则更换。
- 改善供电，或在无线模块供电端增加储能电容。

**验证方法：**
- 静止放置 24h 与带负载运动 2h 的对照测试：若仅运动场景复发 → 确证 H1/E1。

### 5.7 针对资源（R1、R2）

**【根治】**（建议执行，3.8 GiB 内存且无 Swap 风险偏大）
```bash
# 增加 2GiB 交换文件，降低内存压力
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**验证：** `free -h` 应显示 Swap 2GiB。

### 5.8 修复后的回归确认标准

修复后需**同时满足**以下全部条目，方可判定闭环：

| # | 验收项 | 标准 | 判定命令 |
| --- | --- | --- | --- |
| 1 | 热点持续可见 | 连续 **72 小时**内周边设备可稳定搜到 SSID | 客户端实测 / `iw dev p2p0 info` |
| 2 | 上联 WiFi 稳定 | `wlan0` 72 小时无 `CTRL-EVENT-DISCONNECTED` | `sudo zgrep -c "CTRL-EVENT-DISCONNECTED" /var/log/syslog*` |
| 3 | 无异常信道切换 | `CHANNEL-SWITCH` 计数不增长 | `sudo zgrep -c "CHANNEL-SWITCH" /var/log/syslog*` |
| 4 | 无 deauth 风暴 | `OnDeAuth(p2p0)` 不出现或极少 | `sudo zgrep -c "OnDeAuth" /var/log/kern.log*` |
| 5 | 省电已关闭 | 两接口均为 `Power save: off` | `sudo iw dev <if> get power_save` |
| 6 | 驱动报错收敛 | `RTW: ERROR` 不再大量刷屏 | `sudo dmesg \| grep -c "RTW: ERROR"` |
| 7 | 重启后日志可追溯 | `journalctl --list-boots` 可见多次启动 | 见 4.6.1 |
| 8 | 自愈机制生效 | 人为制造断连后可自动/告警恢复 | 查看 `/var/log/wifi_watchdog/` |
| 9 | 重启次数显著下降 | 对比修复前后 `last -x reboot` | 应明显减少 |
| 10 | 运动场景不复发 | 带负载运动 2 小时无故障 | 现场跑车验证 |

> **放行标准**：第 1、2、5 项必须满足；其余项作为观察指标记录。

---

## 6. 待补充信息清单

请现场确认并回填以下信息，用于收敛根因。**未填项对应的原因只能保持"待验证假设"。**

### 6.1 故障复现特征（最重要）

| # | 需确认项 | 为什么需要 |
| --- | --- | --- |
| 1 | 故障发生的大致频率（每天几次 / 几天一次） | 判断是必现还是偶发 |
| 2 | **是否与机器人运动状态相关**（静止时是否也发生） | ★ 区分 H1/E1（硬件/供电）与 D1/C1（驱动/信道） |
| 3 | 故障时刻是否在充电 / 电量水平 | 验证 E1 |
| 4 | 故障是否有时间规律（如固定运行 N 小时后） | 判断是否资源泄漏或定时器相关 |
| 5 | 最近一次故障的**精确时间点**（年月日时分） | 日志比对的时间锚点 |
| 6 | 故障前是否有其他操作（启停推流、插拔设备、切换网络） | 找触发条件 |

### 6.2 现象细节

| # | 需确认项 | 为什么需要 |
| --- | --- | --- |
| 7 | 热点消失时，手机**能否搜到 SSID** | ★ 区分 S3（DHCP 挂，能搜到）与 D1（物理层死，搜不到） |
| 8 | 热点消失与 WiFi 断连是否**严格同时**（同一秒） | 判因果先后 |
| 9 | 能否用有线 eth1 连上主机（无线全挂时） | 确认是否整机失联 |
| 10 | 故障时 SSH / 串口是否仍可登录 | 决定能否在线取证 |
| 11 | 重启后是否**一定能**恢复，还是偶尔需二次重启 | 判断状态机卡死程度 |

### 6.3 设备与版本

| # | 需确认项 | 当前已知 |
| --- | --- | --- |
| 12 | RK3588 板卡型号与供应商 | 已知为 Rockchip RK3588 |
| 13 | 无线模块是否为原装 / 是否自行更换过 | 未知 |
| 14 | 供应商是否提供更新的 RTL8822CE 驱动与固件 | 未知，需索取 |
| 15 | 设备投入使用时长、是否经历过摔碰 | 未知 |
| 16 | 同批次其他机器（如 103）是否有同样问题 | 未知，用于判断是否批次性问题 |

### 6.4 使用与网络环境

| # | 需确认项 | 为什么需要 |
| --- | --- | --- |
| 17 | 现场 2.4 GHz 环境 AP 数量与信道占用 | 验证 C3 干扰假设 |
| 18 | 上联路由器 `Tenda_FCFA20` 的型号、是否开启 5G | 若上联改 5G，AP 会被拖到 5G，可验证 C1 |
| 19 | 热点主要用途与客户端数量（当前实测 2 个） | 评估负载 |
| 20 | 是否要求热点必须是 5 GHz | 决定方案 A（加网卡）的必要性 |
| 21 | 业务能否接受"热点与上联共用 2.4G" | 决定短期可接受方案 |

### 6.5 已排除 / 已确认汇总（供回填对照）

| 项目 | 结论 |
| --- | --- |
| 内存 OOM | 暂未发现证据 |
| 温度过热 | 暂排除（44 ℃） |
| 磁盘空间 | 暂排除（56% 使用） |
| 并发模式信道强绑 | **已证实存在** |
| 配置 5G 实际跑 2.4G | **已证实存在** |
| wlan0 省电开启 | **已证实存在** |
| 驱动为老版本厂商驱动 | **已证实存在** |
| 重启会丢失 journal 日志 | **已证实存在** |
| 无无线自愈看门狗 | **已证实存在** |

---

## 附录 A：一键采集脚本（现场取证用）

复现故障后**在重启之前**执行，能救回最多证据：

```bash
#!/bin/bash
# /usr/local/sbin/wifi_diag_collect.sh
OUT=/home/ysc/wifi_diag_$(date '+%Y%m%d_%H%M%S')
mkdir -p "$OUT"
{
  echo "===== 采集时间 $(date '+%F %T') ====="
  echo "--- 基础信息 ---"; uname -a; uptime; free -h
  echo "--- 重启历史 ---"; last -x reboot | head -20
  echo "--- iw dev ---";       iw dev
  echo "--- wlan0 link ---";   iw dev wlan0 link
  echo "--- p2p0 info ---";    iw dev p2p0 info
  echo "--- power save ---";   iw wlan0 get power_save; iw p2p0 get power_save
  echo "--- nmcli 连接 ---";    nmcli -t -f NAME,TYPE,DEVICE con show
  echo "--- nmcli 设备 ---";    nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev status
  echo "--- dnsmasq ---";       ps aux | grep -E "[d]nsmasq"
  echo "--- AP 客户端 ---";      iw dev p2p0 station dump
  echo "--- 温度 ---";          for f in /sys/class/thermal/thermal_zone*/temp; do echo "$f $(cat $f)"; done
  echo "--- 驱动模块 ---";       lsmod | grep -iE "8822ce|rtl88"; modinfo 8822ce | grep -E "^version"
} > "$OUT/snapshot.txt" 2>&1

sudo dmesg > "$OUT/dmesg.txt" 2>&1
sudo journalctl -k --since "2 hours ago" --no-pager > "$OUT/journal_kern.txt" 2>&1
sudo journalctl --since "2 hours ago" --no-pager > "$OUT/journal_all.txt" 2>&1

# 关键日志切片
sudo zgrep -ahE "RTW|HALMAC|8822ce|wlan0|p2p0" /var/log/kern.log* > "$OUT/kern_wifi.txt" 2>&1
sudo zgrep -ahE "wpa_supplicant|NetworkManager|dnsmasq" /var/log/syslog* > "$OUT/syslog_net.txt" 2>&1

echo "采集完成：$OUT"
ls -lh "$OUT"
```

**用法：**
```bash
sudo bash /usr/local/sbin/wifi_diag_collect.sh
# 把生成的 /home/ysc/wifi_diag_* 目录打包带回
```

---

## 附录 B：现场速查卡片

| 场景 | 动作 |
| --- | --- |
| 热点消失但**能搜到 SSID** | 多为 dnsmasq/DHCP：`sudo nmcli con down myap50G && sudo nmcli con up myap50G` |
| 热点消失且**搜不到 SSID** | 物理层已死：记录时间 → 执行附录 A 采集 → 再重启 |
| 只有上联 WiFi 断 | 先关省电：`sudo iw dev wlan0 set power_save off`，再重连 |
| 两者同时断 | 按 4.5 定位；**采集完再重启** |
| 远程操作怕失联 | 务必通过 **eth1 有线**（`192.168.1.120`）登录，不要用无线通道操作 |
| 想立刻降低复发概率 | 关省电（5.4）+ 开持久化日志（4.6.1）+ 装看门狗（4.6.2） |
