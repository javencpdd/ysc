"""PatrolDevice 指令编解码（PLAN §10.3 指令全集）。

帧头编码复用 ``ingestion.asdu_parser.encode_frame`` —— 帧格式只写一处，避免两套实现漂移。

指令值域一律以 docs/04 §1.2 原文为准（v1.2 协议事实修正）：
- 运动状态转换 (2/22) ``MotionParam``: 0/1/2/3/4/17（旧稿 -2/-1/5 不见于文档，勿用）
- 步态切换 (2/23) ``GaitParam``: 0x1001/0x1003/0x3002/0x3003（字段名是 GaitParam，不是 Gait）
- 六轴轴指令 (2/21) X/Y/Z/Roll/Pitch/Yaw ∈ [-1,1]，**仅常规模式下可执行**；
  另有实时通道 (2/25) RealSteer，字段完全相同（2026-10-16 三通道取证：
  basic_server 中 2/21→cmdHandle_Steer（/STEER + /HANDLE_STEER）、
  2/25→cmdHandle_RealSteer（/REAL_STEER）—— 两条通道订阅方不同，
  可用于"同一轴值换通道"的对照排查）

⚠️ Python 3.8 兼容。

帧头 magic（2026-10-17 取证，详见 ``asdu_parser.HEAD_TAG_AUTHORIZED``）：
    默认 ``EB 91 EB 90``；**DeviceControl 类指令（1101/3 设备开关）只认厂商 App 的
    ``EB 90 EB 90``**，否则回 ``ErrorCode 57351 / "No operation permission"``。
    该差异由 ``encode()`` 按指令自动处理，调用方无感。
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
    """零位指令（看门狗兜底，主通道 2/21）。"""
    return axis(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def axis_real(x: float = 0.0, y: float = 0.0, z: float = 0.0,
              roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0,
              limits: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """六轴轴指令（**实时通道**，2/25 RealSteer）：字段与 (2/21) 完全相同。

    2026-10-16 取证（basic_server 二进制内三条话题）：``/STEER``、
    ``/HANDLE_STEER``、``/REAL_STEER``；两路指令只是订阅方不同。
    排查"主通道发了车没执行"时，可用同一轴值换本通道做对照实验。
    """
    msg = axis(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw, limits=limits)
    msg["command"] = 25
    return msg


#: 轴指令通道键 → 指令名（前端/API 用键，编解码用名）
AXIS_CHANNELS = {"steer": "axis", "real": "axis_real"}


def channel_key(channel: Optional[str]) -> str:
    """规范化通道键；非法/缺省一律回退 ``steer``（绝不因拼错而静默换通道）。"""
    c = str(channel or "steer")
    return c if c in AXIS_CHANNELS else "steer"


def channel_command(channel: Optional[str]) -> str:
    """通道键 → COMMANDS 指令名。"""
    return AXIS_CHANNELS[channel_key(channel)]


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


def sleep_config_query() -> Dict[str, Any]:
    """休眠配置查询 (1101/7) = ``cmdHandle_GetSleepConfig``。

    车侧应答 ``{"Sleep":0,"Auto":false,"Time":10}``（2026-10-18 实测）：
    ``Sleep`` 是**当前是否处于休眠**（0/1，不是布尔）、``Auto`` 是自动休眠开关、
    ``Time`` 是自动休眠等待时长（分钟，车侧校验 5~30）。
    """
    return {"type": 1101, "command": 7, "items": {}}


def sleep_query() -> Dict[str, Any]:
    """（旧名）休眠配置查询，等价于 :func:`sleep_config_query`。"""
    return sleep_config_query()


def set_auto_reset(enable: bool) -> Dict[str, Any]:
    """首位站立前是否自动回零 (1101/10) = ``cmdHandle_SetAutoResetJointsZero``。

    ⚠️ **这条指令车侧不回帧**（2026-10-18 实测：下发后 3s 无应答，但回读
    确实变成了目标值）。所以"有没有生效"只能靠 :func:`auto_reset_query`
    回读校验，绝不能拿"没收到应答"当失败——报文面板会显示 ``no_response``，
    那是"不知道"，不是"没做成"。
    """
    return {"type": 1101, "command": 10, "items": {"Enable": bool(enable)}}


def auto_reset_query() -> Dict[str, Any]:
    """读取回零开关 (1101/11) = ``cmdHandle_GetAutoResetJointsZero``。

    车侧应答 ``{"Enable":true}``（2026-10-18 实测，与 ``basic_server.toml``
    的 ``[VelControl] autoResetJointsZero`` 一致）。
    """
    return {"type": 1101, "command": 11, "items": {}}


def gps_time_sync(enable: bool = True) -> Dict[str, Any]:
    """GPS 时间同步 (1101/16)：或可修 196 时钟问题（C6/Q6）。"""
    return {"type": 1101, "command": 16, "items": {"Enable": bool(enable)}}


# ---------------------------------------------------------------- 设备供电开关
#: 1101/3「设备开关写入」的 Items 键白名单（2026-10-17 抓包 + 真机探测**逐键实证**）。
#:
#: 取证方式：tcpdump 抓厂商 App 的报文 + 我们自己用授权 magic 回放同一 Items，
#: 再对照车侧日志确认（如 ``{"Video":{...}}`` → `设置广角相机开关 front:1 back:1`）。
#:
#: 值类型：
#:   pair  —— {"Front":0|1,"Back":0|1}   前后两路
#:   flag  —— 0|1                        单路开关
#:   speed —— 0..100                     风扇转速
#:   mode  —— 0..2^32-1                   GPS 模式（语义未公开，仅供取证/排障）
#:
#: ⚠️ **下发值**统一是 0/1（关/开），但**上报值**不全是布尔 —— 真机实测
#: ``DevEnable.Lidar`` 开启后会变成 ``2``（车侧日志 ``mLIDAR_POWER_.front 2``
#: 即"运行中"；1 = 已供电/启动中，0 = 关）。由此三条铁律：
#:   · 判定"是否关闭"只能用 ``== 0``，绝不能写 ``== 1``
#:   · 前端回填另一路当前值时要把 2 归一成 1 再下发
#:   · 本文件 ``_flag`` 只管**下发值域**（0/1），与上报值域无关
DEVICE_SWITCH_SPEC: Dict[str, Dict[str, Any]] = {
    "Video":     {"kind": "pair",  "label": "广角相机供电", "front": "前相机", "back": "后相机"},
    "Lidar":     {"kind": "pair",  "label": "雷达供电",     "front": "前雷达", "back": "后雷达"},
    "GPS":       {"kind": "flag",  "label": "GPS 供电"},
    "LedHost":   {"kind": "flag",  "label": "主机电源指示灯"},
    "LedExt":    {"kind": "flag",  "label": "外部负载电源指示灯"},
    "LoadPower": {"kind": "flag",  "label": "外部负载供电"},
    "FP":        {"kind": "flag",  "label": "对频模块供电"},
    "FanSpeed":  {"kind": "speed", "label": "风扇转速"},
    "GPSMode":   {"kind": "mode",  "label": "GPS 模式（语义未公开，仅取证）"},
}

#: 前端可暴露的设备键（GPSMode 语义不明，只留后端/取证用，不进 UI）
DEVICE_SWITCH_UI_KEYS = ("Video", "Lidar", "GPS", "LedHost", "LedExt",
                         "LoadPower", "FP", "FanSpeed")

#: 运动中禁关的键（断电即失去平衡参考，保守策略）
DEVICE_SWITCH_MOTION_LOCKED = ("Lidar",)


def _flag(value: Any) -> int:
    v = int(value)
    if v not in (0, 1):
        raise ValueError("开关值只能是 0 或 1，收到 %r" % (value,))
    return v


def device_switch(items: Optional[Dict[str, Any]] = None, **_ignored: Any) -> Dict[str, Any]:
    """设备供电开关写入 (1101/3)。

    **只能写白名单内的键**（``DEVICE_SWITCH_SPEC``）—— 绝不透传任意 Items：
    这条指令能断电任何设备（含关节/视频/雷达），键名猜错等于盲目操作硬件。

    ⚠️ 该指令需要**授权帧头 magic**，见 ``encode()`` / ``asdu_parser.HEAD_TAG_AUTHORIZED``。
    """
    items = dict(items or {})
    if not items:
        raise ValueError("设备开关必须指定至少一个 Items 键（可用: %s）"
                         % ", ".join(sorted(DEVICE_SWITCH_SPEC)))
    out: Dict[str, Any] = {}
    for key, value in items.items():
        spec = DEVICE_SWITCH_SPEC.get(key)
        if spec is None:
            raise ValueError("设备开关不支持的键 %r（可用: %s）"
                             % (key, ", ".join(sorted(DEVICE_SWITCH_SPEC))))
        kind = spec["kind"]
        if kind == "pair":
            if not isinstance(value, dict):
                raise ValueError("%s 需要 {'Front':0|1,'Back':0|1}，收到 %r" % (key, value))
            for side in ("Front", "Back"):
                if side not in value:
                    # 绝不默认 0 —— 缺字段默认"关"等于悄悄断电，必须显式写清
                    raise ValueError("%s 必须显式给出 Front 与 Back（各 0 或 1）" % key)
            out[key] = {"Front": _flag(value["Front"]),
                        "Back": _flag(value["Back"])}
        elif kind == "flag":
            out[key] = _flag(value)
        elif kind == "speed":
            v = int(value)
            if not 0 <= v <= 100:
                raise ValueError("FanSpeed 值域 0~100，收到 %r" % (value,))
            out[key] = v
        else:  # mode —— 真机实测值 0x11111(69905) 超出 16 位，按 32 位无符号校验
            v = int(value)
            if not 0 <= v <= 0xFFFFFFFF:
                raise ValueError("GPSMode 值域 0~4294967295，收到 %r" % (value,))
            out[key] = v
    return {"type": 1101, "command": 3, "items": out}


#: 设备键 → DevEnable 里的字段名（用于拿"当前值"做对比）
DEVICE_SWITCH_STATE_FIELDS = {
    "Video": "Video", "Lidar": "Lidar", "GPS": "GPS", "GPSMode": "GPSMode",
    "LedHost": "LedHost", "LedExt": "LedExt", "LoadPower": "LoadPower",
    "FP": "FP", "FanSpeed": "FanSpeed",
}


def _as_int(value: Any, default: int = 0) -> int:
    """尽力转 int；转不动就回 default（协议字段可能是 null / 字符串）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def device_switch_turns_off(items: Optional[Dict[str, Any]],
                            current: Optional[Dict[str, Any]] = None) -> bool:
    """这组 Items 是否**真的会把某个设备从"开"变成"关"**。

    ⚠️ 必须带上 ``current``（当前 ``DevEnable``）才不会误判 —— 只看目标值会把
    "保持不变"当成"关闭"：例如开前相机时 Items 是 ``{"Video":{"Front":1,"Back":0}}``，
    后相机的 0 只是**保持它本来就是关的**，不是关闭操作。
    2026-10-17 真踩：这样点「开」会被服务端要求二次确认，而前端没弹框 → 用户看到
    ``CONFIRM_REQUIRED``，表现为"点开启没反应"。

    ``current`` 取不到时**回退到保守判定**（有 0 就算关闭）—— 宁可多要一次确认，
    也不能放过真正的断电操作。
    """
    items = items or {}
    strict = current is None
    cur = current or {}
    for key, value in items.items():
        field = DEVICE_SWITCH_STATE_FIELDS.get(key, key)
        before = cur.get(field)
        if key in ("Video", "Lidar"):
            value = value or {}
            before = before if isinstance(before, dict) else {}
            for side in ("Front", "Back"):
                if side not in value:
                    continue
                after_v = _as_int(value[side])
                before_v = _as_int(before.get(side)) if not strict else 1
                # 从"非 0"（开/运行中）变成 0 才算关闭
                if after_v == 0 and before_v != 0:
                    return True
        elif key == "GPSMode":
            # 掩码切换不是"关供电"；但掩码 0（所有星座全关）确实是关
            if _as_int(value) == 0 and (strict or _as_int(before, 1) != 0):
                return True
        else:
            after_v = _as_int(value)
            before_v = _as_int(before) if not strict else 1
            if after_v == 0 and before_v != 0:
                return True
    return False


