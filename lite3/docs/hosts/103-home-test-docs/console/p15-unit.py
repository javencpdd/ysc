#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1.5 单元测试：configlib 新函数 + server 新辅助函数（Py3.8 兼容，零第三方依赖）。

本地（Windows py3.13）与 103 真机（py3.8.10）都可跑：
    python3 p15-unit.py
全部通过时退出码 0；任一失败打印 FAIL 并不做后续副作用。
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import configlib                                                   # noqa: E402
import server                                                      # noqa: E402

PASS = 0
FAIL = 0


def expect(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS  %s" % msg)
    else:
        FAIL += 1
        print("FAIL  %s" % msg)


# ---------------------------------------------------------------- backup_and_write
work = tempfile.mkdtemp(prefix="p15-unit-")
cfg_path = os.path.join(work, "yolo8.json")

# 首次写入：无备份，返回 None，文件落地且 0600
first = {"version": 2, "console": {"token": "t1"}, "detect": {"conf_threshold": 0.4}}
bak = configlib.backup_and_write(cfg_path, first, keep=10)
expect(bak is None, "backup_and_write 首次写入无备份返回 None")
expect(os.path.isfile(cfg_path), "首次写入文件存在")
# Windows 的 chmod 只影响只读位，拿不到 POSIX 权限位 ⇒ 仅 POSIX 严格断言 0600
_mode = os.stat(cfg_path).st_mode & 0o777
if os.name == "posix":
    expect(_mode == 0o600, "写入文件权限 0600（实际 %s）" % oct(_mode))
else:
    expect(_mode in (0o600, 0o666), "写入文件可读写（实际 %s）" % oct(_mode))
with open(cfg_path, "r", encoding="utf-8") as fh:
    expect(json.load(fh) == first, "首次写入内容一致")
expect(not os.path.exists(cfg_path + ".tmp"), "无残留 .tmp")

# 二次写入：生成 .bak-<ts>，内容为旧值
second = {"version": 2, "console": {"token": "t2"}, "detect": {"conf_threshold": 0.45}}
bak = configlib.backup_and_write(cfg_path, second, keep=10)
expect(bak is not None and os.path.isfile(bak), "二次写入生成备份文件 %s" % bak)
with open(bak, "r", encoding="utf-8") as fh:
    expect(json.load(fh) == first, "备份内容是旧配置")
with open(cfg_path, "r", encoding="utf-8") as fh:
    expect(json.load(fh) == second, "新配置已落地")

# 轮换：连续写 13 次，keep=10 时只留 10 份备份
for i in range(13):
    configlib.backup_and_write(cfg_path, {"version": 2, "n": i}, keep=10)
baks = [f for f in os.listdir(work) if f.startswith("yolo8.json.bak-")]
expect(len(baks) == 10, "轮换后备份份数=10（实际 %d）" % len(baks))

# 轮换保留的是最新几份（第 12 次写入的备份应还在，最早的不在）
expect(os.path.basename(bak) in baks, "最近一次备份被保留")

# 同一秒内连续写入：备份不得互相覆盖（秒级时间戳会撞名，靠 -1/-2 后缀区分）
burst = os.path.join(work, "burst.json")
configlib.backup_and_write(burst, {"v": 1}, keep=10)
b1 = configlib.backup_and_write(burst, {"v": 2}, keep=10)
b2 = configlib.backup_and_write(burst, {"v": 3}, keep=10)
expect(b1 != b2 and os.path.isfile(b1) and os.path.isfile(b2),
       "同秒两次写入备份互不覆盖（%s / %s）" % (os.path.basename(b1), os.path.basename(b2)))
with open(b1, "r", encoding="utf-8") as fh:
    expect(json.load(fh) == {"v": 1}, "同秒第一次备份内容是写入前的旧值")
with open(b2, "r", encoding="utf-8") as fh:
    expect(json.load(fh) == {"v": 2}, "同秒第二次备份内容是写入前的旧值")

# ---------------------------------------------------------------- needs_restart
base = configlib.copy.deepcopy(configlib.DEFAULTS)
expect(configlib.needs_restart(base, configlib.copy.deepcopy(base)) == [],
       "needs_restart 无变化 → []")
expect(configlib.needs_restart(base, dict(base, updated_at="x")) == [],
       "needs_restart 仅簿记字段变化 → []")
mod = configlib.deep_merge(base, {"detect": {"conf_threshold": 0.5}})
expect(configlib.needs_restart(base, mod) == ["yolo"], "detect 变化 → [yolo]")
mod2 = configlib.deep_merge(base, {"source": {"rtsp_url": "rtsp://1.2.3.4:8554/x"}})
expect(configlib.needs_restart(base, mod2) == ["yolo"], "source 变化 → [yolo]")
mod3 = configlib.deep_merge(base, {"console": {"token": "zz"}})
expect(configlib.needs_restart(base, mod3) == ["console"], "console 变化 → [console]")
mod4 = configlib.deep_merge(base, {"stream": {"rtmp_url": "rtmp://h:1936/a/b"},
                                   "console": {"port": 8091}})
expect(configlib.needs_restart(base, mod4) == ["console", "yolo"],
       "console+stream 同时变化 → [console, yolo]")

# ---------------------------------------------------------------- validate 拒绝路径（写接口的地基）
bad = configlib.deep_merge(base, {"stream": {"rtmp_url": "rtmp://x:1935/live/lite3"}})
try:
    configlib.validate_config(bad)
    expect(False, "live/lite3 互踢应被拒绝")
except configlib.ConfigError:
    expect(True, "live/lite3 互踢被拒绝")

# ---------------------------------------------------------------- read_env_port
env_path = os.path.join(work, "yolo-publish.env")
with open(env_path, "w", encoding="utf-8") as fh:
    fh.write("# 注释行\nROSBRIDGE_PORT=9099\nOTHER=1\nBROKEN=abc\n")
server.ENV_FILE = env_path                      # 指向临时 env（真机上是 deploy/yolo-publish.env）
expect(server.read_env_port("ROSBRIDGE_PORT", 9090) == 9099, "read_env_port 读到 9099")
expect(server.read_env_port("MISSING", 9090) == 9090, "read_env_port 缺键回退默认")
expect(server.read_env_port("BROKEN", 9090) == 9090, "read_env_port 非整数回退默认")
server.ENV_FILE = os.path.join(work, "no-such.env")
expect(server.read_env_port("ROSBRIDGE_PORT", 9090) == 9090, "read_env_port 文件缺失回退默认")

# ---------------------------------------------------------------- lan_ip / probe_tcp
ip = server.lan_ip()
expect(ip is None or (ip.count(".") == 3), "lan_ip 返回 None 或 IPv4 字符串（实际 %r）" % ip)

closed = server.probe_tcp("127.0.0.1", 1, timeout=1.0)     # 1 号端口必然拒连
expect(closed.get("reachable") is False, "probe_tcp 对关闭端口 reachable=false")
expect("error" in closed, "probe_tcp 失败带 error")
listening = None
import socket as _socket                                        # noqa: E402
srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
srv.bind(("127.0.0.1", 0))
srv.listen(1)
port = srv.getsockname()[1]
opened = server.probe_tcp("127.0.0.1", port, timeout=2.0)
expect(opened.get("reachable") is True, "probe_tcp 对监听端口 reachable=true")
expect(isinstance(opened.get("elapsed_ms"), int), "probe_tcp 成功带 elapsed_ms")
srv.close()

# ---------------------------------------------------------------- probe_rtsp 降级路径
# 本机可能没有 ffprobe / 没有可直达的 RTSP 流：两条降级路径都必须返回结构化错误而非抛异常
rt = server.probe_rtsp("rtsp://127.0.0.1:1/none", "udp", timeout=3.0)
expect(isinstance(rt, dict) and "reachable" in rt, "probe_rtsp 返回结构化结果")
expect(rt.get("reachable") is False, "probe_rtsp 对不可达流 reachable=false")

# ---------------------------------------------------------------- server 模块冒烟
expect(hasattr(server.ConsoleContext, "reload_config"), "ConsoleContext.reload_config 存在")
expect(hasattr(server.ConsoleContext, "list_topics"), "ConsoleContext.list_topics 存在")
expect(server.WRITABLE_SECTIONS == ("source", "detect", "snapshot", "stream", "model", "pic_dir"),
       "WRITABLE_SECTIONS 白名单六节")
expect(server.VERSION == "2.1.0-p1", "VERSION 未变（ui-test U9 依赖）")

shutil.rmtree(work, ignore_errors=True)
print("")
print("===== 单元测试汇总: PASS=%d FAIL=%d =====" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
