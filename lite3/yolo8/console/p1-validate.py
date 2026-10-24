#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1-3 响应体结构校验（Py3.8 兼容，103 真机运行）。"""
import json
import sys

OUT = "/tmp/p1_out"
fails = []


def load(name):
    with open("%s/%s" % (OUT, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def expect(cond, msg):
    if cond:
        print("PASS  %s" % msg)
    else:
        print("FAIL  %s" % msg)
        fails.append(msg)


# ---- /api/state ----
st = load("state.json")
expect(st.get("ok") is True, "state.ok=true")
s = st.get("state", {})
for key in ("console", "host", "services", "worker", "config_from_file"):
    expect(key in s, "state 含 %s" % key)
expect(s.get("config_from_file") is True, "config_from_file=true（读的是 config/yolo8.json）")
c = s.get("console", {})
for key in ("version", "pid", "rss_mb", "uptime_s", "bind", "port", "sessions", "allowed_cidrs"):
    expect(key in c, "console 含 %s" % key)
expect(c.get("bind") == "0.0.0.0" and c.get("port") == 8090, "console bind/port 符合 D1 裁决")
expect(c.get("allowed_cidrs") == ["192.168.1.0/24"], "白名单为 192.168.1.0/24")
h = s.get("host", {})
for key in ("load1", "load5", "load15", "mem_avail_mb", "disk_avail_gb"):
    expect(key in h and h[key] is not None, "host.%s 有值" % key)
sv = s.get("services", {})
expect(set(sv.keys()) == {"yolo", "rosbridge"}, "services 含 yolo+rosbridge 两个目标")
y = sv.get("yolo", {})
expect(y.get("mode") == "installed_disabled", "yolo mode=installed_disabled（unit 已安装未启用）")
expect(y.get("unit") == "lite3-yolo-publish.service", "yolo unit 名正确")
expect(y.get("enabled") == "disabled", "yolo enabled=disabled")
expect(isinstance(y.get("log_tail"), list) and y["log_tail"], "yolo log_tail 非空（ctl 输出被解析）")
expect(s.get("worker") is None, "worker=None（P1 未接入，符合预期）")

# ---- /api/config ----
cf = load("config.json")
expect(cf.get("ok") is True, "config.ok=true")
expect(cf.get("from_file") is True, "config.from_file=true")
cfg = cf.get("config", {})
expect(cfg.get("version") == 2, "config.version=2")
for key in ("console", "source", "detect", "snapshot", "stream", "model", "pic_dir"):
    expect(key in cfg, "config 含 %s" % key)
expect(cfg.get("console", {}).get("token") == "***", "console.token 回显被脱敏为 ***")

# ---- /api/service/status ----
ss = load("status.json")
expect(ss.get("ok") is True, "status.ok=true")
svc = ss.get("services", {})
expect(set(svc.keys()) == {"yolo", "rosbridge"}, "status 覆盖两个目标")
expect(all("mode" in v and "running" in v for v in svc.values()), "每个目标都有 mode/running")

# ---- /api/logs ----
lg = load("logs.json")
expect(lg.get("ok") is True, "logs.ok=true")
expect(lg.get("target") == "yolo", "logs.target=yolo")
expect(isinstance(lg.get("lines"), list) and len(lg["lines"]) <= 5, "logs.lines 行数受 lines=5 约束")
expect(len(lg.get("lines") or []) > 0, "logs.lines 非空（yolo-publish.log 有历史）")

# ---- yolo 启停后的状态 ----
try:
    ys = load("yolo_status_after.json")
    ysvc = ys.get("services", ys)
    yy = ysvc.get("yolo", ysvc)
    expect(yy.get("running") is False, "yolo 停止后 running=false")
    expect(yy.get("mode") == "installed_disabled", "yolo 停止后 mode 仍为 installed_disabled")
except Exception as exc:                                   # noqa: BLE001
    expect(False, "yolo_status_after.json 可解析（%s）" % exc)

print("")
if fails:
    print("结构校验失败 %d 项" % len(fails))
    sys.exit(1)
print("结构校验全部通过")
