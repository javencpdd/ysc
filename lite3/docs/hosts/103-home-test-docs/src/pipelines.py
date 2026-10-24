# -*- coding: utf-8 -*-
"""GStreamer 管线模板与 URL 工具（worker 侧）。

设计依据：计划书 §5.9.2 管线模板、§5.9.4 凭据脱敏。
与现状硬编码管线的差异：去掉固定 location、可切 protocols/latency、
`file` 走 decodebin、输出尺寸参数化；**编码链本身不变**（低风险替换）。
"""

import re

_CRED_RE = re.compile(r'^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)'
                      r'(?P<user>[^/@]*)(?P<at>@)(?P<rest>.*)$')


def mask_url(url):
    """URL 凭据脱敏：`rtsp://user:pass@host/x` → `rtsp://user:***@host/x`。

    日志与 `worker_state.json` 里一律走这里，避免密码进日志（§5.9.4）。
    """
    if not url:
        return url
    m = _CRED_RE.match(str(url))
    if not m:
        return url
    user = m.group('user')
    if ':' in user:                      # 只保留用户名，口令整段替换
        user = user.split(':', 1)[0] + ':***'
    return m.group('scheme') + user + m.group('at') + m.group('rest')


def build_source_pipeline(src):
    """按 source 配置节生成采集管线字符串。

    src 需含 type / rtsp_url / file_path / codec / decoder / transport /
    latency_ms / out_width / out_height。缺键走保守默认。
    """
    src = src or {}
    w = int(src.get("out_width") or 640)
    h = int(src.get("out_height") or 360)
    tail = (" ! nvvidconv ! video/x-raw,format=BGRx"
            " ! videoscale ! video/x-raw,width=%d,height=%d"
            " ! videoconvert ! video/x-raw,format=BGR"
            " ! queue max-size-buffers=5 max-size-bytes=0 "
            "max-size-time=50000000 leaky=downstream"
            " ! appsink name=sink sync=false max-buffers=1 drop=1" % (w, h))

    if src.get("type") == "file":
        head = 'filesrc location="%s"' % (src.get("file_path") or "",)
        mid = "decodebin"
        return head + " ! " + mid + tail

    head = ('rtspsrc location="%s" protocols=%s latency=%d drop-on-latency=true'
            % (src.get("rtsp_url") or "",
               src.get("transport") or "udp",
               int(src.get("latency_ms") or 200)))
    codec = src.get("codec") or "h264"
    dec = src.get("decoder") or "hw"
    if dec == "auto":
        mid = "decodebin"
    elif codec == "h265":
        # 与现状 h264 链同构：depay → parse → 硬解 → NVMM
        mid = ("rtph265depay ! h265parse config-interval=1 ! nvv4l2decoder"
               " ! video/x-raw(memory:NVMM)")
    else:
        mid = ("rtph264depay ! h264parse config-interval=1 ! nvv4l2decoder"
               " ! video/x-raw(memory:NVMM)")
    return head + " ! " + mid + tail
