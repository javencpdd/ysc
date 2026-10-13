# ROS 1：SLAM 与地图

## 目录定位与职责

`/home/ysc/lite_cog/slam` 负责将雷达/IMU 数据交给 Faster-LIO 建图，再用 `pcd2grid` 生成二维栅格；`system/map` 是定位、导航与保存脚本共享的地图交付目录。

## 脚本清单与流程

| 脚本 | 参数/交互 | 执行流程 |
| --- | --- | --- |
| `system/scripts/slam/start_slam.sh` | 无位置参数，要求图形桌面 | 新开 3 个 `gnome-terminal`：Faster-LIO、`gridmap.sh`、`save_map.sh`。 |
| `gridmap.sh` | 仅输入 `1` 才执行 | source `slam/devel/setup.bash`，运行 `roslaunch pcd2grid pcd2grid.launch`。 |
| `save_map.sh` | 仅输入 `2` 才执行 | source 环境，运行 `rosrun map_server map_saver -f /home/ysc/lite_cog/system/map/lite3`。 |

`start_slam.sh` 是交互式编排器而非守护进程：建图终端、栅格终端、地图保存终端互不管理；用户需要在对应窗口输入 `1` 或 `2`。

## 核心模块与依赖

```text
lslidar/livox 点云 + IMU
  -> faster_lio/run_mapping_online（mapping_c16.launch）
  -> 点云地图/在线点云
  -> pcd2grid
  -> /projected_map 等二维地图
  -> map_server/map_saver
  -> system/map/lite3.yaml + lite3.pgm + 相关 PCD
  -> hdl_localization 与 navigation
```

- `faster-lio`：上游 Faster-LIO 算法代码，目录本身按第三方算法处理；集成层使用 `mapping_c16.launch`，加载 `config/c16.yaml`，运行 `run_mapping_online`，默认开启 RViz。
- `pcd2grid`：本地 Catkin 包，用于从点云/OctoMap 结果生成二维占据栅格。
- `map_server`、`octomap_mapping`：ROS 上游地图服务/OctoMap 组件；在本项目中是栅格输出和保存的依赖。

## 关键配置

`mapping_c16.launch`：禁用特征提取；点过滤 `4`；最大迭代 `3`；表面/地图滤波 `0.5`；地图立方体边长 `1000`；不输出运行位置日志。不同雷达的 `mapping_avia`、`mapping_ouster64`、`mapping_velodyne*` 仅切换 YAML/点过滤及节点配置。

## 风险与硬编码

1. **桌面依赖**：`gnome-terminal -x` 在无 DISPLAY、SSH 或 systemd 中会失败。
2. **交互门槛**：`gridmap.sh`/`save_map.sh` 对非预期输入只打印 `wrong`，没有退出码约束或自动化接口。
3. **地图覆盖**：`map_saver -f .../lite3` 会覆盖同名输出，保存前应备份现有地图。
4. **地图一致性**：导航定位要求 YAML 与 PCD 均为同一地图版本；仅保存 pgm/yaml 不会自动生成/更新 PCD。
5. **传感器型号耦合**：默认启动 C16 mapping；启动其他雷达时应明确选择对应 launch。
