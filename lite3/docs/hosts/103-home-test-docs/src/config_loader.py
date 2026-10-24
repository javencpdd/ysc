# -*- coding: utf-8 -*-
"""运行期配置加载与热更新（`config/yolo8.json`）。

设计依据：计划书 §5.11 三层优先级 + §5.7 状态上行 + §5.3 阈值热更新。

三条硬规则：
  1. **优先级**：`config/yolo8.json` > `deploy/yolo-publish.env`（仅 fallback）> 代码默认值；
  2. **热更新**：轮询 mtime（主循环每帧调 `poll()`，≤1s 生效）；
  3. **绝不带病运行**：解析/校验失败 → **保持上一次有效配置**并记 `last_err`，
     不回退到默认值、不崩溃（改一半的文件不会让 worker 变成错误行为）。

Py3.8 兼容、纯标准库（真机 Python 3.8.10，无 pip 源，禁 3.9+ 语法）。
"""

import copy
import json
import os
import time

# config/yolo8.json 相对本文件（src/config_loader.py）的位置
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.normpath(
    os.path.join(_HERE, '..', 'config', 'yolo8.json'))

DEFAULTS = {
    "version": 2,
    "source": {
        "type": "rtsp",
        "rtsp_url": "rtsp://192.168.1.120:8554/test",
        "file_path": "",
        "codec": "h264",
        "decoder": "hw",
        "transport": "udp",
        "latency_ms": 200,
        "out_width": 640,
        "out_height": 360,
        "read_timeout_ms": 5000,
        "reconnect": {"enabled": True, "backoff_ms": 1000,
                      "backoff_max_ms": 30000},
    },
    "detect": {"conf_threshold": 0.4, "classes": [0]},
    "snapshot": {
        "enabled": True, "cooldown_ms": 2000, "cooldown_ms_per_class": 1000,
        "daily_quota": 500, "retention_days": 7, "min_free_gb": 5,
        "save_meta": True, "save_annotated": True,
    },
    "stream": {
        "rtmp": True,
        "rtmp_url": "rtmp://172.31.68.227:1936/live/lite3_yolo",
        "rtmp_bitrate": 1000000,
        "rtmp_sink": "rtmpsink",
        "out_width": 640,
        "out_height": 360,
        "fps": 30,
        "ros2_image": False,
        "ros2_every": 3,
        "reconnect": {"backoff_ms": 1000, "backoff_max_ms": 30000},
    },
    "model": {"engine": "yolov8n_arm.engine", "imgsz": 640},
    "pic_dir": "../pic",
}

# env → config 的 fallback 表：(配置路径, env 名, 转换器)
# 仅用于「config 文件缺失/缺该键」时兜底（§5.11 第二层）。
ENV_FALLBACK = (
    # 注：RTSP 源地址历史上是**硬编码**在 GStreamerWrapper 里的，env 中没有对应键，
    # 因此这里没有 source.rtsp_url 的回退项（避免凭空造一个不存在的 env 名）。
    ("detect.conf_threshold", "YOLO8_CONF", float),
    ("stream.rtmp", "YOLO8_ENABLE_RTMP", lambda v: v != "0"),
    ("stream.rtmp_url", "YOLO8_RTMP_URL", str),
    ("stream.rtmp_bitrate", "YOLO8_RTMP_BITRATE", int),
    ("stream.rtmp_sink", "YOLO8_RTMP_SINK", str),
    ("stream.ros2_image", "YOLO8_ENABLE_ROS2_IMAGE", lambda v: v != "0"),
    ("stream.ros2_every", "YOLO8_ROS2_EVERY", int),
)


def _deep_merge(base, over):
    """把 over 深合并进 base 的副本（dict 递归，其余整体覆盖）。"""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _get_path(cfg, dotted):
    cur = cfg
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_path(cfg, dotted, value):
    parts = dotted.split('.')
    cur = cfg
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def validate(cfg):
    """轻量校验：只挡"会让下游崩"的错。返回错误列表（空=通过）。

    注意（§5.3）：阈值越界**不静默夹取**——那是管理面的职责（服务端应 400 拒绝）。
    worker 侧发现越界只记录告警，由调用方决定是否采用。
    """
    errs = []
    if not isinstance(cfg, dict):
        return ["配置不是 dict"]
    src = cfg.get("source") or {}
    if src.get("type") not in ("rtsp", "file"):
        errs.append("source.type 必须是 rtsp/file，实际 %r" % (src.get("type"),))
    if src.get("type") == "rtsp" and not src.get("rtsp_url"):
        errs.append("source.type=rtsp 但 rtsp_url 为空")
    if src.get("type") == "file" and not src.get("file_path"):
        errs.append("source.type=file 但 file_path 为空")
    if src.get("decoder") not in ("hw", "auto"):
        errs.append("source.decoder 只支持 hw/auto（无软解），实际 %r"
                    % (src.get("decoder"),))
    if src.get("codec") not in ("h264", "h265", "auto"):
        errs.append("source.codec 只支持 h264/h265/auto，实际 %r"
                    % (src.get("codec"),))
    for key in ("out_width", "out_height"):
        v = src.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0 or v > 4096:
            errs.append("source.%s 非法：%r" % (key, v))
    st = cfg.get("stream") or {}
    if not isinstance(st.get("fps"), int) or isinstance(st.get("fps"), bool) \
            or not (1 <= st["fps"] <= 60):
        errs.append("stream.fps 非法：%r" % (st.get("fps"),))
    det = cfg.get("detect") or {}
    conf = det.get("conf_threshold")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) \
            or not (0.0 < float(conf) <= 1.0):
        errs.append("detect.conf_threshold 非法：%r" % (conf,))
    if not isinstance(det.get("classes"), list):
        errs.append("detect.classes 必须是列表：%r" % (det.get("classes"),))
    return errs


