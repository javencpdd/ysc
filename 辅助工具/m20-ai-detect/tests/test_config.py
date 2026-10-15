import unittest

from m20_ai_detect.config import Config, ConfigError


def base_env(**over):
    env = {
        "M20AI_ENABLE_F": "1",
        "M20AI_SRC_F": "rtsp://10.21.31.103:8554/video1",
        "M20AI_BASE_DIR": "/tmp/m20ai-test",
    }
    env.update(over)
    return env


class TestConfig(unittest.TestCase):
    def test_defaults_and_urls(self):
        cfg = Config.from_env(base_env())
        self.assertEqual(cfg.task_url, "http://jsxy.aihyzh.com:30881/api/v1/tasks/ai-04-yolov8-object-detection")
        self.assertEqual(cfg.health_url, "http://jsxy.aihyzh.com:30881/api/v1/health")
        self.assertEqual(len(cfg.cameras), 1)
        self.assertEqual(cfg.cameras[0].name, "front")
        self.assertEqual(cfg.fps, 1.0)
        self.assertEqual(cfg.ring_max_bytes, 200 * 1024 * 1024)

    def test_rtmp_source_ok(self):
        cfg = Config.from_env(
            base_env(M20AI_SRC_F="rtmp://127.0.0.1:1936/live/m20pro-f", M20AI_CAM_NAME_F="m20pro-f")
        )
        self.assertEqual(cfg.cameras[0].src, "rtmp://127.0.0.1:1936/live/m20pro-f")

    def test_two_cameras(self):
        cfg = Config.from_env(
            base_env(
                M20AI_ENABLE_B="1",
                M20AI_SRC_B="rtsp://10.21.31.103:8554/video2",
                M20AI_CAM_NAME_F="front",
                M20AI_CAM_NAME_B="back",
            )
        )
        self.assertEqual([c.name for c in cfg.cameras], ["front", "back"])

    def test_no_camera_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_ENABLE_F="0"))

    def test_bad_fps_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_FPS="0"))
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_FPS="abc"))

    def test_bad_jpeg_q_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_JPEG_Q="99"))

    def test_bad_params_json_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_PARAMS_JSON="{not json"))
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_PARAMS_JSON="[1,2]"))

    def test_params_json_ok(self):
        cfg = Config.from_env(base_env(M20AI_PARAMS_JSON='{"obj_thresh": 0.3}'))
        self.assertEqual(cfg.params, {"obj_thresh": 0.3})

    def test_forbidden_token_in_src_raises(self):
        with self.assertRaises(ConfigError) as ctx:
            Config.from_env(base_env(M20AI_SRC_F="rtsp://127.0.0.1:8554/push_video"))
        self.assertIn("push_video", str(ctx.exception))

    def test_duplicate_camera_names_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(
                base_env(M20AI_ENABLE_B="1", M20AI_SRC_B="rtsp://10.21.31.103:8554/video2",
                         M20AI_CAM_NAME_B="front")
            )

    def test_alert_score_range(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_ALERT_SCORE="1.5"))

    def test_redacted_masks_credentials(self):
        cfg = Config.from_env(base_env(M20AI_AI_BASE="http://user:secret@example.com:8080"))
        self.assertNotIn("secret", cfg.redacted()["ai_base"])
        self.assertIn("***@", cfg.redacted()["ai_base"])

    def test_ffmpeg_extra_parsed(self):
        cfg = Config.from_env(base_env(M20AI_FFMPEG_EXTRA="-fflags nobuffer -rw_timeout 10000000"))
        self.assertEqual(cfg.ffmpeg_extra, ("-fflags", "nobuffer", "-rw_timeout", "10000000"))


class TestTsOffset(unittest.TestCase):
    """ADR-004：M20AI_TS_OFFSET_SEC 解析。

    车队 PTP 主时钟把系统时间钉在 2024-06-20，默认 0 表示"启动时自动测量"，
    非 0 表示手动钉值（漂移 >2s 时 doctor 告警）。
    """

    def test_default_zero_means_auto_measure(self):
        cfg = Config.from_env(base_env())
        self.assertEqual(cfg.ts_offset_sec, 0.0)

    def test_parses_float_and_negative(self):
        cfg = Config.from_env(base_env(M20AI_TS_OFFSET_SEC="73100565.5"))
        self.assertEqual(cfg.ts_offset_sec, 73100565.5)
        cfg2 = Config.from_env(base_env(M20AI_TS_OFFSET_SEC="-12.5"))
        self.assertEqual(cfg2.ts_offset_sec, -12.5)

    def test_non_numeric_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_TS_OFFSET_SEC="abc"))


class TestResultsKeepDays(unittest.TestCase):
    """M20AI_RESULTS_KEEP_DAYS 解析（0=永不删，控制台留存旋钮的后端）。"""

    def test_default_zero(self):
        cfg = Config.from_env(base_env())
        self.assertEqual(cfg.results_keep_days, 0.0)

    def test_parses_days(self):
        cfg = Config.from_env(base_env(M20AI_RESULTS_KEEP_DAYS="30"))
        self.assertEqual(cfg.results_keep_days, 30.0)

    def test_non_numeric_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_RESULTS_KEEP_DAYS="abc"))


