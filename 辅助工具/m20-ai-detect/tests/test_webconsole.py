"""webconsole 测试：纯逻辑模块 + HTTP 层端到端（本地回环，外部依赖全部打桩）。"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from m20_ai_detect.config import Config  # noqa: E402
from m20_ai_detect.detect import DetectResult  # noqa: E402
from webconsole import envfile, logfilter, server, sysactions  # noqa: E402

ENV_FIXTURE = """# 测试 env
M20AI_AI_BASE=http://127.0.0.1:1
M20AI_CAP_ID=ai-04-yolov8-object-detection
M20AI_PARAMS_JSON={"obj_thresh":0.3,"nms_thresh":0.45}
M20AI_ENABLE_F=1
M20AI_SRC_F=rtsp://127.0.0.1:8554/video1
M20AI_FPS=1
M20AI_RING_MAX_MB=200
M20AI_RESULTS_KEEP_DAYS=0
M20AI_BASE_DIR={base}
"""


def write_env_file(tmp: str) -> str:
    path = os.path.join(tmp, "m20-ai-detect.env")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(ENV_FIXTURE.replace("{base}", tmp))
    return path


def fake_detector_with(payload):
    """打桩 Detector 类：detect 返回预设响应，decode_result_image 用真实实现。"""
    import m20_ai_detect.detect as detect_mod

    fake = mock.Mock()
    fake.detect.return_value = DetectResult(True, 200, payload, None, 250, 65.0)
    fake.decode_result_image = detect_mod.Detector.decode_result_image
    return fake


class TestEnvfile(unittest.TestCase):
    def test_read_parses_and_unquotes(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_env_file(td)
            env = envfile.read_env(p)
            self.assertEqual(env["M20AI_FPS"], "1")
            self.assertEqual(env["M20AI_PARAMS_JSON"], '{"obj_thresh":0.3,"nms_thresh":0.45}')

    def test_read_missing_file_returns_empty(self):
        self.assertEqual(envfile.read_env("/nonexistent/x.env"), {})

    def test_set_updates_in_place_and_preserves_comments(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_env_file(td)
            envfile.set_env_keys(p, {"M20AI_FPS": "2", "M20AI_NEW_KEY": "v"})
            text = open(p, encoding="utf-8").read()
            self.assertIn("# 测试 env", text)
            self.assertIn("M20AI_FPS=2", text)
            self.assertIn("M20AI_NEW_KEY=v", text)
            self.assertNotIn("M20AI_FPS=1\n", text)

    def test_shell_quote_rules(self):
        self.assertEqual(envfile.shell_quote(""), "")
        self.assertEqual(envfile.shell_quote("rtsp://a.b/c"), "rtsp://a.b/c")
        self.assertEqual(envfile.shell_quote('{"a":1}'), "'{\"a\":1}'")
        with self.assertRaises(ValueError):
            envfile.shell_quote("it's")

    def test_validate_rejects_bad_fps(self):
        ok, errors = envfile.validate_env(ENV_FIXTURE and {}, {"M20AI_FPS": "abc"})
        self.assertFalse(ok)
        self.assertTrue(errors)

    def test_validate_accepts_good_updates(self):
        with tempfile.TemporaryDirectory() as td:
            current = envfile.read_env(write_env_file(td))
            ok, errors = envfile.validate_env(current, {"M20AI_FPS": "2", "M20AI_RING_MAX_MB": "500"})
            self.assertTrue(ok, errors)


class TestLogfilter(unittest.TestCase):
    LINE = "2026-06-21T00:05:49+0800 gos m20-ai-detect[15586]: ALERT cam=front frame=x n=2"

    def test_classify(self):
        self.assertEqual(logfilter.classify(self.LINE), "alert")
        self.assertEqual(logfilter.classify("... detect FAIL err=timeout"), "fail")
        self.assertEqual(logfilter.classify("... start cap=ai-04"), "boot")
        self.assertEqual(logfilter.classify("... nothing special"), "ok")

    def test_split_ts(self):
        self.assertEqual(logfilter.split_ts(self.LINE), "2026-06-21T00:05:49+0800")
        self.assertIsNone(logfilter.split_ts("no timestamp here"))

    def test_filter(self):
        lines = [self.LINE, "plain ok line", "detect FAIL boom"]
        self.assertEqual(len(logfilter.filter_lines(lines, "alert")), 1)
        self.assertEqual(len(logfilter.filter_lines(lines, "fail")), 1)
        self.assertEqual(len(logfilter.filter_lines(lines, "all", "FAIL")), 1)
        self.assertEqual(len(logfilter.filter_lines(lines, "all", "nomatch")), 0)


class TestSysactions(unittest.TestCase):
    def test_service_status_parses_runner(self):
        runner = lambda cmd, t=15.0: (0, "active\n", "")  # noqa: E731
        with mock.patch.object(sysactions.shutil, "which", return_value="/usr/bin/systemctl"):
            self.assertEqual(sysactions.service_status(runner), "active")

    def test_service_status_unknown_without_systemctl(self):
        runner = lambda cmd, t=15.0: (0, "active\n", "")  # noqa: E731
        with mock.patch.object(sysactions.shutil, "which", return_value=None):
            self.assertEqual(sysactions.service_status(runner), "unknown")

    def test_service_action_rejects_unknown_verb(self):
        ok, msg = sysactions.service_action("reload", "/bin/true")
        self.assertFalse(ok)
        self.assertIn("非法动作", msg)

    def test_service_action_uses_sudo_helper(self):
        seen = []

        def runner(cmd, t=15.0):
            seen.append(cmd)
            return (0, "ok", "")

        ok, _ = sysactions.service_action("restart", "/usr/local/sbin/m20-ai-console-helper", runner)
        self.assertTrue(ok)
        self.assertEqual(seen[0][:3], ["sudo", "-n", "/usr/local/sbin/m20-ai-console-helper"])
        self.assertEqual(seen[0][3], "svc-restart")

    def test_journal_lines_clamps_n(self):
        seen = []

        def runner(cmd, t=15.0):
            seen.append(cmd)
            return (0, "l1\nl2\n", "")

        sysactions.journal_lines(99999, runner)
        self.assertEqual(seen[0][seen[0].index("-n") + 1], "2000")

    def test_call_helper_writes_req_and_rejects_bad_sub(self):
        with tempfile.TemporaryDirectory() as td:
            ok, msg = sysactions.call_helper("svc; rm", {}, td, "/bin/true")
            self.assertFalse(ok)
            self.assertIn("非法", msg)
            seen = []

            def runner(cmd, t=15.0):
                seen.append(cmd)
                return (0, "done", "")

            ok, _ = sysactions.call_helper("journal-vacuum", {"size": "200M"}, td, "/bin/true", runner)
            self.assertTrue(ok)
            req = os.path.join(td, "tmp", "console-journal-vacuum.req")
            self.assertTrue(os.path.exists(req))
            self.assertIn("size=200M", open(req, encoding="utf-8").read())

    def test_value_prechecks(self):
        self.assertIsNone(sysactions.check_vacuum({"size": "200M"}))
        self.assertIsNone(sysactions.check_vacuum({"time": "7d"}))
        self.assertTrue(sysactions.check_vacuum({"size": "200M", "time": "7d"}))
        self.assertTrue(sysactions.check_vacuum({"size": "abc"}))
        self.assertTrue(sysactions.check_vacuum({}))
        self.assertTrue(sysactions.check_journald_limits({}))
        self.assertTrue(sysactions.check_journald_limits({"SystemMaxUse": "xx"}))
        self.assertTrue(sysactions.check_logrotate({"rotate": "0"}))
        self.assertTrue(sysactions.check_logrotate({"rotate": "999"}))


class TestClearSpoolWithRestart(unittest.TestCase):
    """清空积压帧（clear_spool_with_restart）：停采样器 → 删 spool/ → 起采样器的顺序与失败路径。"""

    def _mk_env(self, td):
        env_file = write_env_file(td)
        cfg = server.ConsoleConfig(
            {
                "M20AIC_BASE_DIR": td,
                "M20AIC_ENV_FILE": env_file,
                "M20AIC_HELPER": "/usr/local/sbin/m20-ai-console-helper",
            }
        )
        from m20_ai_detect.store import Store

        store = Store(cfg.sampler_cfg)
        for i in range(3):
            with open(os.path.join(store.spool_for("front"), "f%d.jpg" % i), "wb") as fh:
                fh.write(b"\0" * 512)
        with open(os.path.join(store.raw_for("front"), "keep.jpg"), "wb") as fh:
            fh.write(b"\0" * 64)
        return cfg, store

    @staticmethod
    def _spool_jpgs(store):
        return [f for f in os.listdir(store.spool_for("front")) if f.endswith(".jpg")]

    def test_flow_stop_clear_start_in_order(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []

            def runner(cmd, t=15.0):
                seen.append(cmd)
                return (0, "done", "")

            ok, msg = server.clear_spool_with_restart(cfg, runner)
            self.assertTrue(ok, msg)
            sudo_cmds = [c for c in seen if c and c[0] == "sudo"]
            self.assertEqual([c[3] for c in sudo_cmds], ["svc-stop", "svc-start"])
            self.assertEqual(self._spool_jpgs(store), [])
            self.assertTrue(
                os.path.exists(os.path.join(store.raw_dir, "front", "keep.jpg"))
            )
            self.assertIn("已清空积压 3 帧", msg)

    def test_stop_failure_aborts_before_clearing(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []

            def runner(cmd, t=15.0):
                seen.append(cmd)
                if cmd[0] == "sudo":
                    return (1, "", "sudo: a password is required")
                return (0, "done", "")

            ok, msg = server.clear_spool_with_restart(cfg, runner)
            self.assertFalse(ok)
            self.assertIn("停采样器失败", msg)
            # 未删帧、未尝试重新启动
            self.assertEqual(len(self._spool_jpgs(store)), 3)
            self.assertEqual(len([c for c in seen if c[0] == "sudo"]), 1)

    def test_clear_oserror_attempts_restart(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []

            def runner(cmd, t=15.0):
                seen.append(cmd)
                return (0, "done", "")

            import m20_ai_detect.store as store_mod

            with mock.patch.object(
                store_mod.Store, "clear_spool", side_effect=OSError("boom")
            ):
                ok, msg = server.clear_spool_with_restart(cfg, runner)
            self.assertFalse(ok)
            self.assertIn("采样器已尝试恢复启动", msg)
            # 失败也要把服务尝试拉回启动态，别停在停止态
            self.assertEqual(
                [c[3] for c in seen if c[0] == "sudo"], ["svc-stop", "svc-start"]
            )


class TestHTTP(unittest.TestCase):
    """起真实回环服务打全 API；外部副作用（systemctl/journalctl/helper/网络）全打桩。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="m20ai-http-")
        cls.env_file = write_env_file(cls.tmp)
        cls.cfg = server.ConsoleConfig(
            {
                "M20AIC_BIND": "127.0.0.1",
                "M20AIC_PORT": "0",
                "M20AIC_TOKEN": "",
                "M20AIC_BASE_DIR": cls.tmp,
                "M20AIC_ENV_FILE": cls.env_file,
                "M20AIC_HELPER": "/bin/true",
            }
        )
        cls.srv = server.Console(cls.cfg)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.caps = mock.patch.object(server, "_capabilities", return_value=([{"id": "ai-04", "title": "t", "ready": True}], ""))
        self.caps.start()
        self.addCleanup(self.caps.stop)
        self.offset = mock.patch.object(server.Console, "_measure_offset", return_value=1234.5)
        self.offset.start()
        self.addCleanup(self.offset.stop)
        self.jl = mock.patch.object(
            server.sysactions,
            "journal_lines",
            return_value=[
                "2026-06-21T00:05:49+0800 gos m20-ai-detect[1]: start cap=ai-04",
                "2026-06-21T00:06:12+0800 gos m20-ai-detect[1]: ALERT cam=front n=2",
                "2026-06-21T00:07:00+0800 gos m20-ai-detect[1]: detect FAIL err=timeout",
            ],
        )
        self.jl.start()
        self.addCleanup(self.jl.stop)
        self.act = mock.patch.object(server.sysactions, "service_action", return_value=(True, "done"))
        self.act.start()
        self.addCleanup(self.act.stop)
        self.helper = mock.patch.object(server.sysactions, "call_helper", return_value=(True, "vacuumed"))
        self.helper.start()
        self.addCleanup(self.helper.stop)

    def _get(self, path):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def _post(self, path, obj):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(obj).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_index_served_without_token(self):
        with urllib.request.urlopen("http://127.0.0.1:%d/" % self.port, timeout=5) as r:
            body = r.read().decode("utf-8")
        self.assertIn("m20-ai-console", body)

    def test_status_shape(self):
        st, d = self._get("/api/status")
        self.assertEqual(st, 200)
        self.assertTrue(d["ok"])
        self.assertIn("frames_today", d)
        self.assertIn("clock_offset_sec", d)

    def test_config_roundtrip(self):
        st, d = self._get("/api/config")
        self.assertEqual(st, 200)
        self.assertEqual(d["effective"]["cap_id"], "ai-04-yolov8-object-detection")
        self.assertEqual(d["effective"]["ring_max_mb"], 200.0)
        self.assertEqual(len(d["capabilities"]), 1)

    def test_config_rejects_bad_update(self):
        st, d = self._post("/api/config", {"updates": {"M20AI_FPS": "abc"}})
        self.assertEqual(st, 400)
        self.assertIn("校验失败", d["error"])

    def test_config_rejects_non_m20ai_key(self):
        st, d = self._post("/api/config", {"updates": {"PATH": "/tmp"}})
        self.assertEqual(st, 400)

    def test_config_write_and_restart(self):
        st, d = self._post("/api/config", {"updates": {"M20AI_FPS": "2"}})
        self.assertEqual(st, 200)
        env = envfile.read_env(self.env_file)
        self.assertEqual(env["M20AI_FPS"], "2")
        self.assertIn("已重启", d["detail"])

    def test_logs_filtered(self):
        st, d = self._get("/api/logs?level=alert")
        self.assertEqual(st, 200)
        self.assertEqual(len(d["lines"]), 1)
        self.assertEqual(d["lines"][0]["level"], "alert")

    def test_logs_query(self):
        st, d = self._get("/api/logs?q=timeout")
        self.assertEqual(len(d["lines"]), 1)

    def test_retention_env_level(self):
        st, d = self._post("/api/retention", {"ring_max_mb": "500", "results_keep_days": "30"})
        self.assertEqual(st, 200)
        env = envfile.read_env(self.env_file)
        self.assertEqual(env["M20AI_RING_MAX_MB"], "500")
        self.assertEqual(env["M20AI_RESULTS_KEEP_DAYS"], "30")

    def test_retention_rejects_bad_vacuum(self):
        st, d = self._post("/api/retention", {"journal_vacuum": {"size": "abc"}})
        self.assertEqual(st, 400)

    def test_retention_vacuum_ok(self):
        st, d = self._post("/api/retention", {"journal_vacuum": {"time": "7d"}})
        self.assertEqual(st, 200)

    def test_retention_empty_body_rejected(self):
        st, d = self._post("/api/retention", {})
        self.assertEqual(st, 400)

    def test_retention_spool_clear(self):
        """spool_clear 接线：POST 后 spool/ 内 *.jpg 被清空，notes 带帧数；raw/ 不动。"""
        from m20_ai_detect.store import Store

        store = Store(self.cfg.sampler_cfg)
        for i in range(2):
            with open(os.path.join(store.spool_for("front"), "sc%d.jpg" % i), "wb") as fh:
                fh.write(b"\0" * 100)
        st, d = self._post("/api/retention", {"spool_clear": True})
        self.assertEqual(st, 200)
        self.assertTrue(any("已清空积压 2 帧" in n for n in d["notes"]), d)
        self.assertEqual(
            [f for f in os.listdir(store.spool_for("front")) if f.endswith(".jpg")], []
        )


