# M20 机器狗 GPS 获取方式（196 主机实测）

> 实测时间：2026-10-12　主机：`user@192.168.0.196`（`aos`）
> **结论：经纬度现在拿不到 —— 但没有故障，是"没定位"。**
> 两条独立数据源都实测过，一致报告 `FixQuality=0 / NumSatellites=0 / VisibleSatellites=1`。
> 把机器狗放到室外或窗边，等到可见卫星 ≥4 颗，经纬度立刻就有。

---

## 0. 关键结论（两条独立来源互相印证）

| 来源 | 通道 | Latitude | Longitude | FixQuality | 卫星 |
|---|---|---|---|---|---|
| ① 本机 GPS 模块 | `/dev/ttyS5` NMEA → `gps_node` | 0.000000 | 0.000000 | 0 | 0/可见 1 |
| ② 机器狗本体 | M20 直连协议 TCP 30001 | 0.0 | 0.0 | 0 | 0/可见 1 |

两路数值完全一致 —— 说明**是同一个 GNSS 接收机 / 同一颗天线没有定位解**，
不是某一条链路坏了。

**唯一原因是搜不到足够卫星**：实测 NMEA 显示 GPS 0 颗、GLONASS 0 颗、Galileo 0 颗、
北斗 1 颗（信噪比 24）。定位至少要 4 颗。

---

## 1. 实测证据

### 1.1 原始 NMEA（3 秒采样，共 443 字节 / 10 条语句）
```
$GNGGA,002604.690,0000.00000,N,00000.00000,E,0,00,0.000,0.0,M,0.0,M,,*7C   ← 定位质量 0
$GNGLL,0000.00000,N,00000.00000,E,002604.690,V,N*50                        ← 状态 V (Void)
$GNGSA,A,1,,,,,,,,,,,,,0.000,0.000,0.000,1*33                              ← fix type 1 = 无定位
$GPGSV,1,1,0,1*54          ← GPS 卫星 0 颗
$GBGSV,1,1,1,38,,,24,1*4A  ← 北斗 1 颗（信噪比 24）
$GLGSV,1,1,0,1*48          ← GLONASS 0 颗
$GAGSV,1,1,0,7*43          ← Galileo 0 颗
```
多系统（GPS+BDS+GLO+GAL）都开着（`sysMask=0x11111`），模块工作正常。

### 1.2 机器狗本体遥测（M20 直连协议）
```json
{"Latitude":0.0,"Longitude":0.0,"Speed":0.0,"Course":0.0,
 "FixQuality":0,"NumSatellites":0,"Altitude":0.0,
 "HDOP":0.0,"VDOP":0.0,"PDOP":0.0,"VisibleSatellites":1}
```

### 1.3 gps_node 日志（`/var/opt/robot/log/*/gps_node.*.log`）
```
从串口读取数据长度 441 ~ 443        ← 每 100ms 一帧，链路健康
系统模式: GA
纬度: 0.000000°   经度: 0.000000°
定位质量: 0       卫星数量: 0      可见卫星总数: 1
--------------recv:4549-error:0,占比0.000000------------   ← 解析零错误
```

### 1.4 环境
| 项 | 值 |
|---|---|
| 串口 | `/dev/ttyS5` @ **115200** |
| 持有者 | `gps_node` (PID 3087) |
| 启动脚本 | `/opt/robot/share/node_driver/scripts/gps_run.sh`（`taskset -c 1,2,3 ./gps_node`） |
| 配置 | `/opt/robot/share/node_driver/config/gps.yaml` |
| 支持的 NMEA | GGA / GLL / GSA / RMC / VTG / GSV |

---

## 2. 途径 B 详解：M20 直连协议（已完全打通）

**这是本次最有价值的发现** —— 协议已从 `/home/tank/m20/server.js` 完整逆向并实测跑通。

### 2.1 帧格式
```
偏移   长度   内容
0      4      同步头 SYNC = EB 91 EB 90
4      2      ASDU 长度 UInt16 LE（JSON 载荷字节数）
6      2      消息序号 UInt16 LE
8      1      载荷格式：1 = JSON
9      7      保留（填 0）
16     N      UTF-8 JSON 载荷
└──────────────── HEADER_LEN = 16 ─────────────────┘
```
> ⚠️ **`HEADER_LEN` 必须是 16，不是 9**。`server.js` 里这个常量是变量，
> 我最初按报文里的可见字段推断成 9，结果服务端从错误偏移取 JSON，
> 回 `JSON format parsing failed,error code:57346`。
> 从服务端返回的原始字节里才量出真实头长是 16。

### 2.2 载荷 JSON
```json
{"PatrolDevice":{"Type":T,"Command":C,"Time":"YYYY-MM-DD HH:MM:SS","Items":{...}}}
```
- `Time` 用本机时间，格式 `%Y-%m-%d %H:%M:%S`
- 客户端需**每 800ms 发一次心跳**：`Type=100, Command=100, Items={}`

### 2.3 上行遥测（设备周期主动上报）
| Type | Command | Items 键 |
|---|---|---|
| 100 | 100 | ErrorCode（心跳应答） |
| 1002 | 3 | ErrorList |
| 1002 | 4 | MotionStatus, MotorStatus |
| **1002** | **5** | **BatteryList, BatteryStatus, DeviceTemperature, Led, `GPS`, DevEnable, CPU** |
| 1002 | 6 | BasicStatus |
| 1002 | 7 | NavStatus, LocationStatus |

