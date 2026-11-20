"""Formatting / redaction helpers used by logging and the HTML reporter."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

SENSITIVE_KEYS = re.compile(r"authorization|token|secret|password|cookie|api[-_]?key", re.I)
_REDACTED = "***REDACTED***"


def mask_sensitive(obj: Any) -> Any:
    """Recursively redact credentials so logs and reports are safe to share."""
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if SENSITIVE_KEYS.search(str(k)) else mask_sensitive(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [mask_sensitive(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("Bearer "):
        return "Bearer " + _REDACTED
    return obj


def json_dumps(obj: Any, *, pretty: bool = True) -> str:
    try:
        if pretty:
            return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)


def shorten(text: str, limit: int = 160) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
