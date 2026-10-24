# -*- coding: utf-8 -*-
"""抓拍 writer（计划书 §5.4，P3 交付）。

线程模型（§5.4 / R4）：
  * 主循环只调 `offer()`：做触发/冷却/配额判定（全是内存运算，微秒级），
    命中则 `queue.put_nowait()`（有界 64，满则 dropped++）；
  * **独立 daemon 线程**做 `cv2.imencode` + 写盘（JPEG 编码 10–30 ms，
    绝不能放在主循环——R4：抓拍写盘拖慢帧循环）；
  * **入队前必须 `frame.copy()`**：`GetFrame()` 返回的数组由采集线程复用，
    不 copy 的话写盘的是后续被覆写的缓冲（静默数据错误，肉眼极难发现）。
    该铁律集中在 `offer()` 内部完成，调用方无法绕过。

冷却（D3）：全局 `cooldown_ms` **AND** 按类别 `cooldown_ms_per_class`，两者都满足才拍。
配额：`daily_quota` 张/天 + `retention_days` 天保留；启动时与每 300s 各扫一次，
超限删最旧；`disk_avail < min_free_gb` 直接停抓拍并告警（一次性，恢复后自动解除）。
回收站：`pic/.trash/<YYYYMMDD>/`，超过 `trash_retention_days` 由本模块顺带清理
（console 的软删除也只负责搬进去，不负责清）。

Py3.8 兼容、无第三方依赖（cv2 由调用进程保证可用）。
"""

import datetime
import json
import os
import queue as queue_mod
import re
import shutil
import threading
import time

try:
    import cv2
except ImportError:                                  # pragma: no cover - 真机必有
    cv2 = None

QUEUE_MAX = 64                 # §5.4：有界队列，满则丢弃并计数
JPEG_QUALITY = 85              # 存档质量（ROS2 通路用 q70，抓拍取更高质量）
MAINTENANCE_INTERVAL_S = 300   # 配额/保留期/回收站巡检周期
DISK_CHECK_INTERVAL_S = 60     # 磁盘余量检查周期
NAME_RE = re.compile(r"^\d{8}T\d{6}_\d{3}_c\d{3}_id\d{3}\.jpg$")
_POISON = object()             # 退出毒丸（不能用 None：get 超时也返回 None）


def _now_ms(now=None):
    now = time.time() if now is None else now
    return int(round(now * 1000))


