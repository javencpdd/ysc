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
#: 成功抓帧缓存（秒）：同一相机在该窗口内的重复请求直接复用。
CACHE_TTL = 1.5
#: 失败缓存（秒）：防止多客户端连击 ffmpeg 反复拉起。
CACHE_TTL_ERROR = 3.0
#: 环形帧"新鲜"窗口 = max(5 s, FRESH_FACTOR / fps)；fps=1 时约 5 s。
FRESH_FACTOR = 4.0

Grabber = Callable[[Camera, Config], Optional[bytes]]

#: cam.name -> (monotonic 时刻, jpeg 或 None, "live"/"error")
_cache: Dict[str, Tuple[float, Optional[bytes], str]] = {}
_lock = threading.Lock()


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


def _pick_cam(cfg: Config, name: Optional[str]) -> Tuple[Optional[Camera], Optional[str]]:
    if not cfg.cameras:
        return None, "没有启用任何相机（在「相机与采集」里勾选前视/后视后保存）"
    if not name:
        return cfg.cameras[0], None
    for cam in cfg.cameras:
        if cam.name == name:
            return cam, None
    return None, "未知相机 %s（可用：%s）" % (name, "、".join(c.name for c in cfg.cameras))


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
) -> Optional[bytes]:
    """带短缓存的即时抓帧（成功 1.5 s / 失败 3 s），并发请求串行化防连击。

    注意缓存时间戳用**抓帧完成时刻**：单次握手本身要 2~4 s，若用开始时刻计时，
    等第一个请求回来时 TTL 已耗尽，多标签页/连点刷新永远命中不了缓存。
    """
    key = cam.name
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            ts, data, _tag = hit
            ttl = CACHE_TTL if data else CACHE_TTL_ERROR
            if clock() - ts < ttl:
                return data
        data = grabber(cam, cfg)
        _cache[key] = (clock(), data, "live" if data else "error")
        return data


def _pack(
    cam: Camera, jpeg: bytes, source: str, age_s: float, frame: Optional[str]
) -> Dict[str, Any]:
    return {
        "ok": True,
        "cam": cam.name,
        "src": cam.src,
        "source": source,
        "age_s": round(max(0.0, age_s), 1),
        "frame": frame,
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
    或 ``{"ok": False, error[, bad_request]}``。
    """
    cam, err = _pick_cam(cfg, cam_name)
    if cam is None:
        return {"ok": False, "error": err, "bad_request": True}
    clock = now or time.monotonic
    wall = time.time()
    grabber = grabber or _grab_jpeg

    latest = _ring_latest(cfg, cam)
    if latest is not None:
        age = wall - latest[1]
        if age <= _fresh_window(cfg):
            jpeg = _read_file(latest[0])
            if jpeg:
                return _pack(cam, jpeg, "ring", age, os.path.basename(latest[0]))

    # 环形帧过期/缺失 → 即时抓帧（带缓存）
    jpeg_live = _cached_grab(cam, cfg, grabber, clock)
    if jpeg_live:
        return _pack(cam, jpeg_live, "live", 0.0, None)

    # 兜底：过期环形帧（如实标注 age，UI 显示"已定格"）
    if latest is not None:
        jpeg = _read_file(latest[0])
        if jpeg:
            age = wall - latest[1]
            return _pack(cam, jpeg, "stale", age, os.path.basename(latest[0]))

    return {"ok": False, "error": "抓帧失败：源不可达且无历史帧（%s）" % cam.src}
