"""命令行入口：run / doctor / stats / paths。

``doctor`` 把上线前的门禁检查一次性跑完（对应方案里的 V0″）：
  ffmpeg 是否可用、AI 服务是否健康、**时钟偏差**（拿服务端 Date 头当标准时间）、
  每路源能否真的抽出帧、目标目录可写、磁盘余量。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

from . import __version__
from .config import Config, ConfigError
from .detect import Detector
from .sampler import Sampler
from .store import Store


def _log(msg: str) -> None:
    stamp = datetime.now().isoformat(timespec="milliseconds")
    print("[%s] %s" % (stamp, msg), flush=True)


class Report:
    """ doctor 的结果收集器：每项 PASS/WARN/FAIL + 摘要。"""

    def __init__(self) -> None:
        self.rows: List[tuple] = []

    def add(self, name: str, status: str, detail: str) -> None:
        self.rows.append((name, status, detail))
        print("  [%s] %-22s %s" % (status, name, detail), flush=True)

    @property
    def failed(self) -> bool:
        return any(r[1] == "FAIL" for r in self.rows)

    def summary(self) -> str:
        counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for _n, s, _d in self.rows:
            counts[s] += 1
        return "doctor: %d PASS / %d WARN / %d FAIL" % (
            counts["PASS"],
            counts["WARN"],
            counts["FAIL"],
        )


def _check_ffmpeg(cfg: Config, rep: Report) -> bool:
    exe = shutil.which(cfg.ffmpeg_bin)
    if not exe:
        rep.add("ffmpeg", "FAIL", "找不到 %s（apt install ffmpeg 或设 M20AI_FFMPEG_BIN）" % cfg.ffmpeg_bin)
        return False
    try:
        out = subprocess.run(
            [exe, "-version"], capture_output=True, timeout=15
        ).stdout.decode("utf-8", "replace")
        first = out.splitlines()[0] if out else ""
        rep.add("ffmpeg", "PASS", "%s（%s）" % (first[:40], exe))
        return True
    except Exception as exc:
        rep.add("ffmpeg", "FAIL", "执行失败：%s" % exc)
        return False


def _check_health(cfg: Config, detector: Detector, rep: Report) -> Optional[dict]:
    ok, info = detector.health()
    if not ok:
        rep.add("ai_health", "FAIL", "%s（%s）" % (cfg.health_url, info.get("error")))
        return None
    ready = info.get("ready_capability_count")
    total = info.get("capability_count")
    device = info.get("default_device")
    status = "PASS" if (ready == total and ready) else "WARN"
    rep.add(
        "ai_health",
        status,
        "200 ok, 能力 %s/%s, device=%s, models=%d"
        % (ready, total, device, len(info.get("loaded_models") or [])),
    )
    return info


def _check_clock(cfg: Config, info: Optional[dict], rep: Report, warn_sec: float = 2.0) -> None:
    """时钟门禁（ADR-004 改写）。

    车队 PTP 主时钟把系统时间钉在 2024-06-20，"本机 vs 服务端偏差"必然是
    846 天量级——这不是故障，是环境。因此本检查改为验证**偏移量**：
      * 未配置 M20AI_TS_OFFSET_SEC：PASS，打印实测偏移（采样器启动时自动测量）；
      * 已配置：实测偏移与配置值偏差 >warn_sec 判 WARN（钉值已漂移，该更新）。
    """
    if not info or not info.get("server_time"):
        rep.add("clock", "WARN", "服务端未返回 Date 头，跳过")
        return
    try:
        server = datetime.fromisoformat(info["server_time"])
    except ValueError:
        rep.add("clock", "WARN", "无法解析服务端时间 %r" % info["server_time"])
        return
    if server.tzinfo is None:
        server = server.replace(tzinfo=timezone.utc)
    measured = (server - datetime.now(timezone.utc)).total_seconds()
    if cfg.ts_offset_sec != 0.0:
        drift = abs(measured - cfg.ts_offset_sec)
        status = "PASS" if drift <= warn_sec else "WARN"
        rep.add(
            "clock",
            status,
            "实测偏移 %.1f s / 配置 %.1f s / 偏差 %.1f s（>%.0fs 判 WARN：更新 M20AI_TS_OFFSET_SEC）"
            % (measured, cfg.ts_offset_sec, drift, warn_sec),
        )
    else:
        rep.add(
            "clock",
            "PASS",
            "本机时钟比标准时间慢 %.1f s（车队 PTP 基准钉在 2024，见 ADR-004）；"
            "采样器启动时自动测量并修正 JSONL 时间戳" % measured,
        )


def _check_source(cfg: Config, cam, rep: Report) -> bool:
    """真抽一帧：既验证源可达，也量出单次启动抓帧的真实成本。"""
    exe = shutil.which(cfg.ffmpeg_bin)
    if not exe:
        return False
    tmp = os.path.join(cfg.base_dir, "tmp", "doctor_%s.jpg" % cam.name)
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    cmd = [exe, "-loglevel", "error", "-hide_banner"]
    if cam.src.startswith("rtsp://"):
        cmd += ["-rtsp_transport", "tcp"]
    elif cam.src.startswith("rtmp://"):
        cmd += ["-f", "flv"]
    cmd += list(cfg.ffmpeg_extra)
    cmd += ["-i", cam.src, "-frames:v", "1", "-y", tmp]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=max(20, cfg.timeout * 3))
    except subprocess.TimeoutExpired:
        rep.add("source:%s" % cam.name, "FAIL", "抽帧超时 >%ds" % max(20, cfg.timeout * 3))
        return False
    wall = time.time() - t0
    if proc.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        rep.add(
            "source:%s" % cam.name,
            "FAIL",
            "抽帧失败 rc=%d %s" % (proc.returncode, (err[-1] if err else "")[:80]),
        )
        return False
    size = os.path.getsize(tmp)
    rep.add(
        "source:%s" % cam.name,
        "PASS",
        "单帧 %d KB，冷启动抓帧 %.2f s（常驻后可忽略）" % (size // 1024, wall),
    )
    try:
        os.remove(tmp)
    except OSError:
        pass
    return True


def _check_storage(cfg: Config, rep: Report) -> None:
    base = cfg.base_dir
    try:
        # 独立跑 doctor 时 Store 尚未构造，六个子目录可能不存在；
        # 探针走 tmp/，必须先保证它存在（与 Store.__init__ 的目录清单一致）
        os.makedirs(os.path.join(base, "tmp"), exist_ok=True)
        probe = os.path.join(base, "tmp", ".doctor_probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        writable = True
    except OSError as exc:
        writable = False
        rep.add("storage", "FAIL", "%s 不可写：%s" % (base, exc))
    if writable:
        usage = shutil.disk_usage(base)
        free_gb = usage.free / 1073741824.0
        status = "PASS" if free_gb >= 5 else "WARN"
        rep.add("storage", status, "%s 可写，剩余 %.1f GB" % (base, free_gb))


def cmd_doctor(args: argparse.Namespace) -> int:
    print("== m20-ai-detect doctor ==")
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print("配置错误：%s" % exc)
        return 2
    print("配置：cap=%s cameras=%s base=%s" % (cfg.cap_id, [c.name for c in cfg.cameras], cfg.base_dir))
    rep = Report()
    # 健康/时钟检查不依赖 ffmpeg：缺 ffmpeg 不应掩盖"AI 服务不可达"这类真实故障
    detector = Detector(cfg)
    info = _check_health(cfg, detector, rep)
    _check_clock(cfg, info, rep)
    if _check_ffmpeg(cfg, rep):
        for cam in cfg.cameras:
            _check_source(cfg, cam, rep)
    _check_storage(cfg, rep)
    print("== %s ==" % rep.summary())
    return 1 if rep.failed else 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print("配置错误：%s" % exc)
        return 2
    store = Store(cfg, log=_log)
    sampler = Sampler(cfg, store, log=_log)
    try:
        return sampler.run()
    except KeyboardInterrupt:
        sampler.stop()
        return 0


def cmd_stats(args: argparse.Namespace) -> int:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print("配置错误：%s" % exc)
        return 2
    store = Store(cfg)
    for key, value in store.stats().items():
        if isinstance(value, int):
            print("%-14s %.2f MB" % (key, value / 1048576.0))
        else:
            print("%-14s %s" % (key, value))
    return 0


def cmd_paths(args: argparse.Namespace) -> int:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print("配置错误：%s" % exc)
        return 2
    store = Store(cfg)
    for name in ("spool_dir", "raw_dir", "results_dir", "alerts_dir", "log_dir", "tmp_dir"):
        print("%-12s %s" % (name, getattr(store, name)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="m20-ai-detect",
        description="M20 Pro 视频流 → 外部 AI 识别服务 采样与落库（零第三方依赖）",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="启动采样器（前台运行，systemd 用它）")
    run.set_defaults(func=cmd_run)

    doctor = sub.add_parser("doctor", help="上线前门禁检查（V0″）")
    doctor.set_defaults(func=cmd_doctor)

    stats = sub.add_parser("stats", help="查看各目录占用与结果文件")
    stats.set_defaults(func=cmd_stats)

    paths = sub.add_parser("paths", help="打印实际使用的目录")
    paths.set_defaults(func=cmd_paths)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
