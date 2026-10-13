# GUI、RViz 与 Gazebo

## 显示链路

容器中的 GUI 程序不会自动显示到 Windows。使用 VcXsrv 时，数据路径是：

```text
容器 GUI 程序
  → DISPLAY=host.docker.internal:0.0
  → X11/TCP
  → Windows 上的 VcXsrv
  → 桌面窗口
```

常用环境变量：

```bash
export DISPLAY=host.docker.internal:0.0
export QT_X11_NO_MITSHM=1
```

`QT_X11_NO_MITSHM=1` 用于规避跨 Windows/Linux 边界时 Qt 对本地共享内存的假设。若 GUI 始终正常，也可以测试去掉它。

## 三级验证

不要一开始就运行 RViz 或 Gazebo。按复杂度逐层验证：

```bash
# 1. X11
xeyes

# 2. OpenGL / GLX
glxinfo -B

# 3. Qt + ROS + X11
rosrun turtlesim turtlesim_node
```

如果 `xeyes` 失败，应先检查 `DISPLAY`、VcXsrv 和防火墙；此时修改 `ROS_IP` 没有意义。

## RViz

启动：

```bash
rviz
```

RViz 的显示依赖“消息、时间和坐标系”同时正确。看不到数据时依次检查：

```bash
rostopic list
rostopic echo -n 1 <topic>
rostopic hz <topic>
rosrun tf view_frames
rosrun tf tf_echo <fixed_frame> <sensor_frame>
```

常见原因：

- `Fixed Frame` 选择错误；
- 传感器消息的 `frame_id` 不在 TF 树中；
- TF 时间戳过期或使用了错误的仿真时间；
- PointCloud2 或图像数据量过大，X11 链路成为瓶颈；
- GLX/OpenGL 渲染路径不兼容。

软件渲染可用于诊断：

```bash
LIBGL_ALWAYS_SOFTWARE=1 rviz
```

若软件渲染能启动，问题多半集中在硬件 OpenGL/GLX 路径。软件渲染会占用更多 CPU，不应视为高性能解决方案。

## Gazebo

先验证服务端，再启动界面：

```bash
gzserver --verbose
```

使用 ROS 启动无界面仿真：

```bash
roslaunch gazebo_ros empty_world.launch gui:=false
rostopic list
```

最后测试客户端：

```bash
gzclient --verbose
```

若 `gzserver` 和 ROS topics 正常、只有 `gzclient` 卡顿或崩溃，说明物理仿真与 ROS 插件大概率正常，问题集中在图形客户端或显示链路。

## 性能预期

| 程序 | Windows Docker + VcXsrv 体验 | 主要瓶颈 |
|---|---|---|
| turtlesim / rqt | 通常很好 | DISPLAY、防火墙 |
| RViz 基础场景 | 通常可用 | GLX、坐标系、数据量 |
| RViz 大点云 | 可能明显变慢 | X11、GPU/CPU 渲染 |
| Gazebo `gzserver` | 通常可用 | 物理和传感器的 CPU 负载 |
| Gazebo `gzclient` | 最容易出问题 | X11、OpenGL、GPU |
| 深度相机与复杂世界 | 高度依赖硬件 | 渲染、数据吞吐、内存 |

可用下面的命令区分资源瓶颈：

```powershell
docker stats ros1-noetic
```

```bash
glxinfo -B
```

- `gzserver` CPU 很高：优先检查 physics/sensor 配置；
- `gzserver` 正常但 `gzclient` 卡：优先检查 renderer、X11 和 OpenGL；
- RViz 仅在大点云时卡：降低点数、刷新频率或迁移到 WSLg/原生 Linux。

下一步：[网络、多容器与硬件](06-网络多容器与硬件.md)

