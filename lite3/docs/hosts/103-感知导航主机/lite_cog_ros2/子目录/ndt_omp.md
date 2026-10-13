# ndt_omp：OpenMP 点云配准

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/ndt_omp`；唯一包为 `src/ndt_omp`。

## 1. 结构与用途

- CMakeLists.txt、package.xml：ROS1/ROS2 条件构建。
- include/pclomp：NDT、GICP、协方差体素及模板实现。
- src/pclomp/{ndt_omp.cpp,gicp_omp.cpp,voxel_grid_covariance_omp.cpp}：库源文件。
- apps/align.cpp：对齐示例，当前仅 ROS1 CMake 分支创建 align 可执行程序。

它是 nav/hdl_localization 当前 NDT_OMP 模式的底层配准依赖，不读取雷达设备，也不保存导航地图。

## 2. 核心类与函数

| 类 | 功能 |
| --- | --- |
| pclomp::NormalDistributionsTransform | 把目标点云组织成高斯分布体素，优化源点云到目标的变换 |
| pclomp::VoxelGridCovariance | 体素内均值/协方差与近邻访问 |
| pclomp::GeneralizedIterativeClosestPoint | 结合源/目标协方差的 GICP 优化 |

使用者调用 setInputTarget/setInputSource、setResolution、setNumThreads、setNeighborhoodSearchMethod，再 align 和 getFinalTransformation。NDT 的 KDTREE、DIRECT7、DIRECT1 是邻域搜索选择，不是三个独立 ROS 节点。

hdl_localization 当前参数为 NDT_OMP、DIRECT1、分辨率 1.5；地图/扫描降采样由上层另行配置。线程数、迭代限制、收敛阈值也由调用者设置，不是本包全局 ROS 参数。

## 3. 构建与依赖

CMake 选择 C++14、Release、PCL（最低要求 1.7）和 OpenMP。ROS2 分支用 ament_cmake_auto 构建并导出共享库 ndt_omp；本机系统 PCL 为 1.10.0，不能把最低版本当成实际版本。

非 aarch64 分支设置 SSE 选项，aarch64 下绕过这一设置；BUILD_WITH_MARCH_NATIVE 是另一构建分支。迁移平台时要检查编译参数，不能照搬 x86 指令集。

## 4. 接口、运行与边界

没有独立 Topic、Service、Action 或 ROS2 launch；输入输出是 C++ 点云对象与变换矩阵。库的线程并行不承担上层消息同步或 TF 发布。

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/ndt_omp/install/setup.bash
```

随后由 nav 的定位节点调用。需要重建时在 ndt_omp 工作区运行 colcon build，但本文未执行构建或基准测试。ROS2 分支未创建 align 程序，不能把 ROS1 示例命令当作 Foxy 的既有运行入口。

