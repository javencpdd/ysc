"""webconsole 测试：纯逻辑模块 + HTTP 层端到端（本地回环，外部依赖全部打桩）。"""
from __future__ import annotations

import base64
import json
import os
import re
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


class TestJournalDiskBytes(unittest.TestCase):
    """journalctl --disk-usage 英文原文 → 字节数（前端按语言渲染，ADR-013 延伸）。

    真实原文形如 "Archived and active journals take up 208.0M in the file system."
    """

    def _runner(self, out, rc=0):
        return lambda cmd, t=15.0: (rc, out, "")

    def test_parses_english_sentence(self):
        r = self._runner(
            "Archived and active journals take up 208.0M in the file system.\n"
        )
        self.assertEqual(
            sysactions.journal_disk_bytes(r), int(208.0 * 1024 * 1024)
        )

    def test_parses_all_units(self):
        cases = [
            ("16.0K in the file system.", 16 * 1024),
            ("208.0M in the file system.", 208 * 1024 ** 2),
            ("1.5G in the file system.", int(round(1.5 * 1024 ** 3))),
            ("2.0T in the file system.", 2 * 1024 ** 4),
            ("512B in the file system.", 512),
        ]
        for text, want in cases:
            r = self._runner(text)
            self.assertEqual(sysactions.journal_disk_bytes(r), want, text)

    def test_parses_kb_mb_gb_spelled_out(self):
        r = self._runner("Archived and active journals take up 4.0KB in the file system.")
        self.assertEqual(sysactions.journal_disk_bytes(r), 4096)
        r = self._runner("Archived and active journals take up 3.0GB in the file system.")
        self.assertEqual(sysactions.journal_disk_bytes(r), 3 * 1024 ** 3)

    def test_does_not_match_other_numbers(self):
        """句子里出现别的数字（如 208.0M）时仍取带单位的那一个。"""
        r = self._runner("vacuuming 3 files, 208.0M total in the file system.")
        self.assertEqual(sysactions.journal_disk_bytes(r), 208 * 1024 ** 2)

    def test_returns_none_on_failure(self):
        self.assertIsNone(sysactions.journal_disk_bytes(self._runner("", rc=1)))

    def test_returns_none_on_unparseable(self):
        self.assertIsNone(sysactions.journal_disk_bytes(self._runner("no size here\n")))

    def test_raw_text_still_available(self):
        """保留原文接口（日志/排障可能要用整句）。"""
        r = self._runner("Archived and active journals take up 208.0M in the file system.\n")
        self.assertIn("Archived and active", sysactions.journal_disk_usage(r))


