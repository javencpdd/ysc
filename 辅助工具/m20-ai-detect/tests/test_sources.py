"""多路视频源（ADR-016）单元测试。

重点验证三件事：
  1. 新语法能表达任意 N 路 + 逐路参数；
  2. **旧 env 一个字不改仍然跑得一样**（这是本轮改造的底线）；
  3. 非法输入给的是可操作的中文错误，而不是半路的 traceback。
"""
from __future__ import annotations

import unittest

from m20_ai_detect.config import (
    Config,
    ConfigError,
    Source,
    parse_sources,
)

RTSP = "rtsp://10.21.31.103:8554/video1"


def base_env(**over):
    env = {"M20AI_BASE_DIR": "/tmp/m20ai-test"}
    env.update(over)
    return env


class TestSourceModel(unittest.TestCase):
    def test_legacy_positional_construction_still_works(self):
        """Camera(name, src) 这种老写法必须继续可用。"""
        s = Source("front", RTSP)
        self.assertEqual(s.name, "front")
        self.assertEqual(s.src, RTSP)
        self.assertEqual(s.uri, RTSP)

    def test_type_from_scheme(self):
        cases = {
            RTSP: "rtsp",
            "rtsp+tcp://h/p": "rtsp",
            "rtmp://h/live/0": "rtmp",
            "device:///dev/video0": "device",
            "file:///tmp/a.mp4": "file",
            "https://h/m.jpg": "https",
            "http://h:80/x.mjpg": "http",
            "onvif://192.168.1.64": "onvif",
        }
        for uri, want in cases.items():
            with self.subTest(uri=uri):
                self.assertEqual(Source("c", uri).type, want)

    def test_effective_fps_inherits_global(self):
        self.assertEqual(Source("c", RTSP).effective_fps(1.0), 1.0)
        self.assertEqual(Source("c", RTSP, fps=2.5).effective_fps(1.0), 2.5)

    def test_to_dict_shape(self):
        d = Source("gate", "rtmp://h/live/0", transport="tcp", fps=2.0).to_dict()
        self.assertEqual(d["name"], "gate")
        self.assertEqual(d["type"], "rtmp")
        self.assertEqual(d["fps"], 2.0)
        self.assertTrue(d["enabled"])


class TestParseSources(unittest.TestCase):
    def test_single(self):
        got = parse_sources("front=" + RTSP)
        self.assertEqual([(s.name, s.uri) for s in got], [("front", RTSP)])

    def test_multi(self):
        got = parse_sources(
            "front=rtsp://h/v1;back=rtsp://h/v2;cam0=device:///dev/video0"
        )
        self.assertEqual([s.name for s in got], ["front", "back", "cam0"])
        self.assertEqual(got[2].type, "device")

    def test_newline_also_separates(self):
        got = parse_sources("a=rtsp://h/1\nb=rtmp://h/2")
        self.assertEqual([s.name for s in got], ["a", "b"])

    def test_commas_in_extra_survive(self):
        """分隔符必须是 ';' —— extra 里本来就有逗号。"""
        got = parse_sources("a=rtsp://h/1|extra=-vf,hflip")
        self.assertEqual(got[0].extra, ("-vf", "hflip"))

    def test_off_flag_disables(self):
        got = parse_sources("a=rtsp://h/1|off;b=rtsp://h/2")
        self.assertFalse(got[0].enabled)
        self.assertTrue(got[1].enabled)

    def test_per_source_fps_and_transport(self):
        got = parse_sources("a=rtsp://h/1|fps=2|transport=tcp")
        self.assertEqual(got[0].fps, 2.0)
        self.assertEqual(got[0].transport, "tcp")

    def test_empty_string(self):
        self.assertEqual(parse_sources(""), [])
        self.assertEqual(parse_sources("   "), [])

    def test_bad_fragment(self):
        for bad in ("front", "front|off", "=rtsp://h/1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    parse_sources(bad)

    def test_bad_name_charset(self):
        for bad in ("my cam=rtsp://h/1", "a/b=rtsp://h/1", "-x=rtsp://h/1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    parse_sources(bad)

    def test_bad_fps(self):
        for bad in ("abc", "0", "40"):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    parse_sources("a=rtsp://h/1|fps=" + bad)


class TestLegacyCompat(unittest.TestCase):
    def test_default_still_front_only(self):
        cfg = Config.from_env(base_env())
        self.assertEqual([c.name for c in cfg.cameras], ["front"])
        self.assertEqual(cfg.cameras[0].src, "rtsp://10.21.31.103:8554/video1")
        self.assertTrue(cfg.cameras[0].enabled)

    def test_enable_b_still_works(self):
        cfg = Config.from_env(base_env(M20AI_ENABLE_B="1", M20AI_SRC_B="rtsp://h/v2"))
        self.assertEqual([c.name for c in cfg.cameras], ["front", "back"])
        self.assertEqual(cfg.cameras[1].src, "rtsp://h/v2")

    def test_disable_front_alone_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_ENABLE_F="0"))

    def test_sources_overrides_legacy(self):
        cfg = Config.from_env(
            base_env(M20AI_ENABLE_F="1", M20AI_SOURCES="cam0=device:///dev/video0",
                 M20AI_ALLOW_LOCAL_DEVICE="1")
        )
        self.assertEqual([c.name for c in cfg.cameras], ["cam0"])


