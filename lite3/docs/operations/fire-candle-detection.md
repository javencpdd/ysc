# Lite3 火灾 / 应急蜡烛视觉检测方案

> 范围：在 Lite3 双主机的实际硬件与现有软件栈条件下，设计一套可直接在主机本地运行的"应急蜡烛 / 火焰"检测方案。覆盖数据接入、算法选型、误报抑制、输出与联动、实时性、部署与实机验证。
>
> 依据：`docs/operations/host-maintenance.md`、`docs/hosts/103-感知导航主机/`、`docs/hosts/120-运动控制主机/` 等只读审计报告，采集时间 2026-09-07。
>
> 适用目标：用户提供的应急蜡烛（图：透明玻璃罐装白色蜡烛、单一黄色火苗，可持续照明 26 小时）以及室内应急救援场景下其它近距离点状火焰。

## 1. 主控主机条件提炼

笔记中 LITE3 双主机的角色、算力、内存、操作系统和现有视觉链路如下表，是本方案的硬约束：

| 维度 | user-f20-103 / `lite`（感知/导航侧） | user-f20-120 / `ysc`（运动/视频侧） |
| --- | --- | --- |
| 平台 | NVIDIA L4T R35.4.1，board `t186ref`（Jetson 系列，未无歧义锁定到商业模块名） | Rockchip RK3588 WEB-S3588-YSC-V10 |
| CPU | 6 核 ARMv8，最大 1907.2 MHz | 8 核 Cortex-A55，最大 2208 MHz |
| 内存 / Swap | 6.7 GiB；zram swap 共 3.3 GiB（采集时未用） | 3.8 GiB；无 swap |
| 系统盘 | 116.5 GiB 根分区，已用 65% | 27.9 GiB 根分区，已用 40% |
| 操作系统 | Ubuntu 20.04.6 LTS aarch64；ROS Foxy + Noetic 双栈，`.ros_version.sh` 当前指向 Foxy、Cyclone DDS | Ubuntu 20.04.5 LTS aarch64；未安装 ROS；GStreamer（含 Rockchip 插件）、OpenCV 4.2、RKNN Runtime 已部署 |
| 加速器 | 板载 GPU（CUDA 已在 VOA 中启用）、可推断具备 TensorRT（track 中已用 YOLOv8n engine） | RK3588 NPU（RKNN Runtime + `librknnrt.so` 在 `track/lib`），Rockchip MPP H.264 硬编码 |
| 摄像头接入 | 不直接挂相机；从 120 拉 `rtsp://192.168.1.120:8554/test`（H.264，1280×720@30） | 唯一相机入口 `/dev/video0`，V4L2 MJPEG 1280×720@30，由 GStreamer 解码后经 `mpph264enc` 推 RTSP |
| 现有视觉程序 | `track`（YOLOv8n TensorRT + Ultralytics，GStreamer 拉 RTSP）；VOA（PCL/grid_map + CUDA）；深度相机 RealSense/Orbbec 工作区 | `track`（YOLOv5 + RKNN，闭源 ELF）；`jy_exe` 闭源运动控制；`rtsp_stream` MediaMTX v1.4.2 |
| 与机器狗控制耦合 | `transfer_ros2.service` active，发布/订阅 `cmd_vel`、`cmd_vel_corrected`、`leg_odom2`、`/imu/data`；状态/控制 UDP 端口 43897/43893 与 120 互通 | `jy_exe.service` active，监听 43893；`track` 私有 UDP 控速；急停、CAN 链均在 120 本机 |

**关键限制**：
- 103 的 Jetson 商业模块型号未在笔记中无歧义锁定，需要实机 `cat /etc/nv_tegra_release` 与 `cat /proc/device-tree/model` 二次确认；本方案在推理选型时给出**条件化分支**，避免硬编码算力档位。
- 120 仅有 3.8 GiB 内存且 `track.service` 已经在跑 YOLOv5/RKNN 推理；新增检测模块必须**严格控制常驻内存**，否则会和现有 track 抢资源。
- 103 默认 ROS 2 Transfer 已在跑，新增检测节点应避免与 `jetson2motion` / `sensor_checker` 抢占话题或端口；优先沿用 `rtspclientsink` 拉流而不是另开 V4L2 设备。
- 双主机之间已有 RTSP（视频）和 UDP `43893/43897`（控制/状态）两条链路，新模块应复用它们，不应引入新的网络依赖。

**假设清单（笔记未覆盖的项）**：

| 假设 | 实机验证方式 |
| --- | --- |
| Jetson 板载 GPU ≥ 1.5 TFLOPS FP16（t186ref 常见对应 Nano/TX2 档） | 实机 `cat /proc/device-tree/model`、`cat /sys/devices/gpu.0/*`、`sudo tegrastats`、`dpkg -l \| grep -E 'tensorrt\|cuda'` |
| 103 当前 ROS 2 Cyclone DDS 与新节点 topic 兼容 | `ros2 topic list`、`ros2 daemon stop && ros2 daemon start`；新节点 source `~/.ros_version.sh` |
| 120 的 RKNN NPU 对自定义模型开放（不锁死厂商签名） | `strings /usr/lib/librknnrt.so \| head`、检查 `track/model` 是否含 RKNN 模型；不在 `track/lib` 之外的私有 SDK 范围内重新训练 |
| 120 的 `/dev/video0` 在 `track` 工作时仍可被新检测模块以 V4L2 独占占用 | `v4l2-ctl --list-devices`、`v4l2-ctl --device=/dev/video0 --list-formats`；避免同时打开两次造成冲突 |
| 双机时钟基本同步（视频帧时间戳可对齐） | 实测 `ntpq` / `date`；若不同步则在 103 端以 RTSP 帧 PTS 为单一时间源 |

