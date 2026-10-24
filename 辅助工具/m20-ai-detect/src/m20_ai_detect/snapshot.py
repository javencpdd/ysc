"""「相机画面」单帧快照（ADR-012）。

给控制台提供"这台相机现在看到什么"，来源优先级（快且准 → 慢但独立）：
  1. ``ring``  —— raw/<cam>/ 最新帧：采样器运行中帧就落在这里，零额外开销，
     而且**正是检测器刚处理过的画面**；
  2. ``live``  —— ffmpeg 单次抓帧：采集未运行（或环形帧过期）时从同一路 RTSP
     即时抓取，带短缓存防多客户端连击；
  3. ``stale`` —— 抓帧失败时兜底返回环形帧，如实标注 ``age_s``，UI 显示"已定格"。

设计约束：本模块不向上抛异常，失败一律 ``{"ok": False, "error": ...}``；
配置类问题（未知相机/未启用相机）附 ``bad_request: True`` 供调用方映射 400，
其余（抓帧失败）由调用方映射 502——一张图抓不到不允许影响控制台其他功能。
"""
from __future__ import annotations

import base64
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from .capture import build_snapshot_cmd
from .config import Camera, Config
from .store import Store

#: 单次抓帧超时（秒）。RTSP 握手实测 1.6~2.0 s，留足余量。
GRAB_TIMEOUT = 8.0
#: 成功抓帧缓存（秒）：只为合并"同一时刻的并发请求"（多标签页/连点）。
#: 2026-10-18 由 1.5 收到 0.6 —— 1.5s 会让 1s 轮询有一半轮次复用旧图（看着像"没刷新"）。
CACHE_TTL = 0.6
#: 失败缓存（秒）：防止多客户端连击 ffmpeg 反复拉起。
CACHE_TTL_ERROR = 3.0
#: 环形帧"新鲜"窗口 = max(5 s, FRESH_FACTOR / fps)；fps=1 时约 5 s。
FRESH_FACTOR = 4.0

Grabber = Callable[[Camera, Config], Optional[bytes]]

#: cam.name -> (monotonic 时刻[TTL 用], wall 时刻[展示用], jpeg 或 None, "live"/"error")
_cache: Dict[str, Tuple[float, float, Optional[bytes], str]] = {}
#: ★按相机分锁（2026-10-18 修）：原先一把全局锁把**整个抓帧过程**包住，导致
#: 多相机 live 抓帧串行（前台 2s + 后台 2s），两路画面错开约 2s、且总耗时翻倍。
#: 现在"同一路"仍串行（防连击/防重复拉起 ffmpeg），"不同路"可并行。
_grab_locks: Dict[str, threading.Lock] = {}
_grab_locks_guard = threading.Lock()
#: 仅保护 _cache 字典本身（微秒级），不与抓帧耗时可交叉。
_cache_lock = threading.Lock()


def _cam_lock(key: str) -> threading.Lock:
    with _grab_locks_guard:
        lk = _grab_locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _grab_locks[key] = lk
        return lk


