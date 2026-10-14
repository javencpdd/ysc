"""HTTP 壳：JSON API + 静态单页。

路由（全部 JSON，错误统一 {"ok": false, "error": "..."}）：
  GET  /                    静态页
  GET  /api/status          服务状态 + 磁盘 + journal 占用 + 时钟偏移 + 版本
  POST /api/service         {"action": start|stop|restart}
  GET  /api/config          当前 env（脱敏）+ 生效配置 + AI 能力列表
  POST /api/config          {"updates": {...}} 校验→写 env→（按需）重启
  GET  /api/logs            ?level=&q=&n=   过滤后的 journal 行
  POST /api/detect          单帧检测（body 为 JPEG，?cap=&include_image=1&save=1）
  GET  /api/recent          ?n=    今日 JSONL 尾部真实检测记录（解析后）
  GET  /api/response        ?frame=&cam=&redetect=1   单帧响应详情（已留存直读/原帧重测）
  GET  /api/retention       当前留存策略
  POST /api/retention       混合保存（env 级 + root helper 级 + spool 清空）

提权与安全见 sysactions 模块 docstring 与 docs/ADR-005。
响应留存与查看见 docs/ADR-006。
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

from . import __version__, envfile, logfilter, sysactions
from m20_ai_detect.config import Config, ConfigError

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
INDEX_HTML = os.path.join(STATIC_DIR, "index.html")


# ---------------------------------------------------------------- 配置
class ConsoleConfig:
    """控制台自身配置（M20AIC_* 环境变量，由 systemd EnvironmentFile 注入）。"""

    def __init__(self, env: Optional[Dict[str, str]] = None) -> None:
        env = os.environ if env is None else env
        self.bind = env.get("M20AIC_BIND", "0.0.0.0")
        self.port = int(env.get("M20AIC_PORT", "5050"))
        self.token = env.get("M20AIC_TOKEN", "").strip()
        self.base_dir = env.get("M20AIC_BASE_DIR", "/home/djw/m20-ai-detect")
        self.env_file = env.get(
            "M20AIC_ENV_FILE", os.path.join(self.base_dir, "m20-ai-detect.env")
        )
        self.helper = env.get("M20AIC_HELPER", "/usr/local/sbin/m20-ai-console-helper")

    @property
    def sampler_cfg(self) -> Config:
        return Config.from_env(envfile.read_env(self.env_file))


def _redact(env: Dict[str, str]) -> Dict[str, str]:
    out = dict(env)
    for key in list(out):
        if any(s in key for s in ("PASS", "TOKEN", "SECRET", "KEY")):
            out[key] = "***"
    if "M20AI_AI_BASE" in out and "@" in out["M20AI_AI_BASE"]:
        out["M20AI_AI_BASE"] = "***@" + out["M20AI_AI_BASE"].split("@", 1)[1]
    return out


def _capabilities(cfg: Config) -> Tuple[List[Dict[str, Any]], str]:
    """拉 AI 服务能力列表。失败返回 ([], 错误信息)——不阻断页面。"""
    url = cfg.ai_base.rstrip("/") + "/api/v1/capabilities"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = [
            {
                "id": it.get("id", ""),
                "title": it.get("title") or it.get("id", ""),
                "group": it.get("group", ""),
                "ready": bool(it.get("model_ready")),
            }
            for it in data.get("items", [])
            if it.get("id")
        ]
        return items, ""
    except Exception as exc:  # 网络失败不该打爆控制台
        return [], "%s: %s" % (type(exc).__name__, exc)


def _today_counts(base_dir: str) -> Tuple[int, int]:
    """今日（本机日历日）帧数与告警数——直接数 results/YYYYMMDD.jsonl，不构造 Store。"""
    from datetime import datetime

    path = os.path.join(
        base_dir, "results", datetime.now().strftime("%Y%m%d") + ".jsonl"
    )
    frames = alerts = 0
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                frames += 1
                if '"alert": true' in line:
                    alerts += 1
    except OSError:
        pass
    return frames, alerts


def _disk_stats(cfg: ConsoleConfig) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in ("spool", "raw", "results", "alerts", "saved", "log"):
        path = os.path.join(cfg.base_dir, name)
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        out[name + "_mb"] = round(total / 1048576.0, 1)
    try:
        statvfs = getattr(os, "statvfs", None)  # Windows 无此函数（开发机跑测试用）
        if statvfs is None:
            out["disk_free_gb"] = None
        else:
            usage = statvfs(cfg.base_dir)
            out["disk_free_gb"] = round(usage.f_bavail * usage.f_frsize / 1073741824.0, 1)
    except OSError:
        out["disk_free_gb"] = None
    return out


# ---------------------------------------------------------------- 单帧检测
def detect_single_frame(
    cfg: Config,
    jpeg: bytes,
    cap: str = "",
    include_image: bool = True,
    save: bool = False,
) -> Dict[str, Any]:
    """单帧检测：直接调 AI 接口，不落库不进环形缓冲。

    save=True 时（ADR-006）把标注结果图 + 原始响应对落 saved/console/，
    与采样器的条件留存同一格式，便于控制台「单帧检测」也能留证据。
    """
    from datetime import datetime

    from m20_ai_detect.detect import Detector, strip_result_image
    from m20_ai_detect.store import Store

    if cap:
        cfg = replace(cfg, cap_id=cap)
    det = Detector(cfg)
    res = det.detect(jpeg, "console-single.jpg")
    if not res.ok:
        return {"ok": False, "error": res.error, "http_status": res.http_status}
    payload = res.payload or {}
    items = ((payload.get("results") or {}).get("items")) or []
    out: Dict[str, Any] = {
        "ok": True,
        "capability": payload.get("capability", cfg.cap_id),
        "elapsed_ms": payload.get("elapsed_ms"),
        "e2e_ms": res.wall_ms,
        "device": payload.get("device"),
        "n_items": len(items),
        "items": [
            {k: it.get(k) for k in ("label", "score", "box") if k in it} for it in items
        ],
        # 原始响应（剥掉 base64 大图字段）——控制台直接展示"接口回了什么"
        "raw_response": strip_result_image(payload),
    }
    if include_image:
        img = det.decode_result_image(payload)
        if img:
            out["result_image"] = "data:image/jpeg;base64," + base64.b64encode(img).decode()
    if save:
        stem = "console_%s" % datetime.now().strftime("%Y%m%d_%H%M%S")
        img_rel, json_rel = Store(cfg).save_pair(
            "console", stem, det.decode_result_image(payload), payload
        )
        if img_rel:
            out["saved_image"] = img_rel
        if json_rel:
            out["resp_path"] = json_rel
    return out


# ---------------------------------------------------------------- 清空积压帧
def clear_spool_with_restart(
    cfg: ConsoleConfig, runner=sysactions.default_runner
) -> Tuple[bool, str]:
    """清空 spool/ 积压帧（2026-10-15 新增）：停采样器 → 删帧 → 起采样器。

    提权模型（与 ADR-005 一致）：
      * 启停走 sudoers 白名单里的 svc-stop/svc-start（root helper）；
      * 删帧本身**不提权**——spool/ 归 user 所有，控制台与采样器同 user；
      * 停失败即中止（运行中删帧会与抽帧/推理竞争，且删除期间会有新帧写入）；
      * 全程 logger 留痕。
    只清 spool/（未推理的待办帧）；raw/ 环形缓冲与 results/ JSONL 不动。
    """
    ok, msg = sysactions.service_action("stop", cfg.helper, runner)
    if not ok:
        return False, "停采样器失败：%s" % msg
    try:
        from m20_ai_detect.store import Store

        frames, nbytes = Store(cfg.sampler_cfg).clear_spool()
    except OSError as exc:
        sysactions.service_action("start", cfg.helper, runner)  # 别把服务落在停止态
        return False, "清空失败：%s（采样器已尝试恢复启动）" % exc
    note = "已清空积压 %d 帧（%.1f MB），采样器已重启，以实时为主" % (
        frames,
        nbytes / 1048576.0,
    )
    ok2, msg2 = sysactions.service_action("start", cfg.helper, runner)
    if not ok2:
        return False, note + "；但重启采样器失败：%s" % msg2
    try:
        runner(
            [
                "logger",
                "-t",
                "m20-ai-console",
                "spool cleared: %d frames, %.1f MB" % (frames, nbytes / 1048576.0),
            ],
            10,
        )
    except Exception:
        pass
    return True, note


# ---------------------------------------------------------------- 最近检测记录
def _recent_records(base_dir: str, n: int = 12) -> List[Dict[str, Any]]:
    """读今日 JSONL 尾部 n 条真实检测记录（解析后，给「最近检测」卡用）。"""
    from datetime import datetime

    n = max(1, min(n, 100))
    path = os.path.join(
        base_dir, "results", datetime.now().strftime("%Y%m%d") + ".jsonl"
    )
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "ts": r.get("ts"),
                "cam": r.get("cam"),
                "frame": r.get("frame"),
                "n_items": r.get("n_items"),
                "items": r.get("items") or [],
                "alert": bool(r.get("alert")),
                "elapsed_ms": r.get("elapsed_ms"),
                "e2e_ms": r.get("e2e_ms"),
                "saved_image": r.get("saved_image"),
                "resp_path": r.get("resp_path"),
                "http": r.get("http"),
            }
        )
    return out


def _safe_component(s: str) -> bool:
    """帧名/相机名只允许安全字符（防路径穿越）。"""
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", s or "")) and ".." not in s


# ---------------------------------------------------------------- 响应详情
def _response_detail(
    cfg: ConsoleConfig, frame: str, cam: str, redetect: bool
) -> Dict[str, Any]:
    """单帧响应详情（ADR-006）。

    优先读 saved/<cam>/<stem>.json（SAVE_MODE 触发过才存在）；
    未留存且 redetect=1 时，用 raw/<cam>/<frame> 里的原帧重新调一次 AI 服务，
    拿完整响应（原帧在 200MB 环形缓冲内可回放近几小时）。
    """
    from m20_ai_detect.detect import Detector, strip_result_image

    if not _safe_component(frame) or not _safe_component(cam):
        return {"ok": False, "error": "frame/cam 含非法字符"}
    stem = os.path.splitext(frame)[0]
    base = cfg.base_dir

    jpath = os.path.join(base, "saved", cam, stem + ".json")
    if os.path.exists(jpath):
        try:
            with open(jpath, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": "已留存响应读取失败：%s" % exc}
        img_data = ""
        img_rel = doc.get("_result_image")
        if img_rel:
            p = os.path.normpath(os.path.join(base, str(img_rel)))
            if p.startswith(base + os.sep):  # 防留存文件被改出工作区
                try:
                    with open(p, "rb") as fh:
                        img_data = "data:image/jpeg;base64," + base64.b64encode(fh.read()).decode()
                except OSError:
                    pass
        return {
            "ok": True,
            "source": "saved",
            "frame": frame,
            "cam": cam,
            "raw": doc,
            "result_image": img_data,
        }

    if not redetect:
        return {
            "ok": False,
            "saved": False,
            "error": "该帧未留存响应（SAVE_MODE 未触发或已被清理）；可点「重新检测」用原帧重调",
        }

    raw_path = os.path.join(base, "raw", cam, frame)
    try:
        with open(raw_path, "rb") as fh:
            jpeg = fh.read()
    except OSError:
        return {
            "ok": False,
            "saved": False,
            "error": "原帧不在 raw/ 环形缓冲（已被覆盖或路径不存在）：%s" % raw_path,
        }
    try:
        scfg = cfg.sampler_cfg
        det = Detector(scfg)
        res = det.detect(jpeg, frame)
    except Exception as exc:  # 配置错误/网络异常都不该打爆控制台
        return {"ok": False, "error": "重新检测失败：%s" % exc}
    if not res.ok:
        return {"ok": False, "error": "重新检测失败：%s" % res.error}
    payload = res.payload or {}
    items = ((payload.get("results") or {}).get("items")) or []
    img = det.decode_result_image(payload)
    return {
        "ok": True,
        "source": "redetect",
        "frame": frame,
        "cam": cam,
        "raw": strip_result_image(payload),
        "n_items": len(items),
        "items": [{k: it.get(k) for k in ("label", "score", "box") if k in it} for it in items],
        "elapsed_ms": payload.get("elapsed_ms"),
        "e2e_ms": res.wall_ms,
        "result_image": (
            "data:image/jpeg;base64," + base64.b64encode(img).decode() if img else ""
        ),
    }


# ---------------------------------------------------------------- HTTP 壳
class Handler(BaseHTTPRequestHandler):
    server_version = "m20-ai-console/" + __version__
    protocol_version = "HTTP/1.1"

    # ---- 基础工具 ----
    def _send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status: int, msg: str) -> None:
        self._send_json({"ok": False, "error": msg}, status)

    def _authorized(self) -> bool:
        token = self.server.cfg.token  # type: ignore[attr-defined]
        if not token:
            return True
        supplied = self.headers.get("X-Console-Token") or self._query().get("token", "")
        return supplied == token

    def _query(self) -> Dict[str, str]:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        self._q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return self._q

    def _body_json(self) -> Tuple[Optional[Dict[str, Any]], str]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "Content-Length 非法"
        if length <= 0:
            return {}, ""
        if length > 32 * 1024 * 1024:
            return None, "请求体过大"
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, "JSON 解析失败：%s" % exc
        if not isinstance(obj, dict):
            return None, "请求体必须是 JSON object"
        return obj, ""

    def log_message(self, fmt: str, *args: Any) -> None:  # 走 journal，不重复 stderr
        pass

    # ---- 路由 ----
    def do_GET(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            if path == "/":
                return self._get_index()  # 首页不校验 token，API 才校验
            if not self._authorized():
                return self._err(401, "token 不符")
            if path == "/api/status":
                return self._get_status()
            if path == "/api/config":
                return self._get_config()
            if path == "/api/logs":
                return self._get_logs()
            if path == "/api/recent":
                return self._get_recent()
            if path == "/api/response":
                return self._get_response()
            if path == "/api/retention":
                return self._get_retention()
            self._err(404, "not found")
        except Exception as exc:  # 全局兜底：任何异常都不许打爆服务
            self._err(500, "%s: %s" % (type(exc).__name__, exc))

    def do_POST(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            if not self._authorized():
                return self._err(401, "token 不符")
            if path == "/api/service":
                return self._post_service()
            if path == "/api/config":
                return self._post_config()
            if path == "/api/detect":
                return self._post_detect()
            if path == "/api/retention":
                return self._post_retention()
            self._err(404, "not found")
        except Exception as exc:
            self._err(500, "%s: %s" % (type(exc).__name__, exc))

    # ---- GET 实现 ----
    def _get_index(self) -> None:
        try:
            with open(INDEX_HTML, encoding="utf-8") as fh:
                self._send_html(fh.read())
        except OSError:
            self._err(500, "static/index.html 缺失")

    def _get_status(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        scfg = cfg.sampler_cfg
        offset = self.server.cached_offset()  # type: ignore[attr-defined]
        frames, alerts = _today_counts(scfg.base_dir)
        self._send_json(
            {
                "ok": True,
                "version": __version__,
                "service": sysactions.service_status(),
                "clock_offset_sec": offset,
                "journal_usage": sysactions.journal_disk_usage(),
                "disk": _disk_stats(cfg),
                "frames_today": frames,
                "alerts_today": alerts,
                "sampler": {
                    "cap_id": scfg.cap_id,
                    "cameras": [c.name for c in scfg.cameras],
                    "fps": scfg.fps,
                    "base_dir": scfg.base_dir,
                },
            }
        )

    def _get_config(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        env = envfile.read_env(cfg.env_file)
        scfg = cfg.sampler_cfg
        caps, cap_err = _capabilities(scfg)
        self._send_json(
            {
                "ok": True,
                "env": _redact(env),
                "effective": {
                    "cap_id": scfg.cap_id,
                    "cameras": [
                        {"name": c.name, "src": c.src} for c in scfg.cameras
                    ],
                    "fps": scfg.fps,
                    "alert_labels": list(scfg.alert_labels),
                    "alert_score": scfg.alert_score,
                    "params": scfg.params,
                    "ring_max_mb": round(scfg.ring_max_bytes / 1048576.0, 1),
                    "results_keep_days": scfg.results_keep_days,
                    "ts_offset_sec": scfg.ts_offset_sec,
                    "save_result_image": scfg.save_result_image,
                    "save_mode": scfg.save_mode,
                },
                "capabilities": caps,
                "capabilities_error": cap_err,
            }
        )

    def _get_logs(self) -> None:
        q = self._query()
        level = q.get("level", "all")
        if level not in logfilter.LEVELS:
            level = "all"
        try:
            n = int(q.get("n", "300"))
        except ValueError:
            n = 300
        lines = sysactions.journal_lines(n)
        lines = logfilter.filter_lines(lines, level, q.get("q", ""))
        out = [{"raw": ln, "level": logfilter.classify(ln)} for ln in lines[-500:]]
        self._send_json({"ok": True, "lines": out, "total": len(lines)})

    def _get_recent(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        try:
            n = int(q.get("n", "12"))
        except ValueError:
            n = 12
        records = _recent_records(cfg.sampler_cfg.base_dir, n)
        self._send_json(
            {
                "ok": True,
                "records": list(reversed(records)),  # 最新在前
                "save_mode": cfg.sampler_cfg.save_mode,
            }
        )

    def _get_response(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        frame = q.get("frame", "")
        cam = q.get("cam", "front")
        if not frame:
            return self._err(400, "缺少 frame 参数")
        redetect = q.get("redetect", "0") == "1"
        out = _response_detail(cfg, frame, cam, redetect)
        if not out.get("ok"):
            status = 404 if out.get("saved") is False else 400
            return self._err(status, out.get("error", "查询失败"))
        self._send_json(out)

    def _get_retention(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        scfg = cfg.sampler_cfg
        self._send_json(
            {
                "ok": True,
                "ring_max_mb": round(scfg.ring_max_bytes / 1048576.0, 1),
                "results_keep_days": scfg.results_keep_days,
                "save_mode": scfg.save_mode,
                "journal_usage": sysactions.journal_disk_usage(),
                "journald_managed": _read_journald_block(),
                "logrotate_rotate": _read_logrotate_rotate(),
                "note": "env 级改动重启采样器后生效；journald/logrotate 级立即生效",
            }
        )

    # ---- POST 实现 ----
    def _post_service(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        body, err = self._body_json()
        if err:
            return self._err(400, err)
        action = str(body.get("action", ""))
        ok, msg = sysactions.service_action(action, cfg.helper)
        if not ok:
            return self._err(500, msg or "动作失败")
        self._send_json({"ok": True, "action": action, "detail": msg})

    def _post_config(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        body, err = self._body_json()
        if err:
            return self._err(400, err)
        updates = body.get("updates")
        if not isinstance(updates, dict) or not updates:
            return self._err(400, "updates 必须是非空 object")
        clean = {str(k): str(v) for k, v in updates.items()}
        if not all(k.startswith("M20AI_") for k in clean):
            return self._err(400, "只允许 M20AI_* 键")
        current = envfile.read_env(cfg.env_file)
        ok, errors = envfile.validate_env(current, clean)
        if not ok:
            return self._err(400, "配置校验失败：" + "；".join(errors))
        try:
            envfile.set_env_keys(cfg.env_file, clean)
        except (OSError, ValueError) as exc:
            return self._err(500, "写入 env 失败：%s" % exc)
        restart = bool(body.get("restart", True))
        detail = "已写入 env"
        if restart:
            ok, msg = sysactions.service_action("restart", cfg.helper)
            detail += "；已重启" if ok else "；重启失败：%s" % msg
        else:
            detail += "；未重启（重启后生效）"
        self._send_json({"ok": True, "detail": detail, "applied": sorted(clean)})

    def _post_detect(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._err(400, "Content-Length 非法")
        if length <= 0 or length > 20 * 1024 * 1024:
            return self._err(400, "图片大小必须在 0-20MB")
        jpeg = self.rfile.read(length)
        try:
            result = detect_single_frame(
                cfg.sampler_cfg,
                jpeg,
                cap=q.get("cap", ""),
                include_image=q.get("include_image", "1") != "0",
                save=q.get("save", "0") == "1",
            )
        except Exception as exc:
            return self._err(500, "检测失败：%s" % exc)
        if not result.get("ok"):
            return self._err(502, result.get("error", "检测失败"))
        self._send_json(result)

    def _post_retention(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        body, err = self._body_json()
        if err:
            return self._err(400, err)
        notes: List[str] = []

        # ---- env 级（ring / results keep / save mode）----
        env_updates = {}
        if "ring_max_mb" in body:
            env_updates["M20AI_RING_MAX_MB"] = str(body["ring_max_mb"])
        if "results_keep_days" in body:
            env_updates["M20AI_RESULTS_KEEP_DAYS"] = str(body["results_keep_days"])
        if "save_mode" in body:
            mode = str(body["save_mode"]).strip().lower()
            if mode not in ("off", "alert", "any", "all"):
                return self._err(400, "save_mode 必须是 off/alert/any/all 之一")
            env_updates["M20AI_SAVE_MODE"] = mode
        if env_updates:
            current = envfile.read_env(cfg.env_file)
            ok, errors = envfile.validate_env(current, env_updates)
            if not ok:
                return self._err(400, "配置校验失败：" + "；".join(errors))
            try:
                envfile.set_env_keys(cfg.env_file, env_updates)
            except (OSError, ValueError) as exc:
                return self._err(500, "写入 env 失败：%s" % exc)
            notes.append("env 级已写入（重启采样器后生效）")

        # ---- root 级（helper）----
        if "journal_vacuum" in body:
            fields = body["journal_vacuum"] or {}
            err = sysactions.check_vacuum(fields)
            if err:
                return self._err(400, err)
            ok, msg = sysactions.call_helper(
                "journal-vacuum", fields, cfg.base_dir, cfg.helper
            )
            notes.append(("journal vacuum 已执行" if ok else "vacuum 失败：%s" % msg))
        if "journald_limits" in body:
            fields = body["journald_limits"] or {}
            err = sysactions.check_journald_limits(fields)
            if err:
                return self._err(400, err)
            ok, msg = sysactions.call_helper(
                "journald-limits", fields, cfg.base_dir, cfg.helper
            )
            notes.append(("journald 上限已更新" if ok else "journald 更新失败：%s" % msg))
        if "logrotate_rotate" in body:
            fields = {"rotate": str(body["logrotate_rotate"])}
            err = sysactions.check_logrotate(fields)
            if err:
                return self._err(400, err)
            ok, msg = sysactions.call_helper(
                "logrotate-rotate", fields, cfg.base_dir, cfg.helper
            )
            notes.append(("logrotate 轮转数已更新" if ok else "logrotate 更新失败：%s" % msg))

        if body.get("spool_clear"):
            ok, msg = clear_spool_with_restart(cfg)
            if not ok:
                return self._err(500, msg)
            notes.append(msg)

        if not notes:
            return self._err(400, "没有可保存的项")
        self._send_json({"ok": True, "notes": notes})


# ---------------------------------------------------------------- journald/logrotate 读取
def _read_journald_block() -> Dict[str, str]:
    """读 journald.conf 里控制台管理的标记块。"""
    out: Dict[str, str] = {}
    try:
        with open("/etc/systemd/journald.conf", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return out
    m = re_search_block(text)
    for line in m.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def re_search_block(text: str) -> str:
    m = re.search(
        r"# m20-ai-console managed begin\n(.*?)# m20-ai-console managed end",
        text,
        re.S,
    )
    return m.group(1) if m else ""


def _read_logrotate_rotate() -> Optional[int]:
    try:
        with open("/etc/logrotate.d/m20-ai-detect", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.search(r"^\s*rotate\s+(\d+)", text, re.M)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- 入口
class Console(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, cfg: ConsoleConfig) -> None:
        self.cfg = cfg
        self._offset_cache: Tuple[float, Optional[float]] = (0.0, None)
        super().__init__((cfg.bind, cfg.port), Handler)

    def cached_offset(self) -> Optional[float]:
        """时钟偏移缓存 60s（每次 status 都测会浪费 AI 服务配额）。"""
        now = time.time()
        ts, val = self._offset_cache
        if now - ts > 60:
            val = self._measure_offset()
            self._offset_cache = (now, val)
        return val

    def _measure_offset(self) -> Optional[float]:
        try:
            from m20_ai_detect.detect import measure_clock_offset

            return measure_clock_offset(self.cfg.sampler_cfg)
        except Exception:
            return None


def main(argv: Optional[List[str]] = None) -> int:
    cfg = ConsoleConfig()
    srv = Console(cfg)
    print(
        "m20-ai-console v%s listening on %s:%d (token %s)"
        % (__version__, cfg.bind, cfg.port, "on" if cfg.token else "off"),
        flush=True,
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
