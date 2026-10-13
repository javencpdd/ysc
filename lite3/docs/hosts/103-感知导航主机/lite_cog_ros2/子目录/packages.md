# ROS 功能包完整清单

[返回总览](README.md)。所有路径相对于远端 `/home/ysc/lite_cog_ros2/`。

共 50 份 package.xml：49 个 colcon 可发现包，加上嵌套 Sophus。以下版本和依赖来自源码清单，不代表系统已安装这些依赖，也不是完整传递依赖求解结果。每个包同级 CMakeLists.txt 均已核对；主要构建目标和实现见各目录笔记。

## driver

[目录笔记](driver.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `livox_ros_driver2` | 1.0.0 | `driver/mid360_ws/src/livox_ros_driver2/package.xml` | `ament_cmake_auto`、`rosidl_default_generators`、`rclcpp`、`rclcpp_components`、`std_msgs`、`sensor_msgs`、`rcutils`、`pcl_conversions`、`rcl_interfaces`、`libpcl-all-dev`、`rosbag2`、`rosidl_default_runtime`、`ament_lint_auto`、`ament_lint_common`、`git`、`apr` |
| `lslidar_driver` | 4.2.3 | `driver/leishen_ws/src/Lslidar_ROS2_driver-C16_V4.0/lslidar_driver/package.xml` | `ament_cmake`、`angles`、`pcl_conversions`、`pluginlib`、`rclcpp`、`sensor_msgs`、`rclpy`、`std_msgs`、`rslidar_input`、`libpcl-all-dev`、`lslidar_msgs`、`libpcap`、`message_runtime`、`libpcl-all` |
| `lslidar_msgs` | 3.0.1 | `driver/leishen_ws/src/Lslidar_ROS2_driver-C16_V4.0/lslidar_msgs/package.xml` | `ament_cmake`、`rosidl_default_generators`、`builtin_interfaces`、`sensor_msgs`、`rosidl_default_runtime`、`std_msgs`、`ament_lint_auto`、`ament_lint_common` |
| `orbbec_camera` | 1.4.2 | `driver/orbbec_ws/src/orbbec_camera/package.xml` | `ament_cmake`、`ament_lint_auto`、`ament_lint_common`、`ament_index_cpp`、`image_transport`、`image_publisher`、`rclcpp_components`、`cv_bridge`、`camera_info_manager`、`orbbec_camera_msgs`、`builtin_interfaces`、`rclcpp`、`sensor_msgs`、`std_msgs`、`std_srvs`、`tf2`、`tf2_ros`、`tf2_sensor_msgs`、`tf2_msgs` |
| `orbbec_camera_msgs` | 1.2.2 | `driver/orbbec_ws/src/orbbec_camera_msgs/package.xml` | `ament_cmake`、`ament_lint_auto`、`ament_lint_common`、`rosidl_default_generators`、`sensor_msgs`、`std_msgs`、`rosidl_default_runtime` |
| `orbbec_description` | 0.0.0 | `driver/orbbec_ws/src/orbbec_description/package.xml` | `ament_cmake`、`ament_lint_auto`、`ament_lint_common` |
| `realsense2_camera` | 3.2.3 | `driver/realsense_ws/src/realsense2_camera/package.xml` | `ament_cmake`、`eigen`、`builtin_interfaces`、`cv_bridge`、`image_transport`、`librealsense2`、`rclcpp`、`rclcpp_components`、`realsense2_camera_msgs`、`sensor_msgs`、`geometry_msgs`、`std_msgs`、`std_srvs`、`nav_msgs`、`tf2`、`tf2_ros`、`diagnostic_updater`、`launch_ros`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common`、`libopencv-dev`、`ros_environment` |
| `realsense2_camera_msgs` | 3.2.3 | `driver/realsense_ws/src/realsense2_camera_msgs/package.xml` | `ament_cmake`、`rosidl_default_generators`、`builtin_interfaces`、`std_msgs`、`rosidl_default_runtime`、`ament_lint_common` |
| `realsense2_description` | 3.2.3 | `driver/realsense_ws/src/realsense2_description/package.xml` | `ament_cmake`、`rclcpp`、`rclcpp_components`、`realsense2_camera_msgs`、`launch_ros`、`xacro`、`ament_lint_auto`、`ament_lint_common` |

## fast_gicp

[目录笔记](fast_gicp.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `fast_gicp` | 0.0.0 | `fast_gicp/src/fast_gicp/package.xml` | `ament_cmake`、`ros_environment`、`libpcl-all-dev`、`eigen` |
| `sophus` | 1.1.0 | `fast_gicp/src/fast_gicp/thirdparty/Sophus/package.xml` | `cmake`、`eigen` |

## grid_map_foxy

[目录笔记](grid_map_foxy.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `grid_map` | 2.0.0 | `grid_map_foxy/src/grid_map/package.xml` | `ament_cmake`、`grid_map_core`、`grid_map_ros`、`grid_map_cv`、`grid_map_msgs`、`grid_map_filters`、`grid_map_visualization`、`grid_map_rviz_plugin`、`grid_map_loader`、`grid_map_demos` |
| `grid_map_cmake_helpers` | 2.0.0 | `grid_map_foxy/src/grid_map_cmake_helpers/package.xml` | `ament_cmake_core` |
| `grid_map_core` | 2.0.0 | `grid_map_foxy/src/grid_map_core/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`eigen`、`ament_cmake_gtest`、`ament_lint_common`、`ament_lint_auto` |
| `grid_map_costmap_2d` | 1.6.2 | `grid_map_foxy/src/grid_map_costmap_2d/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_core`、`nav2_costmap_2d`、`geometry_msgs`、`tf2_ros`、`tf2_geometry_msgs`、`ament_cmake_gtest`、`ament_lint_common`、`ament_lint_auto` |
| `grid_map_cv` | 2.0.0 | `grid_map_foxy/src/grid_map_cv/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_core`、`cv_bridge`、`filters`、`pluginlib`、`rclcpp`、`sensor_msgs`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_demos` | 2.0.0 | `grid_map_foxy/src/grid_map_demos/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`cv_bridge`、`geometry_msgs`、`grid_map_core`、`grid_map_cv`、`grid_map_filters`、`grid_map_loader`、`grid_map_msgs`、`grid_map_octomap`、`grid_map_ros`、`grid_map_rviz_plugin`、`grid_map_visualization`、`octomap_msgs`、`rclcpp`、`sensor_msgs`、`rclpy`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_filters` | 2.0.0 | `grid_map_foxy/src/grid_map_filters/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`filters`、`grid_map_core`、`grid_map_msgs`、`grid_map_ros`、`pluginlib`、`tbb`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_loader` | 2.0.0 | `grid_map_foxy/src/grid_map_loader/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_msgs`、`grid_map_ros`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_msgs` | 2.0.0 | `grid_map_foxy/src/grid_map_msgs/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`rclcpp`、`std_msgs`、`geometry_msgs`、`rosidl_default_generators` |
| `grid_map_octomap` | 2.0.0 | `grid_map_foxy/src/grid_map_octomap/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_core`、`octomap`、`ament_cmake_gtest`、`ament_lint_common`、`ament_lint_auto` |
| `grid_map_pcl` | 2.0.0 | `grid_map_foxy/src/grid_map_pcl/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_core`、`grid_map_msgs`、`grid_map_ros`、`rclcpp`、`rcutils`、`yaml-cpp`、`libpcl-all`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_ros` | 2.0.0 | `grid_map_foxy/src/grid_map_ros/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`cv_bridge`、`geometry_msgs`、`grid_map_core`、`grid_map_cv`、`grid_map_msgs`、`nav2_msgs`、`nav_msgs`、`rclcpp`、`rcutils`、`rosbag2_cpp`、`sensor_msgs`、`std_msgs`、`tf2`、`visualization_msgs`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_rviz_plugin` | 2.0.0 | `grid_map_foxy/src/grid_map_rviz_plugin/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`qtbase5-dev`、`grid_map_msgs`、`grid_map_ros`、`rclcpp`、`rviz_common`、`rviz_ogre_vendor`、`rviz_rendering`、`libqt5-core`、`libqt5-gui`、`libqt5-widgets`、`ament_lint_auto`、`ament_lint_common` |
| `grid_map_sdf` | 2.0.0 | `grid_map_foxy/src/grid_map_sdf/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_core`、`ament_cmake_gtest`、`ament_lint_common`、`ament_lint_auto` |
| `grid_map_visualization` | 2.0.0 | `grid_map_foxy/src/grid_map_visualization/package.xml` | `ament_cmake`、`grid_map_cmake_helpers`、`grid_map_core`、`grid_map_msgs`、`grid_map_ros`、`nav_msgs`、`rclcpp`、`sensor_msgs`、`visualization_msgs`、`ament_cmake_gtest`、`ament_lint_auto`、`ament_lint_common` |

## nav

[目录笔记](nav.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `dr_nav2` | 0.0.0 | `nav/src/dr_nav2/package.xml` | `ament_cmake` |
| `hdl_global_localization` | 0.0.0 | `nav/src/hdl_global_localization/package.xml` | `ament_cmake`、`rosidl_default_generators`、`rosidl_default_runtime`、`rclcpp`、`rclcpp_components`、`ament_index_cpp`、`pcl_conversions`、`pcl_ros`、`nav_msgs`、`sensor_msgs`、`geometry_msgs`、`libopencv-dev` |
| `hdl_localization` | 0.0.0 | `nav/src/hdl_localization/package.xml` | `ament_cmake`、`rosidl_default_generators`、`rosidl_default_runtime`、`rclcpp`、`rclcpp_components`、`ament_index_cpp`、`pcl_conversions`、`pcl_ros`、`nav_msgs`、`sensor_msgs`、`geometry_msgs`、`std_srvs`、`ndt_omp`、`fast_gicp`、`hdl_global_localization`、`pcl`、`tf2`、`tf2_ros`、`tf2_eigen`、`tf2_geometry_msgs` |
| `sensor_test` | 0.0.0 | `nav/src/sensor_test/package.xml` | `ament_cmake_auto`、`rclcpp`、`sensor_msgs`、`rosidl_default_generators`、`rosidl_default_runtime` |

## navigation2-foxy

[目录笔记](navigation2-foxy.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `costmap_queue` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/costmap_queue/package.xml` | `ament_cmake`、`nav2_common`、`nav2_costmap_2d`、`rclcpp`、`ament_lint_common`、`ament_lint_auto`、`ament_cmake_gtest` |
| `dwb_core` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/dwb_core/package.xml` | `ament_cmake`、`nav2_common`、`rclcpp`、`std_msgs`、`geometry_msgs`、`nav_2d_msgs`、`dwb_msgs`、`nav2_costmap_2d`、`pluginlib`、`sensor_msgs`、`visualization_msgs`、`nav_2d_utils`、`nav_msgs`、`tf2_ros`、`nav2_util`、`nav2_core`、`ament_lint_common`、`ament_lint_auto` |
| `dwb_critics` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/dwb_critics/package.xml` | `ament_cmake`、`nav2_common`、`angles`、`nav2_costmap_2d`、`nav2_util`、`costmap_queue`、`dwb_core`、`geometry_msgs`、`nav_2d_msgs`、`nav_2d_utils`、`pluginlib`、`rclcpp`、`sensor_msgs`、`ament_lint_common`、`ament_lint_auto` |
| `dwb_msgs` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/dwb_msgs/package.xml` | `ament_cmake`、`builtin_interfaces`、`geometry_msgs`、`nav_2d_msgs`、`std_msgs`、`nav_msgs`、`rosidl_default_runtime` |
| `dwb_plugins` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/dwb_plugins/package.xml` | `ament_cmake`、`nav2_common`、`angles`、`dwb_core`、`nav_2d_msgs`、`nav_2d_utils`、`pluginlib`、`rclcpp`、`nav2_util`、`ament_lint_common`、`ament_lint_auto`、`ament_cmake_gtest` |
| `nav_2d_msgs` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/nav_2d_msgs/package.xml` | `rosidl_default_runtime`、`ament_cmake`、`geometry_msgs`、`std_msgs`、`rosidl_default_generators` |
| `nav_2d_utils` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/nav_2d_utils/package.xml` | `ament_cmake`、`nav2_common`、`geometry_msgs`、`nav_2d_msgs`、`nav_msgs`、`tf2`、`tf2_geometry_msgs`、`nav2_msgs`、`nav2_util`、`ament_lint_common`、`ament_lint_auto` |
| `nav2_bt_navigator` | 0.4.7 | `navigation2-foxy/src/nav2_bt_navigator/package.xml` | `tf2_ros`、`ament_cmake`、`nav2_common`、`rclcpp`、`rclcpp_action`、`rclcpp_lifecycle`、`nav2_behavior_tree`、`nav_msgs`、`nav2_msgs`、`behaviortree_cpp_v3`、`std_msgs`、`geometry_msgs`、`std_srvs`、`nav2_util`、`ament_lint_common`、`ament_lint_auto` |
| `nav2_dwb_controller` | 0.4.7 | `navigation2-foxy/src/nav2_dwb_controller/nav2_dwb_controller/package.xml` | `ament_cmake`、`costmap_queue`、`dwb_core`、`dwb_critics`、`dwb_msgs`、`dwb_plugins`、`nav_2d_msgs`、`nav_2d_utils` |
| `nav2_regulated_pure_pursuit_controller` | 0.4.7 | `navigation2-foxy/src/nav2_regulated_pure_pursuit_controller/package.xml` | `ament_cmake`、`nav2_common`、`nav2_core`、`nav2_util`、`nav2_costmap_2d`、`rclcpp`、`geometry_msgs`、`nav2_msgs`、`pluginlib`、`tf2`、`ament_cmake_gtest`、`ament_lint_common`、`ament_lint_auto` |
| `nav2_rviz_plugins` | 0.4.7 | `navigation2-foxy/src/nav2_rviz_plugins/package.xml` | `ament_cmake`、`qtbase5-dev`、`geometry_msgs`、`nav2_util`、`nav2_lifecycle_manager`、`nav2_msgs`、`nav_msgs`、`pluginlib`、`rclcpp`、`rclcpp_lifecycle`、`resource_retriever`、`rviz_common`、`rviz_default_plugins`、`rviz_ogre_vendor`、`rviz_rendering`、`std_msgs`、`tf2_geometry_msgs`、`visualization_msgs`、`libqt5-core`、`libqt5-gui`、`libqt5-opengl`、`libqt5-widgets`、`ament_lint_common`、`ament_lint_auto` |

## ndt_omp

[目录笔记](ndt_omp.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `ndt_omp` | 0.0.0 | `ndt_omp/src/ndt_omp/package.xml` | `ament_cmake_auto`、`libpcl-all-dev` |

## slam

[目录笔记](slam.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `faster_lio` | 0.0.0 | `slam/src/faster_lio/package.xml` | `ament_cmake`、`geometry_msgs`、`nav_msgs`、`rclcpp`、`std_msgs`、`sensor_msgs`、`tf2_ros`、`pcl_ros`、`faster_lio_interface`、`message_generation`、`message_runtime`、`ament_lint_auto`、`ament_lint_common`、`rosidl_default_generators`、`rosidl_default_runtime` |
| `faster_lio_interface` | 2.0.0 | `slam/src/faster_lio_interface/package.xml` | `ament_cmake`、`rosidl_default_generators`、`rosidl_default_runtime`、`rclcpp`、`std_msgs`、`pcl_ros`、`rosbag`、`sensor_msgs`、`git`、`apr`、`ament_lint_auto`、`ament_lint_common` |
| `octomap_mapping` | 2.0.0 | `slam/src/octomap_mapping/octomap_mapping/package.xml` | `ament_cmake`、`octomap_server`、`ament_lint_auto`、`ament_lint_common` |
| `octomap_server` | 2.0.0 | `slam/src/octomap_mapping/octomap_server/package.xml` | `ament_cmake_auto`、`geometry_msgs`、`libpcl-all-dev`、`message_filters`、`nav_msgs`、`octomap`、`octomap_msgs`、`octomap_ros`、`pcl_conversions`、`pcl_ros`、`rclcpp`、`rclcpp_components`、`sensor_msgs`、`std_msgs`、`std_srvs`、`tf2`、`tf2_eigen`、`tf2_geometry_msgs`、`tf2_ros`、`visualization_msgs`、`ament_lint_auto`、`ament_lint_common` |
| `pcd2grid` | 0.0.0 | `slam/src/pcd2grid/package.xml` | `ament_cmake` |

## transfer

[目录笔记](transfer.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `transfer` | 0.0.0 | `transfer/src/transfer/package.xml` | `ament_cmake`、`rclcpp`、`rosidl_default_generators`、`rosidl_default_runtime`、`rosidl_interface_packages`、`transfer_interfaces`、`ament_lint_auto`、`ament_lint_common` |
| `transfer_interfaces` | 0.0.0 | `transfer/src/transfer_interfaces/package.xml` | `ament_cmake`、`rclcpp`、`rosidl_default_generators`、`rosidl_default_runtime`、`rosidl_interface_packages`、`ament_lint_auto`、`ament_lint_common` |

## voa

[目录笔记](voa.md)

| 包名 | 版本 | package.xml 路径 | 清单声明的依赖（去重） |
| --- | --- | --- | --- |
| `voa` | 0.0.0 | `voa/src/voa/package.xml` | `ament_cmake`、`rclcpp`、`rclpy`、`grid_map_core`、`grid_map_ros`、`grid_map_cv`、`grid_map_filters`、`grid_map_loader`、`grid_map_msgs`、`grid_map_octomap`、`grid_map_rviz_plugin`、`grid_map_visualization`、`std_msgs`、`nav_msgs`、`geometry_msgs`、`sensor_msgs`、`ament_lint_auto`、`ament_lint_common` |

## 无 package.xml 的一级目录

pipeline、system、track 没有 ROS 包清单，但仍分别含 ROS Python 应用、聚合脚本和跟踪应用，均有独立笔记。driver/Livox_SDK2 是非 ROS CMake 库。Sophus 为内嵌数学库，不按独立部署节点计算。

## 复核口径

排除 build/install 中复制或生成的 package.xml，避免把同一个包重复计数；不以目录名带 ROS2 与否判断包归属。ROS1 遗留源文件、禁用 CMake 目标与接口定义都保留说明，但不计作已启用 ROS2 节点。

