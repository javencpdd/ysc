# -*- coding: utf-8 -*-
"""P5 单测：存储治理（留存清理 + 按需清空）。

不启动 HTTP 服务、不碰真机目录：所有目录都注入 tmpdir，
purge/storage 的可注入参数就是为这个准备的。
双跑：本地 py3.13 与真机 py3.8.10。

用法：python3 p5-unit.py
"""

import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import server as s                                # noqa: E402

PASS = 0
FAIL = 0


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


def mk(path, size=1024, age_days=None):
    """写文件；age_days 给定时把 mtime 拨到 N 天前。"""
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    if age_days is not None:
        os.utime(path, (time.time() - age_days * 86400.0,) * 2)
    return path


def count(directory):
    if not os.path.isdir(directory):
        return 0
    return len([n for n in os.listdir(directory)])


# ---------------------------------------------------------------- T1 retention_of
check("T1a 无 retention 段回落默认", s.retention_of({}), dict(s.DEFAULT_RETENTION))
check("T1b 非 dict 回落默认", s.retention_of({"retention": "x"}),
      dict(s.DEFAULT_RETENTION))
check("T1c 部分覆盖", s.retention_of({"retention": {"pic_max_mb": 100}})["pic_max_mb"], 100)
check("T1d 未覆盖的取默认", s.retention_of({"retention": {"pic_max_mb": 100}})["pic_keep_days"],
      s.DEFAULT_RETENTION["pic_keep_days"])
check("T1e 坏值忽略", s.retention_of({"retention": {"pic_max_mb": "abc"}})["pic_max_mb"],
      s.DEFAULT_RETENTION["pic_max_mb"])
check("T1f 负值忽略（不变成'不清理'）",
      s.retention_of({"retention": {"pic_keep_days": -1}})["pic_keep_days"],
      s.DEFAULT_RETENTION["pic_keep_days"])
check("T1g 0 是合法值（表示不按该维度清理）",
      s.retention_of({"retention": {"pic_keep_days": 0}})["pic_keep_days"], 0)

