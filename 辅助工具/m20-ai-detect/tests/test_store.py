import json
import os
import time
import unittest

from m20_ai_detect.config import Config
from m20_ai_detect.store import Store


def make_cfg(base_dir):
    return Config.from_env(
        {
            "M20AI_ENABLE_F": "1",
            "M20AI_SRC_F": "rtsp://127.0.0.1:8554/video1",
            "M20AI_BASE_DIR": base_dir,
            "M20AI_RING_MAX_MB": "10",
        }
    )


class TestStore(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-store-")
        self.cfg = make_cfg(self.tmp)
        self.store = Store(self.cfg)

    def test_dirs_created(self):
        for d in (
            self.store.spool_dir,
            self.store.raw_dir,
            self.store.results_dir,
            self.store.alerts_dir,
            self.store.log_dir,
            self.store.tmp_dir,
        ):
            self.assertTrue(os.path.isdir(d), d)

    def test_append_writes_valid_jsonl(self):
        self.store.append({"v": 1, "cam": "front", "n_items": 2})
        path = self.store.today_jsonl()
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            rec = json.loads(fh.read().strip())
        self.assertEqual(rec["cam"], "front")

    def test_summarize_items_keeps_only_known_keys(self):
        items = [
            {"label": "person", "class_id": 0, "score": 0.9, "box": [1, 2, 3, 4], "junk": "x"},
            {"label": "chair", "score": 0.5},
        ]
        out = self.store.summarize_items(items)
        self.assertEqual(out["n_items"], 2)
        self.assertNotIn("junk", out["items"][0])
        self.assertEqual(out["items"][1], {"label": "chair", "score": 0.5})

    def test_ring_enforce_deletes_oldest(self):
        raw = self.store.raw_for("front")
        # 造 12 个 1MB 文件，配额 10MB → 应删到 <= 10MB
        for i in range(12):
            p = os.path.join(raw, "f%02d.jpg" % i)
            with open(p, "wb") as fh:
                fh.write(b"\0" * (1024 * 1024))
            os.utime(p, (time.time() - 100 + i, time.time() - 100 + i))
        freed = self.store.enforce_ring()
        self.assertGreater(freed, 0)
        total = sum(
            os.path.getsize(os.path.join(raw, f)) for f in os.listdir(raw)
        )
        self.assertLessEqual(total, self.cfg.ring_max_bytes)
        # 最旧的应先被删
        self.assertFalse(os.path.exists(os.path.join(raw, "f00.jpg")))
        self.assertTrue(os.path.exists(os.path.join(raw, "f11.jpg")))

    def test_ring_enforce_noop_when_under_quota(self):
        raw = self.store.raw_for("front")
        with open(os.path.join(raw, "a.jpg"), "wb") as fh:
            fh.write(b"\0" * 1024)
        self.assertEqual(self.store.enforce_ring(), 0)

    def test_save_alert(self):
        jpeg = b"\xff\xd8\xff\xe0fake-jpeg"
        path = self.store.save_alert("front", "front_20261014_235000", jpeg)
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), jpeg)

    def test_stats(self):
        self.store.append({"v": 1, "cam": "front"})
        stats = self.store.stats()
        self.assertGreater(stats["results_bytes"], 0)
        self.assertTrue(all(f.endswith(".jsonl") for f in stats["results_files"]))

    def test_clear_spool_removes_jpgs_keeps_rest(self):
        """清空积压：只删 spool/ 下的 *.jpg；raw/、results/ 不动；返回 (帧数, 字节)。"""
        spool = self.store.spool_for("front")
        raw = self.store.raw_for("front")
        for i in range(3):
            with open(os.path.join(spool, "f%d.jpg" % i), "wb") as fh:
                fh.write(b"\0" * 1000)
        with open(os.path.join(spool, "note.txt"), "w") as fh:
            fh.write("keep me")
        with open(os.path.join(raw, "old.jpg"), "wb") as fh:
            fh.write(b"\0" * 500)
        self.store.append({"v": 2, "cam": "front"})

        frames, nbytes = self.store.clear_spool()
        self.assertEqual(frames, 3)
        self.assertEqual(nbytes, 3000)
        self.assertEqual([f for f in os.listdir(spool) if f.endswith(".jpg")], [])
        self.assertTrue(os.path.exists(os.path.join(spool, "note.txt")))
        self.assertTrue(os.path.exists(os.path.join(raw, "old.jpg")))
        self.assertTrue(os.path.exists(self.store.today_jsonl()))


