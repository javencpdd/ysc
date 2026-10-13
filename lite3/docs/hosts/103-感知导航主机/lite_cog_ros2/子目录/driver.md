# driver：传感器与硬件 SDK

[返回总览](README.md)。远端根目录：`/home/ysc/lite_cog_ros2/driver`。

## 1. 用途、结构与包

| 子目录 | ROS 包 | 职责 |
| --- | --- | --- |
| mid360_ws/src | livox_ros_driver2 | Livox 点云/IMU 转 ROS 消息，含 CustomPoint/CustomMsg |
| leishen_ws/src/Lslidar_ROS2_driver-C16_V4.0 | lslidar_driver、lslidar_msgs | C16 等雷达 UDP 解包、过滤、LaserScan 与控制服务 |
| realsense_ws/src | realsense2_camera、realsense2_camera_msgs、realsense2_description | RealSense 驱动、接口定义与 URDF/RViz 描述 |
| orbbec_ws/src | orbbec_camera、orbbec_camera_msgs、orbbec_description | Orbbec 驱动、接口与相机模型 |
| Livox_SDK2 | 无 ROS package.xml | C/C++ SDK、UDP 收发和设备命令；并非另一个 ROS 节点包 |

各 ROS 包的 package.xml、CMakeLists.txt 均列于[包清单](packages.md)。description 包只提供模型/显示资源，不采集相机数据。SDK 的 CMake 构建 livox_lidar_sdk_static/shared，源码版本字段为 0.0.2；ROS 驱动版本另见包清单。

## 2. Livox 主链

重点文件：`mid360_ws/src/livox_ros_driver2/src/{driver_node.cpp,lds_lidar.cpp,lddc.cpp}`、`launch_ROS2/msg_MID360s_launch.py`、`config/MID360s_config.json`。

- DriverNode 管理 ROS 节点，LdsLidar 对接 SDK 数据接收，Lddc 按格式发布缓存点云和 IMU。
- SDK 入口在 `Livox_SDK2/include/livox_lidar_api.h`：LivoxLidarSdkInit/Start/Uninit、SetLivoxLidarPointCloudCallBack、SetLivoxLidarImuDataCallback；sdk_core 负责设备、命令、网络线程和数据分发。
- 当前 MID360s launch：xfer_format=0（PointCloud2）、multi_topic=0、publish_freq=10.0、frame_id=rslidar。
- `/livox/lidar` 重映射为 `/rslidar_points`；IMU 保持 `/livox/imu`，**不是 transfer 的 /imu/data**。
- SDK 配置：host_ip=192.168.1.103，雷达 IP=192.168.1.201；设备端口 56100～56500，主机端 56101～56501。
- SDK 外参含 pitch=18.0、x=187、z=400，单位应按 SDK 协议处理；不能把该值直接当作 ROS 米制 TF。launch 同时发布全零 `base_link → rslidar`，需结合 SDK 是否已应用外参理解。
- 主 ROS2 发布链未发现自定义服务端；改变 SDK 设备配置与发布 ROS 参数不是同一操作。

## 3. 雷神 C16 主链

重点文件：`leishen_ws/src/Lslidar_ROS2_driver-C16_V4.0/lslidar_driver/src/{lslidar_driver.cpp,input.cpp,lslidar_driver_node.cpp}`、`params/lslidar_c16.yaml`。

LslidarDriver 的 initialize/loadParameters/createRosIO 初始化配置与接口；poll/decodePacket 解码，difopPoll 接收设备信息，publishPointcloud 过滤并发布，pointcloudToLaserscan/publishScan 输出扫描。Input 实现 socket/PCAP 输入。

| 项目 | 当前 C16 配置 |
| --- | --- |
| 地址/端口 | 192.168.1.201，MSOP 2368，DIFOP 2369 |
| 点云 | /c16/lslidar_point_cloud 重映射到 /rslidar_points；PointCloud2 |
| 扫描 | /c16/scan；LaserScan；publish_scan=true |
| frame/range | rslidar；0.3～200.0 m |
| 降采样 | filter_voxel=true，filter_leaf_size_m=0.05 |
| 自体/平面过滤 | filter_box=true、crop_negative=true、filter_plane=true；平面系数与包围盒写死在 YAML |
| 静态 TF | base_link→rslidar，平移 [0.16,0,0.47]，launch 旋转参数 [1.57,0,0] |

