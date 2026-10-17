"""ASDU 解析器 —— 协议与领域模型之间的**防腐层（ACL）**（PLAN §3 / §10）。

这是整个设计里唯一不可妥协的边界：协议怎么变，都关在本文件里。

协议真相（PROTOCOL.md §1/§2，docs/04 §1.3 原文核实）：
    16 字节二进制帧头 + UTF-8 JSON 信封 {"PatrolDevice": {Type, Command, Time, Items}}
    帧头 = EB 91 EB 90(4) + dataSize LE16(2) + messageID LE16(2) + protocolType(1) + RESERVE(7×00)
    ⚠️ 帧头 magic 有第二个取值 ``EB 90 EB 90``（厂商 App），DeviceControl 类
    指令（1101/3）只认它 —— 见 ``HEAD_TAG_AUTHORIZED``。

本文件同时提供帧头编解码原语（``encode_frame`` / ``decode_frame``）；控制出口
``patrol_codec`` 复用 ``encode_frame``，避免帧格式在两处各写一遍。

⚠️ Python 3.8 兼容（196 实测 3.8.10）。
"""
from __future__ import annotations

import json
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

from errors import ProtocolError
from logging_setup import get_logger

logger = get_logger("ingestion.parser")

# ---------------------------------------------------------------- 帧格式常量
#: 默认帧头 magic —— 第三方/SDK 客户端标识（控制台一直用这个，运动/查询类指令均正常）。
HEAD_TAG = b"\xeb\x91\xeb\x90"
#: 授权帧头 magic —— **厂商 App 使用的客户端标识**。
#:
#: 2026-10-17 真机取证（tcpdump 抓厂商 App + 我们自己下发对照）：
#: basic_server 对 **DeviceControl 类指令（Type=1101 / Command=3 设备开关写入）**
#: 会校验该 magic —— 用 ``EB 91 EB 90`` 一律回
#: ``ErrorCode 57351 / "No operation permission"``；换成 ``EB 90 EB 90`` 立即执行。
#:
#: 实测该 magic 对其余指令**完全等价**（心跳 100/100、休眠查询 1101/7、照明灯 1101/2
#: 两种 magic 都返回 ErrorCode 0），所以只在 DeviceControl 类指令上按需切换，
#: 绝不全局替换（心跳链路已验证过，不动它 = 零回归）。
HEAD_TAG_AUTHORIZED = b"\xeb\x90\xeb\x90"
#: **接收侧**要认的全部 magic。
#:
#: 2026-10-17 抓包实证：basic_server **按「客户端注册时用的 magic」回复该客户端** ——
#: 厂商 App 用 EB90EB90 注册，它收到的 2714 帧（含状态上报）全是 EB90EB90；
#: 我们用心跳 socket 的 EB91EB90 注册，遥测帧就是 EB91EB90。
#: 后果：`1101/3` 我们用授权 magic 发出去，**应答也回 EB90EB90** ——
#: 解码器若只认 EB91EB90 就解析失败，报文记录会永远停在 ``no_response``
#: （2026-10-17 实际踩到）。故接收侧必须两种都认。
#: ⚠️ 放宽的是"客户端标识"，**不是完整性校验**：帧体仍要 JSON 解析通过才算合法。
HEAD_TAGS = (HEAD_TAG, HEAD_TAG_AUTHORIZED)
HEADER_SIZE = 16
PROTOCOL_TYPE_JSON = 0x01
#: struct 小端：4s 标签 + H dataSize + H messageID + B protocolType + 7x 保留
HEADER_STRUCT = struct.Struct("<4sHHB7x")

# ------------------------------------------------- 五类状态消息（PLAN §10.4）
#: (Type, Command) -> topic 名
#: 前 6 项来自 docs/04 §1.3；后 2 项为 **2026-10-14 真机抓包实测新增**（PLAN §10.4 已回填）
TOPIC_BY_KEY = {
    (1002, 6): "basic",     # 基础状态上报   2Hz
    (1002, 4): "motion",    # 运控状态上报   10Hz（含 16 关节）
    (1002, 5): "device",    # 设备状态上报   2Hz（BatteryList 等 7 大类）
    (1002, 3): "fault",     # 异常状态       2Hz + 变更额外上报
    (1101, 7): "sleep",     # 休眠状态查询响应（按需）
    (1002, 1): "basic_query",  # 基础状态查询请求（外部→机器人，一般不出现在接收侧）
    (100, 100): "ack",      # 【实测】心跳应答：{"ErrorCode": 0}，每发一次心跳回一帧
    (1002, 7): "nav",       # 【实测】导航状态 + 定位位姿：NavStatus + LocationStatus，1Hz
}
KEY_BY_TOPIC = {v: k for k, v in TOPIC_BY_KEY.items()}

