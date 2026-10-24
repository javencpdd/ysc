# -*- coding: utf-8 -*-
"""P3 抓拍单元测试（snapshot_writer）。

双跑约定（同 p15-unit.py）：本地 py3.13 与真机 py3.8.10 都可执行。
  * 逻辑测试（冷却/配额/磁盘红线/copy 语义/巡检）不依赖 cv2，任何环境全跑；
  * 写盘测试（命名/sidecar/UMat）需要 cv2，仅在真机计入总数。

用法：
  python3 p3-unit.py            # 本地：逻辑部分全过，cv2 部分 SKIP
  python3 p3-unit.py            # 103：全部执行
"""

import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import snapshot_writer as sw                      # noqa: E402

HAVE_CV2 = sw.cv2 is not None

PASS = 0
FAIL = 0
SKIP = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("PASS  %s = %r" % (name, got))
    else:
        FAIL += 1
        print("FAIL  %s: got %r want %r" % (name, got, want))


def check_true(name, val):
    check(name, bool(val), True)


def skip(name, why):
    global SKIP
    SKIP += 1
    print("SKIP  %s（%s）" % (name, why))


# ---------------------------------------------------------------- 测试夹具

class _Boxes(object):
    """最小 Boxes 模拟：ultralytics 的 Boxes 支持 len() 与逐框索引。"""

    def __init__(self, xyxy, conf, cls, tid):
        self.xyxy = xyxy
        self.conf = conf
        self.cls = cls
        self.id = tid

    def __len__(self):
        return len(self.xyxy)


def make_results(n=1, conf=0.87, cls=0, tid=3):
    """造一个最小 ultralytics 结果（numpy 数组即可满足 .tolist()/.item()）。"""
    try:
        import numpy as np
    except ImportError:
        return None
    boxes = _Boxes(
        xyxy=np.array([[10.0, 20.0, 110.0, 220.0]] * n),
        conf=np.array([conf] * n),
        cls=np.array([cls] * n),
        tid=np.array([tid] * n),
    )
    return [types.SimpleNamespace(boxes=boxes)]


def make_writer(tmpdir, snap=None, extra=None):
    cfg = {
        "snapshot": snap if snap is not None else {
            "enabled": True, "cooldown_ms": 0, "cooldown_ms_per_class": 0,
            "daily_quota": 500, "retention_days": 7, "min_free_gb": 0,
            "save_meta": True, "save_annotated": True,
        },
        "pic_dir": tmpdir,
        "trash_retention_days": 7,
        "detect": {"conf_threshold": 0.4},
    }
    if extra:
        cfg.update(extra)
    return sw.SnapshotWriter(cfg_getter=lambda: cfg, log=lambda m: None)


def solid(color, w=64, h=48):
    try:
        import numpy as np
    except ImportError:
        return None
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


