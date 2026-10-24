"""视频代理：RTSP → HLS（PLAN §6.3 / ADR-003，T3.2–T3.4）。

为什么走 HLS 而不是浏览器直连 RTSP：
  - 浏览器不支持 RTSP；
  - 代理让前端只面对标准 HTTP，穿越代理/防火墙友好；
  - 延迟 1–3s 对**监控**可接受（遥控低延迟应走带安全闸的控制通道，不靠压视频延迟）。

**实测依据（2026-10-15 于 196）**：
  - 相机需先唤醒（`1101/6` Sleep=false）才会枚举 `/dev/video*` 并出现在 MediaMTX；
  - 流参数：`h264 (High) 800x600 30fps`，故可用 **`-c:v copy` 不转码**（196 的 ffmpeg 4.2.7
    **没有 rkmpp 硬编**，只有 libx264 软编——转码会吃掉 CPU，必须避免）；
  - 实测命令首个切片约 3.8s（含 RTSP 握手 + 等首帧关键帧）。

失败行为（PLAN §5.5）：上游断 → 保留最后的 m3u8/片段，
`status().available=False` → 前端显示"视频中断"而不是白屏。

⚠️ Python 3.8 兼容。
"""

from __future__ import annotations

import os
import posixpath
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from logging_setup import get_logger

logger = get_logger("video.proxy")

#: 默认 HLS 工作目录（部署时用 systemd Environment=M20_VIDEO__HLS_DIR 覆盖，
#: 196 上为 /home/djw/monitor/hls）
DEFAULT_HLS_DIR = "/tmp/m20-hls"


