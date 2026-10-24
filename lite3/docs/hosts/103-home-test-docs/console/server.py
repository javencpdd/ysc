#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lite3 yolo8 Web 控制台（计划书 v2.1 P1 骨架+认证；P1.5 话题+配置；P3 抓拍浏览；
P4 模型上传/导出/重载）。

设计要点（对应计划书章节）：
  * 零第三方依赖：只用 Python 标准库（103 无 venv / 无可用 pip 源）；
    唯一例外是缩略图生成用 cv2（§5.5 设计如此，真机 ysc 用户可导入），
    导入失败时自动降级为直出原图。onnx 解析与 TRT 构建都在**子进程**里做
    （`src/export_engine.py`），console 自身永远不 import onnx/tensorrt。
  * 双进程解耦（§4.1）：本进程只做管理面；数据面是 yolo_worker，两者以 config.json 为接口（P2 接入）。
  * 认证与会话（§6.5）：配置令牌（console.token，默认 jack1419）+ HttpOnly Cookie 会话 +
    写接口双因子（X-Yolo-Token）+ CIDR 白名单 + 登录失败退避 + 限流 + 审计日志。
  * 服务启停（§5.1）：只 subprocess 调 deploy/lite3-publish-ctl.sh，不重复实现生命周期逻辑。
  * 抓拍浏览（§5.5/§5.5.1）：文件名即索引（不另建索引文件）；timeline 按
    (date, 目录 mtime + 文件名清单) 缓存；软删除 os.replace 进 pic/.trash/；文件名白名单 +
    realpath containment 双保险。
  * 模型（P4/§5.6）：上传 → inspect（onnx 输出推断类别数）→ 异步导出（TRT 子进程）
    → 预加载自检 → 原子替换（旧 engine 留 .bak-<ts>）→ 写 config pending_reload
    → worker 帧边界重建。单任务队列，10 min 超时强杀。

