# 06 ROS1 与 ROS2 环境切换

> 本章讲 **103 主机上 ROS 环境本身的切换**（怎么从 ROS2 切到 ROS1、怎么切回来）。
> 监控侧"自动识别版本并选方案"的能力见 [README 第十三章](../README.md)，
> 两者相关但不同：本章是**运维操作**，第十三章是**监控程序的自适应行为**。
>
> 实测依据（2026-09-26 在 103 上核对）：`/opt/ros/` 下为 `foxy` + `noetic` 双栈；
> `transfer_ros2.service` = enabled，`transfer.service` = disabled。

---

## 6.1 103 上的双栈现状

| 项 | 值 |
| --- | --- |
| ROS 发行版 | `/opt/ros/foxy`（ROS2）、`/opt/ros/noetic`（ROS1）**同时安装** |
| ROS2 服务 | `transfer_ros2.service` —— **enabled**（开机自启） |
| ROS1 服务 | `transfer.service` —— **disabled**（且实际多由脚本拉起，不走 systemd） |
| ROS1 启动脚本 | `/home/ysc/lite_cog/system/scripts/transfer/start_transfer.sh` |
| 争抢端口 | **UDP 43897**（两套 transfer 都要收，互斥） |

因为两边都装了，`/opt/ros/*` 扫描、PATH 上的 `ros2`/`roscore` 判断**全都不可用**
（结果必然歧义）——这也是监控改用"实际在跑的进程"来判版本的根本原因。

## 6.2 端口与进程对照表（判断当前版本的最可靠依据）

| | ROS2 | ROS1 |
| --- | --- | --- |
| 主进程 | `jetson2motion` | `qnx2ros` |
| 辅助进程 | `jetson2app` | `ros2qnx` / `nx2app` |
| 占用端口 | 43897（主，实测）、43899（实测 `jetson2app`） | 43897（主）；**43899 归属待验证** |
| 是否有 roscore | 无 | **有**（`rosmaster`，端口 11311） |
| 启动方式 | systemd：`transfer_ros2.service` | 脚本：`start_transfer.sh` |

> 端口一栏的"实测"指 2026-09-26 在 103 上 `sudo ss -lunp` 亲眼所见。
> ROS1 侧的 43899 没有抓到过实测样本，**按"待验证"处理，别拿它当判据**。

```bash
sudo ss -lunp | grep 43897          # 看 43897 归谁
pgrep -af "jetson2motion|qnx2ros"   # 看谁在跑
```

## 6.3 怎么判断当前是 ROS1 还是 ROS2

**方法 1（推荐）—— 看进程与端口**

```bash
sudo ss -lunp | grep 43897
# 显示 jetson2motion → ROS2；显示 qnx2ros → ROS1
```

**方法 2 —— 用监控的检测模块**

```bash
/home/test/monitor/.venv/bin/python /home/test/monitor/backend/ros_env.py --verbose
```

会打印每条信号的命中情况（推荐用它，因为它就是为了这种歧义环境设计的）。

**方法 3 —— 厂商脚本 `print_ros_version.sh`（有局限，见下）**

```bash
sudo bash /home/ysc/scripts/print_ros_version.sh
```

**方法 4 —— 看有没有 roscore**

```bash
pgrep -af rosmaster        # 有 → ROS1
```

### ⚠️ `print_ros_version.sh` 的局限

它的判据是：

```bash
if systemctl is-enabled transfer == enabled; then  echo "ROS 1"; else echo "ROS 2"; fi
```

问题：**ROS1 链路是脚本拉起的，不会让 `transfer.service` 变成 enabled**。
所以即使你已经在跑 ROS1，只要没手动 `enable transfer`，它仍然输出 **ROS 2** —— 误判。

（该项目**未修改**此脚本，仅在监控的 `ros_env.py` 中把它的判据保留为**最低优先级**的兜底信号。）

## 6.4 怎么切换

### ROS2 → ROS1

```bash
# ⚠️ 风险提醒：会中断 ROS2 遥测话题。先确认当前没有 ROS2 消费方
#   （如 Nav2 / faster_lio ROS2 版 / rosbridge / Foxglove）
pgrep -af "nav2|faster_lio|rosbridge|foxglove" | head

sudo systemctl stop transfer_ros2.service      # 让出 43897
sudo systemctl disable transfer_ros2.service   # 关键：否则重启会被抢回（见 6.5）

bash /home/ysc/lite_cog/system/scripts/transfer/start_transfer.sh

# 验证
sudo ss -lunp | grep 43897                     # 应显示 qnx2ros
/home/test/monitor/.venv/bin/python /home/test/monitor/backend/ros_env.py   # 应输出 ros1
```

### ROS1 → ROS2

```bash
# 先停 ROS1（脚本拉起，用 pkill 或按其自带停止脚本）
pkill -f qnx2ros; pkill -f ros2qnx; pkill -f nx2app

sudo systemctl enable transfer_ros2.service
sudo systemctl start transfer_ros2.service

# 验证
sudo ss -lunp | grep 43897                     # 应显示 jetson2motion
```

## 6.5 头号陷阱：重启后被抢回端口

**现象**
手动切到 ROS1 一切正常，**103 重启后 ROS1 又失效了**，43897 回到 `jetson2motion` 手上。

**原因分析**
`systemctl stop` 只停止当前运行；服务若为 **enabled**，开机仍会自启。
实测 `transfer_ros2.service` 就是 `enabled`，这个坑已经真实发生过。

**解决方案**

