# -*- coding: utf-8 -*-
import json
import os

from ultralytics import YOLO
from . import CocoTypeId

# P4：默认 engine（相对 src/，与 config model.engine 同一约定）
DEFAULT_ENGINE = '../model/yolov8n_arm.engine'
ENGINE_META_MAX = 1 << 20


def read_engine_names(path):
    """读 engine 元数据头得到类别数（4B 小端 meta_len + JSON）。

    为什么不用 `YOLO(path).names`：ultralytics 8.1.0 里 `YOLO(engine)` 只把字符串
    存进 self.model，真正的 AutoBackend 要到 predict 时才建，此时 `names` 是 **None**
    （P4 真机实测，曾让 worker_state 显示 classes_total=0）。读文件头零副作用、毫秒级。
    """
    try:
        with open(path, 'rb') as fh:
            meta_len = int.from_bytes(fh.read(4), byteorder='little', signed=True)
            if meta_len <= 0 or meta_len > ENGINE_META_MAX:
                return 0
            meta = json.loads(fh.read(meta_len).decode('utf-8'))
        return len(meta.get('names') or {})
    except (OSError, ValueError, UnicodeDecodeError):
        return 0


class YoloWrapper:
    def __init__(self, engine_path=None):
        # P4（§5.6.4）：engine 可配（config model.engine），由 RobotController 透传。
        # 相对路径以**当前工作目录 src/** 为基准（与历史硬编码一致）。
        self.engine_path = engine_path or os.environ.get('YOLO8_ENGINE') or DEFAULT_ENGINE
        self.model = YOLO(self.engine_path)
        self.classes_total = read_engine_names(self.engine_path)
        # 置信度阈值可调：部署层 deploy/yolo-publish.env 里配 YOLO8_CONF
        # （默认 0.5；0.4 对远距离/小目标更友好，误检多可调回）
        # P2 起由 config/yolo8.json 的 detect.conf_threshold 每帧同步覆盖，
        # 这里保留 env 仅作"配置文件缺失"时的回退。
        self.conf = float(os.environ.get('YOLO8_CONF', '0.5'))
        # 类别可配（config 的 detect.classes）。默认与改造前完全一致：只检 person。
        # 主循环检测到变化即整体替换，不需要重建模型。
        self.classes = [CocoTypeId.kPerson]

    def Reload(self, engine_path):
        """帧边界重建模型（P4）：**先建新实例再替换**，失败不影响在跑的旧模型。

        返回新模型类别数（读 metadata 头）；异常向上抛，由 worker 记到
        worker_state.model.reload_error。
        """
        target = engine_path or self.engine_path
        new_model = YOLO(target)          # 失败即抛，旧 self.model 原封不动
        self.model = new_model
        self.engine_path = target
        self.classes_total = read_engine_names(target)
        return self.classes_total

    def Track(self, img):
        return self.model.track(img, persist=True, classes=self.classes,
                                conf=self.conf)