约束（103 真机）：Python 3.8.10 ⇒ 禁 3.9+ 语法（无 X | Y、无 match）。
"""

import argparse
import datetime
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from configlib import (CONFIG_VERSION, DEFAULT_TOKEN, ConfigError,  # noqa: E402
                       atomic_write, backup_and_write, deep_merge,
                       load_config, needs_restart, strip_sensitive,
                       validate_config)

APP_DIR = "/home/test/yolo8"
CONSOLE_DIR = os.path.join(APP_DIR, "console")
STATIC_DIR = os.path.join(CONSOLE_DIR, "static")
LOG_DIR = os.path.join(APP_DIR, "logs")
CONFIG_PATH = os.path.join(APP_DIR, "config", "yolo8.json")
AUDIT_LOG = os.path.join(LOG_DIR, "console-audit.log")
CTL_SCRIPT = os.path.join(APP_DIR, "deploy", "lite3-publish-ctl.sh")
WORKER_STATE = os.path.join(LOG_DIR, "worker_state.json")
MODEL_DIR = os.path.join(APP_DIR, "model")
UPLOAD_DIR = os.path.join(MODEL_DIR, "uploads")
EXPORT_DIR = os.path.join(MODEL_DIR, "exports")
EXPORT_SCRIPT = os.path.join(APP_DIR, "src", "export_engine.py")

VERSION = "2.1.0-p4"
SERVICE_TARGETS = ("yolo", "rosbridge")
SERVICE_ACTIONS = ("start", "stop", "restart")
SESSION_COOKIE = "yolo8_s"
TOKEN_HEADER = "X-Yolo-Token"
MAX_BODY_BYTES = 1 * 1024 * 1024          # JSON 体上限；上传走 P4 的 64 MB 专用通道
MAX_UPLOAD_BYTES = 50 * 1024 * 1024       # §6.4：单文件 ≤ 50 MB
MAX_UPLOAD_BODY = 64 * 1024 * 1024        # §6.4：请求体 ≤ 64 MB
UPLOAD_READ_TIMEOUT_S = 30.0              # §6.4：读超时 30 s
EXPORT_TIMEOUT_S = 2700                   # §5.6.4 原定 10 min；P4 真机实测 yolov8n
                                          # (onnx→engine, FP16, 1 GB workspace, 推理进程在跑)
                                          # 单次要 ~26 min（1580 s），30 min 余量只剩 220 s 太紧，
                                          # 放宽到 45 min，留出 ≥1.7× 余量。停掉推理后再导会更快。
EXPORT_LOG_LINES = 200                    # 环形日志行数
EXPORT_POLL_S = 1.0
CTL_TIMEOUT_S = 60                        # ctl 的 stop 最长等 10s，留足余量
STATUS_CACHE_TTL_S = 1.0                  # /api/state 1s 轮询，给 status 加 1s 缓存
LOGIN_MIN_INTERVAL_S = 1.0
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_S = 300
# P3：图片浏览（拖动预取缩略图）比普通 API 更密集，单独给 30/s 桶；
# 精确匹配在前（limiter 跳过 "/api" 前缀本身，见 RateLimiter.allow）
RATE_BUCKET = {"/api/pics": (30.0, 30.0), "/api/model/upload": (0.5, 1.0),
               "/api/model/export": (1.0, 1.0),
               "/api/maintenance/purge": (0.1, 1.0),   # P5：破坏性操作，10s 一次
               "/api": (10.0, 10.0)}
REJECT_WINDOW_S = 30.0                    # 拒绝事件聚合窗口（见 RejectThrottle）
CONFIG_BACKUPS_KEEP = 10                  # config/yolo8.json.bak-* 轮换保留份数
WRITABLE_SECTIONS = ("source", "detect", "snapshot", "stream", "model", "pic_dir",
                     "retention")
ENV_FILE = os.path.join(APP_DIR, "deploy", "yolo-publish.env")
ROS_SETUP = "/opt/ros/foxy/setup.bash"
ROS2_BIN = "/opt/ros/foxy/bin/ros2"
ROSBRIDGE_PORT_DEFAULT = 9090
TOPICS_TIMEOUT_S = 10.0                   # ros2 topic list 上限（DDS 发现通常 <3s）
PROBE_TIMEOUT_S = 12.0                    # ffprobe 探 RTSP 上限
TCP_PROBE_TIMEOUT_S = 5.0                 # RTMP 目标 TCP 连通探测上限
YOLO_COLD_START_S = 35                    # 冷启动时长（前端提示与计划书一致）

# ---- P5 存储治理（对齐 m20-ai-detect 的 ADR-008 / ADR-011）----
# 两个维度各自独立，0 = 不按该维度清理（aiDetect 同语义）
DEFAULT_RETENTION = {
    "pic_max_mb": 2048,          # pic/ 体积上限（.trash 不计入）
    "pic_keep_days": 30,         # pic/ 保留天数
    "trash_keep_days": 7,        # 回收站保留天数（补上"只进不出"的缺口）
    "prune_interval_s": 600,     # 周期清理间隔，10 min（与 aiDetect 同粒度）
}
PURGE_TARGETS = ("pics", "trash", "uploads", "exports", "logs")
STORAGE_CACHE_S = 30.0                    # 占用统计缓存（UI 轮询不重复 walk 目录）
# 计时缓存是把导出构建从 26 min 压到 2 min 的资产（P4 实测），purge 默认跳过它
TIMING_CACHE_NAME = ".trt-timing-cache"
# worker_state.json 超过这个秒数没更新，就认为 worker 不在了（worker 1s 写一次，
# 给 15s 是留足卡顿/GC 余量，避免误拒）
WORKER_STALE_S = 15.0

# ---------------------------------------------------------------- 抓拍图片（P3）

PIC_DATE_RE = re.compile(r"^\d{8}$")
PIC_NAME_RE = re.compile(r"^\d{8}T\d{6}_\d{3}_c\d{3}_id\d{3}\.jpg$")
PIC_SAFE_RE = re.compile(r"^[0-9A-Za-z._-]+$")     # §5.5 文件名白名单
THUMB_WIDTH = 320                           # §5.5：缩略图宽 320，缓存 pic/.thumbs/
TIMELINE_MAX_ITEMS = 5000                   # §5.5.1：单日超此数返回等距抽稀刻度

try:
    import cv2                              # 缩略图生成用；缺失时降级为直出原图
except ImportError:                         # pragma: no cover - 真机必有
    cv2 = None


def today_str():
    return datetime.date.today().strftime("%Y%m%d")


def parse_pic_name(name):
    """抓拍文件名 → (ts_ms, conf, tid)；不合规返回 None。

    文件名即索引（§5.5.1：不另建索引文件）：`YYYYmmddTHHMMSS_mmm_cNNN_idNNN.jpg`。
    ts_ms 按**本地时区**解析（与写入侧 datetime.fromtimestamp 一致）。
    """
    matched = re.match(
        r"^(\d{8})T(\d{2})(\d{2})(\d{2})_(\d{3})_c(\d{3})_id(\d{3})\.jpg$", name)
    if not matched:
        return None
    date_s, hh, mm, ss, ms, conf, tid = matched.groups()
    try:
        dt = datetime.datetime.strptime(date_s, "%Y%m%d").replace(
            hour=int(hh), minute=int(mm), second=int(ss))
    except ValueError:
        return None
    ts_ms = int(time.mktime(dt.timetuple())) * 1000 + int(ms)
    return ts_ms, int(conf) / 1000.0, int(tid)


class PicStore(object):
    """pic/ 目录的浏览 + 软删除（计划书 §5.5 / §5.5.1）。

    安全两条（§5.5）：文件名白名单 `PIC_SAFE_RE` + `realpath` containment，
    任何 `../` 穿越在 resolve() 就被挡掉。
    缓存：timeline/list 按 (date, 目录 mtime + 文件名清单) 缓存；
    删除/还原后主动失效。
    """

    def __init__(self, dir_getter):
        self._dir_getter = dir_getter
        self._lock = threading.Lock()
        self._cache = {}                     # date -> (dir_mtime, payload)

    @property
    def pic_dir(self):
        return self._dir_getter()

    def day_dir(self, date):
        return os.path.join(self.pic_dir, date)

    def dates(self):
        out = []
        try:
            for name in os.listdir(self.pic_dir):
                if PIC_DATE_RE.match(name) \
                        and os.path.isdir(os.path.join(self.pic_dir, name)):
                    out.append(name)
        except OSError:
            pass
        return sorted(out, reverse=True)

    # ---------- 索引 ----------
    def _scan(self, date):
        """扫一个日期目录 → 升序 items；带缓存。不存在返回 None。

        缓存键 = (目录 mtime, jpg 文件名清单)：mtime 在前挡掉无变化调用，
        names 在后兜底——某些文件系统（实测本机 Windows）在「紧接着的连续
        创建」时会合并不刷新目录 mtime（实测 28/30 复现），只靠 mtime 会把
        刚写入的抓拍漏掉最长一个粒度窗口。listdir 本来就无条件执行，
        比对 names 零额外成本。删除/还原走 invalidate() 主动失效。
        """
        day_dir = self.day_dir(date)
        try:
            mtime = os.stat(day_dir).st_mtime
            names = [n for n in os.listdir(day_dir) if n.endswith(".jpg")]
        except OSError:
            return None
        with self._lock:
            hit = self._cache.get(date)
            if hit and hit[0] == mtime and hit[1] == names:
                return hit[2]
        items = []
        for name in names:
            parsed = parse_pic_name(name)
            if parsed is None:
                continue
            ts_ms, conf, _tid = parsed
            try:
                size = os.path.getsize(os.path.join(day_dir, name))
            except OSError:
                continue
            items.append({"ts_ms": ts_ms, "name": name, "conf": conf,
                          "cls": self._cls_of(day_dir, name), "size": size})
        items.sort(key=lambda it: it["ts_ms"])
        payload = {"date": date, "count": len(items), "items": items}
        with self._lock:
            self._cache[date] = (mtime, names, payload)
        return payload

    @staticmethod
    def _cls_of(day_dir, name):
        """主类别取 sidecar 的 classes[0]；无 sidecar（save_meta=false）返回 None。"""
        try:
            with open(os.path.join(day_dir, name[:-4] + ".json"),
                      "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            classes = meta.get("classes") or []
            return classes[0] if classes else None
        except (OSError, ValueError):
            return None

    def timeline(self, date):
        """§5.5.1：当日抓拍时间轴（升序）。>5000 条等距抽稀 + total。"""
        payload = self._scan(date)
        if payload is None:
            return {"ok": True, "date": date, "exists": False,
                    "count": 0, "items": []}
        items = payload["items"]
        sampled = False
        if len(items) > TIMELINE_MAX_ITEMS:
            step = int(math.ceil(len(items) / float(TIMELINE_MAX_ITEMS)))
            items = items[::step]
            sampled = True
        return {"ok": True, "date": date, "exists": True,
                "count": payload["count"], "items": items, "sampled": sampled}

    def list_pics(self, date, page, size):
        """§5.5：分页列表（时间倒序）。"""
        payload = self._scan(date)
        if payload is None:
            return {"ok": True, "date": date, "exists": False,
                    "total": 0, "page": page, "size": size, "items": []}
        items = list(reversed(payload["items"]))
        total = len(items)
        start = (page - 1) * size
        return {"ok": True, "date": date, "exists": True, "total": total,
                "page": page, "size": size, "items": items[start:start + size]}

    # ---------- 原图 / 缩略图 ----------
    def resolve(self, date, name):
        """校验并返回原图绝对路径；任何不合法返回 None。"""
        if not PIC_DATE_RE.match(date) or not PIC_SAFE_RE.match(name):
            return None
        if not PIC_NAME_RE.match(name) or not name.startswith(date):
            return None
        path = os.path.realpath(os.path.join(self.day_dir(date), name))
        root = os.path.realpath(self.pic_dir)
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            return None
        return path

    def ensure_thumb(self, date, name):
        """生成/复用缩略图（cv2 缩到宽 320，pic/.thumbs/ 缓存）。失败返回 None。"""
        src = self.resolve(date, name)
        if src is None or cv2 is None:
            return None
        thumb = os.path.join(self.pic_dir, ".thumbs", name)
        try:
            if os.path.isfile(thumb) \
                    and os.path.getmtime(thumb) >= os.path.getmtime(src):
                return thumb
            img = cv2.imread(src, cv2.IMREAD_COLOR)
            if img is None:
                return None
            height, width = img.shape[:2]
            if width > THUMB_WIDTH:
                scale = THUMB_WIDTH / float(width)
                img = cv2.resize(img, (THUMB_WIDTH, max(1, int(height * scale))),
                                 interpolation=cv2.INTER_AREA)
            os.makedirs(os.path.dirname(thumb), exist_ok=True)
            ok, buf = cv2.imencode(".jpg", img,
                                   [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return None
            tmp = thumb + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(buf.tobytes())
            os.replace(tmp, thumb)
            return thumb
        except Exception:                    # noqa: BLE001  缩略图是旁路，失败回退原图
            return None

    # ---------- 软删除 / 回收站（D2） ----------
    def trash(self, date, name):
        """os.replace 到 pic/.trash/<date>/（同分区原子移动，不复制）。

        返回目标路径；不存在返回 None；目标已占用返回 "exists"。
        """
        src = self.resolve(date, name)
        if src is None:
            return None
        dst_dir = os.path.join(self.pic_dir, ".trash", date)
        dst = os.path.join(dst_dir, name)
        if os.path.exists(dst):
            return "exists"
        os.makedirs(dst_dir, exist_ok=True)
        os.replace(src, dst)
        self.invalidate(date)
        return dst

    def restore(self, name):
        """从回收站还原到原日期目录（日期从文件名前 8 位恢复）。"""
        if not PIC_SAFE_RE.match(name) or not PIC_NAME_RE.match(name):
            return None
        date = name[:8]
        src = os.path.realpath(os.path.join(self.pic_dir, ".trash", date, name))
        root = os.path.realpath(os.path.join(self.pic_dir, ".trash"))
        if not src.startswith(root + os.sep) or not os.path.isfile(src):
            return None
        dst_dir = self.day_dir(date)
        dst = os.path.join(dst_dir, name)
        if os.path.exists(dst):
            return "exists"
        os.makedirs(dst_dir, exist_ok=True)
        os.replace(src, dst)
        self.invalidate(date)
        return dst

    def trash_list(self):
        """回收站清单（按时间倒序）。"""
        out = []
        root = os.path.join(self.pic_dir, ".trash")
        try:
            date_dirs = os.listdir(root)
        except OSError:
            return out
        for date in date_dirs:
            if not PIC_DATE_RE.match(date):
                continue
            try:
                names = os.listdir(os.path.join(root, date))
            except OSError:
                continue
            for name in names:
                if not name.endswith(".jpg"):
                    continue
                parsed = parse_pic_name(name)
                try:
                    size = os.path.getsize(os.path.join(root, date, name))
                except OSError:
                    continue
                out.append({"date": date, "name": name,
                            "ts_ms": parsed[0] if parsed else None,
                            "size": size})
        out.sort(key=lambda it: (it["ts_ms"] or 0), reverse=True)
        return out

    def invalidate(self, date):
        with self._lock:
            self._cache.pop(date, None)


# ---------------------------------------------------------------- 模型上传/导出（P4）

UPLOAD_NAME_RE = re.compile(r"^[0-9a-f]{16,32}\.onnx$")
ENGINE_NAME_RE = re.compile(r"^[0-9A-Za-z._-]+\.engine$")
ENGINE_REL_RE = re.compile(r"^[0-9A-Za-z._/-]+\.engine$")
ENGINE_META_KEYS = ("stride", "task", "batch", "imgsz", "names")
ENGINE_META_MAX = 1 << 20


def parse_multipart(body, content_type):
    """§6.4：用 email 标准库解析 multipart。

    `cgi` 在 Python 3.13 已移除、3.8 起就 deprecated；email 方案跨 3.8→3.13+ 一致。
    返回 {字段名: {"filename", "content_type", "data"}}；非 multipart 返回 {}。
    """
    if not body:
        return {}
    raw = (b"Content-Type: " + content_type.encode("latin-1")
           + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    try:
        msg = BytesParser(policy=email_policy).parsebytes(raw)
    except Exception:                                  # noqa: BLE001  坏 multipart 一律当空
        return {}
    if not msg.is_multipart():
        return {}
    out = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        data = part.get_payload(decode=True)
        if data is None:
            continue
        out[name] = {"filename": part.get_filename(),
                     "content_type": part.get_content_type(),
                     "data": data}
    return out


def read_engine_meta(path):
    """只读 engine 头（与 src/export_engine.py 同一格式），不 import 任何三方库。"""
    try:
        size = os.path.getsize(path)
        if size < 8:
            return None, "文件过小（%d 字节）" % size
        with open(path, "rb") as fh:
            meta_len = int.from_bytes(fh.read(4), byteorder="little", signed=True)
            if meta_len <= 0 or meta_len > ENGINE_META_MAX or meta_len + 4 > size:
                return None, "meta_len 非法（%d，文件 %d 字节）" % (meta_len, size)
            payload = fh.read(meta_len)
        meta = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, "%s" % exc
    if not isinstance(meta, dict):
        return None, "metadata 不是 JSON 对象"
    missing = [k for k in ENGINE_META_KEYS if k not in meta]
    if missing:
        return None, "metadata 缺必需 key：%s" % ", ".join(missing)
    meta["_meta_len"] = meta_len
    meta["_plan_len"] = size - 4 - meta_len
    meta["_size"] = size
    return meta, None


def run_engine_tool(args, timeout=60):
    """调用 src/export_engine.py（inspect / verify），解析 RESULT 行。"""
    try:
        proc = subprocess.run([sys.executable, EXPORT_SCRIPT] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, cwd=os.path.dirname(EXPORT_SCRIPT))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "export_engine 超时（%ss）" % timeout}
    except OSError as exc:
        return {"ok": False, "error": "无法执行 export_engine：%s" % exc}
    payload = None
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("RESULT "):
            try:
                payload = json.loads(line[len("RESULT "):])
            except ValueError:
                payload = None
    if payload is None:
        err = (proc.stderr.decode("utf-8", "replace") or "").strip()[-400:]
        return {"ok": False, "error": "export_engine 无 RESULT 输出（exit=%s）：%s"
                                      % (proc.returncode, err)}
    if proc.returncode != 0:
        payload["ok"] = False
        payload.setdefault("error", "export_engine exit=%s" % proc.returncode)
    return payload


def mem_available_mb():
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def normalize_names(raw):
    """names 规整为 {"0": "person", ...}；接受数组/对象/Python 字面量字符串。"""
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("names 不能为空")
        try:
            import ast
            raw = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            try:
                raw = json.loads(text)
            except ValueError:
                raise ValueError("names 既不是 Python 字面量也不是 JSON")
    if isinstance(raw, (list, tuple)):
        return dict((str(i), str(v)) for i, v in enumerate(raw))
    if isinstance(raw, dict):
        out = {}
        for key, val in raw.items():
            try:
                out[str(int(key))] = str(val)
            except (TypeError, ValueError):
                raise ValueError("names 的键必须是整数：%r" % (key,))
        return out
    raise ValueError("names 必须是数组、对象或字符串")


def validate_names(names, classes):
    if not names:
        raise ValueError("names 不能为空")
    ids = sorted(int(k) for k in names)
    if ids != list(range(len(ids))):
        raise ValueError("names 的 id 必须从 0 连续")
    if classes is not None and len(ids) != int(classes):
        raise ValueError("类别数不匹配：names 有 %d 个，onnx 输出推断 %d 个"
                         % (len(ids), int(classes)))
    warnings = []
    if names.get("0") != "person":
        warnings.append("names[0]=%r 不是 person（跟踪目标由 detect.classes 决定）"
                        % names.get("0"))
    return warnings


def sanitize_engine_rel(raw, default="yolov8n_arm.engine"):
    """把前端给的 engine 路径规整成 model/ 下的相对路径（不含 ../model/ 前缀）。

    只接受 ``sub/name.engine``；拒绝绝对路径与任何 ``..``（穿越）。
    """
    text = (raw or "").strip() or default
    for prefix in ("../model/", "./", "/"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if not text or text.startswith("/") or ".." in text.split("/"):
        raise ValueError("engine 路径不合法：%r" % (raw,))
    if not ENGINE_REL_RE.match(text):
        raise ValueError("engine 必须是 .engine 文件名（可含子目录），当前 %r" % (text,))
    return text


def looks_like_text(data):
    """前 64 字节全是可打印 ASCII/空白 ⇒ 当作文本拒绝（挡住"改扩展名"的假 onnx）。"""
    head = data[:64]
    if not head:
        return True
    return all(32 <= b < 127 or b in (9, 10, 13) for b in head)


class ExportManager(object):
    """单任务导出队列（§5.6.4）。

    状态机：idle → exporting → exported / failed。
    `exporting` 期间 progress/phase/log 由子进程 stdout 协议驱动
    （PROGRESS/INFO/RESULT，见 src/export_engine.py）。单任务、10 min 超时强杀。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._task = {"state": "idle", "progress": 0, "phase": "idle",
                      "log": [], "error": None, "engine": None, "size": None,
                      "started_at": None, "finished_at": None,
                      "upload": None, "build": None, "warnings": []}
        self._thread = None

    # ---- 读 ----
    def snapshot(self):
        with self._lock:
            task = dict(self._task)
            task["log"] = list(self._task["log"])
            return task

    def busy(self):
        with self._lock:
            return self._task["state"] == "exporting"

    # ---- 内部 ----
    def _append(self, line):
        with self._lock:
            log = self._task["log"]
            log.append(line)
            if len(log) > EXPORT_LOG_LINES:
                del log[:len(log) - EXPORT_LOG_LINES]

    def _set(self, **kw):
        with self._lock:
            self._task.update(kw)

    def _fail(self, error):
        self._append("ERROR %s" % error)
        self._set(state="failed", error=error, finished_at=now_iso(), phase="failed")

    def _preload_check(self, path):
        """§5.6.4「替换前必须试加载」——用 TRT 反序列化 + metadata 双检。

        为什么不用 `AutoBackend`：P4 真机实测，在 worker 常驻（GPU 上下文已被占用）
        时 `AutoBackend(weights=..., device='cuda:0')` 会长时间挂住（90 s 无输出，
        内存也吃 2 GB），既拖慢导出又产生假失败。改为在同一子进程里只做
        `deserialize_cuda_engine`（验证 plan 可用）+ 头解析（5 个 key），
        秒级完成、零 GPU 上下文争用；**真正的 ultralytics 端到端加载由 worker
        重载后的首帧推理证明**（L5 的 reload + fps 检查）。
        """
        code = ("import json,sys,tensorrt as trt\n"
                "p=sys.argv[1]\n"
                "ml=int.from_bytes(open(p,'rb').read(4),'little',signed=True)\n"
                "f=open(p,'rb'); f.seek(4+ml); plan=f.read()\n"
                "rt=trt.Runtime(trt.Logger(trt.Logger.ERROR))\n"
                "eng=rt.deserialize_cuda_engine(plan)\n"
                "print('PRELOAD '+json.dumps({'ok':bool(eng),'mode':'trt_deserialize',"
                "'bindings':(eng.num_bindings if eng else 0)}))\n")
        try:
            proc = subprocess.run([sys.executable, "-c", code, path],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=120, cwd=os.path.join(APP_DIR, "src"),
                                  env=dict(os.environ, PYTHONUNBUFFERED="1"))
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "TRT 反序列化超时（120s）"}
        except OSError as exc:
            return {"ok": False, "error": "无法执行预加载：%s" % exc}
        out = proc.stdout.decode("utf-8", "replace")
        for line in out.splitlines():
            if line.startswith("PRELOAD "):
                try:
                    return json.loads(line[len("PRELOAD "):])
                except ValueError:
                    pass
        err = (proc.stderr.decode("utf-8", "replace") or out).strip()[-400:]
        return {"ok": False, "error": "TRT 反序列化失败（exit=%s）：%s"
                                      % (proc.returncode, err)}

    def _run(self, onnx_path, names, target_rel, workspace_mb, half, opt_level):
        out_path = os.path.join(MODEL_DIR, target_rel)
        names_json = os.path.join(UPLOAD_DIR, os.path.basename(onnx_path) + ".names.json")
        cmd = [sys.executable, EXPORT_SCRIPT, "--onnx", onnx_path, "--out", out_path,
               "--workspace-mb", str(int(workspace_mb)),
               "--opt-level", str(int(opt_level))]
        if not half:
            cmd.append("--fp32")
        deadline = time.time() + EXPORT_TIMEOUT_S
        proc = None
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(names_json, "w", encoding="utf-8") as fh:
                json.dump(names, fh, ensure_ascii=False)
            cmd.extend(["--names-json", names_json])
            self._append("INFO %s → %s（workspace %d MB，opt %d，%s）"
                         % (os.path.basename(onnx_path), target_rel,
                            int(workspace_mb), int(opt_level),
                            "FP16" if half else "FP32"))
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    cwd=os.path.dirname(EXPORT_SCRIPT),
                                    env=dict(os.environ, PYTHONUNBUFFERED="1"))
            result = None
            while True:
                if time.time() > deadline:
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    self._fail("导出超时（%d s）已强杀；旧 engine 未动" % EXPORT_TIMEOUT_S)
                    return
                ready, _, _ = select.select([proc.stdout], [], [], EXPORT_POLL_S)
                if ready:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", "replace").rstrip()
                    if text.startswith("PROGRESS "):
                        parts = text.split(None, 2)
                        try:
                            pct = int(parts[1])
                        except (IndexError, ValueError):
                            pct = self._task["progress"]
                        phase = parts[2] if len(parts) > 2 else ""
                        with self._lock:
                            self._task["progress"] = max(0, min(100, pct))
                            self._task["phase"] = phase
                        self._append(text)
                    elif text.startswith("RESULT "):
                        try:
                            result = json.loads(text[len("RESULT "):])
                        except ValueError:
                            result = None
                    elif text:
                        self._append(text)
                elif proc.poll() is not None:
                    break
            try:
                rc = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                rc = -1
            if result is None or not result.get("ok"):
                self._fail((result or {}).get("error")
                           or "导出失败（exit=%s）" % rc)
                return
            self._append("INFO 导出完成（%s 字节），开始自检" % result.get("size"))
            self._set(progress=94, phase="preload")
            meta, err = read_engine_meta(out_path)
            if meta is None:
                self._fail("engine 头校验失败：%s" % err)
                return
            if len(meta.get("names") or {}) != int(result.get("classes") or 0):
                self._fail("metadata names 数量（%d）与类别数（%s）不一致"
                           % (len(meta.get("names") or {}), result.get("classes")))
                return
            preload = self._preload_check(out_path)
            if not preload.get("ok"):
                self._fail("预加载自检失败（旧 engine 未动）：%s"
                           % preload.get("error"))
                return
            names_n = len(meta.get("names") or {})
            build = result.get("build") or {}
            self._append("INFO 预加载通过（%s，%d 类）；构建耗时 %ss，workspace %sMB，fp16=%s"
                         % (preload.get("mode"), names_n,
                            build.get("build_s", "-"),
                            build.get("workspace_mb", "-"),
                            build.get("fp16", "-")))
            self._set(state="exported", progress=100, phase="done",
                      finished_at=now_iso(), engine=target_rel,
                      size=os.path.getsize(out_path),
                      build=result.get("build"),
                      warnings=(result.get("warnings") or [])
                      + ([preload["note"]] if preload.get("note") else []))
        except Exception as exc:                       # noqa: BLE001 后台线程兜底
            self._fail("%s: %s" % (type(exc).__name__, exc))
        finally:
            try:
                if proc is not None and proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                if os.path.exists(names_json):
                    os.unlink(names_json)
            except OSError:
                pass

    # ---- 写 ----
    def start(self, upload_name, onnx_path, names, target_rel, workspace_mb, half,
              opt_level=2):
        with self._lock:
            if self._task["state"] == "exporting":
                return False, "已有导出任务在运行（单任务队列）"
            self._task = {"state": "exporting", "progress": 1, "phase": "start",
                          "log": [], "error": None, "engine": None, "size": None,
                          "started_at": now_iso(), "finished_at": None,
                          "upload": upload_name, "build": None, "warnings": []}
        self._thread = threading.Thread(target=self._run, name="engine-export",
                                        args=(onnx_path, names, target_rel,
                                              workspace_mb, half, opt_level))
        self._thread.daemon = True
        self._thread.start()
        return True, None


