#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""onnx → ultralytics 兼容的 TensorRT engine（计划书 §5.6.2 / P4）。

为什么不用 ultralytics 的 export（§5.6.1）：
    YOLO("x.onnx") 加载后 self.model 是 onnxruntime InferenceSession，
    export(format="engine") 内部会调 torch.onnx.export(self.model, ...) 必然失败；
    torch2trt 在 103 上也不存在。因此走 TensorRT Python API 手工构建，
    再按真机文件结构手工复刻 ultralytics 的 metadata 头。

文件结构（真机既有 yolov8n_arm.engine 实测，头 4 字节 4c 06 00 00 = 1612）：
    [4 字节小端有符号 meta_len][meta_len 字节 UTF-8 JSON][TRT plan 序列化数据]
autobackend.py:334-345 要求 metadata 必含 5 个 key（缺一 KeyError）：
    stride / task / batch / imgsz / names

三种运行模式：
    python3 export_engine.py --onnx x.onnx --out y.engine [--names-json n.json]
    python3 export_engine.py --inspect x.onnx     # 打印输入输出/类别数/onnx 侧 names
    python3 export_engine.py --verify y.engine    # 解析 engine 头并打印 metadata

与 console 的契约（stdout 按行解析）：
    PROGRESS <0-100> <phase>     进度（TRT 8.5 无 IProgressMonitor，按阶段报）
    INFO <text>                  普通日志
    RESULT <json>                最终结果（单行 JSON，成功/失败都有）
    ERROR <text>                 失败原因（同时体现在 RESULT.ok=false）

约束：Python 3.8（103 系统 python3）⇒ 禁 3.9+ 语法；tensorrt / onnx 均延迟导入，
       便于在无 TRT 的机器上单测纯逻辑（pack/parse/meta）。
"""

import argparse
import ast
import datetime
import json
import os
import sys
import tempfile
import threading
import time

META_REQUIRED_KEYS = ("stride", "task", "batch", "imgsz", "names")
META_MAX_BYTES = 1 << 20          # meta JSON 上限 1 MB（防御坏文件）
DEFAULT_WORKSPACE_MB = 1024       # P4 实测：512 MB 时 TRT 报"tactics workspace 不足"
                                  # 并长时间重试（yolov8n 在 NX 上 >10 min）；
                                  # 1 GB 是计划书 §12 的上限，也是能拿到完整 tactic 集的值
DEFAULT_OPT_LEVEL = 2             # TRT 8.5 builder_optimization_level：3=默认（最慢，
                                  # P4 实测 NX 上 >16 min 仍在搜 tactic）；2 明显更快，
                                  # 精度/延迟差异 <5%（见计划书 §21 实测表）
DEFAULT_IMGSZ = 640
DEFAULT_STRIDE = 32
BUILD_HEARTBEAT_S = 30.0          # TRT 8.5 无 IProgressMonitor ⇒ 定时打点维持可见性
TIMING_CACHE_NAME = ".trt-timing-cache"


# ---------------------------------------------------------------- 输出协议

def emit(kind, text):
    """按 console 约定的协议输出一行（flush 保证子进程管道即时可读）。"""
    sys.stdout.write("%s %s\n" % (kind, text))
    sys.stdout.flush()


def progress(pct, phase):
    emit("PROGRESS", "%d %s" % (int(pct), phase))


def info(text):
    emit("INFO", text)


def result(payload):
    emit("RESULT", json.dumps(payload, ensure_ascii=False, sort_keys=True))


# ---------------------------------------------------------------- 名称与类别

def normalize_names(raw):
    """把 names 规整为 {"0": "person", ...}（ultralytics 要求 str 键）。

    接受 list/tuple（下标即 id）、dict（键可为 int 或 str）、以及 Python 字面量
    字符串（ultralytics 写进 onnx metadata 的是 "{0: 'person', ...}"，单引号）。
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("names 不能为空")
        try:
            raw = ast.literal_eval(text)      # 单引号字典 → dict（安全，不执行代码）
        except (ValueError, SyntaxError):
            try:
                raw = json.loads(text)
            except ValueError:
                raise ValueError("names 字符串既不是 Python 字面量也不是 JSON")
    if isinstance(raw, (list, tuple)):
        return dict((str(i), str(v)) for i, v in enumerate(raw))
    if isinstance(raw, dict):
        out = {}
        for key, val in raw.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                raise ValueError("names 的键必须是整数或数字字符串：%r" % (key,))
            out[str(idx)] = str(val)
        return out
    raise ValueError("names 必须是数组、对象或字符串")


