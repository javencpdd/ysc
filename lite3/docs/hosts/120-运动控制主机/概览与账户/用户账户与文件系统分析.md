# `user` 与 `ysc` 账户及文件关系分析

> 取证方式：通过 `mcp-ssh-apply-patch` 对 `user-f20` 执行账户、权限、挂载、目录元数据、文件内容比较和服务配置的**只读**检查。
>
> 未读取密码散列、私钥或 SSH 已知主机内容；未修改远端用户、文件、服务或网络。

## 1. 结论

`user` 和 `ysc` 是同一块运动主机上的**两个独立 Linux 账户**，不存在“`user` 是 `ysc` 的子用户”或“一个家目录挂载到另一个家目录”的关系。

- `/home/user` 和 `/home/ysc` 都是根文件系统中两个独立目录，inode 不同，均不是软链接、bind mount 或网络挂载。
- `user` 是可交互的管理账户：UID/GID `1000`，属于 `sudo` 组；需要使用 sudo 时可获得系统管理能力。
- `ysc` 是机器人软件的运行时/部署账户：UID/GID `998`，属于 `video` 组；当前机器人关键服务均从 `/home/ysc/...` 启动。
- 两者均有一份名为 `jy_exe` 的目录，但它们是**不同 inode 的独立副本**。共同文件的字节内容相同，但没有任何文件共享 inode，因此不是硬链接，也没有实时同步。
- `user/jy_exe` 的文件更多、体积更大且时间更旧；`ysc/jy_exe` 是较小、较新的运行时部署目录，并包含当前服务使用的启动脚本、二进制、策略和配置。

所以，资源管理器里“看起来是子集”的直觉来自两个账户都保存了相同软件包的部分内容，而不是文件系统层面的父子、共享或同步关系。

## 2. 账户与权限关系

| 项目 | `user` | `ysc` | 含义 |
| --- | --- | --- | --- |
| passwd 条目 | `user:x:1000:1000::/home/user:/bin/bash` | `ysc:x:998:998::/home/ysc:/bin/bash` | UID/GID 均不同，是两个独立账户 |
| 主组 | `user`（GID 1000） | `ysc`（GID 998） | 不共享主组 |
| 补充组 | `sudo` | `video` | `user` 可经 sudo 管理系统；`ysc` 具有视频设备相关权限 |
| 家目录所有者 | `user:user` | `ysc:ysc` | 各自拥有各自的家目录 |
| 家目录模式 | `755` | `755` | 可进入目录；子目录/文件权限各自独立 |

这不是账号继承关系。标准 Linux 中账户之间也没有“家目录子集”这一内建概念。

### 权限上的实际不对称

`user` 是 sudo 组成员，意味着经过显式 sudo 提权后，可以管理 `/home/ysc` 中的部署内容和 systemd 服务。`ysc` 不属于 sudo 组，且其可见的补充组是 `video`。因此，若只从系统管理权限看，`user` 的权限更高；但这不代表 `/home/user` 的文件会自动从 `/home/ysc` 继承或同步。

## 3. 文件系统证据

两份家目录都位于同一个本地根分区：`/dev/mmcblk0p8`（ext4，读写挂载）。

| 路径 | inode | 设备 | 所有者/模式 | 结论 |
| --- | ---: | --- | --- | --- |
| `/home/user` | `71813` | `b308` | `user:user`, `755` | 独立目录 |
| `/home/ysc` | `71814` | `b308` | `ysc:ysc`, `755` | 独立目录 |

`readlink -f` 分别返回其自身路径，`findmnt -T` 对二者都只显示根 ext4 分区；没有发现符号链接、独立挂载点或 bind mount 证据。

## 4. 家目录内容与运行时角色

### 4.1 顶层内容差异

`/home/user` 主要有：`jy_exe`、`lite3_voice`、`testsh` 以及编辑器/Codex/npm 等用户工具目录。

`/home/ysc` 除 `jy_exe`、`lite3_voice` 外，还包含以下机器人运行时/开发资产：

- `Lite3_MotionSDK`、`sdk_lib`：运动 SDK 和传输库；
- `rtsp_stream`、`track`：RTSP 视频流和视觉跟随组件；
- `host`、`master`、`module`、`slave`、`qirui`、`.zetton` 等部署/工具目录；
- 运行策略、日志、安装包和厂商相关程序。

因此从“顶层项目数量”看，`ysc` 看起来更完整；但这不表示 `user` 的内容是它的子集。

### 4.2 systemd 的实际引用

当前关键服务全部指向 `/home/ysc`，例如：

