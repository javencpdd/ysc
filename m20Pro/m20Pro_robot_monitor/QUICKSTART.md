# QUICKSTART — M20 Pro Web 控制台

> 从零到跑通：**构建 → 打包 → 安装 → 验证**，约 10 分钟。
> 部署目标：AOS 主机 **192.168.0.196**（SSH 别名 `m20pro-f20-0-196`），安装目录 **`/home/djw/monitor`**。
> 深度内容见 [README.md](README.md) 与 [docs/](docs/)；完整方案见 [note/ 计划书](note/M20%20Pro%20Web%20控制台%20—%20计划书v1.md)。

---

## 0. 前置条件

| 项 | 要求 |
| --- | --- |
| PC | 可 SSH 到 196（`ssh m20pro-f20-0-196` 免密），装有 Node.js（构建前端）与 Python 3（跑测试） |
| 196 | 在线（AOS 主机），`python3` = 3.8.10，磁盘 `~/` 有 ≥1G 余量 |
| 机器人 | 不强制在线——控制台无数据时会显示"链路断开"，服务本身可先起 |

> 196 上 `sudo` 需要密码，非交互场景用：`printf "'\n" | sudo -S <cmd>`。

---

## 1. 三步部署

### ① PC：构建前端

```bash
cd m20Pro_robot_monitor/frontend
npm run build          # 产物在 frontend/dist/
cd ..
```

> 前端必须在 PC 构建：196 未验证 Node 环境，且其系统时钟慢 846 天会让 npm 的 HTTPS 全部失败。

### ② PC：打包并上传

```bash
bash deploy/pack.sh                       # 生成 m20pro-console-deploy.tar.gz（自动剔除 node_modules/venv）
scp m20pro-console-deploy.tar.gz m20pro-f20-0-196:/tmp/
```

### ③ 196：解压安装

```bash
ssh m20pro-f20-0-196
cd /tmp && tar xzf m20pro-console-deploy.tar.gz
sudo bash m20pro_console/deploy/install.sh /home/djw/monitor
```

`install.sh` 自动完成：

1. 复制 backend / frontend/dist / tools / note 到 `/home/djw/monitor`（`rsync -a --delete`，防 `cp -r` 嵌套坑）；
2. 建 venv（三层降级：`python3 -m venv` → `apt install python3.8-venv` → `virtualenv`）；
3. pip 装依赖走 **http 阿里镜像 + `--trusted-host`**（绕开 TLS/时钟问题）；
4. 生成 systemd 单元（路径替换为实际安装目录 + `User=` 自动探测）并 `enable + restart`；
5. 打印健康检查结果。

---

## 2. 验证

```bash
# 在 196（或任何能访问 8080 的机器）执行
python3 /home/djw/monitor/tools/verify_deploy.py
```

期望输出：**13 项全绿**——

| 组 | 检查 |
| --- | --- |
| 链路 | `/health`（connected=true, source=udp）、`/ready`（非降级） |
| 数据 | 快照 schema_version=1.0、`basic`/`motion`/`device`/`fault`/`nav` 各 topic 非 stale 且字段数正常 |
| 视频 | `/api/v1/video/status`（running + available）、HLS 播放列表 200 |
| 页面 | 前端静态资源 200 |

浏览器打开 **`http://192.168.0.196:8080/`**，应看到：基础/设备/异常面板 + 16 关节面板 + 运动控制面板 + 相机画面面板，右上角"链路在线"。

---

## 3. 无真机演练（本地 Mock 模式）

机器人不在线也能把全部功能走一遍（MockSource 用**真实字节帧**驱动）：

```bash
cd m20Pro_robot_monitor/backend
M20__DATA_SOURCE=mock python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

浏览器打开 `http://127.0.0.1:8080/`：状态持续更新、关节数值摆动、控制面板可开 L1（Mock 下 `RecordingSink` 记录指令不真发）。

---

## 4. 日常迭代（改了代码怎么更新）

**后端 / 前端小改**——增量同步，不重装、不重建 venv：

```bash
# PC 侧（Windows 本机无 rsync 时用 tar+scp 方式，见下）
cd frontend && npm run build && cd ..     # 只有前端改动才需要
bash deploy/deploy_196.sh                 # rsync backend + dist → systemctl restart
```

> ⚠️ 本机（Windows Git Bash）**没有 rsync**，`deploy_196.sh` 会失败。替代方式（以更新前端为例）：

```bash
tar czf /tmp/m20-dist.tar.gz -C frontend dist
scp /tmp/m20-dist.tar.gz m20pro-f20-0-196:/tmp/
ssh m20pro-f20-0-196 "cd /home/djw/monitor/frontend && rm -rf dist.old && mv dist dist.old && \
  tar xzf /tmp/m20-dist.tar.gz -C . && rm -rf dist.old"
# 静态资源按请求读盘，无需重启服务；后端改动才需要：
ssh m20pro-f20-0-196 "printf \"'\n\" | sudo -S systemctl restart m20pro-console"
```

**只有这 4 种情况才需要重跑 `install.sh`**：改了 `requirements.txt`、改了 `deploy/*.service`、要部署全新构建的 `frontend/dist`（或换了安装目录）、首次安装。

---

## 5. 看视频前先唤醒机器人

相机随机器人供电——**休眠时相机不通电**，`/dev/video*` 不存在、MediaMTX 无流、视频面板显示"视频源不可用"。

```bash
# 唤醒全车（含传感器，相机随之通电）
python3 /home/djw/monitor/tools/probe_asdu.py --send 1101/6 --items '{"Sleep":false}'
# 约 3~5 秒后重试视频；确认流在线：
python3 /home/djw/monitor/tools/probe_asdu.py --query 1101/7
```

---

## 6. 常见故障速查

| 现象 | 先查这里 |
| --- | --- |
| 页面打不开 | `systemctl status m20pro-console`；`journalctl -u m20pro-console -n 50` |
| 页面能开但"链路断开" | 机器人是否上电；`curl 127.0.0.1:8080/health`；196 上 `tcpdump -i any -nn udp port 30000 -c 5` |
| 部分面板置灰 | `/ready` 看哪些 topic stale；休眠中的机器人 `nav`/`motion` 停更是正常现象 |
| 视频面板提示"源不可用" | 先唤醒机器人（见上）；`curl 127.0.0.1:8554` 是否 MediaMTX 在线；`journalctl -u m20pro-console \| grep -i ffmpeg` |
| 控制指令返回 `CONTROL_DISABLED` | 需先 `POST /api/v1/control/enable {"enable":true,"confirmed":true}` |
| 控制指令返回 `LEASE_EXPIRED` | 前端需持续续约（WS 在线即自动续）；WS 断开重连即可 |
| 轴指令被拒 `PRECONDITION` | 需先"站立"（MotionParam=1/17）且常规模式（Mode=0） |
| 部署后改动"不生效" | 九成是打包/同步静默失败——核对 196 上文件 mtime 与内容；`install.sh` 已内置防嵌套清理 |
| 时钟相关报错（pip/HTTPS） | 196 时钟慢 846 天为已知问题；装依赖必须走 http 镜像（install.sh 已内置） |

完整排错手册见 [docs/debugging.md](docs/debugging.md)。
