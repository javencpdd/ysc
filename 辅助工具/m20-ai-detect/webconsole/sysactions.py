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


def service_is_active(runner: Runner = default_runner) -> Optional[bool]:
    """采样器是否在运行：True / False；无法确认时 None。不提权。

    与 service_status 的差异：不依赖 shutil.which（测试可注入 runner 模拟任何环境），
    机器上没有 systemctl（rc=127）或命令超时时返回 None——调用方据此走保守路径
    （不碰服务直接清，见 server._purge_with_restart 的说明）。
    activating/reloading 视为在运行（马上可停）；deactivating 视为未运行。
    """
    rc, out, _ = runner(["systemctl", "is-active", SERVICE], 10)
    val = (out or "").strip().lower()
    if val in ("active", "reloading", "activating"):
        return True
    if val in ("inactive", "failed", "deactivating"):
        return False
    return None


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
    """`journalctl --disk-usage` 原始输出（整句英文原文）。

    仅在需要原文时使用；界面展示请用 journal_disk_bytes()（结构化、可本地化）。
    """
    rc, out, _ = runner(["journalctl", "--disk-usage"], 15)
    return out.strip() if rc == 0 else "unknown"


# journalctl --disk-usage 的英文原文形如：
#   "Archived and active journals take up 208.0M in the file system."
# 注意：原文单位**不带 B**（`M`/`K`/`G`），但也兼容带 B 的写法（`MB`/`KB`）与
# 无单位（纯 B）。解析出字节数交给前端按语言渲染（ADR-013：界面不直接展示系统英文原文）。
_DU_RE = re.compile(
    r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>B|[KMGTP]B?)\b", re.IGNORECASE
)
_DU_UNIT = {
    "B": 1,
    "K": 1024, "KB": 1024,
    "M": 1024 ** 2, "MB": 1024 ** 2,
    "G": 1024 ** 3, "GB": 1024 ** 3,
    "T": 1024 ** 4, "TB": 1024 ** 4,
    "P": 1024 ** 5, "PB": 1024 ** 5,
}


def journal_disk_bytes(runner: Runner = default_runner) -> Optional[int]:
    """解析 journal 占用字节数；失败/无法解析返回 None（前端显示 –）。

    保留 float→int 的中间步骤：原文是 "208.0M" 这类带小数的可读值。
    ⚠️ `journalctl --disk-usage` **会忽略 -u 等过滤器**（systemd 明确行为），
    返回值是**整机**所有单元的合计——要区分"本服务占多少"请用
    journal_service_usage()（按行数/文本量估算）。
    """
    rc, out, _ = runner(["journalctl", "--disk-usage"], 15)
    if rc != 0:
        return None
    m = _DU_RE.search(out)
    if not m:
        return None
    unit = m.group("unit").upper()
    if unit not in _DU_UNIT:
        return None
    return int(round(float(m.group("size")) * _DU_UNIT[unit]))


def journal_service_usage(
    unit: str = "m20-ai-detect", runner: Runner = default_runner
) -> Optional[Dict[str, int]]:
    """单个 unit 在 journal 里的体量估算：{"lines": N, "bytes": M}。

    journal 文件按时间分片、各单元混写，**没有**"某 unit 占多少磁盘"的官方命令，
    这里用 `journalctl -u <unit> -o cat` 的输出做文本量估算（未计压缩，只作量级参考）。
    失败返回 None。用于解释"整机 journal 里本服务占多少"（实测：m20-ai-detect
    仅约 0.2%，大头是厂商 rsdriver 驱动日志）。
    """
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", unit):
        return None
    rc, out, _ = runner(
        ["journalctl", "-u", unit, "--no-pager", "-o", "cat"], 20
    )
    if rc != 0:
        return None
    lines = sum(1 for ln in out.splitlines() if ln.strip())
    return {"lines": lines, "bytes": len(out.encode("utf-8"))}


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
_SIZE_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]*)$")
_TIME_RE = re.compile(r"^([0-9]+)\s*([A-Za-z]*)$")
_SIZE_UNITS = ("K", "M", "G", "T")
_TIME_UNITS = ("MS", "S", "M", "H", "D", "W", "Y")


def _norm_size(value: str, what: str) -> Tuple[bool, str]:
    """体积归一化（ADR-010）：裸数字补默认单位 M；单位大小写归一；非法则报错。"""
    v = (value or "").strip()
    m = _SIZE_RE.match(v)
    if not m:
        return False, "%s 格式错误：%r（可写 200 / 200M / 1G / 512K；裸数字按 MB 解释）" % (what, value)
    num, unit = m.group(1), m.group(2).upper()
    if not unit:  # 裸数字 → 默认 MB（systemd 的 size 必须带后缀）
        return True, num + "M"
    if unit not in _SIZE_UNITS:
        return False, "%s 单位无法识别：%r（合法：K/M/G/T；裸数字按 MB）" % (what, value)
    return True, num + unit


def _norm_time(value: str, what: str) -> Tuple[bool, str]:
    """时长归一化（ADR-010）：裸数字补默认单位 d。

    ⚠️ systemd 的裸数字时长是**秒**——用户填 "7" 的意图几乎总是 7 天，
    这里统一重解释为 "7d"，避免 "7" 变成 "7 秒" 的静默事故。
    """
    v = (value or "").strip()
    m = _TIME_RE.match(v)
    if not m:
        return False, "%s 格式错误：%r（可写 7 / 7d / 24h / 2w；裸数字按天解释）" % (what, value)
    num, unit = m.group(1), m.group(2).upper()
    if not unit:  # 裸数字 → 默认天（systemd 默认秒，必须纠正）
        return True, num + "d"
    if unit not in _TIME_UNITS:
        return False, "%s 单位无法识别：%r（合法：s/m/h/d/w/y；裸数字按天）" % (what, value)
    return True, num + unit.lower()


def check_vacuum(fields: Dict[str, str]) -> Optional[str]:
    """vacuum 预校验 + 单位归一化（就地改写 fields，ADR-010）。

    size 或 time 二选一；裸数字分别按 MB / 天 解释。
    """
    size, t = fields.get("size", ""), fields.get("time", "")
    if bool(size) == bool(t):
        return "size 与 time 必须二选一"
    if size:
        ok, v = _norm_size(size, "size")
        if not ok:
            return v
        fields["size"] = v
    else:
        ok, v = _norm_time(t, "time")
        if not ok:
            return v
        fields["time"] = v
    return None


def check_journald_limits(fields: Dict[str, str]) -> Optional[str]:
    """journald 持久上限预校验 + 单位归一化（就地改写 fields，ADR-010）。"""
    use, keep = fields.get("SystemMaxUse", ""), fields.get("MaxRetentionSec", "")
    if use:
        ok, v = _norm_size(use, "SystemMaxUse")
        if not ok:
            return v
        fields["SystemMaxUse"] = v
    if keep:
        ok, v = _norm_time(keep, "MaxRetentionSec")
        if not ok:
            return v
        fields["MaxRetentionSec"] = v
    if not use and not keep:
        return "至少填一项"
    return None


def check_logrotate(fields: Dict[str, str]) -> Optional[str]:
    n = fields.get("rotate", "")
    if not n.isdigit() or not 1 <= int(n) <= 365:
        return "rotate 必须是 1-365 的整数（份数，无单位；每份=一天的日志文件）"
    return None