class SnapshotWriter(object):
    """抓拍队列 + 写盘线程。用法：

        snap = SnapshotWriter(cfg_getter=lambda: worker.cfg, log=print)
        ...
        snap.offer(frame, results, frame_no, infer_ms)   # 主循环每帧
        st = snap.stats()                                # 供 worker_state.json
        snap.close()                                     # 退出时
    """

    def __init__(self, cfg_getter, log=print):
        self._cfg_getter = cfg_getter
        self._log = log
        self._pic_dir = None
        self._resolve_pic_dir(initial=True)

        self.queue = queue_mod.Queue(maxsize=QUEUE_MAX)
        self.lock = threading.Lock()
        self.written = 0
        self.dropped = 0
        self.errors = 0
        self.today_count = 0
        self.last_save = None            # 最近一次保存的文件名
        self.last_save_ts = None         # 最近一次保存的时间戳（s）
        self.disk_low = False            # 磁盘低于 min_free_gb → 停抓拍
        self._cur_date = datetime.date.today().strftime("%Y%m%d")

        # 冷却状态：全局 + 按类别（D3）
        self._last_save_mono = 0.0
        self._last_save_cls = {}         # cls -> monotonic

        self._thread = threading.Thread(target=self._consume,
                                        name="snapshot-writer", daemon=True)
        self._thread.start()
        self._check_disk()               # 启动即校准红线，别等 60s
        self._maintain()                 # 含今日计数按磁盘校准 + 保留期清扫

    # ---------- 配置 ----------
    def _snap_cfg(self):
        cfg = self._cfg_getter() or {}
        return cfg.get("snapshot") or {}

    def _resolve_pic_dir(self, initial=False):
        """pic_dir 可能被在线修改（相对 src/ 或绝对路径）；每次 offer 前核对。

        相对路径相对 **src/**（与 console/server.py 的 ConsoleContext.pic_dir
        同一约定，也是 config_loader 的约定）——历史上这里曾按项目根解析，
        导致 worker 写 /home/test/pic 而 console 读 /home/test/yolo8/pic，
        浏览侧永远看不到抓拍（2026-10-22 部署时实测发现，p3-unit T16 回归）。
        """
        cfg = self._cfg_getter() or {}
        raw = cfg.get("pic_dir") or "../pic"
        if not os.path.isabs(raw):
            base = os.path.dirname(os.path.abspath(__file__))   # .../yolo8/src
            raw = os.path.normpath(os.path.join(base, raw))
        if raw != self._pic_dir:
            self._pic_dir = raw
            if not initial:
                self._log("[snapshot] pic_dir -> %s" % raw)
            try:
                os.makedirs(self._pic_dir, exist_ok=True)
            except OSError as exc:
                self._log("[snapshot] 创建 pic 目录失败: %s" % exc)

    # ---------- 主循环入口 ----------
    def offer(self, frame, results, frame_no, infer_ms):
        """触发+冷却+配额判定，命中则入队。返回是否入队。

        frame：要存的帧（标注帧或原始帧，由调用方按 save_annotated 决定）。
        results：ultralytics track 结果（本进程只用 boxes）。
        """
        snap = self._snap_cfg()
        if not snap.get("enabled", True):
            return False

        boxes = self._extract_boxes(results)
        if not boxes:
            return False

        now = time.time()
        # 1) 全局冷却
        cd_global = float(snap.get("cooldown_ms", 2000)) / 1000.0
        if cd_global > 0 and now - self._last_save_mono < cd_global:
            return False
        # 2) 按类别冷却（AND：任一类别还在冷却中就不拍）
        cd_cls = float(snap.get("cooldown_ms_per_class", 1000)) / 1000.0
        if cd_cls > 0:
            for cls in boxes["classes"]:
                last = self._last_save_cls.get(cls, 0.0)
                if now - last < cd_cls:
                    return False

        # 3) 日配额（入队即计数——不能等写盘：连续两帧的间隔远小于编码耗时，
        #    按写盘计数会让配额瞬时超发；_maintain 会按磁盘实况再校准）
        quota = int(snap.get("daily_quota", 500))
        if quota > 0 and self.today_count >= quota:
            return False

        # 4) 磁盘红线（消费线程每 60s 更新标志）
        if self.disk_low:
            return False

        # 5) 入队前 copy（铁律，见模块 docstring）
        if hasattr(frame, "get"):          # cv2.UMat → ndarray（P10 坑）
            frame = frame.get()
        buf = frame.copy()

        meta = {
            "ts_ms": _now_ms(now),
            "frame_no": frame_no,
            "infer_ms": round(float(infer_ms), 2),
            "conf_threshold": self._conf_threshold(),
            "boxes": boxes["detail"],
            "max_conf": boxes["max_conf"],
            "annotated": bool(snap.get("save_annotated", True)),
        }
        try:
            self.queue.put_nowait((buf, meta))
        except queue_mod.Full:
            with self.lock:
                self.dropped += 1
            return False

        # 冷却计时以"成功入队"为准（丢帧不算消费）；配额同此——入队即计数
        self._last_save_mono = now
        for cls in boxes["classes"]:
            self._last_save_cls[cls] = now
        with self.lock:
            self.today_count += 1
        return True

    def _conf_threshold(self):
        cfg = self._cfg_getter() or {}
        det = cfg.get("detect") or {}
        try:
            return float(det.get("conf_threshold", 0.4))
        except (TypeError, ValueError):
            return 0.4

    @staticmethod
    def _extract_boxes(results):
        """从 ultralytics 结果提取 [{x1,y1,x2,y2,conf,cls,id}] + 类别集合。

        任何形状异常都按"无检出"处理——抓拍是旁路，绝不影响主循环。
        """
        if not results or len(results) == 0:
            return None
        r = results[0]
        if getattr(r, "boxes", None) is None or len(r.boxes) == 0:
            return None
        detail = []
        classes = set()
        max_conf = 0.0
        best_id = 0
        try:
            xyxy = r.boxes.xyxy
            conf = r.boxes.conf
            cls = r.boxes.cls
            tid = getattr(r.boxes, "id", None)
            for i in range(len(xyxy)):
                x1, y1, x2, y2 = (int(v) for v in xyxy[i].tolist())
                c = float(conf[i].item())
                k = int(cls[i].item())
                t = int(tid[i].item()) if tid is not None else 0
                detail.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                               "conf": round(c, 4), "cls": k, "id": t})
                classes.add(k)
                if c > max_conf:
                    max_conf = c
                    best_id = t
        except (AttributeError, IndexError, ValueError, TypeError):
            return None
        if not detail:
            return None
        return {"detail": detail, "classes": classes,
                "max_conf": max_conf, "best_id": best_id}

    # ---------- 消费线程 ----------
    def _consume(self):
        """取队列写盘；顺带按周期做巡检（磁盘 60s / 全套 300s）。

        用带超时的 get 而不是永久阻塞：退出毒丸与巡检都要靠它驱动。
        """
        last_maint = time.monotonic()
        last_disk = last_maint
        while True:
            try:
                item = self.queue.get(timeout=1.0)
            except queue_mod.Empty:
                item = None
            if item is not None:
                if item is _POISON:         # 退出毒丸
                    self.queue.task_done()
                    break
                frame, meta = item
                try:
                    self._write_one(frame, meta)
                except Exception as exc:     # noqa: BLE001  抓拍失败绝不影响推流
                    with self.lock:
                        self.errors += 1
                    self._log("[snapshot] 写盘失败: %r" % exc)
                finally:
                    self.queue.task_done()
            now = time.monotonic()
            if now - last_disk >= DISK_CHECK_INTERVAL_S:
                last_disk = now
                self._check_disk()
            if now - last_maint >= MAINTENANCE_INTERVAL_S:
                last_maint = now
                self._maintain()

    def _write_one(self, frame, meta):
        self._resolve_pic_dir(initial=False)
        self._roll_date()
        now = meta["ts_ms"] / 1000.0
        day_dir = os.path.join(self._pic_dir, self._cur_date)
        os.makedirs(day_dir, exist_ok=True)

        conf_milli = min(999, int(round(meta["max_conf"] * 1000)))
        # id3 = 最高置信框的 track id（无跟踪 id 时 000）
        tid = 0
        for b in meta["boxes"]:
            if round(b["conf"], 4) == round(meta["max_conf"], 4):
                tid = min(999, int(b.get("id") or 0))
                break
        name = self._unique_name(day_dir, now, conf_milli, tid)

        ok, buf = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            raise IOError("cv2.imencode 失败")
        path = os.path.join(day_dir, name)
        with open(path, "wb") as fh:
            fh.write(buf.tobytes())

        snap = self._snap_cfg()
        if snap.get("save_meta", True):
            sidecar = {
                "name": name,
                "ts": datetime.datetime.fromtimestamp(
                    now).astimezone().isoformat(timespec="milliseconds"),
                "ts_ms": meta["ts_ms"],
                "frame_no": meta["frame_no"],
                "infer_ms": meta["infer_ms"],
                "conf_threshold": meta["conf_threshold"],
                "max_conf": round(meta["max_conf"], 4),
                "classes": sorted({b["cls"] for b in meta["boxes"]}),
                "boxes": meta["boxes"],
                "annotated": meta["annotated"],
                "image_wh": [frame.shape[1], frame.shape[0]],
            }
            with open(os.path.join(day_dir, name[:-4] + ".json"), "w") as fh:
                json.dump(sidecar, fh, ensure_ascii=False)

        with self.lock:
            self.written += 1
            self.last_save = name
            self.last_save_ts = now

    @staticmethod
    def _unique_name(day_dir, now, conf_milli, tid):
        """同毫秒碰撞防护（冷却设为 0 时理论上可出现）：顺延 2ms 重算时间戳。

        不追加序号后缀——那会破坏 `NAME_RE` 与时间轴解析。
        """
        for _ in range(50):
            dt = datetime.datetime.fromtimestamp(now)
            name = "%s_%03d_c%03d_id%03d.jpg" % (
                dt.strftime("%Y%m%dT%H%M%S"), dt.microsecond // 1000,
                conf_milli, tid)
            if not os.path.exists(os.path.join(day_dir, name)):
                return name
            now += 0.002
        # 极端情况：放弃本次（返回的名字会覆盖，但 50×2ms 内不可能发生）
        return name

    def _roll_date(self):
        """跨天重置计数（按磁盘实况校准，防进程跨天运行计数漂移）。"""
        today = datetime.date.today().strftime("%Y%m%d")
        if today == self._cur_date:
            return
        self._cur_date = today
        self._last_save_cls = {}
        self._last_save_mono = 0.0
        self.today_count = self._count_today()

    def _count_today(self):
        day_dir = os.path.join(self._pic_dir or ".", self._cur_date)
        try:
            return len([n for n in os.listdir(day_dir) if n.endswith(".jpg")])
        except OSError:
            return 0

    # ---------- 巡检 ----------
    def _check_disk(self):
        """磁盘红线（60s）：低于 min_free_gb 停抓拍，恢复后自动解除。"""
        try:
            snap = self._snap_cfg()
            min_free = float(snap.get("min_free_gb", 5)) * (1024 ** 3)
            try:
                usage = shutil.disk_usage(self._pic_dir or "/")
                low = usage.free < min_free
            except OSError:
                return
            if low != self.disk_low:
                self.disk_low = low
                self._log("[snapshot] %s：磁盘余量 %.1fGB（红线 %.0fGB）"
                          % ("已暂停抓拍" if low else "余量恢复，抓拍继续",
                             usage.free / (1024 ** 3), min_free / (1024 ** 3)))
        except Exception as exc:             # noqa: BLE001
            self._log("[snapshot] 磁盘检查异常: %r" % exc)

    def _maintain(self):
        """配额兜底 + 保留期 + 回收站清理（300s）。"""
        try:
            snap = self._snap_cfg()
            # 配额兜底（在线改小 quota 等场景）：今天超量删最旧
            quota = int(snap.get("daily_quota", 500))
            if quota > 0 and self._pic_dir:
                day_dir = os.path.join(self._pic_dir, self._cur_date)
                jpgs = sorted(n for n in _listdir(day_dir) if n.endswith(".jpg"))
                if len(jpgs) > quota:
                    for name in jpgs[:len(jpgs) - quota]:
                        _remove_pair(day_dir, name)
                    self._log("[snapshot] 日配额 %d 已满，清理最旧 %d 张"
                              % (quota, len(jpgs) - quota))
                self.today_count = len(jpgs)
            # 保留期：pic/<日期>/ 超 retention_days 整目录删
            keep_days = int(snap.get("retention_days", 7))
            if keep_days > 0 and self._pic_dir:
                cutoff = (datetime.date.today()
                          - datetime.timedelta(days=keep_days)).strftime("%Y%m%d")
                for name in _listdir(self._pic_dir):
                    if re.match(r"^\d{8}$", name) and name < cutoff:
                        shutil.rmtree(os.path.join(self._pic_dir, name),
                                      ignore_errors=True)
            # 回收站：.trash/<日期>/ 超 trash_retention_days 整目录删
            trash_days = int((self._cfg_getter() or {}).get(
                "trash_retention_days", 7))
            if trash_days > 0 and self._pic_dir:
                trash_root = os.path.join(self._pic_dir, ".trash")
                cutoff = (datetime.date.today()
                          - datetime.timedelta(days=trash_days)).strftime("%Y%m%d")
                for name in _listdir(trash_root):
                    if re.match(r"^\d{8}$", name) and name < cutoff:
                        shutil.rmtree(os.path.join(trash_root, name),
                                      ignore_errors=True)
        except Exception as exc:             # noqa: BLE001  巡检失败只记日志
            self._log("[snapshot] 巡检异常: %r" % exc)

    # ---------- 状态 / 退出 ----------
    def stats(self):
        with self.lock:
            snap = self._snap_cfg()
            return {
                "enabled": bool(snap.get("enabled", True)),
                "today_count": self.today_count,
                "written": self.written,
                "dropped": self.dropped,
                "errors": self.errors,
                "queue_depth": self.queue.qsize(),
                "last_save": self.last_save,
                "last_save_ts": self.last_save_ts,
                "disk_low": self.disk_low,
                "pic_dir": self._pic_dir,
            }

    def close(self, timeout=5.0):
        """退出：发毒丸，等消费线程排空（最多 timeout 秒）。"""
        if not self._thread.is_alive():
            return
        try:
            self.queue.put_nowait(_POISON)
        except queue_mod.Full:
            pass
        self._thread.join(timeout=timeout)


def _listdir(path):
    try:
        return os.listdir(path)
    except OSError:
        return []


def _remove_pair(day_dir, name):
    """删 jpg 时连同 json sidecar 一起删（防孤儿元数据）。"""
    for suffix in ("", ".json"):
        try:
            os.remove(os.path.join(day_dir, name[:-4] + suffix))
        except OSError:
            pass