#: 各 topic 的推送频率（Hz）—— docs/04 §1.3 + 2026-10-14 真机抓包实测。
#: 这是**协议层事实**，状态层据此推算 per-topic 的 stale 阈值（见 state_store）。
TOPIC_HZ = {
    "basic": 2.0,    # 2Hz
    "motion": 10.0,  # 10Hz
    "device": 2.0,   # 2Hz
    "fault": 2.0,    # 2Hz + 变更额外上报
    "nav": 1.0,      # 实测新增 1Hz
    "sleep": 0.2,    # 按需查询，按 5s 计
    "ack": 5.0,      # 随心跳 1:1
}

# -------------------------------------------------------------- 枚举与标签
MOTION_STATE = {0: "空闲", 1: "站立", 2: "关节阻尼/软急停", 3: "开机阻尼",
                4: "趴下", 17: "RL控制"}
#: 0 = 未选择步态（真机实测：空闲状态下 Gait 就是 0；docs/04 未列该值）
GAIT = {0: "未设置", 0x1001: "基础(标准)", 0x1002: "高台(标准)",
        0x3002: "平地(敏捷)", 0x3003: "楼梯(敏捷)"}
CHARGE = {0: "空闲", 1: "前往充电桩", 2: "充电中", 3: "退出充电桩", 4: "机器人异常"}
CONTROL_USAGE_MODE = {0: "常规", 1: "导航", 2: "辅助"}
DIRECTION = {0: "正向为前进正方向", 1: "后向为前进正方向"}
OOA = {0: "未启动", 1: "空闲", 2: "未触发避障", 3: "主动避障中"}
POWER_MANAGEMENT = {0: "常规", 1: "单电池"}
SLEEP_STATE = {0: "未休眠", 1: "已休眠", 2: "进入休眠中"}

# ------------------------------------------------------------------------
# 关节回零（2026-10-17 取证）
# 1) 车侧默认开启自动回零：/opt/robot/share/basic_server/conf/basic_server.toml
#    第 14 行 `autoResetJointsZero = true` —— 这就是"开机后第一次站立要先回零"的成因。
# 2) BasicStatus 上报里确实带 `ResetJointsZero` 字段（真机抓包实测 = 0）。
# 3) 运控 rl_deploy 二进制含 qw_m20::ZeroCalibrationState 状态机与 `state=SetZero`；
#    basic_server 含 cmdHandle_ResetJointsZero / GetAutoResetJointsZero /
#    SetAutoResetJointsZero，且约束原文
#    "can not reset joints zero unless standing or lying down"。
# ⚠️ 值域**未见任何官方文档**（docs/04 未收录该字段），故这里不臆造标签：
#    只标注 0 的实测含义，其余原样透传数值 + "未知"。
RESET_JOINTS_ZERO = {0: "无需回零"}

# ---------------------------------------------------------------- GPS 卫星系统
#: GPSMode = GNSS **系统掩码**（哪些星座参与定位）。
#:
#: ★来源不是推测：车侧 GNSS 驱动配置文件
#: ``/opt/robot/share/node_driver/config/gps.yaml`` 的 ``system.sysMask`` 注释原文
#: （2026-10-17 取证）——
#:     bit0-GPS L1CA, bit4-BDS B1I, bit8-GLONASS L1, bit12-GALILEO E1, bit16-QZSS
#:     默认值 0x11111 表示启用所有系统(GN模式)
#: 该值与 ``DeviceStatus.DevEnable.GPSMode`` 上报、``1101/3`` 的 ``GPSMode`` 键同源。
GPS_SYSTEM_BITS = (
    (0x00001, "GPS"),       # L1CA
    (0x00010, "BDS"),       # 北斗 B1I
    (0x00100, "GLONASS"),   # L1
    (0x01000, "Galileo"),   # E1
    (0x10000, "QZSS"),      # L1
)

