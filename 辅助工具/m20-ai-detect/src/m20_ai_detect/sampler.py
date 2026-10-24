"""采样主循环：把 capture / detect / store 串起来。

主循环刻意做成"每路独立、可单测"：
  * ``_process_camera()`` 只做"扫描 spool → 推理 → 落库"，不碰 ffmpeg，
    测试里可以用假 Detector 直接驱动；
  * ``run()`` 负责拉起抽帧进程与退避重试。
"""
from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from .capture import Capture
from .config import Camera, Config
from .detect import DetectResult, Detector, measure_clock_offset
from .store import Store

Log = Callable[[str], None]


def _default_hostname() -> str:
    """跨平台取主机名（os.uname 在 Windows 不存在，开发机常在 Windows）。"""
    try:
        return os.uname().nodename  # type: ignore[attr-defined]
    except AttributeError:
        return socket.gethostname()


class Sampler:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        detector: Optional[Detector] = None,
        log: Optional[Log] = None,
        hostname: Optional[str] = None,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.detector = detector or Detector(cfg)
        self.log = log or print
        self.hostname = hostname or _default_hostname()
        self.captures: List[Capture] = []
        # ★逐路退避（ADR-016 §5）：按 cam.name 分组。
        # 原因：只有一把全局退避时，一路坏源（相机掉电、流断了）会把**所有**源一起
        # 拖慢，表现为"另一路明明好的也不出帧"。现在每路各退各的。
        self._backoffs: Dict[str, float] = {}
        self._backoff = cfg.retry_base  # 旧字段保留：给外部只读/旧测试看，不再参与决策
        self._running = True
        self.ts_offset = cfg.ts_offset_sec
        self._last_prune = 0.0
        self._last_saved_prune = 0.0

    # ------------------------------------------------------------ 时钟校准
    def calibrate_clock(self) -> float:
        """确定时钟偏移量（秒），返回生效值。

        配置值优先；未配置（0）时启动时自动向 AI 服务 Date 头测量。
        测量失败则退化为 0（本机时间）并记日志——不阻断运行。
        背景见 ADR-004：车队 PTP 主时钟把系统时间钉在 2024。
        """
        if self.cfg.ts_offset_sec != 0.0:
            self.ts_offset = self.cfg.ts_offset_sec
            self.log("clock offset %.1f s (M20AI_TS_OFFSET_SEC)" % self.ts_offset)
            return self.ts_offset
        offset = measure_clock_offset(self.cfg, self.detector)
        if offset is None:
            self.ts_offset = 0.0
            self.log(
                "clock offset measurement failed (AI service unreachable?); "
                "falling back to host time; consider setting M20AI_TS_OFFSET_SEC"
            )
            return 0.0
        self.ts_offset = offset
        self.log("clock offset %.1f s (auto-measured vs AI server Date header)" % offset)
        return offset

    def _now_pair(self) -> Tuple[str, str]:
        """返回 (ts, ts_host)：ts 为偏移修正后的真实时间，ts_host 为本机原值。"""
        now = datetime.now()
        return (
            (now + timedelta(seconds=self.ts_offset)).isoformat(timespec="milliseconds"),
            now.isoformat(timespec="milliseconds"),
        )

    # ------------------------------------------------------------ 主循环
    def run(self) -> int:
        cfg = self.cfg
        self.calibrate_clock()
        self.log(
            "start cap=%s cameras=%s base=%s ring=%.0fMB"
            % (cfg.cap_id, [c.name for c in cfg.enabled_cameras], cfg.base_dir, cfg.ring_max_bytes / 1048576)
        )
        for cam in cfg.enabled_cameras:
            self.captures.append(
                Capture(cam, cfg, self.store.spool_for(cam.name), self.log)
            )
        try:
            while self._running:
                progressed = False
                for cam, capture in zip(cfg.enabled_cameras, self.captures):
                    if not capture.alive:
                        if not capture.ensure_running():
                            continue
                    progressed = self._process_camera(cam) or progressed
                self.store.enforce_ring()
                self._maybe_prune_results()
                self._maybe_prune_saved()
                if not progressed:
                    time.sleep(0.5)
        finally:
            for capture in self.captures:
                capture.stop()
        self.log("stopped")
        return 0

    def stop(self) -> None:
        self._running = False

    def _maybe_prune_results(self) -> None:
        """results/ 保留策略（M20AI_RESULTS_KEEP_DAYS，0=永不删）：每小时检查一次。"""
        if self.cfg.results_keep_days <= 0:
            return
        now = time.time()
        if now - self._last_prune < 3600:
            return
        self._last_prune = now
        self.store.prune_results(self.cfg.results_keep_days)

    def _maybe_prune_saved(self) -> None:
        """saved/ 留存清理（ADR-008，M20AI_SAVED_MAX_MB / M20AI_SAVED_KEEP_DAYS）。

        超上限或超龄的成对 .jpg/.json 从最旧开始删；每 10 分钟检查一次
        （any 模式约 1GB/天量级，10 分钟粒度把超出上限的余量压在几十 MB 内）。
        """
        if self.cfg.saved_max_bytes <= 0 and self.cfg.saved_keep_days <= 0:
            return
        now = time.time()
        if now - self._last_saved_prune < 600:
            return
        self._last_saved_prune = now
        self.store.clean_saved(self.cfg.saved_max_bytes, self.cfg.saved_keep_days)

    # ------------------------------------------------------------ 单路处理
    def _process_camera(self, cam: Camera) -> bool:
        """处理一路的全部待推理帧。返回本帧是否成功落库（用于退避决策）。"""
        progressed = False
        spool = self.store.spool_for(cam.name)
        try:
            names = sorted(n for n in os.listdir(spool) if n.endswith(".jpg"))
        except OSError:
            return False
        # spool 防爆：AI 长时间不可用时抽帧仍在继续，若无上限会无限增长撑爆磁盘。
        # 超限丢最旧的（信息价值最低），并限流记日志（每分钟最多一条）。
        limit = getattr(self.cfg, "spool_max_files", 600)
        if len(names) > limit:
            drop = names[:len(names) - limit]
            for n in drop:
                try:
                    os.unlink(os.path.join(spool, n))
                except OSError:
                    pass
            self._spool_dropped = getattr(self, "_spool_dropped", 0) + len(drop)
            now2 = time.time()
            if now2 - getattr(self, "_spool_log_at", 0.0) >= 60.0:
                self._spool_log_at = now2
                self.log(
                    "spool 超限：丢弃最旧 %d 帧（上限 %d，累计已丢 %d）cam=%s"
                    % (len(drop), limit, self._spool_dropped, cam.name)
                )
            names = names[len(drop):]
        now = time.time()
        for name in names:
            if not self._running:
                break
            path = os.path.join(spool, name)
            try:
                # 小于 fresh_age_sec 的文件可能还在写，先不碰（名字有序，后面更新）
                if now - os.path.getmtime(path) < self.cfg.fresh_age_sec:
                    break
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            if not data:
                continue

            result = self.detector.detect(data, name)
            if not result.ok:
                self._on_failure(cam, name, result)
                break  # 退避期间停止发送，帧留在 spool 等重试
            self._set_backoff(cam, self.cfg.retry_base)
            self._on_success(cam, name, path, data, result)
            progressed = True
        return progressed

    # ------------------------------------------------------------ 回调
    def _backoff_of(self, cam: Camera) -> float:
        """该路当前的退避秒数（未记过则为配置的初始退避）。"""
        return self._backoffs.get(cam.name, self.cfg.retry_base)

    def _set_backoff(self, cam: Camera, value: float) -> None:
        self._backoffs[cam.name] = value
        self._backoff = value  # 镜像给旧字段（兼容旧的外部观察者）

    def _on_failure(self, cam: Camera, name: str, result: DetectResult) -> None:
        cur = self._backoff_of(cam)
        self._set_backoff(cam, min(cur * 2, self.cfg.retry_max))
        self.log(
            "detect FAIL cam=%s frame=%s err=%s backoff=%.0fs"
            % (cam.name, name, result.error, self._backoff_of(cam))
        )
        ts, ts_host = self._now_pair()
        self.store.append(
            {
                "v": 2,
                "ts": ts,
                "ts_host": ts_host,
                "ts_offset_sec": round(self.ts_offset, 3),
                "host": self.hostname,
                "cam": cam.name,
                "cap": self.cfg.cap_id,
                "event": "detect_fail",
                "frame": name,
                "error": str(result.error)[:200],
                "e2e_ms": result.wall_ms,
            }
        )
        time.sleep(self._backoff_of(cam))

    def _on_success(self, cam: Camera, name: str, path: str, data: bytes, result: DetectResult) -> None:
        payload = result.payload or {}
        items = ((payload.get("results") or {}).get("items")) or []
        # stem 与查看器约定一致：帧名去扩展名（帧名已含相机名前缀，无跨相机冲突）；
        # 控制台 /api/response?frame=&cam= 按 saved/<cam>/<stem>.json 查找（ADR-006）。
        stem = os.path.splitext(name)[0]
        ts, ts_host = self._now_pair()
        record = {
            "v": 2,
            "ts": ts,
            "ts_host": ts_host,
            "ts_offset_sec": round(self.ts_offset, 3),
            "host": self.hostname,
            "cam": cam.name,
            "cap": payload.get("capability", self.cfg.cap_id),
            "frame": name,
            "frame_sha1": self.store.sha1(data),
            "frame_bytes": len(data),
            "http": result.http_status,
            "elapsed_ms": payload.get("elapsed_ms"),
            "device": payload.get("device"),
            "provider": payload.get("provider"),
            "params": payload.get("params", {}),
            "e2e_ms": result.wall_ms,
            "result_image_saved": False,
        }
        record.update(self.store.summarize_items(items))
        is_alert = self._is_alert(items)
        if is_alert:
            record["alert"] = True
            self.log(
                "ALERT cam=%s frame=%s n=%d" % (cam.name, name, record["n_items"])
            )
        if self._should_save(is_alert, record["n_items"]):
            jpeg = self.detector.decode_result_image(payload)
            # meta 供时间轴（ADR-008）：_saved_at = 真实时间（含时钟偏移修正），
            # 时间轴 API 以它排序/显示，避免依赖相机时钟命名的文件名。
            img_rel, json_rel = self.store.save_pair(
                cam.name,
                stem,
                jpeg,
                payload,
                meta={"_saved_at": ts, "_alert": True if is_alert else None},
            )
            if img_rel:
                record["result_image_saved"] = True
                record["saved_image"] = img_rel
            if json_rel:
                record["resp_path"] = json_rel
            self.log(
                "SAVE cam=%s frame=%s mode=%s n=%d"
                % (cam.name, name, self.cfg.save_mode, record["n_items"])
            )
        self.store.append(record)

        # 原始帧移入环形缓冲
        dst = os.path.join(self.store.raw_for(cam.name), name)
        try:
            os.replace(path, dst)
        except OSError:
            pass

    def _is_alert(self, items: List[dict]) -> bool:
        if not self.cfg.alert_labels:
            return False
        for it in items:
            if it.get("label") in self.cfg.alert_labels and float(it.get("score", 0)) >= self.cfg.alert_score:
                return True
        return False

    def _should_save(self, is_alert: bool, n_items: int) -> bool:
        """响应留存触发判断（ADR-006，M20AI_SAVE_MODE）。

        off=不存；all=每帧；any=检出任意目标；alert=命中告警规则。
        """
        mode = self.cfg.save_mode
        if mode == "all":
            return True
        if mode == "any":
            return n_items > 0
        if mode == "alert":
            return is_alert
        return False
