# sdk-deploy — DeepRobotics sdk_deploy（ROS 2 Sim-to-Sim / Sim-to-Real 部署）

> 来源：官方开源仓库 [DeepRoboticsLab/sdk_deploy](https://github.com/DeepRoboticsLab/sdk_deploy)。
> 机器人控制 SDK，当前支持 **Lite3 与 M20** 两个平台；官方说明见 [`README.upstream.md`](README.upstream.md)。
> ⚠️ 官方提示：**因使用 SDK 造成的设备损坏不在保修范围内。** 真机部署前务必阅读 `../docs/08-ROS2导航与强化学习部署路线.md` 第 6 阶段（限幅、跌倒保护、吊装测试、SDK 授权）。

## 目录结构

```
sdk-deploy/
├── img/                      官方说明图（Lite3 改频 / 切模式 / APP）
└── src/
    ├── drdds/                SDK 使用的 drdds 通信格式（.msg 定义：Joint/Battery/Imu/Gamepad 等）
    ├── M20_sdk_deploy/       M20 部署源码（main.cpp + state_machine + run_policy + policy.onnx + interface）
    ├── Lite3_sdk_deploy/     Lite3 部署源码（结构同 M20）
    ├── lite3_sdk_service/    Lite3 SDK 模式切换与频率修改服务
    └── lite3_transfer/       Lite3 UDP ↔ ROS 2 消息转换
```

各子包内主要组成（以 `M20_sdk_deploy` 为例）：`include/`（头文件）、`interface/`（接口层）、`state_machine/`（状态机）、`run_policy/`（策略推理运行器）、`policy/policy.onnx`（785KB 策略本体，已随库保留）、`scripts/`、`CMakeLists.txt`、`package.xml`。

## 未入库内容（需要时从上游/厂商获取）

| 内容 | 体积 | 原因 | 获取方式 |
|---|---|---|---|
| `*/third_party/onnxruntime/`（arm/x86 的 libonnxruntime.so.1.22.0） | 160MB×2 | 预编译第三方库 | [onnxruntime 1.22.0 官方 release](https://github.com/microsoft/onnxruntime/releases) 或上游仓库 |
| `*/third_party/gamepad/controlapp.apk` | — | 厂商手柄 APP | 厂商提供 |
| `*/third_party/eigen/` | 小 | 第三方头文件 | apt / 上游 |
| `M20_sdk_deploy/M20_description/m20_mjcf/` | 25MB | MJCF 网格（与 `../models/` 同源） | 上游 clone 或 `../models/README.md` |
| `Lite3_sdk_deploy/Lite3_description/` | 17MB | 同上 | 同上 |

> `third_party` 在原仓库中随包提供，缺失时按上游目录结构放回即可构建；`CMakeLists.txt` 中的相对路径未改动。

## 与其他目录的关系

- 训练侧：`../rl-training/`（Isaac Lab 训练 → 导出 ONNX）。
- 模型侧：`../models/`（M20/M20S URDF/MJCF 文本描述符）。
- 消息格式：`src/drdds/msg/*.msg` 与 196 主机 GPS 话题（`/GPS` 等 `drdds/msg/NavSat`）同源，详见 `../rtsp-rtmp/note/m20-GPS获取方式.md`。
