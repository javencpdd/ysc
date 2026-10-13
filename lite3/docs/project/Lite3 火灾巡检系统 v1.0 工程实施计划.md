# 《Lite3 火灾巡检系统 v1.0 工程实施计划》

版本目标：

> 基于 Lite3 双主机平台，构建一套可长期运行的室内自主巡检系统，实现“远程无头运维 + 自主导航 + 蜡烛/火焰检测 + 告警联动 + 数据取证”的完整闭环。

本版本**不追求一次完成 SCAN-Planner 级 3D 导航升级**，而是采用工程渐进路线：

```
v1.0
=
Headless Robot Platform
+
Nav2巡检
+
YOLO火焰检测
+
Foxglove远程运维
+
安全告警闭环

↓

v2.0
=
3D Local Planner
+
语义地图
+
多传感器融合
```

---

# 1. v1.0 总体目标

## 1.1 功能目标

|编号|目标|说明|
|-|-|-|
|F1|无头运行|103 无 RViz、无桌面依赖|
|F2|远程可视化|控制端 Foxglove 查看机器人状态|
|F3|自主巡检|Nav2执行固定路线|
|F4|火焰检测|检测应急蜡烛/小火焰|
|F5|告警联动|减速、停止、语音报警|
|F6|事件记录|保存图片、时间、位置|
|F7|安全运行|VOA作为最终速度安全层|

---

# 2. 系统总体架构


```
                         Laptop

                    Foxglove Studio

                           |
                           |
                  foxglove_bridge

                           |
                     ROS2 DDS


================================================


                       Lite3

------------------------------------------------

                103 感知导航主机


        ┌───────────────────────┐
        │ ROS2 Foxy             │
        │                       │
        │ Patrol Manager        │
        │        │              │
        │        ▼              │
        │ Nav2                  │
        │        │              │
        │        ▼              │
        │ VOA Safety            │
        │                       │
        │ Fire Detector         │
        │        │              │
        │        ▼              │
        │ Fire Event Manager    │
        │                       │
        └──────────┬────────────┘

                   |

              UDP / ROS2


------------------------------------------------

                120运动主机


        Camera

          |

        RTSP

          |

       Voice

          |

       Motor Control


================================================

```

---

# 3. 软件目录设计

不新建大工程，基于现有：

```
/home/ysc/lite_cog_ros2
```

扩展：

```
lite_cog_ros2/

├── src/

│
├── fire_detector/
│
├── patrol_manager/
│
├── fire_event_manager/
│
├── safe_cmd_mux/
│
└── lite3_interfaces/


ops/

├── launch/

├── config/

├── systemd/

└── scripts/

```

---

# 4. ROS2 Package设计


## 4.1 fire_detector


职责：

视频输入 → 火焰检测 → 发布结果


节点：

```
fire_detector_node

```


输入：

```
RTSP

rtsp://192.168.1.120:8554/test

```


输出：

|Topic|类型|
|-|-|
|/candle_detected|vision_msgs/Detection2DArray|
|/fire_alert|std_msgs/Bool|
|/fire_bbox|geometry_msgs|
|/fire_debug_image|sensor_msgs/Image|


---

## 节点内部结构


```
                Image

                  |

              GStreamer

                  |

              Preprocess

                  |

       ----------------------

       |                    |

       L1                 L2

 HSV+Motion          YOLOv8n TRT


       |

       |

 Temporal Filter


       |

 Fire State

```

---

# 5. patrol_manager设计


职责：

负责巡检任务。


输入：

```
waypoints.yaml

```


输出：

```
Nav2 Goal

```


---

节点：

```
patrol_manager_node

```


功能：


## 路点管理


例如：

```yaml
waypoints:

- name: room1
  x: 2.5
  y: 1.8
  yaw: 0

- name: corridor
  x: 5.0
  y: 3.2
  yaw: 1.57

```


---

## 任务状态机


```
INIT

 |

START_PATROL

 |

NAVIGATING

 |

ARRIVED

 |

INSPECTION

 |

NEXT_POINT

 |

FINISH


```

---

# 6. fire_event_manager设计


负责：

火灾事件处理。


输入：

```
/fire_alert

/robot_pose

/image

```


输出：

```
/mission_cancel

/voice_alert

/event_record

```


---

状态机：


```
NORMAL


 |

疑似火焰


 |

CONFIRMED


 |

Emergency


```


---

# 7. safe_cmd_mux设计


目的：

避免多个模块抢控制权。


当前：

```
Nav2

 |

VOA

 |

jetson2motion

```


升级：

```
Nav2 cmd_vel

        |

        |

safe_cmd_mux

        |

        |

VOA

        |

        |

robot

```


---

优先级：

|等级|来源|
|-|-|
|0|人工急停|
|1|火灾停止|
|2|VOA避障|
|3|导航|
|4|遥控|

---

# 8. Topic设计


## 导航相关


|Topic|作用|
|-|-|
|/cmd_vel|Nav2输出|
|/cmd_vel_safe|安全融合|
|/cmd_vel_corrected|VOA输出|


---

## 火灾相关


新增：

```
/fire_alert

```


消息：

建议：

```
FireAlert.msg


bool detected

float32 confidence

string class

geometry_msgs/Pose fire_pose

string image_path

builtin_interfaces/Time stamp

```


---

# 9. Launch设计


目录：