## 2. 整体架构与运行模式

方案给出**三种部署形态**，按"在哪台主机跑"划分。三种形态**互斥**，一次任务只跑一种，避免双机重复推理与告警冲突。

### 形态 A：Jetson 103 端检测（推荐默认）

```text
120 /dev/video0 (1280x720 MJPEG)
  -> GStreamer mpph264enc -> MediaMTX :8554/test
                                   │
                                   ▼
103 rtspclientsink (nvv4l2decoder -> nvvidconv -> CUDA)
  -> 预处理（letterbox 640x640，RGB，fp16）
  -> 双路推理：
        L1  颜色+运动预筛 (CPU，每帧 ~1ms)
        L2  YOLOv8n TensorRT (GPU，每帧 30~60ms)
  -> 时序稳定性 + 误报抑制
  -> ROS 2 话题 /candle_detected, /fire_alert
  -> 与现有 transfer/jetson2motion 通过 /cmd_vel_safe 或 service 联动
```

适合：算力相对充裕、需要复杂模型、有 ROS 2 集成需求。

### 形态 B：RK3588 120 端检测（边缘侧）

```text
120 /dev/video0 (MJPEG) ─┐
                         ├─> 多路分支（注意资源）
120 rtsp_stream 已发布流 ─┘
                         │
                         ▼
  fire_detector 进程（独立 systemd unit）
    -> GStreamer v4l2src (jpegdec -> videoconvert -> RGA resize)
    -> RKNN YOLOv5n 火焰定制模型
    -> 报警：本地 UDP -> 103:43897（复用现有 Transfer 状态通道）
         或  本地 UDP -> jy_exe 私有端口触发减速/停车
```

适合：网络不稳定、需要"摄像头+判别"在同一侧降低时延、或 103 算力被 SLAM/导航占用时。

### 形态 C：双机协同（高可靠模式）

120 仅做采集 + 轻量预筛（L1），103 跑 L2 精细判定。L1 在 120 上用 RKNN/CPU 跑出粗候选框（位置、置信度），随 RTSP 流或独立 UDP 通道送到 103；103 在 ROI 区域跑 YOLO 二次确认。

适合：120 资源不足以全帧 YOLO 但又能用 NPU 减负的场景；对告警延迟敏感（每帧端到端 ≤ 150 ms 时此形态优于 B）。

> **默认推荐形态 A**：与现有 `track` 的部署边界不冲突，可直接复用 `pull.sh` 的 GStreamer 拉流脚本和 YOLOv8n TensorRT 链路，工程改动最小。

## 3. 摄像头数据接入与图像预处理

### 3.1 数据接入

无论形态 A/B，视频源都来自 120 的 `/dev/video0`。接入方式：

| 来源 | 形态 A 推荐 | 形态 B 推荐 |
| --- | --- | --- |
| `/dev/video0`（MJPEG） | 不直接打开，避免与 120 `push_video.sh` 抢设备 | `v4l2src io-mode=2 ! jpegdec ! videoconvert ! video/x-raw,RGB,width=640,height=480` |
| `rtsp://192.168.1.120:8554/test`（H.264 1280×720@30） | `rtspsrc latency=30 ! rtph264depay ! h264parse ! nvv4l2decoder ! nvvidconv ! video/x-raw,RGB,width=640,height=480` | 不推荐：自己再解码 H.264 浪费 120 端已做好的 MPP 编码 |

接入参数约束：
- **目标帧率**：5~10 FPS 即可满足"应急场景秒级响应"。降低帧率直接换取检测算力余裕。
- **目标分辨率**：进网络前缩放到 640×480（YOLO 输入）或 416×416（YOLOv5-tiny / RKNN）。注意不要破坏原 16:9 比例，避免火苗畸变。
- **缓冲区**：`max-size-buffers=2`、`latency=30~50ms`。RTSP 抖动缓冲不要过大，避免告警延迟。
- **时钟**：所有时间戳以 103 的 `ros2` 系统时间为准；120 端 L1 输出若有 timestamp 必须用本地时钟，避免双机时间不同步导致误报抑制失准。

### 3.2 预处理

| 处理 | 目的 | 备注 |
| --- | --- | --- |
| Letterbox（保持长宽比缩放到 640×640 或 416×416） | YOLO 标准输入 | 不要用 stretch，否则小火焰被压扁 |
| RGB / BGR 归一化到 [0,1] 或 [0,255] int8 | 满足 TensorRT/RKNN 量化要求 | 火焰检测建议保留 8-bit 颜色信息，不要直接归一化 |
| HSV 色彩空间并行计算 | 给 L1 颜色预筛使用 | 仅算 ROI 区域，避免全帧 HSV 重计算 |
| 直方图均衡（仅 V 通道） | 应对室内强光/逆光 | 注意：若现场有手电直射，可能反而放大误报，需配合 L1 颜色门 |
| 时序差分（前后两帧灰度差） | 检测运动火焰特有的闪烁 | 与 LED 频闪的区分点是：火焰闪烁频率不规则（< 20 Hz，且无固定基频） |

