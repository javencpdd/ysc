import base64
import json
import os
import time
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

from m20_ai_detect.config import Config, Source
from m20_ai_detect.detect import DetectResult
from m20_ai_detect.sampler import Sampler
from m20_ai_detect.store import Store


class FakeDetector:
    """测试替身：按队列返回结果，并记录收到的字节。"""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def detect(self, jpeg, filename):
        self.calls.append((filename, len(jpeg)))
        return self.results.pop(0)

    @staticmethod
    def decode_result_image(payload):
        """与真实 Detector 同样的静态方法（留存路径会调到）。"""
        img = (payload or {}).get("result_image") or ""
        if not isinstance(img, str) or "," not in img:
            return None
        import base64 as _b64

        return _b64.b64decode(img.split(",", 1)[1])


def ok_payload(items):
    return DetectResult(
        ok=True,
        http_status=200,
        payload={
            "capability": "ai-04-yolov8-object-detection",
            "device": "cpu",
            "provider": "CPUExecutionProvider",
            "elapsed_ms": 65.4,
            "params": {"obj_thresh": 0.25},
            "results": {"type": "detection", "items": items},
        },
        error=None,
        wall_ms=250,
        elapsed_ms=65.4,
    )


def fail_result(msg="EXC:timeout"):
    return DetectResult(ok=False, http_status=None, payload=None, error=msg, wall_ms=10000)


def ok_payload_with_image(items):
    """带 result_image（base64 小图）的成功响应，用于留存触发测试。"""
    r = ok_payload(items)
    r.payload["result_image"] = (
        "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8fake-img").decode()
    )
    return r


class TestSampler(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-sampler-")
        self.cfg = Config.from_env(
            {
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": self.tmp,
                "M20AI_FRESH_AGE_SEC": "0",
                "M20AI_RING_MAX_MB": "10",
                "M20AI_RETRY_BASE": "0",
                "M20AI_RETRY_MAX": "0",
                "M20AI_ALERT_LABELS": "person",
                "M20AI_ALERT_SCORE": "0.6",
            }
        )
        self.store = Store(self.cfg)
        self.logs = []
        self.sampler = Sampler(
            self.cfg, self.store, detector=FakeDetector([]), log=self.logs.append, hostname="testhost"
        )

    def _write_frame(self, cam="front", name="20261014_235000.jpg", content=b"\xff\xd8jpeg"):
        d = self.store.spool_for(cam)
        path = os.path.join(d, name)
        with open(path, "wb") as fh:
            fh.write(content)
        # fresh_age_sec=0，但要确保 mtime 不晚于 now
        os.utime(path, (time.time() - 1, time.time() - 1))
        return path

    def _read_records(self):
        path = self.store.today_jsonl()
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_success_moves_frame_and_writes_record(self):
        self.sampler.detector = FakeDetector([ok_payload([{"label": "chair", "score": 0.65}])])
        path = self._write_frame()
        self.assertTrue(self.sampler._process_camera(self.cfg.cameras[0]))

        recs = self._read_records()
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["host"], "testhost")
        self.assertEqual(rec["cam"], "front")
        self.assertEqual(rec["n_items"], 1)
        self.assertEqual(rec["items"][0]["label"], "chair")
        self.assertEqual(rec["elapsed_ms"], 65.4)
        self.assertEqual(rec["e2e_ms"], 250)
        self.assertFalse(rec["result_image_saved"])
        # 帧应被移入 raw/
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(os.path.join(self.store.raw_for("front"), os.path.basename(path))))

    def test_failure_keeps_frame_and_logs_event(self):
        self.sampler.detector = FakeDetector([fail_result()])
        path = self._write_frame()
        self.assertFalse(self.sampler._process_camera(self.cfg.cameras[0]))
        self.assertTrue(os.path.exists(path), "失败时帧必须留在 spool 等待重试")
        recs = self._read_records()
        self.assertEqual(recs[0]["event"], "detect_fail")
        self.assertIn("timeout", recs[0]["error"])

    def test_alert_without_image(self):
        self.sampler.detector = FakeDetector([ok_payload([{"label": "person", "score": 0.9}])])
        self._write_frame()
        self.sampler._process_camera(self.cfg.cameras[0])
        recs = self._read_records()
        self.assertTrue(recs[0].get("alert"))
        self.assertFalse(recs[0]["result_image_saved"])

    def test_low_score_not_alert(self):
        self.sampler.detector = FakeDetector([ok_payload([{"label": "person", "score": 0.3}])])
        self._write_frame()
        self.sampler._process_camera(self.cfg.cameras[0])
        recs = self._read_records()
        self.assertNotIn("alert", recs[0])

    def test_empty_spool_returns_false(self):
        self.assertFalse(self.sampler._process_camera(self.cfg.cameras[0]))

    def test_zero_byte_frame_skipped(self):
        path = self._write_frame(content=b"")
        self.assertFalse(self.sampler._process_camera(self.cfg.cameras[0]))
        self.assertTrue(os.path.exists(path))

    def test_multiple_frames_processed_in_order(self):
        self.sampler.detector = FakeDetector(
            [ok_payload([{"label": "a", "score": 0.9}]), ok_payload([{"label": "b", "score": 0.9}])]
        )
        self._write_frame(name="20261014_235000.jpg")
        self._write_frame(name="20261014_235001.jpg")
        self.assertTrue(self.sampler._process_camera(self.cfg.cameras[0]))
        recs = self._read_records()
        self.assertEqual(len(recs), 2)
        self.assertEqual([r["frame"] for r in recs], ["20261014_235000.jpg", "20261014_235001.jpg"])


