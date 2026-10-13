# ROS 数据源排查手册

面向「ROS 话题订阅模式收不到数据」的定位流程。配套页面上的**自检面板**
（操作台 → 监听模式 → 自检结论，数据来自 `GET /api/source` 的 `diag` 字段）。

## 0. 数据链路（先确认自己卡在哪一段）

```
120 运动主机 ──UDP 43897──> 103: transfer_ros2
                                   │ 发布 ROS2 topic
                                   ▼
                            /imu/data  /leg_odom2  /joint_states
                                   │ 订阅
                                   ▼
                          lite3-ros-bridge（ros_bridge_node.py）
                                   │ 本地 UDP 转发 JSON
                                   ▼
                          127.0.0.1:43900 ──> lite3-monitor 后端
```

**关键点**：monitor 后端并不碰 43897（sniff 除外），它只收 `ros_bridge_node`
转发到本地 43900 的 JSON。所以 ROS 模式没数据时，先判断是「桥接没起来」还是「桥接起来了但 topic 没数据」。

## 1. 页面自检先读一遍

操作台 → 监听模式 下方的自检面板会逐项打勾：

| 检查项 | 异常含义 |
|---|---|
| 模式配置 | `LITE3_DATA_SOURCE` 不是 `ros` / `auto`，根本不会走 ROS |
| 当前生效数据源 | 显示 `sniff` 且标注「已回退」= ROS 取不到数据已降级 |
| 桥接端口收包 | `frames_received` 为 0 = 43900 上一个包都没收到 |
| sniff 兜底能力 | 不支持（非 Linux / 缺 CAP_NET_RAW）时 ROS 失败后**没有兜底** |

结论档位：`ok`（正常）/ `wait`（等首帧）/ `warn`（配置问题）/ `fail`（已降级或中断）。

## 2. 在 103 上的核对命令

```bash
# ① 桥接服务在不在跑（第二套实例注意带 2 后缀）
systemctl status lite3-ros-bridge
systemctl status lite3-ros-bridge2          # monitor2 对应的桥接
journalctl -u lite3-ros-bridge -n 50 --no-pager

# ② 桥接端口有没有在被监听 / 有没有数据在发
sudo ss -lunp | grep 43900
sudo tcpdump -i lo -nn udp port 43900 -c 5   # 本地回环，看桥接有没有转发

# ③ ROS 侧：topic 是否真的在发布
source /opt/ros/<distro>/setup.bash
ros2 topic list | grep -E 'imu|odom|joint'
ros2 topic hz /imu/data                      # 应有 ~稳定频率
ros2 topic echo /leg_odom2 --once

# ④ 后端视角（把 8002 换成你的实例端口）
curl -s http://127.0.0.1:8002/api/source | python3 -m json.tool

# ⑤ 上游确认：43897 到底有没有到 103
sudo tcpdump -i any -nn udp dst port 43897 -c 5
```

**判读**：
- ⑤ 没数据 → 问题在上游（120 侧 `jy_exe/conf/network.toml` 的 ip/端口、机器人是否上电），与 ROS 模式无关。
- ⑤ 有数据、③ 没 topic → `transfer_ros2` 没在发布，查它自己的服务状态。
- ③ 有 topic、② 没包 → `ros_bridge_node` 没起来或端口/topic 名不匹配。
- ② 有包、页面仍无数据 → 桥接端口与后端 `LITE3_ROS_BRIDGE_PORT` 不一致。

## 3. 常见失败原因

| 现象 | 原因 | 处理 |
|---|---|---|
| 桥接服务起不来 | ROS 环境没 source / `rclpy` 不可用 | `deploy/lite3-ros-bridge.service` 用 `ls /opt/ros/*/setup.bash` 自动探测；若 ROS 装在别处，改 ExecStart 里的路径 |
| 桥接起来了但 43900 没包 | 订阅的 topic 名与 `transfer_ros2` 实际发布的不一致 | 用 `ros2 topic list` 核对，改 ExecStart 的 `--imu/--odom/--joints` |
| 端口对不上 | 第二套实例端口是 `43900 + TAG` | TAG=2 → 43902，服务名为 `lite3-ros-bridge2`；两边要用同一个 TAG |
| ROS 图里节点名冲突 | 多套实例节点同名会互相顶掉 | 桥接已支持 `--name`，install.sh 会按 TAG 生成 `lite3_ros_bridge2` |
| 一会儿有一会儿没有 | 桥接只在收到 topic 回调时才发送（`_dirty` 门控） | 属正常：topic 静默则桥接静默；超过 `LITE3_ROS_STALE_TIMEOUT` 会自动回退 sniff |
| ROS 失败后彻底没数据 | 本机不支持 AF_PACKET | 给服务加 `AmbientCapabilities=CAP_NET_RAW`（install.sh 已配置） |

## 4. 相关环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `LITE3_DATA_SOURCE` | `auto` | `auto`=ROS 为主 + sniff 兜底（双向自愈） |
| `LITE3_ROS_BRIDGE_PORT` | `43900` | 桥接端口，第二套为 `43900 + TAG` |
| `LITE3_ROS_STALE_TIMEOUT` | `10.0` | ROS 曾正常后断流多久判定失效 |
| `LITE3_ROS_RETRY_INTERVAL` | `15.0` | 回退 sniff 期间多久探测一次 ROS 是否恢复 |
| `LITE3_LINK_TIMEOUT` | `3.0` | 启动后多久没首帧即降级 |

## 5. 已知限制

- **`velocity_body` 恒为 0**：`ros_bridge_node.py` 只在初始化时把它设为 0，
  没有任何话题回调会更新它。走 ROS 时机体系速度不可信，暂以世界系为准。
- 心跳以 4Hz 发送，服务端审计是 200 条环形缓冲；现在心跳记录会被裁剪到最近 20 条，
  因此业务指令不会被挤出历史（详见 `control_service.AUDIT_HEARTBEAT_KEEP`）。
