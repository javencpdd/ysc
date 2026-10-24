# -*- coding: utf-8 -*-
"""带双通路发布的主入口：ROS2(CompressedImage → Foxglove) + RTMP(H.264 硬件编码)。

P2 起（计划书 §5）：
  * **配置唯一来源 = `config/yolo8.json`**（mtime 轮询热更新，≤1 s 生效），
    env 只作 fallback（§5.11 三层优先级）；
  * 阈值 / 类别 / 视频源 / 推流目标 均可运行时改；改源与改目标 = **整条管线重建**，
    并带"先探测后写、失败回滚 last_good"的护栏；
  * **RTMP 出错不再 `break` 杀整个进程**（R11）：只销毁推流器 → error → 指数退避重连；
  * 源不可达不再永久阻塞（R10）：`try-pull-sample` + 首帧超时 → reconnecting 重试；
  * 每 250 ms 原子写 `logs/worker_state.json`（§5.7），console 只读该文件。

P3 起（计划书 §5.4）：高置信帧抓拍——主循环只做判定与入队（`snapshot_writer`），
编码写盘在独立线程；冷却/配额/保留期/磁盘红线全在 writer 内闭环。

用法（务必 cd 到 src，模型相对路径 ../model 依赖此目录）：
  cd /home/test/yolo8/src
  HEADLESS=1 python3 run_tracker_publish.py

遗留：env 里 `YOLO8_STATUS_INTERVAL`（打印间隔）仍生效——它属于"启动期静态"键（§5.11）。
"""

import os
import signal
import sys
import time

import cv2

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# 注意（命名空间包坑）：`from GStreamerWrapper import GStreamerWrapper` 拿到的是
# **模块**不是类（原代码写作 `GStreamerWrapper.GStreamerWrapper()`）。这里直接导入类。
from GStreamerWrapper.GStreamerWrapper import (     # noqa: E402
    GStreamerWrapper, SourceUnavailable)
from RobotController import RobotController          # noqa: E402
from RtmpPublisher.RtmpPublisher import RtmpPublisher  # noqa: E402
from config_loader import ConfigLoader, atomic_write_json    # noqa: E402
from pipelines import mask_url                               # noqa: E402
from snapshot_writer import SnapshotWriter                   # noqa: E402

RED = (0, 0, 255)     # BGR 红框
GREEN = (0, 128, 0)   # fps 字色
FONT = cv2.FONT_HERSHEY_SIMPLEX

STATE_PATH = os.path.normpath(
    os.path.join(_HERE, '..', 'logs', 'worker_state.json'))
STATE_INTERVAL_S = 0.25        # §5.7：每 250 ms 写一次状态
FRAME_TIMEOUT_S = 0.5          # GetFrame 等待上限（无帧时不忙等）
DEFAULT_ENGINE = '../model/yolov8n_arm.engine'

break_flag = False


def resolve_engine(raw):
    """config model.engine → 绝对路径。

    相对路径以 **src/** 为基准（与 pic_dir、YoloWrapper 历史默认同一约定）；
    统一转绝对路径，便于与已加载路径比较、也避免 cwd 变化带来的歧义。
    """
    raw = (raw or '').strip() or DEFAULT_ENGINE
    if not os.path.isabs(raw):
        raw = os.path.normpath(os.path.join(_HERE, raw))
    return raw


def _set_break_flag(signum, frame):
    global break_flag
    break_flag = True


signal.signal(signal.SIGINT, _set_break_flag)
signal.signal(signal.SIGTERM, _set_break_flag)