class FakeClockDetector:
    """时钟测量替身：health() 按预设返回 (ok, info)，不碰网络。"""

    def __init__(self, ok=True, server_time=None, info_extra=None):
        self._ok = ok
        info = dict(info_extra or {})
        if server_time is not None:
            info["server_time"] = server_time
        self._info = info

    def health(self):
        return self._ok, self._info

    def detect(self, jpeg, filename):
        raise AssertionError("时钟测试不应触发 detect")


class TestClockOffset(unittest.TestCase):
    """ADR-004：软件时钟偏移——配置优先 / 自动测量 / 失败退化。"""

    def _cfg(self, **over):
        env = {
            "M20AI_ENABLE_F": "1",
            "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
            "M20AI_BASE_DIR": self.tmp,
            "M20AI_FRESH_AGE_SEC": "0",
            "M20AI_RING_MAX_MB": "10",
            "M20AI_RETRY_BASE": "0",
            "M20AI_RETRY_MAX": "0",
        }
        env.update(over)
        return Config.from_env(env)

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-clock-")
        self.store = Store(self._cfg())

    def test_configured_offset_wins(self):
        """配置了 M20AI_TS_OFFSET_SEC 时直接生效，不联网测量。"""
        cfg = self._cfg(M20AI_TS_OFFSET_SEC="3600")
        sampler = Sampler(cfg, self.store, detector=FakeClockDetector(ok=False), log=lambda m: None)
        self.assertEqual(sampler.calibrate_clock(), 3600.0)
        self.assertEqual(sampler.ts_offset, 3600.0)

    def test_auto_measure_from_server_date(self):
        """未配置时用 AI 服务 Date 头自动测量（车队钉 2024，实测偏移约 846 天量级）。"""
        future = datetime.now(timezone.utc) + timedelta(seconds=73100565)
        det = FakeClockDetector(server_time=future.isoformat())
        logs = []
        sampler = Sampler(self._cfg(), self.store, detector=det, log=logs.append)
        offset = sampler.calibrate_clock()
        self.assertAlmostEqual(offset, 73100565.0, delta=5)
        self.assertTrue(any("auto-measured" in m for m in logs))

    def test_measure_failure_falls_back_to_zero(self):
        """测量失败退化为 0（本机时间）并明确记日志，不阻断运行。"""
        logs = []
        sampler = Sampler(
            self._cfg(), self.store, detector=FakeClockDetector(ok=False), log=logs.append
        )
        self.assertEqual(sampler.calibrate_clock(), 0.0)
        self.assertEqual(sampler.ts_offset, 0.0)
        self.assertTrue(any("measurement failed" in m for m in logs))

    def test_records_carry_corrected_and_host_time(self):
        """v=2 记录：ts 为偏移修正时间，ts_host 为本机原值，差值恰为偏移量。"""
        cfg = self._cfg(M20AI_TS_OFFSET_SEC="3600")
        sampler = Sampler(
            cfg,
            self.store,
            detector=FakeDetector([ok_payload([{"label": "chair", "score": 0.65}])]),
            log=lambda m: None,
            hostname="clockhost",
        )
        sampler.calibrate_clock()
        path = self._write_frame_in(self.store)
        sampler._process_camera(cfg.cameras[0])
        with open(self.store.today_jsonl(), encoding="utf-8") as fh:
            recs = [json.loads(line) for line in fh if line.strip()]
        rec = recs[0]
        self.assertEqual(rec["v"], 2)
        self.assertEqual(rec["ts_offset_sec"], 3600.0)
        ts = datetime.fromisoformat(rec["ts"])
        ts_host = datetime.fromisoformat(rec["ts_host"])
        self.assertAlmostEqual((ts - ts_host).total_seconds(), 3600.0, delta=1.0)
        self.assertFalse(os.path.exists(path))

    @staticmethod
    def _write_frame_in(store):
        name = "20261014_235000.jpg"
        path = os.path.join(store.spool_for("front"), name)
        with open(path, "wb") as fh:
            fh.write(b"\xff\xd8jpeg")
        os.utime(path, (time.time() - 1, time.time() - 1))
        return path


