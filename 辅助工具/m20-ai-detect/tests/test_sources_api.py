"""源管理 API 测试（ADR-016 T5）：dump_sources 往返、mutate_sources 纯列表运算、
GET/POST /api/sources 与 /api/sources/discover 的 HTTP 行为（回环 + 全副作用打桩）。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from m20_ai_detect.config import Source, dump_sources, parse_sources  # noqa: E402
from webconsole import envfile, server  # noqa: E402

ENV_FIXTURE = """# 测试 env（旧两槽位写法：无 M20AI_SOURCES）
M20AI_AI_BASE=http://127.0.0.1:1
M20AI_CAP_ID=ai-04-yolov8-object-detection
M20AI_ENABLE_F=1
M20AI_SRC_F=rtsp://127.0.0.1:8554/video1
M20AI_FPS=1
M20AI_BASE_DIR={base}
"""


def write_env_file(tmp: str, text: str = ENV_FIXTURE) -> str:
    path = os.path.join(tmp, "m20-ai-detect.env")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("{base}", tmp))
    return path


class TestDumpSourcesRoundtrip(unittest.TestCase):
    """parse → dump → parse 必须等价（网页保存与手写 env 同一套语法）。"""

    def test_roundtrip_basic(self):
        srcs = parse_sources(
            "front=rtsp://10.21.31.103:8554/video1|transport=tcp;"
            "back=rtsp://10.21.31.103:8554/video2|off|fps=2"
        )
        self.assertEqual(parse_sources(dump_sources(srcs)), srcs)

    def test_roundtrip_with_extra_and_note(self):
        srcs = parse_sources(
            "gate=rtmp://192.168.2.1:1935/live/0|transport=udp|fps=2|"
            "extra=-vf,hflip|note=onvif-cam"
        )
        self.assertEqual(parse_sources(dump_sources(srcs)), srcs)

    def test_roundtrip_float_fps_no_noise(self):
        srcs = parse_sources("a=rtsp://h/p|fps=2")
        text = dump_sources(srcs)
        self.assertIn("fps=2", text)  # 不是 fps=2.0
        self.assertNotIn("fps=2.0", text)
        self.assertEqual(parse_sources(text), srcs)

    def test_unsafe_chars_rejected(self):
        for bad in ("rtsp://h/p;x=1", "rtsp://h/p|off", "rtsp://h/p\nx"):
            with self.assertRaises(Exception):
                dump_sources([Source(name="bad", uri=bad)])
        with self.assertRaises(Exception):  # note 同样不许含分隔符
            dump_sources([Source(name="bad", uri="rtsp://h/p", note="a|b")])


class TestMutateSources(unittest.TestCase):
    def setUp(self):
        self.srcs = parse_sources(
            "front=rtsp://10.21.31.103:8554/video1|transport=tcp;"
            "back=rtsp://10.21.31.103:8554/video2|off"
        )

    def test_add_appends_with_defaults(self):
        out = server.mutate_sources(
            self.srcs, "add", {"name": "gate", "uri": "rtmp://192.168.2.1:1935/live/0"}
        )
        self.assertEqual(len(out), 3)
        self.assertEqual(out[2].transport, "auto")
        self.assertIsNone(out[2].fps)
        self.assertTrue(out[2].enabled)
        self.assertEqual(len(self.srcs), 2)  # 不改入参

    def test_update_changes_only_given_fields(self):
        out = server.mutate_sources(
            self.srcs, "update", {"name": "front", "uri": "rtsp://new/path", "transport": "udp"}
        )
        self.assertEqual(out[0].uri, "rtsp://new/path")
        self.assertEqual(out[0].transport, "udp")
        self.assertTrue(out[0].enabled)
        self.assertEqual(out[1], self.srcs[1])

    def test_update_keeps_fps_when_absent_and_clears_when_none(self):
        base = parse_sources("a=rtsp://h/p|fps=2")
        kept = server.mutate_sources(base, "update", {"name": "a", "uri": "rtsp://h/q"})
        self.assertEqual(kept[0].fps, 2.0)
        cleared = server.mutate_sources(base, "update", {"name": "a", "fps": None})
        self.assertIsNone(cleared[0].fps)

    def test_update_bad_fps_raises(self):
        with self.assertRaises(Exception):
            server.mutate_sources(self.srcs, "update", {"name": "front", "fps": "abc"})

    def test_remove_enable_disable(self):
        out = server.mutate_sources(self.srcs, "remove", {"name": "back"})
        self.assertEqual([s.name for s in out], ["front"])
        out = server.mutate_sources(self.srcs, "disable", {"name": "front"})
        self.assertFalse(out[0].enabled)
        out = server.mutate_sources(out, "enable", {"name": "front"})
        self.assertTrue(out[0].enabled)

    def test_unknown_name_raises(self):
        for action in ("update", "remove", "enable", "disable"):
            with self.assertRaises(Exception, msg=action):
                server.mutate_sources(self.srcs, action, {"name": "nope"})

    def test_add_empty_uri_raises(self):
        with self.assertRaises(Exception):
            server.mutate_sources(self.srcs, "add", {"name": "x", "uri": ""})


class TestSourcesHTTP(unittest.TestCase):
    """起真实回环服务打 /api/sources；systemctl/helper/发现器全部打桩。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="m20ai-src-")
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
        # 每个用例从干净的旧两槽位 env 开始（保证用例间无顺序依赖）
        write_env_file(self.tmp)
        self.sact = mock.patch.object(server.sysactions, "service_is_active", return_value=True)
        self.sact.start()
        self.addCleanup(self.sact.stop)
        self.act = mock.patch.object(server.sysactions, "service_action", return_value=(True, "done"))
        self.act.start()
        self.addCleanup(self.act.stop)

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

    # ---- GET ----
    def test_get_sources_legacy_upgrade_view(self):
        """老部署 env 无 M20AI_SOURCES：GET 给生效 cameras（旧两槽位回落结果）。"""
        st, d = self._get("/api/sources")
        self.assertEqual(st, 200)
        self.assertEqual([s["name"] for s in d["sources"]], ["front"])
        self.assertEqual(d["sources"][0]["uri"], "rtsp://127.0.0.1:8554/video1")
        self.assertEqual(d["raw"], "")
        self.assertEqual(d["fps_global"], 1.0)
        self.assertFalse(d["allow_local_device"])

    def test_get_sources_reads_new_syntax(self):
        write_env_file(
            self.tmp,
            ENV_FIXTURE + "M20AI_SOURCES=front=rtsp://127.0.0.1:8554/video1;gate=rtmp://h:1935/live/0|off\n",
        )
        st, d = self._get("/api/sources")
        self.assertEqual([s["name"] for s in d["sources"]], ["front", "gate"])
        self.assertFalse(d["sources"][1]["enabled"])

    # ---- POST add/update/remove/enable/disable ----
    def test_add_writes_new_syntax_and_upgrades_in_place(self):
        st, d = self._post("/api/sources", {"action": "add", "name": "gate", "uri": "rtmp://192.168.2.1:1935/live/0"})
        self.assertEqual(st, 200, d)
        env = envfile.read_env(self.env_file)
        self.assertIn("M20AI_SOURCES", env)
        self.assertIn("gate=rtmp://192.168.2.1:1935/live/0", env["M20AI_SOURCES"])
        # 旧键保留（向后兼容），但 Config 优先 SOURCES
        self.assertEqual(env["M20AI_ENABLE_F"], "1")
        names = [s["name"] for s in d["sources"]]
        self.assertEqual(names, ["front", "gate"])
        self.assertIn("已写入 env", d["detail"])
        self.assertIn("已重启采集", d["detail"])  # service_is_active=True → 重启

    def test_add_duplicate_rejected(self):
        st, d = self._post("/api/sources", {"action": "add", "name": "front", "uri": "rtsp://h/p"})
        self.assertEqual(st, 400)
        self.assertIn("已存在", d["error"])

    def test_bad_action_and_name_and_fps(self):
        st, _ = self._post("/api/sources", {"action": "nope", "name": "x"})
        self.assertEqual(st, 400)
        st, d = self._post("/api/sources", {"action": "add", "name": "bad;name", "uri": "rtsp://h/p"})
        self.assertEqual(st, 400)
        self.assertIn("源名", d["error"])
        st, d = self._post("/api/sources", {"action": "add", "name": "x", "uri": "rtsp://h/p", "fps": "abc"})
        self.assertEqual(st, 400)
        self.assertIn("fps", d["error"])
        st, d = self._post("/api/sources", {"action": "add", "name": "x", "uri": ""})
        self.assertEqual(st, 400)

    def test_unsafe_uri_rejected(self):
        st, d = self._post("/api/sources", {"action": "add", "name": "x", "uri": "rtsp://h/p|off"})
        self.assertEqual(st, 400)
        self.assertIn("无法序列化", d["error"])

    def test_update_and_remove(self):
        st, d = self._post("/api/sources", {"action": "update", "name": "front", "uri": "rtsp://127.0.0.1:8554/video9", "transport": "udp"})
        self.assertEqual(st, 200, d)
        env = envfile.read_env(self.env_file)
        self.assertIn("video9", env["M20AI_SOURCES"])
        self.assertIn("transport=udp", env["M20AI_SOURCES"])
        st, d = self._post("/api/sources", {"action": "update", "name": "nope", "uri": "rtsp://h/p"})
        self.assertEqual(st, 400)

    def test_cannot_remove_last_source(self):
        st, d = self._post("/api/sources", {"action": "remove", "name": "front"})
        self.assertEqual(st, 400)
        self.assertIn("至少保留一路", d["error"])

    def test_cannot_disable_the_only_enabled_source(self):
        self._post("/api/sources", {"action": "add", "name": "gate", "uri": "rtmp://h:1935/live/0"})
        st, _ = self._post("/api/sources", {"action": "disable", "name": "front"})
        self.assertEqual(st, 200)
        st, d = self._post("/api/sources", {"action": "disable", "name": "gate"})
        self.assertEqual(st, 400)
        self.assertIn("至少启用一路", d["error"])

    def test_device_source_requires_platform_opt_in(self):
        st, d = self._post("/api/sources", {"action": "add", "name": "usb0", "uri": "device:///dev/video0"})
        self.assertEqual(st, 400)
        self.assertIn("ALLOW_LOCAL_DEVICE=1", d["error"])
        # 放行后即可添加
        write_env_file(
            self.tmp, ENV_FIXTURE + "M20AI_ALLOW_LOCAL_DEVICE=1\n"
        )
        st, d = self._post("/api/sources", {"action": "add", "name": "usb0", "uri": "device:///dev/video0"})
        self.assertEqual(st, 200, d)

    def test_restart_false_skips_restart(self):
        st, d = self._post(
            "/api/sources",
            {"action": "add", "name": "gate", "uri": "rtmp://h:1935/live/0", "restart": False},
        )
        self.assertEqual(st, 200)
        self.assertIn("未重启", d["detail"])
        self.assertNotIn("已重启采集", d["detail"])

    def test_inactive_collector_never_auto_started(self):
        """ADR-010：采集未运行时改配置绝不拉起采集。"""
        with mock.patch.object(server.sysactions, "service_is_active", return_value=False):
            st, d = self._post("/api/sources", {"action": "add", "name": "gate", "uri": "rtmp://h:1935/live/0"})
        self.assertEqual(st, 200)
        self.assertIn("采集未运行", d["detail"])
        self.assertNotIn("已重启采集", d["detail"])

    # ---- discover ----
    def test_discover_bad_scope(self):
        st, d = self._post("/api/sources/discover", {"scope": "everything"})
        self.assertEqual(st, 400)
        self.assertIn("scope", d["error"])

    def test_discover_returns_candidates(self):
        canned = {
            "ok": True,
            "candidates": [
                {"name": "dev0", "uri": "device:///dev/video0", "type": "device", "verdict": "unresolved", "via": "device", "detail": "USB Camera", "cost_ms": 0},
                {"name": "live0", "uri": "rtsp://127.0.0.1:8554/live/0", "type": "rtsp", "verdict": "ok", "via": "probe", "detail": "", "cost_ms": 820},
            ],
            "notes": ["本机发现 1 个视频设备"],
            "cost_ms": 900,
            "scope": "local",
        }
        with mock.patch.object(server, "discover_sources", return_value=canned) as m:
            st, d = self._post("/api/sources/discover", {"scope": "local", "timeout_s": 2})
        self.assertEqual(st, 200)
        self.assertEqual(len(d["candidates"]), 2)
        self.assertEqual(d["candidates"][1]["uri"], "rtsp://127.0.0.1:8554/live/0")
        _args, kwargs = m.call_args
        self.assertEqual(kwargs["scope"], "local")
        self.assertEqual(kwargs["timeout"], 2.0)
        self.assertIn("base_dir", kwargs)


if __name__ == "__main__":
    unittest.main()
