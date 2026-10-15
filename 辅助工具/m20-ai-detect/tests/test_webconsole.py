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
import urllib.error
import urllib.parse
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

    def test_service_is_active_true_variants(self):
        """active/reloading/activating 都视为"在运行"（可安全停）。"""
        for val in ("active", "reloading", "activating"):
            runner = lambda cmd, t=15.0, v=val: (0, v + "\n", "")  # noqa: E731
            self.assertIs(sysactions.service_is_active(runner), True, val)

    def test_service_is_active_false_variants(self):
        for val in ("inactive", "failed", "deactivating"):
            runner = lambda cmd, t=15.0, v=val: (3, v + "\n", "")  # noqa: E731
            self.assertIs(sysactions.service_is_active(runner), False, val)

    def test_service_is_active_none_when_uncheckable(self):
        """无 systemctl（rc=127）或输出异常 → None（调用方走保守路径）。"""
        missing = lambda cmd, t=15.0: (127, "", "systemctl: not found")  # noqa: E731
        self.assertIsNone(sysactions.service_is_active(missing))
        weird = lambda cmd, t=15.0: (0, "something-else\n", "")  # noqa: E731
        self.assertIsNone(sysactions.service_is_active(weird))

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


class TestPurgeWithRestart(unittest.TestCase):
    """数据清空（_purge_with_restart，ADR-011）：停采集（仅运行中）→ 清所选 → 恢复采集原状态。

    覆盖三类采集状态与失败路径：
      * 原本运行：stop → 清 → start（恢复）；
      * 原本未运行：不碰服务（ADR-010 采集开关归用户，清数据不拉起采集）；
      * 状态未知：不碰服务直接清。
    """

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
        with open(os.path.join(store.saved_for("front"), "pair.jpg"), "wb") as fh:
            fh.write(b"\0" * 128)
        with open(
            os.path.join(store.saved_for("front"), "pair.json"), "w", encoding="utf-8"
        ) as fh:
            fh.write("{}")
        with open(
            os.path.join(store.results_dir, "20240621.jsonl"), "w", encoding="utf-8"
        ) as fh:
            fh.write("{}\n")
        return cfg, store

    @staticmethod
    def _spool_jpgs(store):
        return [f for f in os.listdir(store.spool_for("front")) if f.endswith(".jpg")]

    @staticmethod
    def _mk_runner(seen, active, sudo_rc=0):
        """假 runner：systemctl is-active 按 active 应答；sudo 动作按 sudo_rc。

        active=True → "active"；False → "inactive"；None → 模拟无 systemctl（127）。
        """

        def runner(cmd, t=15.0):
            seen.append(cmd)
            if cmd[0] == "systemctl":
                if active is True:
                    return (0, "active\n", "")
                if active is False:
                    return (3, "inactive\n", "")
                return (127, "", "systemctl: not found")
            if cmd[0] == "sudo":
                if sudo_rc == 0:
                    return (0, "done", "")
                return (1, "", "boom")
            return (0, "done", "")

        return runner

    def test_active_flow_stop_clear_start(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            ok, msg = server._purge_with_restart(cfg, ["spool"], self._mk_runner(seen, True))
            self.assertTrue(ok, msg)
            self.assertEqual(
                [c[3] for c in seen if c[0] == "sudo"], ["svc-stop", "svc-start"]
            )
            self.assertEqual(self._spool_jpgs(store), [])
            # 未选的 raw/ 不动
            self.assertTrue(os.path.exists(os.path.join(store.raw_dir, "front", "keep.jpg")))
            self.assertIn("已清空：spool/ 积压帧 3 个文件", msg)
            self.assertIn("采集已重启恢复", msg)

    def test_inactive_never_starts_nor_stops(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            ok, msg = server._purge_with_restart(cfg, ["spool"], self._mk_runner(seen, False))
            self.assertTrue(ok, msg)
            self.assertEqual([c for c in seen if c[0] == "sudo"], [])
            self.assertEqual(self._spool_jpgs(store), [])
            self.assertIn("采集未运行，未做启停", msg)

    def test_unknown_state_no_service_touch(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            ok, msg = server._purge_with_restart(cfg, ["spool"], self._mk_runner(seen, None))
            self.assertTrue(ok, msg)
            self.assertEqual([c for c in seen if c[0] == "sudo"], [])
            self.assertIn("未能确认采集状态", msg)

    def test_multi_kinds_saved_results_raw(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            ok, msg = server._purge_with_restart(
                cfg, ["saved", "results", "raw"], self._mk_runner(seen, True)
            )
            self.assertTrue(ok, msg)
            self.assertEqual(os.listdir(store.saved_for("front")), [])
            self.assertEqual(
                [f for f in os.listdir(store.results_dir) if f.endswith(".jsonl")], []
            )
            self.assertEqual(os.listdir(store.raw_for("front")), [])
            # 未选的 spool/ 保留
            self.assertEqual(len(self._spool_jpgs(store)), 3)
            self.assertIn("saved/ 留存图片 2 个文件", msg)
            self.assertIn("results/ 检测记录 1 个文件", msg)

    def test_stop_failure_aborts_before_clearing(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            ok, msg = server._purge_with_restart(
                cfg, ["spool"], self._mk_runner(seen, True, sudo_rc=1)
            )
            self.assertFalse(ok)
            self.assertIn("停采集失败", msg)
            # 未删帧、只有一次 stop 尝试（没有 start）
            self.assertEqual(len(self._spool_jpgs(store)), 3)
            self.assertEqual([c[3] for c in seen if c[0] == "sudo"], ["svc-stop"])

    def test_purge_oserror_restores_when_active(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            import m20_ai_detect.store as store_mod

            with mock.patch.object(store_mod.Store, "purge", side_effect=OSError("boom")):
                ok, msg = server._purge_with_restart(cfg, ["spool"], self._mk_runner(seen, True))
            self.assertFalse(ok)
            self.assertIn("已尝试恢复启动", msg)
            # 失败也要把采集尝试拉回启动态，别停在停止态
            self.assertEqual(
                [c[3] for c in seen if c[0] == "sudo"], ["svc-stop", "svc-start"]
            )

    def test_purge_oserror_inactive_no_restart(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, store = self._mk_env(td)
            seen = []
            import m20_ai_detect.store as store_mod

            with mock.patch.object(store_mod.Store, "purge", side_effect=OSError("boom")):
                ok, msg = server._purge_with_restart(cfg, ["spool"], self._mk_runner(seen, False))
            self.assertFalse(ok)
            self.assertNotIn("恢复启动", msg)
            self.assertEqual([c for c in seen if c[0] == "sudo"], [])


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
        self.sact = mock.patch.object(server.sysactions, "service_is_active", return_value=True)
        self.sact.start()
        self.addCleanup(self.sact.stop)
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
        # ADR-010：采集运行中时，配置保存后重启采集使其生效
        self.assertIn("已重启采集", d["detail"])

    def test_config_write_does_not_start_inactive_collect(self):
        """采集未运行时写配置绝不拉起采集（ADR-010），仅提示下次生效。"""
        with mock.patch.object(server.sysactions, "service_is_active", return_value=False):
            st, d = self._post("/api/config", {"updates": {"M20AI_FPS": "2"}})
        self.assertEqual(st, 200)
        self.assertIn("采集未运行", d["detail"])
        self.assertNotIn("已重启", d["detail"])

    def test_snapshot_ring_http(self):
        """相机画面（ADR-012）：造一个新鲜环形帧 → 走 ring 分支（不起 ffmpeg）。"""
        d = os.path.join(self.tmp, "raw", "front")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "front_20261016_120000.jpg"), "wb") as fh:
            fh.write(b"\xff\xd8" + b"x" * 2048 + b"\xff\xd9")
        st, out = self._get("/api/snapshot?cam=front")
        self.assertEqual(st, 200)
        self.assertTrue(out["ok"])
        self.assertEqual(out["source"], "ring")
        self.assertEqual(out["cam"], "front")
        self.assertTrue(out["image"].startswith("data:image/jpeg;base64,"))

    def test_snapshot_unknown_cam_400(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/snapshot?cam=nope")
        self.assertEqual(ctx.exception.code, 400)

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

    def test_retention_saved_keys_roundtrip(self):
        """ADR-008：saved/ 留存清理参数走同一留存 POST/GET（env 级）。"""
        st, d = self._post("/api/retention", {"saved_max_mb": "120", "saved_keep_days": "2"})
        self.assertEqual(st, 200)
        env = envfile.read_env(self.env_file)
        self.assertEqual(env["M20AI_SAVED_MAX_MB"], "120")
        self.assertEqual(env["M20AI_SAVED_KEEP_DAYS"], "2")
        st, d = self._get("/api/retention")
        self.assertEqual(st, 200)
        self.assertEqual(d["saved_max_mb"], 120.0)
        self.assertEqual(d["saved_keep_days"], 2.0)

    def test_retention_rejects_negative_saved_max(self):
        st, d = self._post("/api/retention", {"saved_max_mb": "-1"})
        self.assertEqual(st, 400)
        self.assertIn("校验失败", d["error"])

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
        """spool_clear（旧字段兼容）：POST 后 spool/ 内 *.jpg 被清空，notes 带统计；raw/ 不动。"""
        from m20_ai_detect.store import Store

        store = Store(self.cfg.sampler_cfg)
        for i in range(2):
            with open(os.path.join(store.spool_for("front"), "sc%d.jpg" % i), "wb") as fh:
                fh.write(b"\0" * 100)
        st, d = self._post("/api/retention", {"spool_clear": True})
        self.assertEqual(st, 200)
        self.assertTrue(any("已清空：spool/ 积压帧 2 个文件" in n for n in d["notes"]), d)
        self.assertEqual(
            [f for f in os.listdir(store.spool_for("front")) if f.endswith(".jpg")], []
        )

    # ---- 关注目标（ADR-011）----

    def test_retention_get_includes_targets_and_label_stats(self):
        """GET /api/retention 带「关注目标」配置与今日检出标签统计。"""
        from datetime import datetime

        path = os.path.join(self.tmp, "results", datetime.now().strftime("%Y%m%d") + ".jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"items": [{"label": "person"}, {"label": "chair"}]}) + "\n")
            fh.write(json.dumps({"items": [{"label": "person"}]}) + "\n")
        server._label_stats_cache["base"] = ""  # 使缓存失效，读刚写入的数据
        st, d = self._get("/api/retention")
        self.assertEqual(st, 200)
        # env 文件为类内共享，不作具体值断言（顺序无关）
        self.assertIsInstance(d["alert_labels"], list)
        self.assertTrue(0.0 < float(d["alert_score"]) <= 1.0)
        stats = {it["label"]: it["count"] for it in d["label_stats"]}
        self.assertEqual(stats, {"person": 2, "chair": 1})

    def test_retention_post_targets_roundtrip(self):
        st, _ = self._post(
            "/api/retention", {"alert_labels": ["person", "chair"], "alert_score": "0.5"}
        )
        self.assertEqual(st, 200)
        env = envfile.read_env(self.env_file)
        self.assertEqual(env["M20AI_ALERT_LABELS"], "person,chair")
        self.assertEqual(env["M20AI_ALERT_SCORE"], "0.5")
        st, d = self._get("/api/retention")
        self.assertEqual(d["alert_labels"], ["person", "chair"])
        self.assertEqual(d["alert_score"], 0.5)

    def test_retention_alert_labels_dedup_and_trim(self):
        st, _ = self._post("/api/retention", {"alert_labels": " person , ,person, chair "})
        self.assertEqual(st, 200)
        env = envfile.read_env(self.env_file)
        self.assertEqual(env["M20AI_ALERT_LABELS"], "person,chair")

    def test_retention_alert_labels_can_be_cleared(self):
        st, _ = self._post("/api/retention", {"alert_labels": ""})
        self.assertEqual(st, 200)
        env = envfile.read_env(self.env_file)
        self.assertEqual(env.get("M20AI_ALERT_LABELS", ""), "")

    def test_retention_rejects_bad_label_chars(self):
        st, d = self._post("/api/retention", {"alert_labels": "per son!"})
        self.assertEqual(st, 400)
        self.assertIn("非法", d["error"])

    def test_retention_rejects_too_many_labels(self):
        st, d = self._post(
            "/api/retention", {"alert_labels": ",".join("l%d" % i for i in range(33))}
        )
        self.assertEqual(st, 400)
        self.assertIn("最多", d["error"])

    def test_retention_rejects_bad_score(self):
        st, d = self._post("/api/retention", {"alert_score": "1.5"})
        self.assertEqual(st, 400)
        self.assertIn("校验失败", d["error"])

    def test_retention_restart_collect_when_active(self):
        st, d = self._post(
            "/api/retention", {"alert_labels": "person", "restart_collect": True}
        )
        self.assertEqual(st, 200)
        self.assertTrue(any("已重启采集" in n for n in d["notes"]), d)
        # 重启消息替代了"重启后生效"，避免自相矛盾
        self.assertFalse(any("重启采集后生效" in n for n in d["notes"]), d)

    def test_retention_restart_collect_when_inactive(self):
        with mock.patch.object(server.sysactions, "service_is_active", return_value=False):
            st, d = self._post(
                "/api/retention", {"alert_labels": "person", "restart_collect": True}
            )
        self.assertEqual(st, 200)
        self.assertTrue(any("下次开启采集" in n for n in d["notes"]), d)

    # ---- 数据清空（ADR-011）----

    def test_retention_purge_http(self):
        from m20_ai_detect.store import Store

        store = Store(self.cfg.sampler_cfg)
        with open(os.path.join(store.saved_for("front"), "pg.jpg"), "wb") as fh:
            fh.write(b"\0" * 64)
        with open(os.path.join(store.raw_for("front"), "pg.jpg"), "wb") as fh:
            fh.write(b"\0" * 64)
        st, d = self._post("/api/retention", {"purge": ["saved", "raw"]})
        self.assertEqual(st, 200)
        self.assertTrue(any("已清空" in n for n in d["notes"]), d)
        self.assertNotIn("pg.jpg", os.listdir(store.saved_for("front")))
        self.assertNotIn("pg.jpg", os.listdir(store.raw_for("front")))

    def test_retention_purge_rejects_unknown_kind(self):
        st, d = self._post("/api/retention", {"purge": ["saved", "etc"]})
        self.assertEqual(st, 400)
        self.assertIn("未知类别", d["error"])

    def test_retention_purge_rejects_empty_list(self):
        st, d = self._post("/api/retention", {"purge": []})
        self.assertEqual(st, 400)


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


class TestSavedGallery(unittest.TestCase):
    """ADR-008：/api/saved（目标图片时间轴汇总）与 /api/saved/img（JPEG 服务）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="m20ai-gallery-")
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
        # 固定时钟偏移：无 _saved_at 的老文件退化为 mtime + offset
        self.offset = mock.patch.object(server.Console, "_measure_offset", return_value=1234.5)
        self.offset.start()
        self.addCleanup(self.offset.stop)

    def _get_raw(self, path):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (self.port, path), timeout=5
            ) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _get(self, path):
        st, _h, body = self._get_raw(path)
        return st, json.loads(body.decode("utf-8"))

    @staticmethod
    def _mk_pair(base, cam, stem, saved_at="", alert=False, items=None, mtime=None):
        d = os.path.join(base, "saved", cam)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, stem + ".jpg")
        with open(p, "wb") as fh:
            fh.write(b"\xff\xd8\xff\xe0" + b"\0" * 16)
        doc = {"capability": "ai-04", "results": {"items": items or []}}
        if saved_at:
            doc["_saved_at"] = saved_at
        if alert:
            doc["_alert"] = True
        js = os.path.join(d, stem + ".json")
        with open(js, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
            os.utime(js, (mtime, mtime))
        return p

    def test_gallery_sorted_newest_first_with_meta(self):
        self._mk_pair(
            self.tmp, "front", "g1", saved_at="2026-10-15T10:00:00.000",
            items=[{"label": "person", "score": 0.9}], alert=True,
        )
        self._mk_pair(self.tmp, "front", "g2", saved_at="2026-10-15T11:00:00.000")
        st, d = self._get("/api/saved?n=50&cam=front")
        self.assertEqual(st, 200)
        self.assertTrue(d["ok"])
        self.assertIn("front", d["cams"])
        stems = [r["stem"] for r in d["records"]]
        self.assertLess(stems.index("g2"), stems.index("g1"))  # 最新在前
        g1 = [r for r in d["records"] if r["stem"] == "g1"][0]
        self.assertEqual(g1["frame"], "g1.jpg")
        self.assertEqual(g1["cam"], "front")
        self.assertEqual(g1["ts"], "2026-10-15T10:00:00.000")
        self.assertEqual(g1["n_items"], 1)
        self.assertEqual(g1["items"][0]["label"], "person")
        self.assertTrue(g1["alert"])
        self.assertEqual(g1["url"], "/api/saved/img?cam=front&frame=g1.jpg")

    def test_gallery_cam_filter(self):
        self._mk_pair(self.tmp, "back", "bk1", saved_at="2026-10-15T09:00:00.000")
        st, d = self._get("/api/saved?n=50&cam=back")
        self.assertEqual(st, 200)
        self.assertTrue(d["records"])
        self.assertTrue(all(r["cam"] == "back" for r in d["records"]))

    def test_gallery_fallback_ts_from_mtime_plus_offset(self):
        """老文件（无 _saved_at）：ts = mtime + 时钟偏移。"""
        import datetime as _dt

        mt = 1700000000.0
        self._mk_pair(self.tmp, "front", "fb", mtime=mt)
        st, d = self._get("/api/saved?n=50&cam=front")
        rec = [r for r in d["records"] if r["stem"] == "fb"][0]
        expect = _dt.datetime.fromtimestamp(mt + 1234.5).isoformat(timespec="milliseconds")
        self.assertEqual(rec["ts"], expect)

    def test_gallery_skips_json_only_and_non_pairs(self):
        """只有 .json（无 jpg）的留存不算时间轴条目；无关文件不出现。"""
        d = os.path.join(self.tmp, "saved", "front")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "onlyjson.json"), "w", encoding="utf-8") as fh:
            json.dump({"_saved_at": "2026-10-15T10:30:00.000"}, fh)
        with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        st, g = self._get("/api/saved?n=50&cam=front")
        self.assertNotIn("onlyjson", [r["stem"] for r in g["records"]])

    def test_img_served_as_jpeg(self):
        self._mk_pair(self.tmp, "front", "img1", saved_at="2026-10-15T12:00:00.000")
        st, headers, body = self._get_raw("/api/saved/img?cam=front&frame=img1.jpg")
        self.assertEqual(st, 200)
        self.assertEqual(headers.get("Content-Type"), "image/jpeg")
        self.assertTrue(body.startswith(b"\xff\xd8"))

    def test_img_404_for_missing(self):
        st, d = self._get("/api/saved/img?cam=front&frame=missing.jpg")
        self.assertEqual(st, 404)
        self.assertFalse(d["ok"])

    def test_img_rejects_path_traversal(self):
        st, d = self._get("/api/saved/img?cam=front&frame=..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(st, 400)


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

    def test_save_stamps_clock_offset_ts(self):
        """ADR-008：单帧检测留存时带 _saved_at（真实时钟 = 本机 + 偏移）。"""
        with tempfile.TemporaryDirectory() as td:
            payload = {"capability": "ai-04", "results": {"items": []}}
            fake = fake_detector_with(payload)
            with mock.patch("m20_ai_detect.detect.Detector", return_value=fake):
                out = server.detect_single_frame(
                    self._cfg(td), b"\xff\xd8jpg", save=True, clock_offset=3600.0
                )
            with open(os.path.join(td, out["resp_path"]), encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertIn("_saved_at", doc)


class TestReadOnlyFiles(unittest.TestCase):
    """ADR-009：/api/files（只读目录列表）与 /api/file（单文件只读 + tail）。

    核心安全断言：白名单之外的任何路径（工程代码 / env / /etc）都必须 400。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="m20ai-files-")
        cls.env_file = write_env_file(cls.tmp)
        for d in ("saved/front", "raw/front", "results", "spool", "log"):
            os.makedirs(os.path.join(cls.tmp, d), exist_ok=True)
        # 白名单外的诱饵：工程代码 + env，绝不可被读走
        os.makedirs(os.path.join(cls.tmp, "src"), exist_ok=True)
        with open(os.path.join(cls.tmp, "src", "secret.py"), "w", encoding="utf-8") as fh:
            fh.write("TOKEN='leak'\n")
        with open(os.path.join(cls.tmp, "saved", "front", "a1.jpg"), "wb") as fh:
            fh.write(b"\xff\xd8\xff\xe0JPEGDATA")
        with open(
            os.path.join(cls.tmp, "saved", "front", "a1.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump({"results": {"items": []}}, fh)
        with open(
            os.path.join(cls.tmp, "results", "20261016.jsonl"), "w", encoding="utf-8"
        ) as fh:
            for i in range(50):
                fh.write(json.dumps({"i": i}) + "\n")
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

    def _get_raw(self, path):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (self.port, path), timeout=5
            ) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _get(self, path):
        st, _h, body = self._get_raw(path)
        return st, json.loads(body.decode("utf-8"))

    def test_root_listing_shows_only_whitelist(self):
        st, d = self._get("/api/files")
        self.assertEqual(st, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(d["dir"], "")
        names = [e["name"] for e in d["entries"]]
        self.assertIn("saved", names)
        self.assertIn("results", names)
        self.assertNotIn("src", names)  # 工程代码不可见
        self.assertNotIn("m20-ai-detect.env", names)

    def test_subdir_listing_dirs_first_then_newest_files(self):
        st, d = self._get("/api/files?dir=saved/front")
        self.assertEqual(st, 200)
        self.assertEqual(d["dir"], "saved/front")
        self.assertEqual(d["parent"], "saved")
        types = [e["type"] for e in d["entries"]]
        self.assertEqual(types, sorted(types, key=lambda t: 0 if t == "dir" else 1))
        a1 = [e for e in d["entries"] if e["name"] == "a1.jpg"][0]
        self.assertEqual(a1["type"], "file")
        self.assertIsInstance(a1["size"], int)

    def test_match_filter(self):
        st, d = self._get("/api/files?dir=saved/front&match=json")
        self.assertEqual(st, 200)
        self.assertEqual([e["name"] for e in d["entries"]], ["a1.json"])

    def test_traversal_dirs_rejected(self):
        for bad in ("../..", "/etc", "src", "saved/../../src", "saved/.."):
            st, d = self._get("/api/files?dir=%s" % urllib.parse.quote(bad))
            self.assertEqual(st, 400, "dir=%r 应被拒" % bad)
            self.assertFalse(d["ok"])

    def test_file_outside_whitelist_rejected(self):
        for bad in ("src/secret.py", "../m20-ai-detect.env", "/etc/passwd", "results/../../etc/passwd"):
            st, d = self._get("/api/file?path=%s" % urllib.parse.quote(bad))
            self.assertEqual(st, 400, "path=%r 应被拒" % bad)
            self.assertFalse(d["ok"])

    def test_file_read_json_and_jpeg_content_types(self):
        st, h, body = self._get_raw("/api/file?path=saved/front/a1.json")
        self.assertEqual(st, 200)
        self.assertIn("application/json", h.get("Content-Type", ""))
        self.assertTrue(json.loads(body.decode("utf-8")).get("results") is not None)

        st, h, body = self._get_raw("/api/file?path=saved/front/a1.jpg")
        self.assertEqual(st, 200)
        self.assertEqual(h.get("Content-Type"), "image/jpeg")
        self.assertTrue(body.startswith(b"\xff\xd8"))

    def test_file_tail_returns_last_n_lines(self):
        st, h, body = self._get_raw("/api/file?path=results/20261016.jsonl&tail=3")
        self.assertEqual(st, 200)
        lines = [l for l in body.decode("utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(l)["i"] for l in lines], [47, 48, 49])

    def test_file_tail_over_limit_rejected(self):
        st, _h, _b = self._get_raw("/api/file?path=results/20261016.jsonl&tail=99999")
        self.assertEqual(st, 400)

    def test_file_download_header(self):
        st, h, _b = self._get_raw("/api/file?path=saved/front/a1.jpg&dl=1")
        self.assertEqual(st, 200)
        self.assertIn('attachment; filename="a1.jpg"', h.get("Content-Disposition", ""))

    def test_file_missing_is_404(self):
        st, d = self._get("/api/file?path=saved/front/nope.jpg")
        self.assertEqual(st, 404)
        self.assertFalse(d["ok"])

    def test_file_missing_path_param(self):
        st, d = self._get("/api/file")
        self.assertEqual(st, 400)
        self.assertFalse(d["ok"])


class TestJournalUnitNormalization(unittest.TestCase):
    """ADR-010：journal/journald 字段的单位归一化。

    关键点：systemd 的裸数字时长是「秒」，我们必须重解释为「天」，
    否则用户填 7 想表达 7 天会变成 7 秒。
    """

    def test_vacuum_size_bare_appends_m(self):
        f = {"size": "20"}
        self.assertIsNone(sysactions.check_vacuum(f))
        self.assertEqual(f["size"], "20M")

    def test_vacuum_size_suffix_kept_and_uppercased(self):
        for raw, want in (("200M", "200M"), ("1g", "1G"), ("512k", "512K"), ("1T", "1T")):
            f = {"size": raw}
            self.assertIsNone(sysactions.check_vacuum(f), raw)
            self.assertEqual(f["size"], want)

    def test_vacuum_time_bare_becomes_days_not_seconds(self):
        f = {"time": "7"}
        self.assertIsNone(sysactions.check_vacuum(f))
        self.assertEqual(f["time"], "7d")  # 不是 "7"（=7 秒）

    def test_vacuum_time_suffix_kept(self):
        for raw in ("7d", "24h", "30m", "60s", "2w"):
            f = {"time": raw}
            self.assertIsNone(sysactions.check_vacuum(f), raw)
            self.assertEqual(f["time"], raw)

    def test_vacuum_requires_exactly_one_of_size_time(self):
        self.assertIn("二选一", sysactions.check_vacuum({"size": "1", "time": "1"}))
        self.assertIn("二选一", sysactions.check_vacuum({}))

    def test_vacuum_bad_unit_message_lists_legal_forms(self):
        msg = sysactions.check_vacuum({"size": "20X"})
        self.assertIn("20X", msg)
        self.assertIn("裸数字按 MB", msg)
        msg = sysactions.check_vacuum({"time": "7q"})
        self.assertIn("裸数字按天", msg)

    def test_journald_limits_normalized(self):
        f = {"SystemMaxUse": "200", "MaxRetentionSec": "7"}
        self.assertIsNone(sysactions.check_journald_limits(f))
        self.assertEqual(f["SystemMaxUse"], "200M")
        self.assertEqual(f["MaxRetentionSec"], "7d")

    def test_journald_limits_empty_both(self):
        self.assertIn("至少填一项", sysactions.check_journald_limits({}))

    def test_journald_limits_bad_unit(self):
        self.assertIn("无法识别", sysactions.check_journald_limits({"SystemMaxUse": "200X"}))

    def test_logrotate_is_pure_count(self):
        self.assertIsNone(sysactions.check_logrotate({"rotate": "7"}))
        self.assertIn("无单位", sysactions.check_logrotate({"rotate": "7d"}))
        self.assertIn("1-365", sysactions.check_logrotate({"rotate": "0"}))
        self.assertIn("1-365", sysactions.check_logrotate({"rotate": "999"}))


class TestRetentionUnitRoundTrip(unittest.TestCase):
    """控制台留存 POST 接受带单位写法，落 env 后采样器仍能解析（ADR-010）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="m20ai-units-")
        self.env_file = write_env_file(self.tmp)
        self.cfg = server.ConsoleConfig(
            {
                "M20AIC_BIND": "127.0.0.1",
                "M20AIC_PORT": "0",
                "M20AIC_TOKEN": "",
                "M20AIC_BASE_DIR": self.tmp,
                "M20AIC_ENV_FILE": self.env_file,
                "M20AIC_HELPER": "/bin/true",
            }
        )
        self.srv = server.Console(self.cfg)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def _post(self, body):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/retention" % self.port,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_with_units_accepted_and_sampler_parses(self):
        st, d = self._post({"saved_max_mb": "1G", "saved_keep_days": "24h"})
        self.assertEqual(st, 200, d)
        self.assertTrue(d["ok"])
        # 落 env 后再由采样器侧解析，值必须正确
        cfg = Config.from_env(envfile.read_env(self.env_file))
        self.assertEqual(cfg.saved_max_bytes, 1024 * 1024 * 1024)
        self.assertEqual(cfg.saved_keep_days, 1.0)

    def test_bad_unit_rejected_with_clear_error(self):
        st, d = self._post({"saved_max_mb": "1x"})
        self.assertEqual(st, 400)
        self.assertFalse(d["ok"])
        self.assertIn("单位", d["error"])

    def test_bare_number_still_works(self):
        st, d = self._post({"ring_max_mb": "300"})
        self.assertEqual(st, 200, d)
        cfg = Config.from_env(envfile.read_env(self.env_file))
        self.assertEqual(cfg.ring_max_bytes, 300 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
