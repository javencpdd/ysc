# Lite3 机器人 SSH 技能

在连接机器人主机前核对当前 Wi-Fi 热点，并将 SSH 连接固定在对应的热点网卡上。适合本机同时连着办公网和 Lite3 热点的情况；脚本不修改系统路由。主机参数集中在配置文件，新增或更换主机不需要改脚本。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| [`SKILL.md`](SKILL.md) | Codex 技能触发条件与安全连接规则。 |
| [`config/hosts.conf`](config/hosts.conf) | 逐主机配置名称、必需 SSID、SSH 别名、IPv4、用户。 |
| [`scripts/lite3-ssh`](scripts/lite3-ssh) | 实际 SSID 检查、配置核验、端口探测和 SSH 连接。 |
| [`references/hosts-ops.md`](references/hosts-ops.md) | 只读运维命令示例。 |

## 前提与配置

本机需要 Linux、`bash`、`nmcli`、`iw`、`socat`、`ssh` 和 `timeout`。连接目标前，先让本机连接该主机配置的热点。当前配置为：

```text
# 名称|必需热点 SSID|SSH 别名|目标 IPv4|登录用户
103|YSC-JYML-aw3bal-5G|ysc-f20-103|192.168.1.103|ysc
120|YSC-JYML-aw3bal-5G|ysc-f20-120|192.168.1.120|ysc
```

需要其他主机时，在 `config/hosts.conf` 中按行添加或修改。字段用 `|` 分隔；名称、SSH 别名和用户仅用字母、数字、下划线、点、连字符，SSID 不可包含 `|`。可用 `LITE3_SSH_CONFIG=/absolute/path/hosts.conf` 指定另一份配置，便于不同项目共用脚本。脚本将核对 `ssh -G <别名>` 的地址与用户，端口使用 SSH 配置解析值。

本机 `~/.ssh/config` 也必须有匹配的别名，例如：

```sshconfig
Host ysc-f20-120
    HostName 192.168.1.120
    User ysc
```

别名不匹配时脚本会停止。首次连接要通过可信渠道核对主机密钥指纹；脚本不会关闭严格主机密钥检查。密码或私钥仅由 SSH 正常交互处理，不要写进本配置、文档、命令行或日志。

## 快速开始

从仓库根目录执行：

```bash
script/lite3-robot-ssh/scripts/lite3-ssh --check
script/lite3-robot-ssh/scripts/lite3-ssh --check 120
script/lite3-robot-ssh/scripts/lite3-ssh 120
script/lite3-robot-ssh/scripts/lite3-ssh 120 'hostname; id -un; uname -r'
```

`--check` 不带名称时检查配置中的所有主机；它只验证实际 SSID、别名和 SSH 端口，不验证登录凭据。连接命令可以进入交互 shell，也可以在主机名后传远端命令。2026-09-25 实测：103 的 hostname 为 `lite`、内核 `5.10.120-tegra`；120 的 hostname 为 `ysc`、内核 `5.10.198`。这些只是当时观测值，操作前请重新确认。

## 在 Codex 中启用

该目录保存在仓库 `script/` 下。若要让新 Codex 会话自动发现它，可在本机运行：

```bash
ln -s /home/jack/云深处/lite3/script/lite3-robot-ssh /home/jack/.codex/skills/lite3-robot-ssh
```

重启 Codex 会话后，可要求“使用 `lite3-robot-ssh` 检查 120 主机”。也可不安装 skill，直接调用脚本。使用 MCP 工具时，仍须先验证实际热点和连接路径；MCP 的普通 SSH 别名连接不一定选中热点网卡。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 提示未连接指定热点 | 用 `nmcli device status`、`iw dev <网卡> link` 核对实际 SSID，连上后重试。 |
| 普通 SSH 超时，脚本可达 | 多网卡时普通路由可能选中其他网络；本脚本只为 SSH 绑定热点接口。 |
| `--check` 成功但登录失败 | 分别检查认证凭据、SSH 用户及主机密钥；端口通不等于能登录。 |
| 别名与配置不一致 | 修正 `hosts.conf` 或 `~/.ssh/config`，确保地址和用户吻合。 |
| 主机密钥未知或变化 | 通过可信渠道核对指纹后再处理 `known_hosts`，不要直接关闭校验。 |

运维前先确认当前主机身份及实时状态；涉及网络、服务或机器人控制的变更，应以具体任务授权为准。
