# slam：激光惯性建图与地图转换

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/slam`。

## 1. 目录和全部包

| 路径 | 包 | 功能 |
| --- | --- | --- |
| src/faster_lio | faster_lio | 点云/IMU 同步、去畸变、迭代滤波与增量地图 |
| src/faster_lio_interface | faster_lio_interface | CustomPoint、CustomMsg、Pose6d 接口 |
| src/pcd2grid | pcd2grid | PCD→OctoMap→二维栅格的聚合 launch |
| src/octomap_mapping/octomap_mapping | octomap_mapping | 元包 |
| src/octomap_mapping/octomap_server | octomap_server | 当前定制 my_octomap 实现 |

faster_lio 的 CMake 使用 C++17、PCL、TBB、glog、gflags、yaml-cpp；核心库和 run_mapping_online 被构建，offline 可执行目标被注释。octomap_server 中保留多份上游实现，但当前启用的主要可执行目标是 my_octomap；不能照上游教程假定所有目标都已构建安装。

## 2. faster_lio 主算法

入口 `app/run_mapping_online.cc`；主逻辑在 `src/laser_mapping.cc`，辅助为 imu_processing.cc、pointcloud_preprocess.cc、options.cc、utils.cc 与 include 下的 iVox/滤波实现。

- LaserMapping::InitROS 读取参数并连接发布订阅；Run 驱动一帧处理。
- SyncPackages 对齐点云与 IMU；ImuProcess 传播状态并补偿扫描运动畸变。
- 点云预处理按雷达格式提取时间/线束等信息，随后体素降采样。
- ObsModel 使用地图近邻平面约束完成迭代状态更新；MapIncremental 向 iVox 增量地图插入点。
- Finish 处理退出时保存。这里不是运行 Nav2 导航，也没有在线回环优化已启用的证据。

### Topic、TF 与服务

| 方向 | 名称 | 类型/说明 |
| --- | --- | --- |
| 输入 | /rslidar_points | PointCloud2，c16.yaml 配置 |
| 输入 | /imu/data | Imu |
| 输出 | /cloud_registered | PointCloud2，全局注册点 |
| 输出 | /cloud_registered_body | PointCloud2，机体坐标点 |
| 输出 | /cloud_registered_effect_world | PointCloud2，有效点输出路径 |
| 输出 | /Odometry | nav_msgs/Odometry；注意大写 O |
| 可选输出 | /path | nav_msgs/Path；当前 publish.path_publish_en=false |
| TF | camera_init→body | 默认世界/IMU frame，可由 publish 参数改变 |

各点云是否持续发布取决于开关与订阅条件。主建图节点未发现自定义 ROS Service/Action。faster_lio_interface 的消息定义不意味着当前所有格式入口都在使用；AVIA CustomMsg 订阅分支被注释，不能只改 lidar_type 就保证 Livox 自定义消息接入。

### 当前 c16.yaml 参数

| 类别 | 值 |
| --- | --- |
| 预处理 | lidar_type=4，scan_line=16，blind=1.0，time_scale=1e-3 |
| 同步 | time_sync_en=true |
| 降采样/迭代 | 地图/表面体素约 0.3，point_filter_num=3，max_iteration=3 |
| 噪声 | acc_cov/gyr_cov=0.1，bias 协方差 1e-4 |
| 外参 | 在线估计开启；T=[0.075,0,0.023]，R 含绕 z 轴 90° 初值 |
| 输出 | 注册点云与 body 点云开启；路径关闭 |
| PCD | pcd_save_en=true、interval=0；累计后由退出保存路径写入 system/map/lite3.pcd |

外参是雷达/IMU建模的一部分，不能与 driver 的 base_link 静态 TF 混为一组参数。应正常退出使 Finish 执行，不能依赖 kill -9 保存地图；内存累积和保存成功均需运行验证。

## 3. pcd2grid 与 my_octomap

`src/pcd2grid/launch/pcd2grid.launch.py` 启动四项：my_octomap、Nav2 map_saver_server、管理后者的生命周期节点、RViz。

MyOctomap 构造时读取 file_path，降采样后每 5 秒把 PCD 转成 PointCloud2 调用 insertCloudCallback；同时仍注册 cloud_in 订阅和 TF MessageFilter，当前 launch 将它重映射为 /pcd。不是只有“离线读文件”一种输入。

| 参数 | launch 值 |
| --- | --- |
| file_path | /home/ysc/lite_cog_ros2/system/map/lite3.pcd |
| frame_id / resolution | map / 0.05 |
| filter_leaf_size_m | 0.05 |
| point_cloud_min_z / max_z | 0.4 / 1.2 |
| occupancy_min_z / max_z | 0.0 / 1.6 |
| sensor_model.max_range | 100.0 |
| latch | true，发布端 transient_local |

主要输出：/projected_map（nav_msgs/OccupancyGrid）、/octomap_binary 和 /octomap_full（octomap_msgs/Octomap）、/occupied_cells_vis_array、/free_cells_vis_array（MarkerArray，受发布条件控制）、/octomap_point_cloud_centers（PointCloud2）。

my_octomap 服务：octomap_binary、octomap_full（octomap_msgs/GetOctomap），~/clear_bbox（octomap_msgs/BoundingBoxQuery），~/reset（std_srvs/Empty）。私有名在当前节点名下展开为 /my_octomap/clear_bbox 和 /my_octomap/reset。

map_saver_server 的 /map_saver_server/save_map（nav2_msgs/SaveMap）来自系统 Nav2，不是 pcd2grid 新定义的服务。配置 save_map_timeout=30000、free_thresh_default=0.25、occupied_thresh_default=0.65、map_subscribe_transient_local=true。其中 filter_ground_plane 被传给 map_saver_server 不等于它会替 my_octomap 滤地面；点云过滤应看 my_octomap 自己的参数。

## 4. 运行与地图交接

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/slam/install/setup.bash
ros2 launch faster_lio mapping_c16.launch.py
```

建图完成并确认生成 PCD 后，在另一干净环境运行 `ros2 launch pcd2grid pcd2grid.launch.py`，核查 /projected_map 后再保存二维图。

地图交接链：lite3.pcd 供 hdl_localization 定位；lite3.pgm+lite3.yaml 供 Nav2 map_server 导航。PCD、PGM 必须属于同一地图坐标约定。

当前 system/map 仅有 YAML，两个数据文件均缺失。system 的 start_slam.sh 依赖 gnome-terminal 打开多终端；保存脚本先删旧 pgm/yaml，存在失败后丢图风险，本次没有执行。保留旧地图后再人工确认保存，是后续维护事项而非本次已实施修改。
