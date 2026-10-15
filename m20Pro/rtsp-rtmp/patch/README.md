# 补丁集：相机存活守护 + 日志轮转

> 目标主机：196 AOS（`m20pro-f20-0-196`）
>
> | 补丁 | 状态 | 说明 |
> |---|---|---|
> | **A. 相机推流"假死管道"存活守护**（`camera-liveness-guard`） | ✅ **已于 2026-10-16 部署** | 对应风险 R19 / R31，见本文 §1–§6 |
> | **B. 日志大小上限 + 轮换存储**（`m20-log`） | ✅ **已于 2026-10-16 部署** | 见本文 §7 与 `note/日志轮转方案-20261016.md` |

---

# A. 相机推流"假死管道"存活守护

> 部署日期：2026-10-16（`/usr/local/sbin/camera-liveness-guard.sh` + `cam-guard.{service,timer}`）
> 对应风险：**R19 / R31**（上游相机服务无自愈能力）

---

## 1. 要解决什么

`push_video.sh` 的监控函数 `_is_stream_alive()`（脚本第 394–405 行）**只判断进程是否活着**：

```bash
_is_stream_alive() {
    [ -n "$gst_pid" ] || return 1
    kill -0 "$gst_pid" 2>/dev/null || return 1
    pgrep -P "$gst_pid" "gst-launch" >/dev/null 2>&1 && return 0
    cmdline=$(cat /proc/$gst_pid/cmdline 2>/dev/null | tr '\0' ' ')
    echo "$cmdline" | grep -q "gst-launch" && return 0
    return 1
}
```

于是产生**"活着但不出数据"的假死管道**（2026-10-15 一天内复现 3 次）：

| 观测 | 实测值 |
|---|---|
| `gst-launch` 进程 | 存活，持有 `/dev/video0`、`/dev/mpp_service` |
| 交付给 `rtspclientsink` 的数据 | **0 字节**（`tcpdump -i lo 'tcp port 8554'` 8 秒仅 1 个零载荷包） |
| CPU 实际用途 | 全部用于向 `/dev/log` 刷错误（`mpp_frame_deinit invalid NULL pointer input`，**2954 条/分钟**） |
| MediaMTX 侧 | `closed: no one is publishing to path 'video1'` |
| 中继侧 | 源探测（HLS）404 → 拒绝起 `rtmp-gst` → **推流中断且永不自愈** |
| 商业影响 | SRS 后台看不到 `m20pro-f` / `m20pro-b`；用户 `m20video up` 却提示"已启动" |

**根因**：GStreamer 1.16 的 `rtspclientsink` **不重试** RTSP 会话——一旦 ANNOUNCE 未成功（开机降级/竞态、`mpph264enc` 初始化异常等），管道就永久停在假死态。

---

## 2. 设计：刻意"最小侵入"

**不改 `push_video.sh` 一行代码。** 它的外层 `while true` 在 `_is_stream_alive` 返回假时会重新拉起管道——所以只要有人把假死管道**杀掉**，它自己就会重生。本守护就是那个"杀"的人。

```
[systemd timer 每 60s]
        │
        ▼
camera-liveness-guard.sh
        │
        ├─ ① mediamtx 是否在监听 8554？否 → 跳过（源全断是中继侧问题，杀相机无意义）
        ├─ ② 遍历 gst-launch-1.0 进程，从 cmdline 解析发布路径（…/8554/video1）
        ├─ ③ 进程运行 < GRACE_SEC(90s) → 跳过（新管道要时间 publish）
        ├─ ④ 探测 http://127.0.0.1:8888/<path>/index.m3u8
        │     =200 → 清零计数
        │     ≠200 → 计数 +1，连续 ≥ FAIL_THRESHOLD(3) 次
        └─ ⑤ 判定假死 → kill -TERM（5s 未退则 -9）
                        ↓
              push_video.sh 自动重建该路 ✅
```

**保守性设计（防误杀正常流）**：

