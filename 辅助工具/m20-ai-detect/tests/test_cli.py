"""cli 层的 doctor 门禁测试。

重点回归：**独立运行 doctor 时 Store 尚未构造**，六个数据子目录不存在——
`_check_storage` 曾因探针路径 `base/tmp/` 缺失而误报 FAIL（2026-10-15 修复）。
本测试用"ffmpeg 缺失 + Detector 打桩"把检查项收敛到 storage，锁定该行为。
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from m20_ai_detect import cli  # noqa: E402


def _run_doctor(base_dir: str) -> tuple:
    """在隔离 base_dir 下跑 doctor，返回 (退出码, stdout)。"""
    env = {
        "M20AI_BASE_DIR": base_dir,
        "M20AI_ENABLE_F": "1",
        "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
        "M20AI_CAM_NAME_F": "front",
        "M20AI_ENABLE_B": "0",
    }
    buf = io.StringIO()
    with mock.patch.dict(os.environ, env), \
         mock.patch.object(cli.shutil, "which", return_value=None), \
         mock.patch.object(cli, "_check_health", return_value=None):
        with redirect_stdout(buf):
            rc = cli.main(["doctor"])
    return rc, buf.getvalue()


class DoctorStorageTest(unittest.TestCase):
    def test_storage_passes_when_subdirs_missing(self):
        """tmp/ 等子目录不存在时，storage 必须 PASS（曾误报 FAIL）。"""
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "workspace-not-created-yet")
            rc, out = _run_doctor(base)
            # ffmpeg 缺失 → 整体退出码非 0，但 storage 行必须是 PASS
            self.assertNotEqual(rc, 0)
            self.assertIn("[PASS] storage", out)
            self.assertIn("可写", out)

    def test_doctor_is_idempotent(self):
        """doctor 可重复跑：第一次建的目录不影响第二次结果。"""
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "ws")
            rc1, out1 = _run_doctor(base)
            rc2, out2 = _run_doctor(base)
            self.assertEqual(rc1, rc2)
            self.assertIn("[PASS] storage", out1)
            self.assertIn("[PASS] storage", out2)

    def test_missing_env_via_bad_fps_exits_2(self):
        """配置非法时 doctor 返回 2 且不打堆栈。"""
        with tempfile.TemporaryDirectory() as td:
            env = {"M20AI_BASE_DIR": td, "M20AI_FPS": "999"}
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env):
                with redirect_stdout(buf):
                    rc = cli.main(["doctor"])
            self.assertEqual(rc, 2)
            self.assertIn("配置错误", buf.getvalue())


def _run_doctor_clock(base_dir: str, info, ts_offset: str = "0"):
    """时钟门禁专用：info 为假的服务端健康信息，ts_offset 为 M20AI_TS_OFFSET_SEC。"""
    env = {
        "M20AI_BASE_DIR": base_dir,
        "M20AI_ENABLE_F": "1",
        "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
        "M20AI_CAM_NAME_F": "front",
        "M20AI_ENABLE_B": "0",
        "M20AI_TS_OFFSET_SEC": ts_offset,
    }
    buf = io.StringIO()
    with mock.patch.dict(os.environ, env), \
         mock.patch.object(cli.shutil, "which", return_value=None), \
         mock.patch.object(cli, "_check_health", return_value=info):
        with redirect_stdout(buf):
            rc = cli.main(["doctor"])
    return rc, buf.getvalue()


class DoctorClockTest(unittest.TestCase):
    """ADR-004：时钟门禁按"偏移量"语义判定——车队 PTP 钉 2024 不是故障。"""

    def test_unconfigured_passes_and_reports_offset(self):
        with tempfile.TemporaryDirectory() as td:
            future = datetime.now(timezone.utc) + timedelta(seconds=73100565)
            _rc, out = _run_doctor_clock(td, {"server_time": future.isoformat()})
            self.assertIn("[PASS] clock", out)
            self.assertIn("车队 PTP", out)

    def test_configured_matching_passes(self):
        with tempfile.TemporaryDirectory() as td:
            future = datetime.now(timezone.utc) + timedelta(seconds=3600)
            _rc, out = _run_doctor_clock(td, {"server_time": future.isoformat()}, ts_offset="3600")
            self.assertIn("[PASS] clock", out)

    def test_configured_drift_warns(self):
        """钉值与实测偏差 >2s → WARN（提醒更新 M20AI_TS_OFFSET_SEC）。"""
        with tempfile.TemporaryDirectory() as td:
            future = datetime.now(timezone.utc) + timedelta(seconds=3600)
            _rc, out = _run_doctor_clock(td, {"server_time": future.isoformat()}, ts_offset="3605")
            self.assertIn("[WARN] clock", out)

    def test_no_date_header_warns(self):
        with tempfile.TemporaryDirectory() as td:
            _rc, out = _run_doctor_clock(td, None)
            self.assertIn("[WARN] clock", out)
            self.assertIn("Date", out)


if __name__ == "__main__":
    unittest.main()
