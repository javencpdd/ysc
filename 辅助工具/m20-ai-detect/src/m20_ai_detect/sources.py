"""视频源适配层：把 ``type://...`` 翻译成 ffmpeg 能吃的命令行片段（ADR-016）。

为什么要这一层
--------------
1. **源不止 RTSP**：RTMP（Lite3 的发布链路）、本地相机、文件回放、MJPEG over HTTP，
   各自的 ffmpeg 参数都不一样，散落各处必然漏。
2. **本地相机必须"绕着写"**：``config.FORBIDDEN_TOKENS`` 禁掉了 ``v4l2`` 这个词
   （上游 ``restart.sh`` 会 ``pkill -f`` 误杀），所以用户写的是 ``device:///dev/video0``，
   由本模块在**构建命令行时**才展开成 ``-f v4l2 -i /dev/video0``。
   env 里永远不出现禁词 ⇒ 配置能过校验；命令行里出现 ⇒ 仍需平台显式放行。

约定
----
* ``resolve()`` 只做纯函数变换，不碰网络、不读文件 —— 因此可单测；
* 返回的 ``target`` 是给 ``-i`` 的实参，``input_args`` 必须放在 ``-i`` **之前**；
* 任何新 scheme 都先在 ``KNOWN_TYPES`` 登记，否则 ``resolve()`` 按 ``raw`` 处理
  （向后兼容：裸路径 / 老式 rtsp:// 地址不受影响）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import FORBIDDEN_TOKENS, Config, Source

#: 已知类型。``raw`` = 没有 scheme（裸路径或老式写法），按 ffmpeg 默认处理。
KNOWN_TYPES: Tuple[str, ...] = (
    "rtsp", "rtmp", "device", "file", "http", "https", "onvif", "raw",
)

#: 需要 -rtsp_transport 的协议标记写法：rtsp+tcp://、rtmp+flv:// 之类
_PLUS_RE = re.compile(r"^(?P<base>[a-z]+)\+(?P<opt>[a-z0-9]+)://(?P<rest>.*)$", re.I)
_SCHEME_RE = re.compile(r"^(?P<base>[a-z]+)://(?P<rest>.*)$", re.I)

#: 这些 scheme 抓单帧时要低延迟参数（否则 ffmpeg 先缓冲一大段，实测 2.7~6.6s）
LOW_DELAY_TYPES = ("rtsp", "rtmp")

#: device:// 展开时会带上这个词 —— 属于 FORBIDDEN_TOKENS，需要平台显式放行
LOCAL_DEVICE_TOKENS = ("v4l2",)


@dataclass(frozen=True)
class Resolved:
    """解析结果。``input_args`` 必须置于 ``-i <target>`` 之前。"""

    type: str
    target: str
    input_args: Tuple[str, ...] = ()
    low_delay: bool = False
    #: True ⇒ 展开出的命令行含 FORBIDDEN_TOKENS，需平台显式放行（M20AI_ALLOW_LOCAL_DEVICE）
    needs_local_ok: bool = False

    def ffmpeg_input(self) -> List[str]:
        """``[...input_args, '-i', target]``。"""
        return list(self.input_args) + ["-i", self.target]


def _device_target(rest: str) -> str:
    """``device:///dev/video0`` → ``/dev/video0``；``device://0`` → ``/dev/video0``。"""
    rest = rest.strip()
    if not rest:
        return "/dev/video0"
    if rest.startswith("/"):
        return rest
    if rest.isdigit():
        return "/dev/video" + rest
    return rest


