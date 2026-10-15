"""端到端集成测试：起一个本地假 AI 服务，跑真实的 HTTP + multipart + 落库链路。

不依赖外网、不依赖 ffmpeg，可在任何开发机上 ``python -m unittest`` 直接跑。
"""
import json
import os
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from m20_ai_detect.config import Config
from m20_ai_detect.detect import Detector
from m20_ai_detect.sampler import Sampler
from m20_ai_detect.store import Store


class FakeAIHandler(BaseHTTPRequestHandler):
    """模拟 /api/v1/health 与 /api/v1/tasks/{cap}。"""

    received = {}

    def log_message(self, *args):  # 静音
        pass

    def _json(self, obj, status=200, headers=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/v1/health"):
            self._json(
                {
                    "status": "ok",
                    "capability_count": 33,
                    "ready_capability_count": 33,
                    "default_device": "cpu",
                    "loaded_models": ["yolov8n.onnx"],
                },
                headers={"Date": "Wed, 14 Oct 2026 16:00:00 GMT"},
            )
        else:
            self._json({"detail": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype or not self.path.startswith("/api/v1/tasks/"):
            self._json({"detail": "bad request"}, status=400)
            return
        boundary = ctype.split("boundary=", 1)[1].strip()
        parts = body.split(("--" + boundary).encode())
        file_part = [p for p in parts if b'name="file"' in p]
        FakeAIHandler.received["file_parts"] = len(file_part)
        if file_part:
            head, _, payload = file_part[0].partition(b"\r\n\r\n")
            FakeAIHandler.received["filename"] = ""
            for line in head.split(b"\r\n"):
                if b"filename=" in line:
                    FakeAIHandler.received["filename"] = line.split(b"filename=", 1)[1].strip(b'"').decode()
            FakeAIHandler.received["bytes"] = len(payload.rstrip(b"\r\n"))
            FakeAIHandler.received["magic"] = payload[:4]
        FakeAIHandler.received["params_obj_thresh"] = b'name="obj_thresh"' in body
        self._json(
            {
                "capability": self.path.rsplit("/", 1)[-1],
                "title": "fake",
                "model": "yolov8n.onnx",
                "device": "cpu",
                "provider": "CPUExecutionProvider",
                "elapsed_ms": 42.0,
                "input": {"type": "image", "width": 800, "height": 600},
                "params": {"obj_thresh": 0.3},
                "results": {
                    "type": "detection",
                    "items": [
                        {"label": "person", "class_id": 0, "score": 0.91, "box": [1, 2, 3, 4]},
                        {"label": "chair", "class_id": 56, "score": 0.55, "box": [5, 6, 7, 8]},
                    ],
                },
                "result_image": "data:image/jpeg;base64,QUJD",
                "detail": {},
            }
        )


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAIHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _cfg(self, base_dir):
        return Config.from_env(
            {
                "M20AI_AI_BASE": "http://127.0.0.1:%d" % self.port,
                "M20AI_CAP_ID": "ai-04-yolov8-object-detection",
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": base_dir,
                "M20AI_PARAMS_JSON": '{"obj_thresh": 0.3}',
                "M20AI_FRESH_AGE_SEC": "0",
                "M20AI_ALERT_LABELS": "person",
                "M20AI_ALERT_SCORE": "0.6",
            }
        )

    def test_detector_against_fake_server(self):
        import tempfile

        cfg = self._cfg(tempfile.mkdtemp(prefix="m20ai-e2e-"))
        detector = Detector(cfg)
        res = detector.detect(b"\xff\xd8\xff\xe0fake-jpeg-bytes", "20261014_235000.jpg")
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.http_status, 200)
        self.assertEqual(res.elapsed_ms, 42.0)
        items = res.payload["results"]["items"]
        self.assertEqual(len(items), 2)
        # 服务端应真的收到了 multipart 文件字段与参数
        self.assertEqual(FakeAIHandler.received["file_parts"], 1)
        self.assertEqual(FakeAIHandler.received["filename"], "20261014_235000.jpg")
        self.assertEqual(FakeAIHandler.received["magic"], b"\xff\xd8\xff\xe0")
        self.assertTrue(FakeAIHandler.received["params_obj_thresh"])

    def test_health_and_clock(self):
        import tempfile
        from datetime import datetime, timezone

        cfg = self._cfg(tempfile.mkdtemp(prefix="m20ai-e2e-"))
        ok, info = Detector(cfg).health()
        self.assertTrue(ok)
        self.assertEqual(info["ready_capability_count"], 33)
        # server_time 取响应 Date 头：http.server 会自动生成"当前时间"，
        # 盖过 handler 里手工设的 Date —— 用"接近当前 UTC 时刻"判断，避免跨日失效。
        got = datetime.fromisoformat(info["server_time"])
        self.assertLess(abs((datetime.now(timezone.utc) - got).total_seconds()), 2 * 86400)

    def test_full_pipeline_without_ffmpeg(self):
        """直接往 spool 写帧，跑 _process_camera：验证 HTTP→JSONL→raw 全链路。"""
        import tempfile

        base = tempfile.mkdtemp(prefix="m20ai-e2e-")
        cfg = self._cfg(base)
        store = Store(cfg)
        sampler = Sampler(cfg, store, log=lambda m: None, hostname="e2ehost")
        spool = store.spool_for("front")
        for i, name in enumerate(["20261014_235000.jpg", "20261014_235001.jpg"]):
            with open(os.path.join(spool, name), "wb") as fh:
                fh.write(b"\xff\xd8\xff\xe0" + bytes([i]) * 200)

        self.assertTrue(sampler._process_camera(cfg.cameras[0]))

        with open(store.today_jsonl(), encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["n_items"], 2)
        self.assertEqual(records[0]["items"][0]["label"], "person")
        self.assertEqual(records[0]["elapsed_ms"], 42.0)
        self.assertTrue(records[0]["alert"])  # person 0.91 ≥ 0.6
        self.assertFalse(records[0]["result_image_saved"])  # SAVE_RESULT_IMAGE 默认关
        # 帧应已移入 raw/
        self.assertEqual(os.listdir(spool), [])
        self.assertEqual(len(os.listdir(store.raw_for("front"))), 2)

    def test_pipeline_survives_server_down(self):
        """服务端不可用时：帧留在 spool，写 detect_fail，不抛异常。"""
        import tempfile

        base = tempfile.mkdtemp(prefix="m20ai-e2e-")
        cfg = Config.from_env(
            {
                "M20AI_AI_BASE": "http://127.0.0.1:1",  # 必然连不上
                "M20AI_ENABLE_F": "1",
                "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
                "M20AI_BASE_DIR": base,
                "M20AI_FRESH_AGE_SEC": "0",
                "M20AI_TIMEOUT": "1",
                "M20AI_RETRY_BASE": "0",
                "M20AI_RETRY_MAX": "0",
            }
        )
        store = Store(cfg)
        sampler = Sampler(cfg, store, log=lambda m: None)
        spool = store.spool_for("front")
        frame = os.path.join(spool, "20261014_235000.jpg")
        with open(frame, "wb") as fh:
            fh.write(b"\xff\xd8\xff\xe0")

        self.assertFalse(sampler._process_camera(cfg.cameras[0]))
        self.assertTrue(os.path.exists(frame), "失败时帧必须保留待重试")
        with open(store.today_jsonl(), encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]
        self.assertEqual(records[0]["event"], "detect_fail")


if __name__ == "__main__":
    unittest.main()
