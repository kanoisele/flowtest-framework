"""A single, consistently configured logger for the whole framework."""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def get_logger(name: str = "flowtest") -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        level = os.getenv("FLOWTEST_LOG_LEVEL", "INFO").upper()
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
        )
        root = logging.getLogger("flowtest")
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(getattr(logging, level, logging.INFO))
        root.propagate = False
        _CONFIGURED = True
    return logger


log = get_logger()
