# 主机运维速查

从仓库根目录调用 `script/lite3-robot-ssh/scripts/lite3-ssh`。以下以配置中的 `120` 为例；更换主机时改用 `config/hosts.conf` 中的名称。所有命令只读。

```bash
script/lite3-robot-ssh/scripts/lite3-ssh --check 120
script/lite3-robot-ssh/scripts/lite3-ssh 120 'hostname; id -un; uname -a'
script/lite3-robot-ssh/scripts/lite3-ssh 120 'ip -br address; ip route'
script/lite3-robot-ssh/scripts/lite3-ssh 120 'df -hT; lsblk'
script/lite3-robot-ssh/scripts/lite3-ssh 120 'systemctl --no-pager --failed'
```

`--check` 只验证热点、别名和 SSH 端口；实际登录还需要可用凭据及受信任的主机密钥。不要在笔记中记录密码。排查用户级服务时，可在远端命令中设置 `XDG_RUNTIME_DIR=/run/user/$(id -u)` 后调用 `systemctl --user`；运行前仍应核对远端用户和当前会话环境。

## 120：视频推流检查

历史笔记提到 `/home/ysc/rtsp_stream/`、`rtsp_stream.service` 和用户级 `rtmp-forward.service`。它们是否仍在使用，需以当前文件、进程和服务状态为准，不要根据笔记直接重启。

```bash
script/lite3-robot-ssh/scripts/lite3-ssh 120 'ls -ld /home/ysc/rtsp_stream; systemctl status rtsp_stream.service --no-pager'
script/lite3-robot-ssh/scripts/lite3-ssh 120 'XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user show rtmp-forward.service -p ActiveState -p MainPID -p NRestarts'
script/lite3-robot-ssh/scripts/lite3-ssh 120 'ps -eo pid,args | grep "[g]st-launch-1.0"'
script/lite3-robot-ssh/scripts/lite3-ssh 120 'ss -lntup; ss -tnp'
```

采集与转发可能是两条独立的 GStreamer 管线，不能仅凭第一个 `gst-launch-1.0` PID 判断转发是否运行。推送地址和 stream key 以当前脚本、服务配置与完整进程命令行为准。

## 103：ROS 与监控检查

历史笔记提到 `lite3-monitor*.service` 和 `lite3-ros-bridge*.service`；实例名及端口可能变化。

```bash
script/lite3-robot-ssh/scripts/lite3-ssh 103 'systemctl list-units --all "lite3-monitor*" "lite3-ros-bridge*" --no-pager'
script/lite3-robot-ssh/scripts/lite3-ssh 103 'ps -eo pid,args | grep -E "[u]vicorn|[r]os_bridge"; ss -lntup'
```

## 网络与日志

历史笔记记录 103 的出网可能依赖 120 的 NAT。遇到 103 可达局域网但无法出网时，先分别检查两机的实时路由、转发和 NAT 规则；不要直接套用旧规则或接口名。主机重启可能清空内存型 journal，查历史故障时还应检查持久化日志是否存在、是否有读取权限。