# ---------------------------------------------------------------- 基础设施

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def log_line(msg):
    """控制台自身日志（stdout 由 systemd 追加到 logs/console.log）。"""
    sys.stdout.write("[%s] %s\n" % (now_iso(), msg))
    sys.stdout.flush()


def lan_ip():
    """本机在 192.168.1.0/24 网段的出口 IP（拼 ws_url 用）。

    UDP connect 不发包、只做选路：对端不可达时通常仍能拿到源地址；全失败返回 None。
    """
    for probe in ("192.168.1.120", "192.168.1.1", "192.168.1.103"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe, 80))
            return sock.getsockname()[0]
        except OSError:
            continue
        finally:
            sock.close()
    return None


def read_env_port(name, default):
    """从 deploy/yolo-publish.env 读 KEY=VALUE。

    自行解析而不 source：env 文件是部署产物，不该在 console 进程里执行 shell。
    """
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip() != name:
                    continue
                val = val.strip().strip("\"'")
                try:
                    return int(val)
                except ValueError:
                    return default
    except OSError:
        pass
    return default


def probe_rtsp(url, transport, timeout=PROBE_TIMEOUT_S):
    """ffprobe 探 RTSP 流：返回首个视频流的编码/分辨率/帧率。

    subprocess 超时是硬护栏——ffprobe 对流不可达时会挂住等首帧，不能光靠它自己。
    """
    cmd = ["ffprobe", "-v", "error", "-rtsp_transport", transport,
           "-select_streams", "v:0",
           "-show_entries", "stream=codec_name,width,height,avg_frame_rate",
           "-of", "json", url]
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"reachable": False,
                "error": "ffprobe 超时（%gs）：流不可达或握手过慢" % timeout}
    except OSError as exc:
        return {"reachable": False, "error": "无法执行 ffprobe: %s" % exc}
    out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        return {"reachable": False,
                "error": (proc.stderr.decode("utf-8", "replace") or out).strip()[-300:]}
    try:
        streams = (json.loads(out) or {}).get("streams") or []
    except ValueError:
        return {"reachable": False, "error": "ffprobe 输出无法解析"}
    if not streams:
        return {"reachable": False, "error": "连接成功但没有视频流"}
    first = streams[0]
    return {"reachable": True, "codec": first.get("codec_name"),
            "width": first.get("width"), "height": first.get("height"),
            "fps": first.get("avg_frame_rate")}


def probe_tcp(host, port, timeout=TCP_PROBE_TIMEOUT_S):
    """TCP 连通探测（RTMP 推流目标的轻量预检，不校验鉴权/流名）。"""
    started = time.time()
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        conn.close()
        return {"reachable": True, "elapsed_ms": int((time.time() - started) * 1000)}
    except OSError as exc:
        return {"reachable": False, "elapsed_ms": int((time.time() - started) * 1000),
                "error": "%s" % exc}


class AuditLog(object):
    """所有写操作与安全事件追加到 logs/console-audit.log（单行 JSON）。"""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)

    def record(self, event, result, ip="-", detail=None):
        entry = {"ts": now_iso(), "event": event, "result": result, "ip": ip}
        if detail:
            entry["detail"] = detail
        line = json.dumps(entry, ensure_ascii=False)
        with self.lock:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:            # 审计写不进去不能拖垮服务，但必须留痕
                log_line("AUDIT WRITE FAILED: %s (%s)" % (line, exc))


class TokenManager(object):
    """访问令牌：取自配置文件 console.token（默认 jack1419，开发期固定值）。

    历史版本读 console/token 文件（32 hex、首次启动自动生成、0600）；现改为配置驱动，
    该文件不再使用（已存在也忽略）。令牌限 1~128 位可打印 ASCII 且无空白——同一值
    既用于登录体，也用于写接口的 X-Yolo-Token 头。日志不打印明文。
    """

    def __init__(self, token):
        self.token = token

    def verify(self, candidate):
        if not isinstance(candidate, str) or not candidate:
            return False
        return hmac.compare_digest(candidate, self.token)


class SessionStore(object):
    """内存会话表：sid -> {ip, created, last_seen}。进程重启即全部失效（可接受）。"""

    def __init__(self, ttl_s):
        self.ttl_s = ttl_s
        self.lock = threading.Lock()
        self.sessions = {}

    def _gc(self):
        now = time.time()
        for sid in [s for s, v in self.sessions.items() if now - v["last_seen"] > self.ttl_s]:
            del self.sessions[sid]

    def create(self, ip):
        sid = secrets.token_hex(16)
        with self.lock:
            self._gc()
            self.sessions[sid] = {"ip": ip, "created": now_iso(), "last_seen": time.time()}
        return sid

    def valid(self, sid, ip):
        if not sid:
            return False
        with self.lock:
            self._gc()
            info = self.sessions.get(sid)
            if not info:
                return False
            info["last_seen"] = time.time()
            return True

    def drop(self, sid):
        with self.lock:
            self.sessions.pop(sid, None)

    def count(self):
        with self.lock:
            self._gc()
            return len(self.sessions)


class LoginBackoff(object):
    """同 IP 连续失败 LOGIN_MAX_FAILS 次 -> 锁 LOGIN_LOCK_S 秒。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.fails = {}
        self.locked_until = {}

    def check(self, ip):
        with self.lock:
            until = self.locked_until.get(ip, 0)
            return until > time.time()

    def fail(self, ip):
        with self.lock:
            n = self.fails.get(ip, 0) + 1
            self.fails[ip] = n
            if n >= LOGIN_MAX_FAILS:
                self.locked_until[ip] = time.time() + LOGIN_LOCK_S
                self.fails[ip] = 0
                return True
            return False

    def success(self, ip):
        with self.lock:
            self.fails.pop(ip, None)
            self.locked_until.pop(ip, None)


class RateLimiter(object):
    """按 IP 的令牌桶；额外限制登录接口频率。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.buckets = {}
        self.last_login = {}

    def allow(self, ip, path):
        now = time.time()
        with self.lock:
            rate, cap = RATE_BUCKET.get("/api", (10.0, 10.0))
            for prefix, val in RATE_BUCKET.items():
                if prefix != "/api" and path.startswith(prefix):
                    rate, cap = val
                    break
            bucket = self.buckets.setdefault(ip, [cap, now])
            bucket[0] = min(cap, bucket[0] + (now - bucket[1]) * rate)
            bucket[1] = now
            if bucket[0] < 1.0:
                return False
            bucket[0] -= 1.0
            if path.startswith("/api/auth/login"):
                last = self.last_login.get(ip, 0)
                if now - last < LOGIN_MIN_INTERVAL_S:
                    return False
                self.last_login[ip] = now
            return True


