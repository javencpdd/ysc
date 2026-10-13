# nav：点云定位与导航集成

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/nav`。

## 1. 结构与职责

| src 下的包 | 主要入口 | 职责 |
| --- | --- | --- |
| dr_nav2 | launch/dr_nav2.launch.py、config/lite_nav2.yaml | Nav2 聚合启动、插件与代价地图配置；没有独立业务节点 |
| hdl_localization | apps/hdl_localization_composition.cpp、hdl_localization_app.hpp、globalmap_server_app.hpp | NDT/IMU 点云定位与全局 PCD 地图发布 |
| hdl_global_localization | src/hdl_global_localization_node_ros2.cpp、engines、config/*.json、srv | 可选全局重定位服务 |
| sensor_test | src/sensor_test.cpp | 按秒统计输入传感器消息数并输出日志 |

CMake 通过 ament 构建，定位依赖 PCL、Eigen、tf2、ndt_omp、fast_gicp；全局定位还包含 BBS 与 FPFH/RANSAC。dr_nav2 的外部依赖由 /opt/ros/foxy 的 Nav2 和 STVL 补齐。

## 2. hdl_localization 内部链路

`hdl_localization_composition` 在一个进程中创建 HdlLocalizationApp 和 GlobalmapServerApp，使用 SingleThreadedExecutor。

1. GlobalmapServerApp 读取 globalmap_pcd，经体素降采样发布 /globalmap；/map_request/pcd 可要求更换地图。
2. HdlLocalizationApp 接收 IMU、点云、初始位姿与腿式里程计。
3. PoseEstimator 用 IMU 预测，通过点云配准校正 UKF 状态；DeltaEstimater 用于重定位过程中的增量运动补偿。
4. 发布定位里程计、配准后的点云和 ScanMatchingStatus，并直接广播 map→base_link。

### ROS 接口（当前 lite launch 的重映射后）

| 方向 | 名称 | 类型/用途 |
| --- | --- | --- |
| 订阅 | /rslidar_points | sensor_msgs/PointCloud2；源码原名 /velodyne_points |
| 订阅 | /imu/data | sensor_msgs/Imu；源码原名 /gpsimu_driver/imu_data |
| 订阅 | /globalmap | sensor_msgs/PointCloud2 |
| 订阅 | /initialpose | geometry_msgs/PoseWithCovarianceStamped |
| 订阅 | /leg_odom2 | nav_msgs/Odometry |
| 发布 | /odom | nav_msgs/Odometry；frame_id=map，child_frame_id=base_link |
| 发布 | /aligned_points | sensor_msgs/PointCloud2；map 坐标 |
| 发布 | /status | hdl_localization/ScanMatchingStatus |
| 地图节点订阅/发布 | /map_request/pcd → /globalmap | std_msgs/String 路径 → PointCloud2 |
| 条件服务 | /relocalize | std_srvs/Empty；仅启用 use_global_localization 时创建 |

GlobalmapServerApp 定时约 1 秒重发地图；代码使用普通深度 5 QoS，不应只根据注释把它写成 transient_local。重新载图路径含再次 declare_parameter 的逻辑，重复调用需验证参数重复声明问题。里程计发布处使用 leg_odom2_msg，启动时该输入的就绪与空指针保护也应实测。

### 关键参数（launch/lite_localization.launch.py）

| 参数 | 当前值 |
| --- | --- |
| globalmap_pcd | /home/ysc/lite_cog_ros2/system/map/lite3.pcd |
| use_imu / invert_acc / invert_gyro | true / false / false |
| cool_time_duration | 2.0 |
| enable_robot_odometry_prediction | false |
| reg_method | NDT_OMP |
| ndt_neighbor_search_method / radius | DIRECT1 / 3.0 |
| ndt_resolution / downsample_resolution | 1.5 / 0.5 |
| specify_init_pose | true；位置零、单位四元数 |
| use_global_localization | false |
| t_diff | 0.25 |

这里的零初始位姿是配置初值，不代表机器人已经定位成功。CUDA 库参与链接也不代表当前使用 CUDA 配准。launch 中定义的雷达静态 TF 函数没有加入 LaunchDescription，实际依赖 driver 的静态 TF。

## 3. hdl_global_localization

ROS2 主程序创建 `hdl_global_localization_node`。引擎包括 BBS（分支定界搜索）和 FPFH_RANSAC（特征匹配与 RANSAC）；FPFH_TEASER 源文件存在，但当前 CMake 没有把它作为有效构建实现加入。

| 相对服务名 | srv 文件 | 含义 |
| --- | --- | --- |
| set_engine | SetGlobalLocalizationEngine.srv | 按字符串选择引擎 |
| set_global_map | SetGlobalMap.srv | 输入 PointCloud2 全局地图 |
| query | QueryGlobalLocalization.srv | 输入点云和候选数量，输出候选位姿、误差与内点比例 |

主配置为 config/config.json 及 config_base.json、config_bbs.json；base 地图/查询降采样均为 0.5。BBS 示例搜索 x/y 为 [-50,50]、theta 为 [-3.15,3.15]，地图分辨率 0.5。config/ros1 的 YAML 是旧 ROS1 路径，不要误当当前 ROS2 配置。

定位客户端使用 /hdl_global_localization/... 服务路径，而服务端创建的是相对服务名；启用此功能前应核对 namespace/remapping。当前 lite launch 将该功能关闭，不能声称系统已经自动全局重定位。

## 4. dr_nav2 导航配置

`dr_nav2.launch.py` 调用外部 nav2_bringup/bringup_launch.py，并启动 RViz。map_file 默认 system/map/lite3.yaml，配置默认为 lite_nav2.yaml，use_sim_time=False、autostart=True。

| 子系统 | 当前选择与关键值 |
| --- | --- |
| 控制器 | DWBLocalPlanner；controller_frequency=5 Hz，odom_topic=/leg_odom2 |
| 速度/采样 | max_vel_x=1.0、max_vel_y=0.2、max_vel_theta=0.8；vx/vy/vtheta_samples=20/6/40；sim_time=3.0 |
| 到点判断 | xy/yaw 容差均 0.4（长度与角度单位不同） |
| 局部代价地图 | map frame，8×8 m，0.1 m 栅格，rolling_window=true；STVL+inflation |
| 全局代价地图 | static+STVL+inflation；静态输入 /map |
| STVL | /rslidar_points；voxel_size=0.1，voxel_decay=0.3，障碍高度 0.15～1.20 |
| 全局规划 | Navfn，use_astar=false、allow_unknown=true |
| 恢复插件 | 配置了 spin、backup、wait；实际是否调用由 BT 决定 |

Nav2 对外提供 navigate_to_pose Action，控制链发布 /cmd_vel；planner/controller/map_server 不是本目录自行实现的节点。话题中间产物与生命周期/清图服务来自实际加载的 Nav2 包，不能用本目录四个包的数量衡量整套运行节点数。

**已核验的配置覆盖**：本机 /opt/ros/foxy/share/nav2_bringup/launch/navigation_launch.py 用 RewrittenYaml 重写 use_sim_time 与 default_bt_xml_filename。因此 YAML 某处 use_sim_time=True、BT 路径是相对名，不直接等于主 launch 的最终值。系统 localization_launch.py 已注释 AMCL，当前默认仅启地图服务；迁移需保留这一差异。

## 5. 启动与排查

已存在入口为 `system/scripts/nav/start_nav.sh`：先 source navigation2-foxy/install，再 source nav/install，然后启动：

```bash
ros2 launch hdl_localization lite_localization.launch.py
```

新 shell 还应先 source /opt/ros/foxy/setup.bash；若安装环境未记录依赖前缀，需按依赖关系加入 ndt_omp、fast_gicp 的 install 环境。本文未重建工作区、未验证库加载成功。

启动前先核验 PCD、PGM/YAML、/imu/data、/rslidar_points、/leg_odom2 与 base_link→rslidar。当前默认 PCD 和 PGM 均缺失，不能把此命令当成已验证可启动。

sensor_test 的 SensorTest 节点订阅 /imu/data（Imu）、/rslidar_points 和 /camera/depth/color/points（PointCloud2），三个回调仅累加计数，timerCallback 每秒输出并清零；没有业务发布、Service 或 Action，也没有自定义参数。它仅用于输入频率辅助观察，不验证数值正确性或同步质量；默认深度 10 的订阅 QoS 还需与发布端匹配。