class TestPruneHook(unittest.TestCase):
    """_maybe_prune_results：每小时一次、keep_days<=0 不动作。"""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-prunehook-")
        env = {
            "M20AI_ENABLE_F": "1",
            "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
            "M20AI_BASE_DIR": self.tmp,
            "M20AI_RESULTS_KEEP_DAYS": "7",
        }
        self.cfg = Config.from_env(env)
        self.store = Store(self.cfg)
        self.sampler = Sampler(self.cfg, self.store, detector=FakeDetector([]), log=lambda m: None)

    def test_zero_keep_days_skips(self):
        cfg = Config.from_env(
            {
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": self.tmp,
                "M20AI_RESULTS_KEEP_DAYS": "0",
            }
        )
        s = Sampler(cfg, self.store, detector=FakeDetector([]), log=lambda m: None)
        s._last_prune = 0.0
        calls = []
        self.store.prune_results = lambda d: calls.append(d) or 0
        s._maybe_prune_results()
        self.assertEqual(calls, [])

    def test_runs_when_due(self):
        self.sampler._last_prune = 0.0
        calls = []
        self.store.prune_results = lambda d: calls.append(d) or 0
        self.sampler._maybe_prune_results()
        self.assertEqual(calls, [7.0])

    def test_skips_within_interval(self):
        self.sampler._last_prune = time.time()
        calls = []
        self.store.prune_results = lambda d: calls.append(d) or 0
        self.sampler._maybe_prune_results()
        self.assertEqual(calls, [])


class TestPruneSavedHook(unittest.TestCase):
    """_maybe_prune_saved：10 分钟一次、上限与天数都为 0 时不动作（ADR-008）。"""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-savedhook-")
        env = {
            "M20AI_ENABLE_F": "1",
            "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
            "M20AI_BASE_DIR": self.tmp,
            "M20AI_SAVED_MAX_MB": "200",
        }
        self.cfg = Config.from_env(env)
        self.store = Store(self.cfg)
        self.sampler = Sampler(self.cfg, self.store, detector=FakeDetector([]), log=lambda m: None)

    def test_both_zero_skips(self):
        cfg = Config.from_env(
            {
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": self.tmp,
                "M20AI_SAVED_MAX_MB": "0",
                "M20AI_SAVED_KEEP_DAYS": "0",
            }
        )
        s = Sampler(cfg, self.store, detector=FakeDetector([]), log=lambda m: None)
        calls = []
        self.store.clean_saved = lambda mb, kd: calls.append((mb, kd)) or (0, 0)
        s._maybe_prune_saved()
        self.assertEqual(calls, [])

    def test_runs_only_keep_days(self):
        """max=0 但 keep_days>0 时也要跑（只用年龄维度）。"""
        cfg = Config.from_env(
            {
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": self.tmp,
                "M20AI_SAVED_MAX_MB": "0",
                "M20AI_SAVED_KEEP_DAYS": "3",
            }
        )
        s = Sampler(cfg, self.store, detector=FakeDetector([]), log=lambda m: None)
        calls = []
        self.store.clean_saved = lambda mb, kd: calls.append((mb, kd)) or (0, 0)
        s._maybe_prune_saved()
        self.assertEqual(calls, [(0, 3.0)])

    def test_runs_when_due(self):
        self.sampler._last_saved_prune = 0.0
        calls = []
        self.store.clean_saved = lambda mb, kd: calls.append((mb, kd)) or (0, 0)
        self.sampler._maybe_prune_saved()
        self.assertEqual(calls, [(200 * 1024 * 1024, 0.0)])

    def test_skips_within_interval(self):
        self.sampler._last_saved_prune = time.time()
        calls = []
        self.store.clean_saved = lambda mb, kd: calls.append((mb, kd)) or (0, 0)
        self.sampler._maybe_prune_saved()
        self.assertEqual(calls, [])


