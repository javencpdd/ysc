# -*- coding: utf-8 -*-
"""P3 console 侧 PicStore 单元测试（server.py 的 §5.5/§5.5.1 实现）。

本地 py3.13 与真机 py3.8.10 双跑（cv2 相关用例仅在可用时执行）。
用法：python3 p3-pics-unit.py
"""

import datetime
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import server                                     # noqa: E402

HAVE_CV2 = server.cv2 is not None
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


def make_pic(day_dir, name, conf=87, tid=3, size_body=b"x"):
    os.makedirs(day_dir, exist_ok=True)
    path = os.path.join(day_dir, name)
    with open(path, "wb") as fh:
        fh.write(size_body)
    # sidecar（主类别 0）
    with open(path[:-4] + ".json", "w") as fh:
        json.dump({"name": name, "classes": [0], "boxes": []}, fh)
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="p3pics-")
    try:
        run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n===== P3 console 单测: PASS=%d FAIL=%d SKIP=%d ====="
          % (PASS, FAIL, SKIP))
    return 1 if FAIL else 0


def run(tmp):
    # ---- parse_pic_name ----
    p = server.parse_pic_name("20261022T071945_123_c870_id003.jpg")
    check_true("P1 合法文件名可解析", p is not None)
    if p:
        ts_ms, conf, tid = p
        dt = datetime.datetime.fromtimestamp(ts_ms / 1000.0)
        check("P2 解析出本地时间",
              (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
               dt.microsecond // 1000),
              (2026, 10, 22, 7, 19, 45, 123))
        check("P3 conf 还原", round(conf, 3), 0.87)
        check("P4 tid 还原", tid, 3)
    check("P5 坏名返回 None",
          server.parse_pic_name("../../etc/passwd"), None)
    check("P6 非抓拍名返回 None",
          server.parse_pic_name("photo.jpg"), None)

    # ---- 目录与索引 ----
    today = datetime.date.today().strftime("%Y%m%d")
    store = server.PicStore(dir_getter=lambda: tmp)
    check("P7 空目录 dates", store.dates(), [])

    day_dir = os.path.join(tmp, today)
    make_pic(day_dir, "%sT010000_000_c500_id001.jpg" % today)
    make_pic(day_dir, "%sT020000_000_c900_id002.jpg" % today)
    make_pic(day_dir, "%sT030000_000_c100_id003.jpg" % today)
    # 不合规文件应被忽略
    with open(os.path.join(day_dir, "notes.txt"), "w") as fh:
        fh.write("hi")

    check("P8 dates 倒序", store.dates(), [today])
    tl = store.timeline(today)
    check("P9 timeline 存在", tl["exists"], True)
    check("P10 timeline 条数", tl["count"], 3)
    check("P11 timeline 升序",
          [it["name"][9:11] for it in tl["items"]], ["01", "02", "03"])
    check("P12 cls 来自 sidecar", tl["items"][0]["cls"], 0)
    check("P13 conf 字段", tl["items"][1]["conf"], 0.9)
    lst = store.list_pics(today, 1, 2)
    check("P14 分页总数", lst["total"], 3)
    check("P15 分页首页 2 条倒序",
          [it["name"][9:11] for it in lst["items"]], ["03", "02"])
    lst2 = store.list_pics(today, 2, 2)
    check("P16 分页第二页", [it["name"][9:11] for it in lst2["items"]], ["01"])
    check("P17 不存在的日期", store.timeline("20200101")["exists"], False)

    # ---- resolve 安全 ----
    name = "%sT010000_000_c500_id001.jpg" % today
    check_true("P18 resolve 正常路径", store.resolve(today, name) is not None)
    check("P19 穿越名被拒", store.resolve(today, "../../etc/passwd"), None)
    check("P20 日期与文件名不匹配被拒", store.resolve("20200101", name), None)
    check("P21 非抓拍名被拒", store.resolve(today, "photo.jpg"), None)
    check("P22 不存在图被拒",
          store.resolve(today, "%sT999999_999_c999_id999.jpg" % today), None)

    # ---- 缓存：目录 mtime 变化即失效 ----
    tl2 = store.timeline(today)
    check("P23 命中缓存（同对象）", tl2["items"] is tl["items"], True)
    make_pic(day_dir, "%sT040000_000_c600_id004.jpg" % today)
    tl3 = store.timeline(today)
    check("P24 新文件后缓存失效", tl3["count"], 4)

    # P24b 回归（实测坑）：某些文件系统（本机 Windows）在「紧接着的连续
    # 创建」时合并不刷新目录 mtime（28/30 复现）⇒ 只靠 mtime 会把刚写入
    # 的抓拍漏掉。先写文件、再把缓存 mtime 抹成写入后的当前值——mtime 键
    # 必然相等，此时只有 names 兜底能发现新文件（全平台确定性复现）。
    make_pic(day_dir, "%sT050000_000_c700_id005.jpg" % today)
    with store._lock:
        entry = store._cache[today]
        store._cache[today] = (os.stat(day_dir).st_mtime, entry[1], entry[2])
    tl4 = store.timeline(today)
    check("P24b mtime 键相等时 names 兜底", tl4["count"], 5)

    # ---- 缩略图 ----
    if not HAVE_CV2:
        skip("P25 缩略图生成", "无 cv2")
        skip("P26 缩略图缓存复用", "无 cv2")
    else:
        import numpy as np
        src = os.path.join(day_dir, name)
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        img[:] = (30, 60, 90)
        import cv2
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        with open(src, "wb") as fh:
            fh.write(buf.tobytes())
        # sidecar 也要存在（make_pic 已写，但这里覆盖了 jpg，sidecar 仍在）
        thumb = store.ensure_thumb(today, name)
        check_true("P25 缩略图已生成", thumb is not None)
        if thumb:
            check_true("P26 缩略图落在 .thumbs/",
                       thumb.startswith(os.path.join(tmp, ".thumbs")))
            back = cv2.imread(thumb)
            check("P27 缩略图宽 320", back.shape[1], 320)
            thumb2 = store.ensure_thumb(today, name)
            check("P28 二次请求复用缓存（同路径）", thumb2, thumb)
        # 坏图：非 JPEG 内容 → imread 失败 → 回退 None
        bad_dir = os.path.join(tmp, "20200101")
        make_pic(bad_dir, "20200101T010000_000_c500_id001.jpg", size_body=b"notjpg")
        check("P29 坏图缩略图返回 None",
              store.ensure_thumb("20200101",
                                 "20200101T010000_000_c500_id001.jpg"), None)

    # ---- 软删除 / 还原 ----
    victim = "%sT020000_000_c900_id002.jpg" % today
    res = store.trash(today, victim)
    check_true("P30 软删除成功", isinstance(res, str) and res != "exists")
    check("P31 原目录已无该文件",
          os.path.isfile(os.path.join(day_dir, victim)), False)
    check_true("P32 回收站有该文件",
               os.path.isfile(os.path.join(tmp, ".trash", today, victim)))
    items = store.trash_list()
    check("P33 回收站清单 1 条", len(items), 1)
    check("P34 回收站条目字段",
          sorted(items[0].keys()), ["date", "name", "size", "ts_ms"])
    check("P35 timeline 删除后即时生效", store.timeline(today)["count"], 4)
    # 重复删除（文件已不在原目录）→ None（路由层转 404）
    check("P36 已删除文件再删返回 None", store.trash(today, victim), None)
    # 预置同名文件进回收站 → exists（防覆盖）
    victim_b = "%sT030000_000_c100_id003.jpg" % today
    make_pic(os.path.join(tmp, ".trash", today), victim_b, size_body=b"old")
    check("P36b 回收站同名占位 → exists",
          store.trash(today, victim_b), "exists")
    # 还原
    res2 = store.restore(victim)
    check_true("P37 还原成功", isinstance(res2, str) and res2 != "exists")
    check_true("P38 原目录恢复",
               os.path.isfile(os.path.join(day_dir, victim)))
    check("P39 还原后 timeline", store.timeline(today)["count"], 5)
    # 还原不存在 → None
    check("P40 还原不存在项", store.restore("20200101T010000_000_c500_id001.jpg"),
          None)
    # 穿越还原名 → None
    check("P41 穿越还原名被拒", store.restore("../../etc/passwd"), None)

    # ---- 抽稀 ----
    many_dir = os.path.join(tmp, "20261231")
    for i in range(server.TIMELINE_MAX_ITEMS + 10):
        hh = i // 3600
        mm = (i % 3600) // 60
        ss = i % 60
        make_pic(many_dir, "20261231T%02d%02d%02d_000_c500_id%03d.jpg"
                 % (hh, mm, ss, i % 1000), size_body=b"")
    tl_many = store.timeline("20261231")
    check("P42 抽稀标记", tl_many["sampled"], True)
    check("P43 总数不减", tl_many["count"], server.TIMELINE_MAX_ITEMS + 10)
    check_true("P44 抽稀后条数受限",
               len(tl_many["items"]) <= server.TIMELINE_MAX_ITEMS)


if __name__ == "__main__":
    sys.exit(main())
