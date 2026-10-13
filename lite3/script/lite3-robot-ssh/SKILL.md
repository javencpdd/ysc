---
name: lite3-robot-ssh
description: Safely connect to Lite3 robot hosts over their configured Wi-Fi hotspot for SSH inspection, diagnostics, or maintenance. Use when a task mentions Lite3 hosts, ysc-f20-103, ysc-f20-120, or robot-host SSH access.
---

# Lite3 机器人 SSH

## 连接前必须做的事

1. 读取 [主机配置](config/hosts.conf)，确认目标名称、必需热点 SSID、SSH 别名、IPv4 和用户。需要其他主机时编辑配置文件，不要修改脚本中的主机映射。不要在配置或文档中存放密码。
2. 执行 `scripts/lite3-ssh --check <主机名>`。脚本检查无线网卡**当前实际 SSID**、SSH 别名解析结果，并通过该热点网卡探测 SSH 端口。任一检查失败时停止，不要绕过热点检查直接连接。
3. 检查通过后，用 `scripts/lite3-ssh <主机名> [远端命令]` 连接。该入口只为当前 SSH 连接绑定热点网卡，不改变系统全局路由；必须保留严格主机密钥检查。
4. `--check` 不验证账号认证。若登录失败，分别排查凭据、主机密钥和远端 SSH 服务；不要把密码写入命令、日志或仓库。

配置可通过 `LITE3_SSH_CONFIG=/path/to/hosts.conf` 替换。新增主机需要同时在本机 `~/.ssh/config` 设置对应别名；脚本会核对别名解析出的目标地址和用户。详细格式与示例见 [README](README.md)。

## 操作边界

- 先运行只读命令核对目标身份和实时状态，再决定后续操作；历史笔记不能当作当前配置。
- 如果改用 `mcp-ssh-apply-patch`，必须先完成同样的热点检查，并验证该 MCP 连接实际经过热点网卡。当前本机多网卡路由可能使普通别名连接走错网，无法验证时使用本技能入口。
- 服务重启、网络修改、机器人运动控制或文件写入应以用户任务授权为准，先核对准确目标。
- 常用只读命令见 [主机运维速查](references/hosts-ops.md)。
