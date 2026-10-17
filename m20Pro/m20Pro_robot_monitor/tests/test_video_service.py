"""视频推流服务控制单测（2026-10-17）。

不碰真机：只测**解析与语义**这块 —— 它出过一次真 bug（动作只返回单条链的状态，
另一条被上层误读成"未运行"），以及"进程活着但没出流"这个最需要被正确表达的坏状态。
"""

import pytest

from video import service_ctl as vs

# 真机 helper 的原始输出（2026-10-17 实测，含那个经典坏状态）
REAL_STUCK = """local.processes=5
local.gst=0
local.hls_video1=404
local.hls_video2=404
local.ready=no
local.stuck=yes
relay.unit=active
relay.processes=2
relay.target=172.31.68.227:1936
relay.target_tcp=yes
relay.enabled=enabled
"""

REAL_OK = """local.processes=5
local.gst=2
local.hls_video1=200
local.hls_video2=200
local.ready=yes
local.stuck=no
relay.unit=active
relay.processes=2
relay.target=172.31.68.227:1936
relay.target_tcp=yes
relay.enabled=enabled
"""


def test_parse_types():
    """yes/no → bool、纯数字 → int、其余 → str（前端不必自己判字符串）。"""
    p = vs._parse(REAL_OK)
    assert p["local"]["ready"] is True
    assert p["local"]["stuck"] is False
    assert p["local"]["hls_video1"] == 200
    assert p["local"]["processes"] == 5
    assert p["relay"]["unit"] == "active"
    assert p["relay"]["target"] == "172.31.68.227:1936"
    assert p["relay"]["enabled"] == "enabled"


def test_stuck_is_reported_as_warning_not_ok():
    """★核心语义：**进程活着但没出流**必须报成 warn，不能只看进程数说"正常"。

    这是本机最常见的坏法（gst 进程在、mpph264enc 内部报错、HLS 拉不到），
    只报"进程 5 个 = 在跑"会把坏链路显示成好的。
    """
    d = vs._describe(vs._parse(REAL_STUCK))
    assert d["local"]["level"] == "warn"
    assert "没出流" in d["local"]["summary"]
    assert d["local"]["stuck"] is True
    assert d["local"]["ready"] is False


def test_ready_when_hls_actually_serves():
    d = vs._describe(vs._parse(REAL_OK))
    assert d["local"]["level"] == "ok"
    assert d["local"]["summary"] == "在出流"


def test_stopped_local_is_off_not_warn():
    """真的没进程 → off（"未运行"），别和"卡住"混为一谈 —— 处置手法不同。"""
    d = vs._describe(vs._parse("local.processes=0\nlocal.gst=0\n"
                               "local.hls_video1=404\nlocal.hls_video2=404\n"
                               "local.ready=no\nlocal.stuck=no\n"))
    assert d["local"]["level"] == "off"
    assert d["local"]["summary"] == "未运行"


def test_missing_group_says_unknown_not_stopped():
    """★回归（2026-10-17 真踩）：只拿到一条链的数据时，另一条**不能编造"未运行"**。

    当时 restart relay 只返回 relay 的状态，上层把缺失的 local 显示成"未运行"——
    用户会以为本地推流停了，实际它只是没有数据。缺数据就说"状态未知"。
    """
    d = vs._describe({"relay": {"unit": "active", "target_tcp": True}})
    assert d["local"]["summary"] == "状态未知"
    assert d["local"].get("unknown") is True
    assert d["relay"]["level"] == "ok"

    d2 = vs._describe({})
    assert d2["local"]["summary"] == "状态未知"
    assert d2["relay"]["summary"] == "状态未知"


def test_relay_target_unreachable_is_warn():
    d = vs._describe(vs._parse(REAL_OK.replace("relay.target_tcp=yes",
                                               "relay.target_tcp=no")))
    assert d["relay"]["level"] == "warn"
    assert "目标不可达" in d["relay"]["summary"]


def test_labels_tell_the_two_chains_apart():
    """两条链必须一眼能分清 —— 用户最容易误以为"关掉推流画面就没了"。"""
    d = vs._describe(vs._parse(REAL_OK))
    assert "控制台画面" in d["local"]["label"]
    assert "远端" in d["relay"]["label"]