服务在节点 namespace=c16 下创建：

| 相对服务名 | 类型（lslidar_msgs/srv） |
| --- | --- |
| lslidar_control | LslidarControl |
| motor_control | MotorControl |
| set_motor_speed | MotorSpeed |
| set_data_port / set_dev_port | DataPort / DevPort |
| set_data_ip / set_destination_ip | DataIp / DestinationIp |
| time_service | TimeService |

这些服务可改变雷达工作模式或网络配置，不应作为只读检查命令调用。lslidar_msgs 还定义 LslidarPacket、LslidarPoint、LslidarScan；接口定义不意味着每种消息都在当前启动链发布。

## 4. RealSense

重点文件：`realsense_ws/src/realsense2_camera/src/{realsense_node_factory.cpp,base_realsense_node.cpp,t265_realsense_node.cpp}`。

RealSenseNodeFactory 选择设备并创建处理节点；BaseRealSenseNode 配置流、发布图像/CameraInfo/点云/IMU/TF；T265 路径另处理跟踪里程计。

- Topic 随 namespace、流开关和 filters 变化。常见相对输出有 color/image_raw、depth/image_rect_raw、各流 camera_info、depth/color/points（PointCloud2）、gyro/sample、accel/sample、metadata、extrinsics；不能把全部接口当作默认都开启。
- 服务：相对 `enable`（std_srvs/SetBool，切换传感器）、`device_info`（realsense2_camera_msgs/DeviceInfo）。
- `config/d435i.yaml`：彩色 640×480@30，深度 1280×720@30，启用 accel/gyro/infra，enable_pointcloud=false、filters 为空。该文件是否载入须以 launch 为准；存在 YAML 不代表自动生效。
- 补充复核：`launch/dr_camera_launch.py` 已补齐为 12847 字节，SHA-256 为 `08dcb8617499d00e5682fa7ffd8cd6b0ddbc6a9f5f8fdc341ff0e46e93efb9f7`，原“空文件”缺项已解除。安装侧链接解析到同一源码文件，不需为复制此 launch 单独重新构建；但这不证明驱动二进制与 C++ 源码同步。

### 4.1 定制 launch 的实际行为

declare_configurable_parameters 声明参数，set_configurable_parameters 转为 LaunchConfiguration 字典，generate_launch_description 按 ROS_DISTRO 选择 Node 写法。Foxy 使用新版分支，目标为 realsense2_camera/realsense2_camera_node，namespace 和 name 均默认 camera，完整节点名为 `/camera/camera`。

两项 Node 动作以 config_file 是否为空互斥，默认仅选择无 YAML 的一项，不是启动两个相机。有 YAML 时，文件参数位于默认字典之后，匹配节点的配置可覆盖默认值。system/scripts/depth_camera/realsense/start_realsense.sh 没有传覆盖参数，因此**不会自动加载 d435i.yaml**。

| 参数 | 当前默认值 | 意义 |
| --- | --- | --- |
| enable_depth、depth_width/height/fps | true、424/240/30.0 | 请求 424×240@30 深度流；硬件是否支持未验证 |
| enable_pointcloud | true | 启用点云；filters 为空不等于禁用点云 |
| enable_color、enable_infra1/2 | false | 默认不启彩色/红外流 |
| pointcloud_texture_stream | RS2_STREAM_ANY | 无纹理 XYZ 分支，不需要彩色帧 |
| align_depth、enable_sync | false | 不对齐至彩色、不启同步模式 |
| enable_gyro、enable_accel | false | 不提供相机 IMU，VOA 仍需外部 /imu/data |
| filter_voxel、filter_leaf_size_m | true、0.05 | 发布前做 5 cm PCL 体素降采样 |
| depth_qos、pointcloud_qos | SYSTEM_DEFAULT | 实际 DDS QoS 仍应运行核对 |
| serial_no、usb_port_id、device_type | 空 | 未固定相机，多设备环境需选择 |
| wait_for_device_timeout、reconnect_timeout | -1.0、1.0 | 可持续等待设备，进程存在不代表出流成功 |
| tf_publish_rate | 0.0 | 不能直接解释为关闭静态 TF |

