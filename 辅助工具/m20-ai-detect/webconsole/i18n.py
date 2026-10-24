"""控制台 server 侧用户可见文案的中英目录（ADR-013：界面中英适配）。

语言来源：请求头 ``X-Lang``（``zh`` 默认 / ``en``），前端 ``api()`` 每次请求自动带上。

覆盖边界（有意为之）：
  * 本目录覆盖 **server.py 自身拼装**的 detail / notes / error；
  * 核心模块（config / envfile / sysactions / store / capture）与 snapshot 的
    "来源文案"原文保留（snapshot 带 ``code``，由 server 映射成本目录）；
  * 前端静态文案走 ``webconsole/static/index.html`` 内嵌的 i18n JSON，
    与本目录同源维护（单测保证两边键集合一致、无漏译）。
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

#: 键 → (中文, English)。``{name}`` 为占位符，由 fmt() 用关键字参数替换。
MSG: Dict[str, Tuple[str, str]] = {
    # ---- 通用错误 ----
    "err.token": ("token 不符", "Invalid token"),
    "err.not_found": ("not found", "not found"),
    "err.index_missing": ("static/index.html 缺失", "static/index.html missing"),
    "err.illegal_char": ("cam/frame 含非法字符", "Illegal characters in cam/frame"),
    "err.img_gone": ("图片不存在或已被留存清理删除", "Image not found (deleted by a purge?)"),
    "err.n_int": ("n 必须是整数", "n must be an integer"),
    "err.no_path": ("缺少 path 参数", "Missing the path parameter"),
    "err.path_not_allowed": (
        "路径不在只读白名单内（允许根：{roots}）",
        "Path is outside the read-only whitelist (allowed roots: {roots})",
    ),
    "err.file_gone": ("文件不存在或不是普通文件", "File not found or not a regular file"),
    "err.bad_param": ("参数非法", "Invalid parameter"),
    "err.tail_max": ("tail 不得超过 {n} 行", "tail must not exceed {n} lines"),
    "err.file_too_big": (
        "文件 {size} MB 超过直读上限 {max} MB，请改用 tail=N 读末尾",
        "File is {size} MB, over the {max} MB read limit; use tail=N instead",
    ),
    "err.read_fail": ("读取失败：{e}", "Read failed: {e}"),
    "err.no_frame": ("缺少 frame 参数", "Missing the frame parameter"),
    "err.query_fail": ("查询失败", "Query failed"),
    "err.snap_fail": ("抓帧失败", "Snapshot failed"),
    "err.body_json": ("请求体必须是 JSON object", "Request body must be a JSON object"),
    "err.updates_obj": ("updates 必须是非空 object", "updates must be a non-empty object"),
    "err.m20ai_only": ("只允许 M20AI_* 键", "Only M20AI_* keys are allowed"),
    "err.validate": ("配置校验失败：{detail}", "Config validation failed: {detail}"),
    "err.env_write": ("写入 env 失败：{e}", "Failed to write env: {e}"),
    "err.cl_bad": ("Content-Length 非法", "Invalid Content-Length"),
    "err.body_big": ("请求体过大", "Request body too large"),
    "err.labels_max": (
        "关注目标最多 {max} 个（当前填了 {n} 个）",
        "At most {max} watch targets (you entered {n})",
    ),
    "err.label_bad": (
        "标签只允许英文字母/数字/. _ -（最长 40 字符），非法：{bad}",
        "Labels may only contain letters/digits/. _ - (max 40 chars); invalid: {bad}",
    ),
    "err.img_size": ("图片大小必须在 0-20MB", "Image size must be 0-20 MB"),
    "err.detect_fail": ("检测失败：{e}", "Detection failed: {e}"),
    "err.detect_bad": ("检测失败", "Detection failed"),
    "err.save_mode": (
        "save_mode 必须是 off/alert/any/all 之一",
        "save_mode must be one of off/alert/any/all",
    ),
    "err.purge_array": (
        "purge 必须是非空数组（可选：{scopes}）",
        "purge must be a non-empty array (allowed: {scopes})",
    ),
    "err.purge_kind": (
        "purge 含未知类别：{bad}（可选：{scopes}）",
        "purge contains unknown kinds: {bad} (allowed: {scopes})",
    ),
    "err.nothing": ("没有可保存的项", "Nothing to save"),
    # ---- 视频源管理（POST /api/sources，ADR-016）----
    "src.action_bad": (
        "未知动作 {action}（可用：{actions}）",
        "Unknown action {action} (allowed: {actions})",
    ),
    "src.name_required": ("缺少 name 字段（源逻辑名）", "Missing the name field"),
    "src.name_bad": (
        "源名 {name} 非法：只能含字母/数字/下划线/连字符，最长 32 位，且以字母或数字开头",
        "Invalid source name {name}: letters/digits/_/- only, max 32 chars, starting with a letter or digit",
    ),
    "src.dup": ("源 {name} 已存在（改地址请用 update）", "Source {name} already exists (use update to change it)"),
    "src.last_one": (
        "至少保留一路视频源（全删掉采集无从开始）",
        "Keep at least one source (the sampler cannot run with none)",
    ),
    "src.fps_bad": (
        "fps={v} 不是数字（范围 0~30；留空 = 继承全局）",
        "fps={v} is not a number (0-30; empty = inherit the global value)",
    ),
    "src.scope_bad": (
        "scope 只能是 local / auto / host:<ip>[:port]",
        "scope must be local / auto / host:<ip>[:port]",
    ),
    "src.timeout_bad": ("timeout_s / budget_s 不是数字", "timeout_s / budget_s is not a number"),
    "src.written": ("已写入 env", "Saved to env"),
    # ---- 快照（snapshot.py 的 code → 本目录）----
    "snap.no_cameras": (
        "没有启用任何相机（在「相机与采集」里勾选前视/后视后保存）",
        "No camera is enabled (check front/back in Cameras & capture, then save)",
    ),
    "snap.unknown_cam": (
        "未知相机 {cam}（可用：{cams}）",
        "Unknown camera {cam} (available: {cams})",
    ),
    "snap.grab_failed": (
        "抓帧失败：源不可达且无历史帧（{src}）",
        "Snapshot failed: source unreachable and no cached frame ({src})",
    ),
    # ---- 服务动作 ----
    "svc.fail": ("动作失败", "Action failed"),
    # ---- POST /api/config 的 detail ----
    "cfg.written": ("已写入 env", "Saved to env"),
    "cfg.restarted": ("；已重启采集，改动生效", "; collector restarted, changes applied"),
    "cfg.restart_fail": (
        "；重启采集失败：{msg}",
        "; failed to restart the collector: {msg}",
    ),
    "cfg.not_running": (
        "；采集未运行（不自动拉起），改动将在下次开启采集时生效",
        "; collector not running (not auto-started); changes apply the next time you start it",
    ),
    "cfg.unknown_state": (
        "；未能确认采集状态，请手动重启采集使改动生效",
        "; could not confirm collector state; restart it manually to apply changes",
    ),
    "cfg.no_restart": ("；未重启（重启采集后生效）", "; not restarted (restart the collector to apply)"),
    # ---- GET /api/retention 的 note ----
    "ret.note": (
        "env 级改动重启采样器后生效；journald/logrotate 级立即生效",
        "env-level changes apply after restarting the sampler; journald/logrotate apply immediately",
    ),
    # ---- 数据清空（_purge_with_restart）----
    "purge.stop_fail": (
        "停采集失败，未清任何数据：{msg}",
        "Failed to stop the collector; nothing was purged: {msg}",
    ),
    "purge.fail_restored": (
        "清空失败：{e}（采集已尝试恢复启动）",
        "Purge failed: {e} (tried to restart the collector)",
    ),
    "purge.fail": ("清空失败：{e}", "Purge failed: {e}"),
    "purge.kind.saved": ("saved/ 留存图片", "saved/ retained images"),
    "purge.kind.results": ("results/ 检测记录", "results/ detection records"),
    "purge.kind.raw": ("raw/ 原始帧", "raw/ raw frames"),
    "purge.kind.spool": ("spool/ 积压帧", "spool/ pending frames"),
    "purge.part": ("{label} {files} 个文件（{size}）", "{label}: {files} files ({size})"),
    "purge.head": ("已清空：{parts}", "Purged: {parts}"),
    "purge.restarted": ("；采集已重启恢复", "; collector restarted"),
    "purge.restore_fail": (
        "；⚠ 恢复采集失败：{msg}（请手动开启：aiDetect collect on）",
        "; ⚠ failed to restore the collector: {msg} (start it manually: aiDetect collect on)",
    ),
    "purge.idle": ("；采集未运行，未做启停", "; collector was not running; left untouched"),
    "purge.unknown": ("；未能确认采集状态，未做启停", "; could not confirm collector state; left untouched"),
    # ---- helper 动作的 note ----
    "helper.vacuum_ok": ("journal vacuum 已执行", "journal vacuum executed"),
    "helper.vacuum_fail": ("vacuum 失败：{msg}", "vacuum failed: {msg}"),
    "helper.journald_ok": ("journald 上限已更新", "journald limits updated"),
    "helper.journald_fail": ("journald 更新失败：{msg}", "journald update failed: {msg}"),
    "helper.logrotate_ok": ("logrotate 轮转数已更新", "logrotate rotation updated"),
    "helper.logrotate_fail": ("logrotate 更新失败：{msg}", "logrotate update failed: {msg}"),
    # ---- POST /api/retention 的其它 note ----
    "ret.env_written": ("env 级已写入（重启采集后生效）", "Saved to env (restart the collector to apply)"),
    "ret.restarted_env": ("已重启采集，env 级改动即时生效", "Collector restarted; env changes applied"),
    "ret.restarted": ("已重启采集", "Collector restarted"),
    "ret.restart_fail": (
        "重启采集失败：{msg}（改动将在下次开启采集时生效）",
        "Failed to restart the collector: {msg} (changes apply next time it starts)",
    ),
    "ret.not_running": (
        "采集未运行；env 级改动将在下次开启采集时生效",
        "Collector not running; env changes apply next time it starts",
    ),
    "ret.unknown_state": (
        "未能确认采集状态；请用上方「采集开关」重启采集使改动生效",
        "Could not confirm collector state; restart it via the switch above to apply changes",
    ),
}


def pick_lang(headers: Any = None) -> str:
    """从请求头取语言：默认 zh；X-Lang 以 en 开头才返回 en；其余回退 zh。"""
    try:
        raw = (headers.get("X-Lang") or "").strip().lower()
    except Exception:
        return "zh"
    return "en" if raw.startswith("en") else "zh"


def fmt(key: str, lang: str = "zh", **params: Any) -> str:
    """取文案并按语言渲染；缺键回退为键名（便于测试发现漏译）。"""
    pair = MSG.get(key)
    if pair is None:
        return key
    text = pair[1] if lang == "en" else pair[0]
    for name, value in params.items():
        text = text.replace("{%s}" % name, str(value))
    return text
