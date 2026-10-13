# 主机审计文档

本目录按主机角色和专题保存只读审计报告。目录名以 IP 后缀开头，后接中文角色说明；每个专题目录均有 `README.md` 作为文件索引和阅读入口。

## 主机分组

| 目录 | 主机角色 | 使用方式 |
| --- | --- | --- |
| [`103-感知导航主机/`](103-感知导航主机/README.md) | 实际 hostname 为 `lite` 的 NVIDIA/ROS 感知、定位、建图与导航侧 | 查询 ROS 1/ROS 2、传感器、地图、Transfer 与导航集成。 |
| [`120-运动控制主机/`](120-运动控制主机/README.md) | 实际 hostname 为 `ysc` 的 Rockchip/Lite3 运动控制、视频与网络侧 | 查询 `jy_exe`、RTSP/RTMP、视觉跟随、热点及底层部署资料。 |
| [`103-home-test-docs/`](103-home-test-docs/README.md) | 从 103 功能复现仓库留存的文档副本 | 仅用于追溯；现行代码和部署说明先看 `/home/jack/lite3Code`。 |

## 使用约定

1. 先进入目标主机的 `README.md`，再按专题进入下级目录；
2. 服务状态、地址、端口和资源数据均会随时间变化，变更前必须重新实测；
3. 涉及两机控制链、端口或运行基线时，阅读 [`../operations/host-maintenance.md`](../operations/host-maintenance.md)。
4. 需要从笔记跳到实际代码时，使用 [两库协作索引](../codebase-map.md)；本目录不替代 103 代码仓库。

不要将历史报告中的命令、地址或状态直接当作生产变更依据。