```bash
systemctl is-enabled transfer_ros2.service    # 先确认
sudo systemctl disable transfer_ros2.service  # 长期跑 ROS1 必须执行
```

**规避建议**
判断"会不会开机自启"要看 **`is-enabled`**，不是 `is-active`。

## 6.6 切换对各系统的影响

| 系统 | 是否受影响 | 说明 |
| --- | --- | --- |
| **机器狗本体运动** | ❌ 不受影响 | 运动控制是 120 上的 `jy_exe`；遥测是 UDP 单向推送，103 收不收不影响它 |
| **监控面板（sniff 旁路）** | ❌ 不受影响 | AF_PACKET 在链路层看报文，与 ROS 版本无关 |
| **监控的 ros 数据源** | ✅ 受影响 | `lite3-ros-bridge` 是 **ROS2 节点**，切 ROS1 后 43900 无数据 → 自动回退 sniff |
| **Nav2 / ROS2 感知栈** | ✅ 受影响 | 依赖 `/imu/data`、`/leg_odom2`；ROS1 下这些是 ROS1 话题，ROS2 侧收不到 |
| **RO1 faster_lio** | ✅ 需要 ROS1 | `/Odometry` 由 ROS1 侧 faster_lio 产出 |

> 简言之：**切 ROS1 会让 ROS2 侧失去本体里程计与 IMU**，
> 但**监控面板照样能用**（降级到 sniff），这也是监控要做版本自适应的原因。

## 6.7 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `print_ros_version.sh` 一直说 ROS2 | 它的判据是 `transfer.service` 是否 enabled，而 ROS1 是脚本拉起的 | 改用 6.3 的方法 1/2 判断 |
| ROS1 起不来，报 `bind error` | 43897 还被 `jetson2motion` 占着 | `sudo systemctl stop transfer_ros2.service` 后再启动 |
| 节点在、话题在、但无数据 | 同上；`qnx2ros` bind 失败只 perror **不退出**，伪装成"正常" | `sudo ss -lunp \| grep 43897` 看真实归属 |
| 重启后 ROS1 失效 | `transfer_ros2` 仍 enabled 被自启 | `sudo systemctl disable transfer_ros2.service` |
| 监控显示 `ros_degraded=true` | 版本识别失败或方案不支持 | `curl -s http://127.0.0.1:8000/api/ros` 看 error 字段 |

## 6.8 双栈并存时的检测陷阱（实测，2026-09-26）

> 这一节记录的是**真机刚发生过的现象**：同一台 103，命令行跑检测模块输出 `ros1`，
> 而在线服务 `/api/ros` 输出 `ros2`。两个都是"程序算出来的"，但只有一个是对的。

**现象**

```bash
# 命令行（ssh 非登录 shell）
/home/test/monitor/.venv/bin/python /home/test/monitor/backend/ros_env.py --verbose
# → ROS 版本: ros1    命中信号: executable

# 在线服务
curl -s http://127.0.0.1:8000/api/ros
# → "version":"ros2","source":"auto","signal":"process"
```

而此刻的真实情况是：`43897` 归 `jetson2motion`（ROS2 占着），
同时 `roscore`/`rosmaster`/`rosout` 也活着（ROS1 侧残留）。

**原因分析**

三个因素叠加：

1. **`process` 信号在双栈并存时判为歧义** —— `rosmaster`（ROS1）与
   `jetson2motion`/`jetson2app`（ROS2）同时命中，模块主动放弃判定，
   向下退化到更弱的信号。这是**设计上的保守行为**，不是 bug。
2. **`executable` 信号依赖 PATH** —— 它看 PATH 上有 `roscore` 还是 `ros2`。
   ssh 非登录 shell 与 systemd 拉起的服务，PATH 不一样，于是**同一台机器两个答案**。
   这是所有信号里最弱的一条，本就只作兜底。
3. **服务的 ROS 方案只算一次并缓存** —— `main.py` 里
   `_ROS_PLAN_CACHE` 在首次调用 `get_ros_plan()` 时填充，之后不再刷新。
   如果你在**服务启动之后**才切换 ROS 环境，`/api/ros` 会一直报**旧版本**。

**解决方案**

判断"现在到底是哪套在跑"，**只认端口归属**，不要认进程名、更不要认 roscore：

```bash
printf "\047\n" | sudo -S ss -lunp | grep 43897
# users:(("jetson2motion",...)) → ROS2 生效
# users:(("qnx2ros",...))       → ROS1 生效
```

**（注意 `sudo` 在 103 上需要密码；非交互场景用 `printf "\047\n" | sudo -S`，
直接 `sudo ss` 会报 `a terminal is required to read the password`。）**

切完 ROS 环境后，让监控重新识别：

```bash
sudo systemctl restart lite3-monitor.service
curl -s http://127.0.0.1:8000/api/ros | python3 -m json.tool
```

**规避建议**

- 切到 ROS2 时把 ROS1 残留一起清掉，避免双栈并存制造歧义：
  `pkill -f roscore; pkill -f rosmaster; pkill -f rosout`
- 反过来切到 ROS1 时，务必 `disable transfer_ros2.service`（见 6.5）。
- 长期固定一套环境，别来回切；真要频繁切，就用 `LITE3_ROS_VERSION=ros1|ros2`
  显式指定，绕开自动判定。

## 6.9 一条命令速查

```bash
# 当前是谁 + 会不会开机自启
sudo ss -lunp | grep 43897
systemctl is-active transfer_ros2.service; systemctl is-enabled transfer_ros2.service

# 监控侧识别结果
curl -s http://127.0.0.1:8000/api/ros | python3 -m json.tool
```