class TestConfigMultiSource(unittest.TestCase):
    def test_four_sources(self):
        cfg = Config.from_env(
            base_env(
                M20AI_SOURCES=(
                    "f=rtsp://h/1;b=rtsp://h/2;top=device:///dev/video1;"
                    "gate=rtmp://h/live/0|transport=tcp"
                ),
                M20AI_ALLOW_LOCAL_DEVICE="1",
            )
        )
        self.assertEqual(
            [(c.name, c.type) for c in cfg.cameras],
            [("f", "rtsp"), ("b", "rtsp"), ("top", "device"), ("gate", "rtmp")],
        )

    def test_duplicate_names_rejected(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_SOURCES="a=rtsp://h/1;a=rtsp://h/2"))

    def test_all_off_rejected(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_SOURCES="a=rtsp://h/1|off"))

    def test_empty_sources_list_rejected(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_SOURCES=";"))

    def test_device_uri_passes_forbidden_check(self):
        """device:// 必须能通过禁词校验（这是它存在的唯一理由）。"""
        cfg = Config.from_env(
            base_env(
                M20AI_SOURCES="cam0=device:///dev/video0",
                M20AI_ALLOW_LOCAL_DEVICE="1",
            )
        )
        self.assertEqual(cfg.cameras[0].type, "device")

    def test_device_needs_platform_opt_in(self):
        """不放行不许用 —— 这是 device:// 唯一的危险点（会被 upstream pkill 杀）。"""
        with self.assertRaises(ConfigError) as cm:
            Config.from_env(base_env(M20AI_SOURCES="cam0=device:///dev/video0"))
        self.assertIn("M20AI_ALLOW_LOCAL_DEVICE", str(cm.exception))

    def test_disabled_device_never_triggers_gate(self):
        """停用（|off）的设备源不参与采集，也就不需要放行。"""
        cfg = Config.from_env(
            base_env(M20AI_SOURCES="f=rtsp://h/1;cam0=device:///dev/video0|off")
        )
        self.assertEqual([c.name for c in cfg.enabled_cameras], ["f"])

    def test_raw_v4l2_args_still_rejected(self):
        """反过来：把 -f v4l2 写进地址必须被拒，并提示正确写法。"""
        with self.assertRaises(ConfigError) as cm:
            Config.from_env(base_env(M20AI_SOURCES="cam0=-f v4l2 -i /dev/video0"))
        self.assertIn("device://", str(cm.exception))

    def test_empty_sources_falls_back_to_legacy(self):
        """SOURCES 留空 = 没配 → 走旧语法（而不是"配了但为空"）。"""
        cfg = Config.from_env(base_env(M20AI_SOURCES="  "))
        self.assertEqual([c.name for c in cfg.cameras], ["front"])


if __name__ == "__main__":
    unittest.main()