# ---------------------------------------------------------------- T2 iter_files
tmp = tempfile.mkdtemp(prefix="p5unit-")
try:
    mk(os.path.join(tmp, "pic", "20260101", "a.jpg"), 10)
    mk(os.path.join(tmp, "pic", "20260102", "b.jpg"), 10)
    mk(os.path.join(tmp, "pic", "20260102", "c.txt"), 10)
    mk(os.path.join(tmp, "pic", ".trash", "20260101", "d.jpg"), 10)

    got = s.iter_files(os.path.join(tmp, "pic"), (".jpg",), True, skip_dirs=(".trash",))
    check("T2a 递归并跳过 .trash", len(got), 2)
    got2 = s.iter_files(os.path.join(tmp, "pic"), (".jpg",), True)
    check("T2b 不跳过 .trash 时全收", len(got2), 3)
    got3 = s.iter_files(os.path.join(tmp, "pic"), None, False)
    check("T2c 非递归只收顶层（pic 顶层无文件）", len(got3), 0)
    check("T2d 目录不存在返回空", s.iter_files(os.path.join(tmp, "nope")), [])

    # ------------------------------------------------------------ T3 storage_stats
    up = os.path.join(tmp, "uploads")
    ex = os.path.join(tmp, "exports")
    lg = os.path.join(tmp, "logs")
    mk(os.path.join(up, "a.onnx"), 100)
    mk(os.path.join(ex, "y.engine"), 200)
    mk(os.path.join(ex, s.TIMING_CACHE_NAME), 50)
    mk(os.path.join(lg, "console.log"), 300)

    st = s.storage_stats(os.path.join(tmp, "pic"), uploads_dir=up,
                         exports_dir=ex, log_dir=lg)
    check("T3a pics 只数 jpg（2 个共 20B）", st["kinds"]["pics"], {"files": 2, "bytes": 20})
    check("T3b trash 单列", st["kinds"]["trash"], {"files": 1, "bytes": 10})
    check("T3c uploads", st["kinds"]["uploads"], {"files": 1, "bytes": 100})
    check("T3d exports 含计时缓存", st["kinds"]["exports"], {"files": 2, "bytes": 250})
    check("T3e logs", st["kinds"]["logs"], {"files": 1, "bytes": 300})
    check("T3f 计时缓存单独计数", st["timing_cache_bytes"], 50)
    check("T3g 合计", st["total_bytes"], 20 + 10 + 100 + 250 + 300)

    # ------------------------------------------------------------ T4 prune_pics
    p = os.path.join(tmp, "prune")
    mk(os.path.join(p, "20260101", "old.jpg"), 1000, age_days=40)
    mk(os.path.join(p, "20260102", "mid.jpg"), 1000, age_days=10)
    mk(os.path.join(p, "20260103", "new.jpg"), 1000, age_days=1)
    res = s.prune_pics(p, 0, 30)          # 只按年龄：40 天的删掉
    check("T4a 超龄删 1 个", res["files"], 1)
    check("T4b 无错误", res["errors"], [])
    check("T4c 剩下的两个还在", count(os.path.join(p, "20260102")) + count(os.path.join(p, "20260103")), 2)

    q = os.path.join(tmp, "prune2")
    mk(os.path.join(q, "20260101", "a.jpg"), 600, age_days=50)   # 最旧
    mk(os.path.join(q, "20260102", "b.jpg"), 600, age_days=40)
    mk(os.path.join(q, "20260103", "c.jpg"), 600, age_days=30)   # 最新
    # 上限 1 KB（1024 B）：总 1800 B，需删到 <=1024，删最旧 1 个（1200）还不够 → 再删 1 → 600
    res = s.prune_pics(q, 0, 0)           # 先不设上限，验证 0/0 不删
    check("T4d 两个维度都为 0 时不删", res["files"], 0)

    r2 = os.path.join(tmp, "prune3")
    mk(os.path.join(r2, "20260101", "a.jpg"), 600, age_days=50)
    mk(os.path.join(r2, "20260102", "b.jpg"), 600, age_days=40)
    mk(os.path.join(r2, "20260103", "c.jpg"), 600, age_days=30)
    # 用 KB 粒度的上限做不到（max_mb 是 MB），改用总量 1800B 与 limit=1MB 比较：
    res = s.prune_pics(r2, 1, 0)          # 1 MB 上限，总量 1800B 远低于 → 不删
    check("T4e 未超上限不删", res["files"], 0)

    # 超量场景：把单文件撑到 1 MB 以上
    big = os.path.join(tmp, "prune4")
    mk(os.path.join(big, "20260101", "a.jpg"), 700 * 1024, age_days=50)
    mk(os.path.join(big, "20260102", "b.jpg"), 700 * 1024, age_days=40)
    res = s.prune_pics(big, 1, 0)         # 上限 1 MB，总 1.4 MB → 删最旧一个
    check("T4f 超上限删最旧 1 个", res["files"], 1)
    check("T4g 删后剩 1 个", count(os.path.join(big, "20260102")), 1)

    # ------------------------------------------------------------ T5 prune_trash
    tr = os.path.join(tmp, "tr")
    mk(os.path.join(tr, ".trash", "20260101", "old.jpg"), 100, age_days=40)
    mk(os.path.join(tr, ".trash", "20260103", "new.jpg"), 100, age_days=1)
    res = s.prune_trash(tr, 0)
    check("T5a keep_days=0 不清理", res["files"], 0)
    res = s.prune_trash(tr, 7)
    check("T5b 超龄删 1 个", res["files"], 1)
    check("T5c 未超龄保留", count(os.path.join(tr, ".trash", "20260103")), 1)

    # ------------------------------------------------------------ T6 truncate_logs
    lg2 = os.path.join(tmp, "logs2")
    mk(os.path.join(lg2, "console.log"), 500)
    mk(os.path.join(lg2, "audit.log"), 300)
    res = s.truncate_logs(lg2)
    check("T6a 截断 2 个文件", res["files"], 2)
    check("T6b 释放 800B", res["bytes"], 800)
    check("T6c 文件仍存在（不是删除）", os.path.isfile(os.path.join(lg2, "console.log")), True)
    check("T6d 内容已清空", os.path.getsize(os.path.join(lg2, "console.log")), 0)
    check("T6e 标记为截断", res["truncated"], True)

    # ------------------------------------------------------------ T7 purge_targets
    pg = os.path.join(tmp, "pg")
    mk(os.path.join(pg, "20260101", "a.jpg"), 100)
    mk(os.path.join(pg, ".trash", "20260101", "b.jpg"), 100)
    pgu = os.path.join(tmp, "pgu")
    mk(os.path.join(pgu, "x.onnx"), 100)
    pge = os.path.join(tmp, "pge")
    mk(os.path.join(pge, "y.engine"), 100)
    mk(os.path.join(pge, s.TIMING_CACHE_NAME), 60)
    pgl = os.path.join(tmp, "pgl")
    mk(os.path.join(pgl, "console.log"), 100)

    res = s.purge_targets(pg, ["pics", "trash", "uploads", "exports", "logs"],
                          keep_timing_cache=True, uploads_dir=pgu,
                          exports_dir=pge, log_dir=pgl)
    check("T7a pics 清空", res["pics"], {"files": 1, "bytes": 100, "errors": []})
    check("T7b trash 清空", res["trash"]["files"], 1)
    check("T7c uploads 清空", res["uploads"]["files"], 1)
    check("T7d exports 只删 engine", res["exports"]["files"], 1)
    check("T7e 计时缓存保留", os.path.isfile(os.path.join(pge, s.TIMING_CACHE_NAME)), True)
    check("T7f logs 走截断", res["logs"]["truncated"], True)
    check("T7g 日志被截断为 0", os.path.getsize(os.path.join(pgl, "console.log")), 0)

    mk(os.path.join(pge, "z.engine"), 100)
    res = s.purge_targets(pg, ["exports"], keep_timing_cache=False, exports_dir=pge)
    check("T7h 显式关闭保护时计时缓存也被删",
          os.path.isfile(os.path.join(pge, s.TIMING_CACHE_NAME)), False)

    res = s.purge_targets(pg, ["nope", "pics"], uploads_dir=pgu, exports_dir=pge,
                          log_dir=pgl)
    check("T7i 未知 target 被忽略", "nope" in res, False)
    check("T7j 合法 target 仍执行", "pics" in res, True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ------------- T8 worker 判活兜底（游离 worker 不能绕过 purge 的停服保护）-------------
check("T8a 无状态视为不在跑", s.worker_looks_alive(None), False)
check("T8b alive=False 视为不在跑",
      s.worker_looks_alive({"worker": {"alive": False, "pid": 1}, "_age_s": 1}), False)
check("T8c 状态新鲜视为在跑",
      s.worker_looks_alive({"worker": {"alive": True, "pid": 16091}, "_age_s": 2.0}), True)
check("T8d 状态过期视为不在跑",
      s.worker_looks_alive({"worker": {"alive": True, "pid": 16091},
                            "_age_s": 600.0}), False)
check("T8e 缺 _age_s 时回退 ts",
      s.worker_looks_alive({"worker": {"alive": True, "pid": 1},
                            "ts": time.time() - 3}), True)
check("T8f ts 与 _age_s 都没有视为不在跑",
      s.worker_looks_alive({"worker": {"alive": True, "pid": 1}}), False)
check("T8g worker 段不是 dict 视为不在跑",
      s.worker_looks_alive({"worker": "x", "_age_s": 1}), False)
check("T8h 自定义阈值生效",
      s.worker_looks_alive({"worker": {"alive": True}, "_age_s": 20.0},
                           stale_s=30.0), True)

print("")
print("RESULT PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