def _from_env(cfg):
    """第二层：config 里没有的键，用 env 兜底（只在缺键时生效）。"""
    for dotted, env_name, cast in ENV_FALLBACK:
        if _get_path(cfg, dotted) is not None:
            continue
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            _set_path(cfg, dotted, cast(raw))
        except (TypeError, ValueError):
            pass  # env 值不可解析 → 继续用默认值，不阻断启动
    return cfg


def atomic_write_json(path, obj, fsync=False):
    """原子写 JSON（tmp + `os.replace`，同目录避免跨设备 rename 失败）。

    `fsync` **默认关闭**：worker_state 这类遥测文件每秒写 4 次，在 Jetson eMMC 上
    单次 fsync 可达几十 ms——实测把主循环从 ~22fps 拖到 13fps（2026-10-22 P2 实测）。
    掉电保护对"下一帧就会覆盖"的状态文件没有意义；只有配置文件落盘才需要 fsync。
    """
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        if fsync:
            os.fsync(f.fileno())
    os.replace(tmp, path)


class ConfigLoader(object):
    """mtime 轮询的配置加载器。用法：

        loader = ConfigLoader()
        cfg = loader.cfg                 # 首次即加载
        while True:
            if loader.poll():            # 变了才 True
                apply(loader.cfg)
    """

    def __init__(self, path=None, poll_interval_s=0.4):
        self.path = path or DEFAULT_CONFIG_PATH
        self.poll_interval_s = float(poll_interval_s)
        self.cfg = None
        self.mtime = None
        self.last_err = None        # 最近一次解析/校验错误（None = 无）
        self.load_count = 0
        self.last_check = 0.0
        self._ensure_file()
        cfg, err = self._build()
        if cfg is None:
            # 首次加载就失败：没有"上一次有效配置"可保 → 退回默认值 + env，并告警。
            # 绝不返回 None，否则下游 KeyError 崩在半路更难查。
            self.last_err = err
            print("[config] 首次加载失败，退回默认值: %s" % err)
            cfg = _from_env(copy.deepcopy(DEFAULTS))
        self.cfg = cfg
        try:
            self.mtime = os.stat(self.path).st_mtime
        except OSError:
            self.mtime = None
        self.last_check = time.time()

    # ---------- 内部 ----------
    def _ensure_file(self):
        """文件缺失 → 用默认值 + env 兜底生成一份（0600）。"""
        if os.path.exists(self.path):
            return
        cfg = _from_env(copy.deepcopy(DEFAULTS))
        try:
            d = os.path.dirname(self.path)
            if d and not os.path.isdir(d):
                os.makedirs(d)
            atomic_write_json(self.path, cfg, fsync=True)
            os.chmod(self.path, 0o600)
            print("[config] 配置文件缺失，已生成默认: %s" % self.path)
        except (IOError, OSError) as e:
            print("[config] 生成默认配置失败: %s（继续用内存默认值）" % e)

    def _build(self):
        """读文件 → 合并默认值 → env 兜底 → 校验。失败返回 (None, err)。"""
        try:
            with open(self.path, "r") as f:
                raw = json.load(f)
        except (IOError, OSError) as e:
            return None, "读取失败: %s" % e
        except ValueError as e:
            return None, "JSON 解析失败: %s" % e
        if not isinstance(raw, dict):
            return None, "配置根节点不是对象"
        cfg = _deep_merge(DEFAULTS, raw)
        cfg = _from_env(cfg)
        errs = validate(cfg)
        if errs:
            return None, "; ".join(errs)
        self.load_count += 1
        return cfg, None

    # ---------- 对外 ----------
    def reload(self):
        """强制重读。成功更新 self.cfg 并返回 True；失败保旧值并返回 False。"""
        cfg, err = self._build()
        if cfg is None:
            self.last_err = err
            print("[config] 配置无效，保持上一次有效配置: %s" % err)
            return False
        try:
            self.mtime = os.stat(self.path).st_mtime
        except OSError:
            self.mtime = None
        self.cfg = cfg
        self.last_err = None
        return True

    def poll(self):
        """按间隔检查 mtime；文件变化则重读。返回 True 表示配置已更新。"""
        now = time.time()
        if now - self.last_check < self.poll_interval_s:
            return False
        self.last_check = now
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            return False                      # 文件短暂不可读，下次再试
        if self.mtime is not None and mtime == self.mtime:
            return False
        return self.reload()
