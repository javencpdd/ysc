"""M20 自身 WiFi 热点受控读写（backend/net/ap_ctl.py）契约测试（2026-10-18 加）。

守住三条底线：

1. **密码必须是字符串**：纯数字密码（如 ``00123456``）被 ``int()`` 掉会丢前导零，
   用户照着界面显示的去输就连不上热点。这是加"回显当前密码"时发现的真 bug。
2. **读不出原文时明说**：密码含控制字符或首尾空白时，helper 只报
   ``password_unreadable=1`` —— 显示一个连不上的密码比不显示更糟。
3. **缺数据不能说成"没开热点"**：helper 输出里整个 ``ap`` 分组缺失 = 没拿到数据，
   必须标 ``unknown``，那是"不知道"，不是"关闭"。
"""

from net import ap_ctl


def _status_text(**over):
    """拼一份 helper 的 status 输出（默认是一台正常开着热点的车）。"""
    fields = {
        "ap.found": "1", "ap.con": "myap24G", "ap.dev": "wlan0",
        "ap.state": "activated", "ap.ssid": "CA9B_NO.1273_24G",
        "ap.band": "bg", "ap.security": "wpa-psk",
        "ap.password_set": "1", "ap.password": "12345678",
        "ap.managed_by_vendor": "1", "ap.ip": "10.21.41.1/24",
        "ap.channel": "40 (5200 MHz)", "ap.clients": "0",
        "ap.shared_radio": "1",
        "uplink.found": "1", "uplink.con": "Tenda_FCFA20_5G",
        "uplink.dev": "p2p0", "uplink.state": "100 (connected)",
        "uplink.ip": "192.168.0.196/24",
    }
    fields.update(over)
    return "".join("%s=%s\n" % kv for kv in sorted(fields.items()))


# ------------------------------------------------ ① 密码必须是字符串
def test_numeric_password_keeps_leading_zeros():
    """``00123456`` 不能被 int() 成 ``123456`` —— 丢了前导零就再也连不上。"""
    parsed = ap_ctl._parse(_status_text(**{"ap.password": "00123456"}))
    pwd = parsed["ap"]["password"]
    assert pwd == "00123456", "前导零被吃掉了：%r" % (pwd,)
    assert isinstance(pwd, str)


def test_all_digit_password_stays_string():
    parsed = ap_ctl._parse(_status_text())
    assert parsed["ap"]["password"] == "12345678"
    assert isinstance(parsed["ap"]["password"], str)


def test_connection_names_stay_string_too():
    """连接名同理（现实中不是纯数字，但不该靠"现实中不会"兜底）。"""
    parsed = ap_ctl._parse(_status_text(**{"ap.con": "12345",
                                           "uplink.con": "67890"}))
    assert parsed["ap"]["con"] == "12345"
    assert parsed["uplink"]["con"] == "67890"


def test_other_numeric_fields_still_become_int():
    """修前导零不能把别的字段也变成字符串 —— clients/found 还得是数字。"""
    parsed = ap_ctl._parse(_status_text())
    assert parsed["ap"]["clients"] == 0 and isinstance(parsed["ap"]["clients"], int)
    assert parsed["ap"]["found"] == 1 and isinstance(parsed["ap"]["found"], int)
    assert parsed["ap"]["shared_radio"] == 1
    assert parsed["ap"]["password_set"] == 1


# ------------------------------------------------ ② 读不出原文
def test_unreadable_password_is_flagged_not_shown():
    parsed = ap_ctl._parse(_status_text())
    del parsed["ap"]["password"]                      # helper 不输出 password=
    parsed["ap"]["password_unreadable"] = 1
    view = ap_ctl._describe({"ap": parsed["ap"], "uplink": parsed["uplink"]})
    assert view["ap"]["password_unreadable"] == 1
    assert "password" not in view["ap"], "读不出原文时不该给 password 字段"


def test_no_password_at_all():
    """开放网络：password_set=0，且不该凭空多个 password 字段。"""
    text = _status_text()
    text = text.replace("ap.password=12345678\n", "")
    text = text.replace("ap.password_set=1", "ap.password_set=0")
    view = ap_ctl._describe(ap_ctl._parse(text))
    assert view["ap"]["password_set"] == 0
    assert "password" not in view["ap"]


# ------------------------------------------------ ③ 缺数据 ≠ 没开热点
def test_missing_ap_group_is_unknown_not_off():
    """helper 整个 ap 分组没输出 = 没拿到数据，必须标 unknown。"""
    view = ap_ctl._describe({"ap": {}, "uplink": {}})
    assert view["ap"]["unknown"] is True
    assert view["ap"]["level"] == "off"
    assert view["ap"]["summary"] == "状态未知"


def test_no_ap_connection_is_reported_as_such():
    # 真机上没有 AP 连接时 helper 会提前返回，不输出 shared_radio —— 按真实路径拼
    text = _status_text()
    text = text.replace("ap.state=activated", "ap.state=no_ap_connection")
    text = text.replace("ap.shared_radio=1\n", "")
    view = ap_ctl._describe(ap_ctl._parse(text))
    assert view["ap"]["summary"] == "本机未配置热点连接"
    assert view["ap"]["level"] == "off"
    # "没配热点连接"是**已知**状态，不是"不知道"—— 两者语义相反，不能混
    assert view["ap"].get("unknown") is not True


def test_uplink_connected_summary():
    view = ap_ctl._describe(ap_ctl._parse(_status_text()))
    assert view["uplink"]["summary"] == "已连接（Tenda_FCFA20_5G）"
    assert view["uplink"]["level"] == "ok"


def test_uplink_down_is_warn_not_silent():
    text = _status_text()
    text = text.replace("uplink.state=100 (connected)", "uplink.state=0 (unknown)")
    view = ap_ctl._describe(ap_ctl._parse(text))
    assert view["uplink"]["level"] == "warn"
    assert "未连接" in view["uplink"]["summary"]
