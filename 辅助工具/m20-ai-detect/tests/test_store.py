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


class TestPurge(unittest.TestCase):
    """Store.purge（ADR-011）：整体清空所选类别，只删对应扩展名，其它文件不碰。"""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-purge-")
        self.cfg = make_cfg(self.tmp)
        self.store = Store(self.cfg)
        # saved：一对 jpg+json（含 console 子目录）
        for cam in ("front", "console"):
            d = self.store.saved_for(cam)
            with open(os.path.join(d, "a.jpg"), "wb") as fh:
                fh.write(b"\0" * 128)
            with open(os.path.join(d, "a.json"), "w", encoding="utf-8") as fh:
                fh.write("{}")
        # raw / spool：各一帧
        with open(os.path.join(self.store.raw_for("front"), "r.jpg"), "wb") as fh:
            fh.write(b"\0" * 64)
        with open(os.path.join(self.store.spool_for("front"), "s.jpg"), "wb") as fh:
            fh.write(b"\0" * 32)
        # results：两个 jsonl + 一个不该被删的 txt
        with open(os.path.join(self.store.results_dir, "20240621.jsonl"), "w") as fh:
            fh.write("{}\n")
        with open(os.path.join(self.store.results_dir, "20261016.jsonl"), "w") as fh:
            fh.write("{}\n")
        with open(os.path.join(self.store.results_dir, "notes.txt"), "w") as fh:
            fh.write("keep")

    def _ls(self, d):
        return sorted(os.listdir(d))

    def test_purge_saved_removes_pairs_including_console(self):
        stats = self.store.purge(["saved"])
        files, nbytes = stats["saved"]
        self.assertEqual(files, 4)  # 2 相机 × (jpg+json)
        self.assertEqual(nbytes, 260)
        self.assertEqual(self._ls(self.store.saved_for("front")), [])
        self.assertEqual(self._ls(self.store.saved_for("console")), [])
        # 其它目录不动
        self.assertTrue(os.path.exists(os.path.join(self.store.raw_dir, "front", "r.jpg")))

    def test_purge_results_only_jsonl(self):
        stats = self.store.purge(["results"])
        self.assertEqual(stats["results"][0], 2)
        self.assertTrue(os.path.exists(os.path.join(self.store.results_dir, "notes.txt")))
        self.assertEqual(
            [f for f in self._ls(self.store.results_dir) if f.endswith(".jsonl")], []
        )

    def test_purge_multi_dedup_and_sizes(self):
        stats = self.store.purge(["raw", "spool", "raw"])  # 重复项去重
        self.assertEqual(stats["raw"], (1, 64))
        self.assertEqual(stats["spool"], (1, 32))
        self.assertEqual(len(stats), 2)
        self.assertEqual(self._ls(self.store.raw_for("front")), [])
        self.assertEqual(self._ls(self.store.spool_for("front")), [])

    def test_purge_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            self.store.purge(["saved", "etc"])

    def test_purge_empty_list_is_noop(self):
        self.assertEqual(self.store.purge([]), {})
        self.assertEqual(len(self._ls(self.store.saved_for("front"))), 2)


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

    def test_meta_embedded_and_empty_skipped(self):
        """ADR-008：meta 里非空字段写进 json（_saved_at/_alert），空值省略。"""
        img_rel, json_rel = self.store.save_pair(
            "front",
            "front_z",
            b"\xff\xd8jpg",
            {"results": {"items": []}},
            meta={"_saved_at": "2026-10-15T14:00:00.000", "_alert": None},
        )
        with open(os.path.join(self.tmp, json_rel), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["_saved_at"], "2026-10-15T14:00:00.000")
        self.assertNotIn("_alert", doc)  # None 不落


