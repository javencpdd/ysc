"""发现器（ADR-016 §3）单元测试。

原则：**一个字节的网络都不许发**。所有外部命令都注入假 runner。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from m20_ai_detect import discover as D
from m20_ai_detect.discover import (
    Candidate,
    build_probe_cmd,
    classify,
    discover,
    probe_uri,
    read_mediamtx_paths,
)


def runner_of(rc: int, err: str = ""):
    """构造假 runner：记录调用、返回固定结果。"""
    calls = []

    def _run(cmd, timeout):
        calls.append((cmd, timeout))
        return rc, "", err

    return _run, calls


class TestClassify(unittest.TestCase):
    def test_all_verdicts(self):
        cases = [
            (0, "", "ok"),
            (1, "401 Unauthorized", "auth_required"),
            (1, "Connection refused", "refused"),
            (1, "Connection timed out", "timeout"),
            (124, "", "timeout"),
            (1, "No route to host", "refused"),
            (1, "Invalid data found", "no_frame"),
        ]
        for rc, err, want in cases:
            with self.subTest(err=err or "rc0"):
                self.assertEqual(classify(rc, err), want)


class TestProbeCommand(unittest.TestCase):
    def test_nostdin_is_mandatory(self):
        """不放 -nostdin，脚本里 ffmpeg 会进交互模式卡死（部署记录里踩过）。"""
        self.assertIn("-nostdin", build_probe_cmd("rtsp://h/p"))

    def test_rtsp_forces_tcp(self):
        cmd = build_probe_cmd("rtsp://h/p")
        self.assertIn("-rtsp_transport", cmd)
        self.assertIn("tcp", cmd)

    def test_rtmp_declares_flv(self):
        self.assertIn("flv", build_probe_cmd("rtmp://h/live/0"))

    def test_output_is_null(self):
        cmd = build_probe_cmd("rtsp://h/p")
        self.assertEqual(cmd[-3:], ["-f", "null", "-"])


class TestProbeUri(unittest.TestCase):
    def test_ok(self):
        run, calls = runner_of(0)
        c = probe_uri("rtsp://10.0.0.1:8554/video1", runner=run, timeout=1.5)
        self.assertEqual(c.verdict, "ok")
        self.assertEqual(c.type, "rtsp")
        self.assertEqual(c.name, "video1")
        self.assertEqual(c.uri, "rtsp://10.0.0.1:8554/video1")
        self.assertTrue(c.uri in calls[0][0])

    def test_refused(self):
        run, _ = runner_of(1, "Connection refused")
        c = probe_uri("rtsp://h/p", runner=run)
        self.assertEqual(c.verdict, "refused")

    def test_device_expands_to_path(self):
        """device:// 要展开成真实设备路径再交给 ffmpeg（这才是它能用的原因）。"""
        run, calls = runner_of(0)
        c = probe_uri("device:///dev/video0", runner=run)
        self.assertEqual(c.type, "device")
        self.assertIn("/dev/video0", calls[0][0])
        self.assertNotIn("device://", " ".join(calls[0][0]))

    def test_exception_never_escapes(self):
        def boom(cmd, timeout):
            raise RuntimeError("nope")

        c = probe_uri("rtsp://h/p", runner=boom)
        self.assertIn(c.verdict, ("timeout", "no_frame"))
        self.assertIn("nope", c.detail)

    def test_name_sanitized(self):
        run, _ = runner_of(0)
        c = probe_uri("rtsp://h/m20 front cam", runner=run)
        self.assertEqual(c.name, "m20_front_cam")


class TestMediaMtxConfig(unittest.TestCase):
    def test_read_paths_from_temp_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "mediamtx.yml")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(
                    "paths:\n"
                    "  video1:\n    source: publisher\n"
                    "  video2:\n    source: publisher\n"
                    "  all_others:\n    source: publisher\n"
                )
            self.assertEqual(read_mediamtx_paths([p]), ["video1", "video2"])

    def test_missing_file_is_fine(self):
        self.assertEqual(read_mediamtx_paths(["/nonexistent/x.yml"]), [])


