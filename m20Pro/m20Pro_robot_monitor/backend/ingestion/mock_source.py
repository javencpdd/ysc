"""MockSource：构造 / 回放 ASDU 报文，供无真机开发与单测（PLAN §14.1 D3 / T1.3）。

覆盖**全部 5 类状态消息**（PLAN §10.4 确切结构），并尽量贴近真实：
- 用 ``asdu_parser.encode_frame`` 生成**真实字节帧**（16 字节帧头 + JSON），
  因此 MockSource 会把「解析」这一段真实跑通，而不是绕过；
- 轮足 16 关节、BatteryList 多电池、ErrorList 均按 docs/04 结构构造。

另支持**文件回放模式**（T2.6）：读取录制好的 JSONL（每行一帧，含 t 与 hex），
按时间戳重发，用于 M2 之后的无真机回归。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ingestion import asdu_parser
from ingestion.data_source import DataSource
from logging_setup import get_logger

logger = get_logger("ingestion.mock")

#: 各 topic 的推送频率（docs/04 §1.3：基础 2Hz / 运控 10Hz / 设备 2Hz / 异常 2Hz+变更）
#: 频率取自 docs/04 §1.3；nav/ack 取 2026-10-14 真机抓包实测值
TOPIC_HZ = {"basic": 2.0, "motion": 10.0, "device": 2.0, "fault": 2.0,
            "sleep": 0.2, "nav": 1.0}


def _items_basic(seq: int = 0) -> Dict[str, Any]:
    """基础状态 1002/6。"""
    motion = [0, 1, 1, 1, 4, 17][seq % 6]
    return {"BasicStatus": {
        "MotionState": motion,                       # 空闲/站立/…/RL控制
        "Gait": [0x1001, 0x3002, 0x3003][seq % 3],
        "Charge": 0,
        "HES": 0,
        "ControlUsageMode": 0,                       # 常规模式（轴指令前提）
        "Direction": 0,
        "OOA": 0,
        "PowerManagement": 0,
        "Sleep": 0,
        "Version": "PRO",
    }}


def _items_motion(seq: int = 0) -> Dict[str, Any]:
    """运控状态 1002/4：轮足 16 关节。"""
    t = seq / 10.0
    # Joint[16]：4 腿 × (hip_x, hip_y, knee, wheel)
    joints = [round(0.15 * math.sin(t + i * 0.4), 4) for i in range(asdu_parser.JOINT_COUNT)]
    motor = {"Joint": joints}
    for i, name in enumerate(asdu_parser.JOINT_NAMES):
        # 命名字段与 Joint 数组保持一致（docs/04 两种表示并存）
        # 关节名形如 "LF_hip_x"，按第一个下划线拆分
        leg, part = name.split("_", 1)
        key = "%s%s" % (asdu_parser._LEG_PREFIX[leg], asdu_parser._PART_SUFFIX[part])
        motor[key] = joints[i]
    return {
        "MotionStatus": {
            "Roll": round(0.02 * math.sin(t), 4),
            "Pitch": round(0.03 * math.cos(t), 4),
            "Yaw": round(0.1 * math.sin(t / 3.0), 4),
            "OmegaZ": round(0.05 * math.cos(t / 2.0), 4),
            "LinearX": round(0.2 * math.sin(t / 4.0), 4),
            "LinearY": round(0.05 * math.cos(t / 5.0), 4),
            "Height": 0.42, "Payload": 0.0, "RemainMile": 12.5,
        },
        "MotorStatus": motor,
    }


def _items_device() -> Dict[str, Any]:
    """设备状态 1002/5：BatteryList（多电池，块数待真机核实）。"""
    return {"BatteryList": [{
        "Voltage": 50.4, "BatteryLevel": 86.5,
        "battery_temperature": 31.0, "charge": False, "serial": "BAT-A",
    }]}


def _items_fault() -> Dict[str, Any]:
    """异常状态 1002/3：ErrorList（正常时为空列表）。"""
    return {"ErrorList": []}


def _items_sleep() -> Dict[str, Any]:
    """休眠状态查询响应 1101/7。"""
    return {"Sleep": 0, "Auto": True, "Time": 10}


def _items_nav() -> Dict[str, Any]:
    """导航状态 + 定位位姿 1002/7 —— **真机抓包实测新增**（2026-10-14，1Hz）。"""
    return {
        "NavStatus": {"Value": 0, "Status": 0, "ErrorCode": 0,
                      "LoopCnt": 0, "RemainingCnt": 0, "Name": ""},
        "LocationStatus": {"Location": 1, "PosX": 0.0, "PosY": 0.0, "PosZ": 0.0,
                           "Roll": 0.0, "Pitch": 0.0, "Yaw": 0.0,
                           "Confidence": 0.5, "Relocation": 1},
    }


#: topic -> (type, command, items 构造函数)
TOPIC_BUILDERS = {
    "basic": (1002, 6, _items_basic),
    "motion": (1002, 4, _items_motion),
    "device": (1002, 5, _items_device),
    "fault": (1002, 3, _items_fault),
    "sleep": (1101, 7, _items_sleep),
    "nav": (1002, 7, _items_nav),      # 真机实测新增（1Hz）
}


class MockSource(DataSource):
    """构造/回放报文的数据源。"""

    mode = "mock"

    def __init__(self, replay_file: str = "", topics: Optional[List[str]] = None,
                 hz_override: Optional[Dict[str, float]] = None,
                 seed: int = 20261014) -> None:
        super().__init__()
        self.replay_file = replay_file or ""
        self.topics = topics or list(TOPIC_BUILDERS.keys())
        self.hz = dict(TOPIC_HZ)
        if hz_override:
            self.hz.update(hz_override)
        self._seed = seed
        self._seq = 0
        self._thread: Optional[threading.Thread] = None
        self.emitted = 0
        self._replay: List[Tuple[float, bytes]] = []
        if self.replay_file:
            self._replay = self._load_replay(self.replay_file)

    # ---------------------------------------------------------- 构造单帧
    def build_bytes(self, topic: str, seq: Optional[int] = None) -> bytes:
        """构造某一 topic 的真实字节帧。"""
        type_, command, builder = TOPIC_BUILDERS[topic]
        seq = self._seq if seq is None else seq
        # _items_motion/_items_basic 接受 seq，其余不需要
        try:
            items = builder(seq)
        except TypeError:
            items = builder()
        return asdu_parser.encode_frame(type_, command, items, message_id=seq & 0xFFFF)

    def emit_once(self, topic: Optional[str] = None) -> int:
        """立即发射一帧（每个 topic 一帧）；供单测与手动触发。返回发射帧数。"""
        targets = [topic] if topic else self.topics
        count = 0
        for t in targets:
            data = self.build_bytes(t, self._seq)
            self._seq += 1
            self.emitted += 1
            count += 1
            self._emit({"kind": "raw", "data": data, "addr": ("127.0.0.1", 30000)})
        return count

    # ---------------------------------------------------------- 回放模式
    @staticmethod
    def _load_replay(path: str) -> List[Tuple[float, bytes]]:
        """加载 JSONL 回放文件：每行 {"t": 秒, "hex": "..."}。"""
        frames: List[Tuple[float, bytes]] = []
        if not os.path.isfile(path):
            logger.warning("回放文件不存在: %s", path)
            return frames
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    frames.append((float(rec.get("t", 0.0)), bytes.fromhex(rec["hex"])))
                except (ValueError, KeyError) as exc:
                    logger.warning("回放记录解析失败已跳过: %s", exc)
        logger.info("已加载回放帧 %d 条: %s", len(frames), path)
        return frames

    def replay_all(self) -> int:
        """按时间戳重发全部回放帧（测试/回归用，不做实时限速）。"""
        for _t, data in self._replay:
            self.emitted += 1
            self._emit({"kind": "raw", "data": data, "addr": ("127.0.0.1", 30000)})
        return len(self._replay)

    # ---------------------------------------------------------- 生命周期
    def start(self) -> None:
        if self._running:
            return
        if self._replay:
            self._running = True
            self._thread = threading.Thread(target=self._replay_loop, name="m20-replay", daemon=True)
        else:
            random.seed(self._seed)
            self._running = True
            self._thread = threading.Thread(target=self._gen_loop, name="m20-mock", daemon=True)
        self._thread.start()
        logger.info("MockSource 已启动: 主题=%s 回放=%s", self.topics, bool(self._replay))

    def _gen_loop(self) -> None:
        """按各 topic 频率定时构造帧。"""
        next_at = {t: time.monotonic() for t in self.topics}
        while self._running:
            now = time.monotonic()
            soonest = None
            for t in self.topics:
                if now >= next_at[t]:
                    self.emit_once(t)
                    next_at[t] = now + (1.0 / max(0.1, self.hz.get(t, 1.0)))
                soonest = next_at[t] if soonest is None else min(soonest, next_at[t])
            delay = max(0.01, (soonest or (now + 0.05)) - time.monotonic())
            time.sleep(min(delay, 0.2))

    def _replay_loop(self) -> None:
        """按录制间隔重放（T2.6）。"""
        start = time.monotonic()
        base = self._replay[0][0] if self._replay else 0.0
        for t, data in self._replay:
            if not self._running:
                break
            wait = (t - base) - (time.monotonic() - start)
            if wait > 0:
                time.sleep(wait)
            self.emitted += 1
            self._emit({"kind": "raw", "data": data, "addr": ("127.0.0.1", 30000)})

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("MockSource 已停止（累计发射 %d 帧）", self.emitted)

    def stats(self) -> Dict[str, Any]:
        base = super().stats()
        base.update({"emitted": self.emitted, "topics": list(self.topics),
                     "replay": bool(self._replay)})
        return base
