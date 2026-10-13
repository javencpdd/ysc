# fast_gicp：高速点云配准库

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/fast_gicp`。

## 1. 目录与定位

`src/fast_gicp` 是主包，include/fast_gicp 提供公共头文件，src/fast_gicp 包含 GICP、VGICP 与 CUDA/NDT 实现；src/align.cpp、kitti.cpp 是离线应用；thirdparty 存放数学和 GPU 辅助依赖。

另在 `src/fast_gicp/thirdparty/Sophus/package.xml` 发现 sophus 1.1.0。它嵌套于已有包内部，未作为独立包出现在本次 colcon list 中，但仍计入 50 份清单。Sophus 的 CMake 定义头文件 INTERFACE 库，依赖 Eigen，不是 ROS 节点。

主消费者是 nav/hdl_localization 的配准模块。当前定位 launch 选择 NDT_OMP，所以“链接 fast_gicp”与“正在使用 GPU 配准”不是一回事。

## 2. 主要类与调用

| 类/模块 | 作用 |
| --- | --- |
| LsqRegistration | 非线性最小二乘配准基础、线性化与位姿增量优化 |
| FastGICP / FastGICPSingleThread | 估计源/目标局部协方差，通过马氏距离误差配准 |
| FastVGICP | 把目标点组织为高斯体素，减少逐点匹配开销 |
| FastVGICPCuda | CUDA 加速体素 GICP |
| NDTCuda | GPU NDT 的 P2D/D2D 路径 |
| CUDA kernels | kNN、协方差、体素对应、导数及误差计算 |
| Sophus::SE3 / SO3 | 旋转/刚体变换表示；SE3Base 组合 SO3 与三维平移 |

典型调用顺序为 setInputTarget → setInputSource → 配置分辨率/线程/邻域 → align → getFinalTransformation。源/目标方向与初始估计必须保持一致；该库不会自行提供机器人 frame 或处理传感器时间同步。

重点源码：`include/fast_gicp/gicp/`、`src/fast_gicp/gicp/`、`src/fast_gicp/cuda/`、`src/fast_gicp/ndt/ndt_cuda.cpp`；Sophus 数学入口为 `thirdparty/Sophus/sophus/se3.hpp`、so3.hpp。

## 3. 构建配置

| CMake 选项 | 本地源码默认值 | 含义 |
| --- | --- | --- |
| BUILD_VGICP_CUDA | ON | 查找 CUDA，构建 fast_vgicp_cuda 并链接 cuBLAS |
| BUILD_apps | ON | 构建 gicp_align、gicp_kitti |
| BUILD_test | OFF | GTest 测试默认不构建 |
| BUILD_PYTHON_BINDINGS | OFF | pygicp/pybind11 默认关闭 |
| CMAKE_BUILD_TYPE | Release | 源码中设置 |

主要依赖 PCL、Eigen3、OpenMP；按 ROS_VERSION 选择 catkin 或 ament。当前 aarch64 环境还需实际 CUDA 工具链和兼容架构。选项默认开启不等于已有 install 必定由相同选项构建。

Sophus 自身 CMake 的 BUILD_TESTS/BUILD_EXAMPLES 默认 ON，与 fast_gicp 的 BUILD_test 不是同一个参数；不能混淆。

## 4. ROS 接口与运行方式

该包在此工程中是 C++ 库，**没有自行发布的 Topic、ROS Service 或 Action，也没有机器人生产 launch**。离线程序不是 ROS 订阅节点。

已有安装供其他工作区使用：

```bash
source /opt/ros/foxy/setup.bash
source /home/ysc/lite_cog_ros2/fast_gicp/install/setup.bash
```

维护性重建入口是在该工作区执行 colcon build；本次没有执行。CMake 的 ament 安装段安装库和头文件，没有把 gicp_align/gicp_kitti 加入 ROS 可执行安装项，因此不应直接承诺 `ros2 run fast_gicp gicp_align` 可用。离线程序应从实际构建输出定位，并按源码要求提供数据。

