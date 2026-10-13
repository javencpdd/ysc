# transfer：机器人 UDP 与 ROS 桥接

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/transfer`。

## 1. 结构与构建

- `src/transfer/src/Jetson2Motion.cpp`：运动主机收发。
- `src/transfer/src/Jetson2App.cpp`：App 指令接收与状态响应。
- `src/transfer/src/SensorChecker.cpp`、`SensorsLogger.hpp`：传感器存活检查。
- `src/transfer/include`：UDP 协议与公共定义；协议结构需与运动主机一致。
- `src/transfer/launch/transfer_launch.py`：启动 jetson2app、jetson2motion、sensor_checker 三个可执行程序。
- `src/transfer_interfaces/msg`：MotionSimpleCMD、MotionComplexCMD 两种消息；独立接口包。

CMake 与 package.xml 使用 ament/rosidl，依赖 rclcpp、sensor_msgs、geometry_msgs、nav_msgs、std_msgs、tf2 等。没有自定义 ROS 服务定义。

## 2. 节点和关键函数

jetson2motion 进程创建 MotionSender（motion_sender）和 MotionReceiver（motion_receiver），由 MultiThreadedExecutor 执行。Sender 的 CmdVelCallback 将速度编码成 UDP 指令；Receiver 根据报文长度和命令码解析机器人状态、关节、手柄、IMU、超声。

jetson2app 中 AppReceiver（app_receiver）接收 App 报文，处理手柄与启停请求。Sensor<T> 维护输入的最近时间，SensorChecker 按周期输出 Bool 存活标记；它只说明近期收到了数据，不代表数据质量合格。

| launch 参数 | 当前值 |
| --- | --- |
| jetson2motion target_ip / target_port | 192.168.1.120 / 43893 |
| jetson2motion local_port | 43897 |
| jetson2app local_port | 43899 |
| sensor_checker is_debug | true；但 C++ 声明的是 isdebug，名称不一致 |

参数名不一致意味着不能只凭 launch 中 is_debug=True 认定调试分支启用，应读取节点实际参数验证。

## 3. ROS 数据接口

### MotionSender 输入

| Topic（根命名空间下） | 类型 | 行为 |
| --- | --- | --- |
| /cmd_vel | geometry_msgs/Twist | 速度直接送往运动主机 |
| /cmd_vel_corrected | geometry_msgs/Twist | 与原始速度共用同一 CmdVelCallback |
| /simple_cmd | transfer_interfaces/MotionSimpleCMD | int32 cmd_code、size、type |
| /complex_cmd | transfer_interfaces/MotionComplexCMD | 上述字段加 float64 data |

速度订阅为 best_effort、深度 1。linear.x、linear.y、-angular.z 分别编码为命令 320、325、321。负号属于当前运动协议约定，不宜随意移除。

**原始与修正速度没有优先级或互斥判断**：两个 Topic 到达哪个就执行哪个。因此不能把这条链描述成“所有速度一定经 VOA 后再执行”。

### MotionReceiver 输出

| Topic | 类型 | frame/细节 |
| --- | --- | --- |
| /leg_odom | geometry_msgs/PoseWithCovarianceStamped | frame_id=odom |
| /leg_odom2 | nav_msgs/Odometry | 写入 pose/twist；当前代码没有设置 frame_id/child_frame_id |
| /joint_states | sensor_msgs/JointState | 12 个关节值按代码取负 |
| /handle_state | geometry_msgs/Twist | 手柄速度，best_effort 深度 1 |
| /imu/data | sensor_msgs/Imu | frame_id=base_link，使用接收时刻时间戳 |
| /us_publisher/ultrasound_distance | std_msgs/Float64 | 超声距离 |

代码中的里程计 sendTransform 已注释，因此该进程不能被当作已提供 odom→base_link 的 TF 来源。报文码包括机器人状态 2305、关节 2306、手柄 2309、IMU 0x010901；结构体对齐/浮点布局必须与对端一致。

### App 与存活标记

App 发布 `/commands/joy_raw`（sensor_msgs/Joy）。传感器检查输出：

`/sensor_status/{imu,odom,odom2,joint,realsense,lidar,ultrasound}_isalive`（std_msgs/Bool）。

检查周期约 500 ms，沉默阈值约 5 s；输入使用固定名称，包括 /rslidar_points 和深度点云。重映射传感器话题时需要同步处理 checker。

## 4. 系统服务副作用

App 命令 0x21012109 的特定值 0x40 在 IMU 存活条件下会调用 systemctl 启动 realsense_ros2 与 voa_ros2；值 0 请求停止。0x2101210D 返回状态。此状态包含内部标志，**不是读取 systemd 实际健康状态的等价结果**。

日志路径含 `/home/ysc/lite_cog_ros2/transfer/nx2app_log.txt`。这些 systemctl 操作不是 ROS Service；unit 是否存在、调用者是否有权限，需另外核验。本次未触发 App 指令或修改服务。

## 5. 启动和风险

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/transfer/install/setup.bash
ros2 launch transfer transfer_launch.py
```

上述命令会打开 UDP 端口并可能发送运动命令，本文没有执行。先确认现有服务/进程是否已占用端口，不要启动重复实例。

静态风险还包括：接收线程在阻塞 recv 情况下，析构先 join 再关闭 socket 可能影响正常退出；SensorChecker 的对象所有权与调试分支值得专门测试。这里记录的是代码风险，不声称已在机器人上复现故障。