class RejectThrottle(object):
    """拒绝类审计事件的聚合器。

    需求两头堵（P1-3 验收 G2 实测出来的）：
      * 不记 → 未认证 401 完全无痕，探测行为不可见（原实现的缺口）；
      * 逐条记 → 白名单外 403 / 无会话 401 可被扫描器按限流上限（10 req/s）
        写爆审计日志，真正的事件被淹掉。
    解法：窗口内**首条立即落盘**（保证刚发生就被看见），其余只累加计数；
    后台线程每 window_s 把被抑制的条数汇总补一条，次数信息不丢。
    （进程被杀时最多丢失一个窗口的汇总，可接受——精确计数由 LoginBackoff
      独立负责，那条路径不降频。）
    """

    def __init__(self, window_s=30.0):
        self.window_s = window_s
        self.lock = threading.Lock()
        self.state = {}

    def due(self, event, ip):
        """True 表示调用方应立即写一条审计（本窗口首条）。"""
        key = event + "|" + ip
        now = time.time()
        with self.lock:
            ent = self.state.get(key)
            if ent is None or now - ent["first"] >= self.window_s:
                ent = {"first": now, "count": 0, "reported": 0}
                self.state[key] = ent
            ent["count"] += 1
            if ent["count"] == 1:
                ent["reported"] = 1
                return True
            return False

    def drain(self):
        """取出各 (event, ip) 自上次汇总以来被抑制的条数，并标记为已汇总。"""
        out = []
        with self.lock:
            for key, ent in self.state.items():
                suppressed = ent["count"] - ent["reported"]
                if suppressed > 0:
                    event, ip = key.split("|", 1)
                    out.append((event, ip, suppressed))
                    ent["reported"] = ent["count"]
        return out


