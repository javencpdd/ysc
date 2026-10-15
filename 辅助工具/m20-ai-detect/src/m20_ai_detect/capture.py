"""常驻 ffmpeg 抽帧进程的管理。

为什么必须常驻：单次启动 ffmpeg 抓 1 帧要 1.6~2.0 s（RTSP 握手开销，
2026-10-14 在 AOS 实测 1.63/2.01/2.00 s），比推理本身慢 20 倍。
常驻进程 + ``-vf fps=N`` 让抽帧成本趋近于零。
"""
from __future__ import annotations

import subprocess
import time
from typing import Callable, List, Optional

from .config import FORBIDDEN_TOKENS, Camera, Config

Log = Callable[[str], None]


def _input_args(cam: Camera) -> List[str]:
    """按源协议补输入参数：RTSP 强制 TCP；RTMP 声明 flv；mjpeg over http 声明封装。"""
    if cam.src.startswith("rtsp://"):
        return ["-rtsp_transport", "tcp"]
    if cam.src.startswith("rtmp://"):
        return ["-f", "flv"]  # RTMP 必须显式声明封装，否则 ffmpeg 认不出
    if cam.src.startswith(("http://", "https://")) and cam.src.endswith((".mjpg", ".mjpeg")):
        return ["-f", "mjpeg"]
    return []


def build_ffmpeg_cmd(cam: Camera, cfg: Config, out_pattern: str) -> List[str]:
    """拼出常驻抽帧命令。按协议自动补输入参数，并对命令行做安全自检。"""
    cmd: List[str] = [cfg.ffmpeg_bin, "-loglevel", "error", "-hide_banner"]
    cmd += _input_args(cam)
    cmd += list(cfg.ffmpeg_extra)
    cmd += [
        "-i", cam.src,
        "-vf", "fps=%g" % cfg.fps,
        "-q:v", str(cfg.jpeg_q),
        "-strftime", "1",
        "-f", "image2",
        out_pattern,
    ]
    _assert_safe(cmd)
    return cmd


def build_snapshot_cmd(cam: Camera, cfg: Config) -> List[str]:
    """单次抓拍命令（控制台「相机画面」，ADR-012）：一次握手抓 1 帧、mjpeg 输出到 stdout。

    与常驻抽帧的差异：不做 fps 过滤、不落盘、抓完即退。RTSP 单次握手实测
    1.6~2.0 s（2026-10-14 AOS），调用方必须带超时与短缓存（见 snapshot.py）。
    """
    cmd: List[str] = [cfg.ffmpeg_bin, "-loglevel", "error", "-hide_banner"]
    cmd += _input_args(cam)
    cmd += list(cfg.ffmpeg_extra)
    cmd += [
        "-i", cam.src,
        "-frames:v", "1",
        "-q:v", str(cfg.jpeg_q),
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
    ]
    _assert_safe(cmd)
    return cmd


def _assert_safe(cmd: List[str]) -> None:
    """防止命令行里出现上游 pkill 的关键词（见 config.FORBIDDEN_TOKENS）。"""
    joined = " ".join(cmd)
    for token in FORBIDDEN_TOKENS:
        if token in joined:
            raise RuntimeError(
                "ffmpeg 命令行含禁用关键词 %r，会被机器人上游 restart.sh 误杀：%s"
                % (token, joined)
            )


class Capture:
    """一路源的抽帧进程：崩溃自动重启 + 指数退避。"""

    def __init__(self, cam: Camera, cfg: Config, out_dir: str, log: Log) -> None:
        self.cam = cam
        self.cfg = cfg
        self.out_dir = out_dir
        self.log = log
        self._proc: Optional[subprocess.Popen] = None
        self._backoff = 1.0

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.alive:
            return
        pattern = "%s/%s_%%Y%%m%%d_%%H%%M%%S.jpg" % (self.out_dir.rstrip("/"), self.cam.name)
        cmd = build_ffmpeg_cmd(self.cam, self.cfg, pattern)
        self.log("spawn capture cam=%s src=%s fps=%g" % (self.cam.name, self.cam.src, self.cfg.fps))
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            raise RuntimeError(
                "找不到 ffmpeg（%s）：请先安装（apt install ffmpeg）或用 M20AI_FFMPEG_BIN 指定路径"
                % self.cfg.ffmpeg_bin
            )

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3)
        except Exception:
            pass
        finally:
            self._proc = None

    def ensure_running(self) -> bool:
        """活着就返回 True；死了则按退避重启，返回 False（本次不重启）。"""
        if self.alive:
            self._backoff = 1.0
            return True
        rc = None if self._proc is None else self._proc.returncode
        self.log(
            "capture cam=%s exited rc=%s, restart in %.0fs"
            % (self.cam.name, rc, self._backoff)
        )
        time.sleep(self._backoff)
        self._backoff = min(self._backoff * 2, 60.0)
        if not self.alive:
            self.start()
        return False
