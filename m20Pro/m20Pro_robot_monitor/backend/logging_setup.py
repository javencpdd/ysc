"""结构化 JSON 日志（PLAN §8 可观测性）。

为什么自己配 handler：uvicorn 会重置 root logger 的 handler，导致 app 层日志被吞掉
（表现为 journal 里只有 access log，看不到收包/解析/错误日志）。这里显式给
``m20.console`` logger 挂 StreamHandler 并禁止向 root 传播。

零第三方依赖：只用 stdlib logging（PLAN §13.3 依赖最小化）。
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Dict, Optional

LOGGER_NAME = "m20.console"


class JsonFormatter(logging.Formatter):
    """单行 JSON 日志：便于 journald / 后续采集。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 允许 logger.info("...", extra={"event": "stale", "topic": "motion"})
        for key in ("event", "topic", "topic_key", "packets", "reason", "cmd"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """配置并返回 app logger（幂等）。"""
    logger = logging.getLogger(LOGGER_NAME)
    level_value = getattr(logging, str(level).upper(), logging.INFO)
    logger.setLevel(level_value)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    # 防止向 root 重复传播（uvicorn 的 handler 已在 root 上）
    logger.propagate = False
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """取 app logger 的子 logger，如 ``m20.console.ingestion``。"""
    if not logging.getLogger(LOGGER_NAME).handlers:
        setup_logging()
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger("%s.%s" % (LOGGER_NAME, name))