class TestSaveTrigger(unittest.TestCase):
    """ADR-006：SAVE_MODE 四值触发矩阵（off/alert/any/all → saved/ 成对留存）。"""

    def _sampler(self, **env):
        import tempfile

        tmp = tempfile.mkdtemp(prefix="m20ai-savemode-")
        base = {
            "M20AI_ENABLE_F": "1",
            "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
            "M20AI_BASE_DIR": tmp,
            "M20AI_FRESH_AGE_SEC": "0",
            "M20AI_RING_MAX_MB": "10",
            "M20AI_RETRY_BASE": "0",
            "M20AI_RETRY_MAX": "0",
            "M20AI_ALERT_LABELS": "person",
            "M20AI_ALERT_SCORE": "0.6",
        }
        base.update(env)
        cfg = Config.from_env(base)
        store = Store(cfg)
        sampler = Sampler(cfg, store, detector=FakeDetector([]), log=lambda m: None, hostname="h")
        return cfg, store, sampler

    def _run_one(self, sampler, store, items):
        sampler.detector = FakeDetector([ok_payload_with_image(items)])
        path = os.path.join(store.spool_for("front"), "20261015_020000.jpg")
        with open(path, "wb") as fh:
            fh.write(b"\xff\xd8jpeg")
        os.utime(path, (time.time() - 1, time.time() - 1))
        sampler._process_camera(sampler.cfg.cameras[0])
        with open(store.today_jsonl(), encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()][0]

    def test_off_saves_nothing(self):
        cfg, store, s = self._sampler()
        rec = self._run_one(s, store, [{"label": "person", "score": 0.9}])
        self.assertTrue(rec.get("alert"))
        self.assertNotIn("saved_image", rec)
        self.assertNotIn("resp_path", rec)
        self.assertEqual(os.listdir(store.saved_dir), [])

    def test_alert_mode_hit_saves_pair(self):
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="alert")
        rec = self._run_one(s, store, [{"label": "person", "score": 0.9}])
        self.assertTrue(rec.get("alert"))
        self.assertTrue(rec["result_image_saved"])
        self.assertTrue(rec["saved_image"].startswith("saved/front/"))
        self.assertTrue(os.path.exists(os.path.join(store.cfg.base_dir, rec["saved_image"])))
        self.assertTrue(os.path.exists(os.path.join(store.cfg.base_dir, rec["resp_path"])))

    def test_saved_path_matches_response_viewer_convention(self):
        """留存路径必须与 webconsole /api/response 的查找约定一致：
        saved/<cam>/<帧名去扩展名>.json——否则采样器留存的响应永远读不回。"""
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="all")
        rec = self._run_one(s, store, [])
        stem = os.path.splitext(rec["frame"])[0]
        self.assertEqual(rec["resp_path"], "saved/front/%s.json" % stem)
        self.assertEqual(rec["saved_image"], "saved/front/%s.jpg" % stem)
        # 模拟 _response_detail 的查找路径
        self.assertTrue(
            os.path.exists(os.path.join(cfg.base_dir, "saved", "front", stem + ".json"))
        )

    def test_saved_json_carries_real_time(self):
        """ADR-008：留存 JSON 带 _saved_at（真实时钟 = 与 JSONL 的 ts 一致）。"""
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="any", M20AI_TS_OFFSET_SEC="3600")
        s.calibrate_clock()
        rec = self._run_one(s, store, [{"label": "chair", "score": 0.9}])
        with open(os.path.join(cfg.base_dir, rec["resp_path"]), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["_saved_at"], rec["ts"])
        self.assertNotIn("_alert", doc)  # chair 不在告警标签里

    def test_saved_json_marks_alert(self):
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="any")
        rec = self._run_one(s, store, [{"label": "person", "score": 0.9}])
        with open(os.path.join(cfg.base_dir, rec["resp_path"]), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertTrue(doc["_alert"])

    def test_alert_mode_miss_saves_nothing(self):
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="alert")
        rec = self._run_one(s, store, [{"label": "chair", "score": 0.9}])
        self.assertNotIn("alert", rec)
        self.assertNotIn("saved_image", rec)
        self.assertEqual(os.listdir(store.saved_dir), [])

    def test_any_mode_zero_items_no_save(self):
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="any")
        rec = self._run_one(s, store, [])
        self.assertEqual(rec["n_items"], 0)
        self.assertNotIn("saved_image", rec)
        self.assertEqual(os.listdir(store.saved_dir), [])

    def test_any_mode_hit_saves_even_without_alert(self):
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="any")
        rec = self._run_one(s, store, [{"label": "chair", "score": 0.9}])
        self.assertNotIn("alert", rec)  # chair 不在告警标签里
        self.assertTrue(rec["saved_image"].endswith(".jpg"))
        self.assertTrue(rec["resp_path"].endswith(".json"))

    def test_all_mode_saves_even_when_empty(self):
        cfg, store, s = self._sampler(M20AI_SAVE_MODE="all")
        rec = self._run_one(s, store, [])
        self.assertEqual(rec["n_items"], 0)
        self.assertTrue(rec["result_image_saved"])
        self.assertIn("saved_image", rec)

    def test_legacy_switch_triggers_alert_mode(self):
        cfg, store, s = self._sampler(M20AI_SAVE_RESULT_IMAGE="true")
        self.assertEqual(cfg.save_mode, "alert")
        rec = self._run_one(s, store, [{"label": "person", "score": 0.9}])
        self.assertIn("saved_image", rec)


