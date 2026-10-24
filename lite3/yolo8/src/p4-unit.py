# -*- coding: utf-8 -*-
"""P4 单测 A：`src/export_engine.py` 纯逻辑（不依赖 tensorrt / onnx 的部分）。

双跑约定（同 p3-unit.py）：本地 py3.13 与真机 py3.8.10 都可执行。
  * T1–T7 无三方依赖，任何环境全跑；
  * T8–T9 需要 engine/onnx 实物（真机 model/ 目录），本机 SKIP。

用法：
  python3 p4-unit.py          # 仓库副本目录或真机 src/ 下均可
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import export_engine as ee                        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.normpath(os.path.join(HERE, "..", "model"))

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


def check_raises(name, fn, needle):
    global PASS, FAIL
    try:
        fn()
    except ValueError as exc:
        if needle in str(exc):
            PASS += 1
            print("PASS  %s -> %s" % (name, exc))
        else:
            FAIL += 1
            print("FAIL  %s: 异常信息不含 %r（%s）" % (name, needle, exc))
        return
    except Exception as exc:                      # noqa: BLE001
        FAIL += 1
        print("FAIL  %s: 抛了 %s 而不是 ValueError" % (name, type(exc).__name__))
        return
    FAIL += 1
    print("FAIL  %s: 未抛异常" % name)


def skip(name, why):
    global SKIP
    SKIP += 1
    print("SKIP  %s（%s）" % (name, why))


# ---------------------------------------------------------------- T1 names
check("T1a list", ee.normalize_names(["person", "dog"]),
      {"0": "person", "1": "dog"})
check("T1b dict-int", ee.normalize_names({0: "person", 1: "dog"}),
      {"0": "person", "1": "dog"})
check("T1c dict-str", ee.normalize_names({"0": "person", "1": "dog"}),
      {"0": "person", "1": "dog"})
check("T1d py-literal", ee.normalize_names("{0: 'person', 1: 'dog'}"),
      {"0": "person", "1": "dog"})
check("T1e json", ee.normalize_names('{"0": "person"}'), {"0": "person"})
try:
    ee.normalize_names("  ")
    check("T1f 空字符串", "no-error", "ValueError")
except ValueError as exc:
    check_true("T1f 空字符串", "不能为空" in str(exc) or "names" in str(exc))
check_raises("T1g 非法键", lambda: ee.normalize_names({"x": "person"}), "键")

# ---------------------------------------------------------------- T2 名称校验
check("T2a 合法无告警", ee.validate_names({"0": "person", "1": "dog"}, 2), [])
check_true("T2b person 不在 0 号位告警",
           ee.validate_names({"0": "cat"}, 1)[0].startswith("names[0]"))
check_raises("T2c 数量不匹配",
             lambda: ee.validate_names({"0": "person"}, 2), "类别数不匹配")
check_raises("T2d id 不连续",
             lambda: ee.validate_names({"1": "dog"}, 1), "连续")

# ---------------------------------------------------------------- T3 类别推断
check("T3a [1,84,8400]", ee.infer_classes([1, 84, 8400]), 80)
check("T3b [1,8400,84] 转置", ee.infer_classes([1, 8400, 84]), 80)
check("T3c [1,6,10]", ee.infer_classes([1, 6, 10]), 2)
check_raises("T3d 非检测头", lambda: ee.infer_classes([1, 3, 3]), "不像 YOLO")

# ---------------------------------------------------------------- T4 meta
meta = ee.make_meta({"0": "person", "1": "dog"}, imgsz=(640, 480), stride=32)
check("T4a 五个必需 key 齐全",
      [k for k in ee.META_REQUIRED_KEYS if k in meta], list(ee.META_REQUIRED_KEYS))
check("T4b imgsz", meta["imgsz"], [640, 480])
check("T4c batch", meta["batch"], 1)
check("T4d names 类型", sorted(meta["names"].items()),
      [("0", "person"), ("1", "dog")])

# ---------------------------------------------------------------- T5/T6 打包
tmpdir = tempfile.mkdtemp(prefix="p4unit-")
try:
    out = os.path.join(tmpdir, "x.engine")
    blob = bytes(range(256)) * 8
    packed = ee.pack_engine(meta, blob, out)
    check("T5a 文件大小", packed["size"], 4 + packed["meta_len"] + len(blob))
    parsed = ee.parse_engine_header(out)
    check("T5b names 往返", parsed["meta"]["names"], meta["names"])
    check("T5c plan 长度", parsed["plan_len"], len(blob))
    with open(out, "rb") as fh:
        raw = fh.read()
    check("T5d 4 字节小端头",
          int.from_bytes(raw[:4], "little", signed=True), packed["meta_len"])
    check("T5e plan 字节完整", raw[4 + packed["meta_len"]:] == blob, True)

    # ---- T5f-I：IHostMemory 兼容（P4 真机首跑在这里炸过：构建成功但序列化失败）----
    class FakeHostMemory(object):
        """模拟 TRT 8.5 的 IHostMemory：能转成 bytes，但**不能 len() 也不能 bool()**。

        真机上 `len(blob)` 与 `if not blob` 都会抛
        TypeError: object of type 'tensorrt.tensorrt.IHostMemory' has no len()。
        注意：Python 对象在两者都未定义时 bool() 默认返回 True，所以这里必须**显式**
        定义 __bool__ 抛错，才能还原真机行为。
        """
        def __init__(self, data):
            self._d = data

        def __bool__(self):
            raise TypeError("object of type 'FakeHostMemory' has no len()")

        def __bytes__(self):
            return self._d

    fake = FakeHostMemory(blob)
    try:
        len(fake)
        check("T5f 假 IHostMemory 不能 len()", "no-error", "TypeError")
    except TypeError:
        check_true("T5f 假 IHostMemory 不能 len()", True)
    try:
        bool(fake)
        check("T5g 假 IHostMemory 不能 bool()", "no-error", "TypeError")
    except TypeError:
        check_true("T5g 假 IHostMemory 不能 bool()", True)
    got5h = ee.blob_to_bytes(fake)
    check("T5h blob_to_bytes 绕过 len/bool（长度）", len(got5h), len(blob))
    check_true("T5h blob_to_bytes 内容一致", got5h == blob)
    check_true("T5i blob_to_bytes 幂等（bytes 直传）", ee.blob_to_bytes(blob) == blob)

    class BadConfig(object):
        def get_timing_cache(self):
            raise RuntimeError("no timing cache")

    check("T5j 计时缓存写回失败不冒泡",
          ee._save_timing_cache(BadConfig(), os.path.join(tmpdir, "tc")), False)

    bad_meta = dict(meta)
    bad_meta.pop("names")
    try:
        ee.pack_engine(bad_meta, b"x", os.path.join(tmpdir, "y.engine"))
        check("T6a 缺 key 拒绝", "no-error", "ValueError")
    except ValueError as exc:
        check_true("T6a 缺 key 拒绝", "names" in str(exc))

    # ------------------------------------------------------------ T7 坏文件
    cases = {
        "空文件": b"",
        "过短": b"\x01\x02",
        "meta_len 越界": b"\xff\xff\x00\x00" + b"{}",
        "meta 非 JSON": b"\x05\x00\x00\x00hello",
        "缺 key": None,
    }
    bad_meta_json = json.dumps({"stride": 32, "names": {}}).encode("utf-8")
    cases["缺 key"] = (len(bad_meta_json).to_bytes(4, "little", signed=True)
                       + bad_meta_json + b"PLAN")
    for idx, (label, data) in enumerate(cases.items()):
        p = os.path.join(tmpdir, "bad%d.engine" % idx)
        with open(p, "wb") as fh:
            fh.write(data)
        try:
            ee.parse_engine_header(p)
            check("T7 %s 拒绝" % label, "no-error", "ValueError")
        except ValueError:
            check_true("T7 %s 拒绝" % label, True)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ---------------------------------------------------------------- T8 真机 engine
arm = os.path.join(MODEL_DIR, "yolov8n_arm.engine")
if os.path.isfile(arm):
    parsed = ee.parse_engine_header(arm)
    missing = [k for k in ee.META_REQUIRED_KEYS if k not in parsed["meta"]]
    check("T8a 现有 arm.engine 必需 key 缺失数", len(missing), 0)
    check("T8b 现有 arm.engine 类别数", len(parsed["meta"]["names"]), 80)
    check("T8c 现有 arm.engine 头长度合理",
          parsed["meta_len"] > 200 and parsed["meta_len"] < 4096, True)
else:
    skip("T8 现有 engine", "无 %s" % arm)

# ---------------------------------------------------------------- T9 真机 onnx
onnx_path = os.path.join(MODEL_DIR, "yolov8n.onnx")
if os.path.isfile(onnx_path):
    try:
        inspected = ee.inspect_onnx(onnx_path)
        check("T9a 类别数", inspected["classes"], 80)
        check("T9b imgsz", inspected["imgsz"], [640, 640])
        check("T9c names 来源", inspected["names_source"], "onnx_metadata")
        check("T9d names 数量", len(inspected["names"]), 80)
        check("T9e person 在 0 号位", inspected["names"]["0"], "person")
    except ImportError:
        skip("T9 onnx 探测", "本机无 onnx 包")
else:
    skip("T9 onnx 探测", "无 %s" % onnx_path)

print("")
print("RESULT PASS=%d FAIL=%d SKIP=%d" % (PASS, FAIL, SKIP))
sys.exit(0 if FAIL == 0 else 1)
