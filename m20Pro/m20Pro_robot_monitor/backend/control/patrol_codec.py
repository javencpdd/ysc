"""PatrolDevice 指令编解码（PLAN §10.3 指令全集）。

帧头编码复用 ``ingestion.asdu_parser.encode_frame`` —— 帧格式只写一处，避免两套实现漂移。

指令值域一律以 docs/04 §1.2 原文为准（v1.2 协议事实修正）：
- 运动状态转换 (2/22) ``MotionParam``: 0/1/2/3/4/17（旧稿 -2/-1/5 不见于文档，勿用）
- 步态切换 (2/23) ``GaitParam``: 0x1001/0x1003/0x3002/0x3003（字段名是 GaitParam，不是 Gait）
- 六轴轴指令 (2/21) X/Y/Z/Roll/Pitch/Yaw ∈ [-1,1]，**仅常规模式下可执行**

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ingestion import asdu_parser

# ---------------------------------------------------------------- 常量
#: 运动状态 MotionParam（docs/04 §1.2.3 / §1.3.1.1）
MOTION_IDLE = 0
MOTION_STAND = 1
MOTION_DAMPING_SOFT_ESTOP = 2   # 关节阻尼 = 软急停
MOTION_BOOT_DAMPING = 3
MOTION_LIE_DOWN = 4
MOTION_RL = 17

#: 使用模式 Mode（1101/5）
MODE_NORMAL = 0
MODE_NAV = 1
MODE_ASSIST = 2

#: 步态 GaitParam（docs/04 §1.2.4）
GAIT_BASIC_STD = 0x1001
GAIT_STAIR_STD = 0x1003
GAIT_FLAT_AGILE = 0x3002
GAIT_STAIR_AGILE = 0x3003

#: 自主充电 Charge（docs/04 §1.2）
CHARGE_START = 1
CHARGE_EXIT = 0
CHARGE_RESET = 2          # ⚠️ 官方标注危险 → L2 黑名单
CHARGE_CANCEL = 3
CHARGE_STOP_LEAVE = 4

AXIS_KEYS = ("X", "Y", "Z", "Roll", "Pitch", "Yaw")


# ---------------------------------------------------------------- 工具
def _clamp(value: float, low: float = -1.0, high: float = 1.0, ndigits: int = 2) -> float:
    """服务端值域钳制：浏览器不是可信边界（PLAN §10.5）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v < low:
        v = low
    elif v > high:
        v = high
    if v != v:  # NaN
        v = 0.0
    return round(v, ndigits)


# ---------------------------------------------------------------- 指令构造
def heartbeat() -> Dict[str, Any]:
    return {"type": 100, "command": 100, "items": {}}


def motion_state(param: int) -> Dict[str, Any]:
    """运动状态转换 (2/22)。"""
    return {"type": 2, "command": 22, "items": {"MotionParam": int(param)}}


def soft_estop() -> Dict[str, Any]:
    """软急停 = 关节阻尼 (MotionParam=2)。"""
    return motion_state(MOTION_DAMPING_SOFT_ESTOP)


def stand_up() -> Dict[str, Any]:
    return motion_state(MOTION_STAND)


def lie_down() -> Dict[str, Any]:
    return motion_state(MOTION_LIE_DOWN)


def gait(param: int) -> Dict[str, Any]:
    """步态切换 (2/23) —— 字段名是 GaitParam。"""
    return {"type": 2, "command": 23, "items": {"GaitParam": int(param)}}


