"""相机画面单帧快照（ADR-012）：命令构建 + 来源优先级 + 缓存 + 失败兜底。"""
import base64
import os
import tempfile
import time
import unittest

from m20_ai_detect import snapshot
from m20_ai_detect.capture import build_snapshot_cmd
from m20_ai_detect.config import Camera, Config


def _jpeg(size=2048, fill=b"x"):
    return b"\xff\xd8" + fill * size + b"\xff\xd9"


class TestSnapshotCmd(unittest.TestCase):
    """单次抓拍命令：协议参数与抽帧一致，但单帧输出到 stdout、不落盘。"""

    def _cmd(self, src):
        cam = Camera("front", src)
        return build_snapshot_cmd(cam, Config(cameras=[cam]))

    def test_rtsp_tcp_and_single_frame_to_stdout(self):
        cmd = self._cmd("rtsp://10.21.31.103:8554/video1")
        self.assertEqual(cmd[cmd.index("-rtsp_transport") + 1], "tcp")
        self.assertEqual(cmd[cmd.index("-frames:v") + 1], "1")
        self.assertEqual(cmd[-1], "pipe:1")
        self.assertIn("image2pipe", cmd)
        # 与常驻抽帧不同：不做 fps 过滤、不落盘（无 image2 / -vf / -strftime）
        self.assertNotIn("-vf", cmd)
        self.assertNotIn("image2", cmd)
        self.assertNotIn("-strftime", cmd)

    def test_rtmp_declares_flv(self):
        cmd = self._cmd("rtmp://1.2.3.4/live/1")
        self.assertEqual(cmd[cmd.index("-f") + 1], "flv")

    def test_forbidden_token_rejected(self):
        with self.assertRaises(RuntimeError):
            self._cmd("rtsp://h/v4l2src")


class TestSnapshotFrame(unittest.TestCase):
    """来源优先级：新鲜环形帧 > 即时抓帧 > 过期环形帧；失败不抛异常。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        self.cfg = Config(
            base_dir=self.base,
            cameras=[Camera("front", "rtsp://10.21.31.103:8554/video1")],
            fps=1.0,
        )
        snapshot._cache.clear()

    def tearDown(self):
        self.tmp.cleanup()
        snapshot._cache.clear()

    def _put_raw(self, age_s, name="front_20261016_000001.jpg", data=None):
        d = os.path.join(self.base, "raw", "front")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as fh:
            fh.write(data if data is not None else _jpeg())
        t = time.time() - age_s
        os.utime(p, (t, t))
        return p

    # ---- 来源优先级 ----

    def test_fresh_ring_preferred_without_grab(self):
        self._put_raw(0.5)
        calls = []

        def grab(c, g):
            calls.append(1)
            return _jpeg()

        out = snapshot.snapshot_frame(self.cfg, grabber=grab)
        self.assertTrue(out["ok"])
        self.assertEqual(out["cam"], "front")
        self.assertEqual(out["source"], "ring")
        self.assertLess(out["age_s"], 5)
        self.assertEqual(out["frame"], "front_20261016_000001.jpg")
        self.assertTrue(out["image"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(base64.b64decode(out["image"].split(",", 1)[1]).startswith(b"\xff\xd8"))
        self.assertEqual(calls, [])  # 新鲜环形帧不应触发抓帧

    def test_stale_ring_falls_back_to_live_and_caches(self):
        self._put_raw(120)
        calls = []

        def grab(c, g):
            calls.append(1)
            return _jpeg()

        out = snapshot.snapshot_frame(self.cfg, grabber=grab)
        self.assertEqual(out["source"], "live")
        self.assertIsNone(out["frame"])
        self.assertEqual(len(calls), 1)
        out2 = snapshot.snapshot_frame(self.cfg, grabber=grab)
        self.assertEqual(out2["source"], "live")
        self.assertEqual(len(calls), 1)  # 缓存命中，不重复抓帧

    def test_cache_timestamps_at_grab_completion(self):
        """抓帧耗时（~2-4s）不允许吃掉缓存 TTL：时间戳按**完成时刻**计。"""
        self._put_raw(120)
        calls = []
        t = [0.0]

        def grab(c, g):
            calls.append(1)
            t[0] += 10.0  # 模拟一次很慢的握手
            return _jpeg()

        clock = lambda: t[0]
        out = snapshot.snapshot_frame(self.cfg, grabber=grab, now=clock)
        self.assertEqual(out["source"], "live")
        # 完成后立即再请求：开始时刻距 now 已 10s，但缓存戳=完成时刻 → 应命中
        out2 = snapshot.snapshot_frame(self.cfg, grabber=grab, now=clock)
        self.assertEqual(out2["source"], "live")
        self.assertEqual(len(calls), 1)

    def test_grab_fail_falls_back_to_stale_ring(self):
        self._put_raw(120)
        out = snapshot.snapshot_frame(self.cfg, grabber=lambda c, g: None)
        self.assertTrue(out["ok"])
        self.assertEqual(out["source"], "stale")
        self.assertGreaterEqual(out["age_s"], 100)

    def test_grab_fail_without_ring_is_error(self):
        out = snapshot.snapshot_frame(self.cfg, grabber=lambda c, g: None)
        self.assertFalse(out["ok"])
        self.assertIn("抓帧失败", out["error"])
        self.assertFalse(out.get("bad_request"))
        self.assertEqual(out["code"], "grab_failed")
        self.assertEqual(out["src"], "rtsp://10.21.31.103:8554/video1")

    # ---- 参数校验 ----

    def test_unknown_cam_is_bad_request(self):
        out = snapshot.snapshot_frame(self.cfg, cam_name="nope")
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("bad_request"))
        self.assertIn("可用", out["error"])
        # webconsole 靠 code 做中英映射（ADR-013）
        self.assertEqual(out["code"], "unknown_cam")
        self.assertEqual(out["cam"], "nope")
        self.assertEqual(out["cams"], ["front"])

    def test_no_cameras_is_bad_request(self):
        out = snapshot.snapshot_frame(Config(base_dir=self.base))
        self.assertFalse(out["ok"])
        self.assertTrue(out.get("bad_request"))
        self.assertEqual(out["code"], "no_cameras")

    def test_default_cam_is_first(self):
        self._put_raw(0.5)
        out = snapshot.snapshot_frame(self.cfg)  # 不指定 cam → 第一个启用相机
        self.assertTrue(out["ok"])
        self.assertEqual(out["cam"], "front")

    # ---- 新鲜窗口随 fps 缩放 ----

    def test_fresh_window_scales_with_fps(self):
        self.assertEqual(snapshot._fresh_window(Config(fps=1.0)), 5.0)
        self.assertEqual(snapshot._fresh_window(Config(fps=0.2)), 20.0)
        self.assertEqual(snapshot._fresh_window(Config(fps=5.0)), 5.0)


if __name__ == "__main__":
    unittest.main()
