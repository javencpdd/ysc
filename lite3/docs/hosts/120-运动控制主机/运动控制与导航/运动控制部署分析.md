# `/home/ysc/jy_exe` 深度分析

## 1. 结论与运行入口

`jy_exe` 是当前活动的 Lite3 运动控制部署目录。`jy_exe.service` 已 enabled 且 active，服务入口为：

```text
/etc/systemd/system/jy_exe.service
  -> /home/ysc/jy_exe/run.sh
      -> scripts/clean_expired_log.sh
      -> catchsegv bin/jy_exe [可选第一个参数]
          -> bin/jy_exe (当前为指向 backup/deeprcs 的符号链接)
```

systemd unit 未指定 `User=`，实际以 root 启动。`deeprcs` 为厂商闭源运动控制二进制；本报告只分析其外围脚本、配置和可见调用关系，不反编译或执行它。

## 2. 目录、入口与未展开内容

| 位置 | 整体用途 | 处理方式/原因 | 项目定位 |
| --- | --- | --- | --- |
| `bin/` | 运行入口、备份二进制及版本记录 | 只检查入口、符号链接和版本脚本；不反编译 ELF | 核心闭源运行时 |
| `bin/backup/` | `deeprcs` 与厂商动态库备份 | 不递归二进制/动态库内部 | 运行时恢复/备份制品 |
| `lib/`、`libdeepras.so` | EtherCAT、RAS 等动态依赖 | 第三方/厂商运行库，按规则跳过 | 底层硬件通信依赖 |
| `robot_common/` | 共享机器人组件目录 | 厂商支持组件，未见本任务所需脚本入口，未展开 | 公共运行时支持 |
| `policy/` | `.pt`、`.onnx` 步态/行为策略 | 模型资产，不逐模型分析 | 推理/行为策略输入 |
| `data/` | 运行数据 | 运行时生成/消费数据，不逐文件分析 | 数据缓存/记录 |
| `log/` | 控制器和启动日志 | 运行时日志，不逐文件分析 | 排障证据；由清理脚本维护 |
| `conf/*.csv` | 特技/轨迹数据 | 数值资产，不逐条分析 | 动作控制配置 |

## 3. 脚本清单与逐项流程

| 脚本 | 参数/调用场景 | 执行流程 | 上下游关系 |
| --- | --- | --- | --- |
| `scripts/run.sh` | service 入口；可透传第一个参数给二进制 | 推导根目录；设 CPU governor 为 performance；固定 IRQ 81–83 的 CPU affinity；清日志；切到 `bin`；以 `catchsegv` 执行 `jy_exe`，标准输出经 `tee` 写入带时间戳日志 | 调 `clean_expired_log.sh`；启动 `bin/jy_exe` |
| `scripts/clean_expired_log.sh` | 由 `run.sh` 自动调用 | 删除 `log/` 中超过 10 天的 `.log`，`data/` 中超过 10 天的 `.csv`/`.gz`，并额外清理 `/home` 顶层同类旧文件 | 日志/数据保留策略 |
| `scripts/restart.sh` | 手工维护 | `systemctl restart jy_exe.service` | 重启整个运动控制服务 |
| `scripts/stop.sh` | 手工维护 | `systemctl stop jy_exe.service` | 停止运动控制服务 |
| `scripts/enable_autorun.sh` | 手工维护 | enable `jy_exe.service` 后 daemon-reload | 设置开机自启 |
| `scripts/disable_autorun.sh` | 手工维护 | stop、disable、daemon-reload | 关闭当前服务和自启 |
| `scripts/show_log.sh` | 手工排障 | 依据当天日期构造 `deeprcs.YYYY_MMDD.log`，持续 tail | 依赖日志目录命名约定 |
| `scripts/ap_start.sh` | `start 5G` / `start 24G` / `stop`；`wifi.service` 模板入口 | 选 `p2p0` 优先、否则 `wlan0`；创建或删除 NetworkManager 的 `myap24G`/`myap50G` profile；使用共享 IPv4 模式 | 旧/备用热点实现；`wifi.service` 当前 disabled |
| `scripts/disable_motor.sh` | 手工维护 | 重置 CAN0–CAN2 为 1 Mbit/s，并发送多帧 CAN 报文 | 直接影响电机通信 |
| `scripts/install.sh` | 安装/修复 | 修改 `bin/*`、`scripts/*` 权限，并尝试在 `/etc`、`/home` 建配置链接 | 部署辅助脚本 |
| `scripts/recovery.sh` | 恢复/回退 | 备份非软链接的 `bin/jy_exe`；重建 `libdeepras.so` 链接；将 `bin/jy_exe` 指到 `backup/jy_exe` | 二进制恢复辅助 |
| `scripts/runrpc.sh` | EtherCAT 调试 | 设置库路径，启动 loopback、资源管理器和 EtherCAT RPC server | 旧调试入口；当前依赖不完整 |
| `scripts/push_video.sh` | 占位脚本 | 仅保留注释的 GStreamer 示例，没有实际命令 | 已被独立 `rtsp_stream` 取代 |
| `bin/backup/version.sh` | 手工查询 | 输出部署版本 `2.0.158` | 备份二进制版本标识 |

