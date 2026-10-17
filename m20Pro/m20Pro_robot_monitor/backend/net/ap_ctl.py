"""M20 自身 WiFi 热点的受控读写（2026-10-18 加）。

**为什么单开一层**：改热点要 root，控制台跑在普通用户 ``user``。给 nmcli
全权不合适，于是收成只干这一件事的受控入口 ``/usr/local/sbin/m20-ap-ctl``，
sudoers 只放行它（见 ``deploy/m20-ap-ctl`` 与 ``deploy/sudoers-m20-ap-ctl``）。

**硬件前提（2026-10-18 真机取证，决定了能改什么）**：

    wlan0（AP，10.21.41.0/24）与 p2p0（上行，192.168.0.196）
    **共用同一块射频 phy#0** —— AP 的信道被上行绑架：配置里写 2.4G，
    实际跟着上行跑在 5.2GHz 信道 40。

由此定出能力边界：

  - ✅ **读当前 SSID / 密码**：操作者要拿密码连新设备，为它去 SSH
    ``sudo cat`` 反而更绕。控制台已暴露视频/遥测/运动控制，读密码的边际风险
    低于这些，故 status 回显 ``ap.password``（前端默认掩码）。
    控制台走 HTTP（196 时钟异常导致 HTTPS 起不来），这点已在界面注明。
  - ✅ **改 SSID / 改密码**：只改信标内容，不动射频，实测上行全程不掉。
    **二者可单独给**：留空的那个字段不会被写，实测只改 SSID 时密码文件
    校验和不变（2026-10-18 真机验证）。
  - ❌ **改频段 / 改信道**：会与上行抢射频，AP 起不来或直接拖垮上行
    —— 所以本模块**根本不提供**这两个字段，而不是"提供了但提示别改"。

**风险不对称，这是本模块存在的核心理由**：写热点失败的最坏结果不是
"热点没了"，而是"上行没了"——而上行正是我们 SSH 与状态链路的通路，
机器人会当场失联。所以改动必须是
``先摘 AP → 改配置 → 重新激活 → 轮询到 activated → 复查上行 → 失败回滚``
这一整条闭环，且**上行的优先级高于 AP**（上行掉了就回滚 AP 去救上行）。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

from logging_setup import get_logger

logger = get_logger("net.ap_ctl")

#: 受控提权入口（root:root 0755，内容见 deploy/m20-ap-ctl）
HELPER = "/usr/local/sbin/m20-ap-ctl"

#: SSID / WPA 密码的合法长度（WPA-PSK 规范要求；helper 侧会再校验一次，
#: 这里是"先手"——在本地就把明显非法的挡掉，省一次提权调用）
SSID_MIN_LEN, SSID_MAX_LEN = 1, 32
PASSWORD_MIN_LEN, PASSWORD_MAX_LEN = 8, 63
#: SSID 只挡**不可打印字符**：换行会把 helper 的 key=value 输出搅烂，
#: 而挡掉点号之类的会让车上的原始 SSID（CA9B_NO.1273_24G）连还原都做不到。
_SSID_PRINTABLE = set(chr(c) for c in range(0x20, 0x7F))

#: 超时（秒）。set 内部含 1s down + 最多 25s 等 AP + 状态复查，给足余量。
_TIMEOUT = {"status": 20, "set": 75}

#: 必须按**字符串**解析的字段（见 _parse 里的说明）。密码 "00123456" 走 int()
#: 会丢前导零；连接名理论上也可能是纯数字（虽现实中不是）。
_STR_FIELDS = {("ap", "password"), ("ap", "con"), ("uplink", "con")}


class ApControlError(Exception):
    """热点读写失败。"""

    def __init__(self, message: str, reason: str = "rejected",
                 status: int = 400) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status


def helper_available() -> bool:
    return os.path.isfile(HELPER) and os.access(HELPER, os.X_OK)


def _run(args: List[str], timeout: float, stdin_data: str = "") -> str:
    """跑 helper（``sudo -n`` 非交互）。

    ``-n`` 是刻意的：**没配好 sudoers 时要立刻失败**，而不是挂住等口令
    —— 后端线程被口令提示挂住比报错难查得多。
    """
    if not helper_available():
        raise ApControlError(
            "受控入口 %s 不存在或不可执行 —— 请先部署 deploy/m20-ap-ctl" % HELPER,
            reason="HELPER_MISSING", status=503)

    cmd = ["sudo", "-n", HELPER] + list(args)
    try:
        proc = subprocess.run(cmd, input=stdin_data, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ApControlError("执行超时（%ss）：%s" % (timeout, " ".join(args)),
                             reason="TIMEOUT", status=504)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if "password is required" in err or "not allowed" in err.lower():
            raise ApControlError(
                "控制台未被授权调用 %s —— 需要安装 sudoers 白名单"
                "（deploy/sudoers-m20-ap-ctl）" % HELPER,
                reason="NOT_AUTHORIZED", status=403)
        # helper 被拒时会在 stdout 留 ap.set_reason=xxx，比退出码有用得多
        raise ApControlError(err or ("helper 退出码 %d" % proc.returncode),
                             reason=_reason_from(proc.stdout), status=502)
    return proc.stdout


def _reason_from(text: str) -> str:
    """从 helper 输出里取结构化原因码（CONFIRM_REQUIRED / BAD_SSID_LENGTH ...）。"""
    for line in (text or "").splitlines():
        key, _, val = line.partition("=")
        if key.strip() == "ap.set_reason" and val.strip():
            return val.strip()
    return "EXEC_FAILED"


def _parse(text: str) -> Dict[str, Dict[str, Any]]:
    """``key=value`` 行 → ``{"ap": {...}, "uplink": {...}}``。"""
    out: Dict[str, Dict[str, Any]] = {"ap": {}, "uplink": {}}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key, raw = key.strip(), raw.strip()
        if "." not in key:
            continue
        group, _, field = key.partition(".")
        if group not in out:
            continue
        # ⚠️ 这几个字段**即使是纯数字也必须按字符串保留**：密码 "00123456"
        #    被 int() 掉会丢前导零，用户照着界面显示的去输就连不上热点。
        #    （2026-10-18 加密码回显时发现，已加测试锁住。）
        if (group, field) in _STR_FIELDS:
            out[group][field] = raw
        elif raw in ("yes", "no"):
            out[group][field] = (raw == "yes")
        elif raw.isdigit():
            out[group][field] = int(raw)
        else:
            out[group][field] = raw
    return out


def _describe(raw: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ap = raw.get("ap") or {}
    uplink = raw.get("uplink") or {}
    # 分组整个缺失 = 上层没拿到数据，**不能说成"没开热点"**（那是凭空断言）
    if not ap:
        ap = {"summary": "状态未知", "level": "off", "unknown": True}
    else:
        ap = _ap_view(ap)
    if not uplink:
        uplink = {"summary": "状态未知", "level": "off", "unknown": True}
    else:
        uplink = _uplink_view(uplink)
    return {"ap": ap, "uplink": uplink}


def _ap_view(ap: Dict[str, Any]) -> Dict[str, Any]:
    activated = str(ap.get("state", "")) == "activated"
    if activated:
        summary = "已开启（%s）" % (ap.get("ssid") or "无 SSID")
        level = "ok"
    elif str(ap.get("state", "")) == "no_ap_connection":
        summary, level = "本机未配置热点连接", "off"
    else:
        summary, level = "未开启", "off"
    # 反直觉事实直接摆出来，免得用户照着配置里的 2.4G 去排查
    shared = ap.get("shared_radio")
    if shared == 1:
        summary += " · 与上行共用射频，信道跟随上行"
    return dict(ap, summary=summary, level=level)


def _uplink_view(uplink: Dict[str, Any]) -> Dict[str, Any]:
    state = str(uplink.get("state", ""))
    if state.startswith("100"):
        summary = "已连接（%s）" % (uplink.get("con") or uplink.get("dev") or "")
        level = "ok"
    else:
        summary = "未连接（%s）" % (state or "unknown")
        level = "warn"
    return dict(uplink, summary=summary, level=level)


def status() -> Dict[str, Any]:
    """热点 + 上行的当前状态（含人话摘要）。"""
    return {"ok": True, **_describe(_parse(_run(["status"], _TIMEOUT["status"])))}


def set_ap(ssid: Optional[str] = None, password: Optional[str] = None,
           confirmed: bool = False) -> Dict[str, Any]:
    """改热点的 SSID / 密码，返回**执行后的新状态**（不是"已下发"）。

    ``applied`` 才算改成了；``rolled_back`` 说明车侧拒绝了、已自动还原，
    **上行掉线会一路走回滚**——这是最坏情况的自救路径。
    """
    if ssid is None and password is None:
        raise ApControlError("至少要给 ssid 或 password 中的一个",
                             reason="NOTHING_TO_SET", status=400)
    if not confirmed:
        raise ApControlError(
            "改热点会让已连设备掉线，需二次确认（confirmed=true）",
            reason="CONFIRM_REQUIRED", status=409)
    if ssid is not None:
        ssid = str(ssid).strip()
        if not (SSID_MIN_LEN <= len(ssid) <= SSID_MAX_LEN):
            raise ApControlError(
                "SSID 长度需 %d~%d 个字符，收到 %d 个"
                % (SSID_MIN_LEN, SSID_MAX_LEN, len(ssid)),
                reason="BAD_SSID_LENGTH", status=400)
        bad = sorted(set(ssid) - _SSID_PRINTABLE)
        if bad:
            raise ApControlError("SSID 含不可打印字符",
                                 reason="BAD_SSID_CHARS", status=400)
    if password is not None:
        password = str(password)
        if not (PASSWORD_MIN_LEN <= len(password) <= PASSWORD_MAX_LEN):
            raise ApControlError(
                "WPA 密码需 %d~%d 位，收到 %d 位"
                % (PASSWORD_MIN_LEN, PASSWORD_MAX_LEN, len(password)),
                reason="BAD_PASSWORD_LENGTH", status=400)

    # ★ 新值走 stdin，不进命令行：密码进 argv 会被 ps 看见
    lines = []
    if ssid is not None:
        lines.append("ssid=%s" % ssid)
    if password is not None:
        lines.append("password=%s" % password)
    text = _run(["set", "--confirmed"], _TIMEOUT["set"],
                stdin_data="\n".join(lines) + "\n")

    parsed = _parse(text)
    result, reason = "", ""
    for line in (text or "").splitlines():
        key, _, val = line.partition("=")
        if key.strip() == "ap.set_result":
            result = val.strip()
        elif key.strip() == "ap.set_reason":
            reason = val.strip()
    logger.info("热点设置: %s %s", result or "unknown", reason)
    return {"ok": result == "applied", "result": result, "reason": reason,
            **_describe(parsed)}