class TestCleanSaved(unittest.TestCase):
    """ADR-008：saved/ 留存清理（按年龄 + 总量上限，成对删 .jpg/.json）。"""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="m20ai-clean-")
        self.cfg = make_cfg(self.tmp)
        self.store = Store(self.cfg)

    def _mk(self, cam, stem, size=1000, age_sec=0.0, pair=True):
        d = self.store.saved_for(cam)
        p = os.path.join(d, stem + ".jpg")
        with open(p, "wb") as fh:
            fh.write(b"\0" * size)
        js = os.path.join(d, stem + ".json")
        if pair:
            with open(js, "w", encoding="utf-8") as fh:
                fh.write("{}")
        if age_sec:
            old = time.time() - age_sec
            os.utime(p, (old, old))
            if pair:
                os.utime(js, (old, old))
        return p

    def test_zero_is_noop(self):
        self._mk("front", "a", age_sec=99 * 86400)
        self.assertEqual(self.store.clean_saved(0, 0.0), (0, 0))
        self.assertTrue(
            os.path.exists(os.path.join(self.store.saved_for("front"), "a.jpg"))
        )

    def test_age_deletes_pairs_only(self):
        self._mk("front", "old", size=1000, age_sec=10 * 86400)
        self._mk("front", "new", size=1000, age_sec=3600)
        pairs, freed = self.store.clean_saved(0, 1.0)
        self.assertEqual(pairs, 1)
        self.assertEqual(freed, 1000 + 2)  # jpg + json({"}"} 2 字节)
        d = self.store.saved_for("front")
        self.assertFalse(os.path.exists(os.path.join(d, "old.jpg")))
        self.assertFalse(os.path.exists(os.path.join(d, "old.json")))
        self.assertTrue(os.path.exists(os.path.join(d, "new.jpg")))
        self.assertTrue(os.path.exists(os.path.join(d, "new.json")))

    def test_size_deletes_oldest_first(self):
        # 4 对 × (1000B jpg + 2B json) = 4008B；上限 2500B → 删最旧 2 对后 2004B
        for i, age_h in enumerate((4.0, 3.0, 2.0, 1.0)):
            self._mk("front", "s%d" % i, age_sec=age_h * 3600)
        pairs, freed = self.store.clean_saved(2500, 0.0)
        self.assertEqual(pairs, 2)
        self.assertEqual(freed, 2 * 1002)
        d = self.store.saved_for("front")
        self.assertFalse(os.path.exists(os.path.join(d, "s0.jpg")))  # 最旧先删
        self.assertFalse(os.path.exists(os.path.join(d, "s1.jpg")))
        self.assertTrue(os.path.exists(os.path.join(d, "s2.jpg")))
        self.assertTrue(os.path.exists(os.path.join(d, "s3.jpg")))

    def test_size_exact_limit_keeps_all(self):
        """总量恰好等于上限时不删（条件是 > max）。"""
        for i in range(2):
            self._mk("front", "e%d" % i, age_sec=(2 - i) * 3600)
        self.assertEqual(self.store.clean_saved(2 * 1002, 0.0), (0, 0))

    def test_multiple_cams_and_orphan_json(self):
        self._mk("front", "f0", age_sec=10 * 86400)
        self._mk("back", "b0", age_sec=10 * 86400)
        d = self.store.saved_for("front")
        with open(os.path.join(d, "orphan.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")  # 只有 json 没有 jpg 的孤儿文件
        old = time.time() - 10 * 86400
        os.utime(os.path.join(d, "orphan.json"), (old, old))
        pairs, _freed = self.store.clean_saved(0, 1.0)
        self.assertEqual(pairs, 3)  # front 一对 + back 一对 + 孤儿 json
        self.assertEqual(
            [f for f in os.listdir(d) if f.endswith((".jpg", ".json"))], []
        )

    def test_other_dirs_untouched(self):
        """只删 saved/；raw/、results/、alerts/ 不动。"""
        self._mk("front", "x", age_sec=10 * 86400)
        raw = self.store.raw_for("front")
        with open(os.path.join(raw, "r.jpg"), "wb") as fh:
            fh.write(b"\0" * 1000)
        self.store.append({"v": 2})
        self.store.save_alert("front", "al", b"jpeg")
        self.store.clean_saved(0, 1.0)
        self.assertTrue(os.path.exists(os.path.join(raw, "r.jpg")))
        self.assertTrue(os.path.exists(self.store.today_jsonl()))
        self.assertTrue(
            os.path.exists(os.path.join(self.store.alerts_dir, "front", "al.jpg"))
        )


if __name__ == "__main__":
    unittest.main()
