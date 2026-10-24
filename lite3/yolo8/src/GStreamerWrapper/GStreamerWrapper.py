# -*- coding: utf-8 -*-
"""采集封装：参数化管线 + `try-pull-sample` + 首帧超时 + 可重建。

修掉现状三个缺陷（计划书 §5.9.3 R10、附录 A）：
  1. 管线**硬编码**（location/尺寸/传输方式写死）→ 改由 `pipelines.build_source_pipeline` 生成；
  2. `__init__` 里同步 `pull-sample` → 源不可达时**永久阻塞**，进程卡死且无日志
     → 改用实测可用的 `try-pull-sample` + 首帧超时（抛 `SourceUnavailable`，进程不退出）；
  3. 主循环 `if frame is None: continue` 是**忙等**（启动期烧满一核）
     → `GetFrame(timeout)` 用 Condition 等待新帧，取不到才返回 None。

另：帧数据落库前 `.copy()`——GStreamer 缓冲区会被复用，直接持有视图会读到被覆写的内容。
"""

import threading
import time

import numpy as np
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from pipelines import build_source_pipeline


class SourceUnavailable(Exception):
    """源不可达 / 首帧超时。调用方应回滚到 last_good_source，**不要退出进程**。"""


class GStreamerWrapper(object):
    def __init__(self, src=None, first_frame_timeout_ms=None):
        Gst.init(None)
        self.src = dict(src or {})
        self.first_frame_timeout_ms = int(
            first_frame_timeout_ms
            or self.src.get("read_timeout_ms") or 5000)

        self.frame = None
        self.width = None
        self.height = None
        self.seq = 0
        self.consumed_seq = 0
        self.cond = threading.Condition()
        self.break_flag = False
        self.thread = None
        self.pipeline = None
        self.pipeline_str = None
        self.sink = None

        self._open(self.src)          # 失败抛 SourceUnavailable

    # ---------------- 生命周期 ----------------
    def _open(self, src):
        self.pipeline_str = build_source_pipeline(src)
        self.pipeline = Gst.parse_launch(self.pipeline_str)
        if self.pipeline is None:
            raise SourceUnavailable("管线创建失败: " + str(self.pipeline_str))
        self.sink = self.pipeline.get_by_name("sink")
        if self.sink is None:
            raise SourceUnavailable("appsink 缺失: " + str(self.pipeline_str))
        self.sink.set_property("emit-signals", True)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise SourceUnavailable("管线启动失败: " + str(self.pipeline_str))

        self.width, self.height = self._wait_first_sample(
            self.first_frame_timeout_ms)

        self.break_flag = False
        self.thread = threading.Thread(target=self._loop)
        self.thread.daemon = True
        self.thread.start()

    def _teardown(self):
        self.break_flag = True
        t = self.thread
        if t is not None and t.is_alive():
            t.join(timeout=3)
        self.thread = None
        if self.pipeline is not None:
            try:
                self.pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
        self.pipeline = None
        self.sink = None

    def Reopen(self, src):
        """关旧管线 → 建新管线。成功返回 True；失败抛 SourceUnavailable。

        注意：失败时**旧管线已停**，调用方负责用 last_good_source 重建（§5.9.4）。
        """
        self._teardown()
        self.src = dict(src or {})
        self.first_frame_timeout_ms = int(
            self.src.get("read_timeout_ms") or 5000)
        try:
            self._open(self.src)
        except BaseException:
            # 卡死/失败都要把这条管线彻底置 NULL：
            # 置 NULL 会解除 appsink 的阻塞，卡在 emit 里的线程才有机会退出。
            self._teardown()
            raise
        return True

    def StopThread(self):
        self._teardown()

    def __del__(self):
        try:
            self._teardown()
        except Exception:
            pass

    # ---------------- 取帧 ----------------
    def _wait_first_sample(self, timeout_ms):
        """用 try-pull-sample 等首帧；超时或总线报错即抛 SourceUnavailable。

        **带看门狗**：P2 实测在"重建管线"这条路径上，`try-pull-sample` 的超时参数
        并不总是生效——管线还没协商出 caps 时会一直等预滚帧，emit 永不返回，
        主循环被整体挂住（帧冻结、日志无输出，而进程还活着，最难查的那种故障）。
        因此这里把等待放进独立线程，`join` 超时即放弃这条管线。
        """
        box = {}

        def _probe():
            try:
                box['wh'] = self._poll_first_sample(timeout_ms)
            except BaseException as exc:      # noqa: BLE001 - 原样带给调用方
                box['err'] = exc

        t = threading.Thread(target=_probe)
        t.daemon = True
        t.start()
        t.join(timeout_ms / 1000.0 + 2.0)
        if t.is_alive():
            raise SourceUnavailable(
                '首帧等待卡死（超过 %.1fs），放弃该管线' % (timeout_ms / 1000.0))
        if 'err' in box:
            raise box['err']
        return box['wh']

    def _poll_first_sample(self, timeout_ms):
        deadline = time.time() + max(timeout_ms, 100) / 1000.0
        bus = self.pipeline.get_bus()
        while time.time() < deadline:
            try:
                sample = self.sink.emit("try-pull-sample", int(0.2 * Gst.SECOND))
            except Exception as e:          # 信号不可用等极端情况
                raise SourceUnavailable("try-pull-sample 失败: %s" % e)
            if sample is not None:
                caps = sample.get_caps()
                if caps is None:
                    raise SourceUnavailable("首帧无 caps")
                st = caps.get_structure(0)
                return st.get_value("width"), st.get_value("height")
            while bus.have_pending():
                msg = bus.pop()
                if msg.type == Gst.MessageType.ERROR:
                    err, dbg = msg.parse_error()
                    raise SourceUnavailable("%s | %s" % (err, dbg))
                if msg.type == Gst.MessageType.EOS:
                    raise SourceUnavailable("源在首帧前即 EOS")
        raise SourceUnavailable("first frame timeout %d ms" % timeout_ms)

    def _loop(self):
        while not self.break_flag:
            try:
                sample = self.sink.emit("try-pull-sample", int(0.2 * Gst.SECOND))
            except Exception:
                break
            if sample is None:
                continue
            buf = sample.get_buffer()
            if buf is None:
                continue
            ok, info = buf.map(Gst.MapFlags.READ)
            if not ok:
                continue
            try:
                arr = np.frombuffer(info.data, dtype=np.uint8)
                if self.width and self.height:
                    frame = arr.reshape((self.height, self.width, 3)).copy()
                else:
                    frame = None
            except ValueError:
                frame = None
            finally:
                buf.unmap(info)
            if frame is None:
                continue
            with self.cond:
                self.frame = frame
                self.seq += 1
                self.cond.notify_all()

    def GetFrame(self, timeout=0.5):
        """取**新**帧；timeout 内没有新帧则返回 None（不忙等、不重复处理旧帧）。"""
        with self.cond:
            if self.seq == self.consumed_seq:
                self.cond.wait(timeout)
            if self.seq == self.consumed_seq:
                return None
            self.consumed_seq = self.seq
            return self.frame