### 4.2 与 VOA 的衔接及注意事项

`base_realsense_node.cpp:1209` 固定使用相对话题 depth/color/points，结合 namespace 得到 `/camera/depth/color/points`。名字中有 color 不代表必须启用彩色：publishPointCloud 在 RS2_STREAM_ANY 下生成 XYZ；align_depth=false 时使用深度 optical frame，默认为 `camera_depth_optical_frame`，与 VOA 硬编码输入匹配。

`base_realsense_node.cpp:1021` 读取自定义体素参数，`:2577` 转为 pcl::PointXYZ 后降采样再发布。VOA 坐标变换后又按 leaf_size=0.05 降采样，需评估点云稀疏度和额外开销；若以后开启纹理，该 PointXYZ 转换还会丢弃颜色。发布函数在没有订阅者时直接返回，不能据此认定设备故障。

仍需相机内部 optical TF、VOA 提供的 base_link→camera_link 外参、外部 /imu/data 及控制器所需的里程计/超声。改 camera_name 或 align_depth 时须配套核对 VOA 的固定话题/frame，不能假定自动适配。

config_file 使用 PythonExpression，路径参数须保留 Python 字符串字面量引号；裸路径可能成为非法表达式。默认空配置分支已验证，非默认 YAML 分支未验证。output 虽声明为参数，Node 输出实际写死 screen，传 output:=log 不会改变该设置。

### 4.3 本次验证范围

通过 AST 语法检查，并在远端 Foxy 环境构造 LaunchDescription、求值默认条件及参数：条件为一项 True、一项 False，布尔/数值转换正确。未调用 Node.execute，未启动相机或验证 USB、帧率、点云、TF 实际输出。

在硬件允许启动且无重复实例时，source Foxy 与 realsense_ws/install/setup.bash 后的入口是 `ros2 launch realsense2_camera dr_camera_launch.py`。本次没有执行该启动命令。

## 5. Orbbec

重点文件：`orbbec_ws/src/orbbec_camera/src/{ob_camera_node_driver.cpp,ob_camera_node.cpp,ros_service.cpp}`，以及 launch 下各机型文件。

OBCameraNodeDriver 负责枚举/连接设备，OBCameraNode 选择 profile、启停流、回调发布；ros_service.cpp 包装曝光、增益和设备属性。Jetson/RK 解码实现是平台可选路径。

- 发布各启用流的 Image/CameraInfo；depth/points、depth_registered/points 为可选 PointCloud2；gyro/sample、accel/sample 为可选 Imu。最终前缀由相机 namespace 决定。
- 按流创建 get/set_<stream>_exposure、get/set_<stream>_gain、set_<stream>_auto_exposure、toggle_<stream>、set_<stream>_mirror。
- 其他服务包括 get_device_info、get_sdk_version、save_images、save_point_cloud，以及白平衡、激光/LDP、风扇、地板检测、IR 切换等设备控制；具体支持受机型和 SDK 约束。
- 常用参数 enable_color/depth/infra、流分辨率/FPS、序列号、depth_registration、点云开关；应以实际机型 launch 为起点，不用其他机型参数代替。
- 当前 system 脚本未提供 Orbbec 聚合入口，不能据此认定设备正在使用。

## 6. 运行方式与边界

以下仅记录入口，未启动硬件。每次在干净 Foxy shell 中只选择实际连接的一种雷达：

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/driver/leishen_ws/install/setup.bash
ros2 launch lslidar_driver lslidar_c16_launch.py
```

Livox 对应 source mid360_ws/install/setup.bash 后运行 `ros2 launch livox_ros_driver2 msg_MID360s_launch.py`。Orbbec 对应 source orbbec_ws/install/setup.bash 后选择实际型号，例如 `ros2 launch orbbec_camera gemini2.launch.py`（仅在型号匹配时）。

不要同时启动两个向 /rslidar_points 发布且广播相同 TF 的驱动。C16 与 Livox 配置都使用 192.168.1.201，不能由 IP 相同推断硬件可互换。相机入口需先补齐/确认配置，再进行启动验证。