> **不要做**：均值去噪 / 大半径高斯模糊。这会抹掉小火焰（应急蜡烛火苗仅几十像素），是反效果。

## 4. 检测算法选型与算力匹配

### 4.1 双路检测（核心思路）

把"快而粗 + 慢而准"两层串联，是嵌入式火焰检测的标准做法，对应本场景需求：

- **L1 颜色+运动预筛（每帧 < 2 ms）**：基于 HSV 颜色阈值、连通域、时序差分，在全帧快速定位候选区域（最多 5 个）。L1 必须**始终先跑**，其作用是：(a) 排除大面积白色 / 灰色 / 蓝色干扰；(b) 给出 ROI 缩小 L2 搜索范围；(c) 在 L2 模型尚未检出时给出"疑似火焰"的快速预警。
- **L2 深度学习精判**：在 L1 给出的 ROI 上跑 YOLO 类模型，输出 `[置信度, 类别 (candle/flame/false_trigger), bbox]`。

为什么要双路而不是单 YOLO：
- 单 YOLO 在小目标（应急蜡烛火苗像素 < 40×40）上漏检率高；L1 用颜色先捞一遍候选，弥补小目标召回。
- 单 YOLO 推理开销固定，双路在无火焰的多数帧里 L2 几乎不需要计算（候选为空时跳过），平均功耗低于单 YOLO。

### 4.2 L2 模型选型矩阵

| 候选 | 适用形态 | 输入 | 量化 | 预期时延（单帧） | 优势 | 取舍 |
| --- | --- | --- | --- | --- | --- | --- |
| YOLOv8n + TensorRT FP16 | A | 640×640 | FP16 | Jetson 30~60 ms | 工程已成熟（track 在用同一管线）；可微调到 candle 类 | 需 GPU；若 103 算力不足 Nano 档则降级到 v5n |
| YOLOv5n + TensorRT FP16 | A | 640×640 | FP16 | 20~40 ms | 略轻量，召回与小目标平衡 | 模型生态稍弱于 v8 |
| YOLOv5s + RKNN INT8 | B | 416×416 或 640×640 | INT8 | RK3588 NPU 20~40 ms | 120 已有 RKNN 运行时和模型转换经验（track） | INT8 对小目标亮度敏感；需带火焰样本重新量化 |
| MobileNetV3 + SSD-Lite + RKNN INT8 | B（备选） | 320×320 | INT8 | 10~20 ms | 算力最低，CPU/NPU 都可跑 | 召回率最低，需配合 L1 强约束 |
| 传统 CV（HSV+运动+轮廓） | L1 替代方案 | 全帧 | — | < 2 ms | 零深度学习依赖，CPU 即跑 | 对伪装色（橙色应急灯）效果差 |

**推荐**：
- 形态 A 默认 L2 = **YOLOv8n + TensorRT FP16**，可直接在 `lite_cog_ros2` 下复用现有 `track/model/export_engine.sh` 的导出方式。
- 形态 B 默认 L2 = **YOLOv5s + RKNN INT8**，模型转换用 `rknn-toolkit2`，输入尺寸 416×416。
- L1 始终用 HSV + 运动差分，不依赖模型。

### 4.3 资源受限时的取舍

| 资源约束 | 应对策略 |
| --- | --- |
| 103 的 Jetson 模块算力低于 Nano 档（FP16 推理 > 80 ms） | 把 L2 降到 YOLOv5n + TensorRT INT8；降低检测 FPS 到 5；L1 阈值收紧让 L2 跳过空帧 |
| 120 内存不足（free < 500 MiB） | 不与 `track` 同时跑；降低 batch=1；模型用 ONNX/RKNN 而非 PyTorch；禁用图形界面 |
| 摄像头曝光变化大（逆光） | 关闭自动曝光的极端跳变；改用 ROI 局部归一化；接受 L1 召回下降但不允许 L2 误报上升 |
| 现场有手电、应急灯、屏幕反光 | L1 增加手电白斑抑制（圆度高、亮度饱和、V>240 且 S<50）；L2 训练集必须包含这些负样本 |

### 4.4 YOLO26n 选型评估

原方案未纳入 YOLO26n，主要理由是**沿用现有 `track` 已验证的 YOLOv8n 管线**（工程延续性、零迁移成本），而非技术论证。补充调研后（数据取自 Ultralytics 官方文档、`yolo26-vs-yolov8` 对比页、`end2end-detection` 指南、YOLO26 论文 arXiv:2606.03748，采集时间 2026-09-07），结论如下。

#### 4.4.1 客观指标对比

