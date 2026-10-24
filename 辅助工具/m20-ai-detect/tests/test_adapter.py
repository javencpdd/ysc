"""适配层（ADR-016 §2）单元测试。

老行为是底线：``rtsp://`` → ``-rtsp_transport tcp``、``rtmp://`` → ``-f flv``、
``http(s)://*.mjpg`` → ``-f mjpeg`` —— 这几条一旦变了，GOS 上的两路 RTSP 就废了。
"""
from __future__ import annotations

import unittest

from m20_ai_detect.capture import build_ffmpeg_cmd, build_snapshot_cmd
from m20_ai_detect.config import Config, Source
from m20_ai_detect.sources import resolve


def cfg_of(**over) -> Config:
    base = dict(ffmpeg_bin="ffmpeg", fps=1.0, jpeg_q=3, cameras=[])
    base.update(over)
    return Config(**base)  # type: ignore[arg-type]


class TestResolveLegacy(unittest.TestCase):
    """回归底线：改造前后必须完全一致。"""

    def test_rtsp_forces_tcp(self):
        r = resolve(Source("front", "rtsp://10.21.31.103:8554/video1"))
        self.assertEqual(r.type, "rtsp")
        self.assertEqual(r.target, "rtsp://10.21.31.103:8554/video1")
        self.assertEqual(list(r.input_args), ["-rtsp_transport", "tcp"])
        self.assertTrue(r.low_delay)

    def test_rtmp_declares_flv(self):
        r = resolve(Source("x", "rtmp://192.168.2.1:1935/live/0"))
        self.assertEqual(r.type, "rtmp")
        self.assertEqual(list(r.input_args), ["-f", "flv"])
        self.assertTrue(r.low_delay)

    def test_mjpeg_over_http(self):
        for uri in ("http://h/c.mjpg", "https://h/c.mjpeg", "http://h/c.mjpg?x=1"):
            r = resolve(Source("x", uri))
            self.assertEqual(list(r.input_args), ["-f", "mjpeg"])

    def test_plain_http_no_demuxer(self):
        self.assertEqual(list(resolve(Source("x", "http://h/stream")).input_args), [])

    def test_raw_path_untouched(self):
        r = resolve(Source("x", "/dev/video0"))
        self.assertEqual(r.type, "raw")
        self.assertEqual(r.target, "/dev/video0")
        self.assertEqual(list(r.input_args), [])

    def test_empty_uri(self):
        r = resolve(Source("x", ""))
        self.assertEqual(r.target, "")


class TestResolveNewTypes(unittest.TestCase):
    def test_device_absolute(self):
        r = resolve(Source("cam0", "device:///dev/video2"))
        self.assertEqual(r.type, "device")
        self.assertEqual(r.target, "/dev/video2")
        self.assertEqual(list(r.input_args), ["-f", "v4l2"])
        self.assertTrue(r.needs_local_ok)

    def test_device_shorthand_numeric(self):
        self.assertEqual(resolve(Source("c", "device://1")).target, "/dev/video1")

    def test_device_default_video0(self):
        self.assertEqual(resolve(Source("c", "device://")).target, "/dev/video0")

    def test_file_strips_scheme(self):
        r = resolve(Source("f", "file:///tmp/clip.mp4"))
        self.assertEqual(r.type, "file")
        self.assertEqual(r.target, "/tmp/clip.mp4")
        self.assertEqual(list(r.input_args), [])

    def test_rtsp_plus_udp(self):
        r = resolve(Source("c", "rtsp+udp://h/p"))
        self.assertEqual(r.target, "rtsp://h/p")
        self.assertEqual(list(r.input_args), ["-rtsp_transport", "udp"])

    def test_rtsp_transport_field(self):
        r = resolve(Source("c", "rtsp://h/p", transport="udp"))
        self.assertEqual(list(r.input_args), ["-rtsp_transport", "udp"])

    def test_rtsp_unknown_transport_falls_back_to_tcp(self):
        self.assertEqual(
            list(resolve(Source("c", "rtsp://h/p", transport="quic")).input_args),
            ["-rtsp_transport", "tcp"],
        )

    def test_onvif_needs_resolution(self):
        r = resolve(Source("c", "onvif://192.168.1.64"))
        self.assertEqual(r.type, "onvif")
        self.assertFalse(r.needs_local_ok)

    def test_ffmpeg_input_shape(self):
        self.assertEqual(
            resolve(Source("c", "rtsp://h/p")).ffmpeg_input(),
            ["-rtsp_transport", "tcp", "-i", "rtsp://h/p"],
        )


class TestBuildCommands(unittest.TestCase):
    def test_snapshot_keeps_low_delay_flags(self):
        cmd = build_snapshot_cmd(Source("c", "rtsp://h/p"), cfg_of())
        self.assertIn("-rtsp_transport", cmd)
        self.assertIn("tcp", cmd)
        self.assertIn("nobuffer", " ".join(cmd))

    def test_snapshot_no_low_delay_for_file(self):
        cmd = build_snapshot_cmd(Source("c", "file:///tmp/a.mp4"), cfg_of())
        self.assertNotIn("nobuffer", " ".join(cmd))

    def test_global_extra_between_input_and_output(self):
        cfg = cfg_of(ffmpeg_extra=("-hwaccel", "none"))
        cmd = build_snapshot_cmd(Source("c", "rtsp://h/p"), cfg)
        joined = " ".join(cmd)
        self.assertLess(joined.index("-hwaccel"), joined.index("-frames:v"))

    def test_per_source_extra_after_global(self):
        cfg = cfg_of(ffmpeg_extra=("-hwaccel", "none"))
        cam = Source("c", "rtsp://h/p", extra=("-vf", "hflip"))
        joined = " ".join(build_snapshot_cmd(cam, cfg))
        self.assertLess(joined.index("-hwaccel"), joined.index("hflip"))

    def test_per_source_fps_wins(self):
        cfg = cfg_of(fps=1.0)
        self.assertIn("fps=1", " ".join(build_ffmpeg_cmd(Source("c", "rtsp://h/p"), cfg, "%d.jpg")))
        cmd = build_ffmpeg_cmd(Source("c", "rtsp://h/p", fps=3.0), cfg, "%d.jpg")
        self.assertIn("fps=3", " ".join(cmd))

    def test_device_cmd_allowed_when_opted_in(self):
        """放行后命令行里出现 -f v4l2 不该再被 _assert_safe 拦。"""
        cfg = cfg_of(allow_local_device=True)
        cmd = build_snapshot_cmd(Source("c", "device:///dev/video0"), cfg)
        self.assertIn("v4l2", " ".join(cmd))
        self.assertIn("/dev/video0", cmd)

    def test_forbidden_token_in_raw_src_raises(self):
        cfg = cfg_of()
        with self.assertRaises(RuntimeError) as cm:
            build_snapshot_cmd(Source("c", "push_video://h/p"), cfg)
        self.assertIn("push_video", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