def main():
    tmp = tempfile.mkdtemp(prefix="p3unit-")
    try:
        run_tests(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n===== P3 单元测试: PASS=%d FAIL=%d SKIP=%d =====" % (PASS, FAIL, SKIP))
    return 1 if FAIL else 0


def run_tests(tmp):
    # ---- T1 disabled ----
    w = make_writer(os.path.join(tmp, "t1"),
                    snap={"enabled": False, "cooldown_ms": 0,
                          "cooldown_ms_per_class": 0})
    r = make_results()
    if r is None:
        skip("T1 disabled", "无 numpy")
    else:
        check("T1 disabled 不入队", w.offer(solid((1, 2, 3)), r, 1, 4.0), False)
    w.close()

    # ---- T2 无检出 ----
    w = make_writer(os.path.join(tmp, "t2"))
    if r is None:
        skip("T2 无检出", "无 numpy")
    else:
        check("T2 无检出不入队",
              w.offer(solid((1, 2, 3)), [types.SimpleNamespace(boxes=None)],
                      1, 4.0), False)
    w.close()

    # ---- T3 全局冷却 AND 按类别冷却 ----
    w = make_writer(os.path.join(tmp, "t3"),
                    snap={"enabled": True, "cooldown_ms": 150,
                          "cooldown_ms_per_class": 100, "daily_quota": 500,
                          "min_free_gb": 0})
    if r is None:
        skip("T3~T6 冷却", "无 numpy")
    else:
        check("T3 首发入队", w.offer(solid((1, 2, 3)), r, 1, 4.0), True)
        check("T4 全局冷却内第二次被拒",
              w.offer(solid((9, 9, 9)), r, 2, 4.0), False)
        time.sleep(0.16)                      # 过全局冷却(150ms)，未过类别冷却？都过了
        check("T5 双冷却过后入队", w.offer(solid((9, 9, 9)), r, 3, 4.0), True)

        # 单独验证按类别冷却：全局冷却关掉
        w2 = make_writer(os.path.join(tmp, "t3b"),
                         snap={"enabled": True, "cooldown_ms": 0,
                               "cooldown_ms_per_class": 120,
                               "daily_quota": 500, "min_free_gb": 0})
        check("T6a 类别冷却内同类别被拒",
              w2.offer(solid((1, 1, 1)), make_results(cls=0), 1, 4.0), True)
        check("T6b 同类别冷却内第二次被拒",
              w2.offer(solid((2, 2, 2)), make_results(cls=0), 2, 4.0), False)
        check("T6c 不同类别不受同类别冷却约束",
              w2.offer(solid((3, 3, 3)), make_results(cls=1), 3, 4.0), True)
        w2.close()
    w.close()

    # ---- T7 入队前 copy 语义（铁律）----
    w = make_writer(os.path.join(tmp, "t7"))
    if r is None:
        skip("T7 copy 语义", "无 numpy")
    else:
        captured = []
        w._write_one = lambda frame, meta: captured.append((frame, meta))
        frame = solid((10, 20, 30))
        check("T7a 入队", w.offer(frame, r, 7, 4.0), True)
        frame[:] = (200, 100, 50)             # 模拟采集线程覆写缓冲
        deadline = time.time() + 2
        while not captured and time.time() < deadline:
            time.sleep(0.02)
        check_true("T7b 已写出", captured)
        if captured:
            buf = captured[0][0]
            check("T7c 缓冲区未被覆写（copy 生效）",
                  (int(buf[0, 0, 0]), int(buf[0, 0, 1]), int(buf[0, 0, 2])),
                  (10, 20, 30))
            check("T7d meta 带帧号", captured[0][1]["frame_no"], 7)
    w.close()

    # ---- T8 配额 ----
    w = make_writer(os.path.join(tmp, "t8"),
                    snap={"enabled": True, "cooldown_ms": 0,
                          "cooldown_ms_per_class": 0, "daily_quota": 1,
                          "min_free_gb": 0})
    if r is None:
        skip("T8 配额", "无 numpy")
    else:
        check("T8a 配额内入队", w.offer(solid((1, 2, 3)), r, 1, 4.0), True)
        check("T8b 超配额被拒", w.offer(solid((1, 2, 3)), r, 2, 4.0), False)
    w.close()

    # ---- T9 磁盘红线 ----
    w = make_writer(os.path.join(tmp, "t9"))
    if r is None:
        skip("T9 磁盘红线", "无 numpy")
    else:
        w.disk_low = True
        check("T9 disk_low 停抓拍", w.offer(solid((1, 2, 3)), r, 1, 4.0), False)
    w.close()

    # ---- T10 stats ----
    w = make_writer(os.path.join(tmp, "t10"))
    st = w.stats()
    for key in ("enabled", "today_count", "written", "dropped", "errors",
                "queue_depth", "last_save", "disk_low", "pic_dir"):
        check_true("T10 stats 含 %s" % key, key in st)
    w.close()

    # ---- T11~T13 写盘（需要 cv2）----
    if not HAVE_CV2:
        skip("T11 命名与 sidecar", "无 cv2")
        skip("T12 conf/id 编码", "无 cv2")
        skip("T13 UMat 入队", "无 cv2")
    elif r is None:
        skip("T11 命名与 sidecar", "无 numpy")
        skip("T12 conf/id 编码", "无 numpy")
        skip("T13 UMat 入队", "无 numpy")
    else:
        day = os.path.join(tmp, "t11",
                           datetime.date.today().strftime("%Y%m%d"))
        w = make_writer(os.path.join(tmp, "t11"),
                        snap={"enabled": True, "cooldown_ms": 0,
                              "cooldown_ms_per_class": 0, "daily_quota": 500,
                              "min_free_gb": 0, "save_meta": True})
        check("T11a 入队", w.offer(solid((30, 60, 90)),
                                   make_results(conf=0.87, tid=3), 11, 4.2),
              True)
        deadline = time.time() + 3
        while w.stats()["written"] < 1 and time.time() < deadline:
            time.sleep(0.02)
        check("T11b 已写盘", w.stats()["written"] >= 1, True)
        names = [n for n in os.listdir(day) if n.endswith(".jpg")]
        check("T11c 命名合规",
              bool(names) and bool(
                  re.match(sw.NAME_RE, names[0])), True)
        if names:
            # c 段 = 置信度千分位（§5.4）：0.87 → 870
            check("T11d conf 千分位 c870", "_c870_" in names[0], True)
            check("T11e id 编码 id003", names[0].endswith("_id003.jpg"), True)
            meta_path = os.path.join(day, names[0][:-4] + ".json")
            check_true("T11f sidecar 存在", os.path.isfile(meta_path))
            if os.path.isfile(meta_path):
                with open(meta_path) as fh:
                    meta = json.load(fh)
                check("T11g sidecar 字段",
                      sorted(meta.keys()),
                      sorted(["name", "ts", "ts_ms", "frame_no", "infer_ms",
                              "conf_threshold", "max_conf", "classes",
                              "boxes", "annotated", "image_wh"]))
                check("T11h sidecar classes", meta["classes"], [0])
                check("T11i sidecar 框数", len(meta["boxes"]), 1)
        # T12 多框 + 非零 id 编码
        w.offer(solid((1, 2, 3)), make_results(n=2, conf=0.55, cls=1, tid=42),
                12, 5.0)
        deadline = time.time() + 3
        while w.stats()["written"] < 2 and time.time() < deadline:
            time.sleep(0.02)
        names = sorted(n for n in os.listdir(day) if n.endswith(".jpg"))
        if len(names) >= 2:
            check("T12 conf 0.55 → c550", "_c550_" in names[-1], True)
            check("T12 id 42 → id042", names[-1].endswith("_id042.jpg"), True)
        else:
            check("T12 第二张已写盘", False, True)
        # T13 UMat
        umat = sw.cv2.UMat(solid((7, 7, 7)))
        check("T13a UMat 入队", w.offer(umat, make_results(conf=0.6), 13, 4.0),
              True)
        deadline = time.time() + 3
        while w.stats()["written"] < 3 and time.time() < deadline:
            time.sleep(0.02)
        check("T13b UMat 已写盘", w.stats()["written"] >= 3, True)
        w.close()

    # ---- T14 巡检：保留期 + 回收站 ----
    base = os.path.join(tmp, "t14")
    w = make_writer(base, extra={"trash_retention_days": 7})
    old = datetime.date.today() - datetime.timedelta(days=30)
    fresh = datetime.date.today().strftime("%Y%m%d")
    old_dir = os.path.join(base, old.strftime("%Y%m%d"))
    os.makedirs(old_dir, exist_ok=True)
    with open(os.path.join(old_dir, "x.jpg"), "wb") as fh:
        fh.write(b"x")
    old_trash = os.path.join(base, ".trash", old.strftime("%Y%m%d"))
    os.makedirs(old_trash, exist_ok=True)
    with open(os.path.join(old_trash, "y.jpg"), "wb") as fh:
        fh.write(b"y")
    os.makedirs(os.path.join(base, fresh), exist_ok=True)
    w._maintain()
    check("T14a 超期日期目录已清", os.path.isdir(old_dir), False)
    check("T14b 超期回收站已清", os.path.isdir(old_trash), False)
    check("T14c 当天目录保留", os.path.isdir(os.path.join(base, fresh)), True)
    w.close()

    # ---- T15 close 退出 ----
    w = make_writer(os.path.join(tmp, "t15"))
    w.close(timeout=2)
    check("T15 消费线程已退出", w._thread.is_alive(), False)

    # ---- T16 默认 pic_dir 相对 src/（与 console 同约定）----
    # 回归：2026-10-22 部署实测发现 worker 曾按「项目根」解析 ../pic
    # （写 /home/test/pic），而 console 按 src/ 解析（读 /home/test/yolo8/pic），
    # 浏览侧永远看不到抓拍。两侧必须同为「相对 src/」。
    default_expect = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(sw.__file__)), "..", "pic"))
    cfg16 = {"snapshot": {"enabled": True}, "pic_dir": ""}   # 空 → 走默认 ../pic
    w16 = sw.SnapshotWriter(cfg_getter=lambda: cfg16, log=lambda m: None)
    check("T16 默认 pic_dir 相对 src/", w16._pic_dir, default_expect)
    w16.close(timeout=2)
    # 绝对路径原样透传（不拼 base）
    abs16 = os.path.join(tmp, "t16-abs")
    cfg16b = {"snapshot": {"enabled": True}, "pic_dir": abs16}
    w16b = sw.SnapshotWriter(cfg_getter=lambda: cfg16b, log=lambda m: None)
    check("T16b 绝对 pic_dir 原样", w16b._pic_dir, abs16)
    w16b.close(timeout=2)
    # 测试副作用清理（默认路径被 makedirs 建出来了；空则删掉，非空说明有别的东西不动）
    for d in (default_expect, abs16):
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