# ---------------------------------------------------------------- 入参白名单
def test_bad_target_and_action_rejected_without_running_anything(monkeypatch):
    called = []
    monkeypatch.setattr(vs, "_run", lambda args, t: called.append(args) or "")
    for target, action in (("nope", "start"), ("", "start"),
                           ("local", "nuke"), ("local", "")):
        with pytest.raises(vs.VideoServiceError) as ei:
            vs.control(target, action, confirmed=True)
        assert ei.value.reason in ("BAD_TARGET", "BAD_ACTION")
    assert called == []          # 一个都没执行


def test_stop_requires_confirmation(monkeypatch):
    called = []
    monkeypatch.setattr(vs, "_run", lambda args, t: called.append(args) or "")
    with pytest.raises(vs.VideoServiceError) as ei:
        vs.control("local", "stop")
    assert ei.value.reason == "CONFIRM_REQUIRED"
    assert ei.value.status == 409
    assert called == []
    # 确认后才真的执行
    vs.control("local", "stop", confirmed=True)
    assert called == [["stop", "local"]]


def test_start_and_restart_need_no_confirmation(monkeypatch):
    called = []
    monkeypatch.setattr(vs, "_run", lambda args, t: called.append(args) or REAL_OK)
    vs.control("relay", "start")
    vs.control("relay", "restart")
    assert called == [["start", "relay"], ["restart", "relay"]]


def test_control_returns_full_state_of_both_chains(monkeypatch):
    """动作的返回必须是**两条链的完整状态**（面板要整体刷新）。"""
    monkeypatch.setattr(vs, "_run", lambda args, t: REAL_OK)
    out = vs.control("relay", "restart")
    assert out["ok"] is True and out["target"] == "relay"
    assert set(out["targets"]) == {"local", "relay"}
    assert out["targets"]["local"]["level"] == "ok"
    assert out["targets"]["relay"]["level"] == "ok"


def test_unauthorized_gives_actionable_message(monkeypatch):
    """没配 sudoers 时要**说清怎么修**，不能只回一句英文报错。"""
    import subprocess

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, "",
                                           "sudo: a password is required\n")
    monkeypatch.setattr(vs, "helper_available", lambda: True)
    monkeypatch.setattr(vs.subprocess, "run", fake_run)
    with pytest.raises(vs.VideoServiceError) as ei:
        vs.status()
    assert ei.value.reason == "NOT_AUTHORIZED"
    assert "sudoers" in str(ei.value)


def test_helper_missing_is_explicit(monkeypatch):
    monkeypatch.setattr(vs, "helper_available", lambda: False)
    with pytest.raises(vs.VideoServiceError) as ei:
        vs.status()
    assert ei.value.reason == "HELPER_MISSING"
    assert "m20-video-ctl" in str(ei.value)


def test_parse_ignores_dirty_lines():
    """★回归：helper 输出里的**脏行**必须被忽略，不能污染解析。

    2026-07-17 实测踩到过：`systemctl is-active` 对未运行的单元会**既**打印
    "inactive" **又**返回非 0，`|| echo unknown` 于是再补一行裸的 "unknown"。
    （同类错误在 http_code 上还犯过一次，输出 `000000`。）
    后端在这一层要够皮实：没有 `=` 的行直接跳过。
    """
    dirty = ("local.processes=5\n"
             "local.gst=2\n"
             "unknown\n"                      # 裸行（systemctl 双输出的残留）
             "\n"                             # 空行
             "   \n"                          # 空白行
             "local.hls_video1=200\n"
             "local.hls_video2=200\n"
             "local.ready=yes\n"
             "local.stuck=no\n")
    d = vs._parse(dirty)
    assert d["local"]["ready"] is True
    assert d["local"]["gst"] == 2
    assert "unknown" not in d["local"]


def test_no_dirty_line_in_current_helper_output():
    """反向守卫：helper 现在不该再产出裸的 unknown 行（fixture 是真机贴回的）。"""
    clean = REAL_OK + "relay.enabled=enabled\n"
    for line in clean.splitlines():
        assert "=" in line, "helper 输出了没有 key=value 形态的脏行: %r" % line
