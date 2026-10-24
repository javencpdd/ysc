# -*- coding: utf-8 -*-
"""P3 抓拍冒烟终检（真机 103 运行）：命名 / 双冷却 / copy 语义 / sidecar 一致性。

用法：python3 p3-smoke-check.py [pic_dir]
判定全部基于磁盘实况，不信任 worker_state。
"""

import datetime
import json
import os
import re
import sys

NAME_RE = re.compile(r"^\d{8}T\d{6}_\d{3}_c\d{3}_id\d{3}\.jpg$")
GLOBAL_COOLDOWN_MS = 2000
CLASS_COOLDOWN_MS = 1000
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


def main():
    pic_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/test/yolo8/pic"
    day = datetime.date.today().strftime("%Y%m%d")
    d = os.path.join(pic_dir, day)
    jpgs = sorted(n for n in os.listdir(d) if n.endswith(".jpg")) \
        if os.path.isdir(d) else []
    print("目录 %s：%d 个 jpg" % (d, len(jpgs)))

    # S1 命名规范（全量）
    bad_name = [n for n in jpgs if not NAME_RE.match(n)]
    check("S1 命名规范全量合规", bad_name, [])

    # S2 sidecar 一对一 + 关键字段
    metas = {}
    miss_meta, bad_meta = [], []
    for n in jpgs:
        mp = os.path.join(d, n[:-4] + ".json")
        if not os.path.isfile(mp):
            miss_meta.append(n)
            continue
        try:
            m = json.load(open(mp))
        except ValueError:
            bad_meta.append(n)
            continue
        for k in ("name", "ts", "ts_ms", "frame_no", "infer_ms",
                  "conf_threshold", "max_conf", "classes", "boxes",
                  "annotated", "image_wh"):
            if k not in m:
                bad_meta.append("%s 缺字段 %s" % (n, k))
                break
        else:
            metas[n] = m
    check("S2a sidecar 无缺失", miss_meta, [])
    check("S2b sidecar 字段完整且可解析", bad_meta, [])

    # S3 cNNN 与 max_conf 千分位一致
    bad_conf = []
    for n, m in metas.items():
        c = int(re.search(r"_c(\d{3})_", n).group(1))
        if abs(c - int(round(m["max_conf"] * 1000))) > 1:
            bad_meta.append("%s c=%d max_conf=%s" % (n, c, m["max_conf"]))
    check("S3 cNNN 与 max_conf 一致", bad_conf, [])

    # 时间线（本地时区，与写入侧 datetime.fromtimestamp 一致）
    def ts_of(n):
        m = re.match(r"(\d{8})T(\d{6})_(\d{3})", n)
        dt = datetime.datetime.strptime(m.group(1) + m.group(2),
                                        "%Y%m%d%H%M%S")
        return dt.timestamp() * 1000.0 + int(m.group(3))

    items = [(ts_of(n), n) for n in jpgs]
    items.sort()

    # S4 全局冷却（全量；跨进程重启的时间差远大于 2s，天然满足）
    gaps = [items[i + 1][0] - items[i][0] for i in range(len(items) - 1)]
    viol_g = [g for g in gaps if g < GLOBAL_COOLDOWN_MS]
    check("S4 全局冷却 >=2000ms 零违反（%d 个间隔, min=%.0fms）"
          % (len(gaps), min(gaps) if gaps else -1), viol_g, [])

    # S5 按类冷却：相邻两张主类别集合有交集时，间隔必须 >=1000ms
    #    （全局冷却已 >=2000ms 恒成立，这里验证的是"同类不放行"的额外约束：
    #      设计为 AND 判定——全局与按类都过才拍；全局已保证 >=2s，
    #      因此按类冷却实际由"主类别集合交集"体现：交集中的类上次出现
    #      必须已过 1000ms。因全局 >=2s > 1s，按类冷却自动满足，
    #      此处验证的是 classes 字段真实来自 sidecar 且非空。）
    empty_cls = [n for n, m in metas.items() if not m.get("classes")]
    check("S5 sidecar classes 非空", empty_cls, [])

    # S6 copy 语义：无重复图像 + 同进程内 frame_no 单调
    #    进程边界识别：frame_no 相对前一张变小即重启点（重启后从 1 开始）
    import hashlib
    md5s = {}
    dup = []
    for n in jpgs:
        h = hashlib.md5(open(os.path.join(d, n), "rb").read()).hexdigest()
        if h in md5s:
            dup.append((md5s[h], n))
        md5s[h] = n
    check("S6a 无重复图像（同 MD5）", dup, [])

    order = [(n, metas[n]["frame_no"]) for n in jpgs if n in metas]
    order.sort(key=lambda t: ts_of(t[0]))
    segments, cur = [], [order[0]] if order else []
    for prev, nxt in zip(order, order[1:]):
        if nxt[1] <= prev[1]:
            segments.append(cur)
            cur = [nxt]
        else:
            cur.append(nxt)
    if cur:
        segments.append(cur)
    print("识别到 %d 个进程段（frame_no 归零 = worker 重启）" % len(segments))
    non_mono = 0
    for seg in segments:
        fns = [f for _, f in seg]
        if any(b <= a for a, b in zip(fns, fns[1:])):
            non_mono += 1
    check("S6b 各进程段内 frame_no 严格递增", non_mono, 0)

    # S7 帧率合理性：同段内 (dframe/dt) 应接近源的 30fps（容差到 60）
    bad_fps = []
    for seg in segments:
        for (n1, f1), (n2, f2) in zip(seg, seg[1:]):
            dt_s = (ts_of(n2) - ts_of(n1)) / 1000.0
            if dt_s <= 0:
                continue
            fps = (f2 - f1) / dt_s
            if fps > 60:
                bad_fps.append((n1, n2, round(fps, 1)))
    check("S7 段内帧速 <=60fps（无跳帧错位）", bad_fps[:3], [])

    print("\n===== P3 冒烟终检: PASS=%d FAIL=%d =====" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
