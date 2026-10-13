# rl-training — DeepRobotics rl_training（Isaac Lab 强化学习训练）

> 来源：官方开源仓库 [DeepRoboticsLab/rl_training](https://github.com/DeepRoboticsLab/rl_training)（BSD 3-Clause）。
> 基于 Isaac Lab 2.3.2 + RSL-RL 5.0.1，提供 **Lite3 / M20** 两个速度跟踪（velocity）locomotion 训练环境。
> 本目录为源码与配置归档（不含 `deep_robotics_model` 子模块与 `.git`），用于阅读、diff 与复现训练配置。
> 官方完整说明见 [`README.upstream.md`](README.upstream.md)。

## 目录结构

```
rl-training/
├── README.upstream.md / VERSION / pyproject.toml   官方说明与版本（IsaacSim 5.1.0 / IsaacLab 2.3.2）
├── LICENSE / LICENSE-robot_lab / CONTRIBUTORS.md   开源许可与贡献者
├── .gitmodules / .gitignore                        子模块声明（deep_robotics_model）与忽略规则
├── source/rl_training/                             库本体（pip 安装目标）
│   ├── assets/deeprobotics.py                      机器人资产注册
│   └── tasks/manager_based/locomotion/velocity/
│       ├── config/quadruped/deeprobotics_lite3/    Lite3 环境（flat/rough + PPO 配置）
│       ├── config/wheeled/deeprobotics_m20/        M20 环境（flat/rough + PPO 配置）
│       └── mdp/                                    observations / rewards / events / curriculums / commands
├── scripts/
│   ├── reinforcement_learning/rsl_rl/              train.py / play.py / cli_args.py（训练与回放入口）
│   └── tools/                                      list_envs / compare_runs / export_onnx_fast
└── docs/imgs/                                      环境渲染图（Lite3 / M20）
```

## 环境与使用

| 环境 ID | 机器人 | 说明 |
|---|---|---|
| `Rough-Deeprobotics-Lite3-v0` | Lite3（四足） | 粗糙地形速度跟踪 |
| `Rough-Deeprobotics-M20-v0` | M20（轮足） | 粗糙地形速度跟踪 |

```bash
# 1. 先装 Isaac Lab（官方推荐 conda 方式），再 clone 本仓库（含子模块）到 Isaac Lab 目录之外
git clone --recurse-submodules https://github.com/DeepRoboticsLab/rl_training.git
# 2. 用装有 Isaac Lab 的解释器安装库
pip install -e source/rl_training
# 3. 训练 / 回放 / 导出 ONNX
python scripts/reinforcement_learning/rsl_rl/train.py --task Rough-Deeprobotics-M20-v0 --headless
python scripts/reinforcement_learning/rsl_rl/play.py  --task Rough-Deeprobotics-M20-v0
python scripts/tools/export_onnx_fast.py --task Rough-Deeprobotics-M20-v0
```

> 真机部署需配套官方 `sdk_deploy`（见 `../sdk-deploy/`）；策略部署的风险边界与分阶段建议见 `../docs/08-ROS2导航与强化学习部署路线.md`。

## 归档说明

1. `deep_robotics_model` 子模块（机器人 URDF/MJCF/USD）未随本目录入库，需要时按 `.gitmodules` 地址 clone，或参考 `../models/`（已收 M20/M20S 文本描述符）。
2. 训练产物（checkpoint、日志、导出的 onnx）不在本目录；`policy.onnx` 示例见 `../sdk-deploy/src/M20_sdk_deploy/policy/`。
3. M20 为轮足（wheeled）构型，其 MDP 配置与 Lite3（quadruped）分列，改动时注意不要串目录。
