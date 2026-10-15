#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向 rtmp_1012/config.env 追加日志轮转配置段（幂等：已存在则跳过）"""
import io
import sys

BLOCK = r'''
# ===========================================================================
# 日志轮转配置（由 lib/m20-log.sh + /usr/local/sbin/m20-log-rotate.sh 提供）
#
#   机制：单个日志文件达到上限即自动切分；只保留最近 N 份历史；超出的删最旧的；
#         切换过程不丢日志、不中断写入（copytruncate，兼容 gst-launch 长期
#         持有 fd 直接写日志的方式）；多进程并发下用 flock 串行化，安全。
#
#   旧的 LOG_MAX_BYTES 仍兼容（优先级低于 M20LOG_MAX_BYTES），
#   若未设置 M20LOG_MAX_BYTES 则回退到 LOG_MAX_BYTES。
# ===========================================================================
M20LOG_MAX_BYTES=10485760     # 单文件大小上限(字节)。默认 10485760 = 10MB。
                              #   达到即切分，新建/清空后继续写入
M20LOG_KEEP=5                 # 保留最近几份历史文件(不含当前正在写的)。默认 5。
                              #   超出的从最旧开始删除
M20LOG_TOTAL_MAX_BYTES=0      # 单路日志「总占用」硬上限(字节)。默认 0 = 不额外限制，
                              #   此时隐含上限 = MAX_BYTES * (KEEP+1) = 10MB*6 = 60MB。
                              #   若想绝对固定占用（例如磁盘小），设为具体值，如 52428800(50MB)
M20LOG_DIR=                   # 历史文件存放目录。留空 = 与日志文件同目录(推荐)
M20LOG_NAME_FMT=seq           # 轮转文件命名格式：
                              #   seq → forward-f.1.log / forward-f.2.log ...
                              #   ts  → forward-f-20261016-030900.log（时间戳）
                              #   也支持自定义模板，占位符 {base} {ext} {n} {ts}
M20LOG_MODE=copytruncate      # 轮转方式。默认 copytruncate：复制后截断，fd 不变、
                              #   写入不中断 —— 必须用它，因为 gst 长期持有 fd。
                              #   mv 是原子改名(零丢失)，但会让 gst 继续写进旧文件
M20LOG_TS_FMT=%Y%m%d-%H%M%S   # {ts} 占位符的时间格式
M20LOG_CHECK_BYTES=4096       # 写入方累积写入多少字节做一次大小检查(主触发条件)
M20LOG_MIN_CHECK_INTERVAL=1   # 低频日志的最小检查间隔(秒)
M20LOG_CATCHUP_ROUNDS=4       # copytruncate 的追赶复制轮数，用于压缩丢失窗口
M20LOG_LOCK_WAIT=0            # 抢锁等待秒数。0 = 非阻塞（推荐，避免竞争进程被阻塞后
                              #   正好撞上截断而多丢日志）
M20LOG_SCAN_DIR=/home/user/rtmp_1012/logs   # 巡检脚本扫描的目录
M20LOG_SCAN_GLOB=*.log        # 巡检脚本匹配的文件名模式
'''


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/home/user/rtmp_1012/config.env"
    with io.open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
        content = fh.read()
    if "M20LOG_MAX_BYTES" in content:
        print("SKIP: config.env 中已存在 M20LOG_* 配置，未修改")
        return 0
    if not content.endswith("\n"):
        content += "\n"
    with io.open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.write(content + BLOCK)
    print("已追加日志轮转配置段 -> %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