def validate_names(names, classes):
    """校验名字数量与类别数一致且 id 连续；返回告警列表（person 不在 0 号位）。"""
    if not isinstance(names, dict) or not names:
        raise ValueError("names 不能为空")
    ids = sorted(int(k) for k in names)
    if ids != list(range(len(ids))):
        raise ValueError("names 的 id 必须从 0 连续：当前 %s" % (ids[:5],))
    if classes is not None and len(ids) != int(classes):
        raise ValueError("类别数不匹配：names 有 %d 个，onnx 输出推断 %d 个"
                         % (len(ids), int(classes)))
    warnings = []
    if names.get("0") != "person":
        warnings.append("names[0]=%r 不是 person（跟踪目标由 detect.classes 决定，"
                        "请自行确认）" % names.get("0"))
    return warnings


def infer_classes(output_dims):
    """YOLOv8 检测头输出 [1, 4+K, N]（或转置 [1, N, 4+K]）⇒ K。

    取两维中较小者减 4：84 与 8400 → 80；若模型直接输出 [1, 4+K] 也适用。
    """
    dims = [d for d in (output_dims or []) if isinstance(d, int) and d > 0]
    if len(dims) < 2:
        raise ValueError("无法从输出维度推断类别数：%r" % (output_dims,))
    small = min(dims[-2], dims[-1])
    if small <= 4:
        raise ValueError("输出维度 %r 不像 YOLO 检测头（应含 4 个框参数）"
                         % (output_dims,))
    return small - 4


# ---------------------------------------------------------------- engine 头

def make_meta(names, imgsz=(DEFAULT_IMGSZ, DEFAULT_IMGSZ), stride=DEFAULT_STRIDE,
              task="detect", source=None):
    """构造 ultralytics 兼容 metadata（必须含 5 个 key）。"""
    return {
        "description": "Lite3 yolo8 console export" + (" from %s" % source if source else ""),
        "author": "lite3-console",
        "license": "AGPL-3.0 https://ultralytics.com/license",
        "date": datetime.datetime.now().isoformat(),
        "version": "1.0.0",
        "stride": int(stride),
        "task": str(task),
        "batch": 1,
        "imgsz": [int(imgsz[0]), int(imgsz[1])],
        "names": dict((str(k), str(v)) for k, v in names.items()),
    }


def blob_to_bytes(blob):
    """把 engine.serialize() 的结果转成 bytes。

    TRT 8.5 Python 里 serialize() 返回的是 IHostMemory：
    - 它**没有 __len__**，所以 `len(blob)` / `if not blob`（bool 回退到 __len__）都会抛
      TypeError: object of type 'tensorrt.tensorrt.IHostMemory' has no len()；
    - 但它支持缓冲协议，可以直接喂给 file.write / bytes()。
    P4 首跑真机构建到 1580 s 后就是在这里炸的（构建其实已成功，只差序列化这一步）。
    """
    if isinstance(blob, bytes):
        return blob
    if isinstance(blob, bytearray):
        return bytes(blob)
    for conv in (lambda b: bytes(memoryview(b)), lambda b: bytes(b)):
        try:
            return conv(blob)
        except (TypeError, ValueError):
            continue
    raise TypeError("无法把 engine.serialize() 的结果转成 bytes：%r" % type(blob))


def _save_timing_cache(config, timing_cache):
    """落盘计时缓存。构建一完成就调用：即便后面序列化失败，下次构建也能命中缓存加速。"""
    if not timing_cache:
        return False
    try:
        data = blob_to_bytes(config.get_timing_cache().serialize())
        if not data:
            return False
        tmp = timing_cache + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, timing_cache)
        info("计时缓存已更新（%d 字节）" % len(data))
        return True
    except (AttributeError, RuntimeError, OSError, TypeError) as exc:
        info("计时缓存写回失败：%s" % exc)
        return False


def pack_engine(meta, blob, out_path):
    """写 [4B meta_len][meta][blob]：同目录 tmp + os.replace 原子替换。"""
    missing = [k for k in META_REQUIRED_KEYS if k not in meta]
    if missing:
        raise ValueError("metadata 缺必需 key：%s" % ", ".join(missing))
    payload = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    if len(payload) > META_MAX_BYTES:
        raise ValueError("metadata 过大（%d 字节）" % len(payload))
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".engine-", suffix=".tmp", dir=out_dir)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(len(payload).to_bytes(4, byteorder="little", signed=True))
            fh.write(payload)
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, out_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"out": out_path, "size": os.path.getsize(out_path),
            "meta_len": len(payload), "plan_len": len(blob)}