class TestPruneResults(unittest.TestCase):
    """results/ 保留策略（M20AI_RESULTS_KEEP_DAYS，0=永不删）。"""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-prune-")
        self.cfg = make_cfg(self.tmp)
        self.store = Store(self.cfg)

    def _mk(self, name, age_days):
        path = os.path.join(self.store.results_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"v":2}\n')
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))

    def test_zero_never_deletes(self):
        self._mk("old.jsonl", 999)
        self.assertEqual(self.store.prune_results(0), 0)
        self.assertTrue(os.path.exists(os.path.join(self.store.results_dir, "old.jsonl")))

    def test_negative_never_deletes(self):
        self._mk("old.jsonl", 999)
        self.assertEqual(self.store.prune_results(-1), 0)

    def test_deletes_only_older_than_cutoff(self):
        self._mk("ancient.jsonl", 30)
        self._mk("recent.jsonl", 2)
        self._mk("today.jsonl", 0)
        self._mk("notes.txt", 30)  # 非 jsonl 不碰
        self.assertEqual(self.store.prune_results(7), 1)
        left = sorted(os.listdir(self.store.results_dir))
        self.assertEqual(left, ["notes.txt", "recent.jsonl", "today.jsonl"])

    def test_today_file_survives(self):
        """今天正在写的文件 mtime 新，任何正数保留天数都不该误删。"""
        self._mk("20240621.jsonl", 0)
        self.assertEqual(self.store.prune_results(1), 0)


class TestSavePair(unittest.TestCase):
    """ADR-006：save_pair 成对留存（jpg + 剥掉 base64 大图的 json）。"""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-savepair-")
        self.cfg = make_cfg(self.tmp)
        self.store = Store(self.cfg)

    def test_pair_written_with_reference(self):
        payload = {
            "capability": "ai-04",
            "results": {"items": [{"label": "person", "score": 0.9}]},
            "result_image": "data:image/jpeg;base64," + "A" * 50,
        }
        img_rel, json_rel = self.store.save_pair(
            "front", "front_20261015_020000", b"\xff\xd8jpg", payload
        )
        self.assertTrue(img_rel.endswith("saved/front/front_20261015_020000.jpg"))
        self.assertTrue(json_rel.endswith("saved/front/front_20261015_020000.json"))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, img_rel)))
        with open(os.path.join(self.tmp, json_rel), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertNotIn("result_image", doc)  # 大图字段必须剥掉
        self.assertEqual(doc["_result_image"], img_rel)  # 留 jpg 引用
        self.assertEqual(doc["_result_image_bytes"], len(payload["result_image"]))
        self.assertEqual(doc["results"]["items"][0]["label"], "person")

    def test_json_only_when_no_image(self):
        img_rel, json_rel = self.store.save_pair("front", "front_x", None, {"results": {"items": []}})
        self.assertIsNone(img_rel)
        self.assertIsNotNone(json_rel)
        with open(os.path.join(self.tmp, json_rel), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertNotIn("_result_image", doc)
        self.assertNotIn("_result_image_bytes", doc)

    def test_saved_bytes_in_stats(self):
        self.store.save_pair("front", "front_y", b"\xff\xd8jpg", {"results": {"items": []}})
        self.assertGreater(self.store.stats()["saved_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