class TestJournalServiceUsage(unittest.TestCase):
    """单个 unit 的 journal 体量估算（解释"208MB 里本服务占多少"）。"""

    def test_counts_lines_and_bytes(self):
        out = "line one\nline two\n\nline three\n"
        r = lambda cmd, t=20.0: (0, out, "")  # noqa: E731
        got = sysactions.journal_service_usage("m20-ai-detect", r)
        self.assertEqual(got["lines"], 3)          # 空行不计
        self.assertEqual(got["bytes"], len(out.encode("utf-8")))
        self.assertEqual(got["bytes"], 30)

    def test_passes_unit_argument(self):
        seen = []
        def r(cmd, t=20.0):
            seen.append(cmd)
            return (0, "x\n", "")
        sysactions.journal_service_usage("m20-ai-console", r)
        self.assertEqual(seen[0][:3], ["journalctl", "-u", "m20-ai-console"])
        self.assertIn("--no-pager", seen[0])

    def test_returns_none_on_failure_or_bad_unit(self):
        self.assertIsNone(sysactions.journal_service_usage("m20-ai-detect", lambda c, t=20.0: (1, "", "err")))
        self.assertIsNone(sysactions.journal_service_usage("bad;rm -rf", lambda c, t=20.0: (0, "x", "")))


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

    def _req(self, path, obj=None, headers=None):
        """带自定义请求头的 GET/POST（ADR-013：X-Lang 中英适配用）。"""
        h = dict(headers or {})
        if obj is None:
            req = urllib.request.Request(
                "http://127.0.0.1:%d%s" % (self.port, path), headers=h
            )
        else:
            req = urllib.request.Request(
                "http://127.0.0.1:%d%s" % (self.port, path),
                data=json.dumps(obj).encode("utf-8"),
                headers=dict({"Content-Type": "application/json"}, **h),
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

    def test_status_api_returns_bytes_not_english(self):
        """HTTP 层：/api/status 给 journal_bytes（数字），不再给英文整句。"""
        jd = mock.patch.object(
            server.sysactions, "journal_disk_bytes",
            return_value=int(208.0 * 1024 * 1024),
        )
        jd.start()
        self.addCleanup(jd.stop)
        st, d = self._get("/api/status")
        self.assertEqual(st, 200)
        self.assertIn("journal_bytes", d)
        self.assertNotIn("journal_usage", d)
        self.assertEqual(d["journal_bytes"], int(208.0 * 1024 * 1024))
        self.assertNotIn("Archived and active journals", json.dumps(d))

    def test_status_api_journal_bytes_none_when_unavailable(self):
        jd = mock.patch.object(server.sysactions, "journal_disk_bytes", return_value=None)
        jd.start()
        self.addCleanup(jd.stop)
        st, d = self._get("/api/status")
        self.assertEqual(st, 200)
        self.assertIsNone(d["journal_bytes"])

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

    # ---- 中英适配（ADR-013：X-Lang 头决定语言，默认 zh）----

    def test_retention_note_localized_en(self):
        st, d = self._req("/api/retention", headers={"X-Lang": "en"})
        self.assertEqual(st, 200)
        self.assertIn("apply immediately", d["note"])
        st2, d2 = self._req("/api/retention")
        self.assertIn("env 级改动重启采样器后生效", d2["note"])

    def test_config_detail_localized_en(self):
        with mock.patch.object(server.sysactions, "service_is_active", return_value=False):
            st, d = self._req(
                "/api/config", {"updates": {"M20AI_FPS": "2"}}, headers={"X-Lang": "en"}
            )
        self.assertEqual(st, 200)
        self.assertIn("Saved to env", d["detail"])
        self.assertIn("not auto-started", d["detail"])

    def test_snapshot_error_localized_en(self):
        st, d = self._req("/api/snapshot?cam=nope", headers={"X-Lang": "en"})
        self.assertEqual(st, 400)
        self.assertIn("Unknown camera", d["error"])
        # 分隔符也随语言：英文消息里不许出现中文顿号
        self.assertNotIn("、", d["error"])

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


class TestI18nDict(unittest.TestCase):
    """ADR-013：index.html 内嵌 i18n JSON——双语键集合一致、无漏译、无死键。"""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(server.__file__), "static", "index.html")
        with open(path, encoding="utf-8") as fh:
            cls.html = fh.read()

    def _dict(self):
        m = re.search(
            r'<script type="application/json" id="i18n-data">(.*?)</script>',
            self.html,
            re.S,
        )
        self.assertIsNotNone(m, "index.html 缺少 i18n-data JSON 块")
        return json.loads(m.group(1))

    def test_langs_key_sets_match_and_non_empty(self):
        data = self._dict()
        self.assertEqual(set(data), {"zh", "en"})
        self.assertEqual(set(data["zh"]), set(data["en"]))
        for lang in ("zh", "en"):
            for key, val in data[lang].items():
                self.assertTrue(
                    isinstance(val, str) and val.strip(),
                    "%s.%s 为空或不是字符串" % (lang, key),
                )

    def test_referenced_keys_exist_and_no_dead_keys(self):
        zh = self._dict()["zh"]
        used = set(re.findall(r'data-i18n(?:-ph|-title|-html)?="([^"]+)"', self.html))
        used |= set(re.findall(r'(?<![A-Za-z0-9_$])t\("([^"]+)"', self.html))
        # JS 里按三元动态引用（静态扫不到）：关注目标 chip 文案、
        # 折叠按钮文案与「全部折叠/展开」按钮文案（随折叠状态切换）
        used |= {
            "alert.chip_on", "alert.chip_off",
            "card.fold", "card.unfold",
            "top.fold_all", "top.fold_all_title",
            "top.unfold_all", "top.unfold_all_title",
        }
        self.assertEqual(used - set(zh), set(), "有引用了字典里不存在的键")
        self.assertEqual(set(zh) - used, set(), "字典里有从未被引用的死键")

    def test_retention_card_two_buttons_not_confusable(self):
        """ADR-014：留存卡两个按钮必须语义互斥（容量/时长 vs 留存条件）。

        两个按钮曾经都叫「保存…（重启后生效）」，用户按错后无效改动不显著，
        故固化：文案互不相同、分别点明各自维度、且都不含对方的命名。
        """
        d = self._dict()
        for lang, words in (("zh", ("容量", "留存条件")), ("en", ("quota", "mode"))):
            save_env = d[lang]["ret.save_env"]
            save_mode = d[lang]["ret.save_mode_btn"]
            self.assertNotEqual(save_env, save_mode, "%s 两个按钮文案相同" % lang)
            self.assertIn(words[0], save_env.lower(), "%s save_env 未点明容量/时长" % lang)
            self.assertIn(words[1], save_mode.lower(), "%s save_mode btn 未点明留存条件" % lang)
            self.assertNotEqual(
                save_env, save_mode.replace(words[1], words[0]), "%s 文案仅关键词互换" % lang
            )
        # 说明性 note 双语都在，且点明各自只管一段
        zh = d["zh"]
        self.assertIn("raw/、results/ 与此无关", zh["ret.cond_note"])
        self.assertIn("四个互不相干的维度", zh["ret.quota_note"])
        for key in ("ret.sec_cond", "ret.cond_note", "ret.sec_quota", "ret.quota_note"):
            self.assertTrue(zh[key].strip() and d["en"][key].strip(), "%s 有空值" % key)
        # 两个 note 的 i18n-html 标记都落在页面上（不是只进词典的死键）
        self.assertIn('data-i18n-html="ret.cond_note"', self.html)
        self.assertIn('data-i18n-html="ret.quota_note"', self.html)
        self.assertIn('data-i18n="ret.sec_cond"', self.html)
        self.assertIn('data-i18n="ret.sec_quota"', self.html)
        # 两个按钮各自只调自己的保存函数
        self.assertIn('onclick="saveSaveMode()" data-i18n="ret.save_mode_btn"', self.html)
        self.assertIn('onclick="saveEnvRetention()" data-i18n="ret.save_env"', self.html)


