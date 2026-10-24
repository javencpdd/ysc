"""雷达默认关闭策略（**显式配置开关**，2026-10-20 加）。

## 这个模块解决什么问题

雷达供电是运行期开关（``1101/3 {"Lidar":{...}}``），本身**不跨重启保持**：
按取证结论，整车休眠会连带断传感器、唤醒会恢复相机/雷达/灯/风扇供电
（见 ``note/逆向与真机取证笔记.md`` §4.3）。所以"每次开机 / 唤醒后雷达又自己开了"
是预期行为，不是 bug。

如果使用者这段时间只用遥测和相机、不跑建图导航，就希望雷达**默认不要开**。
本模块把这件事做成一个**显式开关**（``M20_CONTROL__LIDAR_DEFAULT_OFF`` 或
页面「机器人设置」里的雷达默认关闭），而不是悄悄改掉开机行为。

## 触发时机（只有这两个，绝不循环）

1. **服务启动**：等首个设备帧到达（拿得到雷达当前值）后应用一次；
2. **唤醒整车（1101/6）之后**：唤醒会恢复传感器供电，故按同样条件再应用一次。

刻意**不做周期性巡检**：那会和"操作员刚手动打开雷达"对着干 —— 默认语义应该是
"每次上电/唤醒后的初值"，不是"永远不许开"。

## 三重自我保护（不信任调用方，也不信任配置）

1. 开关没开 → 一条不发；
2. 雷达**已经是关的**（前/后都是 0）→ 一条不发（启动时绝大多数情况就是这种）；
3. 车在**站立 / RL 态** → 跳过（与人工操作共用同一道运动锁，
   见 ``ControlGateway.execute_system_device``）；
4. 两次自动下发之间限速（``MIN_INTERVAL_S``），连点「唤醒」也不会突发。

## 影响面（2026-10-20 两台主机实测）

关雷达 = 建图 / 定位 / 导航 / 自动回充失去输入：AOS 的 ``lio-perception`` /
``height_map_nav`` / ``rob_bag``，NOS 的 ``localization`` / ``map_server`` /
``astar_node`` / ``localPlanner`` / ``pcl_remove`` / ``charge_manager``
（``rslidar`` 会持续刷 ``ERRCODE_MSOPTIMEOUT``）。
遥测 / 控制 / 相机 / 推流 / GPS / 网页控制台**不受影响**。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from control import patrol_codec

logger = logging.getLogger(__name__)

#: 运动状态中文名（与前端 MotionPanel / asdu_parser 的标注保持一致）。
#: 只用于状态展示，不参与任何判定 —— 判定一律用 patrol_codec 的常量。
MOTION_LABEL = {
    patrol_codec.MOTION_IDLE: "空闲",
    patrol_codec.MOTION_STAND: "站立",
    patrol_codec.MOTION_DAMPING_SOFT_ESTOP: "软急停阻尼",
    patrol_codec.MOTION_BOOT_DAMPING: "开机阻尼",
    patrol_codec.MOTION_LIE_DOWN: "趴下",
    patrol_codec.MOTION_RL: "RL 控制",
}

#: 两次自动下发之间的最小间隔（秒）：防连点「唤醒」造成指令突发
MIN_INTERVAL_S = 10.0
#: 启动后等设备帧的耐心（秒）。mock 数据源也会推设备帧，超时只是不应用
STARTUP_WAIT_S = 60.0
#: 等待期间的轮询步长（秒）
POLL_S = 0.5


class LidarDefaultPolicy:
    """雷达默认关闭的判定 + 下发 + 状态记录。

    线程安全：``maybe_apply`` 可能被启动等待线程、HTTP 处理线程同时调到，
    用一把锁把"判定 → 下发 → 记录"做成原子操作（避免两次触发各发一帧）。
    """

    def __init__(self, gateway: Any,
                 device_provider: Callable[[], Dict[str, Any]],
                 basic_provider: Callable[[], Dict[str, Any]],
                 enabled: bool = False,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time) -> None:
        self._gateway = gateway
        self._device_provider = device_provider
        self._basic_provider = basic_provider
        self._enabled_cfg = bool(enabled)
        #: 运行时覆盖：None = 用部署配置值；True/False = 页面改过（重启后回到配置值）
        self._override: Optional[bool] = None
        self._lock = threading.RLock()
        self._clock = clock
        self._wall = wall_clock
        self._last_apply_at: Optional[float] = None
        #: 最近一次"应用尝试"的结果（含被跳过的原因），供页面展示
        self._last: Dict[str, Any] = {
            "at": None, "at_wall": None, "outcome": "never",
            "reason": "", "detail": "", "trigger": ""
        }

    # ------------------------------------------------------------ 开关
    @property
    def enabled(self) -> bool:
        """当前是否生效（运行时覆盖优先于部署配置）。"""
        return self._override if self._override is not None else self._enabled_cfg

    @property
    def source(self) -> str:
        """开关值来自哪里：``config``（部署配置）还是 ``runtime``（页面改过）。"""
        return "runtime" if self._override is not None else "config"

    def set_enabled(self, value: bool) -> Dict[str, Any]:
        """页面开关：改运行时值。返回当前状态（不负责下发，见 :meth:`maybe_apply`）。"""
        with self._lock:
            self._override = bool(value)
            logger.info("雷达默认开关被页面修改: %s（来源=%s）", self.enabled, self.source)
            return self.status()

    # ------------------------------------------------------------ 状态
    def status(self) -> Dict[str, Any]:
        """给页面 / API 的状态快照（只读，无副作用）。"""
        lidar = self._lidar_now()
        basic = self._basic_provider() or {}
        motion = basic.get("motion_state")
        with self._lock:
            last = dict(self._last)
        return {
            "enabled": self.enabled,
            "source": self.source,
            "config_value": self._enabled_cfg,
            "lidar_now": lidar,
            "motion_state": motion,
            "motion_label": basic.get("motion_state_label")
            or (MOTION_LABEL.get(motion, "—") if motion is not None else "—"),
            "last_apply": last,
        }

    # ------------------------------------------------------------ 应用
    def maybe_apply(self, trigger: str = "") -> Dict[str, Any]:
        """按当前条件决定是否下发一次"关闭雷达"。

        ``trigger``：``startup`` / ``wake`` / ``manual``，只进日志与状态展示。

        返回 dict：``{"outcome": ..., "reason": ..., "detail": ...}``，
        outcome ∈ ``applied`` / ``skipped`` / ``failed``。
        """
        with self._lock:
            if not self.enabled:
                return self._record("skipped", "disabled",
                                    "雷达默认关闭未开启（部署配置与页面开关均为关）", trigger)
            lidar = self._lidar_now()
            if lidar is None:
                return self._record("skipped", "no_device_data",
                                    "还没收到设备帧，无法判断雷达当前状态", trigger)
            if all(int(v) == 0 for v in lidar.values()):
                return self._record("skipped", "already_off",
                                    "雷达已是关闭状态，无需下发", trigger)
            motion = (self._basic_provider() or {}).get("motion_state")
            if motion in (patrol_codec.MOTION_STAND, patrol_codec.MOTION_RL):
                return self._record(
                    "skipped", "motion_locked",
                    "站立 / RL 态禁止关闭雷达（与人工操作同一道闸），本次跳过", trigger)
            now = self._clock()
            if (self._last_apply_at is not None
                    and now - self._last_apply_at < MIN_INTERVAL_S):
                return self._record("skipped", "too_soon",
                                    "距上次自动下发不足 %.0fs，本次跳过" % MIN_INTERVAL_S,
                                    trigger)
            res = self._gateway.execute_system_device(
                "device_switch", {"items": {"Lidar": {"Front": 0, "Back": 0}}},
                actor="system", reason="lidar_default_off:%s" % (trigger or "auto"))
            if res.get("ok"):
                self._last_apply_at = now
                return self._record("applied", "ok", "已下发关闭雷达（前/后）", trigger)
            return self._record("failed", res.get("reason") or "rejected",
                                res.get("detail") or "下发被拒", trigger)

    def apply_after_startup(self, is_stale: Callable[[str], bool],
                            should_stop: Optional[Callable[[], bool]] = None) -> None:
        """启动路径：等到设备帧新鲜（或超时）后应用一次。

        跑在守护线程里 —— **不阻塞** ``MonitorService.start()``。
        设备帧一直不来（链路断 / mock 无数据）就静默结束，不留线程。
        """
        deadline = self._wall() + STARTUP_WAIT_S
        while self._wall() < deadline:
            if should_stop is not None and should_stop():
                return
            try:
                if not is_stale("device"):
                    break
            except Exception as exc:  # noqa: BLE001 - 状态读取异常不该拖死线程
                logger.debug("启动等设备帧时读取状态失败: %s", exc)
            time.sleep(POLL_S)
        else:
            logger.info("雷达默认关闭：等待设备帧超时（%.0fs），本次不应用", STARTUP_WAIT_S)
            return
        logger.info("雷达默认关闭：已收到设备帧，按启动条件应用一次")
        self.maybe_apply("startup")

    # ------------------------------------------------------------ 内部
    def _lidar_now(self) -> Optional[Dict[str, int]]:
        """当前雷达供电（原始 DevEnable 结构）。拿不到返回 None，不猜。"""
        dev = self._device_provider() or {}
        enable = dev.get("dev_enable") or {}
        lidar = enable.get("Lidar")
        if not isinstance(lidar, dict):
            return None
        return {k: int(v) for k, v in lidar.items() if v is not None}

    def _record(self, outcome: str, reason: str, detail: str,
                trigger: str) -> Dict[str, Any]:
        """记录最近一次尝试（原子区内调用，勿在锁外直接改 ``_last``）。"""
        now = self._clock()
        self._last = {
            "at": round(now, 1), "at_wall": round(self._wall(), 1),
            "outcome": outcome, "reason": reason, "detail": detail,
            "trigger": trigger
        }
        if outcome != "skipped":
            logger.info("雷达默认关闭[%s] %s: %s（%s）", trigger or "auto",
                        outcome, detail, reason)
        else:
            logger.debug("雷达默认关闭[%s] 跳过: %s（%s）", trigger or "auto",
                         detail, reason)
        return dict(self._last)