| 维度 | YOLOv8n（当前方案） | YOLO26n | 对本项目的实际意义 |
| --- | --- | --- | --- |
| 通用精度 | COCO 37.3 mAP | COCO 40.9 mAP（e2e 40.1） | YOLO26 通用精度更高 |
| 小目标机制 | 无专门设计 | STAL + ProgLoss | **对蜡烛火苗（<40×40）有针对性**，但依赖正确训练配方 |
| CPU 推理（ONNX） | 80.4 ms | 38.9 ms（快约 51%） | 无 GPU 场景优势显著 |
| GPU 推理（T4 TensorRT） | 1.47 ms | 1.7 ms（**慢约 15%**） | 形态 A（Jetson GPU）反而更慢 |
| 参数量 / FLOPs | 3.2 M / 8.7 B | 2.4 M / 5.4 B | 对 120 的 3.8 GiB 内存更友好 |
| 后处理 | 需 NMS | 默认无需 NMS（一对一头，(N,300,6)） | 见下方 fallback 说明 |
| DFL | 有 | 已移除 | 导出与量化更友好 |
| Python 3.8 | 支持 | 官方要求 >=3.8（v8.3.61 起恢复兼容） | 103 不阻断，但需锁定版本 |
| 许可证 | AGPL-3.0 + Enterprise | AGPL-3.0 + Enterprise | **无差异** |
| 生态成熟度 | 发布 3 年+，案例丰富 | 2026-01 发布，约 8 个月 | 排障与第三方集成成本更高 |

#### 4.4.2 决定性约束：RKNN 会回退，NMS-free 优势归零

Ultralytics `end2end-detection` 指南明确列出会回退到一对多头（即仍需 NMS）的格式：

> "NCNN, **RKNN**, PaddlePaddle, ExecuTorch, IMX, Edge TPU and Qualcomm QNN fall back to the one-to-many path when their operators cannot support end-to-end output."
> "Edge devices (NCNN, **RKNN**): These formats auto-fallback to one-to-many, so include NMS in your on-device pipeline."

即：**在形态 B（RK3588 + RKNN）上，YOLO26 的端到端优势完全不成立**，行为退化为与 YOLOv8 相同的传统输出。叠加社区反馈的 RK3588 INT8 量化问题（FP16 正常、INT8 后失效），以及"轻量化模型全局 INT8 会造成小目标特征丢失"，形态 B 属于 YOLO26 的明确劣势区。

#### 4.4.3 形态 A（Jetson GPU）的实测风险信号

社区在 4GB Jetson Orin Nano 上的 C++ TensorRT 实测报告：YOLOv8 转换正常，而 YOLO26 默认导出输出为 `1x84x8400`（缺端到端子图），出现 bbox 漂移与置信度不准，作者最终回退到 YOLOv8n。另有工业落地反馈：部分平台 `end2end=True` 导出时因 NPU 驱动不支持 TopK/Gather 而段错误，需用 `end2end=False` 规避。

同时 YOLO26 有额外训练约束：**不能沿用 YOLOv8 超参**（小数据集微调需降学习率约 30%、骨干学习率低于检测头），且**一对一分配对强增广容错率低**（需弱化 mosaic、关闭随机透视）。本项目训练集仅 200~500 张，配错配方反而会掉点。

#### 4.4.4 架构层面的边际价值判断

本方案采用 L1（颜色+运动预筛）+ L2（YOLO 精判）双路结构。**小目标召回主要由 L1 承担**，L2 的核心职责是降误报（区分火焰与手电/LED/反光）。因此 YOLO26 的 STAL 小目标召回增益，在本架构中的边际价值低于"单 YOLO"方案。

#### 4.4.5 结论

| 形态 | 是否切换 | 理由 |
| --- | --- | --- |
| A（Jetson 103，当前默认） | **暂不切换，但纳入并行验证** | GPU 上无速度优势且存在导出稳定性风险；但 STAL 对小火苗有潜在召回收益，值得实测 |
| B（RK3588 120） | **不切换** | RKNN 回退使 NMS-free 归零；INT8 + 小目标为已知雷区 |
| C（双机协同） | 跟随形态 A 的结论 | 同 A |

切换 YOLO26n 的**充要条件**（须全部满足）：

1. 形态 A 导出为 `(1, 300, 6)` 且无 bbox 漂移 / 置信度异常；
2. 在同一蜡烛验证集上，小目标（火苗面积 < 40×40）召回率不低于 YOLOv8n 且提升 ≥ 5 个百分点；
3. 干扰集（手电/LED/屏幕/反光）误报率不高于 YOLOv8n；
4. 103 实测端到端时延劣化不超过 10%。

不满足任一条件则维持 YOLOv8n。

#### 4.4.6 最小验证实验

准备：x86 Linux 工作站（RKNN 导出不支持 ARM64）、同一份蜡烛数据集（≥200 张，含火苗 <40×40 标注）、固定 val 集、干扰集（≥100 张）。

1. **训练对比**：各训 1 次、100 epoch。A 组 `yolov8n.pt` 用现有配方；B 组 `yolo26n.pt` 用 YOLO26 配方（学习率 ×0.7、弱化 mosaic、关闭随机透视）。记录 mAP@0.5、小目标子集召回、干扰集误报数。
2. **导出 go/no-go**（先于性能测试）：形态 A `export format=engine half=True imgsz=640`（检查输出 shape 是 `(1,300,6)` 还是回退的 `(1,84,8400)`）；形态 B `export format=rknn name=rk3588 quantize=8`（检查是否成功、是否有 fallback 警告）。
3. **实机实测**：103 上对同一段 60 秒蜡烛视频跑两个 engine，记录端到端时延、ALERT 首次触发延迟、误报次数。
4. **按 4.4.5 的四条门限决策**。

