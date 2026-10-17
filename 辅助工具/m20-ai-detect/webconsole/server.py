"""HTTP 壳：JSON API + 静态单页。

路由（全部 JSON，错误统一 {"ok": false, "error": "..."}）：
  GET  /                    静态页
  GET  /api/status          服务状态 + 磁盘 + journal 占用(字节) + 时钟偏移 + 版本
  POST /api/service         {"action": start|stop|restart}
  GET  /api/config          当前 env（脱敏）+ 生效配置 + AI 能力列表
  POST /api/config          {"updates": {...}} 校验→写 env→（按需）重启
  GET  /api/logs            ?level=&q=&n=   过滤后的 journal 行
  POST /api/detect          单帧检测（body 为 JPEG，?cap=&include_image=1&save=1）
  GET  /api/recent          ?n=    今日 JSONL 尾部真实检测记录（解析后）
  GET  /api/snapshot        ?cam=   相机画面单帧（raw 最新帧优先/即时抓帧兜底，ADR-012）
  GET  /api/saved           ?n=&cam=   目标图片时间轴（saved/ 成对文件汇总，ADR-008）
  GET  /api/saved/img       ?cam=&frame=  单张留存图片（JPEG 二进制）
  GET  /api/response        ?frame=&cam=&redetect=1   单帧响应详情（已留存直读/原帧重测）
  GET  /api/retention       当前留存策略（含「关注目标」与今日检出标签统计）
  POST /api/retention       混合保存（env 级 + root helper 级 + 数据清空 + 按需重启采集）
  GET  /api/files           ?dir=&n=&match=  只读文件浏览（限白名单根，ADR-009）
  GET  /api/file            ?path=&tail=&dl=1 单文件只读（文本可 tail 末尾 N 行）

提权与安全见 sysactions 模块 docstring 与 docs/ADR-005。
响应留存与查看见 docs/ADR-006；时间轴与 saved/ 清理见 docs/ADR-008；
受限只读文件浏览见 docs/ADR-009；关注目标与数据清空见 docs/ADR-011；
相机画面预览见 docs/ADR-012。
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

from . import __version__, envfile, i18n, logfilter, sysactions
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
    clock_offset: Optional[float] = None,
) -> Dict[str, Any]:
    """单帧检测：直接调 AI 接口，不落库不进环形缓冲。

    save=True 时（ADR-006）把标注结果图 + 原始响应对落 saved/console/，
    与采样器的条件留存同一格式，便于控制台「单帧检测」也能留证据；
    留存 JSON 带 ``_saved_at``（真实时钟，来自 clock_offset）供时间轴显示（ADR-008）。
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
        from datetime import datetime, timedelta

        stem = "console_%s" % datetime.now().strftime("%Y%m%d_%H%M%S")
        ts = ""
        if clock_offset is not None:
            ts = (datetime.now() + timedelta(seconds=clock_offset)).isoformat(
                timespec="milliseconds"
            )
        img_rel, json_rel = Store(cfg).save_pair(
            "console",
            stem,
            det.decode_result_image(payload),
            payload,
            meta={"_saved_at": ts},
        )
        if img_rel:
            out["saved_image"] = img_rel
        if json_rel:
            out["resp_path"] = json_rel
    return out


# ---------------------------------------------------------------- 数据清空（ADR-011）
#: purge 字段可接受的类别（与 Store.PURGE_KINDS 一致）。
PURGE_SCOPES = ("saved", "raw", "results", "spool")

_PURGE_SCOPE_LABEL = {
    "saved": "saved/ 留存图片",
    "raw": "raw/ 原始帧",
    "results": "results/ 检测记录",
    "spool": "spool/ 积压帧",
}


def _fmt_bytes(nbytes: int) -> str:
    if nbytes < 1024:
        return "%d B" % nbytes
    if nbytes < 1048576:
        return "%.1f KB" % (nbytes / 1024.0)
    return "%.1f MB" % (nbytes / 1048576.0)


