"""StateStore 单测：per-topic 新鲜度、stale 语义、有界环形缓冲（ADR-006/007）。"""

import time

from state.state_store import StateStore


def _frame(topic, fields=None, mono=None):
    mono = time.monotonic() if mono is None else mono
    return {"topic": topic, "key": "%s/1" % topic, "fields": fields or {"v": 1},
            "recv_monotonic": mono, "recv_wall": time.time()}


def test_update_and_snapshot_contains_topic_data():
    store = StateStore(stale_threshold=0.5)
    store.update(_frame("basic", {"motion_state": 1}))
    snap = store.snapshot()
    assert snap["topics"]["basic"]["data"]["motion_state"] == 1
    assert snap["topics"]["basic"]["stale"] is False
    assert snap["connected"] is True


def test_stale_marks_but_keeps_old_value():
    """停更只标脏，绝不把旧数据当新数据展示（PLAN §6.2）。

    注意 stale_threshold 与 link_timeout 是两个独立阈值：
    前者管 topic 置灰，后者管"链路断开"（connected）。
    """
    store = StateStore(stale_threshold=0.05, link_timeout=0.1)
    store.update(_frame("basic", {"motion_state": 1}))
    assert store.is_stale("basic") is False
    time.sleep(0.12)
    assert store.is_stale("basic") is True
    snap = store.snapshot()
    # 值仍在，但被标记 stale —— 前端据此置灰 + 红色横幅
    assert snap["topics"]["basic"]["data"]["motion_state"] == 1
    assert snap["topics"]["basic"]["stale"] is True
    assert snap["connected"] is False


def test_per_topic_stale_is_independent():
    store = StateStore(stale_threshold=0.05)
    now = time.monotonic()
    store.update(_frame("basic", {}, mono=now))
    store.update(_frame("motion", {}, mono=now - 1.0))  # 更早
    assert store.is_stale("basic") is False
    assert store.is_stale("motion") is True


def test_link_timeout_drives_connected():
    store = StateStore(stale_threshold=0.05, link_timeout=0.3)
    store.update(_frame("basic"))
    assert store.connected() is True
    time.sleep(0.45)
    assert store.connected() is False


def test_raw_ring_buffer_is_bounded():
    store = StateStore(raw_history_size=5)
    for i in range(50):
        store.update(_frame("basic", {"i": i}), raw=b"\xeb\x91\xeb\x90" + bytes([i]))
    assert len(store.get_raw_packets(limit=100)) == 5
    counters = store.counters()
    assert counters["dropped"] >= 45          # 有界：旧帧被淘汰并计数
    assert counters["received"] == 50


def test_record_error_counts_dead_letter():
    store = StateStore()
    store.record_error(raw=b"\x00\x01", reason="bad tag")
    counters = store.counters()
    assert counters["errors"] == 1
    assert counters["error_rate"] == 1.0


def test_ready_reports_degraded_when_disconnected():
    store = StateStore(link_timeout=0.05)
    result = store.ready()
    assert result["degraded"] is True
    assert "链路断开" in (result["reason"] or "")


def test_ready_lists_fresh_and_stale_topics():
    store = StateStore(stale_threshold=0.05, link_timeout=5.0)
    now = time.monotonic()
    store.update(_frame("basic", mono=now))
    store.update(_frame("fault", mono=now - 1.0))
    result = store.ready()
    assert "basic" in result["fresh_topics"]
    assert "fault" in result["stale_topics"]