class TestHTTPToken(unittest.TestCase):
    def test_token_required_when_set(self):
        tmp = tempfile.mkdtemp(prefix="m20ai-token-")
        env_file = write_env_file(tmp)
        cfg = server.ConsoleConfig(
            {
                "M20AIC_BIND": "127.0.0.1",
                "M20AIC_PORT": "0",
                "M20AIC_TOKEN": "s3cret",
                "M20AIC_BASE_DIR": tmp,
                "M20AIC_ENV_FILE": env_file,
            }
        )
        srv = server.Console(cfg)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with mock.patch.object(server.Console, "_measure_offset", return_value=None):
                req = urllib.request.Request("http://127.0.0.1:%d/api/status" % port)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=5)
                self.assertEqual(ctx.exception.code, 401)
                req2 = urllib.request.Request(
                    "http://127.0.0.1:%d/api/status" % port,
                    headers={"X-Console-Token": "s3cret"},
                )
                with urllib.request.urlopen(req2, timeout=5) as r:
                    self.assertEqual(r.status, 200)
        finally:
            srv.shutdown()
            srv.server_close()


class TestRecentAndResponse(unittest.TestCase):
    """ADR-006：/api/recent（真实记录）与 /api/response（留存直读 / redetect 重测）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="m20ai-recent-")
        cls.env_file = write_env_file(cls.tmp)
        cls.cfg = server.ConsoleConfig(
            {
                "M20AIC_BIND": "127.0.0.1",
                "M20AIC_PORT": "0",
                "M20AIC_TOKEN": "",
                "M20AIC_BASE_DIR": cls.tmp,
                "M20AIC_ENV_FILE": cls.env_file,
                "M20AIC_HELPER": "/bin/true",
            }
        )
        cls.srv = server.Console(cls.cfg)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _get(self, path):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=5) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _write_jsonl(self, records):
        from datetime import datetime

        path = os.path.join(
            self.tmp, "results", datetime.now().strftime("%Y%m%d") + ".jsonl"
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def test_recent_returns_parsed_records_newest_first(self):
        self._write_jsonl(
            [
                {
                    "v": 2, "ts": "2026-10-15T02:00:00.000", "cam": "front",
                    "frame": "a.jpg", "n_items": 1,
                    "items": [{"label": "person", "score": 0.8}],
                    "alert": True, "e2e_ms": 250,
                },
                {
                    "v": 2, "ts": "2026-10-15T02:00:01.000", "cam": "front",
                    "frame": "b.jpg", "n_items": 0, "items": [],
                },
            ]
        )
        status, d = self._get("/api/recent?n=5")
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(len(d["records"]), 2)
        self.assertEqual(d["records"][0]["frame"], "b.jpg")  # 最新在前
        self.assertTrue(d["records"][1]["alert"])
        self.assertEqual(d["records"][1]["items"][0]["label"], "person")
        self.assertEqual(d["save_mode"], "off")

    def test_recent_empty_when_no_jsonl(self):
        status, d = self._get("/api/recent?n=5")
        self.assertEqual(status, 200)
        self.assertEqual(d["records"], [])

    def test_response_saved_direct_read(self):
        d = os.path.join(self.tmp, "saved", "front")
        os.makedirs(d, exist_ok=True)
        doc = {
            "capability": "ai-04",
            "results": {"items": [{"label": "person", "score": 0.9}]},
            "_result_image": "saved/front/x.jpg",
        }
        with open(os.path.join(d, "x.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        with open(os.path.join(self.tmp, "saved", "front", "x.jpg"), "wb") as fh:
            fh.write(b"\xff\xd8jpg")
        status, r = self._get("/api/response?frame=x.jpg&cam=front")
        self.assertEqual(status, 200)
        self.assertEqual(r["source"], "saved")
        self.assertTrue(r["result_image"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(r["raw"]["results"]["items"][0]["label"], "person")

    def test_response_missing_without_redetect_is_404(self):
        status, r = self._get("/api/response?frame=nope.jpg&cam=front")
        self.assertEqual(status, 404)
        self.assertFalse(r["ok"])

    def test_response_redetect_uses_raw_frame(self):
        raw = os.path.join(self.tmp, "raw", "front")
        os.makedirs(raw, exist_ok=True)
        with open(os.path.join(raw, "y.jpg"), "wb") as fh:
            fh.write(b"\xff\xd8jpg")
        payload = {
            "capability": "ai-04",
            "results": {"items": [{"label": "chair", "score": 0.5}]},
            "result_image": "data:image/jpeg;base64,"
            + base64.b64encode(b"\xff\xd8img").decode(),
        }
        fake = fake_detector_with(payload)
        with mock.patch("m20_ai_detect.detect.Detector", return_value=fake):
            status, r = self._get("/api/response?frame=y.jpg&cam=front&redetect=1")
        self.assertEqual(status, 200)
        self.assertEqual(r["source"], "redetect")
        self.assertEqual(r["n_items"], 1)
        self.assertNotIn("result_image", r["raw"])  # 大图字段已剥离
        self.assertIn("_result_image_bytes", r["raw"])
        self.assertTrue(r["result_image"].startswith("data:image/jpeg;base64,"))

    def test_response_rejects_path_traversal(self):
        status, r = self._get("/api/response?frame=..%2F..%2Fetc%2Fpasswd&cam=front")
        self.assertEqual(status, 400)
        self.assertFalse(r["ok"])


class TestDetectSingleFrameSave(unittest.TestCase):
    """单帧检测：raw_response 恒返 + save=1 成对留存（ADR-006）。"""

    def _cfg(self, td):
        return Config.from_env(
            {
                "M20AI_AI_BASE": "http://127.0.0.1:1",
                "M20AI_CAP_ID": "ai-04-yolov8-object-detection",
                "M20AI_PARAMS_JSON": '{"obj_thresh":0.3}',
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": td,
            }
        )

    def test_save_writes_pair_and_returns_raw(self):
        with tempfile.TemporaryDirectory() as td:
            payload = {
                "capability": "ai-04",
                "device": "cpu",
                "elapsed_ms": 65.0,
                "results": {"items": [{"label": "person", "score": 0.77, "box": [1, 2, 3, 4]}]},
                "result_image": "data:image/jpeg;base64,"
                + base64.b64encode(b"\xff\xd8img").decode(),
            }
            fake = fake_detector_with(payload)
            with mock.patch("m20_ai_detect.detect.Detector", return_value=fake):
                out = server.detect_single_frame(self._cfg(td), b"\xff\xd8jpg", save=True)
            self.assertTrue(out["ok"])
            self.assertEqual(out["n_items"], 1)
            self.assertIn("raw_response", out)
            self.assertNotIn("result_image", out["raw_response"])
            self.assertTrue(out["saved_image"].startswith("saved/console/console_"))
            self.assertTrue(out["resp_path"].startswith("saved/console/console_"))
            self.assertTrue(os.path.exists(os.path.join(td, out["saved_image"])))
            self.assertTrue(os.path.exists(os.path.join(td, out["resp_path"])))

    def test_no_save_leaves_no_files(self):
        with tempfile.TemporaryDirectory() as td:
            payload = {"capability": "ai-04", "results": {"items": []}}
            fake = fake_detector_with(payload)
            with mock.patch("m20_ai_detect.detect.Detector", return_value=fake):
                out = server.detect_single_frame(self._cfg(td), b"\xff\xd8jpg", save=False)
            self.assertTrue(out["ok"])
            self.assertNotIn("saved_image", out)
            self.assertFalse(os.path.exists(os.path.join(td, "saved", "console")))


if __name__ == "__main__":
    unittest.main()
