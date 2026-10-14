import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message

from m20_ai_detect.config import Config
from m20_ai_detect.detect import Detector, encode_multipart, measure_clock_offset


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self._headers = headers or {}
        self.msg = Message()
        for k, v in self._headers.items():
            self.msg[k] = v

    @property
    def headers(self):
        return self

    def get(self, key, default=None):
        return self._headers.get(key, default)

    def getheader(self, key, default=None):
        return self.get(key, default)

    def read(self, *args):
        return super().read(*args)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeHTTPError(io.BytesIO):
    def __init__(self, code, body=b'{"detail":"boom"}'):
        super().__init__(body)
        self.code = code

    def read(self, *args):
        return super().read(*args)


def make_cfg():
    return Config.from_env(
        {
            "M20AI_ENABLE_F": "1",
            "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
            "M20AI_BASE_DIR": "/tmp/m20ai-detect-test",
            "M20AI_PARAMS_JSON": '{"obj_thresh": 0.3}',
        }
    )


class TestMultipart(unittest.TestCase):
    def test_structure(self):
        boundary, body = encode_multipart(
            fields={"obj_thresh": "0.3"},
            files={"file": ("f.jpg", b"\xff\xd8\xffDATA", "image/jpeg")},
        )
        text = body.decode("utf-8", "replace")
        self.assertIn("----m20aidetect", boundary)
        self.assertIn('Content-Disposition: form-data; name="obj_thresh"', text)
        self.assertIn('Content-Disposition: form-data; name="file"; filename="f.jpg"', text)
        self.assertIn("Content-Type: image/jpeg", text)
        self.assertIn(b"\xff\xd8\xffDATA", body)
        self.assertTrue(body.endswith(b"--%s--\r\n" % boundary.encode("ascii")))

    def test_binary_safe(self):
        _b, body = encode_multipart(files={"file": ("x.jpg", bytes(range(256)), "image/jpeg")})
        self.assertIn(bytes(range(256)), body)


class TestDetector(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()
        self.detector = Detector(self.cfg)

    def _patch_urlopen(self, monkey_target):
        """替换 urllib.request.urlopen，并在测试结束后可靠还原。

        注意：必须把模块对象先取出来再传给 addCleanup——
        若写 ``setattr(mod.urllib.request.urlopen, ...)``，
        第一个参数在 cleanup 时已是**被替换后的函数**，还原会静默失败，
        进而污染同一进程内的后续测试（曾导致集成测试拿到假响应）。
        """
        import urllib.request as request_mod

        import m20_ai_detect.detect as mod

        self.assertEqual(mod.urllib.request, request_mod)  # 同一模块对象
        orig = request_mod.urlopen
        request_mod.urlopen = monkey_target
        self.addCleanup(setattr, request_mod, "urlopen", orig)

    def test_detect_success(self):
        payload = {
            "capability": "ai-04-yolov8-object-detection",
            "elapsed_ms": 65.4,
            "device": "cpu",
            "results": {"type": "detection", "items": [{"label": "chair", "score": 0.65}]},
        }

        def fake_urlopen(req, timeout=None):
            self.assertIn("/api/v1/tasks/ai-04", req.full_url)
            self.assertIn("multipart/form-data", req.headers["Content-type"])
            self.assertIn("obj_thresh", req.data.decode("utf-8", "replace"))
            return FakeResponse(json.dumps(payload).encode("utf-8"))

        self._patch_urlopen(fake_urlopen)
        res = self.detector.detect(b"\xff\xd8jpeg", "f.jpg")
        self.assertTrue(res.ok)
        self.assertEqual(res.http_status, 200)
        self.assertEqual(res.elapsed_ms, 65.4)
        self.assertEqual(res.payload["results"]["items"][0]["label"], "chair")
        self.assertGreaterEqual(res.wall_ms, 0)

    def test_detect_http_error(self):
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "ISE", None, FakeHTTPError(500))

        self._patch_urlopen(fake_urlopen)
        res = self.detector.detect(b"\xff\xd8jpeg", "f.jpg")
        self.assertFalse(res.ok)
        self.assertEqual(res.http_status, 500)
        self.assertIn("500", res.error)

    def test_detect_network_error(self):
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("Connection refused")

        self._patch_urlopen(fake_urlopen)
        res = self.detector.detect(b"\xff\xd8jpeg", "f.jpg")
        self.assertFalse(res.ok)
        self.assertIsNone(res.http_status)
        self.assertIn("URLError", res.error)

    def test_health_parses_date_header(self):
        def fake_urlopen(req, timeout=None):
            return FakeResponse(
                json.dumps({"status": "ok", "capability_count": 33, "ready_capability_count": 33}).encode(),
                headers={"Date": "Wed, 14 Oct 2026 16:00:00 GMT"},
            )

        self._patch_urlopen(fake_urlopen)
        ok, info = self.detector.health()
        self.assertTrue(ok)
        self.assertEqual(info["ready_capability_count"], 33)
        self.assertIn("2026-10-14", info["server_time"])

    def test_decode_result_image(self):
        import base64

        raw = b"\xff\xd8\xff\xe0jpegbytes"
        data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
        out = Detector.decode_result_image({"result_image": data_url})
        self.assertEqual(out, raw)
        self.assertIsNone(Detector.decode_result_image({}))
        self.assertIsNone(Detector.decode_result_image({"result_image": "not-a-data-url"}))


class TestMeasureClockOffset(unittest.TestCase):
    """measure_clock_offset：拿 AI 服务 Date 头当标准时间源（ADR-004）。"""

    class _FakeDetector:
        def __init__(self, result):
            self._result = result

        def health(self):
            return self._result

    def test_returns_offset_from_server_time(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=73100565)
        det = self._FakeDetector((True, {"server_time": future.isoformat()}))
        offset = measure_clock_offset(make_cfg(), det)
        self.assertAlmostEqual(offset, 73100565.0, delta=5)

    def test_naive_server_time_treated_as_utc(self):
        naive = (datetime.now(timezone.utc) + timedelta(seconds=3600)).replace(tzinfo=None)
        det = self._FakeDetector((True, {"server_time": naive.isoformat()}))
        self.assertAlmostEqual(measure_clock_offset(make_cfg(), det), 3600.0, delta=5)

    def test_unhealthy_returns_none(self):
        det = self._FakeDetector((False, {"error": "Connection refused"}))
        self.assertIsNone(measure_clock_offset(make_cfg(), det))

    def test_missing_server_time_returns_none(self):
        det = self._FakeDetector((True, {"status": "ok", "capability_count": 33}))
        self.assertIsNone(measure_clock_offset(make_cfg(), det))

    def test_unparsable_server_time_returns_none(self):
        det = self._FakeDetector((True, {"server_time": "not-a-time"}))
        self.assertIsNone(measure_clock_offset(make_cfg(), det))


if __name__ == "__main__":
    unittest.main()
