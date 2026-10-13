# models — 云深处机器人模型（M20 / M20S）

> 来源：官方开源仓库 [DeepRoboticsLab/deep_robotics_model](https://github.com/DeepRoboticsLab/deep_robotics_model)（BSD 3-Clause，见 `LICENSE.txt`）。
> 本目录收 **M20 / M20S 的文本描述符**（URDF / MJCF / USD），用于阅读、diff 与 Nav2 参数派生；**网格文件（STL）与大体积 USD 未入库**，见下文"获取完整模型"。

## 文件清单

| 路径 | 说明 |
|---|---|
| `M20/urdf/M20.urdf` | M20 URDF（22KB，文本） |
| `M20/mjcf/M20.xml` | M20 MJCF（18KB，文本，MuJoCo 用） |
| `M20/usd/M20.usd` + `configuration/*.usd` | M20 USD 组装层与 physics/robot/sensor 配置（`M20_base.usd` 为 17MB 二进制网格，未入库） |
| `M20S/` | M20S 同上（M20 的紧凑衍生型号） |
| `images/M20.png` / `M20S.png` | 官方低分辨率渲染图 |

## 获取完整模型（含 meshes）

```bash
git clone https://github.com/DeepRoboticsLab/deep_robotics_model.git
```

- 上游同时提供 **Lite3 / M20 / M20S / X30 / M20_Piper / DR02 Pro / DR02 Standard** 七个型号的 MJCF / URDF / USD。
- 仓库内置低分辨率网格；**高分辨率网格**在 [Google Drive](https://drive.google.com/drive/folders/1EOELXUYSBPEJeD0rUIkJxnlLMDr6IHBV)（Isaac Lab / Isaac Sim 用）。
- 可视化与测量推荐官方 viewer：https://viewer.robotsfan.com/ （拖入模型文件夹即可）。

## 使用注意

1. 本目录 URDF/MJCF 中的 `mesh filename` 为相对路径（`meshes/*.STL`），**单独使用前需先按上游目录结构补齐网格**，或改写路径指向本地 clone。
2. M20 为四轮足（wheeled-leg），URDF 含 `*_wheel` 关节；M20 Pro 的传感器外参（Mid-360、深度相机等）需在真机标定后自行派生，上游模型不含任务传感器。
3. 派生 Nav2 配置时注意：M20 导航接口含横向速度 `y_vel`（全向底盘），局部控制器运动模型应设为 Omni —— 详见 `../docs/08-ROS2导航与强化学习部署路线.md`。
4. 官方 SDK 部署包内的 M20 描述（`sdk_deploy/src/M20_sdk_deploy/M20_description/m20_mjcf`）与上游同源，未重复入库。
