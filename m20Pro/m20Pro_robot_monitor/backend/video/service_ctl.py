"""视频推流服务控制（2026-10-17 加）。

**为什么单开一层**：两条视频链路都以 root 运行，而控制台服务跑在普通用户
``user``。给控制台 root 或放开 systemctl 全权都不合适，于是把能力收成一个
只干视频服务这一件事的受控入口 ``/usr/local/sbin/m20-video-ctl``，
sudoers 只放行它（见 ``deploy/m20-video-ctl`` 与 ``deploy/sudoers-m20-video-ctl``）。

**两条链不是一回事**（参数用 ``local`` / ``relay``，别混）：

    local —— 厂商本地推流：``mediamtx`` + ``push_video.sh``
             把相机画面推到本机 MediaMTX。**控制台「相机画面」页靠它。**
    relay —— 自研外推中继：``m20video.service``（rtmp_1012）
             把 MediaMTX 的画面转发到远端 RTMP 服务器。
             关掉它**控制台画面照旧**，只是外部看不到。

**状态语义（比"进程在不在"更重要）**：本地推流有一个经典故障 ——
**进程活着但不出流**（gst 存活、mpph264enc 内部报 NULL，HLS 拉不到）。
所以 ``local.ready`` 判的是 **HLS 能否 200 拉到**，``local.stuck`` 专门标出
"有进程、没流"这个状态。只报进程数会把坏掉的链路显示成正常。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

from logging_setup import get_logger

logger = get_logger("video.service_ctl")

#: 受控提权入口（root:root 0755，内容见 deploy/m20-video-ctl）
HELPER = "/usr/local/sbin/m20-video-ctl"

#: 允许的目标与动作 —— 与 helper 内部白名单一一对应，两边都校验
TARGETS = ("local", "relay")
ACTIONS = ("start", "stop", "restart")

#: 中文标签（前端展示用；后端不给的话前端还得硬编码一份，迟早漂移）
TARGET_LABEL = {
    "local": "本地推流（控制台画面靠它）",
    "relay": "外推中继（转到远端 RTMP 服务器）",
}

#: 动作超时（秒）。restart local 内部要停 2s + 起 5s，留足余量。
_TIMEOUT = {"status": 25, "start": 30, "stop": 25, "restart": 40}


class VideoServiceError(Exception):
    """视频服务控制失败（未授权 / 入口缺失 / 执行失败）。"""

    def __init__(self, message: str, reason: str = "rejected", status: int = 400) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status


def helper_available() -> bool:
    return os.path.isfile(HELPER) and os.access(HELPER, os.X_OK)


def _run(args: List[str], timeout: float) -> str:
    """跑 helper（``sudo -n`` 非交互）。

    ``-n`` 是刻意的：**没配好 sudoers 时要立刻失败**，而不是挂在那儿等口令
    —— 后端线程被口令提示挂住比报错难查得多。
    """
    if not helper_available():
        raise VideoServiceError(
            "受控入口 %s 不存在或不可执行 —— 请先部署 deploy/m20-video-ctl" % HELPER,
            reason="HELPER_MISSING", status=503)

    cmd = ["sudo", "-n", HELPER] + list(args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise VideoServiceError("执行超时（%ss）：%s" % (timeout, " ".join(args)),
                                reason="TIMEOUT", status=504)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        # sudo 未授权时 stderr 形如 "sudo: a password is required"
        if "password is required" in err or "not allowed" in err.lower():
            raise VideoServiceError(
                "控制台未被授权调用 %s —— 需要安装 sudoers 白名单"
                "（deploy/sudoers-m20-video-ctl）" % HELPER,
                reason="NOT_AUTHORIZED", status=403)
        raise VideoServiceError(err or ("helper 退出码 %d" % proc.returncode),
                                reason="EXEC_FAILED", status=502)
    return proc.stdout


def _parse(text: str) -> Dict[str, Dict[str, Any]]:
    """``key=value`` 行 → ``{"local": {...}, "relay": {...}}``。

    值统一转成 ``int`` / ``bool`` / ``str``（helper 输出是裸文本，这里做归一化，
    免得前端拿到 "yes"/"no" 还要自己判断）。
    """
    out: Dict[str, Dict[str, Any]] = {"local": {}, "relay": {}}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        raw = raw.strip()
        if "." not in key:
            continue
        group, _, field = key.partition(".")
        if group not in out:
            continue
        if raw in ("yes", "no"):
            out[group][field] = (raw == "yes")
        elif raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            out[group][field] = int(raw)
        else:
            out[group][field] = raw
    return out


def _describe(state: Dict[str, Any]) -> Dict[str, Any]:
    """把裸状态翻译成"人话 + 是否正常"，前端不必自己再拼判断逻辑。"""
    local = state.get("local", {})
    relay = state.get("relay", {})
    # 分组整个缺失 = 上层没拿到数据，**不能说成"未运行"**（那是凭空断言）
    if not local:
        local = {"summary": "状态未知", "level": "off", "unknown": True}
    else:
        local = _local_view(local)
    if not relay:
        relay = {"summary": "状态未知", "level": "off", "unknown": True}
    else:
        relay = _relay_view(relay)
    return {"local": dict(local, label=TARGET_LABEL["local"]),
            "relay": dict(relay, label=TARGET_LABEL["relay"])}


def _local_view(local: Dict[str, Any]) -> Dict[str, Any]:
    ready = bool(local.get("ready"))
    stuck = bool(local.get("stuck"))
    if ready:
        local_summary, local_level = "在出流", "ok"
    elif stuck:
        # 这就是那个经典故障：进程在、流没有。措辞要能让用户直接对症下药。
        local_summary = "进程在但没出流（需重启推流）"
        local_level = "warn"
    else:
        local_summary, local_level = "未运行", "off"

    return dict(local, summary=local_summary, level=local_level)


def _relay_view(relay: Dict[str, Any]) -> Dict[str, Any]:
    unit = str(relay.get("unit", "unknown"))
    if unit == "active":
        summary = "运行中" + ("（目标可达）" if relay.get("target_tcp") else "（目标不可达）")
        level = "ok" if relay.get("target_tcp") else "warn"
    elif unit == "unknown":
        summary, level = "状态未知", "off"
    else:
        summary, level = "未运行（unit=%s）" % unit, "off"
    return dict(relay, summary=summary, level=level)


def status() -> Dict[str, Any]:
    """两条链的当前状态 + 人话摘要。"""
    raw = _parse(_run(["status"], _TIMEOUT["status"]))
    return {"ok": True, "targets": _describe(raw)}


def control(target: str, action: str, confirmed: bool = False) -> Dict[str, Any]:
    """启动 / 停止 / 重启某一条链，返回**执行后的新状态**（不是"已下发"）。"""
    if target not in TARGETS:
        raise VideoServiceError("未知目标 %r（只允许 %s）" % (target, "/".join(TARGETS)),
                                reason="BAD_TARGET")
    if action not in ACTIONS:
        raise VideoServiceError("未知动作 %r（只允许 %s）" % (action, "/".join(ACTIONS)),
                                reason="BAD_ACTION")
    # 停止是"让画面消失"的方向，不可逆感强（要等重新拉流才回来）→ 要确认
    if action == "stop" and not confirmed:
        raise VideoServiceError(
            "停止推流会让画面消失，需二次确认（confirmed=true）",
            reason="CONFIRM_REQUIRED", status=409)

    logger.info("视频服务控制: %s %s", action, target)
    raw = _parse(_run([action, target], _TIMEOUT[action]))
    out = _describe(raw)
    logger.info("视频服务控制完成: %s %s -> %s", action, target,
                out[target].get("summary"))
    return {"ok": True, "target": target, "action": action, "targets": out}
