"""ASDU 解析器 —— 协议与领域模型之间的**防腐层（ACL）**（PLAN §3 / §10）。

这是整个设计里唯一不可妥协的边界：协议怎么变，都关在本文件里。

协议真相（PROTOCOL.md §1/§2，docs/04 §1.3 原文核实）：
    16 字节二进制帧头 + UTF-8 JSON 信封 {"PatrolDevice": {Type, Command, Time, Items}}
    帧头 = EB 91 EB 90(4) + dataSize LE16(2) + messageID LE16(2) + protocolType(1) + RESERVE(7×00)

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
HEAD_TAG = b"\xeb\x91\xeb\x90"
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
                 message_id: int = 0, time_str: str = "") -> bytes:
    """把 PatrolDevice 消息编码为「16 字节帧头 + JSON」字节流。"""
    envelope = {
        "PatrolDevice": {
            "Type": int(type_),
            "Command": int(command),
            "Time": time_str or time.strftime("%Y-%m-%d %H:%M:%S"),
            "Items": items or {},
        }
    }
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    header = HEADER_STRUCT.pack(HEAD_TAG, len(body), message_id & 0xFFFF, PROTOCOL_TYPE_JSON)
    return header + body


def decode_frame(data: bytes) -> Dict[str, Any]:
    """解码一帧：校验帧头 + 长度，返回 PatrolDevice 字典。

    失败抛 ProtocolError（调用方负责计入死信，不向外扩散）。
    """
    if len(data) < HEADER_SIZE:
        raise ProtocolError("帧长 %d < 帧头 16 字节" % len(data))
    tag, data_size, message_id, protocol_type = HEADER_STRUCT.unpack_from(data, 0)
    if tag != HEAD_TAG:
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
    }


# ---------------------------------------------------------------- 字段映射
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
        "led": items.get("Led"),
        "dev_enable": items.get("DevEnable"),
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