#: 合法位全集
GPS_SYSTEM_MASK_ALL = 0x11111

#: 预设名（同样取自 gps.yaml 的 ``system.presets`` 原文）
GPS_MODE_PRESETS = {
    0x00001: "仅 GPS",
    0x00010: "仅 北斗（BDS）",
    0x00100: "仅 GLONASS",
    0x01000: "仅 Galileo",
    0x10000: "仅 QZSS",
    0x11111: "全系统（GN 模式）",
}


def gps_mode_systems(mode: Optional[int]) -> List[str]:
    """掩码 → 已启用星座的中文/通用名列表（未知高位忽略）。"""
    if mode is None:
        return []
    try:
        m = int(mode)
    except (TypeError, ValueError):
        return []
    return [name for bit, name in GPS_SYSTEM_BITS if m & bit]


def gps_mode_label(mode: Optional[int]) -> Optional[str]:
    """掩码 → 人话。

    优先用官方预设名；否则列出星座组合；0 = 全关；含未知位时**显式标注**，
    绝不假装看懂了（与 ``RESET_JOINTS_ZERO`` 处理未知值同一原则）。

        0x11111 → "全系统（GN 模式）"
        0x00001 → "仅 GPS"
        0x00011 → "GPS + BDS"
        0       → "全部关闭（无定位）"
        0x20001 → "仅 GPS（含未知位 0x20000）"
    """
    if mode is None:
        return None
    try:
        m = int(mode)
    except (TypeError, ValueError):
        return None
    if m == 0:
        return "全部关闭（无定位）"
    systems = gps_mode_systems(m)
    if m in GPS_MODE_PRESETS:
        base = GPS_MODE_PRESETS[m]
    elif not systems:
        base = "未启用任何已知星座"
    else:
        base = " + ".join(systems)
    unknown = m & ~GPS_SYSTEM_MASK_ALL
    if unknown:
        base = "%s（含未知位 0x%X）" % (base, unknown)
    return base


#: 轮足：4 腿 × 4 自由度（含轮毂），共 16 关节 —— 与 lite3 的 12 关节不同
JOINT_LEGS = ("LF", "RF", "LB", "RB")
JOINT_PARTS = ("hip_x", "hip_y", "knee", "wheel")
JOINT_NAMES: List[str] = ["%s_%s" % (leg, part) for leg in JOINT_LEGS for part in JOINT_PARTS]
JOINT_COUNT = len(JOINT_NAMES)  # 16

#: 关节名 ↔ 报文字段名映射（docs/04 示例用 LeftFrontHipX 这种驼峰形式）
_LEG_PREFIX = {"LF": "LeftFront", "RF": "RightFront", "LB": "LeftBack", "RB": "RightBack"}
_PART_SUFFIX = {"hip_x": "HipX", "hip_y": "HipY", "knee": "Knee", "wheel": "Wheel"}

# --------------------------------------------- 字段置信度表（PLAN §10.4 标注）
#: 逐字段标注：confirmed=已确认（docs/04 原文直给）/ inferred=推断（待真机核对）/ unknown=未知
FIELD_CONFIDENCE: Dict[str, Dict[str, str]] = {
    "basic": {
        "motion_state": "confirmed", "gait": "confirmed", "charge": "confirmed",
        "hes": "confirmed", "control_usage_mode": "confirmed", "direction": "confirmed",
        "ooa": "confirmed", "power_management": "confirmed", "sleep": "confirmed",
        "version": "confirmed",
    },
    "motion": {
        "roll": "confirmed", "pitch": "confirmed", "yaw": "confirmed",
        "omega_z": "confirmed", "linear_x": "confirmed", "linear_y": "confirmed",
        "height": "confirmed", "payload": "confirmed", "remain_mile": "confirmed",
        "joints": "confirmed",
        # 单位文档未载，待 M2 真机核对（PLAN Q12）
        "unit_attitude": "unknown", "unit_linear": "unknown",
    },
    "device": {
        "batteries": "confirmed", "battery_count": "inferred",
        "voltage": "confirmed", "level": "confirmed",
        "temperature": "confirmed", "charging": "confirmed", "serial": "confirmed",
    },
    "fault": {
        "errors": "confirmed", "error_count": "confirmed",
        "error_code_enum": "unknown",  # docs 未给全 errorCode 取值表
    },
    "sleep": {"sleep": "confirmed", "auto": "confirmed", "time": "confirmed"},
    # 以下两类为 2026-10-14 真机抓包实测新增（字段名实测确认，语义枚举待核）
    "ack": {"error_code": "confirmed"},
    "nav": {
        "nav_value": "confirmed", "nav_status": "confirmed", "nav_error_code": "confirmed",
        "loop_count": "confirmed", "remaining_count": "confirmed", "task_name": "confirmed",
        "located": "confirmed", "pos_x": "confirmed", "pos_y": "confirmed",
        "pos_z": "confirmed", "roll": "confirmed", "pitch": "confirmed",
        "yaw": "confirmed", "confidence": "confirmed", "relocation": "confirmed",
        "nav_status_enum": "unknown",  # NavStatus.Value/Status 取值含义未载
    },
}