class TestCardFold(unittest.TestCase):
    """卡片折叠（ADR-015）：data-fold 键唯一、CSS/JS 钩子齐全、记忆键稳定（与语言无关）。"""

    EXPECTED = {
        "svc", "recent", "snap", "tl", "fb", "cfg", "cam", "alert", "single", "log", "ret",
    }

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(server.__file__), "static", "index.html")
        with open(path, encoding="utf-8") as fh:
            cls.html = fh.read()

    def test_every_target_card_has_unique_fold_key(self):
        # 只扫 HTML 标签（JS 里也有 '.card[data-fold="' + key + '"]' 拼接，不参与）
        keys = re.findall(r'<div class="card[^">]*"[^>]*data-fold="([^"]+)"', self.html)
        self.assertEqual(set(keys), self.EXPECTED, "折叠键集合与预期不符")
        self.assertEqual(len(keys), len(set(keys)), "折叠键有重复")

    def test_css_hides_body_when_collapsed(self):
        # 必须带 !important：卡片内图片由 JS 写行内 style.display（如 snapLoad），
        # 行内优先级更高，不加 !important 折叠后画面会露出来（v0.8.3 bug）
        self.assertIn(".card.collapsed > *:not(h2){display:none !important}", self.html)
        # 标题栏内也收敛：只留标题 + 状态徽标（.tag）；说明与工具条按钮组一并隐藏
        self.assertIn(".card.collapsed h2 .row{display:none !important}", self.html)
        self.assertIn(".card.collapsed h2 .note{display:none !important}", self.html)
        self.assertIn(".card h2 .fold{", self.html)

    def test_inline_display_writers_are_known(self):
        """存在写行内 display 的 JS（折叠规则必须能压过它）——锁住这个前提。"""
        self.assertIn('img.style.display = "block"', self.html)
        self.assertIn('img.style.display = "none"', self.html)

    def test_js_hooks_present(self):
        for fn in ("function initFolds(", "function setFold(", "function toggleAllFolds(",
                   "function isFolded(", "function syncFoldAllBtn("):
            self.assertIn(fn, self.html, "缺少 %s" % fn)
        # 记忆键必须与语言无关（用 data-fold 恒定英文键，不是标题文本）
        self.assertIn('var FOLD_KEY = "m20ai-fold"', self.html)
        self.assertIn('localStorage.setItem(FOLD_KEY + "-" + foldId(card)', self.html)
        # 初始化顺序：先注入按钮再 applyI18n（否则 title 不会本地化）
        self.assertIn("initFolds();\napplyI18n();", self.html)

    def test_fold_pauses_polling(self):
        """折叠卡片时暂停其自动刷新（日志/时间轴/最近检测），页面隐藏仍照旧暂停。

        相机画面已升级为自适应节奏（见 TestSnapThrottle：ring 3s / live 10s /
        失败退避 60s），同样在 snapAutoDue() 里判折叠与后台。
        """
        self.assertIn('!isFolded("log")', self.html)
        self.assertIn('!isFolded("tl")', self.html)
        self.assertIn('!isFolded("recent")', self.html)
        due = re.search(r"function snapAutoDue\(\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn('isFolded("snap")', due)
        self.assertIn("document.hidden", due)

    def test_h2_never_carries_data_i18n(self):
        """v0.8.5 起：卡片标题 h2 自身不得带 data-i18n。

        applyI18n 会对带 data-i18n 的元素整块重写 textContent——若挂在 h2 上，
        注入的折叠按钮会作为子节点被清掉，折叠后无法再单独展开
        （2026-10-17 实测：检测配置/相机与采集/关注目标/日志与数据留存策略）。
        标题一律用 <span data-i18n=...> 包裹。
        """
        self.assertNotIn("<h2 data-i18n", self.html, "h2 不能直接带 data-i18n")
        self.assertNotIn("<h2 data-i18n-html", self.html)
        # 每张可折叠卡的 h2 内都要有 .fold（要么静态存在，要么运行期注入后存在）
        for key in self.EXPECTED:
            m = re.search(r'data-fold="%s"' % key, self.html)
            self.assertIsNotNone(m, "缺少 data-fold=%s" % key)

    def test_apply_i18n_rebuilds_fold_buttons(self):
        """防御逻辑必须存在：applyI18n 末尾幂等重建折叠按钮。"""
        m = re.search(r"function applyI18n\(\)\{(.*?)\n\}", self.html, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("initFolds();", body, "applyI18n 未重建折叠按钮（防御缺失）")
        self.assertIn("syncFoldAllBtn();", body)
        # initFolds 必须幂等（已有按钮则跳过），否则每次 applyI18n 都会叠加按钮
        m2 = re.search(r"function initFolds\(\)\{(.*?)\n\}", self.html, re.S)
        self.assertIn('h2.querySelector(".fold")', m2.group(1))

    def test_fold_buttons_are_real_buttons_not_dead_keys(self):
        zh = json.loads(re.search(
            r'<script type="application/json" id="i18n-data">(.*?)</script>', self.html, re.S
        ).group(1))["zh"]
        for k in ("card.fold", "card.unfold", "top.fold_all", "top.unfold_all"):
            self.assertTrue(zh[k].strip(), "%s 为空" % k)


class TestSnapThrottle(unittest.TestCase):
    """相机画面拉流节奏与多相机（ADR-012 2026-10-18）：不为看不见的画面占用车端带宽。

    能力：相机多选（前/后/都选/都不选）、刷新频率可调（自适应 / 1~60s / 关闭）、
    失败退避 60s、折叠与后台停发、一键停止拉流。
    """

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(server.__file__), "static", "index.html")
        with open(path, encoding="utf-8") as fh:
            cls.html = fh.read()

    def test_no_fixed_interval_loop(self):
        self.assertNotIn('setInterval(function(){ if (!document.hidden && !isFolded("snap")', self.html)
        self.assertIn("snapSchedule();", self.html)
        self.assertIn("function snapDelay()", self.html)

    def test_adaptive_delays_and_backoff(self):
        for probe in ("var SNAP_RING_MS = 3000", "SNAP_LIVE_MS = 10000",
                      "SNAP_FAIL_MAX = 3", "SNAP_PROBE_MS = 60000"):
            self.assertIn(probe, self.html, probe)
        body = re.search(r"function snapDelay\(\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn("SNAP_LIVE_MS", body)
        self.assertIn("SNAP_PROBE_MS", body)
        self.assertIn("snapEveryMs()", body, "用户显式频率应优先于自适应")

    def test_gate_covers_all_stop_paths(self):
        body = re.search(r"function snapAutoDue\(\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn("!SNAP_SEL.length", body, "未选相机时必须不拉流")
        self.assertIn('SNAP_EVERY === "0"', body, "选「关闭」时必须不拉流")
        self.assertIn("document.hidden", body)
        self.assertIn('isFolded("snap")', body)

    def test_camera_multi_select(self):
        """相机可前/后/都选/都不选：chips + localStorage 记忆 + 每台一个 img。"""
        self.assertIn('id="snap-cams"', self.html)
        self.assertIn("function snapToggleCam(", self.html)
        self.assertIn('var SNAP_KEY_SEL = "m20ai-snap-cams"', self.html)
        self.assertIn("function renderSnapChips(", self.html)
        self.assertIn("function renderSnapGrid(", self.html)
        self.assertIn('id="snap-grid"', self.html)
        body = re.search(r"function snapToggleCam\(n\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn('t("snap.no_cam")', body, "取消全部相机后要明确提示不拉流")
        self.assertIn("snapIdle()", body)

    def test_interval_select_and_stop(self):
        self.assertIn('id="snap-every"', self.html)
        self.assertIn("function snapEveryChange(", self.html)
        self.assertIn('SNAP_KEY_EVERY = "m20ai-snap-every"', self.html)
        for v in ('value="auto"', 'value="1000"', 'value="10000"', 'value="60000"', 'value="0"'):
            self.assertIn(v, self.html, v)
        self.assertIn("function stopSnap(", self.html)
        stop = re.search(r"function stopSnap\(\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn('sel.value = "0"', stop)

    def test_each_camera_fetched_separately(self):
        self.assertIn("function snapLoadOne(", self.html)
        self.assertIn("function snapAggregate(", self.html)
        self.assertIn("SNAP_BUSY[cam]", self.html, "每台应有独立 in-flight 标记")
        self.assertIn('t("snap.partial")', self.html, "部分不可达要有单独提示")
        self.assertIn('t("snap.down_msg"', self.html)

    def test_round_renders_all_at_once(self):
        """整轮统一上屏：不能"谁先回来谁先跳"，否则多相机看起来永远不同步。"""
        apply_body = re.search(r"function snapApply\(cam, d\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn("SNAP_PENDING[cam]", apply_body)
        self.assertNotIn("img.src", apply_body, "单路完成时不应直接更新 DOM")
        done = re.search(r"function snapRoundDone\(\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn("renderSnapOne(c, p)", done)
        self.assertIn("SNAP_SEL.forEach", done)

    def test_busy_skip_does_not_hang_round(self):
        """某路上一轮还卡着时也必须报到，否则整轮悬挂、画面停更。"""
        one = re.search(r"function snapLoadOne\(cam\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn("snapRoundDone()", one)

    def test_failure_backoff_and_recovery(self):
        agg = re.search(r"function snapAggregate\(\)\{.*?\n\}", self.html, re.S).group(0)
        self.assertIn("SNAP_FAILS + 1", agg)
        self.assertIn("(SNAP_FAILS + 1) : 0", agg, "成功/未全灭时应清零失败计数")
        self.assertIn('t("snap.auto_paused"', agg)

    def test_new_i18n_keys_present_and_used(self):
        zh = json.loads(re.search(
            r'<script type="application/json" id="i18n-data">(.*?)</script>', self.html, re.S
        ).group(1))["zh"]
        for k in ("snap.cams_label", "snap.every_label", "snap.every_auto", "snap.every_off",
                  "snap.no_cam", "snap.cap_ring", "snap.cap_live", "snap.cap_stale",
                  "snap.cap_fail", "snap.partial", "snap.partial_msg", "snap.live_multi",
                  "snap.cost_warn"):
            self.assertTrue(zh[k].strip(), k)
        used = set(re.findall(r't\("([^"]+)"', self.html))
        for k in ("snap.no_cam", "snap.cap_ring", "snap.cap_live", "snap.cap_stale",
                  "snap.cap_fail", "snap.partial", "snap.partial_msg", "snap.live_multi",
                  "snap.cost_warn"):
            self.assertIn(k, used, "%s 未被 JS 引用" % k)