class TestPerCameraBackoff(unittest.TestCase):
    """逐路退避（ADR-016 §5）：一路坏源不能拖慢其它路。

    _on_failure 内部会 time.sleep(backoff)，这里统一 patch 掉 —— 否则指数退避
    会把测试拖到几十秒。
    """

    def setUp(self) -> None:
        self._sleep_patch = mock.patch("m20_ai_detect.sampler.time.sleep")
        self.slept = []
        self._sleep_patch.start().side_effect = lambda sec: self.slept.append(sec)

    def tearDown(self) -> None:
        self._sleep_patch.stop()

    def _cfg(self, names=("front", "back"), **over):
        cams = [Source(n, "rtsp://h/" + n) for n in names]
        base = dict(cameras=cams, retry_base=1.0, retry_max=30.0)
        base.update(over)
        return Config(**base)  # type: ignore[arg-type]

    def _sampler(self, cfg: Config) -> Sampler:
        return Sampler(cfg, Store(cfg), detector=FakeDetector([]), log=lambda _m: None)

    @staticmethod
    def _fail() -> DetectResult:
        return DetectResult(ok=False, error="boom", wall_ms=1.0, http_status=500, payload=None)

    def test_backoff_is_per_camera(self):
        cfg = self._cfg()
        s = self._sampler(cfg)
        for _ in range(3):
            s._on_failure(cfg.cameras[0], "front_1.jpg", self._fail())
        s._on_failure(cfg.cameras[1], "back_1.jpg", self._fail())

        # front 连退三次：1→2→4→8；back 只退一次：1→2
        self.assertEqual(s._backoff_of(cfg.cameras[0]), 8.0)
        self.assertEqual(s._backoff_of(cfg.cameras[1]), 2.0)
        self.assertEqual(self.slept, [2.0, 4.0, 8.0, 2.0])

    def test_success_resets_only_that_camera(self):
        cfg = self._cfg()
        s = self._sampler(cfg)
        for _ in range(2):
            s._on_failure(cfg.cameras[0], "f.jpg", self._fail())
            s._on_failure(cfg.cameras[1], "b.jpg", self._fail())
        s._set_backoff(cfg.cameras[0], cfg.retry_base)
        self.assertEqual(s._backoff_of(cfg.cameras[0]), 1.0)
        self.assertEqual(s._backoff_of(cfg.cameras[1]), 4.0)

    def test_backoff_capped_by_retry_max(self):
        cfg = self._cfg(names=("c",), retry_max=5.0)
        s = self._sampler(cfg)
        for _ in range(10):
            s._on_failure(cfg.cameras[0], "c.jpg", self._fail())
        self.assertEqual(s._backoff_of(cfg.cameras[0]), 5.0)

    def test_legacy_backoff_field_mirrors_last_value(self):
        """旧字段仍被镜像刷新，防止老观察者读不到值（向后兼容）。"""
        cfg = self._cfg(names=("c",))
        s = self._sampler(cfg)
        s._on_failure(cfg.cameras[0], "c.jpg", self._fail())
        self.assertEqual(s._backoff, 2.0)

    def test_unknown_camera_uses_retry_base(self):
        cfg = self._cfg(names=("c",))
        s = self._sampler(cfg)
        self.assertEqual(s._backoff_of(Source("ghost", "rtsp://h/x")), 1.0)


if __name__ == "__main__":
    unittest.main()