# ---------------------------------------------------------------- 帧级编解码
def encode_frame(type_: int, command: int, items: Optional[Dict[str, Any]] = None,
                 message_id: int = 0, time_str: str = "",
                 head_tag: bytes = HEAD_TAG) -> bytes:
    """把 PatrolDevice 消息编码为「16 字节帧头 + JSON」字节流。

    ``head_tag`` 默认 ``HEAD_TAG``；DeviceControl 类指令需传
    ``HEAD_TAG_AUTHORIZED``（见该常量说明）。
    """
    envelope = {
        "PatrolDevice": {
            "Type": int(type_),
            "Command": int(command),
            "Time": time_str or time.strftime("%Y-%m-%d %H:%M:%S"),
            "Items": items or {},
        }
    }
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    header = HEADER_STRUCT.pack(head_tag, len(body), message_id & 0xFFFF,
                                PROTOCOL_TYPE_JSON)
    return header + body


def decode_frame(data: bytes) -> Dict[str, Any]:
    """解码一帧：校验帧头 + 长度，返回 PatrolDevice 字典。

    失败抛 ProtocolError（调用方负责计入死信，不向外扩散）。
    """
    if len(data) < HEADER_SIZE:
        raise ProtocolError("帧长 %d < 帧头 16 字节" % len(data))
    tag, data_size, message_id, protocol_type = HEADER_STRUCT.unpack_from(data, 0)
    if tag not in HEAD_TAGS:
        raise ProtocolError("帧头标签不匹配: %s" % tag.hex())
    if protocol_type != PROTOCOL_TYPE_JSON:
        raise ProtocolError("protocolType=%d 非 JSON（本期只支持 0x01）" % protocol_type)
    body = data[HEADER_SIZE:HEADER_SIZE + data_size]
    if len(body) < data_size:
        raise ProtocolError("帧体截断: 声明 %d 实际 %d" % (data_size, len(body)))
    try:
        envelope = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("JSON 解析失败: %s" % exc) from exc
    if not isinstance(envelope, dict) or "PatrolDevice" not in envelope:
        raise ProtocolError("缺少 PatrolDevice 信封")
    msg = envelope["PatrolDevice"]
    return {
        "type": int(msg.get("Type", 0)),
        "command": int(msg.get("Command", 0)),
        "time": msg.get("Time", ""),
        "items": msg.get("Items", {}) or {},
        "message_id": message_id,
        #: 实际帧头 magic —— 让上层能看出这条帧走的是默认还是授权通道
        "head_tag": tag.hex(),
    }


# ---------------------------------------------------------------- 字段映射
def _hex16(value: Any) -> Optional[str]:
    """整数 → ``0x11111`` 形式（按 5 位十六进制，与 gps.yaml 的写法保持一致）。

    非整数原样返回 ``str`` —— 协议字段的类型不该在这一层被"修正"。
    """
    if value is None:
        return None
    try:
        return "0x%05X" % int(value)
    except (TypeError, ValueError):
        return str(value)


def _label(table: Dict[int, str], value: Any) -> str:
    try:
        return table.get(int(value), "未知(%s)" % value)
    except (TypeError, ValueError):
        return str(value)


