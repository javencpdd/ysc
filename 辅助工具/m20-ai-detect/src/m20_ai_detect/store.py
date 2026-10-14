"""落盘：JSONL 结果、原始帧环形缓冲、告警帧。

存储策略（ADR-001 + ADR-006）：
  * 结构化 JSONL 是权威数据，体积小（~600 B/帧），**永不删除**；
  * 原始 JPEG 帧只是复绘/复核证据，进环形缓冲，超配额删最旧；
  * 响应留存（ADR-006）：按 M20AI_SAVE_MODE 条件把标注结果图 + 原始响应
    （剥掉 base64 大图、留 jpg 引用）成对落 saved/<cam>/，图 ~120KB、JSON ~2KB；
  * 旧行为：SAVE_RESULT_IMAGE=true + 告警时存一张图到 alerts/（已由 save_mode=alert 取代）。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

from .config import Config

ITEM_KEYS = ("label", "class_id", "score", "box", "box_norm")


class Store:
    def __init__(self, cfg: Config, log=None) -> None:
        self.cfg = cfg
        self.log = log or (lambda msg: None)
        base = cfg.base_dir
        self.spool_dir = os.path.join(base, "spool")
        self.raw_dir = os.path.join(base, "raw")
        self.results_dir = os.path.join(base, "results")
        self.alerts_dir = os.path.join(base, "alerts")
        self.saved_dir = os.path.join(base, "saved")
        self.log_dir = os.path.join(base, "log")
        self.tmp_dir = os.path.join(base, "tmp")
        for d in (
            self.spool_dir,
            self.raw_dir,
            self.results_dir,
            self.alerts_dir,
            self.saved_dir,
            self.log_dir,
            self.tmp_dir,
        ):
            os.makedirs(d, exist_ok=True)

    def spool_for(self, cam: str) -> str:
        d = os.path.join(self.spool_dir, cam)
        os.makedirs(d, exist_ok=True)
        return d

    def raw_for(self, cam: str) -> str:
        d = os.path.join(self.raw_dir, cam)
        os.makedirs(d, exist_ok=True)
        return d

    def saved_for(self, cam: str) -> str:
        d = os.path.join(self.saved_dir, cam)
        os.makedirs(d, exist_ok=True)
        return d

    def clear_spool(self) -> Tuple[int, int]:
        """清空 spool/ 下所有待推理帧（各相机 *.jpg），返回 (帧数, 字节数)。

        用途：AI 服务长时间劣化后积压了大量陈旧帧，"以实时为主"时整体丢弃。
        调用方负责先停采样器再调用（避免删到正在读的帧、也避免删除期间又有新帧写入）。
        只删 spool/（未推理的待办）；raw/ 环形缓冲与 results/ JSONL 不动。
        """
        frames = 0
        nbytes = 0
        for root, _dirs, files in os.walk(self.spool_dir):
            for name in files:
                if not name.endswith(".jpg"):
                    continue
                p = os.path.join(root, name)
                try:
                    nbytes += os.path.getsize(p)
                    os.remove(p)
                    frames += 1
                except OSError as exc:
                    self.log("clear_spool failed %s: %s" % (p, exc))
        return frames, nbytes

    def save_pair(
        self, cam: str, stem: str, jpeg: Optional[bytes], payload: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """响应留存（ADR-006）：标注结果图 + 原始响应成对落 saved/<cam>/。

        * jpg：AI 返回的标注结果图（base64 解码后），None 时跳过；
        * json：原始响应剥掉 result_image 大字段，附 _result_image 引用路径；
        返回 (jpg 相对路径, json 相对路径)（相对 base_dir，便于迁移）。
        单侧失败只记日志不抛——留存是增强，不该打断采集主循环。
        """
        from .detect import strip_result_image

        d = self.saved_for(cam)
        img_rel: Optional[str] = None
        json_rel: Optional[str] = None
        if jpeg:
            p = os.path.join(d, stem + ".jpg")
            try:
                with open(p, "wb") as fh:
                    fh.write(jpeg)
                img_rel = os.path.relpath(p, self.cfg.base_dir).replace(os.sep, "/")
            except OSError as exc:
                self.log("save_pair image failed %s: %s" % (stem, exc))
        doc = strip_result_image(payload)
        if img_rel:
            doc["_result_image"] = img_rel
        p = os.path.join(d, stem + ".json")
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=2)
            json_rel = os.path.relpath(p, self.cfg.base_dir).replace(os.sep, "/")
        except OSError as exc:
            self.log("save_pair json failed %s: %s" % (stem, exc))
        return img_rel, json_rel

    def prune_results(self, keep_days: float) -> int:
        """清理超过 keep_days 天的 *.jsonl（0 = 不清理）。返回删除个数。

        按 mtime 判定；今天正在写的文件 mtime 新，不会被误删。
        任何单文件失败只记日志不中断（权威数据，宁可漏删不可误删）。
        """
        if keep_days <= 0:
            return 0
        cutoff = time.time() - keep_days * 86400
        removed = 0
        try:
            names = os.listdir(self.results_dir)
        except OSError:
            return 0
        for name in names:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(self.results_dir, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError as exc:
                self.log("prune_results skip %s: %s" % (name, exc))
        if removed:
            self.log("prune_results removed %d file(s) older than %.1f d" % (removed, keep_days))
        return removed

    def today_jsonl(self) -> str:
        return os.path.join(self.results_dir, "%s.jsonl" % datetime.now().strftime("%Y%m%d"))

    def append(self, record: Dict[str, Any]) -> None:
        path = self.today_jsonl()
        line = json.dumps(record, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def save_alert(self, cam: str, stem: str, jpeg: bytes) -> Optional[str]:
        path = os.path.join(self.alerts_dir, cam, "%s.jpg" % stem)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(jpeg)
        return path

    def enforce_ring(self) -> int:
        """raw/ 超过配额则删最旧，返回释放的字节数。"""
        entries = []
        total = 0
        for root, _dirs, files in os.walk(self.raw_dir):
            for name in files:
                p = os.path.join(root, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                entries.append((st.st_mtime, p, st.st_size))
                total += st.st_size
        if total <= self.cfg.ring_max_bytes:
            return 0
        entries.sort()
        freed = 0
        for _mtime, path, size in entries:
            if total <= self.cfg.ring_max_bytes:
                break
            try:
                os.remove(path)
                total -= size
                freed += size
            except OSError:
                continue
        if freed:
            self.log(
                "ring: freed %.1f MB (limit %.0f MB)"
                % (freed / 1048576.0, self.cfg.ring_max_bytes / 1048576.0)
            )
        return freed

    @staticmethod
    def summarize_items(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        items = list(items)
        return {
            "n_items": len(items),
            "items": [{k: it.get(k) for k in ITEM_KEYS if k in it} for it in items],
        }

    @staticmethod
    def sha1(data: bytes) -> str:
        return hashlib.sha1(data).hexdigest()

    def stats(self) -> Dict[str, Any]:
        def du(path: str) -> int:
            total = 0
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        total += os.stat(os.path.join(root, name)).st_size
                    except OSError:
                        pass
            return total

        return {
            "spool_bytes": du(self.spool_dir),
            "raw_bytes": du(self.raw_dir),
            "results_bytes": du(self.results_dir),
            "alerts_bytes": du(self.alerts_dir),
            "saved_bytes": du(self.saved_dir),
            "results_files": sorted(
                f for f in os.listdir(self.results_dir) if f.endswith(".jsonl")
            ),
        }
