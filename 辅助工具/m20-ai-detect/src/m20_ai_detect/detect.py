"""与 AI 识别服务的 HTTP 交互（只用标准库 urllib）。

契约要点（2026-10-14 实测 + /openapi.json）：
  * ``POST /api/v1/tasks/{capability_id}`` multipart 上传一帧，返回结构化 JSON；
  * 响应里 ``result_image`` 是**必返**字段（base64 data URL，约占响应 94% 体积），
    因此默认在本地丢弃，只保留结构化 ``results.items``；
  * ``GET /api/v1/health`` 的 ``Date`` 响应头可当作标准时间源，用于时钟校验。
"""
from __future__ import annotations

import json
import mimetypes
import socket
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional, Tuple

from .config import Config

Log = Optional[Any]


def measure_clock_offset(cfg: Config, detector: Optional["Detector"] = None) -> Optional[float]:
    """测量"AI 服务标准时间 - 本机系统时钟"的偏移量（秒）。

    背景（ADR-004）：M20 车队有一个活的 PTP 主时钟把系统时间钉在 2024-06-20，
    本机时钟比真实时间慢一个大量级偏移；AI 服务的 ``Date`` 响应头是可达的
    标准时间源。采样器启动时调用本函数，把 JSONL 时间戳修正为真实时间。

    返回 None 表示测量失败（服务不可达 / 无 Date 头 / 解析失败）。
    """
    det = detector or Detector(cfg)
    ok, info = det.health()
    if not ok or not info.get("server_time"):
        return None
    try:
        server = datetime.fromisoformat(info["server_time"])
    except ValueError:
        return None
    if server.tzinfo is None:
        server = server.replace(tzinfo=timezone.utc)
    return (server - datetime.now(timezone.utc)).total_seconds()


@dataclass
class DetectResult:
    ok: bool
    http_status: Optional[int]
    payload: Optional[Dict[str, Any]]
    error: Optional[str]
    wall_ms: int
    elapsed_ms: Optional[float] = None


def strip_result_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    """复制 payload 并剥掉 ``result_image``（base64 data URL，占响应 ~94% 体积）。

    留存原始响应 JSON 时只保留结构化字段；图片另存 jpg，JSON 里以
    ``_result_image``（路径引用）与 ``_result_image_bytes``（原字段长度）备注。
    """
    out: Dict[str, Any] = dict(payload or {})
    img = out.pop("result_image", None)
    if isinstance(img, str):
        out["_result_image_bytes"] = len(img)
    return out


def encode_multipart(
    fields: Optional[Dict[str, str]] = None, files: Optional[Dict[str, Tuple[str, bytes, str]]] = None
) -> Tuple[str, bytes]:
    """手工构造 multipart/form-data（标准库没有现成 helper）。"""
    fields = fields or {}
    files = files or {}
    boundary = "----m20aidetect%s" % uuid.uuid4().hex
    buf = bytearray()
    for name, value in fields.items():
        buf += ("--%s\r\n" % boundary).encode("ascii")
        buf += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode("utf-8")
        buf += ("%s\r\n" % value).encode("utf-8")
    for name, (filename, data, ctype) in files.items():
        buf += ("--%s\r\n" % boundary).encode("ascii")
        buf += (
            'Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, filename)
        ).encode("utf-8")
        buf += ("Content-Type: %s\r\n\r\n" % ctype).encode("ascii")
        buf += data
        buf += b"\r\n"
    buf += ("--%s--\r\n" % boundary).encode("ascii")
    return boundary, bytes(buf)


class Detector:
    def __init__(self, cfg: Config, log=None) -> None:
        self.cfg = cfg
        self.log = log or (lambda msg: None)

    # ------------------------------------------------------------ health
    def health(self) -> Tuple[bool, Dict[str, Any]]:
        """返回 (ok, info)。info 含服务端标准时间，供时钟校验用。"""
        req = urllib.request.Request(self.cfg.health_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                body = resp.read()
                payload = json.loads(body.decode("utf-8"))
                info = dict(payload)
                date_hdr = resp.headers.get("Date")
                if date_hdr:
                    info["server_time"] = parsedate_to_datetime(date_hdr).isoformat()
                return True, info
        except urllib.error.HTTPError as exc:
            return False, {"error": "HTTP %s" % exc.code}
        except Exception as exc:  # URLError / timeout / JSON
            return False, {"error": "%s: %s" % (type(exc).__name__, exc)}

    # ------------------------------------------------------------ detect
    def detect(self, jpeg: bytes, filename: str) -> DetectResult:
        boundary, body = encode_multipart(
            fields={k: str(v) for k, v in self.cfg.params.items()},
            files={"file": (filename, jpeg, "image/jpeg")},
        )
        req = urllib.request.Request(
            self.cfg.task_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "multipart/form-data; boundary=%s" % boundary,
                "Content-Length": str(len(body)),
                "Accept": "application/json",
            },
        )
        import time

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                raw = resp.read()
                wall_ms = int((time.time() - t0) * 1000)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    return DetectResult(False, resp.status, None, "BAD_JSON: %s" % exc, wall_ms)
                return DetectResult(
                    True, resp.status, payload, None, wall_ms, payload.get("elapsed_ms")
                )
        except urllib.error.HTTPError as exc:
            wall_ms = int((time.time() - t0) * 1000)
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return DetectResult(False, exc.code, None, "HTTP %s %s" % (exc.code, detail), wall_ms)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            wall_ms = int((time.time() - t0) * 1000)
            return DetectResult(False, None, None, "%s: %s" % (type(exc).__name__, exc), wall_ms)

    # ------------------------------------------------------------ 图片
    @staticmethod
    def decode_result_image(payload: Dict[str, Any]) -> Optional[bytes]:
        """把 result_image 的 base64 data URL 解成 JPEG 字节（仅告警帧使用）。"""
        import base64

        img = (payload or {}).get("result_image") or ""
        if not isinstance(img, str) or "," not in img:
            return None
        try:
            return base64.b64decode(img.split(",", 1)[1])
        except Exception:
            return None

    @staticmethod
    def guess_ctype(path: str) -> str:
        return mimetypes.guess_type(path)[0] or "application/octet-stream"
