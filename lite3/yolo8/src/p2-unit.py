# -*- coding: utf-8 -*-
"""P2 worker 侧单元测试（本机 py3.13 + 真机 py3.8.10 双跑）。

覆盖：
  A. Py3.8 语法兼容（真机 3.8.10，禁 3.9+ 语法；本机跑不出来，必须 ast 校验）
  B. config_loader：默认值合并 / env 兜底 / mtime 热更新 / 坏配置保持上次有效 / 原子写
  C. pipelines：build_source_pipeline 三种形态 / mask_url 脱敏
  D. validate()：非法阈值、非法 decoder/codec、非法尺寸 全部被挡

运行：cd /home/test/yolo8/src && python3 p2-unit.py
"""

import ast
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = 0
FAIL = 0


def check(name, expect, actual):
    global PASS, FAIL
    if expect == actual:
        print("PASS  %s = %r" % (name, actual))
        PASS += 1
    else:
        print("FAIL  %s  期望 %r 实际 %r" % (name, expect, actual))
        FAIL += 1


def check_true(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print("PASS  %s" % name)
        PASS += 1
    else:
        print("FAIL  %s  %s" % (name, detail))
        FAIL += 1


# ---------------- A. Py3.8 语法兼容 ----------------
print("========== A. Py3.8 语法兼容 ==========")
TARGETS = [
    "config_loader.py",
    "pipelines.py",
    "run_tracker_publish.py",
    os.path.join("GStreamerWrapper", "GStreamerWrapper.py"),
    os.path.join("RtmpPublisher", "RtmpPublisher.py"),
    os.path.join("RobotController", "YoloWrapper", "YoloWrapper.py"),
]
for rel in TARGETS:
    p = os.path.join(HERE, rel)
    if not os.path.exists(p):
        check_true("A %s 存在" % rel, False, "文件缺失")
        continue
    try:
        with open(p, "r") as f:
            ast.parse(f.read(), filename=rel, feature_version=(3, 8))
        check_true("A py38 语法 %s" % rel, True)
    except SyntaxError as e:
        check_true("A py38 语法 %s" % rel, False, str(e))

# ---------------- C/D. pipelines + validate（纯逻辑，无需 GStreamer） ----------------
print("========== C. pipelines ==========")
from pipelines import build_source_pipeline, mask_url  # noqa: E402

p_rtsp = build_source_pipeline({
    "type": "rtsp", "rtsp_url": "rtsp://1.2.3.4:8554/test", "codec": "h264",
    "decoder": "hw", "transport": "tcp", "latency_ms": 200,
    "out_width": 640, "out_height": 360})
check_true("C1 rtsp 链含 rtspsrc", "rtspsrc location=" in p_rtsp, p_rtsp)
check_true("C2 rtsp 链含 protocols=tcp", "protocols=tcp" in p_rtsp, p_rtsp)
check_true("C3 rtsp 链含 latency=200", "latency=200" in p_rtsp, p_rtsp)
check_true("C4 rtsp 链含 nvv4l2decoder", "nvv4l2decoder" in p_rtsp, p_rtsp)
check_true("C5 rtsp 链含 NVMM cap", "memory:NVMM" in p_rtsp, p_rtsp)
check_true("C6 rtsp 链 appsink 收尾",
           "appsink name=sink sync=false" in p_rtsp, p_rtsp)

p_file = build_source_pipeline({
    "type": "file", "file_path": "/tmp/a.mp4", "out_width": 320,
    "out_height": 240})
check_true("C7 file 链含 filesrc", 'filesrc location="/tmp/a.mp4"' in p_file,
            p_file)
check_true("C8 file 链走 decodebin", " ! decodebin " in p_file, p_file)
check_true("C9 file 链尺寸参数化", "width=320,height=240" in p_file, p_file)

p_auto = build_source_pipeline({
    "type": "rtsp", "rtsp_url": "rtsp://h/x", "decoder": "auto"})
check_true("C10 decoder=auto 走 decodebin", " ! decodebin " in p_auto, p_auto)

check("C11 mask_url 脱敏",
      "rtsp://user:***@192.168.1.120:8554/test",
      mask_url("rtsp://user:secret@192.168.1.120:8554/test"))
check("C12 mask_url 无凭据原样返回", "rtsp://192.168.1.120:8554/test",
      mask_url("rtsp://192.168.1.120:8554/test"))
check("C13 mask_url 空值", "", mask_url(""))

print("========== D. validate 拒绝非法值 ==========")
from config_loader import validate, DEFAULTS, _deep_merge, atomic_write_json, ConfigLoader  # noqa: E402

base = _deep_merge(DEFAULTS, {})
check("D1 默认配置通过", [], validate(base))

bad_conf = _deep_merge(DEFAULTS, {"detect": {"conf_threshold": 1.5}})
check_true("D2 阈值 >1 被拒",
           any("conf_threshold" in e for e in validate(bad_conf)),
           str(validate(bad_conf)))

bad_dec = _deep_merge(DEFAULTS, {"source": {"decoder": "sw"}})
check_true("D3 decoder=sw 被拒（无软解）",
           any("decoder" in e for e in validate(bad_dec)), str(validate(bad_dec)))

bad_w = _deep_merge(DEFAULTS, {"source": {"out_width": 0}})
check_true("D4 out_width=0 被拒", len(validate(bad_w)) > 0, str(validate(bad_w)))

bad_type = _deep_merge(DEFAULTS, {"source": {"type": "http"}})
check_true("D5 source.type 非法被拒", len(validate(bad_type)) > 0)

bad_fps = _deep_merge(DEFAULTS, {"stream": {"fps": 120}})
check_true("D6 fps=120 被拒", any("fps" in e for e in validate(bad_fps)))

# ---------------- B. ConfigLoader ----------------
print("========== B. ConfigLoader ==========")
tmp = tempfile.mkdtemp(prefix="p2cfg-")
cfg_path = os.path.join(tmp, "yolo8.json")
try:
    # B1 文件缺失 → 自动生成
    loader = ConfigLoader(path=cfg_path)
    check_true("B1 缺失时自动生成", os.path.exists(cfg_path), cfg_path)
    check("B2 默认阈值", 0.4, loader.cfg["detect"]["conf_threshold"])

    # B3 env 兜底（缺键时）
    os.environ["YOLO8_CONF"] = "0.77"
    cfg2_path = os.path.join(tmp, "yolo8_env.json")
    with open(cfg2_path, "w") as f:
        json.dump({"version": 2, "detect": {}}, f)   # detect 有键但阈值缺
        # 注意：_deep_merge 会用默认值填 conf_threshold=0.4，env 仅补"完全缺失"的键
    loader_env = ConfigLoader(path=cfg2_path)
    check("B3 env 不覆盖默认值（config 优先）", 0.4,
          loader_env.cfg["detect"]["conf_threshold"])
    os.environ.pop("YOLO8_CONF", None)

    # B4 热更新：改文件 + 改 mtime → poll() 返回 True
    with open(cfg_path, "w") as f:
        json.dump(_deep_merge(DEFAULTS, {"detect": {"conf_threshold": 0.6}}), f)
    os.utime(cfg_path, (time.time() + 1, time.time() + 1))
    loader.poll_interval_s = 0.0        # 去掉间隔限制，测试立即生效
    loader.last_check = 0.0
    changed = loader.poll()
    check("B4 poll 检测到变化", True, changed)
    check("B5 新阈值生效", 0.6, loader.cfg["detect"]["conf_threshold"])

    # B6 无变化不重载
    loader.last_check = 0.0
    check("B6 未变时不重载", False, loader.poll())

    # B7 坏配置 → 保持上次有效值 + 记 last_err
    with open(cfg_path, "w") as f:
        f.write("{ this is not json")
    os.utime(cfg_path, (time.time() + 2, time.time() + 2))
    loader.last_check = 0.0
    loader.poll()
    check("B7 坏 JSON 保持上次有效值", 0.6, loader.cfg["detect"]["conf_threshold"])
    check_true("B8 坏 JSON 记 last_err", loader.last_err is not None,
               str(loader.last_err))

    # B9 语义非法（阈值越界）同样保旧值
    with open(cfg_path, "w") as f:
        json.dump(_deep_merge(DEFAULTS, {"detect": {"conf_threshold": 9}}), f)
    os.utime(cfg_path, (time.time() + 3, time.time() + 3))
    loader.last_check = 0.0
    loader.poll()
    check("B9 非法阈值保旧值", 0.6, loader.cfg["detect"]["conf_threshold"])
    check_true("B10 非法阈值记 last_err", loader.last_err is not None)

    # B11 原子写不残留 tmp
    atomic_write_json(cfg_path, {"a": 1})
    check_true("B11 原子写无 .tmp 残留",
               not os.path.exists(cfg_path + ".tmp"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("")
print("===== P2 单元测试汇总: PASS=%d FAIL=%d =====" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