def axis(x: float = 0.0, y: float = 0.0, z: float = 0.0,
         roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0,
         limits: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """六轴轴指令 (2/21)：钳制到 [-1,1]（limits 可覆盖）。"""
    lo = (limits or {}).get("min", -1.0)
    hi = (limits or {}).get("max", 1.0)
    items = {
        "X": _clamp(x, lo, hi), "Y": _clamp(y, lo, hi), "Z": _clamp(z, lo, hi),
        "Roll": _clamp(roll, lo, hi), "Pitch": _clamp(pitch, lo, hi),
        "Yaw": _clamp(yaw, lo, hi),
    }
    return {"type": 2, "command": 21, "items": items}


def zero_axis() -> Dict[str, Any]:
    """零位指令（看门狗兜底）。"""
    return axis(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def usage_mode(mode: int) -> Dict[str, Any]:
    """使用模式切换 (1101/5)。"""
    return {"type": 1101, "command": 5, "items": {"Mode": int(mode)}}


def light(front: int = 0, back: int = 0) -> Dict[str, Any]:
    """照明灯 (1101/2)：0=关 1=开。"""
    return {"type": 1101, "command": 2, "items": {
        "Front": 1 if front else 0, "Back": 1 if back else 0}}


def charge(action: int) -> Dict[str, Any]:
    """自主充电 (2/24)。Charge=2 由网关黑名单拦截，本函数不判安全。"""
    return {"type": 2, "command": 24, "items": {"Charge": int(action)}}


def sleep(enable: bool, auto: bool = False, minutes: int = 10) -> Dict[str, Any]:
    """休眠模式设置 (1101/6)：Sleep=false 即唤醒全车含传感器。"""
    return {"type": 1101, "command": 6, "items": {
        "Sleep": bool(enable), "Auto": bool(auto),
        "Time": max(5, min(30, int(minutes)))}}


def wake_up() -> Dict[str, Any]:
    """唤醒（退出休眠）。"""
    return sleep(False)


def sleep_query() -> Dict[str, Any]:
    """休眠状态查询 (1101/7)。"""
    return {"type": 1101, "command": 7, "items": {}}


def gps_time_sync(enable: bool = True) -> Dict[str, Any]:
    """GPS 时间同步 (1101/16)：或可修 196 时钟问题（C6/Q6）。"""
    return {"type": 1101, "command": 16, "items": {"Enable": bool(enable)}}


# ---------------------------------------------------------------- 指令注册表
#: name -> (构建函数, 是否视为"运动类"需要前置校验)
COMMANDS: Dict[str, Dict[str, Any]] = {
    "heartbeat":       {"build": lambda p: heartbeat(), "motion": False},
    "stand_up":        {"build": lambda p: stand_up(), "motion": False},
    "lie_down":        {"build": lambda p: lie_down(), "motion": False},
    "soft_estop":      {"build": lambda p: soft_estop(), "motion": False, "always_allowed": True},
    "motion_state":    {"build": lambda p: motion_state(p.get("param", 0)), "motion": False},
    "gait":            {"build": lambda p: gait(p.get("param", GAIT_BASIC_STD)), "motion": False},
    "axis":            {"build": lambda p: axis(**p), "motion": True},
    "usage_mode":      {"build": lambda p: usage_mode(p.get("mode", MODE_NORMAL)), "motion": False},
    "light":           {"build": lambda p: light(p.get("front", 0), p.get("back", 0)), "motion": False},
    "charge":          {"build": lambda p: charge(p.get("action", CHARGE_START)), "motion": False},
    "sleep":           {"build": lambda p: sleep(p.get("enable", False), p.get("auto", False),
                                                 p.get("minutes", 10)), "motion": False},
    "wake_up":         {"build": lambda p: wake_up(), "motion": False},
    "sleep_query":     {"build": lambda p: sleep_query(), "motion": False},
    "gps_time_sync":   {"build": lambda p: gps_time_sync(p.get("enable", True)), "motion": False},
}


def build(name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """按指令名构造消息体（未编码）。"""
    if name not in COMMANDS:
        raise KeyError("未知指令: %s（可用: %s）" % (name, sorted(COMMANDS)))
    return COMMANDS[name]["build"](params or {})


def encode(name: str, params: Optional[Dict[str, Any]] = None,
           message_id: int = 0) -> bytes:
    """构造并编码为完整字节帧（16 字节帧头 + JSON）。"""
    msg = build(name, params)
    return asdu_parser.encode_frame(msg["type"], msg["command"], msg["items"],
                                    message_id=message_id)