| 机制 | 默认值 | 作用 |
|---|---|---|
| 连续失败阈值 | 3 次（≈3 分钟） | 排除瞬时抖动 |
| 启动宽限期 | 90 s | 给新管道完成 publish 的时间 |
| mediamtx 前置检查 | 必须监听 8554 | mediamtx 挂了时不动相机 |
| 先 TERM 后 KILL | 5 s 宽限 | 让 push_video.sh 的 trap 做清理 |
| `--dry-run` | — | 首次部署只报告不动作 |

**明确的职责边界**：本守护**不负责拉起 `push_video.sh`**（只告警"未发现 gst-launch 进程"）。"监督者自己也挂了"属于 R19 的系统单元化范畴，另项处理。

---

## 3. 部署步骤（狗回来后再执行）

```bash
# ── 0) 先看现状（只读）──
ssh m20pro-f20-0-196 'systemctl is-active m20video; pgrep -c -x gst-launch-1.0; \
  for p in video1 video2; do printf "%s=%s " $p \
  "$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8888/$p/index.m3u8)"; done; echo'

# ── 1) 传文件 ──
scp patch/camera-liveness-guard.sh m20pro-f20-0-196:/tmp/
scp patch/cam-guard.service patch/cam-guard.timer m20pro-f20-0-196:/tmp/

# ── 2) 安装（196 上，需要 sudo；sudo 口令是半角单引号）──
#    注意：命令行里不要出现 v4l2 / push_video / gst-launch 字样
#    （上游 restart.sh 会 pkill -f 误杀），一律写脚本再执行。
ssh m20pro-f20-0-196 'bash -s' <<'EOS'
D=/opt/robot/scripts/board_resources/rtsp_service
sudo install -m 755 /tmp/camera-liveness-guard.sh $D/camera-liveness-guard.sh
sudo sed -i 's/\r$//' $D/camera-liveness-guard.sh
sudo bash -n $D/camera-liveness-guard.sh && echo "语法检查通过"

# ── 3) 先干跑一次，看它想做什么（不动作）──
sudo $D/camera-liveness-guard.sh --dry-run

# ── 4) 确认逻辑无误后再启用定时器 ──
sudo install -m 644 /tmp/cam-guard.service /etc/systemd/system/cam-guard.service
sudo install -m 644 /tmp/cam-guard.timer   /etc/systemd/system/cam-guard.timer
sudo systemctl daemon-reload
sudo systemctl enable --now cam-guard.timer
systemctl list-timers cam-guard.timer --no-pager
EOS
```

---

## 4. 验证

```bash
# ① 定时器在跑、下一次触发时间正常
ssh m20pro-f20-0-196 'systemctl list-timers cam-guard.timer --no-pager'

# ② 守护日志（每次运行都会留一行）
ssh m20pro-f20-0-196 'printf "'\''\n" | sudo -S tail -20 /var/log/cam-guard.log'

# ③ 正常态应长这样：HLS=200，计数清零
#    2026-10-15 20:01:03 [cam-guard] pid=2715 path=video1 HLS=200 ...
#    2026-10-15 20:01:03 [cam-guard] pid=2722 path=video2 HLS=200 ...

# ④ 端到端健康（两路都应为 200 / OK）
ssh m20pro-f20-0-196 'for p in video1 video2; do printf "%s=%s " $p \
  "$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8888/$p/index.m3u8)"; done; \
  echo; echo "rtmp-gst=$(pgrep -c -f bin/rtmp-gst)"; \
  ss -tn | grep -c "ESTAB.*172.31.68.227:1936"'
```

**故障注入测试（建议做一次，证明守护真能救）**：
让某一路进入假死态很难人为构造，退而求其次做**误杀防护测试**：
```bash
# 停掉一路相机管道，观察守护是否"正确地不动作"（因为进程没了，不是假死）
# 预期：守护记录 WARN: 未发现任何 gst-launch-1.0 进程  或对另一路只报 HLS=200
```

---

## 5. 回滚（一步到位）

```bash
ssh m20pro-f20-0-196 'bash -s' <<'EOS'
sudo systemctl disable --now cam-guard.timer
sudo rm -f /etc/systemd/system/cam-guard.service /etc/systemd/system/cam-guard.timer
sudo rm -f /opt/robot/scripts/board_resources/rtsp_service/camera-liveness-guard.sh
sudo rm -rf /var/lib/cam-guard /var/log/cam-guard.log
sudo systemctl daemon-reload
echo "已回滚：相机推流恢复到原始行为（无存活判据）"
EOS
```

