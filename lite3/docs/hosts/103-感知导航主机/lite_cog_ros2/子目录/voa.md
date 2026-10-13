# voa：深度点云近场避障与速度修正

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/voa`；唯一 ROS 包为 `src/voa`。

## 1. 结构与处理链

`src/VoaComposition.cpp` 将 PointCloudProcessor、GridMapper、SafetyController 放入同一进程，开启进程内通信并使用 MultiThreadedExecutor。三个核心类分别位于同名 .hpp，栅格辅助类为 MyGridMap；FakeImuPublisher.cpp 是调试输入，不是生产传感器驱动。

```text
深度点云 + IMU → PointCloudProcessor → transformed_points
              → GridMapper/MyGridMap → grid_map
cmd_vel + 手柄 + 腿式里程计 + 超声 + grid_map → SafetyController → cmd_vel_corrected
```

CMake 采用 C++14，依赖 PCL、OpenCV、cv_bridge 与 grid_map 系列。package.xml 与 CMake 的依赖声明并不完全对齐，迁移构建应以实际 find_package 和链接项联合核对，不能只运行 rosdep 后就认定依赖齐全。

## 2. 主要类/算法

### PointCloudProcessor

从 camera_depth_optical_frame 获取到 base_link 的静态变换，结合 IMU 的 roll/pitch（yaw 置零）形成面向 robot_foot_print 的补偿；维护 IMU 缓冲，选择接近点云时刻的消息。对点云做范围裁剪与体素降采样后发布。

### GridMapper / MyGridMap

将补偿点云加入多层 GridMap；以栅格高度表示障碍，按配置执行 OpenCV 膨胀/腐蚀，可走 CUDA 图像操作路径。循环发布地图后清理临时栅格，处理循环中有约 5 ms 休眠；这不是可保证的 200 Hz 发布指标。

### SafetyController

缓存地图、超声、里程计和速度意图，预测机器人矩形占地沿候选速度运动是否碰撞，选择修正速度并发布可视化 marker。后退分支利用超声距离阈值（1.5、0.6）限速。它是近场速度修正层，不替代 Nav2 全局规划。

## 3. Topic 与 TF

| 方向 | 名称 | 类型 |
| --- | --- | --- |
| 输入 | /camera/depth/color/points | sensor_msgs/PointCloud2 |
| 输入 | /imu/data | sensor_msgs/Imu |
| 中间输出 | /camera/depth/color/transformed_points | PointCloud2，frame_id=robot_foot_print |
| 地图输出/控制输入 | /grid_map | grid_map_msgs/GridMap |
| 控制输入 | /us_publisher/ultrasound_distance | std_msgs/Float64 |
| 控制输入 | /leg_odom2 | nav_msgs/Odometry |
| 控制输入 | /handle_state、/cmd_vel | geometry_msgs/Twist |
| 控制输出 | /cmd_vel_corrected | geometry_msgs/Twist，best_effort 深度 1 |
| 调试输出 | /marker | visualization_msgs/MarkerArray |

未发现该包的自定义 ROS Service/Action。接收 cmd_vel、handle_state 不等于实现了全系统多控制源仲裁。

voa_launch.py 另启动 static_transform_publisher：base_link→camera_link，平移 [0.25489,0,0.07249]、旋转参数 [0,0.34907,0]；camera_link 到 optical frame 的链还依赖相机驱动。

源码 Node 名含 `realsense_point_cloud_processer`、`grid_mapper`、`safety_controller`；launch 设置进程节点名 voa_composition，配置 YAML 顶层同名。全局重命名可能影响进程内多个 Node 的实际名称，不能仅比较构造函数字符串就断言参数未生效；运行后应逐节点核对参数。

## 4. 当前 config/voa.yaml

| 参数组 | 值 |
| --- | --- |
| timeout_s_pc / gm / sc | 均 3.000 s；源码某些默认值为 0.2，不可混写 |
| 点云范围 | pass_x_min/max=0/3；pass_y_min/max=-1.5/1.5 |
| leaf_size | 0.05 |
| 地图 | height=6、width=4、resolution=0.05 |
| 图像处理 | use_cv=true、use_cuda=true、is_dilate=true、dilate_kernel_size=3、is_erode=false |
| 预测 | kMaxOdomBufferLength=10、kMaxPredictTimes=5、kPredictDtS=1.0、kSafetyDtS=0.3 |
| 机器人模型 | kRobotLengthM=0.65、kRobotWidthM=0.45 |
| 障碍与调整 | kObstatleHeight=0.10、kP4Vx=0.010、kP4Vyaw=0.010 |

`kObstatleHeight` 是代码原拼写。参数名里的 timeout 不能自动证明已实现“输入中断立刻发零速”；需逐输入验证旧数据、缓存速度和停发策略。

## 5. 启动与边界

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/grid_map_foxy/install/setup.bash
source /home/ysc/lite_cog_ros2/voa/install/setup.bash
ros2 launch voa voa_launch.py
```

入口支持 config_path；voa_rviz_launch.py 提供可视化，debug_launch.py 引入假 IMU。不要在真实 /imu/data 已运行时把假 IMU 当作生产输入启动。

补充复核：RealSense 入口已补齐，默认 424×240@30 深度流、无纹理 XYZ 点云，/camera/depth/color/points 与 camera_depth_optical_frame 符合 VOA 输入约定。相机 gyro/accel 默认关闭，/imu/data 仍需 transfer 等来源提供。驱动先做 0.05 m 体素降采样，VOA 在变换后再做一次，需评估稀疏程度。launch 静态求值通过不代表设备已出流，详见 [driver](driver.md)。

即便 VOA 正常发布修正速度，transfer 仍同时接受原始 /cmd_vel，所以这套静态连接不构成独占的安全控制链；本次没有验证避障或制动效果。
