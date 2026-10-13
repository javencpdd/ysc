# nav-stack — Odin-Nav-Stack（ROS 1 导航栈，参考实现）

> 来源：官方开源仓库 [ManifoldTechLtd/Odin-Nav-Stack](https://github.com/ManifoldTechLtd/Odin-Nav-Stack)。
> **定位：参考资料，非 M20 Pro 主部署方案。** 主体是 Ubuntu 20.04 + ROS 1 Noetic，默认绑定 Odin1 感知设备、Unitree Go2 控制器与特定 TF/话题；迁移到 M20 需同时改控制器、感知输入、TF、模型尺寸与 ROS 1/2 通信，工作量大于直接采用 Nav2。
> 选型结论与分阶段路线见 `../docs/08-ROS2导航与强化学习部署路线.md`；本目录保留其 **NeuPAN 局部规划、工程组织方式与 ROS 包实现** 作为算法参考。
> 官方完整说明见 [`README.upstream.md`](README.upstream.md)。

## 目录结构

```
nav-stack/
├── docs/
│   ├── DOCKER_SETUP.md        Docker 化部署（Dockerfile.cn / global + compose）
│   └── TUNING_GUIDE.md        参数调优指南
├── docker/                    Dockerfile ×2、docker-compose.yml、entrypoint.sh
├── scripts/                   VLN.py、bag_record.sh、map_recording.sh、pcd_convert.py、point_record.py、run_yolo_detector.sh、str_cmd_control.py
├── NeuPAN/                    NeuPAN 规划器（T-RO 2025，端到端 MPC；Odin 定制分支，含示例配置）
└── ros_ws/src/                ROS 1 工作空间（catkin）
    ├── odin_ros_driver/       Odin1 感知驱动（ROS1/ROS2 双支持，含 liblydHostApi 静态库 amd/arm）
    ├── model_planner/         模型驱动规划器（A* + DWA，global/local 分离）
    ├── navigation_planner/    move_base 参数集（costmap / DWA / global_planner 配置）
    ├── map_planner/           地图级规划（goal_state_machine + PlanPath.srv）
    ├── fish2pinhole/          鱼眼→针孔投影与点云裁剪节点
    ├── pcd2pgm / pointcloud_saver   点云转栅格地图 / 点云保存服务
    ├── fake360                360° 激光模拟节点
    ├── unitree_control        Unitree 速度控制器
    ├── yolo_ros               YOLO 检测 ROS 封装（object_query / tf_relay）
    └── odin_vlm_terminal      VLM 终端（ros_vlm_terminal.py）
```

## 未入库内容（需要时从上游获取）

| 内容 | 原因 | 获取方式 |
|---|---|---|
| `yolov5/`（子模块） | 上游公共仓库 | `git submodule update --init` 或 clone [ultralytics/yolov5](https://github.com/ultralytics/yolov5) |
| `ros_ws/src/yolo_ros/scripts/models/yolov5s.pt`（14.8MB） | 模型权重，可重新下载 | ultralytics 官方发布 |
| `ros_ws/src/map_planner/maps/empty.pgm`（20MB 空图） | 占位地图，体积无意义 | 自行建图生成 |
| `img/`（48MB 演示图/GIF） | 演示素材 | 上游仓库 |
| NeuPAN 的 `.git`（子模块元数据） | 归档不需要 | — |

## 阅读建议

1. 先读 `docs/TUNING_GUIDE.md` 与 `NeuPAN/README.md`（论文：T-RO 2025 / arXiv 2403.06828），理解端到端 MPC 思路。
2. 再看 `ros_ws/src/model_planner/`（A*+DWA 的工程实现）与 `odin_ros_driver/`（传感器驱动范式）。
3. 与 M20 相关的新一代方案对比时，以 `../docs/08-ROS2导航与强化学习部署路线.md` 的组件表为准（Nav2 + MPPI Omni 为主链路）。
