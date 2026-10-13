#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lite3 本体接管辅助：自主模式 / 心跳 / 手柄模式 / 零速度。

为什么要这个脚本（103 实测，2026-09-30）
---------------------------------------
ros2qnx（/home/ysc/lite_cog/transfer/src/message_transformer/src/ros2qnx.cpp）
订阅 ROS1 的 /cmd_vel 与 /cmd_vel_corrected，把 Twist 拆成 3 个 ComplexCMD
发往 192.168.1.120:43893：

    linear.x  -> ComplexCMD{cmd_code:320, cmd_value:8, type:1, data: linear.x}
    linear.y  -> ComplexCMD{cmd_code:325, cmd_value:8, type:1, data: linear.y}
    angular.z -> ComplexCMD{cmd_code:321, cmd_value:8, type:1, data:-angular.z}

但机器人本体只有在「自主模式」下才吃这些速度包，默认的手柄模式会直接忽略；
而且自主模式期间上位机必须持续发「心跳」（RobotCommander.py 里是 4 Hz），
心跳一断本体会自行退回手柄模式 —— 这就是「规划器在发速度、狗却不动」的根因。

指令码取自 lite_cog 自带常量表
/home/ysc/lite_cog/pipeline/src/pipeline_tracking/scripts/constants.py：
    kHeartBeat          = 0x21040001
    kSetAutoMode        = 0x21010C03
    kSetHandleMode      = 0x21010C02
    kSoftEmergencyStop  = 0x21010C0E
    kStandLie           = 0x21010202   （本脚本不发，起立请用手柄，避免语义误判）
    kSimpleCMDType      = 0x00
零速度 = ComplexCMD{320 / 325 / 321, cmd_value:8, type:1, data:0.0}

用法（一律走 scripts/auto_mode.sh，它会先建 ROS1 环境）：
    bash scripts/auto_mode.sh auto          # 进自主模式 + 4 Hz 心跳（前台；Ctrl+C 时零速度并退回手柄）
    bash scripts/auto_mode.sh auto --keep   # 同上，但退出时不退回手柄
    bash scripts/auto_mode.sh handle        # 只发一次「退回手柄模式」
    bash scripts/auto_mode.sh zero          # 只发一次零速度
    bash scripts/auto_mode.sh stop          # 只发一次软急停

安全：本脚本只管模式与心跳，不碰速度；真正的速度由 body_link.sh 的 relay 接通。
"""

import sys
import threading
import time

import rospy
from message_transformer.msg import SimpleCMD, ComplexCMD

K_HEARTBEAT = 0x21040001
K_SET_AUTO_MODE = 0x21010C03
K_SET_HANDLE_MODE = 0x21010C02
K_SOFT_EMERGENCY_STOP = 0x21010C0E

HEARTBEAT_HZ = 4.0           # RobotCommander.py 用 rospy.sleep(0.25)，即 4 Hz
VEL_CODES = (320, 325, 321)  # 线速度 x / 线速度 y / 角速度 z


def _simple(code, value=0, ctype=0):
    m = SimpleCMD()
    m.cmd_code = code
    m.cmd_value = value
    m.type = ctype
    return m


def _complex(code, data, value=8, ctype=1):
    m = ComplexCMD()
    m.cmd_code = code
    m.cmd_value = value
    m.type = ctype
    m.data = data
    return m


class Lite3AutoMode(object):
    def __init__(self):
        self.pub_simple = rospy.Publisher('/simple_cmd', SimpleCMD, queue_size=20)
        self.pub_complex = rospy.Publisher('/complex_cmd', ComplexCMD, queue_size=20)
        self._stop = threading.Event()

    def wait_connections(self, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end and not rospy.is_shutdown():
            if self.pub_simple.get_num_connections() > 0:
                return True
            time.sleep(0.1)
        return self.pub_simple.get_num_connections() > 0

    def publish_zero_velocity(self, repeat=3):
        for _ in range(repeat):
            for code in VEL_CODES:
                self.pub_complex.publish(_complex(code, 0.0))
            time.sleep(0.05)

    def publish_simple(self, code, repeat=3):
        for _ in range(repeat):
            self.pub_simple.publish(_simple(code))
            time.sleep(0.05)

    def heartbeat_loop(self):
        rate = rospy.Rate(HEARTBEAT_HZ)
        while not rospy.is_shutdown() and not self._stop.is_set():
            self.pub_simple.publish(_simple(K_HEARTBEAT))
            rate.sleep()


def main():
    argv = list(sys.argv[1:])
    keep_auto = '--keep' in argv
    argv = [a for a in argv if a != '--keep']
    action = argv[0] if argv else 'auto'

    rospy.init_node('lite3_auto_mode', anonymous=True)
    node = Lite3AutoMode()

    if not node.wait_connections():
        rospy.logwarn('[auto_mode] /simple_cmd 没有订阅者 —— ros2qnx 还活着吗？'
                      '（检查：ps -eo comm | grep ros2qnx）')

    def on_shutdown():
        node._stop.set()
        rospy.loginfo('[auto_mode] 退出处理：发零速度 320/325/321 ...')
        node.publish_zero_velocity()

    if action == 'auto':
        rospy.on_shutdown(on_shutdown)
        rospy.loginfo('[auto_mode] 进入自主模式 cmd_code=0x%X' % K_SET_AUTO_MODE)
        node.publish_simple(K_SET_AUTO_MODE)
        rospy.loginfo('[auto_mode] 开始 %g Hz 心跳，Ctrl+C 结束' % HEARTBEAT_HZ)
        t = threading.Thread(target=node.heartbeat_loop)
        t.daemon = True
        t.start()
        rospy.spin()
        if keep_auto:
            rospy.loginfo('[auto_mode] --keep：不发手柄模式（注意心跳已停，本体会自行退回）')
        else:
            rospy.loginfo('[auto_mode] 退回手柄模式 cmd_code=0x%X' % K_SET_HANDLE_MODE)
            node.publish_simple(K_SET_HANDLE_MODE)
    elif action == 'handle':
        node.publish_simple(K_SET_HANDLE_MODE)
        rospy.loginfo('[auto_mode] 已发送：退回手柄模式')
    elif action == 'zero':
        node.publish_zero_velocity()
        rospy.loginfo('[auto_mode] 已发送：零速度 320/325/321')
    elif action == 'stop':
        node.publish_simple(K_SOFT_EMERGENCY_STOP)
        rospy.loginfo('[auto_mode] 已发送：软急停 0x%X' % K_SOFT_EMERGENCY_STOP)
    else:
        rospy.logerr('[auto_mode] 未知动作：%s（auto | handle | zero | stop）' % action)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
