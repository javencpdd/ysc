# pipeline：航点任务与步态编排

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/pipeline`。

## 1. 目录结构和用途

```text
src/
├── pipeline/
│   ├── Task.py、TaskPoint.py、TaskTransfer.py
│   ├── RobotCommander.py、Constants.py
│   └── LocationRecorder.py、LocationRecorder_EN.py
└── data/                 # 本次确认为空
```

没有 package.xml、CMakeLists.txt 或 ROS launch；它是直接由 Python 运行的 ROS2 应用，不应从“无 ROS 包”推断“没有 ROS 通信”。

依赖 rclpy、tf2_ros、geometry_msgs、nav2_msgs、NumPy、tf_transformations；记录器还需 PyQt5 和图形会话。

## 2. 核心类与流程

| 类/文件 | 关键行为 |
| --- | --- |
| Task（Node 名 pipeline） | LoadTaskpoints 读 ../data/*.json 并按 order 排序；GetBestTaskIndex 根据当前位置选最近航点；Init/Run 执行导航与步态 |
| TaskPoint | 解析 robot_pose、order、步态等字段；支持 even_low_speed、even_medium_speed、uneven_high_step |
| TaskTransfer | NavigateToPose ActionClient；发送 map 坐标目标并等待结果 |
| RobotCommander | 使用 UDP 心跳、简单/复杂协议向运动主机发送步态和速度命令 |
| LocationRecorder | Qt 窗口配合后台 ROS spin，读取 TF 并保存编号 JSON |
| LocationRecorder_EN | 英文界面版本；与记录功能同属工具入口 |

执行链：读取航点 → TF 查询 map→base_link → 选最近起点 → 下发步态/目标 → 等待 Nav2 成功 → 继续后续航点。

## 3. 对外通信

- 读取 /tf、/tf_static，由 tf2 查询 map→base_link。
- Action 客户端：`navigate_to_pose`，类型 nav2_msgs/action/NavigateToPose；目标 PoseStamped 的 frame_id=map。
- 未发现自定义 Topic 发布或 ROS Service 服务端；Action 与 Service 不应混称。
- RobotCommander 直接使用 UDP：本地端口 20001，目标 192.168.1.120:43893；约 0.25 s 发一次心跳，码 0x21040001。
- 简单/复杂报文使用 Python struct 的小端布局（<3i、<3id）；部分运动码与 transfer 一致，包括 320、325、321。这条路径不经过 transfer 节点，也不经过 VOA。

JSON 是运行数据，不是 ROS 参数文件。新增航点应由 LocationRecorder 的实际写出结构生成，避免手写时猜测字段名/单位。地图更换后要重新确认航点坐标和姿态。

## 4. 运行入口

记录器与 Task 都使用相对路径，建议在源码约定的工作目录运行：

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/nav/install/setup.bash
cd /home/ysc/lite_cog_ros2/pipeline/src/pipeline
python3 LocationRecorder.py
```

在已具备地图、TF、Nav2 和安全条件后，`python3 Task.py` 才是执行任务入口；它会发导航目标和直接 UDP 命令，本次没有运行。

## 5. 已确认缺项与静态风险

- src/data 为空，LoadTaskpoints 没有任务可读，不能直接运行完整任务流程。
- TaskTransfer 等待 Action server 没有有限超时；结果路径只有成功时清除等待标志，拒绝或失败可能一直等待。
- “选择最近航点”是欧氏距离选择，不代表该点可达或路线无障碍。
- GUI 关闭、Action 失败、ROS 中断及 UDP 心跳停止后的运动主机行为，需专门测试；源码静态阅读不能替代停车验收。

