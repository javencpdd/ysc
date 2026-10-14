"""python -m webconsole —— 控制台入口（systemd ExecStart 调它）。"""
from __future__ import annotations

from .server import main

if __name__ == "__main__":
    raise SystemExit(main())
