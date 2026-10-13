# lite_cog_ros2 源码导读

本组笔记对应 103 感知导航主机的 `/home/ysc/lite_cog_ros2`，按一级目录组织，覆盖传感器、建图、定位、导航、近场避障、视觉跟随与机器人通信。

## 1. 调查范围与可信度

- 整理日期：2026-09-16；通过 `mcp-ssh-apply-patch` 只读采集源码、配置和环境信息。
- 用户指定名称为 `user-f20-103`；本地实际可用 SSH 别名是 `lite3-f20-1-103`，连接 `ysc@192.168.1.103`，远端 hostname 为 `lite`。
- 本次按确认安装了本机已有 SSH 公钥；没有修改机器人业务源码、安装依赖、构建工程或启动运动节点。
- 清点全部 **12 个一级目录、50 份 package.xml**；其中 **49 个包可被 colcon 发现**，另一个为 fast_gicp 内嵌的 Sophus。无不可访问的一级目录。
- 逐包核对 package.xml、CMakeLists.txt、启动/配置和主要实现；接口以源码创建调用、launch 重映射与实际安装脚本为依据。读取清单见[采集文件索引](source-files.md)，完整包清单见[功能包清单](packages.md)。
- 这是静态源码与部署文件分析，**不是运行验收**。没有测量实时 Topic、帧率、TF 连通性、定位精度或机器人制动效果；文中运行命令未执行。
- build/install/log/run_log、Git 元数据、二进制模型/地图不作逐行源码分析。vendor SDK、Ultralytics、IKFoM 等第三方实现按边界与主调用关系说明，不等于逐行审计其所有内部代码。

## 2. 整体定位与技术栈

这不是一个统一的 colcon 工作区，而是一组相互依赖的子工作区和直接运行的 Python 应用。各工作区存在自己的 src、build、install 等目录；不能仅凭顶层文件夹名判断它是否是 ROS 包。

| 层次 | 本机核验/源码依据 |
| --- | --- |
| 系统 | Ubuntu 20.04.6，aarch64，Jetson L4T R35.4.1 |
| ROS | 主链使用 ROS 2 Foxy；系统同时安装 Noetic，不能混用两套环境 |
| 中间件 | 启动脚本选择 `rmw_cyclonedds_cpp`，本机可解析该包 |
| 构建 | ament_cmake、colcon、CMake；C++ 与 Python 3；部分上游库保留 ROS 1 分支 |
| 数学/点云 | Eigen 3.3.7、PCL 1.10.0；OpenMP、TBB、Sophus、OctoMap、grid_map |
| 导航 | Foxy Nav2 0.4.7；局部源码覆盖 BT/DWB/RViz 等，其他组件来自 /opt/ros/foxy |
| 图像/推理 | 发行版 OpenCV 4.2.0；源码还依赖 CUDA、TensorRT、Ultralytics、GStreamer/NVIDIA 解码插件 |
| 硬件 SDK | Livox SDK2、librealsense2、Orbbec SDK；包存在不代表相机/雷达已在线 |

OpenCV 的系统包版本不能证明 Python 实际导入版本或 CUDA 功能；TensorRT engine 也不能仅凭文件存在认定与当前设备匹配。

## 3. 目录概览与索引

下表列全一级目录；结构只展示有意义的源码入口，省略重复构建产物。

| 文件夹 | 核心结构 | 功能一句话概述 | 包数 | 对应笔记 |
| --- | --- | --- | ---: | --- |
| driver | mid360_ws、leishen_ws、realsense_ws、orbbec_ws、Livox_SDK2 | 雷达与深度相机驱动 | 9 | [driver.md](driver.md) |
| fast_gicp | src/fast_gicp | 高速点云配准库及内嵌 Sophus | 1+1 内嵌 | [fast_gicp.md](fast_gicp.md) |
| grid_map_foxy | src 下 15 个包 | 多层栅格地图核心、转换、滤波与显示 | 15 | [grid_map_foxy.md](grid_map_foxy.md) |
| nav | src/{dr_nav2,hdl_localization,hdl_global_localization,sensor_test} | 点云定位与整机导航配置 | 4 | [nav.md](nav.md) |
| navigation2-foxy | src 下 Nav2 与 DWB 包 | 本地修改的导航插件和行为树 | 11 | [navigation2-foxy.md](navigation2-foxy.md) |
| ndt_omp | src/ndt_omp | OpenMP NDT/GICP 配准库 | 1 | [ndt_omp.md](ndt_omp.md) |
| pipeline | src/pipeline、src/data | 航点记录、任务导航与步态命令 | 0 | [pipeline.md](pipeline.md) |
| slam | src 下 faster_lio、pcd2grid、octomap_mapping 等 | 激光惯性建图与 PCD 转二维地图 | 5 | [slam.md](slam.md) |
| system | scripts、map | 聚合启动与地图路径约定 | 0 | [system.md](system.md) |
| track | src、model | RTSP 人体跟踪与速度控制 | 0 | [track.md](track.md) |
| transfer | src/{transfer,transfer_interfaces} | ROS 与运动主机/App 的 UDP 桥接 | 2 | [transfer.md](transfer.md) |
| voa | src/voa | 深度点云栅格化与近场速度修正 | 1 | [voa.md](voa.md) |