def parse_engine_header(path):
    """解析 engine 头，返回 {meta, meta_len, plan_len, size}；坏文件抛 ValueError。"""
    size = os.path.getsize(path)
    if size < 8:
        raise ValueError("文件过小（%d 字节），不是 engine" % size)
    with open(path, "rb") as fh:
        head = fh.read(4)
        meta_len = int.from_bytes(head, byteorder="little", signed=True)
        if meta_len <= 0 or meta_len > META_MAX_BYTES or meta_len + 4 > size:
            raise ValueError("meta_len 非法（%d，文件 %d 字节）" % (meta_len, size))
        payload = fh.read(meta_len)
    try:
        meta = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("metadata 不是合法 UTF-8 JSON：%s" % exc)
    if not isinstance(meta, dict):
        raise ValueError("metadata 必须是 JSON 对象")
    missing = [k for k in META_REQUIRED_KEYS if k not in meta]
    if missing:
        raise ValueError("metadata 缺必需 key：%s" % ", ".join(missing))
    return {"meta": meta, "meta_len": meta_len, "plan_len": size - 4 - meta_len,
            "size": size}


# ---------------------------------------------------------------- onnx 侧

def inspect_onnx(path):
    """读 onnx 输入输出与自带 names（不构建 engine，秒级返回）。"""
    import onnx                                   # 延迟导入：本机单测不需要
    model = onnx.load(path)
    ins, outs = [], []
    for tensor in model.graph.input:
        dims = [d.dim_value if d.dim_value > 0 else (d.dim_param or None)
                for d in tensor.type.tensor_type.shape.dim]
        ins.append({"name": tensor.name, "dims": dims})
    for tensor in model.graph.output:
        dims = [d.dim_value if d.dim_value > 0 else (d.dim_param or None)
                for d in tensor.type.tensor_type.shape.dim]
        outs.append({"name": tensor.name, "dims": dims})

    warnings = []
    image_in = None
    for item in ins:
        dims = item["dims"]
        if len(dims) == 4 and dims[1] in (1, 3):
            image_in = dims
            break
    if image_in is None:
        raise ValueError("找不到 NCHW 图像输入：%r" % (ins,))
    if any(not isinstance(d, int) for d in image_in):
        raise ValueError("输入含动态维度 %r：P4 只支持固定形状 onnx"
                         "（请用 dynamic=False 导出）" % (image_in,))
    if image_in[0] not in (1,):
        warnings.append("batch=%s，engine 元数据按 1 写入" % (image_in[0],))
    imgsz = [int(image_in[2]), int(image_in[3])]
    if imgsz[0] != imgsz[1]:
        warnings.append("输入非正方形 %r，按原尺寸构建" % (imgsz,))

    if not outs:
        raise ValueError("onnx 没有输出")
    classes = infer_classes(outs[0]["dims"])

    props = {}
    try:
        props = dict((p.key, p.value) for p in model.metadata_props)
    except AttributeError:                       # onnx < 1.10
        pass
    names, names_source = {}, None
    if props.get("names"):
        try:
            normalized = normalize_names(props["names"])
            if len(normalized) == classes:
                names, names_source = normalized, "onnx_metadata"
            else:
                warnings.append("onnx 自带 names 有 %d 个，与输出推断的 %d 个不一致，已忽略"
                                % (len(normalized), classes))
        except ValueError as exc:
            warnings.append("onnx 自带 names 解析失败，已忽略：%s" % exc)

    stride = DEFAULT_STRIDE
    try:
        stride = int(props.get("stride") or DEFAULT_STRIDE)
    except ValueError:
        pass
    task = props.get("task") or "detect"
    opset = 0
    try:
        opset = max(o.version for o in model.opset_import)
    except (ValueError, AttributeError):
        pass
    return {"ok": True, "inputs": ins, "outputs": outs, "imgsz": imgsz,
            "classes": classes, "stride": stride, "task": task,
            "opset": opset, "names": names, "names_source": names_source,
            "metadata": dict((k, v[:120]) for k, v in props.items()),
            "warnings": warnings, "size": os.path.getsize(path)}


# ---------------------------------------------------------------- TRT 构建