def _purge_with_restart(
    cfg: ConsoleConfig,
    kinds: List[str],
    runner=sysactions.default_runner,
    lang: str = "zh",
) -> Tuple[bool, str]:
    """清空所选数据（2026-10-16 新增，ADR-011）：停采集（仅当在运行）→ 清空 → 恢复采集。

    提权模型（与 ADR-005 一致）：
      * 启停走 sudoers 白名单里的 svc-stop/svc-start（root helper）；
      * 删文件本身**不提权**——spool/raw/results/saved 归 user，控制台与采样器同 user；
      * 采集**原本未运行则不启动**（ADR-010：采集开关由用户掌握，清数据不改变它）；
      * 采集状态无法确认（无 systemctl / 超时）时不碰服务直接清——各写入点均为
        短 open/write/close 或整文件写入，与运行中采集的竞争最坏损失极少量新记录；
      * 停采集失败即中止（未清任何数据，避免与写入竞争、保证"清得干净"）。
    返回 (ok, note)；note 含每类删除统计与采集恢复结果。全程 logger 留痕。
    """
    from m20_ai_detect.store import Store

    was_active = sysactions.service_is_active(runner)
    if was_active is True:
        ok, msg = sysactions.service_action("stop", cfg.helper, runner)
        if not ok:
            return False, i18n.fmt("purge.stop_fail", lang, msg=msg)
    try:
        stats = Store(cfg.sampler_cfg).purge(kinds)
    except (OSError, ValueError) as exc:
        if was_active is True:
            sysactions.service_action("start", cfg.helper, runner)  # 别把采集落在停止态
            return False, i18n.fmt("purge.fail_restored", lang, e=exc)
        return False, i18n.fmt("purge.fail", lang, e=exc)

    parts = []
    total_files = 0
    total_bytes = 0
    for kind in kinds:
        files, nbytes = stats.get(kind, (0, 0))
        total_files += files
        total_bytes += nbytes
        label = i18n.fmt("purge.kind." + kind, lang)
        parts.append(i18n.fmt("purge.part", lang, label=label, files=files, size=_fmt_bytes(nbytes)))
    note = i18n.fmt("purge.head", lang, parts=("、" if lang != "en" else ", ").join(parts))
    if was_active is True:
        ok2, msg2 = sysactions.service_action("start", cfg.helper, runner)
        if ok2:
            note += i18n.fmt("purge.restarted", lang)
        else:
            note += i18n.fmt("purge.restore_fail", lang, msg=msg2)
    elif was_active is False:
        note += i18n.fmt("purge.idle", lang)
    else:
        note += i18n.fmt("purge.unknown", lang)
    try:
        runner(
            [
                "logger",
                "-t",
                "m20-ai-console",
                "purge %s: %d file(s), %d bytes" % (",".join(kinds), total_files, total_bytes),
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


# ---------------------------------------------------------------- 关注目标（ADR-011）
#: 标签合法性：英文字母/数字与 . _ -（覆盖 YOLO 标签集），单个最长 40 字符。
_LABEL_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")

#: 单次接受的标签数上限
_LABEL_MAX = 32

#: 今日检出标签统计缓存（60s TTL；清空 results/ 后由 _post_retention 主动失效）。
_label_stats_cache: Dict[str, Any] = {"t": 0.0, "base": "", "data": []}


def _label_stats(
    base_dir: str, max_bytes: int = 4 * 1024 * 1024, top: int = 20
) -> List[Dict[str, Any]]:
    """今日 JSONL 尾部按 label 聚合计数（降序 top N）——网页「关注目标」的备选清单。

    只读尾部 max_bytes（防 any 模式大文件拖慢页面）；首行可能被截断，丢弃。
    60s 内重复调用走缓存；解析失败的行静默跳过（与 _recent_records 一致）。
    """
    cache = _label_stats_cache
    now = time.time()
    if cache["base"] == base_dir and now - cache["t"] < 60.0:
        return cache["data"]  # type: ignore[return-value]

    from datetime import datetime

    path = os.path.join(base_dir, "results", datetime.now().strftime("%Y%m%d") + ".jsonl")
    data = b""
    truncated = False
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            truncated = size > max_bytes
            if truncated:
                fh.seek(size - max_bytes)
            else:
                fh.seek(0)  # 不截断时必须回到文件头，否则 read() 从 EOF 读到空
            data = fh.read()
    except OSError:
        data = b""
    lines = data.decode("utf-8", errors="ignore").splitlines()
    if truncated and lines:
        lines = lines[1:]  # 首行可能被截断
    counts: Dict[str, int] = {}
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        for it in rec.get("items") or []:
            label = it.get("label")
            if label:
                key = str(label)
                counts[key] = counts.get(key, 0) + 1
    out = [
        {"label": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    ]
    cache.update(t=now, base=base_dir, data=out)
    return out


def _safe_component(s: str) -> bool:
    """帧名/相机名只允许安全字符（防路径穿越）。"""
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", s or "")) and ".." not in s


# ---------------------------------------------------------------- 受限只读文件浏览（ADR-009）
#: 只读浏览允许进入的**一级目录**。工程代码、env 文件、systemd 配置一律不在列。
FILE_ROOTS = ("saved", "raw", "results", "spool", "log")

#: 单文件整读上限（超过必须改用 tail=N，避免把 200MB 的 jpg/大 jsonl 灌进内存）
FILE_MAX_BYTES = 32 * 1024 * 1024

#: tail 最大行数
FILE_TAIL_MAX = 5000

_FILE_EXT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".json": "application/json; charset=utf-8",
    ".jsonl": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".yml": "text/plain; charset=utf-8",
    ".yaml": "text/plain; charset=utf-8",
}


def _safe_rel_path(rel: str) -> bool:
    """只读浏览的相对路径校验：逐级检查字符、禁止 ..、首段必须落在白名单根。"""
    if not rel or rel.startswith("/") or "\\" in rel or ".." in rel:
        return False
    parts = [p for p in rel.split("/") if p]
    if not parts or len(parts) > 8:
        return False
    for p in parts:
        if not _safe_component(p):
            return False
    return parts[0] in FILE_ROOTS


def _resolve_under(base_dir: str, rel: str) -> Optional[str]:
    """把 rel 解析成 base_dir 下的绝对路径；越界/穿越一律返回 None。

    除字符校验外再补一次 realpath 前缀比对，堵住符号链接指向工程外的可能。
    """
    if not _safe_rel_path(rel):
        return None
    root = os.path.realpath(base_dir)
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def _tail_bytes(path: str, n: int) -> bytes:
    """取文本文件末尾 n 行：只回读尾部若干块，不整读大文件。"""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos = fh.tell()
        chunk = 65536
        buf = b""
        while pos > 0 and buf.count(b"\n") <= n:
            start = max(0, pos - chunk)
            fh.seek(start)
            buf = fh.read(pos - start) + buf
            pos = start
    lines = buf.splitlines()
    return b"\n".join(lines[-n:]) + (b"\n" if lines else b"")


def _file_list(base_dir: str, rel: str = "", limit: int = 300, match: str = "") -> Dict[str, Any]:
    """列出只读目录内容（ADR-009）。rel 为空时只列出白名单根。"""
    limit = max(1, min(int(limit), 2000))
    if rel:
        target = _resolve_under(base_dir, rel)
        if target is None:
            return {"ok": False, "error": "路径不在只读白名单内"}
        if not os.path.isdir(target):
            return {"ok": False, "error": "不是目录"}
        cur = rel.strip("/")
    else:
        target, cur = os.path.realpath(base_dir), ""
    try:
        names = sorted(os.listdir(target))
    except OSError as exc:
        return {"ok": False, "error": "目录不可读：%s" % exc}
    if not cur:
        names = [n for n in names if n in FILE_ROOTS]
    dirs: List[Dict[str, Any]] = []
    files: List[Dict[str, Any]] = []
    for name in names:
        if match and match.lower() not in name.lower():
            continue
        p = os.path.join(target, name)
        try:
            st = os.stat(p)
        except OSError:
            continue
        node = {
            "name": name,
            "path": ("%s/%s" % (cur, name)) if cur else name,
            "type": "dir" if os.path.isdir(p) else "file",
            "ts": _iso_from_epoch(st.st_mtime),
        }
        if node["type"] == "dir":
            dirs.append(node)
        else:
            node["size"] = st.st_size
            files.append(node)
    files.sort(key=lambda e: e["ts"], reverse=True)  # 新文件在前
    ordered = dirs + files
    return {
        "ok": True,
        "dir": cur,
        "parent": "/".join(cur.split("/")[:-1]) if cur else "",
        "roots": list(FILE_ROOTS),
        "entries": ordered[:limit],
        "count": len(ordered),
        "truncated": len(ordered) > limit,
    }


# ---------------------------------------------------------------- 目标图片时间轴
def _iso_from_epoch(epoch: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(epoch).isoformat(timespec="milliseconds")


def _saved_gallery(
    base_dir: str,
    limit: int = 1000,
    cam: str = "",
    offset_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """目标图片时间轴（ADR-008）：汇总 saved/<cam>/ 成对文件，最新 limit 条倒序返回。

    * 以 .jpg 为驱动（时间轴只展示图片；只有 .json 的留存不算条目）；
    * ts 优先取留存 JSON 的 ``_saved_at``（采样时写入的真实时钟，含偏移修正）；
      老文件没有该字段时退化为 文件 mtime + 时钟偏移(offset_sec)；
    * 只读操作，不修改任何文件；单个文件读取失败跳过（清理竞态下属正常）。
    """
    saved_root = os.path.join(base_dir, "saved")
    limit = max(1, min(int(limit), 5000))
    off = offset_sec or 0.0
    try:
        cams = sorted(
            n for n in os.listdir(saved_root) if os.path.isdir(os.path.join(saved_root, n))
        )
    except OSError:
        cams = []
    entries = []  # (mtime, cam, stem, jpg_path, json_path)
    for cname in cams:
        if not _safe_component(cname):
            continue
        d = os.path.join(saved_root, cname)
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            if not name.endswith(".jpg"):
                continue
            jpg = os.path.join(d, name)
            try:
                mtime = os.stat(jpg).st_mtime
            except OSError:
                continue
            stem = name[:-4]
            entries.append((mtime, cname, stem, jpg, os.path.join(d, stem + ".json")))
    cams_present = sorted({e[1] for e in entries})
    total = len(entries)
    if cam:
        entries = [e for e in entries if e[1] == cam]
    entries.sort(key=lambda e: e[0], reverse=True)  # 最新在前；ts 缺失时以其为排序依据
    records: List[Dict[str, Any]] = []
    for mtime, cname, stem, _jpg, js in entries[:limit]:
        ts = ""
        items: List[Dict[str, Any]] = []
        alert = False
        try:
            with open(js, encoding="utf-8") as fh:
                doc = json.load(fh)
            ts = str(doc.get("_saved_at") or "")
            alert = bool(doc.get("_alert"))
            raw_items = ((doc.get("results") or {}).get("items")) or []
            items = [
                {"label": it.get("label"), "score": it.get("score")}
                for it in raw_items
                if isinstance(it, dict)
            ][:6]
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
        if not ts:
            ts = _iso_from_epoch(mtime + off)
        records.append(
            {
                "cam": cname,
                "stem": stem,
                "frame": stem + ".jpg",  # 与 /api/response 的 frame 约定一致
                "ts": ts,
                "n_items": len(items),
                "items": items,
                "alert": alert,
                "url": "/api/saved/img?cam=%s&frame=%s" % (cname, stem + ".jpg"),
            }
        )
    records.sort(key=lambda r: r["ts"], reverse=True)  # ISO 串字典序 = 时间序
    return {
        "records": records,
        "cams": cams_present,
        "total": total,
        "scanned": len(entries),
        "oldest": records[-1]["ts"] if records else "",
        "newest": records[0]["ts"] if records else "",
    }


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

    # ---- 语言（ADR-013：中英适配；前端 api() 每次带 X-Lang 头）----
    def _lang(self) -> str:
        return i18n.pick_lang(self.headers)

    def _t(self, key: str, **params: Any) -> str:
        return i18n.fmt(key, self._lang(), **params)

    def _sep(self, kind: str) -> str:
        """列表/子句连接符按语言取：枚举 、/ , ；子句 ；/ ;。"""
        table = {
            "enum": ({"en": ", ", "zh": "、"}),
            "clause": ({"en": "; ", "zh": "；"}),
        }
        return table[kind][self._lang()]

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
            return None, self._t("err.cl_bad")
        if length <= 0:
            return {}, ""
        if length > 32 * 1024 * 1024:
            return None, self._t("err.body_big")
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, "JSON 解析失败：%s" % exc
        if not isinstance(obj, dict):
            return None, self._t("err.body_json")
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
                return self._err(401, self._t("err.token"))
            if path == "/api/status":
                return self._get_status()
            if path == "/api/config":
                return self._get_config()
            if path == "/api/logs":
                return self._get_logs()
            if path == "/api/recent":
                return self._get_recent()
            if path == "/api/snapshot":
                return self._get_snapshot()
            if path == "/api/saved/img":
                return self._get_saved_img()
            if path == "/api/saved":
                return self._get_saved()
            if path == "/api/response":
                return self._get_response()
            if path == "/api/retention":
                return self._get_retention()
            if path == "/api/files":
                return self._get_files()
            if path == "/api/file":
                return self._get_file()
            self._err(404, "not found")
        except Exception as exc:  # 全局兜底：任何异常都不许打爆服务
            self._err(500, "%s: %s" % (type(exc).__name__, exc))

    def do_POST(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            if not self._authorized():
                return self._err(401, self._t("err.token"))
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
            self._err(500, self._t("err.index_missing"))

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
                "journal_bytes": sysactions.journal_disk_bytes(),
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

    def _get_saved(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        try:
            n = int(q.get("n", "1000"))
        except ValueError:
            n = 1000
        scfg = cfg.sampler_cfg
        offset = self.server.cached_offset()  # type: ignore[attr-defined]
        if offset is None:
            offset = scfg.ts_offset_sec
        out = _saved_gallery(scfg.base_dir, n, q.get("cam", ""), offset)
        out["ok"] = True
        out["save_mode"] = scfg.save_mode
        self._send_json(out)

    def _get_saved_img(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        cam, frame = q.get("cam", ""), q.get("frame", "")
        if not _safe_component(cam) or not _safe_component(frame):
            return self._err(400, self._t("err.illegal_char"))
        stem = os.path.splitext(frame)[0]
        path = os.path.join(cfg.sampler_cfg.base_dir, "saved", cam, stem + ".jpg")
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return self._err(404, self._t("err.img_gone"))
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")  # 留存文件不改写，可缓存
        self.end_headers()
        self.wfile.write(data)

    def _get_files(self) -> None:
        """只读目录列表（ADR-009）。"""
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        try:
            n = int(q.get("n", "300") or 300)
        except ValueError:
            return self._err(400, self._t("err.n_int"))
        out = _file_list(
            cfg.sampler_cfg.base_dir, q.get("dir", ""), n, q.get("match", "")
        )
        self._send_json(out, 200 if out.get("ok") else 400)

    def _get_file(self) -> None:
        """单文件只读（ADR-009）：图片/JSON 直出，大文本用 tail=N 读末尾。"""
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        rel = q.get("path", "")
        if not rel:
            return self._err(400, self._t("err.no_path"))
        full = _resolve_under(cfg.sampler_cfg.base_dir, rel)
        if full is None:
            return self._err(
                400, self._t("err.path_not_allowed", roots=", ".join(FILE_ROOTS))
            )
        if not os.path.isfile(full):
            return self._err(404, self._t("err.file_gone"))
        try:
            size = os.path.getsize(full)
            tail = int(q.get("tail", "0") or 0)
        except (OSError, ValueError):
            return self._err(400, self._t("err.bad_param"))
        try:
            if tail > 0:
                if tail > FILE_TAIL_MAX:
                    return self._err(
                        400, self._t("err.tail_max", n=FILE_TAIL_MAX)
                    )
                data = _tail_bytes(full, tail)
            else:
                if size > FILE_MAX_BYTES:
                    return self._err(
                        413,
                        self._t(
                            "err.file_too_big",
                            size="%.1f" % (size / 1048576.0),
                            max="%.0f" % (FILE_MAX_BYTES / 1048576.0),
                        ),
                    )
                with open(full, "rb") as fh:
                    data = fh.read()
        except OSError as exc:
            return self._err(500, self._t("err.read_fail", e=exc))
        ctype = _FILE_EXT_TYPES.get(
            os.path.splitext(full)[1].lower(), "application/octet-stream"
        )
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if q.get("dl", "0") == "1":
            self.send_header(
                "Content-Disposition", 'attachment; filename="%s"' % os.path.basename(full)
            )
        self.end_headers()
        self.wfile.write(data)

    def _get_response(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        frame = q.get("frame", "")
        cam = q.get("cam", "front")
        if not frame:
            return self._err(400, self._t("err.no_frame"))
        redetect = q.get("redetect", "0") == "1"
        out = _response_detail(cfg, frame, cam, redetect)
        if not out.get("ok"):
            status = 404 if out.get("saved") is False else 400
            return self._err(status, out.get("error") or self._t("err.query_fail"))
        self._send_json(out)

    def _get_snapshot(self) -> None:
        """相机画面：raw/ 最新帧优先，ffmpeg 单次抓帧兜底（ADR-012）。"""
        from m20_ai_detect.snapshot import snapshot_frame

        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        cam = (self._query().get("cam") or "").strip()
        out = snapshot_frame(cfg.sampler_cfg, cam or None)
        if not out.get("ok"):
            code = 400 if out.get("bad_request") else 502
            if out.get("code"):
                params = {k: out[k] for k in ("cam", "cams", "src") if k in out}
                if isinstance(params.get("cams"), list):
                    params["cams"] = self._sep("enum").join(params["cams"])
                msg = self._t("snap." + str(out["code"]), **params)
            else:
                msg = out.get("error") or ""
            return self._err(code, msg or self._t("err.snap_fail"))
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
                "alert_labels": list(scfg.alert_labels),
                "alert_score": scfg.alert_score,
                "label_stats": _label_stats(cfg.base_dir),
                "saved_max_mb": round(scfg.saved_max_bytes / 1048576.0, 1),
                "saved_keep_days": scfg.saved_keep_days,
                "journal_bytes": sysactions.journal_disk_bytes(),
                "journal_service": sysactions.journal_service_usage(),
                "journald_managed": _read_journald_block(),
                "logrotate_rotate": _read_logrotate_rotate(),
                "note": self._t("ret.note"),
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
            return self._err(500, msg or self._t("svc.fail"))
        self._send_json({"ok": True, "action": action, "detail": msg})

    def _post_config(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        body, err = self._body_json()
        if err:
            return self._err(400, err)
        updates = body.get("updates")
        if not isinstance(updates, dict) or not updates:
            return self._err(400, self._t("err.updates_obj"))
        clean = {str(k): str(v) for k, v in updates.items()}
        if not all(k.startswith("M20AI_") for k in clean):
            return self._err(400, self._t("err.m20ai_only"))
        current = envfile.read_env(cfg.env_file)
        ok, errors = envfile.validate_env(current, clean)
        if not ok:
            return self._err(400, self._t("err.validate", detail=self._sep("clause").join(errors)))
        try:
            envfile.set_env_keys(cfg.env_file, clean)
        except (OSError, ValueError) as exc:
            return self._err(500, self._t("err.env_write", e=exc))
        restart = bool(body.get("restart", True))
        detail = self._t("cfg.written")
        if restart:
            # ADR-010：采集开关由用户掌握——配置改动只在采集运行时重启使其生效，
            # 采集关着时**不拉起**（旧行为会无条件 restart，把停着的采集启动）。
            active = sysactions.service_is_active()
            if active is True:
                ok, msg = sysactions.service_action("restart", cfg.helper)
                detail += self._t("cfg.restarted") if ok else self._t("cfg.restart_fail", msg=msg)
            elif active is False:
                detail += self._t("cfg.not_running")
            else:
                detail += self._t("cfg.unknown_state")
        else:
            detail += self._t("cfg.no_restart")
        self._send_json({"ok": True, "detail": detail, "applied": sorted(clean)})

    def _post_detect(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        q = self._query()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._err(400, self._t("err.cl_bad"))
        if length <= 0 or length > 20 * 1024 * 1024:
            return self._err(400, self._t("err.img_size"))
        jpeg = self.rfile.read(length)
        try:
            result = detect_single_frame(
                cfg.sampler_cfg,
                jpeg,
                cap=q.get("cap", ""),
                include_image=q.get("include_image", "1") != "0",
                save=q.get("save", "0") == "1",
                clock_offset=self.server.cached_offset(),  # type: ignore[attr-defined]
            )
        except Exception as exc:
            return self._err(500, self._t("err.detect_fail", e=exc))
        if not result.get("ok"):
            return self._err(502, result.get("error") or self._t("err.detect_bad"))
        self._send_json(result)

    def _post_retention(self) -> None:
        cfg: ConsoleConfig = self.server.cfg  # type: ignore[attr-defined]
        body, err = self._body_json()
        if err:
            return self._err(400, err)
        notes: List[str] = []
        restart_collect = bool(body.get("restart_collect"))

        # ---- env 级（ring / results keep / save mode / 关注目标）----
        env_updates = {}
        if "ring_max_mb" in body:
            env_updates["M20AI_RING_MAX_MB"] = str(body["ring_max_mb"])
        if "results_keep_days" in body:
            env_updates["M20AI_RESULTS_KEEP_DAYS"] = str(body["results_keep_days"])
        if "saved_max_mb" in body:
            env_updates["M20AI_SAVED_MAX_MB"] = str(body["saved_max_mb"])
        if "saved_keep_days" in body:
            env_updates["M20AI_SAVED_KEEP_DAYS"] = str(body["saved_keep_days"])
        if "save_mode" in body:
            mode = str(body["save_mode"]).strip().lower()
            if mode not in ("off", "alert", "any", "all"):
                return self._err(400, self._t("err.save_mode"))
            env_updates["M20AI_SAVE_MODE"] = mode
        if "alert_labels" in body:
            raw = body["alert_labels"]
            if isinstance(raw, (list, tuple)):
                labels = [str(x).strip() for x in raw]
            else:
                labels = [s.strip() for s in str(raw).split(",")]
            uniq: List[str] = []
            for s in labels:
                if s and s not in uniq:
                    uniq.append(s)
            if len(uniq) > _LABEL_MAX:
                return self._err(
                    400,
                    self._t("err.labels_max", max=_LABEL_MAX, n=len(uniq)),
                )
            bad = [s for s in uniq if not _LABEL_RE.match(s)]
            if bad:
                return self._err(
                    400,
                    self._t("err.label_bad", bad=self._sep("enum").join(bad[:5])),
                )
            env_updates["M20AI_ALERT_LABELS"] = ",".join(uniq)
        if "alert_score" in body:
            env_updates["M20AI_ALERT_SCORE"] = str(body["alert_score"]).strip()
        if env_updates:
            current = envfile.read_env(cfg.env_file)
            ok, errors = envfile.validate_env(current, env_updates)
            if not ok:
                return self._err(400, self._t("err.validate", detail=self._sep("clause").join(errors)))
            try:
                envfile.set_env_keys(cfg.env_file, env_updates)
            except (OSError, ValueError) as exc:
                return self._err(500, self._t("err.env_write", e=exc))
            if not restart_collect:
                notes.append(self._t("ret.env_written"))

        # ---- root 级（helper）----
        if "journal_vacuum" in body:
            fields = body["journal_vacuum"] or {}
            err = sysactions.check_vacuum(fields)
            if err:
                return self._err(400, err)
            ok, msg = sysactions.call_helper(
                "journal-vacuum", fields, cfg.base_dir, cfg.helper
            )
            notes.append(self._t("helper.vacuum_ok") if ok else self._t("helper.vacuum_fail", msg=msg))
        if "journald_limits" in body:
            fields = body["journald_limits"] or {}
            err = sysactions.check_journald_limits(fields)
            if err:
                return self._err(400, err)
            ok, msg = sysactions.call_helper(
                "journald-limits", fields, cfg.base_dir, cfg.helper
            )
            notes.append(self._t("helper.journald_ok") if ok else self._t("helper.journald_fail", msg=msg))
        if "logrotate_rotate" in body:
            fields = {"rotate": str(body["logrotate_rotate"])}
            err = sysactions.check_logrotate(fields)
            if err:
                return self._err(400, err)
            ok, msg = sysactions.call_helper(
                "logrotate-rotate", fields, cfg.base_dir, cfg.helper
            )
            notes.append(self._t("helper.logrotate_ok") if ok else self._t("helper.logrotate_fail", msg=msg))

        # ---- 数据清空（停采集 → 清空 → 恢复原状态；ADR-011）----
        kinds: List[str] = []
        if "purge" in body:
            raw_kinds = body["purge"]
            if not isinstance(raw_kinds, list) or not raw_kinds:
                return self._err(
                    400,
                    self._t("err.purge_array", scopes="/".join(PURGE_SCOPES)),
                )
            badk = [str(k) for k in raw_kinds if str(k) not in PURGE_SCOPES]
            if badk:
                return self._err(
                    400,
                    self._t(
                        "err.purge_kind",
                        bad=self._sep("enum").join(badk),
                        scopes="/".join(PURGE_SCOPES),
                    ),
                )
            for k in raw_kinds:
                if str(k) not in kinds:
                    kinds.append(str(k))
        if body.get("spool_clear") and "spool" not in kinds:  # 兼容旧字段
            kinds.append("spool")
        purged = False
        if kinds:
            ok, msg = _purge_with_restart(cfg, kinds, lang=self._lang())
            if not ok:
                return self._err(500, msg)
            notes.append(msg)
            purged = True
            _label_stats_cache["base"] = ""  # 今日标签统计缓存立即失效

        # ---- 采集重启（让 env 级改动即时生效；purge 已恢复过采集则跳过）----
        if restart_collect and not purged:
            active = sysactions.service_is_active()
            if active is True:
                ok, msg = sysactions.service_action("restart", cfg.helper)
                if ok:
                    notes.append(
                        self._t("ret.restarted_env") if env_updates else self._t("ret.restarted")
                    )
                else:
                    notes.append(self._t("ret.restart_fail", msg=msg))
            elif active is False:
                notes.append(self._t("ret.not_running"))
            else:
                notes.append(self._t("ret.unknown_state"))

        if not notes:
            return self._err(400, self._t("err.nothing"))
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
