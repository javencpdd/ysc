#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
m20-ai-sampler —— M20 Pro 视频流 -> AI 识别服务 采样器

做法：常驻 ffmpeg 从本机 MediaMTX 抽帧（避免单次启动 1.6-2.0s 的 RTSP 握手开销），
      逐帧 POST 到 AI 识别服务的 /api/v1/tasks/{capability_id}，
      结构化结果写 JSONL，原始帧进环形缓冲，命中告警规则才存结果图。

命名约定（重要）：
  脚本/路径/命令行 不得包含 push_video / v4l2 / gst-launch 字样 —— 上游 restart.sh
  会 pkill -f 无差别匹配，会误杀本进程。本项目统一使用 m20-ai-sampler。

配置：环境变量（见下方 DEFAULTS），建议由 /opt/ai-detect/sampler.env 提供。
依赖：python3 + requests（196 主机已具备），ffmpeg。
"""

import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

# ----------------------------- 配置 -----------------------------
DEFAULTS = {
    "AI_BASE": "http://jsxy.aihyzh.com:30881",
    "CAP_ID": "ai-04-yolov8-object-detection",
    # 源地址：装在 196 上用 rtsp://127.0.0.1:8554/video1|video2
    #         装在 SRS 服务器(172.31.68.227)上用 rtmp://127.0.0.1:1936/live/m20pro-f|m20pro-b
    "SRC_F": "rtsp://127.0.0.1:8554/video1",
    "SRC_B": "rtsp://127.0.0.1:8554/video2",
    "CAM_NAME_F": "front",
    "CAM_NAME_B": "back",
    "ENABLE_F": "1",
    "ENABLE_B": "0",
    "FFMPEG_EXTRA": "",        # 追加到 ffmpeg 的额外参数，例："-fflags nobuffer -rw_timeout 10000000"
    "FPS": "1",
    "JPEG_Q": "3",
    "TIMEOUT": "10",
    "RETRY_MAX": "30",
    "RING_MAX_MB": "200",
    "ALERT_LABELS": "person,fire,smoke",
    "ALERT_SCORE": "0.60",
    "SAVE_RESULT_IMAGE": "false",
    "BASE_DIR": "/opt/ai-detect",
    "PARAMS_JSON": "",          # 例：{"obj_thresh":0.3,"nms_thresh":0.45}
    "FRESH_AGE_SEC": "0.8",     # 小于该"年龄"的帧先不读，防止读到半截文件
    "SOURCE_DOWN_SEC": "30",    # 多久没有新帧则记一次 source_down 心跳
}

CFG = {k: os.environ.get(k, v) for k, v in DEFAULTS.items()}

BASE = CFG["BASE_DIR"]
DIR_SPOOL = os.path.join(BASE, "spool")
DIR_RAW = os.path.join(BASE, "raw")
DIR_RES = os.path.join(BASE, "results")
DIR_ALERT = os.path.join(BASE, "alerts")
DIR_LOG = os.path.join(BASE, "log")
for d in (DIR_SPOOL, DIR_RAW, DIR_RES, DIR_ALERT, DIR_LOG):
    os.makedirs(d, exist_ok=True)

ALERT_LABELS = [s.strip() for s in CFG["ALERT_LABELS"].split(",") if s.strip()]
ALERT_SCORE = float(CFG["ALERT_SCORE"])
RING_MAX = int(float(CFG["RING_MAX_MB"]) * 1024 * 1024)
PARAMS = json.loads(CFG["PARAMS_JSON"]) if CFG["PARAMS_JSON"].strip() else {}

CAMERAS = []
if CFG["ENABLE_F"] == "1":
    CAMERAS.append((CFG["CAM_NAME_F"], CFG["SRC_F"]))
if CFG["ENABLE_B"] == "1":
    CAMERAS.append((CFG["CAM_NAME_B"], CFG["SRC_B"]))

URL_TASK = "%s/api/v1/tasks/%s" % (CFG["AI_BASE"].rstrip("/"), CFG["CAP_ID"])

_running = True


def _stop(signum, frame):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def log(msg):
    line = "[%s] %s" % (datetime.now().isoformat(timespec="milliseconds"), msg)
    print(line, flush=True)
    try:
        with open(os.path.join(DIR_LOG, "sampler.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ----------------------------- HTTP -----------------------------
try:
    import requests
except ImportError:  # pragma: no cover
    log("FATAL: 缺少 requests（196 主机应已具备）")
    sys.exit(1)

SESSION = requests.Session()


def detect(jpeg_bytes, filename):
    """返回 (ok, payload_or_error, elapsed_wall_ms)"""
    t0 = time.time()
    try:
        r = SESSION.post(
            URL_TASK,
            files={"file": (filename, jpeg_bytes, "image/jpeg")},
            data=PARAMS or None,
            timeout=float(CFG["TIMEOUT"]),
        )
    except Exception as e:
        return False, "EXC:%s" % e, int((time.time() - t0) * 1000)
    wall = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return False, "HTTP%d:%s" % (r.status_code, r.text[:200]), wall
    try:
        return True, r.json(), wall
    except Exception:
        return False, "BAD_JSON", wall


# ----------------------------- 工具 -----------------------------
def jsonl_path():
    return os.path.join(DIR_RES, "%s.jsonl" % datetime.now().strftime("%Y%m%d"))


def append_jsonl(rec):
    with open(jsonl_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def maybe_save_result_image(payload, stem):
    if CFG["SAVE_RESULT_IMAGE"].lower() != "true":
        return None
    img = payload.get("result_image") or ""
    if not img.startswith("data:") or "," not in img:
        return None
    try:
        raw = base64.b64decode(img.split(",", 1)[1])
    except Exception:
        return None
    p = os.path.join(DIR_ALERT, "%s.jpg" % stem)
    with open(p, "wb") as f:
        f.write(raw)
    return p


def is_alert(items):
    for it in items:
        if it.get("label") in ALERT_LABELS and float(it.get("score", 0)) >= ALERT_SCORE:
            return True
    return False


def ring_enforce():
    """raw/ 超过配额则删最旧（跨相机统一计算）"""
    entries = []
    total = 0
    for root, _, files in os.walk(DIR_RAW):
        for fn in files:
            p = os.path.join(root, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            entries.append((os.path.getmtime(p), p, sz))
            total += sz
    if total <= RING_MAX:
        return
    entries.sort()
    for _, p, sz in entries:
        if total <= RING_MAX:
            break
        try:
            os.remove(p)
            total -= sz
        except OSError:
            pass


def spawn_ffmpeg(cam, src):
    outdir = os.path.join(DIR_SPOOL, cam)
    os.makedirs(outdir, exist_ok=True)
    cmd = ["ffmpeg", "-loglevel", "error"]
    if src.startswith("rtsp://"):
        cmd += ["-rtsp_transport", "tcp"]
    elif src.startswith("rtmp://"):
        cmd += ["-f", "flv"]          # RTMP 必须显式声明封装格式
    if CFG["FFMPEG_EXTRA"].strip():
        cmd += CFG["FFMPEG_EXTRA"].split()
    cmd += [
        "-i", src,
        "-vf", "fps=%s" % CFG["FPS"],
        "-q:v", CFG["JPEG_Q"],
        "-strftime", "1",
        "-f", "image2",
        os.path.join(outdir, "%Y%m%d_%H%M%S.jpg"),
    ]
    log("spawn ffmpeg cam=%s src=%s fps=%s" % (cam, src, CFG["FPS"]))
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


# ----------------------------- 主循环 -----------------------------
def main():
    if not CAMERAS:
        log("FATAL: 没有启用任何相机（ENABLE_F/ENABLE_B 至少开一个）")
        return 1

    procs = {cam: spawn_ffmpeg(cam, src) for cam, src in CAMERAS}
    backoff = 1.0
    last_frame_ts = {cam: time.time() for cam, _ in CAMERAS}
    last_heartbeat = {cam: 0.0 for cam, _ in CAMERAS}

    log("start cap=%s cameras=%s ring=%dMB" % (CFG["CAP_ID"], [c for c, _ in CAMERAS], RING_MAX // 1024 // 1024))

    while _running:
        progressed = False

        for cam, src in CAMERAS:
            p = procs.get(cam)
            if p is None or p.poll() is not None:
                rc = None if p is None else p.returncode
                log("ffmpeg cam=%s exited rc=%s, respawn in %.0fs" % (cam, rc, backoff))
                time.sleep(backoff)
                if not _running:
                    break
                procs[cam] = spawn_ffmpeg(cam, src)
                continue

            outdir = os.path.join(DIR_SPOOL, cam)
            try:
                names = sorted(n for n in os.listdir(outdir) if n.endswith(".jpg"))
            except OSError:
                names = []
            if not names:
                if time.time() - last_heartbeat[cam] > float(CFG["SOURCE_DOWN_SEC"]):
                    last_heartbeat[cam] = time.time()
                    append_jsonl({"v": 1, "ts_host": datetime.now().isoformat(timespec="milliseconds"),
                                  "host": os.uname().nodename, "cam": cam, "cap": CFG["CAP_ID"],
                                  "event": "source_down", "spool": 0})
                    log("heartbeat cam=%s source_down" % cam)
                continue

            now = time.time()
            fresh = float(CFG["FRESH_AGE_SEC"])
            for name in names:
                fp = os.path.join(outdir, name)
                try:
                    if now - os.path.getmtime(fp) < fresh:
                        break  # 可能还在写，先不碰（名字有序，后面的更新）
                    with open(fp, "rb") as f:
                        data = f.read()
                except OSError:
                    continue
                if not data:
                    continue

                last_frame_ts[cam] = time.time()
                last_heartbeat[cam] = last_frame_ts[cam]
                stem = "%s_%s" % (cam, name[:-4])
                ok, payload, wall = detect(data, name)

                if not ok:
                    backoff = min(backoff * 2, float(CFG["RETRY_MAX"]))
                    log("detect FAIL cam=%s frame=%s err=%s backoff=%.0fs" % (cam, name, payload, backoff))
                    append_jsonl({"v": 1, "ts_host": datetime.now().isoformat(timespec="milliseconds"),
                                  "host": os.uname().nodename, "cam": cam, "cap": CFG["CAP_ID"],
                                  "event": "detect_fail", "frame": name, "error": str(payload)[:200],
                                  "e2e_ms": wall})
                    time.sleep(backoff)
                    break  # 退避期间不再发，帧留在 spool 待重试

                backoff = 1.0
                progressed = True
                items = (payload.get("results") or {}).get("items") or []
                rec = {
                    "v": 1,
                    "ts_host": datetime.now().isoformat(timespec="milliseconds"),
                    "host": os.uname().nodename,
                    "cam": cam,
                    "cap": payload.get("capability", CFG["CAP_ID"]),
                    "frame": name,
                    "frame_sha1": hashlib.sha1(data).hexdigest(),
                    "frame_bytes": len(data),
                    "http": 200,
                    "elapsed_ms": payload.get("elapsed_ms"),
                    "device": payload.get("device"),
                    "provider": payload.get("provider"),
                    "params": payload.get("params", {}),
                    "items": [{k: it.get(k) for k in ("label", "class_id", "score", "box", "box_norm") if k in it}
                              for it in items],
                    "n_items": len(items),
                    "e2e_ms": wall,
                    "result_image_saved": False,
                }
                if is_alert(items):
                    saved = maybe_save_result_image(payload, stem)
                    rec["result_image_saved"] = bool(saved)
                    rec["alert"] = True
                    if saved:
                        rec["alert_path"] = saved
                    log("ALERT cam=%s frame=%s n=%d path=%s" % (cam, name, len(items), saved))
                append_jsonl(rec)

                # 帧移入环形缓冲
                dst_dir = os.path.join(DIR_RAW, cam)
                os.makedirs(dst_dir, exist_ok=True)
                try:
                    shutil.move(fp, os.path.join(dst_dir, name))
                except OSError:
                    pass

        ring_enforce()
        if not progressed:
            time.sleep(0.5)

    for p in procs.values():
        try:
            p.terminate()
        except Exception:
            pass
    log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