def _build_network(onnx_path, workspace_mb, half, opt_level=DEFAULT_OPT_LEVEL,
                   timing_cache=None, no_cudnn=False):
    """构建并序列化 plan bytes；返回 (blob, builder_info)。"""
    import tensorrt as trt                       # 延迟导入
    logger = trt.Logger(trt.Logger.INFO)
    builder = trt.Builder(logger)
    config = builder.create_builder_config()
    workspace = int(workspace_mb) << 20
    try:
        config.max_workspace_size = workspace    # TRT 8.5 仍接受
    except AttributeError:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace)
    # 构建优化等级：3=默认，tactic 搜索最全但也最慢（NX 上 >16 min）。
    # 2 在 yolov8n 上实测快 2~4 倍且延迟差异很小（§21 实测表）。
    try:
        config.builder_optimization_level = max(0, min(5, int(opt_level)))
    except (AttributeError, TypeError):
        info("TRT 版本不支持 builder_optimization_level，沿用默认（3）")
    # Xavier 上 cuDNN 的 conv tactic profiling 极慢（P4 实测单层可数十秒）。
    # 只保留 cuBLAS/cuBLASLt：构建时间大幅下降，精度不变、延迟通常 <5% 差异。
    if no_cudnn:
        try:
            srcs = int(trt.TacticSource.CUBLAS) | int(trt.TacticSource.CUBLAS_LT)
            config.set_tactic_sources(srcs)
            info("tactic sources 限制为 CUBLAS|CUBLAS_LT（跳过 cuDNN）")
        except (AttributeError, TypeError, RuntimeError) as exc:
            info("无法限制 tactic sources：%s" % exc)
    # 计时缓存：同一 GPU/TRT 版本的第二次构建可跳过重复 profiling。
    cache_blob = b""
    if timing_cache and os.path.isfile(timing_cache):
        try:
            with open(timing_cache, "rb") as fh:
                cache_blob = fh.read()
        except OSError:
            cache_blob = b""
    if timing_cache:
        try:
            cache = config.create_timing_cache(cache_blob)
            config.set_timing_cache(cache, ignore_mismatch=True)
            info("计时缓存：%s（%d 字节）"
                 % ("命中" if cache_blob else "新建", len(cache_blob)))
        except (AttributeError, RuntimeError) as exc:
            info("计时缓存不可用：%s" % exc) 
    flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(flag)
    parser = trt.OnnxParser(network, logger)
    with open(onnx_path, "rb") as fh:
        blob_in = fh.read()
    progress(8, "parse")
    if not parser.parse(blob_in):
        errors = []
        for i in range(parser.num_errors):
            errors.append(str(parser.get_error(i)))
        raise RuntimeError("ONNX 解析失败：%s" % ("; ".join(errors)[:600] or "未知"))

    # 固定形状才免建 optimization profile；动态维度在这里明确拒绝（比 TRT 报错可读）。
    for i in range(network.num_inputs):
        inp = network.get_input(i)
        if any(d < 0 for d in inp.shape):
            raise RuntimeError("输入 %s 含动态维度 %r：P4 只支持固定形状 onnx"
                               % (inp.name, list(inp.shape)))

    fp16 = False
    if half:
        if builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
            fp16 = True
        else:
            info("平台不支持快速 FP16，退回 FP32")
    progress(20, "build")
    started = time.time()
    stop = threading.Event()

    def beat():
        """构建期打点：TRT 8.5 没有进度回调，若不说话，UI 会以为卡死。"""
        while not stop.wait(BUILD_HEARTBEAT_S):
            info("building… 已 %.0fs（tactic 搜索中）" % (time.time() - started))

    beat_thread = threading.Thread(target=beat)
    beat_thread.daemon = True
    beat_thread.start()
    try:
        engine = builder.build_engine(network, config)
    finally:
        stop.set()
    if engine is None:
        raise RuntimeError("build_engine 返回 None（常见原因：workspace 不足 / 内存不够）")
    elapsed = round(time.time() - started, 1)
    # 构建已完成 → 先把计时缓存落盘：即便下一步序列化失败，重试也能命中缓存显著加速
    _save_timing_cache(config, timing_cache)
    progress(85, "serialize")
    blob = blob_to_bytes(engine.serialize())
    if not blob:
        raise RuntimeError("engine.serialize() 返回空数据")
    return blob, {"fp16": fp16, "workspace_mb": int(workspace_mb),
                  "opt_level": int(opt_level), "no_cudnn": bool(no_cudnn),
                  "build_s": elapsed,
                  "timing_cache": bool(timing_cache),
                  "trt_version": ".".join(str(x) for x in trt.__version__.split(".")[:3])}