def _grab_jpeg(cam: Camera, cfg: Config) -> Optional[bytes]:
    """ffmpeg 单次抓一帧；任何失败都返回 None（不抛异常）。"""
    try:
        proc = subprocess.run(
            build_snapshot_cmd(cam, cfg),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GRAB_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout or b""
    if proc.returncode != 0 or len(out) < 1024 or not out.startswith(b"\xff\xd8"):
        return None
    return out


def _fresh_window(cfg: Config) -> float:
    return max(5.0, FRESH_FACTOR / max(cfg.fps, 0.2))


def _pick_cam(
    cfg: Config, name: Optional[str]
) -> Tuple[Optional[Camera], str, str, Dict[str, Any]]:
    """按名字取相机；失败返回 (None, 错误文案, code, 文案参数)。

    ``code`` 供 webconsole 做中英映射（ADR-013）；``error`` 保留中文原文，
    供 CLI / 其它调用方与单测使用。
    """
    if not cfg.enabled_cameras:
        return None, "没有启用任何相机（在「相机与采集」里勾选前视/后视后保存）", "no_cameras", {}
    if not name:
        return cfg.enabled_cameras[0], "", "", {}
    for cam in cfg.enabled_cameras:
        if cam.name == name:
            return cam, "", "", {}
    names = [c.name for c in cfg.enabled_cameras]
    return (
        None,
        "未知相机 %s（可用：%s）" % (name, "、".join(names)),
        "unknown_cam",
        {"cam": name, "cams": names},  # cams 给 list，由调用方按语言拼分隔符
    )


def _ring_latest(cfg: Config, cam: Camera) -> Optional[Tuple[str, float]]:
    """raw/<cam>/ 里最新的 .jpg：返回 (路径, mtime)；目录不存在或为空返回 None。"""
    root = Store(cfg).raw_for(cam.name)
    best: Optional[Tuple[str, float]] = None
    try:
        with os.scandir(root) as entries:
            for ent in entries:
                if not ent.name.lower().endswith(".jpg"):
                    continue
                try:
                    mtime = ent.stat().st_mtime
                except OSError:
                    continue
                if best is None or mtime > best[1]:
                    best = (ent.path, mtime)
    except OSError:
        return None
    return best


def _read_file(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _cached_grab(
    cam: Camera,
    cfg: Config,
    grabber: Grabber,
    clock: Callable[[], float],
) -> Optional[Tuple[bytes, float]]:
    """带短缓存的即时抓帧；返回 ``(jpeg, 抓帧完成时刻[wall])``，失败返回 None。

    并发请求串行化：**按相机**加锁（不同相机可并行，多相机画面才可能同步）。
    注意 TTL 时间戳用**抓帧完成时刻**：单次握手本身要 2~4 s，若用开始时刻计时，
    等第一个请求回来时 TTL 已耗尽，多标签页/连点刷新永远命中不了缓存。

    ⚠️ 展示用的 ``ts`` 必须是"这张图真正被取到的时刻"（wall），不是本次响应的
    打包时刻 —— 否则缓存命中时 ts 会变，界面看起来像"两路不同步/一直在换图"。
    """
    key = cam.name
    with _cam_lock(key):          # 只锁这一路：不同相机可同时抓帧
        with _cache_lock:
            hit = _cache.get(key)
        if hit is not None:
            mono_ts, wall_ts, data, _tag = hit
            ttl = CACHE_TTL if data else CACHE_TTL_ERROR
            if clock() - mono_ts < ttl:
                return (data, wall_ts) if data else None
        data = grabber(cam, cfg)
        wall_now = time.time()
        with _cache_lock:
            _cache[key] = (clock(), wall_now, data, "live" if data else "error")
        return (data, wall_now) if data else None


def _pack(
    cam: Camera,
    jpeg: bytes,
    source: str,
    age_s: float,
    frame: Optional[str],
    ts: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "cam": cam.name,
        "src": cam.src,
        # 源类型（rtsp / rtmp / device / file / http…），由 uri scheme 决定（ADR-016）。
        # 控制台据此显示"这是一路什么源"，用户不必自己从 URL 猜。
        "type": cam.type,
        "source": source,
        "age_s": round(max(0.0, age_s), 1),
        "frame": frame,
        # 这张图**真正取到的时刻**（ring=帧文件 mtime；live=抓帧完成时刻）。
        # 多相机同时刷新时，前端按此显示时间戳：两路 ts 接近 = 真同步。
        "ts": round(ts if ts is not None else time.time(), 3),
        "image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
    }


def snapshot_frame(
    cfg: Config,
    cam_name: Optional[str] = None,
    grabber: Optional[Grabber] = None,
    now: Optional[Callable[[], float]] = None,
) -> Dict[str, Any]:
    """取一帧「相机画面」（``grabber`` / ``now`` 可注入，测试用）。

    返回 ``{"ok": True, cam, src, source, age_s, frame, image}``
    或 ``{"ok": False, error, bad_request, code[, cam/cams/src]}``
    （``code`` 供 webconsole 做中英映射，ADR-013）。
    """
    cam, err, code, params = _pick_cam(cfg, cam_name)
    if cam is None:
        return {"ok": False, "error": err, "bad_request": True, "code": code, **params}
    clock = now or time.monotonic
    wall = time.time()
    grabber = grabber or _grab_jpeg

    latest = _ring_latest(cfg, cam)
    if latest is not None:
        age = wall - latest[1]
        if age <= _fresh_window(cfg):
            jpeg = _read_file(latest[0])
            if jpeg:
                return _pack(cam, jpeg, "ring", age, os.path.basename(latest[0]), ts=latest[1])

    # 环形帧过期/缺失 → 即时抓帧（带缓存）
    live = _cached_grab(cam, cfg, grabber, clock)
    if live:
        jpeg_live, grabbed_at = live
        return _pack(cam, jpeg_live, "live", 0.0, None, ts=grabbed_at)

    # 兜底：过期环形帧（如实标注 age，UI 显示"已定格"）
    if latest is not None:
        jpeg = _read_file(latest[0])
        if jpeg:
            age = wall - latest[1]
            return _pack(cam, jpeg, "stale", age, os.path.basename(latest[0]), ts=latest[1])

    return {
        "ok": False,
        "error": "抓帧失败：源不可达且无历史帧（%s）" % cam.src,
        "code": "grab_failed",
        "src": cam.src,
    }