### 4.5 红外 / 多传感器融合评估

#### 4.5.1 先厘清"红外"指哪一种

| 类型 | 波段 | 本机是否有 | 对火焰检测的价值 |
| --- | --- | --- | --- |
| 近红外 NIR | 0.75–2.5 μm（常用 850/940 nm） | **有**：103 的 RealSense / Orbbec Gemini2 深度相机自带 IR 相机 | 有限，见 4.5.3 |
| 中波红外 MWIR | 3–5 μm，火焰 CO₂ 发射峰在 4.3 μm | 无 | 高（工业 IR3 火焰探测器原理） |
| 长波红外 LWIR | 8–14 μm，即热成像 | 无 | 高（测温、穿透烟雾） |

仓库笔记中**未记录任何热成像（LWIR）或专用火焰探测器**；现有可用的是深度相机的 NIR、超声波和 IMU。

#### 4.5.2 决定性物理约束：玻璃罐挡住中远红外

用户给定的目标外观是**透明玻璃罐装蜡烛**。普通钠钙玻璃在 LWIR（8–14 μm）波段几乎完全不透明（透过率趋近零、发射率约 0.85–0.95），对 >4 μm 的辐射强烈吸收或反射。因此：

- 热成像对准玻璃罐时，看到的是**罐壁被加热后的表面温度**，不是火焰本身；
- 玻璃导热会进一步"抹平"背后热源的空间特征，且热惯性使响应变慢（数十秒量级）；
- 火焰特有的闪烁频率（1–20 Hz）被热惯性平滑掉，无法用于判定。

**推论**：对罐装蜡烛这一主目标，MWIR / LWIR 均失效；**可见光是唯一能穿过玻璃看到火苗的波段**——这反而说明纯 RGB 视觉在本题中是唯一可行的非接触方案。

#### 4.5.3 现有 NIR 深度相机为何帮不上大忙

RealSense D4xx / Orbbec Gemini2 的 IR 相机是**主动照明**（投射红外散斑/图案用于深度计算）配窄带滤光片和自动增益。其结果是：

- 火焰在 NIR 确有强辐射，但会被自身照明和自动增益淹没；
- 开着 IR projector 会干扰火焰信号，关掉则深度失效（但火焰检测本身不需要深度）；
- **NIR 无法区分"热的"与"亮的"**——手电、LED、屏幕反光在 NIR 下同样很亮，**误报抑制能力弱**，而这恰是本方案最大的痛点。

结论：可把 NIR 当作**免费的额外通道**做低成本试验（相机已在机器人上），但不能指望它承担"热信号确认"角色。

#### 4.5.4 红外真正有价值的场景

若任务目标扩展到**蔓延后的明火 / 真实火场**，热成像的价值极高，且是纯 RGB 无法替代的：

| 场景 | 纯 RGB | 加 LWIR 热成像 |
| --- | --- | --- |
| 手电 / LED / 屏幕反光误报 | 高发（本方案痛点） | **几乎消失**（这些不是热源） |
| 有烟雾环境 | 失效 | **可穿透**（8–14 μm 散射小） |
| 全黑环境 | 需补光，且补光本身成误报源 | 正常工作 |
| 被遮挡 / 隐蔽火源 | 不可见 | 可通过温升发现 |

#### 4.5.5 若加硬件：推荐低分辨率热阵列 + 决策级融合

| 候选 | 分辨率 | 成本量级 | 适配性 |
| --- | --- | --- | --- |
| AMG8833 | 8×8 | 极低 | 太低，只能判"有没有热源" |
| **MLX90640** | 32×24 | 低（约百元级） | **推荐**：I2C 直读 768 点温度，几乎零算力，对 120 的 3.8 GiB 内存无压力 |
| FLIR Lepton 3.5 | 160×120 | 中（千元级） | 可跑轻量检测，但需视频接口与更多算力 |
| UV/IR 火焰探测器模组 | 单点 | 低 | 误报率极低，但**普通玻璃强烈吸收 UV，罐装场景无效**，且无法定位 |

**融合方式：决策级（late fusion），热源作为 L1 的第三个门，不改 YOLO 输入。**

```text
RGB 帧 ─> L1a 颜色门 ─┐
        ├> L1b 运动门 ─┼─> 候选 ROI ─> L2 YOLO 精判 ─> 时序稳定 ─> ALERT
热阵列 ─> L1c 热源门 ─┘
```

判定规则（ΔT 建议取环境温度 +15 ℃ 起，需实机标定）：

- RGB 命中 + 热源命中 → 高置信 **ALERT**；
- RGB 命中 + 无热源 → 降为 **WARN**（大概率是灯光/反光）；
- 无 RGB + 强热源 → 新增**隐蔽火源**告警（纯 RGB 做不到的能力）。