def _map_basic(items: Dict[str, Any]) -> Dict[str, Any]:
    s = items.get("BasicStatus", {}) or {}
    return {
        "motion_state": s.get("MotionState"),
        "motion_state_label": _label(MOTION_STATE, s.get("MotionState")),
        "gait": s.get("Gait"),
        "gait_label": _label(GAIT, s.get("Gait")),
        "charge": s.get("Charge"),
        "charge_label": _label(CHARGE, s.get("Charge")),
        "hes": s.get("HES"),
        "control_usage_mode": s.get("ControlUsageMode"),
        "control_usage_mode_label": _label(CONTROL_USAGE_MODE, s.get("ControlUsageMode")),
        "direction": s.get("Direction"),
        "ooa": s.get("OOA"),
        "power_management": s.get("PowerManagement"),
        "sleep": s.get("Sleep"),
        "sleep_label": _label(SLEEP_STATE, s.get("Sleep")),
        "version": s.get("Version"),
        # 关节回零（docs/04 未收录；真机 BasicStatus 实测存在）
        "status_code": s.get("StatusCode"),
        "reset_joints_zero": s.get("ResetJointsZero"),
        "reset_joints_zero_label": (
            _label(RESET_JOINTS_ZERO, s.get("ResetJointsZero"))
            if s.get("ResetJointsZero") == 0 else "回零中/待回零(%s)" % s.get("ResetJointsZero")
        ),
    }


def _map_motion(items: Dict[str, Any]) -> Dict[str, Any]:
    ms = items.get("MotionStatus", {}) or {}
    mt = items.get("MotorStatus", {}) or {}
    joints: List[float] = []
    raw_joint = mt.get("Joint")
    if isinstance(raw_joint, list) and raw_joint:
        joints = [float(v) for v in raw_joint]
    else:
        # 回退到命名字段（LeftFrontHipX ... RightBackWheel）
        # 注意：关节名形如 "LF_hip_x"，必须按第一个下划线拆分，不能直接 split("_")
        for name in JOINT_NAMES:
            leg, part = name.split("_", 1)
            key = "%s%s" % (_LEG_PREFIX[leg], _PART_SUFFIX[part])
            if key in mt:
                joints.append(float(mt[key]))
    return {
        "roll": ms.get("Roll"), "pitch": ms.get("Pitch"), "yaw": ms.get("Yaw"),
        "omega_z": ms.get("OmegaZ"),
        "linear_x": ms.get("LinearX"), "linear_y": ms.get("LinearY"),
        "height": ms.get("Height"), "payload": ms.get("Payload"),
        "remain_mile": ms.get("RemainMile"),
        "joints": joints,
        "joint_count": len(joints),
        "joint_names": JOINT_NAMES[:len(joints)] if joints else JOINT_NAMES,
    }


