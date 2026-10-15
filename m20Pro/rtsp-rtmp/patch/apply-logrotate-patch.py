#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply-logrotate-patch.py —— 把 rtmp_forward.sh 的日志轮转替换为 m20-log.sh 实现

原则：保持现有日志调用方式不变（所有 `log "xxx"` 调用点一行都不改），
      只替换 rotate_log() / log() 两个函数的内部实现。

用法：
    python3 apply-logrotate-patch.py <rtmp_forward.sh>          # 应用并备份
    python3 apply-logrotate-patch.py <rtmp_forward.sh> --check  # 只检查是否已应用
"""
import os
import sys
import time
import shutil

NEW_BLOCK = r'''# ---------------------------------------------------------------------------
# 日志轮转：统一交给 lib/m20-log.sh
#   能力：单文件大小上限切分 + 保留最近 N 份 + 总空间硬上限 + 并发安全 +
#         不中断「长期持有 fd」的写入方（copytruncate）
#   兼容：旧的 LOG_MAX_BYTES 仍然有效（优先级低于 M20LOG_MAX_BYTES）
#   兜底：库缺失时退回原始行为，保证脚本仍能正常启动
# ---------------------------------------------------------------------------
M20LOG_LIB="${M20LOG_LIB:-$SCRIPT_DIR/lib/m20-log.sh}"
if [ -r "$M20LOG_LIB" ]; then
    # shellcheck source=lib/m20-log.sh
    . "$M20LOG_LIB"
    : "${M20LOG_MAX_BYTES:=${LOG_MAX_BYTES:-10485760}}"
fi

rotate_log() {
    if command -v m20log_rotate >/dev/null 2>&1; then
        m20log_rotate "$LOG_FILE"
        return 0
    fi
    # --- 以下为 m20-log.sh 不可用时的原始兜底逻辑 ---
    [ -f "$LOG_FILE" ] || return 0
    local size
    size=$(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -ge "${LOG_MAX_BYTES:-5242880}" ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null
    fi
}
rotate_log

log() {
    local line
    line="$(date '+%Y-%m-%d %H:%M:%S') [forward-$STREAM] $*"
    if command -v m20log_emit >/dev/null 2>&1; then
        m20log_emit "$LOG_FILE" "$line"
    else
        printf '%s\n' "$line" >>"$LOG_FILE" 2>/dev/null
    fi
    [ "${CONSOLE_LOG:-0}" = "1" ] && printf '%s\n' "$line"
    return 0
}
'''


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    check_only = "--check" in sys.argv

    with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
        lines = fh.readlines()

    if any("m20-log.sh" in ln for ln in lines):
        print("ALREADY_APPLIED: 已经打过补丁（文件中已引用 m20-log.sh）")
        return 0

    # 定位 rotate_log() { ... } 与 log() { ... } 两个函数的行区间
    i_rotate = None
    i_log = None
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("rotate_log()"):
            i_rotate = idx
        elif s.startswith("log()") and i_log is None and i_rotate is not None:
            i_log = idx
            break

    if i_rotate is None or i_log is None:
        print("ERROR: 未能定位 rotate_log()/log() 函数，文件结构可能已变化")
        return 1

    # log() 的结束花括号
    i_end = None
    for idx in range(i_log + 1, len(lines)):
        if lines[idx].rstrip("\n") == "}":
            i_end = idx
            break
    if i_end is None:
        print("ERROR: 未能找到 log() 的结束花括号")
        return 1

    print("定位结果: rotate_log 在 第%d行, log 在 第%d行, 结束于 第%d行"
          % (i_rotate + 1, i_log + 1, i_end + 1))
    print("--- 将被替换的原始内容 ---")
    sys.stdout.write("".join(lines[i_rotate:i_end + 1]))
    print("--------------------------")

    if check_only:
        print("CHECK: 可以应用")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = "%s.bak-logrotate-%s" % (path, stamp)
    shutil.copy2(path, backup)
    print("已备份原文件 -> %s" % backup)

    new_lines = lines[:i_rotate] + [NEW_BLOCK] + lines[i_end + 1:]
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
        fh.writelines(new_lines)
    print("已写入新版本: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