## 4. 关键配置及依赖

| 文件 | 关键项 | 对运行的意义 |
| --- | --- | --- |
| `conf/network.toml` | 上位/感知侧 IP `192.168.1.103`；目标端口 `43897`；本地端口 `43893` | 运动控制、SDK 状态和感知/SLAM 对接的网络依赖 |
| `conf/Algorithm.toml` | 速度偏置、站立高度、特技开关、默认雷达标记、负载/偏心、各类增益/补偿 | 直接影响运动行为与机型能力开关 |
| `conf/deeprcs.json` | 机器人模块身份及运动偏置/站高 | 厂商控制程序读取的设备/行为配置 |
| `conf/motor.toml` | `timeout = 200` | 电机超时控制参数 |
| `conf/name.toml` | `professional_2` | 机型/产品类型选择 |
| `conf/model_config.yaml` | 高低电量补偿参数 | 电池状态相关动作补偿 |
| `conf/flat_rl_config.yaml`、`handstand_rl_config.yaml` | 速度/加速度、关节增益、通信端口、栅格地图端口、模型路径 | RL/动作策略配置；当前主 `deeprcs` 的实际读取关系只能由厂商程序确认 |
| `jy_exe.service` | `ExecStart=/home/ysc/jy_exe/run.sh` | 当前安装并运行的主服务定义 |
| `wifi.service` | 调用 `scripts/ap_start.sh start 5G` | 目录内模板；当前系统 service disabled |
| `push.service` | 指向 `/home/firefly/jy_exe/push_video.sh` | 旧硬编码路径模板，不是当前视频入口 |

## 5. 已核实的风险与硬编码依赖

### 高风险：直接影响机器人或系统

1. `run.sh` 在 root 上下文修改所有 CPU governor 和指定 IRQ 的 affinity；IRQ 编号、CPU 路径均硬编码，换板或内核版本后可能失效。
2. `disable_motor.sh` 的首行是异常的 `i#!/bin/bash`，但其后仍会重配 CAN 并发送电机相关报文。不要以“脚本首行有误”推断它无副作用。
3. `clean_expired_log.sh` 使用 `rm -rf`，除模块自身日志/数据外还清理 `/home` 顶层超过 10 天的 `.csv` 和 `.gz`；它会在每次 `jy_exe` 启动时自动执行。
4. `Algorithm.toml`、RL 配置和策略文件影响机体姿态、速度、特技与负载补偿；改动需在维护窗口、低风险环境和明确回滚条件下进行。

### 配置冲突与失效引用

1. `scripts/ap_start.sh` 与 `host/ap_start.sh` 都操作同名 `myap24G`/`myap50G` NetworkManager profile，但地址前缀、SSID 生成规则和用途不同。若启用 `wifi.service`，可能删除并重建当前热点 profile。
2. 该热点脚本含硬编码 WPA 凭据；本报告不记录其值。应迁移到受限权限的机密配置或 NetworkManager 密钥管理，而不是继续保存在可读脚本中。
3. `recovery.sh` 指向的 `bin/backup/jy_exe` 当前不存在；运行后可能制造悬空的 `bin/jy_exe` 链接，导致核心服务无法启动。
4. `install.sh` 预期的 `conf/LinuxEcatKPAMaster.ini` 当前不存在；脚本无法产生有效的 `/etc/LinuxEcatKPAMaster.ini` 链接。`/home/deeprcs.json` 链接目前存在并指向本目录配置。
5. `runrpc.sh` 所需的 `ecatrsmngr`、`ecatmrpcserver`、`master.xml` 均未在当前路径找到，属于不可直接使用的旧调试入口。
6. `push.service` 仍硬编码 `/home/firefly`，该路径当前不存在。

## 6. 维护建议

- 正常运行、查看日志、停止或重启只使用 systemd 和现有 `run.sh` 链路；不要把恢复、安装、RPC、CAN 脚本混作日常操作。
- 任何改动前备份目标配置、记录 `systemctl status jy_exe.service`、`ip route`、NetworkManager profile 和当前软链接目标。
- 修复失效脚本前先由厂商确认正确的 `deeprcs`/EtherCAT 制品版本，不应手工猜测链接目标。
- 若调整热点，统一选择 `host` 或 `jy_exe` 的一种实现，并先停止/禁用另一条入口，避免两个脚本争夺 `p2p0` 和同名 profile。

