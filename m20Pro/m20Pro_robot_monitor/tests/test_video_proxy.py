"""视频代理单测（T3.2–T3.4）：命令构造 + 降级状态，不需要真跑 ffmpeg。"""

import os

import pytest

from video.video_proxy import VideoProxy, DEFAULT_HLS_DIR


def test_cmd_uses_copy_and_tcp():
    """不转码（196 无硬编）+ TCP 传输（内网丢包环境）。"""
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir="/tmp/hls_x")
    cmd = p.build_cmd()
    joined = " ".join(cmd)
    assert "-c:v copy" in joined          # 关键：不转码
    assert "-rtsp_transport tcp" in joined
    assert "rtsp://127.0.0.1:8554/video1" in cmd
    assert cmd[-1].endswith("live.m3u8")
    assert "-hls_flags" in cmd and "delete_segments+append_list" in cmd


def test_cmd_targets_given_url_on_switch_source():
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir="/tmp/hls_x")
    cmd = p.build_cmd("rtsp://127.0.0.1:8554/video2")
    assert "video2" in " ".join(cmd)


def test_status_unavailable_when_nothing_produced(tmp_path):
    """降级：没有产物时 available=False（前端显示提示而非白屏）。"""
    p = VideoProxy("rtsp://x/video1", hls_dir=str(tmp_path))
    st = p.status()
    assert st["running"] is False
    assert st["available"] is False
    assert st["last_segment_age"] is None


def test_status_available_with_fresh_playlist(tmp_path):
    """有 m3u8 + 新鲜片段 → available=True。"""
    (tmp_path / "live.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    (tmp_path / "seg_0.ts").write_bytes(b"\x00" * 1024)
    p = VideoProxy("rtsp://x/video1", hls_dir=str(tmp_path))
    st = p.status()
    assert st["available"] is True
    assert st["last_segment_age"] is not None and st["last_segment_age"] < 5


def test_status_stale_when_segments_old(tmp_path, monkeypatch):
    """片段陈旧（上游断流）→ available=False，触发前端"视频中断"。"""
    (tmp_path / "live.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    seg = tmp_path / "seg_0.ts"
    seg.write_bytes(b"\x00" * 1024)
    old = os.path.getmtime(str(seg)) - 60
    os.utime(str(seg), (old, old))
    p = VideoProxy("rtsp://x/video1", hls_dir=str(tmp_path))
    assert p.status()["available"] is False


def test_start_reports_error_when_ffmpeg_missing(monkeypatch):
    """ffmpeg 不在 → 明确报错，不静默失败。"""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _n: None)
    p = VideoProxy("rtsp://x/video1", hls_dir="/tmp/hls_x")
    assert p.start() is False
    assert "ffmpeg" in (p.last_error or "")


def test_switch_updates_source_even_if_start_fails(monkeypatch):
    """切换前/后相机：URL 必须更新（启动失败不影响状态一致）。"""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _n: None)
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir="/tmp/hls_x")
    p.switch("rtsp://127.0.0.1:8554/video2")
    assert p.rtsp_url.endswith("video2")
    assert "video2" in " ".join(p.build_cmd())


# ---------------------------------------------------------------- 重启退避
def test_backoff_grows_when_process_dies_immediately(tmp_path):
    """★2026-10-18 修的真 bug：Popen 成功就重置退避 → 2s 一次无限重启。

    源站没推流时 ffmpeg 起来就 404 退出（存活 <1s），旧写法把
    `backoff = 2.0` 放在 Popen 成功之后，退避永远长不起来 ——
    真机实测连刷到第 14 次，每次都重建 RTSP 连接，纯白耗资源。
    """
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir=str(tmp_path))
    b = 2.0
    seen = []
    for _ in range(6):
        b = p.next_backoff(b, alive=0.8)      # 每次都秒退
        seen.append(b)
    assert seen == [4.0, 8.0, 16.0, 30.0, 30.0, 30.0], seen
    assert max(seen) <= 30.0                  # 封顶，不无限增长


def test_backoff_resets_after_process_lived_long_enough(tmp_path):
    """活够 STABLE_SECONDS = 真的出过流 → 退避重置回 2s。"""
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir=str(tmp_path))
    b = 2.0
    for _ in range(5):
        b = p.next_backoff(b, alive=0.5)
    assert b > 2.0                            # 已经涨上去了
    assert p.next_backoff(b, alive=p.STABLE_SECONDS) == 2.0
    assert p.next_backoff(b, alive=p.STABLE_SECONDS + 60) == 2.0


def test_backoff_never_below_two_seconds(tmp_path):
    """传入比 2s 还小的退避也不该算出更短的间隔（防止抖成死循环）。"""
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir=str(tmp_path))
    assert p.next_backoff(0.0, alive=0.1) >= 4.0
    assert p.next_backoff(0.5, alive=0.1) >= 4.0


def test_backoff_cap_is_configurable(tmp_path):
    p = VideoProxy("rtsp://127.0.0.1:8554/video1", hls_dir=str(tmp_path),
                   max_restart_backoff=8.0)
    b = 2.0
    for _ in range(5):
        b = p.next_backoff(b, alive=0.2)
    assert b == 8.0
