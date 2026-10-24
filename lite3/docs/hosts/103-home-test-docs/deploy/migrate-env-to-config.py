#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""env -> config/yolo8.json 一次性迁移（计划书 v2.1 P0）。

职责：
  1. 读 deploy/yolo-publish.env，按计划书 §6.1 的 schema v2 生成 config/yolo8.json；
  2. 把"已迁入 config"的键在 env 里注释掉，避免双配置源各说各话（计划书 §5.11）；
  3. 幂等：config/yolo8.json 已存在则跳过（除非 --force）。

约束（103 真机）：Python 3.8.10 / 无 venv / 无 pip 源 ⇒ 只用标准库，禁 3.9+ 语法。

用法：
  python3 deploy/migrate-env-to-config.py            # 迁移
  python3 deploy/migrate-env-to-config.py --force    # 覆盖已存在的 config
  python3 deploy/migrate-env-to-config.py --dry-run  # 只打印将写入的内容
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys

APP_DIR = "/home/test/yolo8"
ENV_FILE = os.path.join(APP_DIR, "deploy", "yolo-publish.env")
CFG_DIR = os.path.join(APP_DIR, "config")
CFG_PATH = os.path.join(CFG_DIR, "yolo8.json")

# 迁入 config.json 的 env 键（改这些不再生效，走 config）
MIGRATED_KEYS = (
    "YOLO8_PUBLISH_MODE",
    "YOLO8_ENABLE_RTMP",
    "YOLO8_ENABLE_ROS2_IMAGE",
    "YOLO8_RTMP_URL",
    "YOLO8_RTMP_BITRATE",
    "YOLO8_CONF",
    "YOLO8_ROS2_EVERY",
)
# 保留在 env 的启动期静态键（改这些仍需重启服务）
KEPT_KEYS = (
    "HEADLESS",
    "YOLO8_STATUS_INTERVAL",
    "YOLO8_IMAGE_TOPIC",
    "YOLO8_IMAGE_QOS",
    "YOLO8_JPEG_QUALITY",
    "YOLO8_FRAME_ID",
    "ROSBRIDGE_PORT",
)

# source 段默认值：RTSP 地址在迁移时并不在 env 里（硬编码在
# src/GStreamerWrapper/GStreamerWrapper.py:24），这里以真机实测值落盘，
# 之后一律以 config 为准。
SOURCE_DEFAULTS = {
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
}


def read_env(path):
    """极简 env 解析：只认 KEY=VALUE，忽略注释与空行，值不带空格。"""
    kv = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, val = stripped.split("=", 1)
            kv[key.strip()] = val.strip()
    return kv


def env_flag(env, key, default):
    """env 布尔语义沿用 deploy/scripts/run-yolo-publish.sh：'0' 为假。"""
    return env.get(key, default) != "0"


def mode_to_switches(env):
    """与 run-yolo-publish.sh 的推导逻辑保持一致（rtmp/dual/ros2）。"""
    mode = env.get("YOLO8_PUBLISH_MODE", "rtmp")
    if mode == "ros2":
        return mode, False, True
    if mode == "dual":
        return mode, True, True
    return "rtmp", True, False


def build_config(env):
    mode, rtmp_on, ros2_on = mode_to_switches(env)

    source = dict(SOURCE_DEFAULTS)
    # 兼容早期把地址写进 env 的情况（真机未出现，防御性保留）
    if env.get("YOLO8_RTSP_URL"):
        source["rtsp_url"] = env["YOLO8_RTSP_URL"]

    try:
        conf_threshold = float(env.get("YOLO8_CONF", "0.5"))
    except ValueError:
        print("WARN: YOLO8_CONF=%r 不是合法浮点数，回退默认 0.5" % env.get("YOLO8_CONF"))
        conf_threshold = 0.5
    try:
        bitrate = int(env.get("YOLO8_RTMP_BITRATE", "1000000"))
    except ValueError:
        print("WARN: YOLO8_RTMP_BITRATE=%r 不是整数，回退默认 1000000" % env.get("YOLO8_RTMP_BITRATE"))
        bitrate = 1000000
    try:
        ros2_every = int(env.get("YOLO8_ROS2_EVERY", "3"))
    except ValueError:
        print("WARN: YOLO8_ROS2_EVERY=%r 不是整数，回退默认 3" % env.get("YOLO8_ROS2_EVERY"))
        ros2_every = 3

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    return {
        "version": 2,
        "_notice": ("P0 迁移生成。当前 worker 尚未消费本文件（计划书 v2.1 P2 接入），"
                    "生效仍以 deploy/yolo-publish.env 为准；接入后以本文件为唯一运行期配置。"),
        "console": {
            "bind": "0.0.0.0",
            "port": 8090,
            "allowed_cidrs": ["192.168.1.0/24"],
            "session_ttl_s": 43200,
            # 访问令牌：默认值与校验规则以 console/configlib.py 的 DEFAULT_TOKEN 为准
            "token": "jack1419",
        },
        "source": source,
        "detect": {"conf_threshold": conf_threshold, "classes": [0]},
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
            "rtmp": rtmp_on,
            "rtmp_url": env.get("YOLO8_RTMP_URL",
                                "rtmp://172.31.68.227:1936/live/lite3_yolo"),
            "rtmp_bitrate": bitrate,
            "rtmp_sink": "rtmpsink",
            "out_width": 640,
            "out_height": 360,
            "fps": 30,
            "ros2_image": ros2_on,
            "ros2_every": ros2_every,
            "reconnect": {"backoff_ms": 1000, "backoff_max_ms": 30000},
        },
        "model": {"engine": "../model/yolov8n_arm.engine", "pending_reload": False},
        "pic_dir": "../pic",
        "trash_retention_days": 7,
        "migrated_from": {
            "env_file": "deploy/yolo-publish.env",
            "mode": mode,
            "rtmp_enabled": rtmp_on,
            "ros2_image_enabled": ros2_on,
            "rtsp_url_origin": "GStreamerWrapper.py 硬编码默认值（真机实测可达）",
        },
        "updated_at": now,
    }