#: **需要二次确认的指令**（2026-10-18 加）。
#:
#: 与"设备供电开关"的确认闸同源思路，但作用面不同：那些是断电，
#: 这里是**改变整车行为**或**摘掉安全动作**，判据一律只看"危险方向"——
#: 顺着安全方向的操作（唤醒、开启回零）不该被拦，否则就是把易用性当代价
#: 付给了安全仪式感。
#:
#: 判定函数签名统一为 ``(params) -> bool``（真 = 需要确认）。
CONFIRM_RULES: Dict[str, Any] = {
    # 整车休眠：依次关 LED→风扇→视频→关节供电，机器人会趴下
    "sleep": lambda p: bool(p.get("enable", False)),
    # 关掉"首次站立前回零"：下次开机直接站立，关节位置未经标定
    "auto_reset_set": lambda p: not bool(p.get("enable", True)),
}


def needs_confirm(name: str, params: Optional[Dict[str, Any]] = None) -> bool:
    """这条指令这次是否必须先二次确认。"""
    rule = CONFIRM_RULES.get(name)
    if rule is None:
        return False
    try:
        return bool(rule(params or {}))
    except Exception:  # noqa: BLE001 - 规则判定失败一律按"需确认"兜底
        return True


def device_switch_is_off(key: str, value: Any) -> bool:
    """单个键是否处于"关"—— 前端按钮态与服务端闸共用同一判定，避免两套语义。"""
    if key in ("Video", "Lidar"):
        return any(int(v or 0) == 0 for v in (value or {}).values())
    if key == "FanSpeed":
        return int(value or 0) == 0
    return int(value or 0) == 0


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
    "axis_real":       {"build": lambda p: axis_real(**p), "motion": True},
    "usage_mode":      {"build": lambda p: usage_mode(p.get("mode", MODE_NORMAL)), "motion": False},
    "light":           {"build": lambda p: light(p.get("front", 0), p.get("back", 0)), "motion": False},
    "charge":          {"build": lambda p: charge(p.get("action", CHARGE_START)), "motion": False},
    "sleep":           {"build": lambda p: sleep(p.get("enable", False), p.get("auto", False),
                                                 p.get("minutes", 10)), "motion": False},
    "wake_up":         {"build": lambda p: wake_up(), "motion": False},
    # 两条**只读查询**指令：不开控制也能问（always_allowed 同时豁免 L1 与租约闸）。
    # 它们不改车上的任何东西，把它们锁在"必须先开控制"后面纯属自找麻烦。
    "sleep_query":     {"build": lambda p: sleep_config_query(), "motion": False,
                        "always_allowed": True},
    # 首启回零开关（1101/10 写 / 1101/11 读）
    "auto_reset_set":  {"build": lambda p: set_auto_reset(p.get("enable", True)),
                        "motion": False},
    "auto_reset_query": {"build": lambda p: auto_reset_query(), "motion": False,
                         "always_allowed": True},
    "gps_time_sync":   {"build": lambda p: gps_time_sync(p.get("enable", True)), "motion": False},
    # 设备供电开关（1101/3）：需要授权帧头 magic，见 encode()
    "device_switch":   {"build": lambda p: device_switch(p.get("items")), "motion": False,
                        "authorized": True},
}


def build(name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """按指令名构造消息体（未编码）。"""
    if name not in COMMANDS:
        raise KeyError("未知指令: %s（可用: %s）" % (name, sorted(COMMANDS)))
    return COMMANDS[name]["build"](params or {})


def encode(name: str, params: Optional[Dict[str, Any]] = None,
           message_id: int = 0) -> bytes:
    """构造并编码为完整字节帧（16 字节帧头 + JSON）。

    帧头 magic 按指令选取：``COMMANDS[name]["authorized"]`` 为真时用
    ``HEAD_TAG_AUTHORIZED``（厂商 App 标识，DeviceControl 类指令必需），
    否则用默认 ``HEAD_TAG``。**绝不全局替换** —— 心跳/运动链路已验证，不动它。
    """
    if name not in COMMANDS:
        raise KeyError("未知指令: %s（可用: %s）" % (name, sorted(COMMANDS)))
    msg = build(name, params)
    tag = (asdu_parser.HEAD_TAG_AUTHORIZED
           if COMMANDS[name].get("authorized") else asdu_parser.HEAD_TAG)
    return asdu_parser.encode_frame(msg["type"], msg["command"], msg["items"],
                                    message_id=message_id, head_tag=tag)
