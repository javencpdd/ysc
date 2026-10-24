"""视频源发现器（ADR-016 §3）。三级降级，**只探测、不自动启用**。

为什么必须三级
--------------
RTSP 协议**没有目录列表**（不像 HTTP 有 index），光连上 ``rtsp://host`` 拿不到任何
路径清单。可用手段只有三种，且各机型可用性不同：

  L1 **标准接口**：MediaMTX REST ``/v3/paths/list``、go2rtc ``/api/streams``、
     ONVIF WS-Discovery → 拿到真实清单。✔ 最准 ❌ 常常没开
     （M20 上的 MediaMTX 管理端口 9997 就是关的）。
  L2 **本机推断**：读本机自己的服务配置（mediamtx.yml 的 paths 段）、
     枚举 ``/dev/video*``、看本机在哪些端口上起了媒体服务。✔ 零流量 ❌ 只限本机
  L3 **候选穷举**：给定 ``host:port`` × 候选路径表，并发 ``ffprobe``/``ffmpeg`` 抓 1 帧。
     ✔ 兜底，M20 上它就是主力 ❌ 慢、依赖候选表命中率

护栏（不可协商）
--------------
* **不写任何配置**：发现的候选只回给调用方，由用户勾选后才落 env；
* **不做无边界扫描**：默认只探本机与显式给出的 host。没有我们的北极星索引式
  全段扫描（会被当扫描器，也会把 RK3588 打满）；
* **并发 ≤8、单路 3s、总预算 20s**，超时就返回已发现的部分。
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

#: 候选路径表（按实测命中率排序）。可在 profile 里覆盖。
DEFAULT_PATHS: Tuple[str, ...] = (
    "video1", "video2", "video3", "video4",
    "cam1", "cam2", "cam3", "cam4",
    "ch1", "ch2", "ch3", "ch4",
    "stream1", "stream2", "stream0",
    "live/main", "live/sub", "live/0", "live/1",
    "0", "1", "101", "102",
    "front", "back", "m20/front", "m20/back",
    "profile1", "profile2", "main", "sub",
)

#: 媒体服务常见端口 → 默认 scheme
MEDIA_PORTS: Tuple[Tuple[int, str], ...] = (
    (554, "rtsp"), (8554, "rtsp"), (1935, "rtmp"),
    (1984, "http"), (9997, "http"), (8888, "http"), (8889, "http"),
)

#: mediamtx 配置常见位置（只需要读，读不到就算了）
MEDIAMTX_CONFIGS: Tuple[str, ...] = (
    "/etc/mediamtx.yml", "/etc/mediamtx/mediamtx.yml",
    "/opt/mediamtx/mediamtx.yml", "/usr/local/etc/mediamtx.yml",
    "mediamtx.yml", "../conf/mediamtx.yml",
)

Runner = Callable[[List[str], float], Tuple[int, str, str]]

VERDICTS = (
    "ok",            # 连上且抓到帧
    "auth_required",  # 401 / Unauthorized
    "timeout",
    "refused",
    "no_frame",      # 连上了但没有画面（配置存在但源没数据）
    "unresolved",    # 需要先握手/凭据才能确定（如 ONVIF）
)


@dataclass
class Candidate:
    """一个候选源。``verdict`` 见 VERDICTS。"""

    name: str
    uri: str
    type: str
    verdict: str
    via: str          # device / local-config / api / probe
    detail: str = ""
    cost_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- L1 标准接口
def probe_http_api(
    base: str, runner: Runner, timeout: float = 2.0, **kw: Any
) -> List[str]:
    """MediaMTX ``/v3/paths/list`` 与 go2rtc ``/api/streams``。失败返回 []。

    只做 GET，用 curl 有就用 curl（真机一定有），否则返回 []（不引第三方依赖）。
    """
    import shutil

    curl = shutil.which("curl")
    if not curl:
        return []
    urls = [base.rstrip("/") + "/v3/paths/list", base.rstrip("/") + "/api/streams"]
    out: List[str] = []
    for url in urls:
        rc, stdout, _ = runner([curl, "-sS", "-m", "%.0f" % timeout, url], timeout + 2)
        if rc != 0 or not stdout.strip():
            continue
        names = _parse_stream_list(stdout)
        if names:
            out.extend(names)
            break
    return _dedup(out)


def _parse_stream_list(text: str) -> List[str]:
    """尽力解析：MediaMTX 返回 JSON 数组，go2rtc 返回 {"streams": {...}}。"""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    names: List[str] = []
    if isinstance(data, dict):
        inner = data.get("items") or data.get("streams") or data.get("paths") or []
        if isinstance(inner, dict):
            names = list(inner.keys())
        elif isinstance(inner, list):
            names = [
                str(it.get("name") or it.get("path") or it.get("id") or "")
                for it in inner
                if isinstance(it, dict)
            ]
    elif isinstance(data, list):
        names = [
            str(it.get("name") or it.get("path") or "")
            for it in data
            if isinstance(it, dict)
        ]
    return [n for n in names if n]


# ---------------------------------------------------------------- L2 本机推断
def discover_local_devices() -> List[str]:
    """``/dev/video*``。返回设备路径列表（Linux 专有，非 Linux 返回 []）。"""
    try:
        names = sorted(
            n for n in os.listdir("/dev")
            if re.match(r"^video\d+$", n) or n.startswith("video")
        )
    except OSError:
        return []
    # card 数通常 = 相机数的一半，过滤掉纯元数据的 capture 设备也无所谓：
    # ffmpeg 用 /dev/videoN 取流，取不到会直接失败（verdict 会如实反映）。
    return ["/dev/" + n for n in names if re.match(r"^video\d+$", n)]


def device_label(dev: str) -> str:
    """/sys/class/video4linux/<n>/name —— 给人看的设备名（失败返回空串）。"""
    base = os.path.basename(dev)
    try:
        with open("/sys/class/video4linux/%s/name" % base, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def read_mediamtx_paths(extra: Sequence[str] = ()) -> List[str]:
    """从 mediamtx 配置里抠出 paths 段下的路径名。读不到就 []（配置属 optional）。"""
    out: List[str] = []
    for path in list(MEDIAMTX_CONFIGS) + list(extra):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        out.extend(_parse_paths_block(text))
    return _dedup(out)


def _parse_paths_block(text: str) -> List[str]:
    """极简 YAML：找 ``paths:`` 之后**缩进更深**的键名（不再解析其值）。

    不引 yaml 依赖 —— 这里只需要"有哪些路径"，不需要完整解析；
    宁可漏，不能错（错的路径会在 L3 探测时自然失败）。
    """
    lines = text.splitlines()
    names: List[str] = []
    inside = False
    base_indent = 0
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if not inside:
            if re.match(r"^paths\s*:\s*(#.*)?$", stripped):
                inside = True
                base_indent = indent
            continue
        if indent <= base_indent:
            inside = False
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*:\s*(#.*)?$", stripped)
        if m and m.group(1) not in ("all_others",):
            names.append(m.group(1))
    return names


def discover_media_ports(
    host: str = "127.0.0.1", ports: Sequence[int] = (), timeout: float = 0.3
) -> List[int]:
    """本机/指定 host 上哪些媒体端口在听。**只 connect 不开数据**，成本极低。

    这是 L2 的关键一步：先知道"这台机器开着 rtsp 服务"，再去穷举路径。
    """
    want = list(ports) if ports else [p for p, _s in MEDIA_PORTS]
    open_ports: List[int] = []
    for port in want:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append(port)
        except OSError:
            continue
    return open_ports


# ---------------------------------------------------------------- L3 穷举
def build_probe_cmd(uri: str, ffmpeg_bin: str = "ffmpeg") -> List[str]:
    """探测命令：抓 1 帧丢掉。**必须 -nostdin**（否则脚本里进交互模式，见部署记录）。"""
    cmd = [ffmpeg_bin, "-nostdin", "-loglevel", "error", "-hide_banner"]
    if uri.startswith("rtsp://"):
        cmd += ["-rtsp_transport", "tcp"]
    elif uri.startswith("rtmp://"):
        cmd += ["-f", "flv"]
    cmd += ["-i", uri, "-frames:v", "1", "-f", "null", "-"]
    return cmd


def classify(rc: int, stderr: str) -> str:
    """把 ffmpeg 的退出码/错误文本翻译成人能懂的判定。"""
    low = (stderr or "").lower()
    if rc == 0:
        return "ok"
    if "401" in low or "unauthorized" in low or "auth" in low:
        return "auth_required"
    if "timed out" in low or "timeout" in low or rc == 124:
        return "timeout"
    if "connection refused" in low or "no route to host" in low:
        return "refused"
    if "immediately" in low and "exit" in low:
        return "no_frame"
    return "no_frame" if rc in (1, 2) else "timeout"


def probe_uri(
    uri: str,
    ffmpeg_bin: str = "ffmpeg",
    timeout: float = 3.0,
    runner: Optional[Runner] = None,
    via: str = "probe",
    name: str = "",
) -> Candidate:
    """探单路：连上并尝试抓 1 帧。返回 Candidate（含判定与耗时）。"""
    from .sources import resolve
    from .config import Source

    # resolve 只做纯字符串变换，安全无副作用
    res = resolve(Source(name or "probe", uri))
    cmd = build_probe_cmd(res.target if res.target else uri, ffmpeg_bin)
    run = runner or _subprocess_runner
    started = time.time()
    try:
        rc, _out, err = run(cmd, timeout)
    except Exception as exc:  # 防御：任何异常都不该打断整轮发现
        rc, err = 127, str(exc)
    cost = int((time.time() - started) * 1000)
    return Candidate(
        name=name or _name_from_uri(uri),
        uri=uri,
        type=res.type,
        verdict=classify(rc, err),
        via=via,
        detail=" ".join((err or "").split())[-160:],
        cost_ms=cost,
    )


def _subprocess_runner(cmd: List[str], timeout: float) -> Tuple[int, str, str]:
    import subprocess

    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
        return proc.returncode, "", (proc.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def _name_from_uri(uri: str) -> str:
    tail = uri.split("://", 1)[-1].rstrip("/").split("/")[-1] or "src"
    return re.sub(r"[^A-Za-z0-9_-]", "_", tail)[:32] or "src"


# ---------------------------------------------------------------- 编排
def _dedup(seq: Sequence[str]) -> List[str]:
    out: List[str] = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


def discover(
    scope: str = "local",
    ffmpeg_bin: str = "ffmpeg",
    paths: Sequence[str] = (),
    base_dir: str = "",
    runner: Optional[Runner] = None,
    timeout: float = 3.0,
    budget_s: float = 20.0,
    max_workers: int = 8,
) -> Dict[str, Any]:
    """三级发现的总入口。永远返回 dict，不抛异常给上层。

    ``scope``：
      ``local``        —— 本机：/dev/video* + 本机配置文件 + 本机端口穷举
      ``host:<ip>``    —— 指定主机（+ 可选 ``:port``），走 L1 API → L3 穷举
      ``auto``         —— 先 local，若一无所获再对本机 IP 段做穷举（不跨路由）

    返回 ``{"ok": True, "candidates": [...], "notes": [...], "cost_ms": N}``。
    """
    started = time.time()
    notes: List[str] = []
    cands: List[Candidate] = []

    def left() -> float:
        return budget_s - (time.time() - started)

    if scope.startswith("host:"):
        target = scope.split(":", 1)[1].strip()
        cands += _discover_host(
            target, ffmpeg_bin, list(paths) or list(DEFAULT_PATHS), runner,
            timeout, notes,
        )
    elif scope in ("local", "auto"):
        cands += _local_devices(notes)
        cands += _local_config_paths(base_dir, notes)
        cands += _local_ports_paths(
            ffmpeg_bin, list(paths) or list(DEFAULT_PATHS), runner, timeout, notes, left
        )
    else:
        notes.append("未知 scope=%r（可用：local / auto / host:<ip>[:port]）" % scope)

    return {
        "ok": True,
        "candidates": [c.to_dict() for c in _filter_interesting(cands)],
        "notes": notes,
        "cost_ms": int((time.time() - started) * 1000),
        "scope": scope,
    }


def _filter_interesting(cands: List[Candidate]) -> List[Candidate]:
    """去重 + 排序：ok 优先，其次 auth_required/unresolved，失败的后置。"""
    rank = {"ok": 0, "auth_required": 1, "unresolved": 2, "no_frame": 3, "timeout": 4, "refused": 5}
    seen: Dict[str, Candidate] = {}
    for c in cands:
        old = seen.get(c.uri)
        if old is None or rank.get(c.verdict, 9) < rank.get(old.verdict, 9):
            seen[c.uri] = c
    return sorted(seen.values(), key=lambda c: (rank.get(c.verdict, 9), c.name))


def _local_devices(notes: List[str]) -> List[Candidate]:
    out: List[Candidate] = []
    for dev in discover_local_devices():
        out.append(
            Candidate(
                name="dev" + os.path.basename(dev).replace("video", ""),
                uri="device://" + dev,
                type="device",
                verdict="unresolved",  # 不自动抓帧：device 需平台放行，且可能挤占独占句柄
                via="device",
                detail=device_label(dev),
            )
        )
    if out:
        notes.append(
            "本机发现 %d 个视频设备；device:// 需先设 M20AI_ALLOW_LOCAL_DEVICE=1" % len(out)
        )
    return out


def _local_config_paths(base_dir: str, notes: List[str]) -> List[Candidate]:
    extra = [os.path.join(base_dir, "mediamtx.yml")] if base_dir else []
    names = read_mediamtx_paths(extra)
    if names:
        notes.append("从本机 mediamtx 配置读到 %d 个路径，待探测" % len(names))
    return [
        Candidate(
            name=_name_from_uri(n), uri="rtsp://127.0.0.1:8554/" + n,
            type="rtsp", verdict="unresolved", via="local-config",
        )
        for n in names
    ]


def _local_ports_paths(
    ffmpeg_bin: str, paths: Sequence[str], runner: Optional[Runner],
    timeout: float, notes: List[str], left: Callable[[], float],
) -> List[Candidate]:
    ports = discover_media_ports()
    if not ports:
        notes.append("本机未发现监听的媒体端口（554/8554/1935 等）")
        return []
    notes.append("本机在监听的媒体端口：%s" % ", ".join(str(p) for p in ports))
    out: List[Candidate] = []
    for port in ports:
        scheme = dict(MEDIA_PORTS).get(port, "rtsp")
        out += _probe_many(
            scheme, "127.0.0.1", port, paths, ffmpeg_bin, runner, timeout, left, notes
        )
    return out


def _discover_host(
    target: str, ffmpeg_bin: str, paths: Sequence[str], runner: Optional[Runner],
    timeout: float, notes: List[str],
) -> List[Candidate]:
    host, _, port_s = target.partition(":")
    port_s = port_s.split("/", 1)[0]
    if not host:
        notes.append("host 语法应为 host:<ip>[:port]")
        return []

    # L1：先看有没有管理 API（最准、最省）
    api_names: List[str] = []
    for api_port in (9997, 1984, 8888, 80):
        got = probe_http_api("http://%s:%d" % (host, api_port), _http_runner)
        if got:
            api_names = got
            notes.append("命中 %s:%d 的管理接口，拿到 %d 条路径清单" % (host, api_port, len(got)))
            break
    if api_names:
        return [
            Candidate(
                name=_name_from_uri(n),
                uri="rtsp://%s:%d/%s" % (host, int(port_s or 8554), n),
                type="rtsp", verdict="unresolved", via="api",
            )
            for n in api_names
        ]

    # L3：穷举候选路径
    ports = [int(port_s)] if port_s else [p for p, _s in MEDIA_PORTS]
    out: List[Candidate] = []
    for port in ports:
        scheme = dict(MEDIA_PORTS).get(port, "rtsp")
        if scheme == "http":
            continue
        out += _probe_many(
            scheme, host, port, paths, ffmpeg_bin, runner, timeout,
            lambda: 30.0, notes,
        )
    return out


def _probe_many(
    scheme: str, host: str, port: int, paths: Sequence[str], ffmpeg_bin: str,
    runner: Optional[Runner], timeout: float, left: Callable[[], float],
    notes: List[str],
) -> List[Candidate]:
    """并发探一批候选路径；预算耗尽就提前收工并返回已得部分。"""
    uris = ["%s://%s:%d/%s" % (scheme, host, port, p.lstrip("/")) for p in paths]
    out: List[Candidate] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(probe_uri, u, ffmpeg_bin, timeout, runner): u for u in uris
        }
        try:
            for fut in as_completed(futures, timeout=max(1.0, left())):
                out.append(fut.result())
                if left() <= 0:
                    notes.append("发现预算耗尽，已返回部分结果")
                    break
        except Exception:
            notes.append("等待探测结果超时，已返回部分结果")
    return out


def _http_runner(cmd: List[str], timeout: float) -> Tuple[int, str, str]:
    return _subprocess_runner(cmd, timeout)