REQUIRED_TOP_KEYS = ("version", "console", "source", "detect", "snapshot",
                     "stream", "model", "pic_dir")


def validate_config(cfg):
    missing = [k for k in REQUIRED_TOP_KEYS if k not in cfg]
    if missing:
        raise ValueError("config 缺少必需字段: %s" % ", ".join(missing))
    if cfg["source"]["type"] not in ("rtsp", "file"):
        raise ValueError("source.type 只能是 rtsp 或 file")
    if cfg["source"]["decoder"] not in ("hw", "auto"):
        raise ValueError("source.decoder 只能是 hw 或 auto（103 无软解，avdec_h264 不存在）")
    if cfg["source"]["codec"] not in ("h264", "h265", "auto"):
        raise ValueError("source.codec 只能是 h264/h265/auto")
    if not 0.05 <= cfg["detect"]["conf_threshold"] <= 0.95:
        raise ValueError("conf_threshold 越界（应为 0.05~0.95）")
    if not re.match(r"^rtmps?://[^/\s]+/[^\s]+$", cfg["stream"]["rtmp_url"]):
        raise ValueError("rtmp_url 形如 rtmp://host:port/app/stream")
    if cfg["stream"]["rtmp_url"].rstrip("/").endswith("/live/lite3"):
        raise ValueError("rtmp_url 不能是 live/lite3（120 摄像头转发占用，同流名会互踢）")
    return True


def comment_out_migrated_keys(env_path, keys):
    """把已迁移的键注释掉，保留原值便于回溯；幂等（已注释则不动）。"""
    with open(env_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    out = []
    changed = 0
    for line in lines:
        stripped = line.strip()
        head = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if (not stripped.startswith("#")) and head in keys:
            out.append("# [已迁移至 config/yolo8.json，改这里不再生效] " + stripped + "\n")
            changed += 1
        else:
            out.append(line)

    if changed:
        backup = env_path + ".bak-migrate"
        shutil.copy2(env_path, backup)
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.writelines(out)
        print("ENV  已注释 %d 个已迁移键（备份 %s）" % (changed, backup))
    else:
        print("ENV  无需修改（已迁移键均已注释或缺失）")
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description="env -> config/yolo8.json 迁移")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 config")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不落盘")
    args = parser.parse_args(argv)

    if not os.path.exists(ENV_FILE):
        print("ERROR: env 文件不存在: %s" % ENV_FILE)
        return 1

    env = read_env(ENV_FILE)
    cfg = build_config(env)

    try:
        validate_config(cfg)
    except ValueError as exc:
        print("ERROR: 生成的配置未通过校验: %s" % exc)
        return 1

    text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"

    if args.dry_run:
        print(text)
        return 0

    if os.path.exists(CFG_PATH) and not args.force:
        print("SKIP: %s 已存在（--force 覆盖）" % CFG_PATH)
        return 0

    if not os.path.isdir(CFG_DIR):
        os.makedirs(CFG_DIR)

    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CFG_PATH)
    os.chmod(CFG_PATH, 0o600)
    print("WROTE %s (%d bytes, 0600)" % (CFG_PATH, len(text.encode("utf-8"))))

    comment_out_migrated_keys(ENV_FILE, MIGRATED_KEYS)

    print("保留在 env 的启动期键: %s" % ", ".join(k for k in KEPT_KEYS if k in env))
    print("迁移摘要: mode=%s rtmp=%s ros2_image=%s conf=%.2f bitrate=%d"
          % (cfg["migrated_from"]["mode"], cfg["stream"]["rtmp"],
             cfg["stream"]["ros2_image"], cfg["detect"]["conf_threshold"],
             cfg["stream"]["rtmp_bitrate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
