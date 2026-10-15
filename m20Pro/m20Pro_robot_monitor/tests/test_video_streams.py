"""`/api/v1/video/streams` 契约测试（2026-10-16：前后双路 + WebRTC 直连 MediaMTX）。

重点守住一条最容易踩的坑：**返回的地址要素不能含主机名**。
前端按 `location.hostname` 拼接，后端若写死 `127.0.0.1`，浏览器会去连
"浏览器本机"而不是 196 —— 页面在本机打开时看似正常，一上位机就黑屏。
"""

import json

from fastapi.testclient import TestClient

import main
from config import Settings, VideoSettings


class _FakeVideoProxy:
    """替身：只要能给出 status()（第三层兜底：后端 ffmpeg 中继）。"""

    def status(self):
        return {"enabled": True, "available": True, "last_segment_age": 1}


class _FakeService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.video = _FakeVideoProxy()


def _get_streams(video: VideoSettings):
    """装上假服务后请求一次，用完立即还原全局 service（避免污染其他用例）。"""
    prev = main.service
    main.service = _FakeService(Settings(video=video))
    try:
        resp = TestClient(main.app).get("/api/v1/video/streams")
    finally:
        main.service = prev
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_streams_returns_front_and_back_paths():
    body = _get_streams(VideoSettings(enabled=True))
    assert body["enabled"] is True
    assert [(s["key"], s["path"], s["label"]) for s in body["streams"]] == [
        ("front", "video1", "前相机"),
        ("back", "video2", "后相机"),
    ]


def test_streams_exposes_three_tiers_without_hostname():
    """WebRTC 主 → MediaMTX HLS 兜底 → 后端代理；且**不含**主机名/IP。"""
    body = _get_streams(VideoSettings(enabled=True))
    assert body["webrtc"]["port"] == 8889
    assert body["webrtc"]["enabled"] is True
    assert body["hls"]["port"] == 8888
    assert body["proxy"]["url"] == "/hls/live.m3u8"
    # endpoint 用 {path} 占位，由前端填入 video1/video2
    assert "{path}" in body["webrtc"]["endpoint"]
    assert "{path}" in body["hls"]["endpoint"]
    # 关键断言：**给浏览器拼地址用**的字段不得含主机（写死会让浏览器连错机器）
    for group in ("webrtc", "hls"):
        text = json.dumps(body[group], ensure_ascii=False)
        for forbidden in ("127.0.0.1", "192.168.", "localhost", "http://", "//"):
            assert forbidden not in text, f"{group} 里不该出现 {forbidden}：{text}"
    # proxy.rtsp_url 例外：那是**后端自己**的取流源（与 MediaMTX 同机），127.0.0.1 才对
    assert body["proxy"]["rtsp_url"].startswith("rtsp://127.0.0.1")


def test_streams_reports_disabled_state():
    body = _get_streams(VideoSettings(enabled=False))
    assert body["enabled"] is False
    # 即使整体未开启，也要把两路配置给前端（前端据此渲染并提示"未开启"）
    assert len(body["streams"]) == 2