class ServiceCtl(object):
    """只负责调 lite3-publish-ctl.sh 并解析输出，不重复实现生命周期逻辑（§5.1）。"""

    def __init__(self, script):
        self.script = script
        self.status_cache = {"ts": 0.0, "data": None}
        self.status_lock = threading.Lock()
        self.action_locks = {t: threading.Lock() for t in SERVICE_TARGETS}

    def _run(self, args, timeout=CTL_TIMEOUT_S):
        # stdin=DEVNULL 是安全关键：ctl 的 ensure_root 见 [ -t 0 ] 为真会 exec sudo
        # 弹密码提示，从交互终端启 console 时会把工作线程挂死。
        try:
            proc = subprocess.run([self.script] + args,
                                  stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, "", "ctl 超时（%ss）" % timeout
        except OSError as exc:
            return 127, "", "无法执行 %s: %s" % (self.script, exc)
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        return proc.returncode, out, err

    @staticmethod
    def parse_status(text):
        """把 ctl status 的人读输出解析成结构化数据。

        ctl 的 show_status 四种分支（真机 2026-10-22 核实）：
          [t] unit=<svc> 已启用（systemd 托管）        → systemd
          [t] unit=<svc> 已安装但未启用（enabled=x）   → installed_disabled
          [t] unit=未安装，进程直管                    → direct
          [t] unit=未安装，进程未运行                  → not_installed
        注意「已安装但未启用」也含「启用」二字，必须先判长串再判短串。
        """
        info = {"mode": "unknown", "unit": None, "enabled": None,
                "running": False, "pid": None, "uptime": None, "log_tail": []}
        for line in text.splitlines():
            # 单位值可能是 "lite3-yolo-publish.service" 或 "未安装，进程直管"（中文逗号结尾），
            # 因此字符类要同时排除空白与两种逗号，否则 \S+ 会把"，进程直管"一起吞掉导致整行失配。
            matched = re.match(r"^\[(\w+)\]\s+unit=([^\s，,]+)[，,\s]*(.*)$", line)
            if matched:
                unit = matched.group(2)
                tail = matched.group(3)
                if unit.startswith("未安装"):
                    info["unit"] = None
                else:
                    info["unit"] = unit
                if "已安装但未启用" in tail:
                    info["mode"] = "installed_disabled"
                    enabled = re.search(r"enabled=(\S+?)\)", tail)
                    info["enabled"] = enabled.group(1) if enabled else "disabled"
                elif "已启用" in tail:
                    info["mode"] = "systemd"
                    info["enabled"] = "enabled"
                elif "进程直管" in tail:
                    info["mode"] = "direct"
                elif "进程未运行" in tail:
                    info["mode"] = "not_installed"
                continue
            matched = re.match(r"^\s+进程 PID=(\d+)\s+uptime=(\S+)", line)
            if matched:
                info["running"] = True
                info["pid"] = int(matched.group(1))
                info["uptime"] = matched.group(2)
                continue
            matched = re.match(r"^\s+\|\s?(.*)$", line)
            if matched:
                info["log_tail"].append(matched.group(1))
                continue
            matched = re.match(r"^\s+(ActiveState|SubState|MainPID|NRestarts)=(\S+)", line)
            if matched:
                info[matched.group(1)] = matched.group(2)
        if info["mode"] == "systemd":
            if info.get("ActiveState") == "active":
                info["running"] = True
            # systemctl show 的 MainPID 是字符串，统一成 int 便于前端比对
            main_pid = info.get("MainPID")
            if main_pid and main_pid.isdigit() and int(main_pid) > 0:
                info["pid"] = int(main_pid)
            else:
                info.pop("MainPID", None)
        return info

    def status(self, target, use_cache=True):
        now = time.time()
        with self.status_lock:
            if use_cache and self.status_cache["data"] is not None \
                    and now - self.status_cache["ts"] < STATUS_CACHE_TTL_S:
                cached = self.status_cache["data"]
                if target in cached:
                    return dict(cached[target])
        code, out, err = self._run(["status", target], timeout=30)
        parsed = self.parse_status(out)
        parsed["exit_code"] = code
        if code != 0:
            parsed["error"] = (err or out).strip()[:300]
        with self.status_lock:
            if self.status_cache["data"] is None:
                self.status_cache["data"] = {}
            self.status_cache["data"][target] = parsed
            self.status_cache["ts"] = time.time()
        return dict(parsed)

    def invalidate_status(self):
        with self.status_lock:
            self.status_cache["data"] = None

    def action(self, target, action):
        if action not in SERVICE_ACTIONS:
            return False, {"error": "不支持的动作 %r" % action}
        with self.action_locks[target]:
            self.invalidate_status()
            code, out, err = self._run([action, target])
        result = {"target": target, "action": action, "exit_code": code,
                  "stdout": out.strip()[-2000:], "stderr": err.strip()[-2000:]}
        if code == 0:
            result["message"] = "%s %s 完成" % (action, target)
        else:
            text = (err or out)
            if "需要 root" in text or "无法提权" in text:
                result["hint"] = ("该目标已由 systemd 托管，提权失败。请在主机上执行 "
                                  "sudo lite3-publish-ctl.sh %s %s，或为 ysc 配置 NOPASSWD 白名单"
                                  % (action, target))
            result["message"] = "%s %s 失败（exit=%d）" % (action, target, code)
        self.invalidate_status()
        return code == 0, result


# ---------------------------------------------------------------- 存储治理（P5）
# 设计来源：m20-ai-detect 的 ADR-008（留存清理）与 ADR-011（数据清空）。
# 全部写成模块级纯函数（只吃参数、不碰 Context），这样不必起服务也能单测。

def retention_of(cfg):
    """取 retention 段，缺键/坏值回落默认。

    向后兼容：老 config 没有 retention 段时照常工作（返回的都是默认值）。
    负值视为无效并忽略（避免"填 -1 变成不清理"这种反直觉行为）。
    """
    out = dict(DEFAULT_RETENTION)
    raw = (cfg or {}).get("retention")
    if not isinstance(raw, dict):
        return out
    for key in DEFAULT_RETENTION:
        if key not in raw:
            continue
        try:
            val = int(raw[key])
        except (TypeError, ValueError):
            continue
        if val < 0:
            continue
        out[key] = val
    return out


def iter_files(root, exts=None, recursive=True, skip_dirs=()):
    """遍历目录 → [(path, size, mtime)]。单文件 stat 失败直接跳过。

    宁可漏统计/漏删，不可让一个坏文件中断整轮清理（aiDetect 同原则）。
    """
    out = []
    if not root or not os.path.isdir(root):
        return out
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for name in filenames:
                if exts and not name.endswith(exts):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                out.append((path, stat.st_size, stat.st_mtime))
        return out
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        if exts and not name.endswith(exts):
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        out.append((path, stat.st_size, stat.st_mtime))
    return out


def _tally(entries):
    return {"files": len(entries), "bytes": sum(e[1] for e in entries)}


def storage_stats(pic_dir, uploads_dir=None, exports_dir=None, log_dir=None):
    """分类占用（只读）。供 UI 与 GET /api/maintenance/storage。

    pics 不含 .trash（两者分开治理：体积上限只约束"在用图片"）。
    三个目录参数可注入，纯粹是为了单测不必碰真实目录。
    """
    uploads_dir = uploads_dir or UPLOAD_DIR
    exports_dir = exports_dir or EXPORT_DIR
    log_dir = log_dir or LOG_DIR
    kinds = {
        "pics": _tally(iter_files(pic_dir, (".jpg",), True, skip_dirs=(".trash",))),
        "trash": _tally(iter_files(os.path.join(pic_dir, ".trash"), (".jpg",))),
        "uploads": _tally(iter_files(uploads_dir, None, False)),
        "exports": _tally(iter_files(exports_dir, None, False)),
        "logs": _tally(iter_files(log_dir, (".log", ".gz"))),
    }
    cache_bytes = 0
    cache_path = os.path.join(exports_dir, TIMING_CACHE_NAME)
    if os.path.isfile(cache_path):
        try:
            cache_bytes = os.path.getsize(cache_path)
        except OSError:
            cache_bytes = 0
    return {"kinds": kinds, "total_bytes": sum(v["bytes"] for v in kinds.values()),
            "timing_cache_bytes": cache_bytes}


def prune_pics(pic_dir, max_mb, keep_days, on_error=None):
    """pic/ 双维度清理：先按年龄、再按总量，**最旧优先**（不含 .trash）。

    entries 已按 mtime 升序，一旦既没超龄也没超量就可以 break——后面的只会更新。
    """
    entries = iter_files(pic_dir, (".jpg",), True, skip_dirs=(".trash",))
    entries.sort(key=lambda e: (e[2], e[0]))
    cutoff = (time.time() - keep_days * 86400.0) if keep_days > 0 else None
    limit = (max_mb * 1024 * 1024) if max_mb > 0 else None
    total = sum(e[1] for e in entries)
    files = gone = 0
    errors = []
    for path, size, mtime in entries:
        if cutoff is not None and mtime < cutoff:
            pass
        elif limit is not None and total > limit:
            pass
        else:
            break
        try:
            os.unlink(path)
        except OSError as exc:
            errors.append("%s: %s" % (os.path.basename(path), exc))
            if on_error:
                on_error(path, exc)
            continue
        files += 1
        gone += size
        total -= size
    return {"files": files, "bytes": gone, "errors": errors}


def prune_trash(pic_dir, keep_days, on_error=None):
    """回收站按年龄清理。keep_days<=0 表示不清理（保留"只进不出"的旧行为）。"""
    if keep_days <= 0:
        return {"files": 0, "bytes": 0, "errors": []}
    cutoff = time.time() - keep_days * 86400.0
    files = gone = 0
    errors = []
    for path, size, mtime in iter_files(os.path.join(pic_dir, ".trash"), (".jpg",)):
        if mtime >= cutoff:
            continue
        try:
            os.unlink(path)
        except OSError as exc:
            errors.append("%s: %s" % (os.path.basename(path), exc))
            if on_error:
                on_error(path, exc)
            continue
        files += 1
        gone += size
    return {"files": files, "bytes": gone, "errors": errors}


def truncate_logs(log_dir, on_error=None):
    """日志**截断**而不是删除。

    console/worker 是长驻进程、持有 fd 追加写：unlink 只会让进程继续往已删
    inode 里写，磁盘一点不释放（直到进程重启）。open(path,"wb") 才是真释放。
    """
    files = gone = 0
    errors = []
    for path, size, _mtime in iter_files(log_dir, (".log",)):
        try:
            with open(path, "wb"):
                pass
        except OSError as exc:
            errors.append("%s: %s" % (os.path.basename(path), exc))
            if on_error:
                on_error(path, exc)
            continue
        files += 1
        gone += size
    return {"files": files, "bytes": gone, "errors": errors, "truncated": True}


def purge_targets(pic_dir, targets, keep_timing_cache=True, on_error=None,
                  uploads_dir=None, exports_dir=None, log_dir=None):
    """一次性整体清空（对齐 ADR-011 的 purge 语义），返回每类 {files,bytes,errors}。

    exports 默认保留 .trt-timing-cache：它是一次性冷启动 26 min 换来的，
    误删的代价远大于它 697 KB 的占用。三个目录参数同样只为单测可注入。
    """
    uploads_dir = uploads_dir or UPLOAD_DIR
    exports_dir = exports_dir or EXPORT_DIR
    log_dir = log_dir or LOG_DIR
    result = {}
    for kind in targets:
        if kind not in PURGE_TARGETS:
            continue
        if kind == "logs":
            result[kind] = truncate_logs(log_dir, on_error=on_error)
            continue
        if kind == "pics":
            entries = iter_files(pic_dir, (".jpg",), True, skip_dirs=(".trash",))
        elif kind == "trash":
            entries = iter_files(os.path.join(pic_dir, ".trash"), (".jpg",))
        elif kind == "uploads":
            entries = iter_files(uploads_dir, None, False)
        else:                                     # exports
            entries = iter_files(exports_dir, None, False)
        files = gone = 0
        errors = []
        for path, size, _mtime in entries:
            name = os.path.basename(path)
            if kind == "exports" and keep_timing_cache and name == TIMING_CACHE_NAME:
                continue
            try:
                os.unlink(path)
            except OSError as exc:
                errors.append("%s: %s" % (name, exc))
                if on_error:
                    on_error(path, exc)
                continue
            files += 1
            gone += size
        result[kind] = {"files": files, "bytes": gone, "errors": errors}
    return result


def worker_looks_alive(state, stale_s=WORKER_STALE_S):
    """从 worker_state.json 判断 worker 是否"看起来还在跑"。

    lite3-publish-ctl.sh 的判活只看 PID 文件（logs/yolo.pid）：worker 若是
    游离拉起的（没走 ctl start），PID 文件不存在 ⇒ ctl 报"未运行"，可进程
    其实活着、还在写 pic/。purge 的"先停服再清理"保护就会整段失效。
    这里用状态文件的新鲜度兜底——它只用于**拒绝**清理，不用于拉起或 kill，
    避免误伤/起出第二个 worker。
    """
    if not isinstance(state, dict):
        return False
    worker = state.get("worker")
    if not isinstance(worker, dict) or not worker.get("alive"):
        return False
    age = state.get("_age_s")
    if isinstance(age, (int, float)):
        return age <= stale_s
    ts = state.get("ts")
    if isinstance(ts, (int, float)):
        return abs(time.time() - ts) <= stale_s
    return False


class StateCollector(object):
    """主机与 console 自身指标（无 psutil，全部读 /proc 与标准库）。"""

    @staticmethod
    def host():
        load1 = load5 = load15 = None
        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as fh:
                parts = fh.read().split()
            load1, load5, load15 = float(parts[0]), float(parts[1]), float(parts[2])
        except (OSError, ValueError, IndexError):
            pass
        mem_avail_mb = None
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        mem_avail_mb = int(line.split()[1]) // 1024
                        break
        except (OSError, ValueError, IndexError):
            pass
        try:
            usage = shutil.disk_usage("/")
            disk_avail_gb = round(usage.free / (1024.0 ** 3), 1)
        except OSError:
            disk_avail_gb = None
        return {"load1": load1, "load5": load5, "load15": load15,
                "mem_avail_mb": mem_avail_mb, "disk_avail_gb": disk_avail_gb}

    @staticmethod
    def worker_state():
        """worker_state.json 是 P2 交付物；P1 不存在时返回 None（前端显示"未接入"）。"""
        if not os.path.exists(WORKER_STATE):
            return None
        try:
            with open(WORKER_STATE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            age = None
            mtime = os.path.getmtime(WORKER_STATE)
            age = round(time.time() - mtime, 1)
            if isinstance(data, dict):
                data["_age_s"] = age
            return data
        except (OSError, ValueError):
            return None

    @staticmethod
    def console_self():
        rss_mb = None
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        rss_mb = int(line.split()[1]) // 1024
                        break
        except (OSError, ValueError, IndexError):
            pass
        return {"version": VERSION, "pid": os.getpid(), "rss_mb": rss_mb,
                "uptime_s": round(time.time() - START_TS, 1)}


START_TS = time.time()


# ---------------------------------------------------------------- HTTP 层

class ConsoleHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "yolo8-console/" + VERSION
    sys_version = ""

    # ---- 基础工具 ----
    def log_message(self, fmt, *args):     # 静默默认访问日志，改走审计
        pass

    def _client_ip(self):
        return self.client_address[0] if self.client_address else "-"

    def _send_json(self, code, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, val in (extra_headers or []):
                self.send_header(key, val)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_body(self, max_bytes=None, timeout=None):
        limit = MAX_BODY_BYTES if max_bytes is None else max_bytes
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        if length > limit:
            return None
        if timeout:
            old = self.connection.gettimeout()
            self.connection.settimeout(timeout)
        try:
            return self.rfile.read(length)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return None
        finally:
            if timeout:
                try:
                    self.connection.settimeout(old)
                except OSError:
                    pass

    def _json_body(self):
        raw = self._read_body()
        if raw is None:
            return None, "请求体过大（上限 %d 字节）" % MAX_BODY_BYTES
        if not raw:
            return {}, None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None, "请求体不是合法 JSON"
        if not isinstance(data, dict):
            return None, "请求体必须是 JSON 对象"
        return data, None

    def _cookie(self, name):
        header = self.headers.get("Cookie") or ""
        for part in header.split(";"):
            if "=" not in part:
                continue
            key, val = part.strip().split("=", 1)
            if key == name:
                return val
        return None

    # ---- 安全判定 ----
    def _authorize(self, need_write):
        """返回 None 表示放行，否则返回 HTTP 状态码（已由调用方转响应）。"""
        ctx = self.server.ctx
        ip = self._client_ip()

        if not ctx.ip_allowed(ip):
            if ctx.reject_throttle.due("cidr_reject", ip):
                ctx.audit.record("cidr_reject", "deny", ip,
                                 {"path": self.path, "allowed": ctx.cfg["console"]["allowed_cidrs"]})
            return 403

        if self.path in ("/healthz", "/api/auth/login", "/api/auth/logout"):
            return None

        if not ctx.sessions.valid(self._cookie(SESSION_COOKIE), ip):
            # 会话缺失/失效也必须留痕（P1-3 G2 发现的原缺口：这里完全不记审计）
            if ctx.reject_throttle.due("auth_reject", ip):
                ctx.audit.record("auth_reject", "deny", ip, {"path": self.path})
            return 401

        if need_write:
            supplied = self.headers.get(TOKEN_HEADER) or ""
            if not ctx.tokens.verify(supplied):
                if ctx.reject_throttle.due("token_reject", ip):
                    ctx.audit.record("token_reject", "deny", ip, {"path": self.path})
                return 401
        return None
    def _audit_write(self, event, result, detail=None):
        self.server.ctx.audit.record(event, result, self._client_ip(), detail)

    # ---- 静态文件 ----
    def _serve_static(self, path):
        if path in ("/", "/index.html"):
            rel = "index.html"
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
        else:
            return self._send_json(404, {"ok": False, "error": "not found"})
        # 防穿越：只允许 STATIC_DIR 内的普通文件
        target = os.path.realpath(os.path.join(STATIC_DIR, rel))
        if not target.startswith(os.path.realpath(STATIC_DIR) + os.sep) \
                or not os.path.isfile(target):
            return self._send_json(404, {"ok": False, "error": "not found"})
        try:
            with open(target, "rb") as fh:
                body = fh.read()
        except OSError:
            return self._send_json(404, {"ok": False, "error": "not found"})
        ctype = "text/html; charset=utf-8" if rel.endswith(".html") else \
                ("application/javascript; charset=utf-8" if rel.endswith(".js") else
                 ("text/css; charset=utf-8" if rel.endswith(".css") else "application/octet-stream"))
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---- 路由 ----
    def do_OPTIONS(self):
        # 跨站预检一律拒绝：写接口靠自定义头 X-Yolo-Token 免疫 CSRF（§6.5）
        self._send_json(403, {"ok": False, "error": "CORS preflight denied"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_DELETE(self):
        self._dispatch("DELETE")            # P3：图片软删除（D2）

    def _dispatch(self, method):
        ctx = self.server.ctx
        ip = self._client_ip()
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        try:
            if not ctx.limiter.allow(ip, path):
                # 登录限流单独给提示语，避免用户以为系统故障
                msg = ("登录过于频繁，请 %.0f 秒后重试" % LOGIN_MIN_INTERVAL_S
                       if path.startswith("/api/auth/login") else "请求过于频繁")
                return self._send_json(429, {"ok": False, "error": msg})

            if path == "/healthz":
                return self._send_json(200, {"ok": True, "version": VERSION,
                                             "ts": now_iso()})

            if path in ("/", "/index.html") or path.startswith("/static/"):
                return self._serve_static(path)

            if not path.startswith("/api/"):
                return self._send_json(404, {"ok": False, "error": "not found"})

            need_write = (method in ("POST", "DELETE")) \
                and not path.startswith("/api/auth/")
            code = self._authorize(need_write)
            if code is not None:
                return self._send_json(code, {"ok": False,
                                              "error": {401: "未授权或凭证无效",
                                                         403: "来源地址不在白名单"}[code]})

            if method == "GET":
                return self._route_get(path, query)
            if method == "DELETE":
                return self._route_delete(path, query)
            return self._route_post(path)

        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:                       # 兜底：绝不让堆栈回到客户端
            ctx.audit.record("internal_error", "error", ip,
                             {"path": path, "err": "%s" % exc})
            log_line("INTERNAL ERROR %s %s: %r" % (method, path, exc))
            try:
                return self._send_json(500, {"ok": False, "error": "内部错误，详见 console.log"})
            except Exception:
                return

    def _route_get(self, path, query):
        ctx = self.server.ctx
        if path == "/api/state":
            return self._send_json(200, {"ok": True, "ts": now_iso(), "state": ctx.snapshot()})
        if path == "/api/config":
            return self._send_json(200, {"ok": True, "config": strip_sensitive(ctx.cfg),
                                         "from_file": ctx.cfg_from_file})
        if path == "/api/service/status":
            target = (query.get("target") or ["all"])[0]
            if target == "all":
                data = {t: ctx.ctl.status(t) for t in SERVICE_TARGETS}
            elif target in SERVICE_TARGETS:
                data = ctx.ctl.status(target)
            else:
                return self._send_json(400, {"ok": False, "error": "target 必须是 yolo/rosbridge/all"})
            return self._send_json(200, {"ok": True, "services": data})
        if path == "/api/logs":
            lines = int((query.get("lines") or ["200"])[0])
            lines = max(1, min(lines, 2000))
            target = (query.get("target") or ["yolo"])[0]
            logfile = os.path.join(LOG_DIR, "yolo-publish.log" if target == "yolo" else "rosbridge.log")
            tail = []
            if os.path.isfile(logfile):
                try:
                    with open(logfile, "rb") as fh:
                        fh.seek(0, os.SEEK_END)
                        size = fh.tell()
                        fh.seek(max(0, size - 256 * 1024))
                        chunk = fh.read().decode("utf-8", "replace")
                    tail = chunk.splitlines()[-lines:]
                except OSError as exc:
                    return self._send_json(200, {"ok": True, "target": target,
                                                 "lines": [], "error": str(exc)})
            return self._send_json(200, {"ok": True, "target": target, "lines": tail})
        # ---- P5：存储治理 ----
        if path == "/api/maintenance/storage":
            return self._get_maintenance_storage()

        if path == "/api/topics":
            return self._send_json(200, dict(self.server.ctx.list_topics(), ok=True))

        # ---- P4：模型（§5.6）----
        if path == "/api/model/info":
            return self._send_json(200, dict(ctx.model_info(), ok=True))
        if path == "/api/model/export/status":
            return self._send_json(200, {"ok": True, "task": ctx.exports.snapshot()})

        # ---- P3：抓拍图片（§5.5/§5.5.1）----
        if path == "/api/pics/dates":
            return self._send_json(200, {"ok": True, "today": today_str(),
                                         "dates": self.server.ctx.pics.dates()})
        if path == "/api/pics/trash":
            return self._send_json(200, {"ok": True,
                                         "items": self.server.ctx.pics.trash_list()})
        if path == "/api/pics/timeline":
            date = (query.get("date") or [today_str()])[0]
            if not PIC_DATE_RE.match(date):
                return self._send_json(400, {"ok": False,
                                             "error": "date 形如 YYYYMMDD"})
            return self._send_json(200, self.server.ctx.pics.timeline(date))
        if path == "/api/pics":
            date = (query.get("date") or [today_str()])[0]
            if not PIC_DATE_RE.match(date):
                return self._send_json(400, {"ok": False,
                                             "error": "date 形如 YYYYMMDD"})
            try:
                page = max(1, int((query.get("page") or ["1"])[0]))
                size = int((query.get("size") or ["24"])[0])
            except ValueError:
                return self._send_json(400, {"ok": False,
                                             "error": "page/size 必须是整数"})
            size = max(1, min(size, 200))
            return self._send_json(200, self.server.ctx.pics.list_pics(date, page, size))
        matched = re.match(r"^/api/pics/(\d{8})/([0-9A-Za-z._-]+)$", path)
        if matched:
            return self._serve_pic(matched.group(1), matched.group(2), query)
        return self._send_json(404, {"ok": False, "error": "not found"})

    def _route_post(self, path):
        ctx = self.server.ctx
        if path == "/api/auth/login":
            body, err = self._json_body()
            if err:
                return self._send_json(400, {"ok": False, "error": err})
            ip = self._client_ip()
            if ctx.backoff.check(ip):
                ctx.audit.record("login_locked", "deny", ip)
                return self._send_json(429, {"ok": False,
                                             "error": "失败次数过多，已锁定 %d 秒" % LOGIN_LOCK_S})
            if ctx.tokens.verify(body.get("token")):
                ctx.backoff.success(ip)
                sid = ctx.sessions.create(ip)
                ctx.audit.record("login", "ok", ip)
                cookie = "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d" % (
                    SESSION_COOKIE, sid, ctx.cfg["console"]["session_ttl_s"])
                return self._send_json(200, {"ok": True, "message": "登录成功"},
                                       extra_headers=[("Set-Cookie", cookie)])
            locked = ctx.backoff.fail(ip)
            ctx.audit.record("login", "deny", ip, {"locked": locked})
            return self._send_json(401, {"ok": False, "error": "token 错误"})

        if path == "/api/auth/logout":
            ctx.sessions.drop(self._cookie(SESSION_COOKIE))
            self._audit_write("logout", "ok")
            return self._send_json(200, {"ok": True, "message": "已退出登录"})

        matched = re.match(r"^/api/service/(start|stop|restart)$", path)
        if matched:
            body, err = self._json_body()
            if err:
                return self._send_json(400, {"ok": False, "error": err})
            action = matched.group(1)
            target = body.get("target")
            if target not in SERVICE_TARGETS:
                return self._send_json(400, {"ok": False,
                                             "error": "target 必须是 yolo 或 rosbridge"})
            ok, result = ctx.ctl.action(target, action)
            self._audit_write("service_%s" % action, "ok" if ok else "fail",
                              {"target": target, "exit_code": result.get("exit_code")})
            return self._send_json(200 if ok else 500, dict(result, ok=ok))

        if path == "/api/config":
            return self._post_config()

        if path == "/api/source/probe":
            return self._post_source_probe()

        if path == "/api/stream/probe":
            return self._post_stream_probe()

        # ---- P4：模型上传 / 导出 / 重载（§5.6）----
        if path == "/api/model/upload":
            return self._post_model_upload()
        if path == "/api/model/export":
            return self._post_model_export()
        if path == "/api/model/reload":
            return self._post_model_reload()

        # ---- P5：存储治理（清空）----
        if path == "/api/maintenance/purge":
            return self._post_maintenance_purge()

        matched = re.match(r"^/api/pics/trash/([0-9A-Za-z._-]+)/restore$", path)
        if matched:
            name = matched.group(1)
            result = self.server.ctx.pics.restore(name)
            if result is None:
                return self._send_json(404, {"ok": False,
                                             "error": "回收站中无此文件"})
            if result == "exists":
                return self._send_json(409, {"ok": False,
                                             "error": "原日期目录已存在同名文件"})
            self._audit_write("pic_restore", "ok", {"name": name})
            return self._send_json(200, {"ok": True, "name": name,
                                         "message": "已还原到原日期目录"})

        return self._send_json(404, {"ok": False, "error": "not found"})

    def _route_delete(self, path, query):
        """P3：软删除抓拍（D2）——os.replace 进 pic/.trash/<date>/。"""
        matched = re.match(r"^/api/pics/(\d{8})/([0-9A-Za-z._-]+)$", path)
        if not matched:
            return self._send_json(404, {"ok": False, "error": "not found"})
        date, name = matched.group(1), matched.group(2)
        result = self.server.ctx.pics.trash(date, name)
        if result is None:
            return self._send_json(404, {"ok": False,
                                         "error": "图片不存在或文件名不合法"})
        if result == "exists":
            return self._send_json(409, {"ok": False,
                                         "error": "回收站已存在同名文件"})
        self._audit_write("pic_delete", "ok", {"date": date, "name": name})
        return self._send_json(200, {"ok": True, "date": date, "name": name,
                                     "message": "已移入回收站（7 天后清理）"})

    def _serve_pic(self, date, name, query):
        """原图 / 缩略图（?thumb=1）。缩略图生成失败时回退原图。"""
        store = self.server.ctx.pics
        want_thumb = (query.get("thumb") or ["0"])[0] in ("1", "true")
        path = None
        if want_thumb:
            path = store.ensure_thumb(date, name)
        if path is None:
            path = store.resolve(date, name)
        if path is None:
            return self._send_json(404, {"ok": False,
                                         "error": "图片不存在或文件名不合法"})
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            return self._send_json(404, {"ok": False, "error": "图片读取失败"})
        try:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _post_config(self):
        """在线改配置（P1.5，计划书 §18）。

        可写范围白名单：source/detect/snapshot/stream/model/pic_dir 六节。
        console 段（绑定/端口/白名单/令牌）改错会把自己锁在门外，仍走手改文件。
        流程：合并 → 校验（不过则 400 且不落盘）→ 轮换备份原子写 → 热替换 ctx
        → needs_restart 判定 → yolo 正在运行则自动重启（约 35s 冷启动）。
        """
        ctx = self.server.ctx
        body, err = self._json_body()
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        patch = body.get("config")
        if not isinstance(patch, dict) or not patch:
            return self._send_json(400, {"ok": False, "error": "config 必须是非空 JSON 对象"})
        unknown = [k for k in patch if k not in WRITABLE_SECTIONS]
        if unknown:
            return self._send_json(400, {"ok": False, "error":
                "不支持的配置节: %s（可在线修改: %s；console 段请手改 config/yolo8.json）"
                % (", ".join(sorted(unknown)), "/".join(WRITABLE_SECTIONS))})

        merged = deep_merge(ctx.cfg, patch)
        merged["version"] = CONFIG_VERSION
        merged["updated_at"] = now_iso()
        try:
            validate_config(merged)
        except ConfigError as exc:
            self._audit_write("config_write", "deny",
                              {"sections": sorted(patch.keys()), "error": "%s" % exc})
            return self._send_json(400, {"ok": False, "error": "校验失败：%s" % exc})

        # P2（§5.9.4 先验后写）：源地址**真的变了**才探测，失败 → 400 且不落盘。
        # 目的：挡掉绝大多数填错（IP/端口/路径/编码不支持），否则 worker 重建后
        # 会陷入"永远重连"，而且这里一旦落盘还会触发自动重启（冷启动 35s）。
        # 手改文件不经过此处——那条路由 worker 的 last_good 回滚兜底。
        old_src = (ctx.cfg or {}).get("source") or {}
        new_src = merged.get("source") or {}
        new_url = new_src.get("rtsp_url") or ""
        if new_src.get("type") == "rtsp" and new_url \
                and new_url != old_src.get("rtsp_url"):
            info = probe_rtsp(new_url, new_src.get("transport") or "udp")
            if not info.get("ok"):
                self._audit_write("config_write", "deny",
                                  {"sections": sorted(patch.keys()),
                                   "error": "source probe failed: %s"
                                            % (info.get("err") or "")})
                return self._send_json(
                    400, {"ok": False, "probe": info,
                          "error": "视频源不可达，已拒绝保存（现有配置不受影响）：%s"
                                   % (info.get("err") or "未知错误")})
        elif new_src.get("type") == "file":
            fp = new_src.get("file_path") or ""
            if fp and not os.path.exists(fp):
                return self._send_json(
                    400, {"ok": False, "error": "回放文件不存在：%s" % fp})

        try:
            backup = backup_and_write(CONFIG_PATH, merged, keep=CONFIG_BACKUPS_KEEP)
        except OSError as exc:
            self._audit_write("config_write", "fail", {"error": "%s" % exc})
            return self._send_json(500, {"ok": False, "error": "写入配置失败: %s" % exc})

        old_cfg = ctx.cfg
        ctx.reload_config(merged, True)
        targets = needs_restart(old_cfg, merged)
        result = {"ok": True,
                  "message": "配置已写入 config/yolo8.json",
                  "changed_sections": sorted(patch.keys()),
                  "needs_restart": targets,
                  "backup": os.path.basename(backup) if backup else None}
        if "yolo" in targets:
            status = ctx.ctl.status("yolo", use_cache=False)
            if status.get("running"):
                ok, action = ctx.ctl.action("yolo", "restart")
                result["restart"] = dict(action, ok=ok, cold_start_s=YOLO_COLD_START_S)
                self._audit_write("config_restart", "ok" if ok else "fail",
                                  {"exit_code": action.get("exit_code")})
            else:
                result["restart"] = {"skipped": True,
                                     "message": "yolo 当前未运行，配置已保存，下次启动生效"}
        self._audit_write("config_write", "ok",
                          {"sections": sorted(patch.keys()), "needs_restart": targets,
                           "backup": os.path.basename(backup) if backup else None})
        return self._send_json(200, result)

    def _post_source_probe(self):
        """保存前预检视频源（ffprobe 探真实流，不只是域名解析）。"""
        body, err = self._json_body()
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        url = (body.get("url") or "").strip()
        transport = body.get("transport") or "udp"
        if transport not in ("udp", "tcp"):
            return self._send_json(400, {"ok": False, "error": "transport 只能是 udp 或 tcp"})
        if not re.match(r"^rtsps?://[^/\s]+/\S*$", url):
            return self._send_json(400, {"ok": False, "error": "url 形如 rtsp://host:port/path"})
        result = probe_rtsp(url, transport)
        self._audit_write("source_probe", "ok" if result.get("reachable") else "fail",
                          {"url": url, "transport": transport})
        return self._send_json(200, dict(result, ok=True, url=url, transport=transport))

    def _post_stream_probe(self):
        """保存前预检 RTMP 推流目标（TCP 连通，不校验鉴权/流名）。"""
        body, err = self._json_body()
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        url = (body.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("rtmp", "rtmps") or not parsed.hostname:
            return self._send_json(400, {"ok": False,
                                         "error": "url 形如 rtmp://host:port/app/stream"})
        port = parsed.port or 1935
        result = probe_tcp(parsed.hostname, port)
        self._audit_write("stream_probe", "ok" if result.get("reachable") else "fail",
                          {"host": parsed.hostname, "port": port})
        return self._send_json(200, dict(result, ok=True, url=url, host=parsed.hostname,
                                         port=port,
                                         note="仅验证 TCP 可达，不校验推流鉴权与流名占用"))

    # ---- P4：模型上传 / 导出 / 重载（§5.6）----

    def _post_model_upload(self):
        """multipart 上传 onnx（字段 onnx，可选 names/names_json）。

        校验四道：体积（≤50 MB / 体 ≤64 MB）→ 扩展名 → 文本魔数 → onnx.load
        （子进程 inspect）。任一道失败都不留残文件。
        """
        ctx = self.server.ctx
        ctype = self.headers.get("Content-Type") or ""
        if not ctype.lower().startswith("multipart/form-data"):
            return self._send_json(400, {"ok": False,
                                         "error": "必须 multipart/form-data（文件字段名 onnx）"})
        raw = self._read_body(MAX_UPLOAD_BODY, UPLOAD_READ_TIMEOUT_S)
        if raw is None:
            self._audit_write("model_upload", "deny", {"reason": "body_too_large"})
            return self._send_json(413, {"ok": False, "error": "请求体超过 %d MB"
                                         % (MAX_UPLOAD_BODY >> 20)})
        parts = parse_multipart(raw, ctype)
        part = parts.get("onnx") or parts.get("file")
        if not part or not part.get("data"):
            return self._send_json(400, {"ok": False,
                                         "error": "缺少 onnx 文件（字段名 onnx）"})
        data = part["data"]
        fname = part.get("filename") or "upload.onnx"
        if len(data) > MAX_UPLOAD_BYTES:
            self._audit_write("model_upload", "deny",
                              {"reason": "file_too_large", "size": len(data)})
            return self._send_json(413, {"ok": False, "error": "onnx 超过 %d MB"
                                         % (MAX_UPLOAD_BYTES >> 20)})
        if len(data) < 64:
            return self._send_json(400, {"ok": False,
                                         "error": "文件过小（%d 字节），不是有效 onnx"
                                                  % len(data)})
        if not fname.lower().endswith(".onnx"):
            return self._send_json(400, {"ok": False,
                                         "error": "只接受 .onnx 文件（当前 %s）" % fname})
        if looks_like_text(data):
            return self._send_json(400, {"ok": False,
                                         "error": "文件内容像纯文本，不是 onnx"
                                                  "（protobuf 魔数校验未通过）"})

        upload_id = uuid.uuid4().hex[:24] + ".onnx"
        path = os.path.join(UPLOAD_DIR, upload_id)
        try:
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            tmp = os.path.join(UPLOAD_DIR, "." + upload_id + ".tmp")
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except OSError as exc:
            return self._send_json(500, {"ok": False, "error": "落盘失败：%s" % exc})

        inspected = run_engine_tool(["--inspect", path], timeout=120)
        if not inspected.get("ok"):
            try:
                os.unlink(path)
            except OSError:
                pass
            self._audit_write("model_upload", "deny",
                              {"reason": "inspect_failed", "file": fname})
            return self._send_json(400, {"ok": False, "error": "onnx 解析失败：%s"
                                                              % inspected.get("error")})

        names = {}
        names_source = inspected.get("names_source")
        warnings = list(inspected.get("warnings") or [])
        names_part = parts.get("names") or parts.get("names_json")
        if names_part and names_part.get("data"):
            try:
                names = normalize_names(json.loads(
                    names_part["data"].decode("utf-8")))
                warnings.extend(validate_names(names, inspected.get("classes")))
                names_source = "upload"
            except (UnicodeDecodeError, ValueError) as exc:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                return self._send_json(400, {"ok": False,
                                             "error": "随包的 names 无效：%s" % exc})
        if not names and inspected.get("names"):
            names = inspected["names"]

        self._audit_write("model_upload", "ok",
                          {"file": fname, "size": len(data),
                           "classes": inspected.get("classes"), "upload_id": upload_id})
        return self._send_json(200, {
            "ok": True, "upload_id": upload_id, "filename": fname,
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "classes": inspected.get("classes"), "imgsz": inspected.get("imgsz"),
            "opset": inspected.get("opset"), "names": names,
            "names_source": names_source, "warnings": warnings,
            "inputs": inspected.get("inputs"), "outputs": inspected.get("outputs"),
        })

    def _post_model_export(self):
        """启动异步导出（单任务）：upload_id + names → exports/<name>.engine。"""
        ctx = self.server.ctx
        body, err = self._json_body()
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        upload_id = (body.get("upload_id") or "").strip()
        if not UPLOAD_NAME_RE.match(upload_id):
            return self._send_json(400, {"ok": False,
                                         "error": "upload_id 不合法（请先上传 onnx）"})
        onnx_path = os.path.join(UPLOAD_DIR, upload_id)
        if not os.path.isfile(onnx_path):
            return self._send_json(404, {"ok": False,
                                         "error": "上传文件不存在（可能已被清理），请重新上传"})
        try:
            workspace = int(body.get("workspace_mb") or 1024)
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False, "error": "workspace_mb 必须是整数"})
        workspace = max(128, min(1024, workspace))
        half = bool(body.get("half", True))
        try:
            opt_level = int(body.get("opt_level") or 2)
        except (TypeError, ValueError):
            return self._send_json(400, {"ok": False, "error": "opt_level 必须是整数"})
        opt_level = max(0, min(3, opt_level))

        inspected = run_engine_tool(["--inspect", onnx_path], timeout=120)
        if not inspected.get("ok"):
            return self._send_json(400, {"ok": False, "error": "onnx 无法解析：%s"
                                                              % inspected.get("error")})
        classes = inspected.get("classes")
        try:
            names = normalize_names(body.get("names")) if body.get("names") \
                else (inspected.get("names") or {})
            warnings = list(inspected.get("warnings") or [])
            warnings.extend(validate_names(names, classes))
        except ValueError as exc:
            return self._send_json(400, {"ok": False, "error": "类别清单无效：%s" % exc})

        target = (body.get("target") or "").strip()
        if target:
            try:
                rel = sanitize_engine_rel(target)
            except ValueError as exc:
                return self._send_json(400, {"ok": False, "error": "%s" % exc})
            if "/" not in rel:
                rel = "exports/" + rel
        else:
            stem = os.path.splitext(upload_id)[0][:8]
            rel = "exports/yolov8n-%s-%s.engine" % (
                stem, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))

        abs_out = os.path.join(MODEL_DIR, rel)
        if os.path.exists(abs_out):        # 同名：旧文件留 .bak-<ts>（§5.6.4）
            bak = abs_out + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            try:
                os.replace(abs_out, bak)
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": "备份旧 engine 失败：%s" % exc})

        ok, why = ctx.exports.start(upload_id, onnx_path, names, rel,
                                    workspace, half, opt_level)
        if not ok:
            self._audit_write("model_export", "deny", {"reason": why})
            return self._send_json(409, {"ok": False, "error": why})
        self._audit_write("model_export", "ok",
                          {"upload_id": upload_id, "target": rel,
                           "classes": classes, "workspace_mb": workspace,
                           "half": half})
        return self._send_json(202, {"ok": True, "target": rel,
                                     "classes": classes,
                                     "names_count": len(names),
                                     "workspace_mb": workspace, "half": half,
                                     "opt_level": opt_level,
                                     "warnings": warnings,
                                     "message": "导出已开始（单任务，预计 1~6 分钟）；"
                                                "轮询 /api/model/export/status"})

    def _post_model_reload(self):
        """写 config model.engine + pending_reload=true；worker 在帧边界重建（§5.6.4）。"""
        ctx = self.server.ctx
        body, err = self._json_body()
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        raw = body.get("engine") or ((ctx.cfg.get("model") or {}).get("engine") or "")
        try:
            rel = sanitize_engine_rel(raw)
        except ValueError as exc:
            return self._send_json(400, {"ok": False, "error": "%s" % exc})
        abs_path = os.path.join(MODEL_DIR, rel)
        if not os.path.isfile(abs_path):
            return self._send_json(404, {"ok": False, "error": "engine 不存在：%s" % rel})
        meta, meta_err = read_engine_meta(abs_path)
        if meta is None:
            return self._send_json(400, {"ok": False,
                                         "error": "engine 头不合法，拒绝启用：%s" % meta_err})

        merged = deep_merge(ctx.cfg, {"model": {
            "engine": "../model/" + rel, "pending_reload": True}})
        merged["version"] = CONFIG_VERSION
        merged["updated_at"] = now_iso()
        try:
            validate_config(merged)
        except ConfigError as exc:
            return self._send_json(400, {"ok": False, "error": "校验失败：%s" % exc})
        try:
            backup = backup_and_write(CONFIG_PATH, merged, keep=CONFIG_BACKUPS_KEEP)
        except OSError as exc:
            self._audit_write("model_reload", "fail", {"error": "%s" % exc})
            return self._send_json(500, {"ok": False, "error": "写入配置失败：%s" % exc})
        ctx.reload_config(merged, True)

        status = ctx.ctl.status("yolo", use_cache=False)
        running = bool(status.get("running"))
        self._audit_write("model_reload", "ok",
                          {"engine": rel, "names": len(meta.get("names") or {}),
                           "running": running,
                           "backup": os.path.basename(backup) if backup else None})
        return self._send_json(200, {
            "ok": True, "engine": rel, "config_engine": "../model/" + rel,
            "pending_reload": True, "worker_running": running,
            "names_count": len(meta.get("names") or {}),
            "imgsz": meta.get("imgsz"), "task": meta.get("task"),
            "backup": os.path.basename(backup) if backup else None,
            "message": ("已写入配置，worker 将在下一帧重建模型（丢帧 2~5s）"
                        if running else
                        "yolo 当前未运行：配置已保存，下次启动加载该 engine"),
        })


    # ---------------------------------------------------------------- P5 存储治理
    def _get_maintenance_storage(self):
        """P5：分类占用 + 当前留存策略 + 上次清理结果（只读）。"""
        ctx = self.server.ctx
        stats = ctx.storage_cached()
        cache_kb = stats["timing_cache_bytes"] // 1024
        return self._send_json(200, {
            "ok": True, "storage": stats,
            "retention": retention_of(ctx.cfg),
            "prune_state": ctx.prune_state,
            "purge_targets": list(PURGE_TARGETS),
            "timing_cache_note": (
                "计时缓存 %d KB：purge 默认保留，误删后下次导出会退回 26 min 冷启动" % cache_kb
                if cache_kb else "暂无计时缓存（首次导出后会生成）"),
        })

    def _post_maintenance_purge(self):
        """P5：一次性清空（对齐 aiDetect ADR-011 的 purge 语义）。

        三条铁律：
          1. 目标走白名单，值域校验不过就 400，一个文件都不动；
          2. 涉及 pics/logs 时——yolo 原本在跑：stop → 清 → start 恢复原状；
             原本没跑：绝不动服务（worker 启停归用户掌握）；
             状态无法确认（mode=unknown）：不碰服务直接清；
          3. 停止失败立即中止，此时尚未删除任何文件。
        """
        ctx = self.server.ctx
        body, err = self._json_body()
        if err:
            return self._send_json(400, {"ok": False, "error": err})
        raw = body.get("targets")
        if not isinstance(raw, list) or not raw:
            return self._send_json(400, {"ok": False,
                                         "error": "targets 必须是非空数组"})
        targets = []
        for item in raw:
            if item in PURGE_TARGETS and item not in targets:
                targets.append(item)
        if not targets:
            return self._send_json(400, {"ok": False,
                                         "error": "targets 只能包含 %s"
                                                  % "/".join(PURGE_TARGETS)})
        keep_cache = body.get("keep_timing_cache", True)
        if not isinstance(keep_cache, bool):
            return self._send_json(400, {"ok": False,
                                         "error": "keep_timing_cache 必须是布尔值"})

        running = None
        if set(targets) & {"pics", "logs"}:
            status = ctx.ctl.status("yolo", use_cache=False) or {}
            running = None if status.get("mode") == "unknown" \
                else bool(status.get("running"))
            if running is False:
                # ctl 说没跑，但状态文件很新鲜 ⇒ 有个不受 ctl 管理的 worker 正在
                # 写 pic/。此时既不能"当作没服务直接清"，也不能叫 ctl 去 start
                # （会起出第二个 worker），只能拒绝并提示先把管理权归一。
                state = StateCollector.worker_state() or {}
                if worker_looks_alive(state):
                    pid = (state.get("worker") or {}).get("pid")
                    self._audit_write("maintenance_purge", "reject", {
                        "targets": targets, "reason": "unmanaged_worker",
                        "worker_pid": pid})
                    return self._send_json(409, {
                        "ok": False,
                        "error": "检测到 worker 可能仍在运行（PID %s），但 ctl 没有它的记录："
                                 "请先在主机执行 deploy/lite3-publish-ctl.sh stop yolo"
                                 "（或 start yolo 补上 PID 文件）后重试，"
                                 "避免 worker 正在写图时被清空。" % (pid,)})
        stopped = False
        if running:
            ok, res = ctx.ctl.action("yolo", "stop")
            if not ok:
                self._audit_write("maintenance_purge", "abort",
                                  {"targets": targets, "reason": "stop_failed"})
                return self._send_json(500, {
                    "ok": False,
                    "error": "停止 yolo 失败，未清任何数据：%s"
                             % (res.get("message") or res.get("error"))})
            stopped = True
        try:
            result = purge_targets(
                ctx.pic_dir(), targets, keep_cache,
                on_error=lambda p, e: log_line("PURGE 删除失败 %s: %s" % (p, e)))
        finally:
            if stopped:
                ctx.ctl.action("yolo", "start")
        ctx.storage_cached(force=True)
        freed = sum(v["bytes"] for v in result.values())
        self._audit_write("maintenance_purge", "ok",
                          {"targets": targets, "keep_timing_cache": keep_cache,
                           "freed_bytes": freed, "service_restarted": stopped})
        return self._send_json(200, {
            "ok": True, "result": result, "freed_bytes": freed,
            "service_restarted": stopped,
            "message": "已释放 %.1f MB%s" % (
                freed / 1048576.0, "，yolo 已自动恢复" if stopped
                else ("（yolo 未运行，未做启停）" if running is False else "")),
        })


# ---------------------------------------------------------------- 服务容器

class ConsoleContext(object):
    def __init__(self, cfg, cfg_from_file):
        self.cfg = cfg
        self.cfg_from_file = cfg_from_file
        self.tokens = TokenManager(cfg["console"]["token"])
        self.sessions = SessionStore(cfg["console"]["session_ttl_s"])
        self.backoff = LoginBackoff()
        self.limiter = RateLimiter()
        self.reject_throttle = RejectThrottle(REJECT_WINDOW_S)
        self.audit = AuditLog(AUDIT_LOG)
        self.ctl = ServiceCtl(CTL_SCRIPT)
        self.pics = PicStore(self.pic_dir)     # P3：抓拍图片（pic_dir 现取）
        self.exports = ExportManager()         # P4：模型导出任务（单任务队列）
        # P5：存储治理。清理放在 console 而不是 worker —— worker 不自启是既定设计，
        # 只有 console 由 systemd 常驻，放它才不会"停了推理就没人清理"。
        self.prune_state = {"last_ts": None, "last": None, "error": None}
        self._storage_cache = {"ts": 0.0, "data": None}
        self._start_prune_worker()
        self._networks = [ipaddress.ip_network(c, strict=False)
                          for c in cfg["console"]["allowed_cidrs"]]
        self._start_reject_flusher()

    def pic_dir(self):
        """抓拍根目录。config 的 pic_dir 相对 src/（与 worker 同一约定）；
        在线改 pic_dir 后此处现取生效（浏览侧无需重启）。"""
        raw = (self.cfg or {}).get("pic_dir") or "../pic"
        if not os.path.isabs(raw):
            raw = os.path.normpath(os.path.join(APP_DIR, "src", raw))
        return raw

    def _start_reject_flusher(self):
        """把被抑制的拒绝事件按窗口汇总补进审计日志（daemon 线程，随进程退出）。"""

        def loop():
            while True:
                time.sleep(REJECT_WINDOW_S)
                try:
                    for event, ip, suppressed in self.reject_throttle.drain():
                        self.audit.record(event, "deny", ip,
                                          {"suppressed": suppressed,
                                           "window_s": REJECT_WINDOW_S})
                except Exception as exc:               # noqa: BLE001  汇总失败不能拖垮线程
                    log_line("REJECT FLUSHER ERROR: %r" % exc)

        threading.Thread(target=loop, name="reject-flusher", daemon=True).start()

    def storage_cached(self, force=False):
        """分类占用（30 s 缓存）。UI 会轮询，不能每次都 walk 整个 pic/ 目录。"""
        now = time.time()
        if not force and self._storage_cache["data"] is not None \
                and now - self._storage_cache["ts"] < STORAGE_CACHE_S:
            return self._storage_cache["data"]
        data = storage_stats(self.pic_dir())
        self._storage_cache = {"ts": now, "data": data}
        return data

    def _start_prune_worker(self):
        """P5：周期清理 pic/ 与回收站（对齐 aiDetect ADR-008 的 10 分钟粒度）。

        间隔每次现取，改 config 的 retention.prune_interval_s 后下一轮生效，无需重启。
        """
        def loop():
            while True:
                interval = retention_of(self.cfg)["prune_interval_s"]
                time.sleep(max(60, interval))       # 60s 下限，防止配 0 变忙等
                try:
                    self.run_prune()
                except Exception as exc:            # noqa: BLE001  清理失败不能拖垮 console
                    self.prune_state["error"] = "%s: %s" % (type(exc).__name__, exc)
                    log_line("PRUNE ERROR: %r" % exc)

        threading.Thread(target=loop, name="prune-worker", daemon=True).start()

    def run_prune(self):
        """执行一次双维度清理，结果记入 prune_state 供 UI 展示。"""
        conf = retention_of(self.cfg)
        root = self.pic_dir()

        def note(path, exc):
            log_line("PRUNE 删除失败 %s: %s" % (path, exc))

        result = {
            "pics": prune_pics(root, conf["pic_max_mb"], conf["pic_keep_days"],
                               on_error=note),
            "trash": prune_trash(root, conf["trash_keep_days"], on_error=note),
        }
        self.prune_state = {"last_ts": now_iso(), "last": result, "error": None}
        total = sum(v["bytes"] for v in result.values())
        if total:
            log_line("PRUNE 完成：回收 %.1f MB（pics %d 个 / trash %d 个）"
                     % (total / 1048576.0, result["pics"]["files"],
                        result["trash"]["files"]))
        return result

    def ip_allowed(self, ip):
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self._networks)

    def reload_config(self, cfg, from_file=None):
        """配置热替换（POST /api/config 写入成功后调用）。

        会话表不动：console 段不在可写范围，sid 与令牌都不变，已登录用户无感。
        只刷新 cfg 引用与派生状态（令牌管理器、白名单网段）。
        """
        self.cfg = cfg
        if from_file is not None:
            self.cfg_from_file = from_file
        self.tokens = TokenManager(cfg["console"]["token"])
        self._networks = [ipaddress.ip_network(c, strict=False)
                          for c in cfg["console"]["allowed_cidrs"]]

    def list_topics(self):
        """ROS2 话题清单 + rosbridge 连接串（GET /api/topics）。"""
        port = read_env_port("ROSBRIDGE_PORT", ROSBRIDGE_PORT_DEFAULT)
        ip = lan_ip()
        rb = self.ctl.status("rosbridge")
        base = {"ws_url": "ws://%s:%d/" % (ip or "<103IP>", port),
                "rosbridge_port": port, "lan_ip": ip,
                "rosbridge_running": bool(rb.get("running")),
                "topics": []}
        cmd = "source %s 2>/dev/null; python3 -u %s topic list -t" % (ROS_SETUP, ROS2_BIN)
        try:
            proc = subprocess.run(["bash", "-c", cmd], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=TOPICS_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            base["error"] = "ros2 topic list 超时（%gs）" % TOPICS_TIMEOUT_S
            return base
        except OSError as exc:
            base["error"] = "无法执行 ros2: %s" % exc
            return base
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            base["error"] = (proc.stderr.decode("utf-8", "replace") or out).strip()[-300:]
            return base
        for line in out.splitlines():
            matched = re.match(r"^(/\S+)\s+\[([^\]]+)\]\s*$", line.strip())
            if matched:
                base["topics"].append({"name": matched.group(1), "type": matched.group(2)})
        return base

    def snapshot(self):
        return {
            "console": dict(StateCollector.console_self(),
                            bind=self.cfg["console"]["bind"],
                            port=self.cfg["console"]["port"],
                            sessions=self.sessions.count(),
                            allowed_cidrs=self.cfg["console"]["allowed_cidrs"]),
            "host": StateCollector.host(),
            "services": {t: self.ctl.status(t) for t in SERVICE_TARGETS},
            "worker": StateCollector.worker_state(),
            "config_from_file": self.cfg_from_file,
            # P4：导出任务态（内存态，1s 轮询零 IO；engine 详情走 /api/model/info）
            "model_export": self.exports.snapshot(),
        }

    # ---- P4：模型信息（GET /api/model/info）----
    @staticmethod
    def _scan_dir(path, name_re):
        out = []
        try:
            names = os.listdir(path)
        except OSError:
            return out
        for name in names:
            if name.startswith(".") or not name_re.match(name):
                continue
            full = os.path.join(path, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            out.append({"name": name, "size": st.st_size,
                        "mtime": datetime.datetime.fromtimestamp(
                            st.st_mtime).isoformat(timespec="seconds")})
        out.sort(key=lambda item: item["mtime"], reverse=True)
        return out

    def model_info(self):
        raw = (self.cfg.get("model") or {}).get("engine") or ""
        try:
            rel = sanitize_engine_rel(raw)
        except ValueError:
            rel = sanitize_engine_rel(None)
        abs_path = os.path.join(MODEL_DIR, rel)
        engine = {"config_engine": raw, "rel": rel, "abs": abs_path,
                  "exists": os.path.isfile(abs_path)}
        if engine["exists"]:
            try:
                st = os.stat(abs_path)
                engine["size"] = st.st_size
                engine["mtime"] = datetime.datetime.fromtimestamp(
                    st.st_mtime).isoformat(timespec="seconds")
            except OSError:
                pass
            meta, err = read_engine_meta(abs_path)
            if meta is None:
                engine["meta_error"] = err
            else:
                engine.update({"names_count": len(meta.get("names") or {}),
                               "imgsz": meta.get("imgsz"),
                               "stride": meta.get("stride"),
                               "task": meta.get("task"),
                               "plan_len": meta.get("_plan_len"),
                               "description": meta.get("description")})
        exports = self._scan_dir(EXPORT_DIR, ENGINE_NAME_RE)
        for item in exports:
            item["rel"] = "exports/" + item["name"]
            meta, err = read_engine_meta(os.path.join(EXPORT_DIR, item["name"]))
            item["names_count"] = len(meta.get("names") or {}) if meta else None
            item["meta_error"] = err
        worker_state = StateCollector.worker_state() or {}
        return {"engine": engine,
                "uploads": self._scan_dir(UPLOAD_DIR, UPLOAD_NAME_RE),
                "exports": exports,
                "export": self.exports.snapshot(),
                "worker_model": worker_state.get("model"),
                "limits": {"max_upload_mb": MAX_UPLOAD_BYTES >> 20,
                           "max_body_mb": MAX_UPLOAD_BODY >> 20,
                           "export_timeout_s": EXPORT_TIMEOUT_S}}


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, ctx):
        self.ctx = ctx
        ThreadingHTTPServer.__init__(self, addr, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lite3 yolo8 web console")
    parser.add_argument("--config", default=CONFIG_PATH, help="配置文件路径")
    parser.add_argument("--bind", default=None, help="覆盖配置中的监听地址")
    parser.add_argument("--port", type=int, default=None, help="覆盖配置中的端口")
    parser.add_argument("--check", action="store_true", help="只做配置校验后退出")
    args = parser.parse_args(argv)

    try:
        cfg, from_file = load_config(args.config)
    except ConfigError as exc:
        log_line("配置加载失败：%s" % exc)
        return 2

    if args.bind:
        cfg["console"]["bind"] = args.bind
    if args.port:
        cfg["console"]["port"] = args.port
    try:
        validate_config(cfg)
    except ConfigError as exc:
        log_line("配置校验失败：%s" % exc)
        return 2

    if args.check:
        log_line("配置校验通过（from_file=%s）" % from_file)
        return 0

    ctx = ConsoleContext(cfg, from_file)
    bind, port = cfg["console"]["bind"], cfg["console"]["port"]
    server = ConsoleServer((bind, port), ConsoleHandler, ctx)
    log_line("console %s 启动于 %s:%d（访问令牌取 console.token%s，审计 %s，配置来源 %s）"
             % (VERSION, bind, port,
                "，当前为弱默认值，建议改强" if cfg["console"]["token"] == DEFAULT_TOKEN else "",
                AUDIT_LOG,
                args.config if from_file else "默认值（配置文件缺失）"))
    if bind == "0.0.0.0":
        log_line("监听 0.0.0.0：来源白名单 %s 之外的访问将被 403 拒绝"
                 % ",".join(cfg["console"]["allowed_cidrs"]))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log_line("收到 KeyboardInterrupt，退出")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