def _map_device(items: Dict[str, Any]) -> Dict[str, Any]:
    """设备状态 1002/5。

    docs/04 只写了 ``BatteryList``，但 **2026-10-14 真机实测** Items 实含 7 大类：
    BatteryList / BatteryStatus（左右电池）/ DeviceTemperature（电机温度等 34 项）/
    Led / GPS / DevEnable / CPU。这里把对控制台有用的都映射出来。
    """
    raw = items.get("BatteryList", []) or []
    batteries: List[Dict[str, Any]] = []
    for b in raw if isinstance(raw, list) else []:
        batteries.append({
            "voltage": b.get("Voltage"),
            "level": b.get("BatteryLevel"),
            "temperature": b.get("battery_temperature"),
            "charging": bool(b.get("charge", False)),
            "serial": b.get("serial"),
        })
    primary = batteries[0] if batteries else {}
    bs = items.get("BatteryStatus", {}) or {}
    temps = items.get("DeviceTemperature", {}) or {}
    motors = temps.get("Motor")
    # ---- 分设备使能（2026-10-17 取证）----
    # DevEnable 真机实测结构：
    #   {"FanSpeed":100,"LoadPower":1,"LedHost":1,"LedExt":1,"FP":1,
    #    "Lidar":{"Front":0,"Back":0},"GPS":1,"GPSMode":69905,
    #    "Video":{"Front":1,"Back":1}}
    # ⚠️ 关键结论：这是**供电使能状态**，但协议 docs/04 只暴露整车休眠(1101/6)
    #    作为开关手段；basic_server 内部虽按 VIDEO_POWER / LIDAR_POWER /
    #    JOINTS_POWER / LED_FILL / FAN_SPEED 分通道控制（见其运行日志），
    #    UDP 侧未公开单设备开关指令编号。故此处只做**状态呈现**，不做下发。
    dev = items.get("DevEnable") or {}
    lidar = dev.get("Lidar") or {}
    video = dev.get("Video") or {}
    fill = (items.get("Led") or {}).get("Fill") or {}
    # GPS（1002/5 DeviceStatus.GPS）：真机实测字段
    #   {"Latitude":0.0,"Longitude":0.0,"Speed":0.0,"Course":0.0,"FixQuality":0,
    #    "NumSatellites":0,"Altitude":0.0,"HDOP":0.0,"VDOP":0.0,"PDOP":0.0,
    #    "VisibleSatellites":0}
    # ⚠️ 单位未见官方文档（docs/04 未收录 GPS 字段说明）→ 不做任何换算，原样透传。
    gp = items.get("GPS") or {}
    return {
        "batteries": batteries,
        "battery_count": len(batteries),
        "level": primary.get("level"),
        "voltage": primary.get("voltage"),
        "temperature": primary.get("temperature"),
        "charging": primary.get("charging"),
        # 左右电池（实测字段名带 Left/Right 后缀）
        "level_left": bs.get("BatteryLevelLeft"),
        "level_right": bs.get("BatteryLevelRight"),
        "voltage_left": bs.get("VoltageLeft"),
        "voltage_right": bs.get("VoltageRight"),
        "charge_left": bs.get("chargeLeft"),
        "charge_right": bs.get("chargeRight"),
        # 温度：电机温度数组 + 其余温感项名
        "motor_temperatures": list(motors) if isinstance(motors, list) else [],
        "temperature_keys": sorted(temps.keys()),
        "gps": items.get("GPS"),
        # 细粒度：供 GPS 标签页逐项呈现
        "gps_latitude": gp.get("Latitude"),
        "gps_longitude": gp.get("Longitude"),
        "gps_speed": gp.get("Speed"),
        "gps_course": gp.get("Course"),
        "gps_fix_quality": gp.get("FixQuality"),
        "gps_num_satellites": gp.get("NumSatellites"),
        "gps_altitude": gp.get("Altitude"),
        "gps_hdop": gp.get("HDOP"),
        "gps_vdop": gp.get("VDOP"),
        "gps_pdop": gp.get("PDOP"),
        "gps_visible_satellites": gp.get("VisibleSatellites"),
        "led": items.get("Led"),
        "dev_enable": items.get("DevEnable"),
        # ★补光灯（前后照明）：1101/2 下发、设备帧 Led.Fill 回读（2026-10-18 实证）
        # 真机实测 items.Led = {"Fill":{"Front":1,"Back":1}} —— 下发 1101/2
        # {"Front":1,"Back":1} 后约 1s 内该值同步翻转，可作为**闭环校验**依据。
        # ⚠️ 它不在 DevEnable 里（DevEnable 只有 LedHost/LedExt 两个**指示灯**），
        #    别把两者混为一谈：LedHost 是电源指示灯，Led.Fill 是照明补光灯。
        "fill_front": (fill or {}).get("Front"),
        "fill_back": (fill or {}).get("Back"),
        # 细粒度：供前端按标签页分区展示（相机页 / 运动控制页 / GPS 页）
        "video_front": video.get("Front"),
        "video_back": video.get("Back"),
        "lidar_front": lidar.get("Front"),
        "lidar_back": lidar.get("Back"),
        "gps_enable": dev.get("GPS"),
        "gps_mode": dev.get("GPSMode"),
        # GPSMode 是人看不懂的系统掩码 → 解成"哪些星座在参与定位"（见 GPS_SYSTEM_BITS）
        "gps_mode_hex": _hex16(dev.get("GPSMode")),
        "gps_mode_label": gps_mode_label(dev.get("GPSMode")),
        "gps_systems": gps_mode_systems(dev.get("GPSMode")),
        "led_host": dev.get("LedHost"),
        "led_ext": dev.get("LedExt"),
        "load_power": dev.get("LoadPower"),
        "fan_speed": dev.get("FanSpeed"),
        # 对频模块（遥控器配对）供电；真机 DevEnable 里字段名就是 FP
        "fp": dev.get("FP"),
        "cpu": items.get("CPU"),
    }