**为什么不把 IR 作为第 4 通道做早期融合**：需要 RGB–IR 像素级配准（1280×720 对 32×24，视场角差异大，标定复杂）；YOLO 预训练权重是 3 通道，改输入层后在 200~500 张小数据集上更难收敛。决策级融合可直接复用现有 COCO 预训练权重，训练成本为零。

#### 4.5.6 结论

1. **若目标严格为"罐装应急蜡烛"**：红外（含热成像）投入回报低，玻璃挡住了 MWIR/LWIR；建议维持纯 RGB 方案，把精力放在训练数据与误报抑制上。
2. **若目标包含"蔓延明火 / 有烟火场"**：**强烈建议加装低分辨率热阵列**（成本极低、零算力），价值在于误报抑制与烟雾穿透，而非提升精度。
3. **现有 NIR 深度相机不作为火焰传感器**，仅在零成本前提下做探索性试验。
4. 加装前需先明确目标定义，并以实机标定 ΔT 阈值与环境温度基线。

## 5. 火焰/蜡烛的判定特征、阈值与误报抑制

### 5.1 视觉特征（从用户提供的应急蜡烛图归纳）

| 特征 | 取值 | 用途 |
| --- | --- | --- |
| 火苗色相 | HSV H ∈ [10°, 35°]（黄→橙红） | 颜色阈值 L1 |
| 火苗饱和度 | HSV S > 100 | 排除白色 / 灰色光斑 |
| 火苗亮度 | HSV V > 180（白天）；室内场景可放宽到 V > 130 | 与背景区分 |
| 火苗面积 | 20~500 像素（640×480 帧） | 排除过大的反光区域 |
| 火苗形状 | 拉长、不规则、上细下宽 | 用 Hu 矩或长宽比区分 |
| 火苗运动 | 时序差分面积有变化；非周期性 | 与 LED 频闪区分 |
| 周边 | 玻璃罐、桌面、应急标识 | 上下文（可选 L2 二次判别） |

### 5.2 L1 颜色门

```text
candidate pixel iff:
   H in [10, 35]
   AND S >= 100
   AND V >= 130 (夜间) / 180 (白天)
   AND pixel belongs to a connected component of area in [20, 2000]
```

### 5.3 L1 运动门

```text
diff_frame = abs(curr_gray - prev_gray)
candidate component must overlap with diff_frame pixels > 30%
```

### 5.4 L2 模型输出后处理

| 后处理 | 阈值/参数 |
| --- | --- |
| NMS IoU | 0.45 |
| 置信度阈值 | 0.35（应急场景宁可多报，召回优先） |
| 多尺度 | 默认 1 尺度；形态 B 可加 2 尺度 |
| 类别 | `candle`, `flame`, `light_reflection`（`light_reflection` 是负类，训练时显式给出） |

### 5.5 时序与空间稳定（消除单帧误报）

- **时序窗口**：连续 5 帧中 ≥ 3 帧 L2 检出，且 bbox 中心抖动 < 30 像素，才输出 `candle_detected`。
- **空间稳定性**：bbox 在连续帧间的 IoU ≥ 0.3 视为同一目标，分类稳定后输出 ID。
- **冷却期**：触发告警后冷却 2 秒，避免扬声器/语音反复播放。
- **分级告警**：
  - **WARN**：仅 L1 颜色 + 运动命中（L1 置信度高）→ 仅在 `/candle_suspicion` 话题置 1，可用于"减速 + 拍照"。
  - **ALERT**：L2 也检出 `candle`/`flame` 且时序稳定 → `/fire_alert` 话题置 1，并触发应急逻辑。
  - **RETRACT**：连续 10 帧无 L2 检出 → 清空告警状态。

### 5.6 误报源与抑制策略

| 误报源 | 表现 | 抑制策略 |
| --- | --- | --- |
| 手电白光 | 圆斑，V>240，S<50，色相无 | L1 颜色门用 S 阈值直接排除 |
| 应急灯（橙红） | 与火焰色相重叠，但轮廓规则（圆形），无运动 | 形状圆度（Hu 矩第一不变矩 > 0.85）+ 运动门 |
| 手机/平板屏幕 | 矩形，色相多样，无运动 | 长宽比 + 边缘直线性 + 运动门 |
| LED 频闪 | 高频闪烁，固定周期 | 时序差分频谱分析（FFT 检测主频 ≥ 50 Hz 排除） |
| 太阳光斑 / 镜面反射 | 高亮、不规则、瞬时 | 时序窗口要求连续 3~5 帧同时命中，反光是瞬时的 |
| 蜡烛包装玻璃高光 | 与火焰同位置但更白、更亮、几何规则 | L2 训练集加入玻璃高光负样本 |

## 6. 检测结果输出与机械狗联动

### 6.1 103 端（形态 A）输出与联动

ROS 2 话题（与现有 Foxy 环境一致）：

| 话题 | 类型 | 含义 |
| --- | --- | --- |
| `/candle_detected` | `vision_msgs/Detection2DArray` | L2 检出目标，包含 bbox、score、class |
| `/candle_suspicion` | `std_msgs/Bool` | L1 命中但 L2 未确认（预警） |
| `/fire_alert` | `std_msgs/Bool` + 警报级别 | 时序稳定后的最终告警 |
| `/candle_pose` | `geometry_msgs/PointStamped` | 像素坐标 → 相机坐标系的反投影（可选） |

