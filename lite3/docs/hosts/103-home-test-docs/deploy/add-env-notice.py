#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 env 顶部插入一条说明性注释（幂等）。"""

import io
import os
import sys

ENV_FILE = "/home/test/yolo8/deploy/yolo-publish.env"
NOTICE = (
    "# ============================================================\n"
    "# [P0 说明] config/yolo8.json 已由 migrate-env-to-config.py 生成，\n"
    "# 但 worker 尚未消费它（计划书 v2.1 P2 才接入）。\n"
    "# ⇒ 接入前，本文件仍然是唯一生效源；下面的键请勿注释掉。\n"
    "# P2 接入后，本文件仅保留启动期静态键（HEADLESS/话题名/端口等），\n"
    "# 运行期配置一律以 config/yolo8.json 为准。\n"
    "# ============================================================\n"
)


def main():
    if not os.path.exists(ENV_FILE):
        print("ERROR missing " + ENV_FILE)
        return 1
    with io.open(ENV_FILE, "r", encoding="utf-8") as fh:
        text = fh.read()
    if "[P0 说明]" in text:
        print("NOTICE already present, skip")
        return 0
    backup = ENV_FILE + ".bak-p0-notice"
    with io.open(backup, "w", encoding="utf-8") as fh:
        fh.write(text)
    with io.open(ENV_FILE, "w", encoding="utf-8") as fh:
        fh.write(NOTICE + text)
    print("NOTICE prepended, backup at " + backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