class TestUnitsInConfig(unittest.TestCase):
    """ADR-010：体积/时长字段同时兼容"带单位"与"不带单位"两种写法。"""

    def test_size_bare_number_means_mb(self):
        cfg = Config.from_env(base_env(M20AI_RING_MAX_MB="200", M20AI_SAVED_MAX_MB="500"))
        self.assertEqual(cfg.ring_max_bytes, 200 * 1024 * 1024)
        self.assertEqual(cfg.saved_max_bytes, 500 * 1024 * 1024)

    def test_size_with_suffix(self):
        cfg = Config.from_env(
            base_env(M20AI_RING_MAX_MB="200M", M20AI_SAVED_MAX_MB="1G")
        )
        self.assertEqual(cfg.ring_max_bytes, 200 * 1024 * 1024)
        self.assertEqual(cfg.saved_max_bytes, 1024 * 1024 * 1024)

    def test_size_suffix_case_insensitive(self):
        cfg = Config.from_env(base_env(M20AI_SAVED_MAX_MB="1g"))
        self.assertEqual(cfg.saved_max_bytes, 1024 * 1024 * 1024)

    def test_size_fractional(self):
        cfg = Config.from_env(base_env(M20AI_SAVED_MAX_MB="0.5G"))
        self.assertEqual(cfg.saved_max_bytes, 512 * 1024 * 1024)

    def test_size_bad_unit_raises_with_hint(self):
        with self.assertRaises(ConfigError) as cm:
            Config.from_env(base_env(M20AI_SAVED_MAX_MB="1x"))
        msg = str(cm.exception)
        self.assertIn("M20AI_SAVED_MAX_MB", msg)
        self.assertIn("1x", msg)
        self.assertIn("裸数字按 MB", msg)

    def test_size_garbage_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_SAVED_MAX_MB="abc"))

    def test_days_bare_number_means_days(self):
        cfg = Config.from_env(base_env(M20AI_SAVED_KEEP_DAYS="7"))
        self.assertEqual(cfg.saved_keep_days, 7.0)

    def test_days_with_suffix(self):
        self.assertEqual(
            Config.from_env(base_env(M20AI_SAVED_KEEP_DAYS="7d")).saved_keep_days, 7.0
        )
        self.assertEqual(
            Config.from_env(base_env(M20AI_SAVED_KEEP_DAYS="24h")).saved_keep_days, 1.0
        )
        self.assertEqual(
            Config.from_env(base_env(M20AI_SAVED_KEEP_DAYS="2w")).saved_keep_days, 14.0
        )

    def test_days_bad_unit_raises_with_hint(self):
        with self.assertRaises(ConfigError) as cm:
            Config.from_env(base_env(M20AI_RESULTS_KEEP_DAYS="3y2"))
        self.assertIn("M20AI_RESULTS_KEEP_DAYS", str(cm.exception))

    def test_negative_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_SAVED_KEEP_DAYS="-3d"))

    def test_parse_helpers_directly(self):
        from m20_ai_detect.config import parse_days, parse_size_mb

        self.assertEqual(parse_size_mb("512K", "K"), 0.5)
        self.assertEqual(parse_size_mb("2T", "K"), 2 * 1024 * 1024.0)
        self.assertAlmostEqual(parse_days("60s", "K"), 60.0 / 86400, places=12)
        self.assertAlmostEqual(parse_days("30m", "K"), 30.0 / 1440, places=12)


class TestSaveMode(unittest.TestCase):
    """ADR-006：M20AI_SAVE_MODE 四值解析与旧开关兼容。"""

    def test_default_off(self):
        self.assertEqual(Config.from_env(base_env()).save_mode, "off")

    def test_parses_all_values(self):
        for m in ("off", "alert", "any", "all"):
            self.assertEqual(Config.from_env(base_env(M20AI_SAVE_MODE=m)).save_mode, m)

    def test_case_and_space_tolerated(self):
        self.assertEqual(Config.from_env(base_env(M20AI_SAVE_MODE=" ANY ")).save_mode, "any")

    def test_invalid_raises(self):
        with self.assertRaises(ConfigError):
            Config.from_env(base_env(M20AI_SAVE_MODE="sometimes"))

    def test_legacy_switch_maps_to_alert(self):
        cfg = Config.from_env(base_env(M20AI_SAVE_RESULT_IMAGE="true"))
        self.assertEqual(cfg.save_mode, "alert")
        self.assertTrue(cfg.save_result_image)

    def test_explicit_mode_wins_over_legacy(self):
        cfg = Config.from_env(base_env(M20AI_SAVE_MODE="off", M20AI_SAVE_RESULT_IMAGE="true"))
        self.assertEqual(cfg.save_mode, "off")


if __name__ == "__main__":
    unittest.main()
