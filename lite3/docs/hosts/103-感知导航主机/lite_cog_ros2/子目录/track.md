# track：视频人体跟踪与跟随控制

[返回总览](README.md)。远端路径：`/home/ysc/lite_cog_ros2/track`。

## 1. 结构与依赖

- `src/run_tracker.py`：视频、检测和控制的主循环。
- `src/GStreamerWrapper/GStreamerWrapper.py`：RTSP 管线和后台取帧。
- `src/RobotController/RobotController.py`：选择跟踪 ID，计算速度并显示结果。
- `src/RobotController/YoloWrapper/`：YOLO tracking 与 COCO 类别。
- `src/RobotController/ROSTransfer/`：ROS1/ROS2 发布适配；当前选择 ROS2。
- `model/`：yolov8n.pt、yolov8n.onnx、yolov8n_amd.engine、yolov8n_arm.engine 与 export_engine.sh；这些文件本次均存在。

该目录没有 package.xml/CMakeLists.txt。Ultralytics/hub_sdk 是随项目携带的 Python 依赖，不是额外 ROS2 功能包；本文分析其调用边界，不逐行审计完整框架。其他依赖包括 OpenCV、NumPy、GObject/GStreamer、Jetson NVIDIA 解码插件、TensorRT、rclpy。

## 2. 主处理流程

run_tracker 创建 GStreamerWrapper 与 RobotController：取帧 → YOLO 检测/跟踪 → 选择 ID → 计算速度 → 显示。GStreamer 使用：

`rtsp://192.168.1.120:8554/test` → H.264 → nvv4l2decoder → NVMM/nvvidconv → BGRx → 640×360 BGR → appsink。

这是读取 120 主机视频的消费者，不是 103 主机上的推流服务器。队列采用丢旧帧策略以控制延迟，但本次没有验证视频实际在线或帧率。

YOLO wrapper 加载相对路径 `../model/yolov8n_arm.engine`，调用 model.track，persist=true、类别为 person、conf=0.5。选择目标由界面按键流程完成；不是任何检测到的人都应被当成已锁定目标。

## 3. 控制与 ROS 接口

ROS2Transfer 创建节点 `track_twist_publisher`，发布 `/cmd_vel`（geometry_msgs/Twist，队列深度 1）。没有自定义 ROS Service 或 Action；ROS1Transfer 是保留的另一适配，kUseRos1Transfer=False 表示当前默认不用它。

- 角速度由目标框水平归一化偏差计算，增益约 1.2，并按代码符号约定输出。
- 前向速度使用目标框上边沿与图像高度的比例及 PD 项，kP=5、kD=0.2；另一分支给出 1.0。
- 这不是基于深度测距的恒定距离跟随；图像位置启发式会受视角、裁剪和遮挡影响。
- 部分速度计算分支没有统一饱和限制，实际限速仍需联动控制链验证。

## 4. 运行和模型导出

在所需 ROS 环境、图形会话与模型依赖已具备时，入口为：

```bash
source /opt/ros/foxy/setup.bash
cd /home/ysc/lite_cog_ros2/track/src
python3 run_tracker.py
```

该入口可能发运动速度，本文未执行。工作目录决定 ../model 路径；不能随意从其他目录运行后把模型找不到归因于 TensorRT。

model/export_engine.sh 使用 `yolo export model=yolov8n.pt format=engine half=True simplify=True`。engine 存在不意味着可在其他 GPU、TensorRT 版本或架构复用；本次未重新导出或加载模型。

## 5. 静态风险

- 目标丢失/停止跟随分支会在图像上绘制零速，但没有在该分支显式发布零 Twist；UI 显示 0 不代表运动端已收到停车命令。
- 初次 GetFrame 可能发生在帧缓存初始化之前；空 sample 和阻塞拉帧/线程停止路径需测试。
- track 与 Nav2 都能发布 /cmd_vel，代码中没有全局仲裁；避免无控制权约定地同时运行。
- 即使接入 VOA，transfer 仍收原始速度，不能假定跟随输出强制经过避障。