## 4. 调用关系与数据流

```text
system/scripts ──组织启动── driver / transfer / voa / slam / nav
driver 雷达 ── /rslidar_points ──┬─ faster_lio + /imu/data → lite3.pcd
                               ├─ hdl_localization + lite3.pcd → /odom、map→base_link
                               └─ Nav2 STVL 障碍层
lite3.pcd → my_octomap → /projected_map → map_saver_server → lite3.pgm + lite3.yaml
lite3.yaml → map_server → /map → Nav2 规划/控制
pipeline 航点 ── NavigateToPose Action ── Nav2 → /cmd_vel
120 主机 RTSP ── track/YOLO ─────────────────→ /cmd_vel
深度相机 → voa/PointCloudProcessor → GridMapper → /grid_map
/imu/data、/leg_odom2、/handle_state、超声 ──→ voa/SafetyController
/cmd_vel ──→ voa ── /cmd_vel_corrected ──→ transfer ── UDP ── 120 运动主机
/cmd_vel ───────────────────────────────→ transfer（同时存在的直接通路）
120 运动主机 ── UDP ── transfer → IMU、腿式里程计、关节、手柄、超声
pipeline/RobotCommander ── 直接 UDP 步态/心跳 ──→ 120（不经过 transfer）
```

这张图表示源码连接，不代表所有分支应同时启动。雷达驱动通常二选一；Nav2 与 track 同发 cmd_vel 时，源码中未见统一仲裁器。transfer 同时订阅原始和修正速度，**不能据此认定 VOA 必然拥有最终控制权**。

### TF 与消息名易混点

- 定位代码直接广播 `map → base_link`，不应默认套用 `map → odom → base_link`。
- transfer 的 odom TF 广播被注释；`/leg_odom2` 是速度/状态来源之一，不等于定位 TF。
- 建图使用 `camera_init → body` 和大写 `/Odometry`；定位输出小写 `/odom`。它们不能仅靠改话题名互换。
- 雷达 launch 广播 `base_link → rslidar`；Livox 与 C16 的外参配置不同。
- VOA 将点云转换为 `robot_foot_print`，该标识符应保留原拼写。

## 5. 部署中的工作区外依赖

`nav2_bringup`、`nav2_controller`、`nav2_map_server`、`spatio_temporal_voxel_layer` 等来自 `/opt/ros/foxy`；本目录没有完整 Nav2 源码。

额外读取本机 `/opt/ros/foxy/share/nav2_bringup/launch/` 后确认：

1. `localization_launch.py` 的 AMCL Node 已被注释，生命周期列表仅保留 map_server；不是未经修改的上游默认行为。
2. `navigation_launch.py` 通过 RewrittenYaml 重写 use_sim_time 和 default_bt_xml_filename。
3. `bringup_launch.py` 默认将行为树文件解析成包 share 下的绝对路径。因此主启动链不会简单使用 YAML 中的相对 BT 文件名；直接启动 bt_navigator 时则仍须检查路径。

迁移或升级时只备份 lite_cog_ros2 不足以保存这些系统目录改动。

## 6. 已确认的缺项与静态风险

| 类别 | 核验结果 | 影响/边界 |
| --- | --- | --- |
| 启动文件（已补齐） | dr_camera_launch.py 已补入 12847 字节；安装链接同步可见，默认参数求值通过 | 原空文件缺项解除；默认点云与 VOA 输入约定匹配，硬件出流未验证，见 driver 笔记 |
| 地图 | system/map 仅见 lite3.yaml，未见其引用的 lite3.pgm，也未见 lite3.pcd | 默认二维地图与点云定位/转换入口缺输入 |
| 航点 | pipeline/src/data 是空目录 | Task.LoadTaskpoints 无可执行任务；先用记录器或按结构准备 JSON |
| 速度仲裁 | transfer 两个速度 Topic 共用回调，track 丢失目标时没有显式发零速 | 需单独验证控制优先级、超时与停车，不能当作已完成安全链 |
| 保存地图 | save_map.sh 先删除现有 pgm/yaml，再调用保存服务 | 服务失败可能丢失旧二维地图；本次未执行 |
| 环境依赖 | RViz、Qt、gnome-terminal 与 Jetson 插件出现在入口中 | 无图形环境或移植到普通 PC 时不保证直接可运行 |

没有不可读的一级目录，也没有需要跳过的空一级目录。空的 Python `__init__.py` 属于正常包标记，不按功能缺失处理。

## 7. 推荐阅读与复核顺序

先看 [system](system.md) 的入口，再看 [driver](driver.md) 和 [transfer](transfer.md) 的输入；随后区分 [slam](slam.md) 建图、[nav](nav.md) 定位导航，最后阅读 [voa](voa.md)、[pipeline](pipeline.md) 与 [track](track.md)。底层库按问题查阅即可。

运行复核应先只读确认环境和地图、再验证传感器及 TF，最后在有急停和安全场地的条件下测试运动。本文没有授权或执行任何运动测试。不要混用 Noetic/Foxy，不要同时启动同端口的多份 transfer。
