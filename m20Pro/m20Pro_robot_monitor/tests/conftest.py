"""pytest 公共配置：把 backend 加入模块搜索路径（与 main.py 的 sys.path 处理一致）。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
for path in (BACKEND, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)