def build_from_onnx(onnx_path, out_path, names, workspace_mb=DEFAULT_WORKSPACE_MB,
                    half=True, source=None, opt_level=DEFAULT_OPT_LEVEL,
                    timing_cache=None, no_cudnn=False):
    """inspect → 构建 → 打包。names 为空时用 onnx 自带的。"""
    progress(2, "inspect")
    inspected = inspect_onnx(onnx_path)
    classes = inspected["classes"]
    used_names = names or inspected.get("names") or {}
    if not used_names:
        raise ValueError("没有类别清单：请随 onnx 提供 names（数量应为 %d）" % classes)
    warnings = inspected.get("warnings") or []
    warnings.extend(validate_names(used_names, classes))
    meta = make_meta(used_names, imgsz=inspected["imgsz"],
                     stride=inspected.get("stride") or DEFAULT_STRIDE,
                     task=inspected.get("task") or "detect", source=source)
    if timing_cache is None:
        timing_cache = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                                    TIMING_CACHE_NAME)
    blob, build_info = _build_network(onnx_path, workspace_mb, half,
                                      opt_level=opt_level,
                                      timing_cache=timing_cache,
                                      no_cudnn=no_cudnn)
    progress(92, "pack")
    packed = pack_engine(meta, blob, out_path)
    verify = parse_engine_header(out_path)
    if list(verify["meta"]["names"]) != list(meta["names"]):
        raise RuntimeError("打包后 metadata 校验失败（names 不一致）")
    return {"ok": True, "out": out_path, "size": packed["size"],
            "meta_len": packed["meta_len"], "plan_len": packed["plan_len"],
            "classes": classes, "imgsz": inspected["imgsz"],
            "names_source": ("user" if names else inspected.get("names_source")),
            "warnings": warnings, "build": build_info,
            "meta_keys": sorted(verify["meta"].keys())}


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="onnx → ultralytics 兼容 TRT engine")
    parser.add_argument("--onnx", help="输入 onnx 路径")
    parser.add_argument("--out", help="输出 engine 路径")
    parser.add_argument("--names-json", default=None,
                        help="类别清单 JSON（数组或对象）；缺省用 onnx 自带 names")
    parser.add_argument("--imgsz", type=int, default=None,
                        help="保留参数：实际以 onnx 输入为准，仅做一致性检查")
    parser.add_argument("--workspace-mb", type=int, default=DEFAULT_WORKSPACE_MB)
    parser.add_argument("--opt-level", type=int, default=DEFAULT_OPT_LEVEL,
                        help="TRT builder_optimization_level（0-5，默认 2；3 最慢但 tactic 最全）")
    parser.add_argument("--no-cudnn", action="store_true",
                        help="跳过 cuDNN tactic（Xavier 上构建快很多，延迟通常 <5%% 差异）")
    parser.add_argument("--no-timing-cache", action="store_true",
                        help="禁用输出目录下的 .trt-timing-cache")
    parser.add_argument("--fp32", action="store_true", help="禁用 FP16")
    parser.add_argument("--inspect", metavar="ONNX", default=None)
    parser.add_argument("--verify", metavar="ENGINE", default=None)
    args = parser.parse_args(argv)

    try:
        if args.inspect:
            result(inspect_onnx(args.inspect))
            return 0
        if args.verify:
            parsed = parse_engine_header(args.verify)
            meta = parsed["meta"]
            result({"ok": True, "path": args.verify, "meta_len": parsed["meta_len"],
                    "required_keys_ok": True,
                    "plan_len": parsed["plan_len"], "size": parsed["size"],
                    "names_count": len(meta.get("names") or {}),
                    "stride": meta.get("stride"), "task": meta.get("task"),
                    "batch": meta.get("batch"), "imgsz": meta.get("imgsz"),
                    "description": meta.get("description")})
            return 0

        if not args.onnx or not args.out:
            parser.error("构建模式必须给 --onnx 与 --out")
        names = None
        if args.names_json:
            with open(args.names_json, "r", encoding="utf-8") as fh:
                names = normalize_names(json.load(fh))
        out = build_from_onnx(args.onnx, args.out, names,
                              workspace_mb=args.workspace_mb,
                              half=not args.fp32,
                              source=os.path.basename(args.onnx),
                              opt_level=args.opt_level,
                              no_cudnn=args.no_cudnn,
                              timing_cache=(None if args.no_timing_cache else
                                            os.path.join(
                                                os.path.dirname(os.path.abspath(args.out)),
                                                TIMING_CACHE_NAME)))
        progress(100, "done")
        result(out)
        return 0
    except Exception as exc:                       # noqa: BLE001  CLI 边界：一律转协议输出
        msg = "%s: %s" % (type(exc).__name__, exc)
        emit("ERROR", msg)
        result({"ok": False, "error": msg})
        return 2


if __name__ == "__main__":
    sys.exit(main())
