# system：启动脚本与地图约定

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/system`。

## 1. 定位与结构

本目录没有 package.xml/CMakeLists.txt，不是 ROS 包；通过 shell 脚本串联其他工作区。

```text
system/
├── scripts/
│   ├── depth_camera/realsense/start_realsense.sh
│   ├── lidar/start_livox.sh、start_lslidar.sh
│   ├── transfer/start_transfer.sh
│   ├── voa/start_voa.sh
│   ├── nav/start_nav.sh
│   └── slam/start_slam.sh、gridmap.sh、save_map.sh
└── map/lite3.yaml
```

脚本精确路径见[采集文件索引](source-files.md)；角色是选择环境与进程入口，没有自己的节点类、ROS Topic、Service 或 Action。

## 2. 启动关系

| 脚本 | 实际目标 | 特别注意 |
| --- | --- | --- |
| start_transfer.sh | transfer/transfer_launch.py | UDP 端口不可被其他实例占用 |
| start_voa.sh | voa/voa_launch.py | 需要深度点云、IMU、里程计等输入 |
| start_realsense.sh | realsense2_camera/dr_camera_launch.py | 已补齐并由 install 链接读取；默认 424×240@30 深度流与无纹理点云，不自动载入 d435i.yaml；硬件未启动验证 |
| start_livox.sh | livox_ros_driver2/msg_MID360s_launch.py | MID360s 配置、雷达 IP 与外参 |
| start_lslidar.sh | lslidar_driver/lslidar_c16_launch.py | 与 Livox 通常二选一 |
| start_nav.sh | hdl_localization/lite_localization.launch.py | source navigation2-foxy 后 source nav |
| start_slam.sh | gnome-terminal 打开建图、gridmap、save_map 三条支线 | 需要图形会话；不是自动完成全部建图步骤 |
| gridmap.sh | 输入 1 后启动 pcd2grid | 依赖已保存 PCD |
| save_map.sh | 输入 2 后调用保存地图服务 | 先删除旧 pgm/yaml，需谨慎 |

多个脚本设置 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp，并设置 ROS_LOG_DIR；transfer 日志走 system/log，部分模块走各自 run_log。部分脚本后台执行 launch，shell 返回不代表节点已成功就绪；部分脚本依赖父进程已配置 ROS 环境。

## 3. 地图参数与保存

当前 lite3.yaml：

- image 为绝对路径 `/home/ysc/lite_cog_ros2/system/map/lite3.pgm`；
- resolution=0.05，origin=[-37.7,-4.1,0]，negate=0；
- 保存脚本使用 /projected_map，格式 pgm，模式 trinary，free_thresh=0.25、occupied_thresh=0.65。

实际目录中未见 lite3.pgm 和 lite3.pcd。仅有 YAML 元数据不足以启动默认地图链。复制到其他路径或主机后，也必须检查 YAML 内 image 的绝对路径。

save_map.sh 调用 `/map_saver_server/save_map`，类型 nav2_msgs/srv/SaveMap；服务由 pcd2grid 启动的 Nav2 进程提供。脚本本身不是服务端。它在调用服务前移除旧 PGM/YAML，保存超时或服务缺失可能导致旧图丢失。

## 4. 使用方式与维护边界

入口形式是 `bash /home/ysc/lite_cog_ros2/system/scripts/<模块>/<脚本>.sh`；操作前读脚本，不要一次批量启动所有项。

建议顺序：确认 Foxy 环境与 RMW → 选择传感器驱动 → 确认 transfer 状态输入 → 按目的选择建图或定位导航 → 最后选择控制源/VOA。具体步骤受硬件状态和安全条件约束，不是本次已通过的启动测试。

这里没有声明或安装 systemd unit；不能因脚本存在就推断同名服务存在。Jetson2App 代码另调用 realsense_ros2.service、voa_ros2.service，需去 systemd 配置中单独核验，不能把 system/scripts 当成 unit 的等价物。