def draw_annotated(frame, results, fps_counter):
    """画红色 person 框；无检出时叠加 NO PERSON。任何情况都返回可推流的帧。"""
    fps_counter.Count()
    n = 0
    img = frame
    if results and len(results) > 0:
        r = results[0]
        if r.boxes is not None and len(r.boxes) > 0:
            img = frame.copy()
            for box in r.boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                conf = float(box.conf[0].item())
                cv2.rectangle(img, (x1, y1), (x2, y2), RED, 2)
                label = 'person %.2f' % conf
                (tw, th), _ = cv2.getTextSize(label, FONT, 0.55, 1)
                ty = y1 - 6 if y1 - 6 > th + 4 else y2 + th + 6
                cv2.rectangle(img, (x1, ty - th - 4), (x1 + tw + 6, ty + 2),
                              RED, -1)
                cv2.putText(img, label, (x1 + 3, ty), FONT, 0.55,
                            (255, 255, 255), 1)
                n += 1
    if n == 0:
        img = frame.copy()
        cv2.putText(img, 'NO PERSON', (10, 40), FONT, 0.9, RED, 2)
    cv2.putText(img, 'fps %.1f' % fps_counter.GetFps(), (10, 18),
                cv2.FONT_HERSHEY_PLAIN, 1.2, GREEN, 2)
    return img