```
ops/launch/


├── robot_headless.launch.py

├── navigation.launch.py

├── fire_detector.launch.py

├── patrol.launch.py

└── emergency.launch.py

```

---

## robot_headless


启动：

```
transfer

VOA

sensor

TF

```


---

## navigation


启动：

```
HDL localization

Nav2

controller

planner

```


---

## fire_detector


启动：

```
RTSP

YOLO TensorRT

ROS publisher

```


---

## patrol


启动：

```
patrol_manager

```


---

# 10. 配置文件设计


## fire_detector.yaml


```yaml
camera:

  url:
    rtsp://192.168.1.120:8554/test


model:

  engine:
    yolov8n_fire.engine


  conf:
    0.35


detect:

  fps:
    10


alert:

  stable_frames:
    5

```

---

# 11. Foxglove布局设计


保存：

```
lite3_fire_patrol.json

```


---

## Panel


### 3D

显示：

```
/tf

/odom

/map

/rslidar_points

```


---

### Image


显示：

```
/fire_debug_image

```


---

### Plot


显示：

```
cmd_vel

battery

cpu

```


---

### Raw


显示：

```
/fire_alert

/patrol_status

```


---

# 12. 火焰检测模型开发计划


## 数据集


目标：

```
应急蜡烛
+
真实室内火焰
+
负样本
```


---

数量：

第一版：

|类别|数量|
|-|-:|
|candle flame|300|
|LED|100|
|手电|100|
|屏幕|100|
|反光|100|

---

# 13. YOLO训练流程


## 数据准备


```
images

labels

dataset.yaml

```


类别：

```yaml
names:

0 candle

1 flame

2 light_reflection

```


---

训练：

```bash
yolo train \
model=yolov8n.pt \
data=fire.yaml \
epochs=100 \
imgsz=640
```


---

导出：

TensorRT:

```bash
yolo export \
model=best.pt \
format=engine \
half=True

```

---

# 14. 实施阶段计划


# Phase 0：基础平台（1周）

目标：

机器人稳定运行。


任务：

|任务|输出|
|-|-|
|headless启动|tmux脚本|
|Foxglove通信|远程查看|
|DDS配置|稳定通信|
|系统状态|监控脚本|


验收：

可以：

SSH连接

↓

启动机器人

↓

Foxglove看到：

- TF
- Map
- Odom


---

# Phase 1：自主巡检（1~2周）


任务：

完成：

```
Nav2

+

waypoint

+

patrol_manager

```


验收：

机器人：

- 自动走路线
- 到点停留
- 失败恢复


---

# Phase 2：火焰检测（2周）


任务：

完成：

```
RTSP

↓

YOLO

↓

ROS2

```


验收：

指标：

|指标|目标|
|-|-:|
|检测延迟|<500ms|
|召回率|>90%|
|误报率|<5%|

---

# Phase 3：事件闭环（1周）


实现：

发现火焰：

```
Fire Alert

↓

Stop Mission

↓

Slow/Stop

↓

Save Image

↓

Voice Alarm

```


---

# Phase 4：优化（持续）


包括：

- 模型优化
- 参数调节
- CPU/GPU分析
- 日志完善


---

# 15. 测试体系


## T1 单模块测试


### 火焰检测

输入：

录像。


输出：

检测结果。


---

## T2 系统测试


场景：

机器人巡逻过程中放置蜡烛。


验证：

```
发现

↓

停止

↓

报警

↓

记录

```


---

## T3 长时间测试


8小时：

检查：

- 内存泄漏
- ROS节点稳定
- RTSP断线恢复


---

# 16. v1.0 暂不实现内容


明确冻结：


## 不做：

### 1. SCAN Planner

原因：

属于导航算法升级。

放：

v2。


---

### 2. 全局3D地图


原因：

收益低。


---

### 3. 热成像融合


原因：

硬件新增。


---

### 4. YOLO26替换


原因：

需要benchmark。


---

# 17. v1.0验收标准


最终达到：


## 功能

✅ SSH启动

✅ Foxglove远程查看

✅ 自动巡检

✅ 火焰检测

✅ 自动报警

✅ 图片取证


---

## 性能


|指标|要求|
|-|-:|
|巡检连续运行|≥2小时|
|检测延迟|≤500ms|
|导航频率|≥10Hz|
|CPU占用|<80%|
|无GUI运行|100%|
|异常恢复|可人工恢复|

---

# 18. 推荐开发顺序（最关键）


不要按照算法复杂度开发。

按照系统闭环：


```
① Headless基础

        ↓

② Foxglove远程

        ↓

③ Nav2巡检

        ↓

④ YOLO检测

        ↓

⑤ 告警联动

        ↓

⑥ 火源定位

        ↓

⑦ SCAN Planner升级


```


---

## 最终判断

Lite3 v1.0 应定位为：

> **“具备自主巡检能力的视觉火灾早期发现机器人平台”**

而不是：

> “完整火场机器人”。

原因：

当前硬件（103 Jetson级主机 + 120 RK3588）足够支撑：

- ROS2导航；
- 视觉检测；
- 远程运维；

但不适合一次性叠加：

- 3D全局地图；
- 高级局部规划；
- 多模态感知；
- 大模型推理。


因此 v1.0 的核心交付应是：

**稳定闭环 > 算法先进性。**

完成 v1.0 后，再进入：

**Lite3 v2.0：SCAN Planner + 语义地图 + 多传感器融合升级路线。**