class VideoProxy:
    """ffmpeg 子进程托管：拉一路 RTSP → 切 HLS 片段。"""

    #: 进程"算活住了"的门槛（秒）。低于它退避继续翻倍。
    #: ⚠️ 曾经的写法是 Popen 成功就 `backoff = 2.0` —— 但**"起来"不等于"出流"**：
    #: 源站没推流时 ffmpeg 起来就 404 退出（`method DESCRIBE failed: 404`），
    #: 退避永远长不起来，变成每 2s 重启一次的死循环（2026-10-18 真机实测
    #: 连刷到第 14 次，每次都要重建 RTSP 连接 + 起进程，纯白耗资源）。
    STABLE_SECONDS = 10.0

    def __init__(self, rtsp_url: str, hls_dir: str = DEFAULT_HLS_DIR,
                 segment_seconds: float = 1.0, list_size: int = 3,
                 ffmpeg: str = "ffmpeg", max_restart_backoff: float = 30.0) -> None:
        self.rtsp_url = rtsp_url
        self.hls_dir = hls_dir
        self.segment_seconds = float(segment_seconds)
        self.list_size = int(list_size)
        self.ffmpeg = ffmpeg
        self._max_backoff = max_restart_backoff

        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        #: 本次进程的启动时刻（monotonic），用来算"活了多久"
        self._spawned_at: float = 0.0

        self.restart_count = 0
        self.last_error: Optional[str] = None
        self.started_at: Optional[float] = None

    # ------------------------------------------------------------ 命令构造
    def build_cmd(self, url: Optional[str] = None) -> List[str]:
        """构造 ffmpeg 命令（独立方法便于单测，不需要真跑 ffmpeg）。

        关键参数：
          - `-rtsp_transport tcp`：196 的 WiFi/内网丢包环境下 TCP 比 UDP 稳；
          - `-c:v copy`：**不转码**（无硬编，转码吃 CPU）；
          - `-fflags nobuffer -flags low_delay -probesize/analyzeduration`：压起播延迟；
          - `delete_segments+append_list`：磁盘不涨。
        """
        target = url or self.rtsp_url
        # ⚠️ 用 posixpath：这些路径是**远端 Linux 主机上 ffmpeg** 的参数。
        # 若用 os.path.join，在开发机（Windows）上会生成反斜杠，
        # 到 Linux 上变成非法路径（实测踩过：/tmp/m20-hls\seg_0.ts 无法创建）。
        playlist = posixpath.join(self.hls_dir, "live.m3u8")
        return [
            self.ffmpeg, "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer", "-flags", "low_delay",
            "-probesize", "32", "-analyzeduration", "0",
            "-i", target,
            "-c:v", "copy",
            "-f", "hls",
            "-hls_time", str(self.segment_seconds),
            "-hls_list_size", str(self.list_size),
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", posixpath.join(self.hls_dir, "seg_%d.ts"),
            playlist,
        ]

    # ------------------------------------------------------------ 生命周期
    def start(self) -> bool:
        """启动 ffmpeg 与守护线程。"""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            if not shutil.which(self.ffmpeg):
                self.last_error = "未找到 %s，视频代理不可用" % self.ffmpeg
                logger.warning("未找到 %s，视频代理不可用", self.ffmpeg)
                return False
            os.makedirs(self.hls_dir, exist_ok=True)
            try:
                self._proc = subprocess.Popen(
                    self.build_cmd(), stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE)
            except OSError as exc:
                self.last_error = "ffmpeg 启动失败: %s" % exc
                logger.warning("ffmpeg 启动失败: %s", exc)
                return False
            self.started_at = time.time()
            self._spawned_at = time.monotonic()
            self._stop.clear()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._supervise,
                                                name="m20-video-supervise",
                                                daemon=True)
                self._thread.start()
            logger.info("视频代理已启动: %s → %s", self.rtsp_url, self.hls_dir)
            return True

    def next_backoff(self, backoff: float, alive: float) -> float:
        """进程退出后，**下一轮**该等多久（独立方法便于单测）。

        ``alive`` 是刚死掉那个进程活了多久：活够 ``STABLE_SECONDS`` 说明
        它真的出过流，退避重置；否则翻倍。上限 ``_max_backoff``。
        """
        if alive >= self.STABLE_SECONDS:
            return 2.0
        return min(max(backoff, 2.0) * 2.0, self._max_backoff)

    def _supervise(self) -> None:
        """进程退出即按退避重启（上游断流恢复后自动重连）。

        退避规则（2026-10-18 修，见 ``STABLE_SECONDS``）：
        进程存活不足 ``STABLE_SECONDS`` 就退出 → 退避翻倍；真的活住了
        才重置回 2s。这样"源站没推流"时不会 2s 一次无限重启。
        """
        backoff = 2.0
        while not self._stop.is_set():
            proc = self._proc
            if proc is None:
                break
            rc = proc.poll()
            if rc is None:
                self._stop.wait(1.0)
                continue
            # ---- 进程已退出：先算它活了多久，再决定这一轮等多久
            alive = (time.monotonic() - self._spawned_at) if self._spawned_at else 0.0
            err = ""
            try:
                if proc.stderr:
                    err = (proc.stderr.read() or b"").decode("utf-8", "ignore")[:300]
            except Exception:  # noqa: BLE001
                pass
            self.last_error = "ffmpeg 退出(code=%s, 存活 %.1fs): %s" % (
                rc, alive, err.strip())
            wait_s = backoff
            backoff = self.next_backoff(backoff, alive)
            logger.warning("视频代理退出（存活 %.1fs），%.0fs 后重启: %s",
                           alive, wait_s, self.last_error)
            self._stop.wait(wait_s)
            if self._stop.is_set():
                break
            self.restart_count += 1
            try:
                self._proc = subprocess.Popen(
                    self.build_cmd(), stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE)
                self._spawned_at = time.monotonic()
                logger.info("视频代理已重启（第 %d 次，下次退避 %.0fs）",
                            self.restart_count, backoff)
            except OSError as exc:  # pragma: no cover
                self.last_error = "重启失败: %s" % exc
                backoff = min(backoff * 2, self._max_backoff)

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    self._proc.kill()
            self._proc = None
        logger.info("视频代理已停止")

    def switch(self, rtsp_url: str) -> bool:
        """切换视频源（前/后相机）。"""
        with self._lock:
            self.rtsp_url = rtsp_url
            old = self._proc
            self._proc = None
            if old is not None and old.poll() is None:
                old.terminate()
                try:
                    old.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    old.kill()
        logger.info("切换视频源: %s", rtsp_url)
        return self.start()

    # ------------------------------------------------------------ 状态
    def _last_segment_age(self) -> Optional[float]:
        """最新片段距现在的秒数（没有片段返回 None）。"""
        try:
            segs = [os.path.join(self.hls_dir, f) for f in os.listdir(self.hls_dir)
                    if f.startswith("seg_") and f.endswith(".ts")]
        except OSError:
            return None
        if not segs:
            return None
        newest = max(segs, key=lambda p: os.path.getmtime(p))
        return round(time.time() - os.path.getmtime(newest), 2)

    def status(self, stale_after: float = 5.0) -> Dict[str, Any]:
        """供 /api/v1/video/status 与前端降级判断。"""
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
        playlist = os.path.join(self.hls_dir, "live.m3u8")
        age = self._last_segment_age()
        available = bool(os.path.isfile(playlist)) and age is not None \
            and age <= stale_after
        return {
            "enabled": True,
            "running": running,
            "available": available,
            "rtsp_url": self.rtsp_url,
            "hls_url": "/hls/live.m3u8",
            "hls_dir": self.hls_dir,
            "last_segment_age": age,
            "restart_count": self.restart_count,
            "last_error": self.last_error,
            "uptime_seconds": round(time.time() - self.started_at, 1)
            if self.started_at else None,
        }