`Items.GPS` 字段：`Latitude` `Longitude` `Altitude` `Speed` `Course`
`FixQuality` `NumSatellites` `VisibleSatellites` `HDOP` `VDOP` `PDOP`

> 顺带一提：**这条通道还能一次拿到电池、温度、电机、CPU、导航状态**等一整套狗端遥测，
> 比只看 GPS 有用得多（`m20gps dogdump` 可看全部键）。

### 2.4 服务端
`basic_server`（`/opt/robot/share/basic_server/`），监听 **TCP 30001** / **UDP 30000**，
本机地址 `10.21.31.103`。机器狗 Web 控制台就是用它取 GPS 并按
`config.json` 每 1400ms 上报到 `http://10.21.31.150:3000/api/gps/data`。

---

## 3. 途径 A：ROS 2 / DDS 话题

```bash
source /opt/ros/foxy/setup.bash
export ROS_DOMAIN_ID=0
ros2 topic echo /GPS
```

| 话题 | 类型 | 发布者 |
|---|---|---|
| `/GPS` | `drdds/msg/NavSat` | 1 |
| `/GPS_SYS_MODE`、`/GPS_CFGSYS` | `drdds/msg/StdMsgInt32` | 1 |
| `/GPS_SYN_UTC` | `std_msgs/msg/String` | 1 |
| `/FIBOCOM/net_rtk/gngga` | `fibocom_msgs/msg/FibocomRtkgngga` | **0** |
| `/FIBOCOM/net_rtk/heading` | `fibocom_msgs/msg/FibocomRtkheading` | **0** |

> ⚠️ 发布者节点名是 **`_CREATED_BY_BARE_DDS_APP_`**（裸 DDS 应用，不走 rmw）。
> **没有定位时 `ros2 topic echo` 一句话都不输出**（不是报错，是没数据）。
> Foxy 也不支持 `--once` 参数。

Python 订阅示例：
```python
import rclpy
from rclpy.node import Node
from drdds.msg import NavSat

class GpsSub(Node):
    def __init__(self):
        super().__init__('gps_sub')
        self.create_subscription(NavSat, '/GPS', self.cb, 10)
    def cb(self, msg):
        print(msg.data)      # NavSatValue

def main():
    rclpy.init(); rclpy.spin(GpsSub())

if __name__ == '__main__':
    main()
```

---

## 4. 途径 C / D

**C. 直读串口 NMEA**：`sudo m20gps nmea`（短暂共享串口）。
要独占读需先停 `gps_node`，用完再
`bash /opt/robot/share/node_driver/scripts/gps_run.sh &` 拉起 —— 不建议。

**D. 看解析结果**：`m20gps`。

---

## 5. 交付：`m20gps` 命令

`/usr/local/bin/m20gps`（源码 `rtmp_1012/patch/m20gps`，
协议客户端 `rtmp_1012/patch/m20_dog_query.py`）

| 子命令 | 作用 |
|---|---|
| `m20gps` | 状态总览：本机模块 + **狗端遥测** + ROS 话题 |
| `m20gps dog` | 查狗端 GPS（`--json` 输出 JSON，`--watch` 持续） |
| `m20gps dogdump` | 转储狗端各类遥测的键（电池/温度/电机/CPU/NavStatus） |
| `m20gps watch` | 持续刷新本机 GPS |
| `m20gps nmea` | 抓原始 NMEA |
| `m20gps topic` | 订阅 `/GPS` |
| `m20gps log` | 跟踪 gps_node 日志 |

---

## 6. 定位质量对照

| FixQuality | 含义 | 典型精度 |
|---|---|---|
| 0 | 无定位 | — |
| 1 | 单点定位 | 米级 |
| 2 | 差分（DGPS） | 亚米级 |
| 4 | RTK 固定解 | 厘米级 |
| 5 | RTK 浮点解 | 分米级 |

> 本机有 `/FIBOCOM/net_rtk/*` 话题（Fibocom 模块的 RTK 通道），但**当前 0 发布者**，
> RTK 未激活（可能需插 SIM / 账号 / 差分源）。需要厘米级定位要单独查这条线
> （模块在 `/opt/robot/share/gs2dds/`）。

---

## 7. 排障

| 现象 | 排查 |
|---|---|
| 经纬度为 0 | **先挪到室外**。室内是首要原因（本次就是这个） |
| 串口无数据 | `fuser /dev/ttyS5` 看 `gps_node` 是否活着；`m20gps log` 看有无数据 |
| 有卫星但不定位 | `可见卫星总数` < 4 无法定位；检查天线是否被金属遮挡 |
| `/GPS` 话题无数据 | `ros2 topic info -v /GPS` 看发布者；无定位时本就不发 |
| `m20gps dog` 无输出 | 确认 `basic_server` 在跑、30001 在监听（`ss -tlnp \| grep 30001`） |
| 需要厘米级 | 查 RTK：`ros2 topic list \| grep -i rtk`（当前 0 发布者） |
