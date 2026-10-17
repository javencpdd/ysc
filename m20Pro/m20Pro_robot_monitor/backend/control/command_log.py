"""指令报文记录（2026-10-17 加）：留下发出的**原始字节帧** + 机器人是否响应。

用户诉求：「像 lite3 控制台那样，保存发出的控制指令的报文，并给出是否成功响应的标记」。

为什么单开一个模块而不是塞进 ``ControlGateway._audit``：
    - 审计回答"谁在什么时候下了什么指令、被哪道闸拦了"（**操作视角**）；
    - 本模块回答"线上到底跑了哪些字节、机器人回了什么"（**报文视角**）。
    两者粒度不同：审计含被闸拒的（没有报文），报文记录含 20Hz 看门狗之外的
    每一次真实出包；硬合在一起会两边都说不清。

**响应三态语义（务必向用户讲清，否则会误导）**：
    - ``ok``          —— 收到响应且 ``ErrorCode == 0``
    - ``error``       —— 收到响应但 ``ErrorCode != 0``（附 ``ErrorMessage``）
    - ``no_response`` —— 超时未收到响应。**这不代表车没执行**：basic_server
                         对部分指令（如运动状态转换）执行了但并不回帧。
                         所以它是"不知道"，不是"失败"。
    - ``send_failed`` —— 本地 socket 都没发出去（压根没上线）
    - ``rejected``    —— 被安全闸拦下，从未生成报文

**匹配策略**：basic_server 的应答信封带回 ``Type``/``Command``（实测
``{"PatrolDevice":{"Items":{"ErrorCode":0},"Type":1101,"Command":3,...}}``），
故按 ``(Type, Command)`` 匹配、**FIFO 取最早未匹配的那条**。局限：同一
(Type, Command) 有多条在途而只回来一条时，会记在最早那条头上 —— 可接受，
因为控制台不会对同一指令并发下发（轴指令由看门狗串行化）。

⚠️ Python 3.8 兼容（196 实测 3.8.10）。
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

#: 响应状态取值（前端分色直接认这几个字符串）
RESP_OK = "ok"
RESP_ERROR = "error"
RESP_NO_RESPONSE = "no_response"
RESP_SEND_FAILED = "send_failed"
RESP_REJECTED = "rejected"
RESP_PENDING = "pending"

#: **查询类指令**的 (Type, Command) 白名单 —— 只有这些的应答进"查询缓存"。
#:
#: 为什么单独存一份、而不是复用在途指令的响应记录：
#: 查询是为了**拿到配置值**（如 1101/7 回 ``{"Sleep":0,"Auto":false,"Time":10}``），
#: 它与"某条在途指令被应答了"是两件事。缓存必须与在途匹配解耦，否则
#: 前端主动轮询拿到的值会被"谁发的"这类关联逻辑牵连。
#:
#: 白名单是必须的：``_on_frame`` 对**所有**收到的帧都会调 ``on_response``
#: （含 1002/5 设备帧，2Hz、带着几十个关节温度），不筛就等于把整机状态
#: 每 500ms 复制一份进缓存。
QUERY_KEYS = {
    (1101, 7): "sleep_config",     # GetSleepConfig
    (1101, 11): "auto_reset",      # GetAutoResetJointsZero
}

#: 默认超时（秒）。真机响应在毫秒级，2s 足够宽容；再长只会让用户干等。
DEFAULT_TIMEOUT_S = 2.0


class CommandLog:
    """有界环形报文记录 + 响应关联。线程安全由调用方保证（见下）。

    ⚠️ 写入发生在数据源线程（``_on_frame`` → ``on_response``）与 FastAPI
    线程（``record_sent`` / ``snapshot``）。CPython 下 deque.append 与 dict
    读写是原子的，且这里不做"读-改-写"的跨步操作（匹配是单次 popleft），
    故不加锁 —— 加锁反而会在高频回调上引入争用。
    """

    def __init__(self, size: int = 200, timeout_s: float = DEFAULT_TIMEOUT_S,
                 clock: Any = time.monotonic) -> None:
        self._items: Deque[Dict[str, Any]] = deque(maxlen=int(size))
        self._timeout_s = float(timeout_s)
        self._clock = clock
        self._seq = 0
        #: (type, command) -> 未匹配的 seq（FIFO）
        self._pending: Dict[Tuple[int, int], Deque[int]] = {}
        #: (type, command) -> {"items": {...}, "at": 时间戳}  查询类应答缓存
        self._queries: Dict[Tuple[int, int], Dict[str, Any]] = {}

    # ------------------------------------------------------------ 记录发送
    def record_sent(self, name: str, type_: int, command: int,
                    items: Optional[Dict[str, Any]], frame: bytes,
                    actor: str = "web", confirmed: bool = False,
                    forced: bool = False, message_id: int = 0) -> int:
        """记录一条**已生成报文**的指令（调用方负责确认真的发出去了）。"""
        self._seq += 1
        seq = self._seq
        self._items.append({
            "seq": seq,
            "ts": time.time(),
            "name": name,
            "type": int(type_),
            "command": int(command),
            "message_id": int(message_id),
            "items": dict(items or {}),
            "frame_hex": frame.hex(),
            "frame_len": len(frame),
            "actor": actor,
            "confirmed": bool(confirmed),
            "forced": bool(forced),
            "resp": {"status": RESP_PENDING},
        })
        self._pending.setdefault((int(type_), int(command)), deque()).append(seq)
        return seq

    def record_rejected(self, name: str, params: Optional[Dict[str, Any]],
                        reason: str, detail: str = "",
                        actor: str = "web", confirmed: bool = False) -> int:
        """记录一条**被安全闸拦下**的指令 —— 没有报文，但要让人看见"点了没反应"。"""
        self._seq += 1
        seq = self._seq
        self._items.append({
            "seq": seq,
            "ts": time.time(),
            "name": name,
            "type": None,
            "command": None,
            "message_id": None,
            "items": dict(params or {}),
            "frame_hex": None,
            "frame_len": 0,
            "actor": actor,
            "confirmed": bool(confirmed),
            "forced": False,
            "resp": {"status": RESP_REJECTED, "reason": reason, "detail": detail},
        })
        return seq

    def record_send_failed(self, name: str, type_: int, command: int,
                           items: Optional[Dict[str, Any]], frame: bytes,
                           detail: str = "") -> None:
        """socket 都没发出去：把对应 pending 直接判死，不等超时。"""
        key = (int(type_), int(command))
        q = self._pending.get(key)
        if q:
            q.popleft()
        for item in reversed(self._items):
            if item["name"] == name and item["frame_hex"] == frame.hex():
                item["resp"] = {"status": RESP_SEND_FAILED, "detail": detail,
                                "latency_ms": 0.0}
                return

    # ------------------------------------------------------------ 记录响应
    def on_response(self, type_: int, command: int,
                    items: Optional[Dict[str, Any]] = None,
                    frame: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
        """收到一帧机器人来的报文：若能匹配上某条在途指令，就落响应。

        返回被更新的记录（便于日志/测试），未匹配返回 ``None``。
        """
        key = (int(type_), int(command))
        # 查询缓存：必须**先于**在途匹配 —— 1101/11 这类查询即使无人等待
        # （比如前端还没轮询、或已被判超时），值本身仍然是有效的。
        if key in QUERY_KEYS and isinstance(items, dict) and items:
            self._queries[key] = {"items": dict(items), "at": time.time()}
        q = self._pending.get(key)
        if not q:
            return None
        seq = q.popleft()
        if not q:
            self._pending.pop(key, None)
        items = items or {}
        code = items.get("ErrorCode")
        try:
            code_int = int(code) if code is not None else None
        except (TypeError, ValueError):
            code_int = None
        status = RESP_OK if code_int in (0, None) else RESP_ERROR
        resp: Dict[str, Any] = {
            "status": status,
            "error_code": code_int,
            "error_message": items.get("ErrorMessage"),
            "frame_hex": frame.hex() if frame else None,
            "items": items,
        }
        for item in reversed(self._items):
            if item["seq"] == seq:
                latency = max(0.0, (time.time() - item["ts"]) * 1000.0)
                resp["latency_ms"] = round(latency, 1)
                item["resp"] = resp
                return item
        return None

    # ------------------------------------------------------------ 快照
    def _expire(self) -> None:
        """惰性超时判定：读出口扫一遍，把等太久的 pending 判为 ``no_response``。

        不做后台定时器 —— 报文记录的消费频率（WS 10Hz / 轮询 1.5s）远高于
        用户需要看到结果的频率，惰性判定足够且少一个线程。
        """
        now = time.time()
        for item in self._items:
            if item["resp"]["status"] != RESP_PENDING:
                continue
            if now - item["ts"] >= self._timeout_s:
                item["resp"] = {"status": RESP_NO_RESPONSE,
                                "latency_ms": round((now - item["ts"]) * 1000.0, 1)}

    def snapshot(self, limit: int = 60) -> Dict[str, Any]:
        """最新在前；附统计（前端角标用）。"""
        self._expire()
        items = list(self._items)
        items.reverse()
        items = items[:int(limit)]
        stats = {RESP_OK: 0, RESP_ERROR: 0, RESP_NO_RESPONSE: 0,
                 RESP_SEND_FAILED: 0, RESP_REJECTED: 0, RESP_PENDING: 0}
        for item in self._items:
            st = item["resp"]["status"]
            stats[st] = stats.get(st, 0) + 1
        return {
            "items": items,
            "stats": stats,
            "pending": sum(len(q) for q in self._pending.values()),
            "timeout_s": self._timeout_s,
        }

    def last(self) -> Optional[Dict[str, Any]]:
        """最近一条（含 pending）—— 全局角标用。"""
        self._expire()
        return self._items[-1] if self._items else None

    # ------------------------------------------------------------ 查询缓存
    def query(self, type_: int, command: int) -> Optional[Dict[str, Any]]:
        """取某条查询类指令的最新应答。

        返回 ``{"items": {...}, "age_s": 秒}``，从没收到过则返回 ``None``。
        ``age_s`` 必须给前端 —— 查询是"发起后异步到达"的，前端要靠它区分
        "还没问过" 和 "问过但车没答"，不能拿旧值冒充当前值。
        """
        entry = self._queries.get((int(type_), int(command)))
        if not entry:
            return None
        return {"items": dict(entry["items"]),
                "age_s": round(max(0.0, time.time() - entry["at"]), 2)}
