#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console 配置读取与校验（计划书 v2.1 P1）。

与 deploy/migrate-env-to-config.py 共用同一套 schema 与校验规则，避免两处漂移。

约束（103 真机）：Python 3.8.10 / 无 venv / 无 pip 源 ⇒ 只用标准库，禁 3.9+ 语法。
"""

import copy
import datetime
import glob
import json
import os
import re
import shutil

CONFIG_VERSION = 2

# 开发期默认访问令牌：配置文件未显式设置时生效；生产环境应在 config/yolo8.json 里覆盖为强令牌
DEFAULT_TOKEN = "jack1419"

# 与 migrate-env-to-config.py 保持一致：未知字段忽略、缺失填默认、整体失败保持上一份
DEFAULTS = {
    "version": CONFIG_VERSION,
    "console": {
        "bind": "0.0.0.0",
        "port": 8090,
        "allowed_cidrs": ["192.168.1.0/24"],
        "session_ttl_s": 43200,
        # 访问令牌：配置文件可覆盖；默认值为开发期固定值（见 DEFAULT_TOKEN）。
        # 同一值既用于登录体，也用于写接口的 X-Yolo-Token 头，故限可打印 ASCII。
        "token": DEFAULT_TOKEN,
    },
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
        "reconnect": {"enabled": True, "backoff_ms": 1000, "backoff_max_ms": 30000},
    },
    "detect": {"conf_threshold": 0.4, "classes": [0]},
    "snapshot": {
        "enabled": True,
        "cooldown_ms": 2000,
        "cooldown_ms_per_class": 1000,
        "daily_quota": 500,
        "retention_days": 7,
        "min_free_gb": 5,
        "save_meta": True,
        "save_annotated": True,
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
    "model": {"engine": "../model/yolov8n_arm.engine", "pending_reload": False},
    "pic_dir": "../pic",
    "trash_retention_days": 7,
}

REQUIRED_TOP_KEYS = ("version", "console", "source", "detect", "snapshot",
                     "stream", "model", "pic_dir")

# 顶层敏感字段：任何接口都不得回显（P1 尚无此类字段，预留）
SENSITIVE_KEYS = ("token", "password", "secret")


class ConfigError(Exception):
    """配置缺失/损坏/校验失败。调用方应保持上一份有效配置，不得带病运行。"""


def deep_merge(base, override):
    """以 override 覆盖 base；dict 递归合并，其余类型直接替换。"""
    out = copy.deepcopy(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _is_int(val):
    return isinstance(val, int) and not isinstance(val, bool)


def _is_num(val):
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def validate_config(cfg):
    """校验并就地修正可修正项；不可修正则抛 ConfigError。"""
    if not isinstance(cfg, dict):
        raise ConfigError("配置根节点必须是对象")

    missing = [k for k in REQUIRED_TOP_KEYS if k not in cfg]
    if missing:
        raise ConfigError("缺少必需字段: %s" % ", ".join(missing))

    if not _is_int(cfg["version"]) or cfg["version"] != CONFIG_VERSION:
        raise ConfigError("version 必须是 %d（当前 %r）" % (CONFIG_VERSION, cfg.get("version")))

    console = cfg["console"]
    if not isinstance(console.get("bind"), str) or not console["bind"]:
        raise ConfigError("console.bind 必须是非空字符串")
    if not _is_int(console.get("port")) or not (1 <= console["port"] <= 65535):
        raise ConfigError("console.port 必须是 1~65535")
    cidrs = console.get("allowed_cidrs")
    if not isinstance(cidrs, list) or not cidrs:
        raise ConfigError("console.allowed_cidrs 必须是非空数组")
    import ipaddress
    for cidr in cidrs:
        try:
            ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            raise ConfigError("console.allowed_cidrs 含非法网段 %r: %s" % (cidr, exc))
    if not _is_int(console.get("session_ttl_s")) or console["session_ttl_s"] < 60:
        raise ConfigError("console.session_ttl_s 必须是 >=60 的整数")
    # 令牌不再限 32 hex（开发期默认 jack1419）；但必须可打印 ASCII 且无空白——
    # 它同时出现在登录 JSON 体与 X-Yolo-Token 请求头里。\Z 不用 $：$ 会放过尾部换行。
    token = console.get("token")
    if not isinstance(token, str) or not re.match(r"^[\x21-\x7e]{1,128}\Z", token):
        raise ConfigError("console.token 必须是 1~128 位可打印 ASCII（不含空格与换行）")

    src = cfg["source"]
    if src.get("type") not in ("rtsp", "file"):
        raise ConfigError("source.type 只能是 rtsp 或 file")
    if src["type"] == "rtsp":
        url = src.get("rtsp_url", "")
        if not isinstance(url, str) or not re.match(r"^rtsps?://[^/\s]+/\S*$", url):
            raise ConfigError("source.rtsp_url 形如 rtsp://host:port/path")
        if src.get("transport") not in ("udp", "tcp"):
            raise ConfigError("source.transport 只能是 udp 或 tcp")
        if not _is_int(src.get("latency_ms")) or not (0 <= src["latency_ms"] <= 10000):
            raise ConfigError("source.latency_ms 必须是 0~10000")
    else:
        if not isinstance(src.get("file_path"), str) or not src["file_path"]:
            raise ConfigError("source.type=file 时 file_path 不能为空")
    if src.get("codec") not in ("h264", "h265", "auto"):
        raise ConfigError("source.codec 只能是 h264/h265/auto")
    # 103 无 gst-libav：avdec_h264 / openh264dec 均不存在，软解不可用
    if src.get("decoder") not in ("hw", "auto"):
        raise ConfigError("source.decoder 只能是 hw 或 auto（103 无软解，avdec_h264 不存在）")
    for dim in ("out_width", "out_height"):
        if not _is_int(src.get(dim)) or not (16 <= src[dim] <= 4096):
            raise ConfigError("source.%s 必须是 16~4096" % dim)
    if not _is_int(src.get("read_timeout_ms")) or not (500 <= src["read_timeout_ms"] <= 60000):
        raise ConfigError("source.read_timeout_ms 必须是 500~60000")

    det = cfg["detect"]
    if not _is_num(det.get("conf_threshold")) or not (0.05 <= det["conf_threshold"] <= 0.95):
        raise ConfigError("detect.conf_threshold 必须是 0.05~0.95")
    classes = det.get("classes")
    if not isinstance(classes, list) or not classes or not all(_is_int(c) for c in classes):
        raise ConfigError("detect.classes 必须是非空整数数组")

    snap = cfg["snapshot"]
    for key in ("enabled", "save_meta", "save_annotated"):
        if not isinstance(snap.get(key), bool):
            raise ConfigError("snapshot.%s 必须是布尔值" % key)
    for key in ("cooldown_ms", "cooldown_ms_per_class", "daily_quota", "retention_days"):
        if not _is_int(snap.get(key)) or snap[key] < 0:
            raise ConfigError("snapshot.%s 必须是非负整数" % key)
    if not _is_num(snap.get("min_free_gb")) or snap["min_free_gb"] < 0:
        raise ConfigError("snapshot.min_free_gb 必须是非负数字")

    st = cfg["stream"]
    if not isinstance(st.get("rtmp"), bool):
        raise ConfigError("stream.rtmp 必须是布尔值")
    url = st.get("rtmp_url", "")
    if not isinstance(url, str) or not re.match(r"^rtmps?://[^/\s]+/[^\s]+$", url):
        raise ConfigError("stream.rtmp_url 形如 rtmp://host:port/app/stream")
    # 互踢保护：live/lite3 是 120 摄像头转发占用的流名
    if url.rstrip("/").endswith("/live/lite3"):
        raise ConfigError("stream.rtmp_url 不能是 live/lite3（120 摄像头转发占用，同流名会互踢）")
    if not _is_int(st.get("rtmp_bitrate")) or not (100000 <= st["rtmp_bitrate"] <= 8000000):
        raise ConfigError("stream.rtmp_bitrate 必须是 100000~8000000")
    if st.get("rtmp_sink") not in ("rtmpsink", "fakesink"):
        raise ConfigError("stream.rtmp_sink 只能是 rtmpsink 或 fakesink")
    for dim in ("out_width", "out_height"):
        if not _is_int(st.get(dim)) or not (16 <= st[dim] <= 4096):
            raise ConfigError("stream.%s 必须是 16~4096" % dim)
    if not _is_int(st.get("fps")) or not (1 <= st["fps"] <= 60):
        raise ConfigError("stream.fps 必须是 1~60")
    if not isinstance(st.get("ros2_image"), bool):
        raise ConfigError("stream.ros2_image 必须是布尔值")
    if not _is_int(st.get("ros2_every")) or st["ros2_every"] < 0:
        raise ConfigError("stream.ros2_every 必须是非负整数（0=关闭）")

    if not isinstance(cfg.get("model"), dict) or not isinstance(cfg["model"].get("engine"), str):
        raise ConfigError("model.engine 必须是字符串")
    if not isinstance(cfg.get("pic_dir"), str) or not cfg["pic_dir"]:
        raise ConfigError("pic_dir 必须是非空字符串")
    return True


def load_config(path, use_defaults=True):
    """读取并校验配置。

    文件不存在且 use_defaults → 返回默认配置（调用方负责提示）。
    文件存在但损坏/校验失败 → 抛 ConfigError（调用方应保持上一份有效配置）。
    """
    if not os.path.exists(path):
        if not use_defaults:
            raise ConfigError("配置文件不存在: %s" % path)
        cfg = copy.deepcopy(DEFAULTS)
        validate_config(cfg)
        return cfg, False  # (cfg, from_file)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ConfigError("读取配置失败 %s: %s" % (path, exc))

    cfg = deep_merge(DEFAULTS, raw if isinstance(raw, dict) else {})
    validate_config(cfg)
    return cfg, True


def strip_sensitive(cfg):
    """移除敏感字段后的副本（用于回显）。"""
    def _walk(node):
        if isinstance(node, dict):
            return {k: ("***" if k in SENSITIVE_KEYS else _walk(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node
    return _walk(copy.deepcopy(cfg))


def atomic_write(path, obj, mode=0o600):
    """写 tmp -> os.replace，失败不留半成品。"""
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    os.chmod(path, mode)


def backup_and_write(path, obj, keep=10):
    """写前把旧文件轮换备份为 <path>.bak-<时间戳>，再原子写入。

    备份按 mtime 排序只保留最近 keep 份（更老的前台删除，删除失败只跳过不中断）。
    时间戳到秒；同一秒内多次写入时追加 -1/-2… 后缀，避免后一次覆盖前一次的备份。
    返回本次备份路径；旧文件不存在（首次写入）时返回 None。
    """
    backup = None
    if os.path.isfile(path):
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = "%s.bak-%s" % (path, stamp)
        suffix = 1
        while os.path.exists(backup):
            backup = "%s.bak-%s-%d" % (path, stamp, suffix)
            suffix += 1
        shutil.copy2(path, backup)
        try:
            os.chmod(backup, 0o600)
        except OSError:
            pass
        olds = sorted(glob.glob(path + ".bak-*"), key=os.path.getmtime)
        for stale in olds[:max(0, len(olds) - keep)]:
            try:
                os.remove(stale)
            except OSError:
                pass
    atomic_write(path, obj)
    return backup


# yolo worker 的运行期输入节：这些值启动时读一次，运行中不感知文件变化
YOLO_SECTIONS = ("source", "detect", "snapshot", "stream", "model", "pic_dir")


def needs_restart(old, new):
    """比较两份配置，返回需重启才能生效的目标列表（["console"] / ["yolo"] / 两者）。

    * console 段（绑定/端口/白名单/会话时长/令牌）只影响 console 进程自身；
    * YOLO_SECTIONS 六节任一变化都要重启 yolo（worker 启动读一次）；
    * version / updated_at 等簿记字段变化不触发重启。
    """
    targets = []
    if old.get("console") != new.get("console"):
        targets.append("console")
    for sec in YOLO_SECTIONS:
        if old.get(sec) != new.get(sec):
            targets.append("yolo")
            break
    return targets
