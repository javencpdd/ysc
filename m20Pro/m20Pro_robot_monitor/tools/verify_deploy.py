#!/usr/bin/env python3
"""部署验收脚本（PLAN T4.4）：在 196 上运行，逐项核对控制台是否真的可用。

用法：
    python3 tools/verify_deploy.py                    # 默认 http://127.0.0.1:8080
    python3 tools/verify_deploy.py --base http://192.168.0.196:8080

检查项：/health /ready /api/v1/state（各 topic 新鲜度与关键字段）
       /api/v1/schema /api/v1/video/status 前端根路径 HLS 播放列表
"""

import argparse
import json
import sys
import urllib.request

OK = "✅"
FAIL = "❌"


def get(base, path, timeout=6):
    url = base + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    results = []

    def check(name, cond, detail=""):
        results.append((cond, name, detail))
        print("%s %-28s %s" % (OK if cond else FAIL, name, detail))

    print("=" * 70)
    print("M20 Pro 控制台部署验收  base=%s" % base)
    print("=" * 70)

    # 1. health
    code, body = get(base, "/health")
    if code == 200:
        h = json.loads(body)
        check("/health", True, "connected=%s source=%s" % (h.get("connected"), h.get("data_source")))
    else:
        check("/health", False, "code=%s %s" % (code, body[:80]))
        print("\n服务未就绪，后续检查跳过")
        return 1

    # 2. ready
    code, body = get(base, "/ready")
    if code == 200:
        r = json.loads(body)
        check("/ready", not r.get("degraded"),
              "degraded=%s fresh=%s stale=%s" % (r.get("degraded"), r.get("fresh_topics"),
                                                 r.get("stale_topics")))
    else:
        check("/ready", False, body[:80])

    # 3. state
    code, body = get(base, "/api/v1/state")
    if code == 200:
        d = json.loads(body)
        topics = d.get("topics", {})
        check("快照 schema_version", d.get("schema_version") == "1.0", str(d.get("schema_version")))
        check("链路 connected", d.get("connected") is True, "")
        for name in ("basic", "motion", "device", "fault", "nav"):
            t = topics.get(name)
            if not t:
                check("topic %s" % name, False, "缺失")
                continue
            check("topic %s" % name, not t.get("stale"),
                  "age=%sms 字段=%d" % (t.get("age_ms"), len(t.get("data", {}))))
        b = topics.get("basic", {}).get("data", {})
        print("   基础状态: %s / %s / 休眠=%s / 机型=%s"
              % (b.get("motion_state_label"), b.get("gait_label"),
                 b.get("sleep_label"), b.get("version")))
        m = topics.get("motion", {}).get("data", {})
        print("   运控: 关节=%s 高度=%s" % (m.get("joint_count"), m.get("height")))
        dv = topics.get("device", {}).get("data", {})
        print("   设备: 电池=%s块 电量=%s 左=%s 右=%s 电机温度=%s路"
              % (dv.get("battery_count"), dv.get("level"), dv.get("level_left"),
                 dv.get("level_right"), len(dv.get("motor_temperatures", []))))
        nv = topics.get("nav", {}).get("data", {})
        print("   导航: 定位=%s 位置=(%s, %s, %s) 置信度=%s"
              % (nv.get("located"), nv.get("pos_x"), nv.get("pos_y"),
                 nv.get("pos_z"), nv.get("confidence")))
    else:
        check("/api/v1/state", False, body[:80])

    # 4. schema 契约
    code, body = get(base, "/api/v1/schema")
    ok = False
    if code == 200:
        try:
            s = json.loads(body)
            ok = s.get("version") == "1.0" and "schema" in s
        except ValueError:
            pass
    check("/api/v1/schema 契约", ok, "version=1.0" if ok else body[:60] if code else str(code))

    # 5. 视频
    code, body = get(base, "/api/v1/video/status")
    if code == 200:
        v = json.loads(body)
        check("视频代理", bool(v.get("available")),
              "running=%s available=%s 源=%s" % (v.get("running"), v.get("available"),
                                                 v.get("rtsp_url")))
    else:
        check("视频代理", False, body[:80])

    # 6. 前端
    code, body = get(base, "/")
    check("前端静态资源", code == 200 and "<div id=\"app\">" in body,
          "code=%s" % code)

    # 7. HLS
    code, body = get(base, "/hls/live.m3u8")
    check("HLS 播放列表", code == 200 and "#EXTM3U" in body, "code=%s" % code)

    print("=" * 70)
    failed = [r for r in results if not r[0]]
    print("通过 %d / %d" % (len(results) - len(failed), len(results)))
    if failed:
        print("未通过：%s" % ", ".join(r[1] for r in failed))
        return 1
    print("全部通过 %s" % OK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