联动点：
- 现有 `transfer/jetson2motion` 已经在订阅 `/cmd_vel` 与 `/cmd_vel_corrected`。告警时可叠加**安全减速包络**：
  - `WARN`：原速度 × 0.5
  - `ALERT`：原速度 × 0.1，并叠加旋转行为（朝向火焰）
- 不要**直接抢 `/cmd_vel`**；推荐用一个 `safe_cmd_vel_mux` 节点，与现有 VOA 的 `cmd_vel_corrected` 同级串入。
- 语音报警复用 120 端 `lite3_voice/` 资产；通过 103 → 120 现有的私有 UDP 通道触发，或在 120 上订阅 RTSP 端点之外加一个 ROS bridge。

### 6.2 120 端（形态 B）输出与联动

- 形态 B 不依赖 ROS 2，直接以本地 UDP 包发送到 103 的 `43897` 端口（与 `transfer` 上报状态共用一个 socket，但用独立消息头或私有协议标识为 `fire_alert`），让 103 在现有 Transfer 链路上"感知到"告警后再由 `jetson2motion` 注入减速。
- 形态 B 也可以直接向 120 端 `jy_exe` 的私有运动端口发送紧急减速包；**这会与 `jy_exe` 闭源协议耦合**，未在笔记中找到完整协议描述，**不建议**。
- 报警本地化：120 端 `lite3_voice/` 已有 WAV 资产，可直接 `aplay` 应急语音。

### 6.3 应急逻辑分层（推荐）

```text
L1 命中 + L2 未命中
   -> /candle_suspicion = true
       -> 减速到 0.5x
       -> 云台/相机朝向候选区域（如果机械狗有云台）
       -> 上位机 UI 显示黄色"疑似火焰"
       -> 不触发扬声器

L1 + L2 同时命中 + 时序稳定
   -> /fire_alert = true (ALERT)
       -> 减速到 0.1x
       -> 立即停止当前巡检任务
       -> 上位机 UI 红色"确认火焰"
       -> 语音报警（lite3_voice 资产）
       -> 拍照取证（高分辨率原图）
       -> 上传事件到上位机 / 云端（可选）
```

## 7. 推理时延、资源占用与实时性

### 7.1 单帧时延估算

| 阶段 | 形态 A（Jetson 103） | 形态 B（RK3588 120） |
| --- | --- | --- |
| RTSP 拉流 + 解码 | 30~50 ms | 0（直读 /dev/video0） |
| 预处理（letterbox + HSV + 差分） | 5~10 ms | 5~10 ms |
| L1 颜色+运动 | < 2 ms | < 2 ms |
| L2 YOLO（FP16/INT8） | 30~60 ms | 20~40 ms |
| 后处理（NMS、时序稳定） | 1~2 ms | 1~2 ms |
| **端到端单帧** | **70~125 ms** | **30~55 ms** |

### 7.2 实时性目标

- **告警端到端时延** ≤ 500 ms（从蜡烛出现在画面到 `/fire_alert` 置 1）。
- 按 5~10 FPS 检测，ALERT 需要的 3 帧连续命中 ≈ 300~600 ms，刚好落在目标窗口。
- 如果机械狗运动速度 > 0.5 m/s，建议把检测 FPS 提到 10 以上，并把时序窗口从 3 帧压到 2 帧；代价是误报率上升，需要用更强的负样本训练集兜底。

### 7.3 资源占用预估

| 资源 | 形态 A（103） | 形态 B（120） |
| --- | --- | --- |
| CPU | 0.5~1 核（预处理 + L1） | 1~2 核 |
| GPU/NPU | YOLOv8n TensorRT 占用约 1~1.5 GB GPU 显存 | RKNN YOLOv5s 约 200~400 MB NPU 内存 |
| 系统内存 | 进程 RSS 约 400~700 MB | 进程 RSS 约 250~400 MB |
| 磁盘 | 模型 30~80 MB；日志 < 100 MB/天 | 同左 |
| 网络 | RTSP 入站 2~4 Mbps | 本机拉流 0 |

形态 B 的总占用（GPU/NPU + CPU + RSS）在 120 端与现有 `track` 同时跑时**会**触发 OOM 风险（120 总内存 3.8 GiB，可用 ~3 GiB）。缓解：
- 与 `track` 分时复用：`track.service` 仅在巡检时启用，火焰检测模块在应急模式下独占。
- 或在 120 上用单独的低功耗模式运行（CPU-only + YOLOv5n INT8 + 极小输入尺寸），时延换取资源。

## 8. 部署、依赖与环境配置

### 8.1 103 端（形态 A）

