# -*- coding: utf-8 -*-
"""P4 单测 B：console 侧模型逻辑（multipart / engine 头 / 名称 / 状态机）。

不启动 HTTP 服务、不碰真机路径：import server 只用到它的纯函数与 ExportManager。
双跑：本地 py3.13 与真机 py3.8.10。

用法：python3 p4-unit.py
"""

import json
import os
import shutil
import sys
import tempfile

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


def expect_error(name, fn, needle):
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
    FAIL += 1
    print("FAIL  %s: 未抛 ValueError" % name)


BOUND = "----p4boundary123"
CTYPE = "multipart/form-data; boundary=" + BOUND


def build_multipart(fields):
    """fields: [(name, filename_or_None, bytes)] → 原始 body。"""
    out = []
    for name, filename, data in fields:
        out.append(("--" + BOUND).encode())
        if filename:
            out.append(('Content-Disposition: form-data; name="%s"; filename="%s"'
                        % (name, filename)).encode())
            out.append(b"Content-Type: application/octet-stream")
        else:
            out.append(('Content-Disposition: form-data; name="%s"' % name).encode())
        out.append(b"")
        out.append(data)
    out.append(("--" + BOUND + "--").encode())
    out.append(b"")
    return b"\r\n".join(out)


# ---------------------------------------------------------------- P1 multipart
payload = b"\x08\x07\x12\x04fakeonnxdata" + b"\x00" * 80
body = build_multipart([("onnx", "yolov8n.onnx", payload),
                        ("names_json", None, b'["person","dog"]')])
parts = s.parse_multipart(body, CTYPE)
check("P1a 部件数", sorted(parts.keys()), ["names_json", "onnx"])
check("P1b 文件字节一致", parts["onnx"]["data"], payload)
check("P1c 文件名", parts["onnx"]["filename"], "yolov8n.onnx")
check("P1d 文本字段", parts["names_json"]["data"], b'["person","dog"]')
check("P1e 非 multipart", s.parse_multipart(b"abc", "application/json"), {})
check("P1f 空体", s.parse_multipart(b"", CTYPE), {})
check("P1g 坏 boundary", s.parse_multipart(body, "multipart/form-data; boundary=zzz"), {})

# ---------------------------------------------------------------- P2 engine 头
tmpdir = tempfile.mkdtemp(prefix="p4srv-")
try:
    meta = {"stride": 32, "task": "detect", "batch": 1, "imgsz": [640, 640],
            "names": {"0": "person", "1": "dog"}}
    raw_meta = json.dumps(meta).encode("utf-8")
    good = os.path.join(tmpdir, "good.engine")
    with open(good, "wb") as fh:
        fh.write(len(raw_meta).to_bytes(4, "little", signed=True))
        fh.write(raw_meta)
        fh.write(b"P" * 1024)
    parsed, err = s.read_engine_meta(good)
    check("P2a 正常解析 err", err, None)
    check("P2b names", parsed["names"], meta["names"])
    check("P2c plan 长度", parsed["_plan_len"], 1024)
    check("P2d 文件大小", parsed["_size"], 4 + len(raw_meta) + 1024)

    bads = {
        "空": b"",
        "过短": b"\x01\x02",
        "meta_len 越界": b"\x00\x10\x00\x00" + b"{}",
        "非 JSON": b"\x03\x00\x00\x00abc",
        "缺 key": (len(b'{"stride":32}').to_bytes(4, "little", signed=True)
                   + b'{"stride":32}' + b"P"),
    }
    for label, data in bads.items():
        p = os.path.join(tmpdir, "bad.engine")
        with open(p, "wb") as fh:
            fh.write(data)
        got, err = s.read_engine_meta(p)
        check("P2e %s 拒绝" % label, got, None)
        check_true("P2f %s 有错误信息" % label, bool(err))
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ---------------------------------------------------------------- P3 names
check("P3a list", s.normalize_names(["person", "dog"]),
      {"0": "person", "1": "dog"})
check("P3b dict int 键", s.normalize_names({0: "person", 1: "dog"}),
      {"0": "person", "1": "dog"})
check("P3c 字面量字符串", s.normalize_names("{0: 'person', 1: 'dog'}"),
      {"0": "person", "1": "dog"})
expect_error("P3d 空字符串", lambda: s.normalize_names("   "), "不能为空")
expect_error("P3e 非法键", lambda: s.normalize_names({"x": "person"}), "键")
check("P3f 合法校验", s.validate_names({"0": "person", "1": "dog"}, 2), [])
expect_error("P3g 数量不匹配", lambda: s.validate_names({"0": "person"}, 3), "类别数")
expect_error("P3h id 不连续", lambda: s.validate_names({"2": "dog"}, 1), "连续")

# ---------------------------------------------------------------- P4 路径
check("P4a 配置值", s.sanitize_engine_rel("../model/yolov8n_arm.engine"),
      "yolov8n_arm.engine")
check("P4b 子目录", s.sanitize_engine_rel("exports/a.engine"), "exports/a.engine")
check("P4c 缺省", s.sanitize_engine_rel(None), "yolov8n_arm.engine")
expect_error("P4d 绝对路径穿越", lambda: s.sanitize_engine_rel("../../etc/a.engine"), "不合法")
expect_error("P4e 非 engine", lambda: s.sanitize_engine_rel("a.onnx"), "engine")
expect_error("P4f 子目录穿越", lambda: s.sanitize_engine_rel("exports/../../x.engine"), "不合法")

# ---------------------------------------------------------------- P5 文本魔数
check("P5a 纯文本", s.looks_like_text(b"hello, this is a renamed txt file"), True)
check("P5b 空内容", s.looks_like_text(b""), True)
check("P5c 二进制", s.looks_like_text(b"\x08\x07\x00\x00binary"), False)
check("P5d 源码文本", s.looks_like_text(b"# -*- coding: utf-8 -*-\nimport os\n"), True)

# ---------------------------------------------------------------- P6 导出状态机
mgr = s.ExportManager()
snap = mgr.snapshot()
check("P6a 初始 idle", snap["state"], "idle")
check("P6b 初始不忙", mgr.busy(), False)
check("P6c log 独立拷贝", (snap["log"].append("x"), len(mgr.snapshot()["log"]))[1], 0)


def fake_run(*a, **k):                            # 不出真进程
    return None


mgr._run = fake_run
mgr.start("a" * 24 + ".onnx", "/tmp/x.onnx", {"0": "person"},
          "exports/t.engine", 512, True)
check("P6d 状态 exporting", mgr.snapshot()["state"], "exporting")
check("P6e busy", mgr.busy(), True)
ok, why = mgr.start("b" * 24 + ".onnx", "/tmp/y.onnx", {"0": "person"},
                    "exports/t2.engine", 512, True)
check("P6f 单任务拒绝", ok, False)
check_true("P6g 拒绝原因", "单任务" in (why or ""))
mgr._fail("模拟失败")
check("P6h failed", mgr.snapshot()["state"], "failed")
check("P6i 失败后不忙", mgr.busy(), False)
check_true("P6j 失败日志", any("模拟失败" in ln for ln in mgr.snapshot()["log"]))

# ---------------------------------------------------------------- P7 版本
check("P7a 版本号", s.VERSION, "2.1.0-p4")

print("")
print("RESULT PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