class Worker(object):
    def __init__(self):
        self.headless = os.environ.get('HEADLESS', '0') != '0'
        if self.headless:
            # 无 X11 时 cv2.waitKey 会抛 "not implemented ... GTK+"
            cv2.waitKey = lambda delay=1: -1

        self.status_interval = int(os.environ.get('YOLO8_STATUS_INTERVAL', '100'))
        self.t0 = time.time()
        self.count = 0
        self.det_frames = 0
        self.pushed = 0
        self.infer_ms_ema = 0.0
        self.reconnects = 0

        self.loader = ConfigLoader()
        self.cfg = self.loader.cfg
        self.src = dict(self.cfg['source'])
        self.last_good_src = dict(self.src)

        self.src_state = 'starting'
        self.src_err = None
        self.src_next_retry = 0.0
        self.src_backoff = 1.0
        self.rtmp_state = 'idle'
        self.rtmp_err = None
        self.push_fail = 0
        self.rtmp_backoff = 1.0
        self.rtmp_next_retry = 0.0
        self.rtmp_ok_since = 0.0

        self.wrapper = None
        self.rtmp = None
        self.last_state_write = 0.0

        # P4（§5.6.4）：模型重载。console 只负责把 config 的 model.pending_reload
        # 置 true 并改 model.engine；worker 在**帧边界**重建 YOLO 后回写 false。
        self.engine_path = None
        self.model_reload_error = None
        self.model_reload_count = 0
        self.model_reload_last_s = None

        # P3：抓拍 writer（§5.4）。cfg_getter 传 self.cfg 的读取闭包——
        # snapshot.* 与 pic_dir 支持在线热改，writer 每次 offer 现取。
        self.snap = SnapshotWriter(cfg_getter=lambda: self.cfg)

        print('[worker] config=%s conf=%.2f source=%s (%s) rtmp=%s'
              % (self.loader.path,
                 self.cfg['detect']['conf_threshold'],
                 self.src.get('type'),
                 mask_url(self.src.get('rtsp_url') or self.src.get('file_path')),
                 self.cfg['stream']['rtmp_url']))

    # ---------------- 视频源 ----------------
    def refresh_cfg(self):
        """轮询配置；有变化则更新 self.cfg 并返回 True。"""
        if self.loader.poll():
            self.cfg = self.loader.cfg
            return True
        return False

    def open_source(self, retry_forever=False):
        """打开采集管线；失败返回 False 并记 src_err（不抛、不退出）。

        关键：重试期间**持续看配置**（P2 实测坑）——源地址可能已被改成可用值，
        若沿用启动时快照的 src，会拿着坏地址无限重试，改配置也救不回来。
        """
        backoff = 1.0
        while True:
            if retry_forever:
                if self.refresh_cfg():
                    self.src = dict(self.cfg['source'])
                    backoff = 1.0
            try:
                self.wrapper = GStreamerWrapper(self.src)
                self.last_good_src = dict(self.src)
                self.src_state = 'running'
                self.src_err = None
                self.src_backoff = 1.0
                self.src_next_retry = 0.0
                print('[source] 已打开: %s -> %sx%s'
                      % (mask_url(self.src.get('rtsp_url')
                                  or self.src.get('file_path')),
                         self.wrapper.width, self.wrapper.height))
                return True
            except SourceUnavailable as e:
                self.src_err = str(e)[:300]
                self.src_state = 'reconnecting'
                self.reconnects += 1
                if not retry_forever:
                    return False
                if break_flag:
                    return False
                print('[source] 打开失败(%s)，%.0fs 后重试'
                      % (self.src_err, backoff))
                self.write_state(time.time(), force=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def reopen_source(self, src):
        """热切换源：失败回滚到 last_good_src（§5.9.4）。"""
        try:
            self.wrapper.Reopen(src)
            self.src = dict(src)
            self.last_good_src = dict(src)
            self.src_state = 'running'
            self.src_err = None
            self.reconnects += 1
            print('[source] 已切换到: %s'
                  % mask_url(src.get('rtsp_url') or src.get('file_path')))
            return True
        except SourceUnavailable as e:
            self.src_err = str(e)[:300]
            self.reconnects += 1
            print('[source] 切换失败(%s)，回滚上一个可用源' % self.src_err)
            try:
                self.wrapper.Reopen(self.last_good_src)
                self.src = dict(self.last_good_src)
                self.src_state = 'running'
            except SourceUnavailable as e2:
                self.src_state = 'failed'
                self.src_err = '回滚也失败: %s' % str(e2)[:200]
                print('[source] ' + self.src_err)
            return False

    # ---------------- RTMP 推流 ----------------
    def _new_publisher(self, st):
        return RtmpPublisher(
            url=st.get('rtmp_url'),
            width=int(st.get('out_width') or 640),
            height=int(st.get('out_height') or 360),
            fps=int(st.get('fps') or 30),
            bitrate=int(st.get('rtmp_bitrate') or 1000000),
            sink=st.get('rtmp_sink') or 'rtmpsink')

    def apply_stream(self, st):
        """按配置重建/关闭推流。URL 变=双缓冲（先建后停）；其余=先停后建（§5.10.3）。"""
        if not st.get('rtmp'):
            if self.rtmp is not None:
                self.rtmp.eos_stop()
                self.rtmp = None
            self.rtmp_state = 'disabled'
            return
        if self.rtmp is None:
            self._build_rtmp(st)
            return
        same_url = (self.rtmp.url == st.get('rtmp_url'))
        if same_url and self.rtmp_state == 'running' and self.rtmp_err is None:
            return                                   # 无实质变化
        if same_url:
            self.rtmp.eos_stop()                     # 同流名：不能并存，先停
            self.rtmp = None
            self._build_rtmp(st)
        else:
            try:                                     # 不同流名：先建新的
                new_pub = self._new_publisher(st)
            except Exception as e:
                self.rtmp_err = str(e)[:300]
                self.rtmp_state = 'error'
                print('[rtmp] 新建失败，旧流保持不变: %s' % self.rtmp_err)
                return
            old = self.rtmp
            self.rtmp = new_pub
            old.eos_stop()                           # 新流已就绪再停旧流
            self.rtmp_state = 'running'
            self.rtmp_err = None
            self.rtmp_ok_since = time.time()
            print('[rtmp] 已切换到 %s' % mask_url(st.get('rtmp_url')))

    def _build_rtmp(self, st):
        try:
            self.rtmp = self._new_publisher(st)
            self.rtmp_state = 'running'
            self.rtmp_err = None
            self.rtmp_ok_since = time.time()
            print('[rtmp] 已启动 %s' % mask_url(st.get('rtmp_url')))
        except Exception as e:
            self.rtmp = None
            self.rtmp_err = str(e)[:300]
            self.rtmp_state = 'error'
            self.rtmp_next_retry = time.time() + self.rtmp_backoff
            print('[rtmp] 启动失败: %s' % self.rtmp_err)

    def degrade_rtmp(self, err):
        """RTMP 出错：**只降级不退出**（R11）。销毁 → error → 指数退避重连。"""
        self.rtmp_err = str(err)[:300]
        self.rtmp_state = 'error'
        if self.rtmp is not None:
            try:
                self.rtmp.eos_stop()
            except Exception:
                pass
            self.rtmp = None
        self.rtmp_next_retry = time.time() + self.rtmp_backoff
        self.rtmp_backoff = min(self.rtmp_backoff * 2, 30.0)
        print('[rtmp] 出错降级，%.0fs 后重连: %s'
              % (self.rtmp_backoff, self.rtmp_err))

    # ---------------- 配置热更新 ----------------
    def apply_config(self, old, new):
        if old.get('source') != new.get('source'):
            self.reopen_source(new['source'])
        if old.get('stream') != new.get('stream'):
            self.apply_stream(new['stream'])
        # detect 每帧同步，无需在此处理

    def sync_detect(self):
        """阈值/类别同步到 YoloWrapper（§5.3：改属性即可，不重建模型）。"""
        det = self.cfg['detect']
        yolo = self.robot.yolo_wrapper
        conf = float(det['conf_threshold'])
        if abs(yolo.conf - conf) > 1e-6:
            yolo.conf = conf
            print('[detect] conf_threshold -> %.2f' % conf)
        classes = list(det.get('classes') or [0])
        # P4 安全钳制：新 engine 类别数可能少于旧模型（如 80 类→2 类），
        # 越界 id 会让 ultralytics 取值错误。这里裁掉越界项并保留至少一个。
        # 类别数来自 YoloWrapper 读 engine 元数据头（YOLO(engine).names 在
        # ultralytics 8.1.0 里预测前恒为 None，不能用）。
        try:
            n_cls = int(getattr(yolo, 'classes_total', 0) or 0)
        except (TypeError, ValueError):
            n_cls = 0
        if n_cls:
            kept = [c for c in classes if 0 <= int(c) < n_cls]
            if kept != classes:
                print('[detect] classes %s 超出模型类别数 %d，已裁剪为 %s'
                      % (classes, n_cls, kept or [0]))
                classes = kept or [0]
        if list(yolo.classes) != classes:
            yolo.classes = classes
            print('[detect] classes -> %s' % classes)

    # ---------------- 模型重载（P4） ----------------
    def _clear_pending_reload(self):
        """把 model.pending_reload 回写 false：**worker 是唯一清除方**（console 只置 true）。

        写失败不影响运行（下一帧还会看到 true 再试）；成功则同步 loader.mtime，
        避免自己写文件触发一次多余的全量 reload。
        """
        model = self.cfg.get('model')
        if not isinstance(model, dict) or not model.get('pending_reload'):
            return
        model['pending_reload'] = False
        try:
            atomic_write_json(self.loader.path, self.cfg, fsync=True)
            try:
                os.chmod(self.loader.path, 0o600)
            except OSError:
                pass
            self.loader.mtime = os.stat(self.loader.path).st_mtime
        except (IOError, OSError) as e:
            print('[model] 回写 pending_reload 失败: %s' % e)

    def maybe_reload_model(self):
        """config model.pending_reload=true → 帧边界重建 YOLO（§5.6.4）。

        为什么不让 console 直接改 worker：数据面不对外开端口（§4.1），
        config 是唯一接口；重建阻塞 2–5 s，期间丢帧但不崩（appsink 自会丢）。
        """
        model = self.cfg.get('model') or {}
        if not model.get('pending_reload'):
            return
        target = resolve_engine(model.get('engine'))
        if target == self.engine_path:
            self._clear_pending_reload()      # 指向同一个文件：无事可做
            return
        if not os.path.exists(target):
            self.model_reload_error = 'engine 不存在: %s' % target
            print('[model] 重载取消：%s' % self.model_reload_error)
            self._clear_pending_reload()
            return
        t0 = time.time()
        try:
            n_cls = self.robot.yolo_wrapper.Reload(target)
        except Exception as e:                # noqa: BLE001  任何异常都不能拖垮主循环
            self.model_reload_error = '%s: %s' % (type(e).__name__, str(e)[:200])
            print('[model] 重载失败，继续使用旧模型: %s' % self.model_reload_error)
            self._clear_pending_reload()
            return
        self.engine_path = target
        self.model_reload_error = None
        self.model_reload_count += 1
        self.model_reload_last_s = round(time.time() - t0, 2)
        print('[model] 已重载 %s（%d 类，耗时 %.1fs）'
              % (os.path.basename(target), n_cls, self.model_reload_last_s))
        self._clear_pending_reload()

    # ---------------- 状态上行 ----------------
    def write_state(self, now, force=False):
        if not force and now - self.last_state_write < STATE_INTERVAL_S:
            return
        self.last_state_write = now
        st = self.cfg['stream']
        src_url = self.src.get('rtsp_url') or self.src.get('file_path') or ''
        up = now - self.t0
        fps = (self.count / up) if up > 0 else 0.0
        state = {
            'ts': now,
            'worker': {
                'alive': True,
                'pid': os.getpid(),
                'uptime_s': round(up, 1),
                'fps': round(fps, 2),
                'frames': self.count,
                'det_frames': self.det_frames,
                'infer_ms_ema': round(self.infer_ms_ema, 1),
                'conf_threshold': self.cfg['detect']['conf_threshold'],
                'config_load_count': self.loader.load_count,
                'config_err': self.loader.last_err,
            },
            'source': {
                'type': self.src.get('type'),
                'state': self.src_state,
                'url_masked': mask_url(src_url),
                'out_w': self.src.get('out_width'),
                'out_h': self.src.get('out_height'),
                'reconnects': self.reconnects,
                'err': self.src_err,
            },
            'stream': {
                'rtmp_state': self.rtmp_state,
                'rtmp_url': st.get('rtmp_url'),
                'rtmp_err': self.rtmp_err,
                'bitrate': st.get('rtmp_bitrate'),
                'pushed_frames': self.pushed,
                'ros2_image_state': ('running' if st.get('ros2_image')
                                     else 'disabled'),
                'ros2_every': st.get('ros2_every'),
            },
            'snapshot': self.snap.stats(),
            'model': {
                'engine': os.path.basename(self.engine_path or ''),
                'engine_path': self.engine_path,
                'pending_reload': bool((self.cfg.get('model') or {})
                                       .get('pending_reload')),
                'reload_count': self.model_reload_count,
                'last_reload_s': self.model_reload_last_s,
                'reload_error': self.model_reload_error,
                'classes_total': (getattr(self.robot.yolo_wrapper, 'classes_total', None)
                                  if getattr(self, 'robot', None) is not None else None),
            },
        }
        try:
            atomic_write_json(STATE_PATH, state)
        except (IOError, OSError) as e:
            print('[state] 写 worker_state 失败: %s' % e)

    # ---------------- 主循环 ----------------
    def run(self):
        # 先起采集（原顺序：源 → 模型 → 推流），源不可达时重试而不是退出
        if not self.open_source(retry_forever=True):
            return 1
        self.robot = RobotController.RobotController(
            resolve_engine((self.cfg.get('model') or {}).get('engine')))
        self.engine_path = self.robot.yolo_wrapper.engine_path
        print('[model] engine=%s' % self.engine_path)
        self.sync_detect()
        self.apply_stream(self.cfg['stream'])
        print('[worker] 就绪，进入主循环')

        while not break_flag:
            now = time.time()

            # 1) 配置热更新（≤1s）
            old_cfg = self.cfg
            if self.refresh_cfg():
                self.apply_config(old_cfg, self.cfg)

            # 2) 模型重载（P4）：model.pending_reload=true 时在此帧边界重建
            self.maybe_reload_model()

            # 2.1) 阈值/类别同步（§5.3：改属性即可，不重建模型）
            #    必须每帧做——P2 实测漏掉这一步时，worker_state 显示的阈值是 config 值
            #    （看着像生效了），但 yolo.conf 一直是启动时的旧值，行为根本没变。
            self.sync_detect()
            frame = self.wrapper.GetFrame(FRAME_TIMEOUT_S) \
                if self.wrapper is not None else None
            if frame is None:
                # 源不在运行 → 周期性重试打开（自愈）。没有这段的话，一旦切换失败
                # 而配置又不再变动，worker 会永远空转（不推流、不检测，但进程还在）。
                if self.src_state != 'running' and now >= self.src_next_retry:
                    if self.open_source(retry_forever=False):
                        self.src_next_retry = 0.0
                    else:
                        self.src_next_retry = now + self.src_backoff
                        self.src_backoff = min(self.src_backoff * 2, 30.0)
                self.write_state(now)
                continue

            self.count += 1
            t_infer = time.time()
            results = self.robot.yolo_wrapper.Track(frame)
            self.infer_ms_ema = (self.infer_ms_ema * 0.9
                                 + (time.time() - t_infer) * 1000.0 * 0.1)
            n_boxes = 0
            if results and len(results) > 0 and results[0].boxes is not None:
                n_boxes = len(results[0].boxes)
            if n_boxes:
                self.det_frames += 1
            final_frame = draw_annotated(frame, results,
                                         self.robot.fps_counter)

            # 2.5) 抓拍（§5.4）：save_annotated 决定存标注帧还是原始帧。
            #     入队前 frame.copy() 与 UMat 转换都在 writer 内部完成
            #     （铁律集中一处，调用方无法绕过）；写盘在独立线程，不占主循环。
            if self.snap is not None:
                save_annotated = bool((self.cfg.get('snapshot') or {}).get(
                    'save_annotated', True))
                self.snap.offer(
                    final_frame if save_annotated else frame,
                    results, self.count, (time.time() - t_infer) * 1000.0)

            # 3) RTMP：出错只降级（R11），到点自动重连
            st = self.cfg['stream']
            if st.get('rtmp'):
                if self.rtmp is None:
                    if now >= self.rtmp_next_retry:
                        self._build_rtmp(st)
                if self.rtmp is not None:
                    if self.rtmp.Drain():                 # 非阻塞取总线
                        self.degrade_rtmp(self.rtmp.CheckError())
                    elif not self.rtmp.Push(final_frame):
                        # push-buffer 返回非 OK = 下游已不接受数据。
                        # 补这条的原因（P2 实测）：rtmpsink 连不可达地址时**总线报错来得很慢**
                        # （内部握手重试），只靠 bus 会在十几秒内都显示 running，
                        # 实际上一帧都没发出去。Push 的返回值是即时信号。
                        # 连续 3 次才判定：管线刚进 PLAYING 的头一两帧可能返回
                        # FLUSHING，那是瞬时状态，不该触发重建。
                        self.push_fail += 1
                        if self.push_fail >= 3:
                            self.degrade_rtmp('push-buffer 连续 %d 次非 OK（流已断）'
                                              % self.push_fail)
                    else:
                        self.push_fail = 0
                        self.pushed += 1
                        # 连续正常满 10s 才复位退避（防抖动式重启风暴）
                        if now - self.rtmp_ok_since >= 10.0:
                            self.rtmp_backoff = 1.0

            # 4) ROS2：JPEG 软编，降频发布
            if st.get('ros2_image') and st.get('ros2_every', 0) > 0 \
                    and self.count % int(st['ros2_every']) == 0:
                transfer = getattr(self.robot, 'ros2_transfer', None)
                if transfer is not None:
                    transfer.SendImage(final_frame)

            # 5) 状态打印
            if self.status_interval > 0 \
                    and self.count % self.status_interval == 0:
                print('frames=%d det_frames=%d fps=%.2f infer_ms=%.1f '
                      'rtmp=%s/%s src=%s'
                      % (self.count, self.det_frames,
                         self.count / max(time.time() - self.t0, 1e-6),
                         self.infer_ms_ema, self.rtmp_state,
                         self.rtmp_err or 'none', self.src_state))

            self.write_state(now)

            if not self.headless:
                cv2.imshow('DR People Tracking', final_frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

        return 0

    def stop(self):
        print('stopping, frames=%d det_frames=%d pushed=%d elapsed=%.1fs'
              % (self.count, self.det_frames, self.pushed,
                 time.time() - self.t0))
        if self.snap is not None:
            self.snap.close()                # 排空抓拍队列（最多 5s）
        if self.wrapper is not None:
            self.wrapper.StopThread()
        if self.rtmp is not None:
            self.rtmp.eos_stop()
        if not self.headless:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass


def main():
    w = Worker()
    try:
        rc = w.run()
    finally:
        w.stop()
    return rc


if __name__ == '__main__':
    sys.exit(main())