> 本补丁**不修改任何厂商文件**（`push_video.sh` / `start_server.sh` / `mediamtx.yml` 均不动），
> 只新增 3 个文件。回滚无残留风险。

---

## 6. 尚未覆盖（留待后续）

| 项 | 说明 |
|---|---|
| **监督者自身挂了** | 若 `push_video.sh` 自己退出，本守护只能告警、不会拉起 → 属 R19 的系统单元化（`Restart=always`） |
| **`m20video up` 语义** | 应改为「源健康 + 目标可推」才报成功；现在报"已启动"但可能一帧未推 |
| **开机竞态根治** | `start_server.sh` 的时间同步门禁在年份错误时会空等 60 s；`NetworkManager-wait-online` / `dr_wifi` / `isc-dhcp-server` 本次开机均失败（降级启动）——建议排期单独处理 |
| **时钟拉锯战** | `ptp_manage`(phc2sys 改系统钟) vs `chrony` 造成 ±846 天振荡，见评估报告 §7.14。⚠️ **稳定的错误时钟无害，来回跳的时钟会杀 RTSP 会话**（MediaMTX 会话超时基于墙上时钟）——这可能是假死管道的触发因素之一，值得优先处置 |

---

# B. 日志大小上限 + 轮换存储（m20-log）

> 部署日期：2026-10-16。完整方案文档见 `note/日志轮转方案-20261016.md`。

## B.1 要解决什么

原 `rtmp_forward.sh` 的 `rotate_log()` 有三个致命问题：

```bash
rotate_log() {
    [ -f "$LOG_FILE" ] || return 0
    size=$(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -ge "${LOG_MAX_BYTES:-5242880}" ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null     # ← 罪魁祸首
    fi
}
rotate_log            # ← 只在启动时调用一次，运行期永不检查
```

1. **只在启动时调用一次** → 运行期无限增长，实测堆到 **475MB**
2. **只保留 1 份**，`mv -f` 直接覆盖旧的
3. **`mv` 对有长持 fd 的写入方是错的** —— gst 启动时 `>>"$LOG_FILE"` 打开并长期持有，
   `mv` 后 fd 仍指向旧 inode → 日志继续写进 `.1`，新 `.log` 永远空、`.1` 无限增长

## B.2 交付物

| 文件 | 本地 | 主机 |
|---|---|---|
| 轮转库 | `m20-log.sh` | `/home/user/rtmp_1012/lib/m20-log.sh` |
| 巡检脚本 | `m20-log-rotate.sh` | `/usr/local/sbin/m20-log-rotate.sh` |
| 定时器 | `m20-log-rotate.{service,timer}` | `/etc/systemd/system/` |
| 回归测试 | `m20-log.test.sh` | 上传 `/tmp` 运行即可 |
| 真实链路验证 | `verify-real-rotate.sh` | 上传 `/tmp` 运行即可 |
| 打补丁工具 | `apply-logrotate-patch.py`（幂等、带备份） | — |
| 追加配置工具 | `append-config.py`（幂等） | — |

## B.3 核心结论（实测）

- **必须用 `copytruncate`**：对照实验中 `mv` 模式让当前日志直接消失、19200 字节全挤进 `.1`
- **追赶式复制 + 非阻塞锁**把并发丢失从 **73%（328/1200）降到 0（1200/1200）**
- 真实生产链路轮转：内容零丢失、**inode 未变**、gst 的 fd 路径仍有效、推流未中断
- 库回归测试 **17/17 通过**；定时器 60 秒周期稳定 `Succeeded`

## B.4 为什么还要一个独立的定时器

`gst-launch` 由内核直接 `>>` 追加日志，**不经过 shell 的 `log()`**，所以"写入方自检"盖不住它。
GStreamer 异常时可刷到 ~60 条/秒。因此需要 `m20-log-rotate.timer` 每 60 秒扫描兜底。

## B.5 回滚

见 `note/日志轮转方案-20261016.md` §7.2。备份文件：
`rtmp_forward.sh.bak-logrotate-20261016-034406`、`config.env.bak-logcfg-20261016`。