def _map_ack(items: Dict[str, Any]) -> Dict[str, Any]:
    """心跳应答 100/100（实测）：机器人对每条心跳回一帧，带 ErrorCode。"""
    return {"error_code": items.get("ErrorCode")}


def _map_nav(items: Dict[str, Any]) -> Dict[str, Any]:
    """导航状态 + 定位位姿 1002/7（实测新增，1Hz）。

    LocationStatus 给出机体在地图中的 XYZ 与 RPY + 定位置信度 —— 控制台可据此
    画"机器人位置"（本期非目标，但字段先落库，避免二次改协议层）。
    """
    nav = items.get("NavStatus", {}) or {}
    loc = items.get("LocationStatus", {}) or {}
    return {
        "nav_value": nav.get("Value"),
        "nav_status": nav.get("Status"),
        "nav_error_code": nav.get("ErrorCode"),
        "loop_count": nav.get("LoopCnt"),
        "remaining_count": nav.get("RemainingCnt"),
        "task_name": nav.get("Name"),
        "located": loc.get("Location"),
        "pos_x": loc.get("PosX"), "pos_y": loc.get("PosY"), "pos_z": loc.get("PosZ"),
        "roll": loc.get("Roll"), "pitch": loc.get("Pitch"), "yaw": loc.get("Yaw"),
        "confidence": loc.get("Confidence"),
        "relocation": loc.get("Relocation"),
    }


def _map_fault(items: Dict[str, Any]) -> Dict[str, Any]:
    raw = items.get("ErrorList", []) or []
    errors = [{"code": e.get("errorCode"), "component": e.get("component")}
              for e in raw if isinstance(e, dict)]
    return {"errors": errors, "error_count": len(errors), "has_fault": len(errors) > 0}


def _map_sleep(items: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sleep": items.get("Sleep"),
        "sleep_label": _label(SLEEP_STATE, items.get("Sleep")),
        "auto": items.get("Auto"),
        "time": items.get("Time"),
    }


_TOPIC_MAPPERS = {
    "basic": _map_basic,
    "motion": _map_motion,
    "device": _map_device,
    "fault": _map_fault,
    "sleep": _map_sleep,
    "ack": _map_ack,
    "nav": _map_nav,
}


# ---------------------------------------------------------------- 对外入口
def parse_frame(data: bytes, addr: Optional[Tuple[str, int]] = None,
                recv_monotonic: Optional[float] = None) -> Dict[str, Any]:
    """把一帧原始 UDP 报文解析为归一化帧（领域模型入口）。

    返回结构（上层只认这个，不知道协议细节）：
        {
          "topic": "basic"|"motion"|"device"|"fault"|"sleep"|"unknown",
          "key": "1002/6", "type": 1002, "command": 6,
          "time": "...",          # 原样透传（196 时钟不可信，仅展示用）
          "fields": {...},        # 领域字段（映射后）
          "items": {...},         # 原始 Items（调试/回放用）
          "recv_monotonic": float, "recv_wall": float,
          "source": {"ip":..., "port":...}, "raw_len": int,
        }
    """
    decoded = decode_frame(data)
    key = (decoded["type"], decoded["command"])
    topic = TOPIC_BY_KEY.get(key, "unknown")
    mapper = _TOPIC_MAPPERS.get(topic)
    fields = mapper(decoded["items"]) if mapper else {}
    if topic == "unknown":
        logger.debug("未知消息类型 %s/%s，仅透传", key[0], key[1])
    return {
        "topic": topic,
        "key": "%d/%d" % key,
        "type": decoded["type"],
        "command": decoded["command"],
        "time": decoded["time"],
        "fields": fields,
        "items": decoded["items"],
        "recv_monotonic": recv_monotonic if recv_monotonic is not None else time.monotonic(),
        "recv_wall": time.time(),
        "source": {"ip": addr[0] if addr else None, "port": addr[1] if addr else None},
        "raw_len": len(data),
    }


def confidence_report() -> Dict[str, Dict[str, str]]:
    """返回逐字段置信度表，供 /api/v1/schema 与《字段核对报告》使用。"""
    return FIELD_CONFIDENCE
