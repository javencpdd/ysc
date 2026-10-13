#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lite3 本体状态「按需探针」—— 跑完即退，不常驻、不占端口。

设计（按你的要求）：
  * 只在需要确认状态时手动跑一次，抓几秒打印结果就退出，不留后台进程。
  * 用 AF_PACKET 旁路抓包（复用 /home/test/monitor/backend/udp_sniffer.py），
    **不 bind UDP 43897**（那个口被 ROS1 的 qnx2ros 占着，bind 会 EADDRINUSE；
    且 SO_REUSEPORT 需要所有 socket 都设置才生效，qnx2ros 没设，单方面设也没用）。
  * 代价：需要 root / CAP_NET_RAW，所以要 sudo。

协议要点（2026-09-30 实测标定）：
  本体遥测端口 43897，RobotState = **code 2305 (0x0901)，长度 220 字节，约 192 Hz**。
  ⚠️ 同端口还有 0x0902/0x0903(108B)、0x0904(16B)、0x010901(52B)、以及偶发的
     0x0906(380B) —— 那个 380 字节的包**不是** RobotState，用它解析会得到垃圾值
     （也是 qnx2ros 刷 "udp pack length not fit into any, 380 220" 的来源）。
  字段偏移由编译器给出（g++ offsetof，见 scripts/README 或本文件注释）：
      basic_state=12  gait=16  policy=20  rpy=28  pos_world=100
      motion_state=184  battery=188  ultrasound=204

用法（103 上）：
  printf "\\047\\n" | sudo -S python3 scripts/robot_state_probe.py [网卡] [秒数]
  #  例：printf "\\047\\n" | sudo -S python3 scripts/robot_state_probe.py eth0 5
"""
import struct
import sys
import time

sys.path.insert(0, "/home/test/monitor/backend")
from udp_sniffer import UDPSniffer  # noqa: E402

CODE_ROBOT_STATE = 2305  # 0x0901
EXPECT_LEN = 220

OFF_BASIC = 12
OFF_GAIT = 16
OFF_POLICY = 20
OFF_RPY = 28
OFF_POS_WORLD = 100
OFF_MOTION = 184
OFF_BATTERY = 188

# 依据 lite3_robot_monitor/docs/protocol/lite3-udp-protocol.md 的取值表（从 0 起编号）
BASIC_STATE = {
    0: "趴下状态",
    1: "准备起立状态",
    2: "正在起立状态",
    3: "力控状态（站立就绪，可运动）",
    4: "正在趴下状态",
    5: "失控保护状态",
    6: "姿态调整状态",
    7: "执行翻身动作",
    8: "AI状态",
    9: "回零状态",
}


def main() -> int:
    iface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    sniffer = UDPSniffer(port=43897, interface=iface, timeout=0.2)
    try:
        sniffer.start()
    except PermissionError as exc:
        print("[probe] 需要 root / CAP_NET_RAW：%s" % exc)
        return 2

    end = time.time() + seconds
    hit = 0
    try:
        while time.time() < end and hit < 3:
            try:
                data, _addr = sniffer._queue.get(timeout=0.5)
            except Exception:  # noqa: BLE001,S110
                continue
            if len(data) != EXPECT_LEN:
                continue
            if struct.unpack_from("<i", data, 0)[0] != CODE_ROBOT_STATE:
                continue
            hit += 1
            if hit > 1:
                break
            basic = struct.unpack_from("<i", data, OFF_BASIC)[0]
            gait = struct.unpack_from("<i", data, OFF_GAIT)[0]
            policy = struct.unpack_from("<i", data, OFF_POLICY)[0]
            motion = struct.unpack_from("<i", data, OFF_MOTION)[0]
            battery = struct.unpack_from("<d", data, OFF_BATTERY)[0]
            rpy = struct.unpack_from("<3d", data, OFF_RPY)
            pos = struct.unpack_from("<3d", data, OFF_POS_WORLD)
            print("=== Lite3 本体状态（按需探针，%s 秒）===" % seconds)
            print("  基本状态 : %-2d  %s" % (basic, BASIC_STATE.get(basic, "未知")))
            print("  步态     : %d      动作状态: %d      AI状态: %d" % (gait, motion, policy))
            print("  电量     : %.1f %%" % battery)
            print("  世界位置 : x=%.3f  y=%.3f  z=%.3f" % pos)
            print("  姿态 rpy : roll=%.1f  pitch=%.1f  yaw=%.1f (度)" % rpy)
    finally:
        sniffer.stop()

    if hit == 0:
        print("[probe] 没抓到 RobotState(0x0901/220B)。检查：网卡名（ip -o link）、本体是否在发遥测")
        return 1
    print("[probe] 完成，已退出（无后台进程残留）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
