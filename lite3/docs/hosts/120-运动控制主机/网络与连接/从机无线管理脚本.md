# `/home/ysc/slave` 深度分析

> 范围：从机 Wi-Fi 管理脚本。目录没有依赖包、构建产物或第三方库子目录，因此没有额外的跳过项。

## 1. 结论

`slave` 是为从机或手工网络维护准备的两个 NetworkManager 脚本。它没有 systemd 服务入口，也不在当前活动主链路中。两个脚本都直接改写保存的 Wi-Fi 连接，特别是 `p2p0` 当前在本机热点架构中具有重要角色，误运行会破坏现有热点或连接状态。

## 2. 目录与入口

| 位置 | 用途 | 项目定位 |
| --- | --- | --- |
| `clean_wifi.sh` | 删除保存的 Wi-Fi profile | 手工清理工具 |
| `connect_wifi.sh` | 交互式将 `p2p0` 加入指定 Wi-Fi | 手工从机/联网工具 |

未发现 `lib`、`build`、SDK、模型、缓存或第三方目录；无须跳过额外子树。

## 3. 脚本清单与执行流程

| 脚本 | 参数/输入 | 执行流程 | 上下游依赖 |
| --- | --- | --- | --- |
| `clean_wifi.sh` | 无命令行参数 | 通过 `nmcli connection show` 筛出含 `wifi` 的行；逐行用 awk 取第二列作为 UUID；执行 `nmcli con delete uuid` | NetworkManager 已保存连接 |
| `connect_wifi.sh` | 交互输入 SSID 和密码；密码可留空 | 固定接口 `p2p0`；校验 SSID 非空；输入密码后调用 `nmcli dev wifi connect ... ifname p2p0` | `p2p0`、NetworkManager、目标 AP |

## 4. 关键配置与调用关系

- `connect_wifi.sh` 把无线接口硬编码为 `p2p0`。
- 若密码输入为空，脚本会使用脚本内置的默认 WPA 凭据；本报告不记录其值。
- 两个脚本仅由操作者手工调用，未发现 systemd、cron 或其他脚本调用它们。

## 5. 风险与维护建议

1. **热点角色冲突。**当前主机的热点使用 `p2p0`；运行 `connect_wifi.sh` 可能将该接口切换为客户端模式，使热点 SSID 消失或客户端断开。
2. **过度删除。**`clean_wifi.sh` 会删除所有被 `nmcli` 输出匹配为 Wi-Fi 的保存连接，而非只删除某一个目标 SSID；错误解析列时也可能删错 profile。
3. **凭据管理。**默认凭据硬编码在脚本中，且连接命令会由系统记录 connection profile。应只在受控环境使用，并迁移到权限受限的配置方式。
4. 操作前应先执行 `nmcli connection show`、`nmcli device status` 并导出当前 NetworkManager 连接；操作后验证热点、默认路由和已连接客户端。