class TestDiscoverScope(unittest.TestCase):
    def test_unknown_scope(self):
        r = discover("nope")
        self.assertTrue(r["ok"])
        self.assertIn("未知 scope", r["notes"][0])
        self.assertEqual(r["candidates"], [])

    def test_host_scope_probes_candidates(self):
        run, calls = runner_of(0)
        with mock.patch.object(D, "probe_http_api", return_value=[]):
            r = discover(
                "host:192.0.2.10",
                paths=["video1", "video2"],
                runner=run,
                timeout=1.0,
                budget_s=10.0,
            )
        self.assertTrue(r["ok"])
        uris = [c["uri"] for c in r["candidates"]]
        self.assertIn("rtsp://192.0.2.10:554/video1", uris)
        self.assertIn("rtsp://192.0.2.10:8554/video2", uris)
        self.assertTrue(all(c["verdict"] == "ok" for c in r["candidates"]))

    def test_explicit_port_skips_port_guessing(self):
        run, _ = runner_of(0)
        with mock.patch.object(D, "probe_http_api", return_value=[]):
            r = discover("host:192.0.2.10:1935", paths=["live/0"], runner=run, timeout=1.0)
        self.assertEqual([c["uri"] for c in r["candidates"]], ["rtmp://192.0.2.10:1935/live/0"])

    def test_api_wins_over_brute_force(self):
        """L1 命中清单就不该再穷举（省时间、省对方资源）。"""
        run, calls = runner_of(0)
        with mock.patch.object(D, "probe_http_api", return_value=["video1", "video2"]):
            r = discover("host:192.0.2.10", runner=run, timeout=1.0)
        self.assertEqual(calls, [])  # 一次 ffmpeg 都没起
        names = [c["name"] for c in r["candidates"]]
        self.assertEqual(names, ["video1", "video2"])
        self.assertEqual(r["candidates"][0]["via"], "api")

    def test_local_devices_are_unresolved_not_ok(self):
        """本机设备不自动抓帧：device 要平台放行，且可能独占设备句柄。"""
        with mock.patch.object(D, "discover_local_devices", return_value=["/dev/video0"]):
            with mock.patch.object(D, "discover_media_ports", return_value=[]):
                with mock.patch.object(D, "read_mediamtx_paths", return_value=[]):
                    r = discover("local", timeout=0.1)
        devs = [c for c in r["candidates"] if c["type"] == "device"]
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0]["uri"], "device:///dev/video0")
        self.assertEqual(devs[0]["verdict"], "unresolved")
        self.assertTrue(any("ALLOW_LOCAL_DEVICE" in n for n in r["notes"]))

    def test_failed_probes_are_demoted(self):
        """排序：能用的排前面，连不上的排最后（UI 直接按数组顺序渲染）。"""

        def flaky(cmd, timeout):
            joined = " ".join(cmd)
            return (0, "", "") if "video1" in joined else (1, "", "Connection refused")

        with mock.patch.object(D, "probe_http_api", return_value=[]):
            r = discover("host:192.0.2.10:8554", paths=["video1", "video2"], runner=flaky)
        verdicts = [c["verdict"] for c in r["candidates"]]
        self.assertEqual(verdicts, ["ok", "refused"])


class TestRanking(unittest.TestCase):
    def test_ok_beats_refused_and_dedups(self):
        cands = [
            Candidate("a", "rtsp://h/1", "rtsp", "refused", "probe"),
            Candidate("b", "rtsp://h/1", "rtsp", "ok", "probe"),
            Candidate("c", "rtsp://h/2", "rtsp", "timeout", "probe"),
        ]
        got = D._filter_interesting(cands)
        # 同一 uri 保留最好的判定；ok 的整体排在前面
        self.assertEqual([c.uri for c in got], ["rtsp://h/1", "rtsp://h/2"])
        self.assertEqual([c.verdict for c in got], ["ok", "timeout"])


if __name__ == "__main__":
    unittest.main()