| 服务 | 启动路径 | 状态 |
| --- | --- | --- |
| `jy_exe.service` | `/home/ysc/jy_exe/run.sh` | active |
| `track.service` | `/home/ysc/track/start_track.sh` | active |
| `rtsp_stream.service` | `/home/ysc/rtsp_stream/start_stream.sh` | active |
| `wifi.service` | `/home/ysc/jy_exe/scripts/ap_start.sh start 5G` | 已配置 |
| `host.service` | `/home/ysc/host/host_start.sh` | 已配置 |

未发现 systemd 服务引用 `/home/user/...`。这说明 `ysc` 是当前机器人软件的部署根，而 `/home/user` 更像管理/开发账户保留的独立副本和工具目录。

## 5. 两份 `jy_exe` 的关系

### 5.1 元数据比较

| 项目 | `/home/user/jy_exe` | `/home/ysc/jy_exe` |
| --- | --- | --- |
| 所有者/模式 | `user:user`，`775` | `ysc:ysc`，`755` |
| inode | `71818` | `97962` |
| 修改时间 | `2024-04-25 10:46:17 +0800` | `2026-08-06 16:42:05 +0800` |
| 目录占用 | 约 `550 MiB` | 约 `273 MiB` |
| 条目数 | `19,893` | `1,758` |
| 当前 systemd 使用 | 否 | 是 |

`/home/user/jy_exe/bin/jy_exe` 不存在；当前实际运行的 `/home/ysc/jy_exe/bin/jy_exe` 是指向 `backup/deeprcs` 的符号链接，并由 `jy_exe.service` 启动。

### 5.2 内容重叠与复制证据

对两棵 `jy_exe` 目录按相对路径进行了只读逐文件比较：

- 从 `user/jy_exe` 看：`19,893` 个条目中，`18,232` 个在 `ysc/jy_exe` 没有对应路径；有 `1,526` 个规则文件字节完全相同，未发现同路径但字节不同的普通文件。
- 从 `ysc/jy_exe` 看：`1,758` 个条目中，仅 `97` 个在 `user/jy_exe` 不存在；同样有 `1,526` 个规则文件字节完全相同。
- 对所有同内容普通文件检查 inode：共享 inode 数为 **0**。

这表明 `ysc/jy_exe` 大部分内容与 `user/jy_exe` 的同名内容来自相同版本/同一次打包，但二者是**实际复制出的独立文件**。同时，`ysc/jy_exe` 有自己的新启动脚本、运行二进制、策略文件、配置和日志；`user/jy_exe` 则保留大量在运行时精简包中不需要的库、头文件和工具文件。

最合理的解释是“历史安装包/开发包被分别部署给两个账户，之后 `ysc` 的运行时包单独更新”，而不是实时镜像。这个解释是基于时间、内容和服务引用的推断；没有发现能证明具体复制时间或操作者的日志。

### 5.3 `lite3_voice` 也不是共享目录

两份 `lite3_voice` 目录的 inode 不同，所有者和修改时间也不同：

- `/home/user/lite3_voice`：`root:root`，inode `391705`；
- `/home/ysc/lite3_voice`：`ysc:ysc`，inode `97963`。

因此该目录同样不是软链接、硬链接或同一挂载目录。

## 6. 是否存在自动同步

本次检查未发现 `user` 与 `ysc` 家目录之间的自动同步证据：

- 没有运行中的 `rsync`、Syncthing、Unison 或 `inotifywait` 相关进程；
- 没有发现 systemd/cron 中将 `/home/user` 与 `/home/ysc` 互相复制的引用；
- `rsync.service` 虽被启用，但当前 inactive，且 `/etc/rsyncd.conf` 不存在，不能构成两个目录的同步任务；
- 共同文件 inode 不同，排除硬链接共享。

不能完全排除有人曾手工复制、离线恢复或从同一安装包分别安装；但当前没有持续同步的系统机制。

## 7. 操作建议与边界

1. **不要将 `/home/user/jy_exe` 当作当前运行目录。**它不是 `jy_exe.service` 的启动源；直接运行其中脚本/二进制仍可能与硬件通信，不能视为安全测试副本。
2. **不要直接删除任一目录来“去重”。**两者均可能含有恢复、升级或开发所需资产；删除前应先做可恢复备份并在停机维护窗口验证服务。
3. **当前运行配置以 `/home/ysc` 为准。**尤其是 `jy_exe/conf`、`scripts`、`bin`、RTSP、热点和跟踪服务引用的路径；这里的改动会直接影响机器人。
4. **将 `user` 用作管理/分析入口。**它有 sudo 能力，适合保存报告和进行只读审计；如需进行受控变更，应先备份 `/home/ysc` 的目标文件、记录服务状态，并制定回滚步骤。
5. **若要确认复制历史，需额外检查安装/升级记录。**例如 Debian 包安装日志、维护脚本或备份介质；本报告没有读取这些可能含有操作人员信息的历史记录。

