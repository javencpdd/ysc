"""systemctl / journalctl / root helper 的动作封装。

提权模型（ADR-005）：
  * 状态查询（systemctl is-active、journalctl 读）**不提权**——user 在 adm 组；
  * 服务动作与 /etc 写入走唯一的 root helper（/usr/local/sbin/m20-ai-console-helper），
    sudoers 精确白名单（无通配符自由参数），参数经 req 文件传递并在 helper 内校验；
  * 所有 subprocess 调用收敛在本模块，测试可注入假 runner。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

SERVICE = "m20-ai-detect"

Runner = Callable[[List[str], float], Tuple[int, str, str]]


def default_runner(cmd: List[str], timeout: float = 15.0) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %.0fs" % timeout
    except OSError as exc:
        return 127, "", str(exc)


# ---------------------------------------------------------------- 服务状态
def service_status(runner: Runner = default_runner) -> str:
    """返回 active / inactive / failed / unknown。不提权。"""
    if not shutil.which("systemctl"):
        return "unknown"
    rc, out, _ = runner(["systemctl", "is-active", SERVICE], 10)
    return out.strip() if rc == 0 else (out.strip() or "unknown")


def service_action(action: str, helper: str, runner: Runner = default_runner) -> Tuple[bool, str]:
    """start/stop/restart —— 经 sudo + root helper 白名单。"""
    if action not in ("start", "stop", "restart"):
        return False, "非法动作：%s" % action
    rc, out, err = runner(["sudo", "-n", helper, "svc-" + action], 20)
    ok = rc == 0
    return ok, (out + err).strip()[-400:]


# ---------------------------------------------------------------- 日志
def journal_lines(n: int = 200, runner: Runner = default_runner) -> List[str]:
    """读本服务 journal（adm 组免提权）。返回原始行列表（最新在末尾）。"""
    n = max(1, min(int(n), 2000))
    rc, out, _ = runner(
        ["journalctl", "-u", SERVICE, "-n", str(n), "--no-pager", "-o", "short-iso"], 15
    )
    if rc != 0:
        return []
    return [ln for ln in out.splitlines() if ln.strip()]


def journal_disk_usage(runner: Runner = default_runner) -> str:
    rc, out, _ = runner(["journalctl", "--disk-usage"], 15)
    return out.strip() if rc == 0 else "unknown"


# ---------------------------------------------------------------- helper 请求
def write_req(base_dir: str, sub: str, fields: Dict[str, str]) -> str:
    """把 helper 参数写进 tmp/console-<sub>.req（helper 以 root 读后即删）。"""
    req_dir = os.path.join(base_dir, "tmp")
    os.makedirs(req_dir, exist_ok=True)
    path = os.path.join(req_dir, "console-%s.req" % sub)
    with open(path, "w", encoding="utf-8") as fh:
        for k, v in fields.items():
            fh.write("%s=%s\n" % (k, v))
    return path


def call_helper(sub: str, fields: Dict[str, str], base_dir: str, helper: str,
                runner: Runner = default_runner) -> Tuple[bool, str]:
    """写 req 文件并调 root helper。helper 内部对值做严格校验。"""
    if not re.fullmatch(r"[a-z-]+", sub):
        return False, "非法 helper 子命令"
    try:
        write_req(base_dir, sub, fields)
    except OSError as exc:
        return False, "写请求文件失败：%s" % exc
    rc, out, err = runner(["sudo", "-n", helper, sub], 30)
    return rc == 0, (out + err).strip()[-400:]


# ---------------------------------------------------------------- 值格式预校验
_SIZE_RE = re.compile(r"^[0-9]+(\.[0-9]+)?[KMGT]?$")
_TIME_RE = re.compile(r"^[0-9]+(ms|s|m|h|d|w|y)?$")


def check_vacuum(fields: Dict[str, str]) -> Optional[str]:
    """vacuum 请求预校验：size 或 time 二选一，格式不对返回错误信息。"""
    size, t = fields.get("size", ""), fields.get("time", "")
    if bool(size) == bool(t):
        return "size 与 time 必须二选一"
    if size and not _SIZE_RE.match(size):
        return "size 格式错误（如 200M / 1G）"
    if t and not _TIME_RE.match(t):
        return "time 格式错误（如 7d / 24h）"
    return None


def check_journald_limits(fields: Dict[str, str]) -> Optional[str]:
    use, keep = fields.get("SystemMaxUse", ""), fields.get("MaxRetentionSec", "")
    if use and not _SIZE_RE.match(use):
        return "SystemMaxUse 格式错误（如 200M）"
    if keep and not _TIME_RE.match(keep):
        return "MaxRetentionSec 格式错误（如 7d）"
    if not use and not keep:
        return "至少填一项"
    return None


def check_logrotate(fields: Dict[str, str]) -> Optional[str]:
    n = fields.get("rotate", "")
    if not n.isdigit() or not 1 <= int(n) <= 365:
        return "rotate 必须是 1-365 的整数"
    return None