- 工作区：复用 `/home/ysc/lite_cog_ros2`。
- 新建包：`ros2 pkg create fire_detector --build-type ament_python --dependencies vision_msgs rclpy sensor_msgs std_msgs`。
- 依赖：Ultralytics（导出 ONNX）、`tensorrt`、`pycuda` 或 `trt-runtime`；GStreamer（含 `nvv4l2decoder`、`nvvidconv`）。
- 模型导出：复用 `track/model/export_engine.sh` 的 `yolo export format=engine half=True simplify=True`，在 `fire_detector/model/` 下产出 `yolov8n_candle.engine`。
- 训练数据：建议自建 200~500 张应急蜡烛 + 干扰样本（手电、LED、应急灯、屏幕、玻璃高光），用 `roboflow` 或 `labelImg` 标注 `candle/flame/light_reflection` 三类。
- 启动：新增 systemd 单元 `fire_detector_ros2.service`，依赖 `transfer_ros2.service` 与 `network-online.target`；不要让告警逻辑在 Transfer 之前启动。

### 8.2 120 端（形态 B）

- 路径：建议 `/home/ysc/fire_detector/`。
- 依赖：GStreamer（含 Rockchip 插件，已在）、OpenCV 4.2（已在）、`librknnrt.so`（在 `track/lib` 内，需用 `LD_LIBRARY_PATH` 或链接 `/usr/lib`）。
- 模型：用 `rknn-toolkit2` 在 x86 工作站上把 YOLOv5s ONNX 转 RKNN INT8，再拷贝到 120。
- 启动：新增 systemd 单元 `fire_detector.service`，与 `track.service` `Conflicts=` 互斥。

### 8.3 双机协同（形态 C）

- 复用 103 的 ROS 2 环境 + 120 的 RKNN L1。
- 通信：120 L1 输出通过现有 RTSP 流（叠加在 RTP 私有头）或独立 UDP 通道（推荐 43893 同 socket 的私有子协议）。
- 配置：103 端新增 `candle_roi_subscriber` 节点，订阅 120 L1 推送的 ROI 列表。

## 9. 实机验证方法

| 验证项 | 方法 | 通过标准 |
| --- | --- | --- |
| 接入链路 | 在 103 上 `gst-launch-1.0` 拉 `rtsp://192.168.1.120:8554/test latency=30`，截图确认能解码出原始帧 | 帧率 ≥ 25 FPS |
| 模型推理 | 在工作区单独运行 `yolo predict model=...engine source=...` 验证模型加载与单帧时延 | 单帧时延在 7.1 节表格范围内 |
| L1 召回 | 用 50 张含蜡烛 + 50 张不含蜡烛的固定图集，统计 L1 命中数 | 召回 ≥ 95%（宁可误报） |
| L2 精度 | 同上，统计 mAP@0.5 | mAP@0.5 ≥ 0.85，`candle/flame` 召回 ≥ 0.9 |
| 误报率 | 用 200 张不含蜡烛的干扰图集（手电、应急灯、屏幕、夜景灯光） | 误报率 ≤ 5% |
| 时序稳定 | 录一段 60 秒视频，逐帧跑端到端管线，统计 ALERT 触发延迟 | 首次 ALERT 距离首帧 ≤ 500 ms |
| ROS 联动 | 在 103 上 mock 一个 `cmd_vel` 发布节点，手动触发 ALERT，验证 safe_cmd_vel_mux 把速度降到目标比例 | 速度比例与告警等级一致 |
| 资源占用 | 在 103 上 `tegrastats` 或 `nvtop` 抓 10 分钟，120 上 `top -p <pid>` 抓 10 分钟 | GPU/内存占用与 7.3 节预估一致，无 OOM |
| 端到端联调 | 蜡烛点然后机械狗静止 → 观察 `/fire_alert` 与语音/减速行为 | 告警触发；速度被安全链路压制；上位机收到事件 |

## 10. 风险与边界

1. **目标外观的有限性**：用户提供的图是单只室内应急蜡烛；室外、远距离、群组蜡烛火焰、多火苗叠加场景需要在训练集中显式扩展。
2. **夜间 vs 白天阈值差异**：当前 L1 用两套 V 阈值；切换场景必须重新校准，否则白天漏报、夜间误报。
3. **103 Jetson 型号未锁定**：方案对 t186ref 系列给出条件化分支；如果实机是更低端模块（TX2 4GB 之类），需要回退到 YOLOv5n + INT8。
4. **120 资源紧张**：形态 B 与 `track` 同时跑会触发 OOM，必须有运行模式切换机制，不能常驻。
5. **闭源耦合**：120 的 `jy_exe`、`track` 都是闭源二进制；不应直接对它们做协议级联动，避免引入兼容性问题。
6. **应急场景的合规**：自动减速 + 语音报警涉及安全行为，必须在上位机维护急停通道，禁止本方案自动覆盖人工急停指令。
7. **样本采集责任**：训练集应使用现场实拍，避免完全依赖互联网通用火焰数据集（室内应急蜡烛与森林/工业火焰差异较大）。

## 11. 一句话总结

**默认在 Jetson 103 上跑"颜色+运动预筛 + YOLOv8n TensorRT 双路检测 + 时序稳定输出"，复用现有 ROS 2 Transfer 与 VOA 安全链路做减速和语音报警；120 仅作为摄像头与 RTSP 发布端，必要时切换到 RKNN 形态 B 但需关闭 `track` 以释放内存。** 算法、阈值与误报抑制全部围绕"近距离小火焰 + 复杂室内光源"目标设计。
