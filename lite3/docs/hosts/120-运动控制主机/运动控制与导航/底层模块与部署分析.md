# `/home/ysc/module` 深度分析

> 范围：部署脚本、制品类型、调用关系和风险。未写入内核模块或 boot 分区。

## 1. 结论

`module` 是一次性或维护期使用的**底层部署材料目录**，而不是常驻服务模块：它含无线网卡内核模块、设备树/boot 制品，以及两个脚本。当前 systemd 没有直接从该目录启动服务。

`deploy.sh` 会安装内核模块、直接写 boot 分区，并把 `host_start2.sh` 覆盖复制到 `/home/ysc/host/`；影响范围极高。已验证，目录中的 `host_start2.sh` 与当前 `host/host_start2.sh` 内容完全相同。

## 2. 目录与未展开制品

| 位置 | 整体用途 | 跳过原因 | 项目定位 |
| --- | --- | --- | --- |
| `8822ce.ko` | AArch64 内核可加载模块，名称表明与 Realtek 8822CE 无线设备相关 | 二进制内核制品，不反汇编 | Wi-Fi 驱动部署材料 |
| `yz-web-s3588-ysc-v10.img` | 设备树 Blob（DTB）格式 boot 制品 | 固件/启动分区制品，不逐字段展开 | 板级硬件描述/启动配置 |

目录无 `lib`、`build` 或第三方源码子树；上述二进制制品保留名称与用途，但不展开内部文件。

## 3. 脚本清单与执行流程

| 脚本 | 参数 | 执行流程 | 下游 |
| --- | --- | --- | --- |
| `deploy.sh` | 无参数；假定当前工作目录就是 `module/` | 复制 `8822ce.ko` 到 `/system/lib/modules/`；以 `dd` 将 `.img` 写入 `/dev/disk/by-partlabel/boot`；复制 `host_start2.sh` 到 `/home/ysc/host/` | 内核模块目录、boot 分区、`host/host_start2.sh` |
| `host_start2.sh` | 无参数；由 `host.service` 经 `host_start.sh` 符号链接使用 | 每 5 秒等待 `p2p0`；向 NAT POSTROUTING 追加两条 MASQUERADE；调用 `host/ap_start.sh start 5G` | iptables、热点 profile、`p2p0` |

`host_start2.sh` 的网络链路为：`192.168.2.0/24` 经 `eth1` 做 NAT，`192.168.137.0/24` 经 `wlan0` 做 NAT，然后创建 5G 热点。该脚本的作用与运行中的热点/网络方案有直接关系，但当前 `host.service` 是 enabled + inactive。

## 4. 关键配置与依赖

| 依赖 | 说明 |
| --- | --- |
| `sudo` | `deploy.sh` 的复制和 `dd` 均要求管理员权限 |
| `/dev/disk/by-partlabel/boot` | 硬编码 boot 分区标签；依赖当前存储布局 |
| 内核版本/模块 ABI | `8822ce.ko` 必须匹配正在运行的内核和硬件 |
| `p2p0` | `host_start2.sh` 无限等待该接口出现 |
| `iptables` | 用 legacy iptables NAT；依赖规则集/后端兼容性 |
| `host/ap_start.sh` 与 NetworkManager | 负责创建热点和 IPv4 shared 模式 |

## 5. 风险与维护建议

1. **最高风险：boot 分区覆盖。**`dd` 无确认、无备份、无校验、无 `set -e`；即使前一步复制失败，脚本仍可能继续写 boot 分区。只能在确认分区标签、镜像版本和可恢复介质后执行。
2. **内核模块兼容性。**复制 `.ko` 不等于加载成功；不匹配时可能导致 Wi-Fi 驱动不可用甚至影响启动后的网络。
3. **相对路径依赖。**`deploy.sh` 不计算自身目录，必须从 `module/` 作为工作目录运行；从其他目录执行会找不到制品或复制错误对象。
4. **NAT 规则重复。**`host_start2.sh` 每次运行均用 `iptables -A` 追加，未检查已有规则；重复启动会积累重复项。
5. **热点副作用。**脚本会重建 `myap50G` profile，可能影响当前热点 SSID、地址前缀和连接设备。网络变更前应备份 NetworkManager profile 和防火墙规则。

