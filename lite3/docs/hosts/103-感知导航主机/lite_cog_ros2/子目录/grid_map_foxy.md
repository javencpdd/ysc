# grid_map_foxy：多层栅格地图基础设施

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/grid_map_foxy`。

## 1. 全部 15 个包与结构

各包均在 src/<包名>，通常含 include、src、package.xml、CMakeLists.txt；消息包以 msg/srv 为主，演示包另有 launch/config。

| 包 | 主要类/模块 | 职责及运行形态 |
| --- | --- | --- |
| grid_map | 元包 | 组织依赖，没有节点 |
| grid_map_cmake_helpers | CMake 配置 | 构建辅助，没有节点 |
| grid_map_core | GridMap、Geometry、迭代器 | Eigen 多层矩阵、环形缓冲、坐标索引 |
| grid_map_msgs | GridMap、GridMapInfo；4 个 srv | 接口定义，不自动创建服务端 |
| grid_map_ros | GridMapRosConverter | 消息、点云、占据图、代价地图、rosbag2 转换 |
| grid_map_cv | GridMapCvConverter、GridMapCvProcessing、InpaintFilter | OpenCV 转换、分辨率变化与插值补洞 |
| grid_map_filters | ThresholdFilter、NormalVectorsFilter 等 | pluginlib 滤波链 |
| grid_map_octomap | GridMapOctomapConverter | OctoMap 与栅格转换 |
| grid_map_costmap_2d | Costmap2DConverter | Nav2 costmap 数据桥接，主要为头文件实现 |
| grid_map_sdf | SignedDistanceField | 三维距离与梯度查询 |
| grid_map_pcl | GridMapPclLoader、PointcloudProcessor | PCD 预处理、分格聚类及高程提取 |
| grid_map_loader | GridMapLoader | 从 bag 加载 GridMap 并发布 |
| grid_map_visualization | GridMapVisualization、VisualizationFactory | 订阅 GridMap，按配置发布显示数据 |
| grid_map_rviz_plugin | GridMapDisplay、GridMapVisual | RViz 显示插件，不是独立服务器 |
| grid_map_demos | 多个 demo 节点 | 演示插值、移动、滤波、图像/OctoMap 转换 |

版本大多为 2.0.0；grid_map_costmap_2d 为 1.6.2，详见[包清单](packages.md)。这套源码被 VOA 作为库调用，不意味着生产运行时要启动所有 demo 或 loader。

## 2. 核心库关系

GridMap 以多层矩阵存储 elevation、颜色、法向量等数据；setGeometry 定义分辨率与尺寸，atPosition 根据位置取值，move 移动环形缓冲的覆盖范围。无效值、基本层和索引起点是转换时需要保留的语义。

GridMapRosConverter 的 fromMessage/toMessage 把该数据结构与 grid_map_msgs/GridMap 互转；toPointCloud、占据图/Costmap 转换按指定 layer 输出。库函数调用不会自行建立 ROS Topic。

grid_map_filters 在 configure/update 中加载参数、处理图层；当前 CMake 构建 16 个滤波库，涵盖阈值、半径最小/均值、法向量、曲率、法向着色、光照、数学表达式、滑窗表达式、复制/删除、颜色填充/映射/混合、基本层和缓冲归一化。使用这些插件需由宿主配置滤波链。

SignedDistanceField 的 getDistanceAt/getDistanceGradientAt 提供距离和梯度，不是 Nav2 控制器。grid_map_cv 使用 OpenCV，grid_map_pcl 使用 PCL/OpenMP，rviz_plugin 使用 Qt5/RViz/Ogre，ROS 转换依赖 rosbag2_cpp；不是仅安装 Eigen 即可构建全部包。

## 3. 节点、Topic 与参数

### grid_map_loader

GridMapLoader::readParameters → load → publish；读取 bag 中指定 Topic，不是 PCD 读取器。

| 参数 | 默认值 |
| --- | --- |
| file_path | 空，必须提供有效 bag 路径 |
| bag_topic / publish_topic | /grid_map / /grid_map |
| duration | 5.0 |
| qos_transient_local | true |

发布 grid_map_msgs/GridMap；无自定义服务端。读取失败不会生成有效地图，duration 是代码保持发布进程的等待配置，不是固定刷新频率。

### grid_map_pcl_loader_node

GridMapPclLoader 通过 preProcessInputCloud、initializeGridMapGeometryFromInputCloud、addLayerFromInputCloud 生成地图。PointcloudProcessor 负责过滤、变换与聚类。

发布 `grid_map_from_raw_pointcloud`（GridMap，transient_local）；可把结果保存到 bag。节点参数包括 folder_path、pcd_filename、output_grid_map、map_frame（默认 map）、map_layer_name（默认 elevation）、map_rosbag_topic。

config/parameters.yaml 的关键值：处理线程 4；cluster_tolerance=0.05、最小聚类点数 4；离群过滤 mean_K=10、stddev_threshold=1.0；体素 0.02；栅格 resolution=0.1，每格至少 4 点。该 YAML 是点云提取算法配置，不等同于 VOA 的 voa.yaml。

### grid_map_visualization

输入 grid_map_topic 默认 /grid_map；activity_check_rate=2.0；transient_local=false。根据 visualizations 列表及各项 type/layer 输出 PointCloud2、OccupancyGrid、Marker 或 GridCells 等；输出名由每个可视化项命名决定，不存在一份适用于所有配置的固定输出 Topic 表。

GridMapVisualization::updateSubscriptionCallback 会按输出是否有人订阅启停输入订阅，callback 转换地图后逐项 visualize。因此“节点存在但没有输入订阅”可能是惰性订阅逻辑，不一定是程序退出。

### RViz、演示与服务定义

GridMapDisplay 消费 GridMap 并生成 RViz 图形；demos 中的 simple_demo 等生成独立演示数据，不能与真实 /grid_map 数据无区别地混用。

grid_map_msgs 声明 GetGridMap、GetGridMapInfo、SetGridMap、ProcessFile 四种 srv；这些是可复用类型，**不能据此声称当前有同名服务在运行**。上述库与常用 loader/visualization 主链未发现创建对应业务服务端。

## 4. 运行入口

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/grid_map_foxy/install/setup.bash
ros2 launch grid_map_demos simple_demo_launch.py
```

这只适用于隔离的演示环境，包含 demo、可视化与 RViz，本次未运行。点云转换入口为 `ros2 launch grid_map_pcl grid_map_pcl_loader_launch.py`，运行前检查其参数、输入 PCD 和输出路径。生产 VOA 只需正确解析相关库，不要求运行演示节点。

主要证据位于各包 CMake、GridMap.cpp、GridMapRosConverter.cpp、GridMapLoader.cpp、GridMapVisualization.cpp、GridMapPclLoader.cpp、helpers.cpp 和 config；逐文件路径与校验值见[源码清单](source-files.md)。