def resolve(src: Source) -> Resolved:
    """纯函数：源地址 → ffmpeg 输入片段。未知 scheme 按 raw 处理（不报错）。"""
    uri = (src.uri or "").strip()
    if not uri:
        return Resolved(type="raw", target="")

    m = _PLUS_RE.match(uri)
    if m:
        base, opt, rest = m.group("base").lower(), m.group("opt").lower(), m.group("rest")
        if base == "rtsp":
            proto = opt if opt in ("tcp", "udp", "http") else "tcp"
            return Resolved(
                type="rtsp",
                target="rtsp://" + rest,
                input_args=("-rtsp_transport", proto),
                low_delay=True,
            )
        if base == "rtmp":
            return Resolved(
                type="rtmp", target="rtmp://" + rest, input_args=("-f", "flv"), low_delay=True
            )
        if base in ("http", "https"):
            scheme = "http" if base == "http" else "https"
            target = "%s://%s" % (scheme, rest)
            demuxer = _is_mjpeg(rest) if opt == "auto" else opt
            return Resolved(
                type=scheme,
                target=target,
                input_args=("-f", demuxer) if demuxer else (),
            )

    m = _SCHEME_RE.match(uri)
    if not m:
        # 没有 scheme —— 裸路径/老式地址，行为与改造前一致
        return Resolved(type="raw", target=uri)

    base, rest = m.group("base").lower(), m.group("rest")
    if base == "rtsp":
        # ★历史行为：RTSP 一律强制 TCP（GOS 实测 UDP 在弱网下花屏/连接不上）
        proto = (src.transport or "auto").lower()
        if proto not in ("tcp", "udp"):
            proto = "tcp"
        return Resolved(
            type="rtsp",
            target="rtsp://" + rest,
            input_args=("-rtsp_transport", proto),
            low_delay=True,
        )
    if base == "rtmp":
        return Resolved(
            type="rtmp", target="rtmp://" + rest, input_args=("-f", "flv"), low_delay=True
        )
    if base in ("http", "https"):
        args = ("-f", "mjpeg") if _is_mjpeg(rest) else ()
        return Resolved(type=base, target="%s://%s" % (base, rest), input_args=args)
    if base == "device":
        # 唯一会展开出禁词的类型
        return Resolved(
            type="device",
            target=_device_target(rest),
            input_args=("-f", "v4l2"),
            low_delay=True,
            needs_local_ok=True,
        )
    if base == "file":
        path = "/" + rest.lstrip("/") if not rest.startswith("/") else rest
        return Resolved(type="file", target=path)
    if base == "onvif":
        # 需要先经 ONVIF 握手拿到真实 RTSP URL（见 discover.py）；这里只能报"未解析"
        return Resolved(type="onvif", target=uri)
    return Resolved(type=base, target=uri)


def _is_mjpeg(rest: str) -> bool:
    """``http://h/cam.mjpg?x=1`` 也要认 —— 只看 ? 之前的部分。"""
    path = rest.split("?", 1)[0].split("#", 1)[0].lower()
    return path.endswith((".mjpg", ".mjpeg"))


# ---------------------------------------------------------------- 安全
def assert_safe(
    cmd: List[str], allow_local: bool = False, forbidden: Tuple[str, ...] = ()
) -> None:
    """防止命令行里出现上游 pkill 的关键词（见 config.FORBIDDEN_TOKENS）。

    ``allow_local=True`` 放行 ``v4l2`` —— 只有当用户在 env 里显式写了
    ``device://`` **且** 平台允许（``M20AI_ALLOW_LOCAL_DEVICE=1``）时才应该为 True。
    """
    tokens = forbidden or FORBIDDEN_TOKENS
    joined = " ".join(cmd)
    for token in tokens:
        if token in LOCAL_DEVICE_TOKENS and allow_local:
            continue
        if token in joined:
            raise RuntimeError(
                "ffmpeg 命令行含禁用关键词 %r，会被机器人上游 restart.sh 误杀：%s"
                % (token, joined)
            )


def merge_extra(res: Resolved, src: Source, cfg: Optional[Config] = None) -> List[str]:
    """按序拼出 `-i` 之前的全部参数：协议默认 → 全局 extra → 逐路 extra。

    逐路在后，方便用逐路参数覆盖全局（例如全局 -vf scale，某路再 -vf 修正）。
    """
    args: List[str] = list(res.input_args)
    if cfg is not None:
        args += list(cfg.ffmpeg_extra)
    args += list(src.extra)
    return args
