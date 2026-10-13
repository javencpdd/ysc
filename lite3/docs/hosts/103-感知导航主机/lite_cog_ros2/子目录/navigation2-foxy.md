# navigation2-foxy：局部 Nav2 源码覆盖层

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/navigation2-foxy`。

## 1. 全部包及部署边界

这是 **11 个包的局部 Nav2 源码集合**，不是完整 Navigation2 仓库。package.xml 版本均为 0.4.7。

| src 相对路径 | 包 | 功能 |
| --- | --- | --- |
| nav2_bt_navigator | nav2_bt_navigator | NavigateToPose 行为树导航服务器 |
| nav2_regulated_pure_pursuit_controller | nav2_regulated_pure_pursuit_controller | RPP 路径跟踪插件 |
| nav2_rviz_plugins | nav2_rviz_plugins | RViz 导航目标工具、面板与 Action 客户端 |
| nav2_dwb_controller/dwb_core | dwb_core | DWB 控制器主体、插件接口与调试发布 |
| nav2_dwb_controller/dwb_plugins | dwb_plugins | 速度采样和轨迹生成器 |
| nav2_dwb_controller/dwb_critics | dwb_critics | 障碍、路径、朝向等轨迹评分 |
| nav2_dwb_controller/dwb_msgs | dwb_msgs | 轨迹评估消息与服务类型 |
| nav2_dwb_controller/nav_2d_msgs | nav_2d_msgs | 二维路径、位姿、速度接口 |
| nav2_dwb_controller/nav_2d_utils | nav_2d_utils | 二维消息转换、TF 与 OdomSubscriber |
| nav2_dwb_controller/costmap_queue | costmap_queue | 代价地图距离传播队列 |
| nav2_dwb_controller/nav2_dwb_controller | nav2_dwb_controller | DWB 元包 |

依赖 rclcpp/lifecycle、nav2_core/nav2_util、nav2_behavior_tree、BehaviorTree.CPP、pluginlib、tf2、nav2_costmap_2d；RViz 部分还需 Qt/RViz。controller_server、planner_server、map_server、bringup、STVL 等来自 /opt/ros/foxy，不在此源码集合中。

## 2. BT Navigator

`nav2_bt_navigator/src/bt_navigator.cpp` 的 BtNavigator 是 Lifecycle 节点；on_configure/on_activate 建立和激活导航行为树，navigateToPose 处理目标，loadBehaviorTree 读取 XML。

- Action 服务端：`navigate_to_pose`（nav2_msgs/NavigateToPose）。
- 订阅：`goal_pose`（geometry_msgs/PoseStamped），转换为内部导航目标；还依赖配置的里程计与 TF。
- 日志发布：`behavior_tree_log`（nav2_msgs/BehaviorTreeLog）。
- 生命周期管理接口来自 LifecycleNode；未另外设计业务 Service 类型。

### 当前主行为树的实际逻辑

文件 `behavior_trees/navigate_w_replanning_and_recovery.xml`：

1. 最外层 RecoveryNode 允许 6 次重试。
2. 规划 RateController 为 1 Hz；ComputePathToPose 失败的局部恢复是 Wait 0.5 s。
3. FollowPath 失败时清理 local_costmap/clear_entirely_local_costmap。
4. 外层恢复检查 GoalUpdated，或清理局部代价地图再 Wait 3 s。

这里 **不是默认“旋转、后退、等待”轮转恢复树**；即使 YAML 加载了 spin/backup 插件，本 XML 也没有直接调用它们。目录另有 round_robin、time/distance/speed 重规划树，follow_point.xml 使用 GoalUpdater 和 TruncatePath，但不是本次主入口默认树。

loadBehaviorTree 以文件路径打开 XML；本机系统 bringup 会用包 share 的绝对路径覆盖 YAML 的相对值。独立启动节点而绕开该 launch 时，仍需明确 default_bt_xml_filename。

## 3. DWB 的类、插件与接口

DWBLocalPlanner 的 configure 加载轨迹生成器和 critics；setPlan 设置路径；computeVelocityCommands、coreScoringAlgorithm、scoreTrajectory 对候选速度轨迹打分，选出合法低代价结果。

DWB 是加载到外部 controller_server 的插件：返回 TwistStamped，由宿主输出控制命令，**不是 dwb_core 自己直接创建 /cmd_vel 速度发布器**。

| 模块 | 关键类/作用 |
| --- | --- |
| dwb_plugins | StandardTrajectoryGenerator、LimitedAccelGenerator、XYThetaIterator、KinematicsHandler；速度/加速度约束和轨迹采样 |
| dwb_critics | BaseObstacle、PathDist、GoalDist、RotateToGoal、PreferForward 等；configure/prepare/scoreTrajectory 路径 |
| costmap_queue | 按距离遍历栅格，为路径/目标距离评分提供辅助 |
| nav_2d_utils | OdomSubscriber、消息/路径转换、TF 辅助 |
| DWBPublisher | 可选输出候选评分、路径和代价云 |

DWBPublisher 的相对 Topic 包括 evaluation（dwb_msgs/LocalPlanEvaluation）、received_global_plan/transformed_global_plan/local_plan（nav_msgs/Path）、marker（MarkerArray）、cost_cloud（PointCloud）。前缀由宿主节点/namespace 决定，且受调试开关控制。

dwb_msgs 含 4 种 msg 和 5 种 srv，nav_2d_msgs 含 6 种 msg；它们是接口包，不等于创建 5 个运行服务。生产速度参数在 nav/src/dr_nav2/config/lite_nav2.yaml 中：控制 5 Hz，采样 20×6×40，sim_time=3.0，最大 x/y/角速度为 1.0/0.2/0.8。修改本库默认值不一定覆盖 YAML。

## 4. RPP 与 RViz

RegulatedPurePursuitController 根据前视点曲率生成控制量，并用速度约束与碰撞检查调节结果。典型配置涉及 desired_linear_vel、lookahead_dist、min/max_lookahead_dist、lookahead_time 与碰撞预测。它也是 nav2_core::Controller 插件，不独立建立导航 Action 服务。

辅助发布：received_global_plan（Path）、lookahead_point（PointStamped）、lookahead_collision_arc（Path）。当前 lite_nav2.yaml 的活动控制器是 DWB，RPP 配置分支被注释，不能声称两个控制器同时生效。

nav2_rviz_plugins 提供目标工具和导航面板，向 NavigateToPose/FollowWaypoints 发送目标并与生命周期管理交互；这是客户端 UI，不是规划器或定位器。

## 5. 启动和维护

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/navigation2-foxy/install/setup.bash
source /home/ysc/lite_cog_ros2/nav/install/setup.bash
ros2 launch hdl_localization lite_localization.launch.py
```

入口会启动整套定位导航并可能接收运动目标，本文未执行。overlay 顺序决定用本地还是系统版本的同名包；可用 ros2 pkg prefix 只读核对，不能仅凭源码修改认定运行进程已加载新库。

本机 /opt/ros/foxy 的 localization_launch.py 已注释 AMCL，navigation_launch.py 会重写参数。包升级可能覆盖这些工作区外定制，迁移时应显式记录，详见[总览](README.md)。

