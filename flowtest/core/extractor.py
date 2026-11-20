"""Response value lookup.

Convention used everywhere in the DSL: a JSONPath expression is evaluated with
the **response body as its root**, e.g. ``$.data.token``. A few virtual roots
are provided for non-body metadata: ``status_code``, ``elapsed_ms`` and
``headers.<Name>``.

``MISSING`` is a sentinel (not ``None``) so "path not found" and "JSON null"
are distinguishable — that distinction matters for ``exists`` assertions.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from jsonpath_ng import parse as _jsonpath_parse

from flowtest.core.context import MISSING
from flowtest.core.errors import ExtractError
from flowtest.core.models import Response


@lru_cache(maxsize=256)
def _compile(expr: str):
    return _jsonpath_parse(expr)


def lookup(response: Response, expr: str) -> Any:
    expr = (expr or "").strip()
    if not expr:
        return MISSING
    if expr == "status_code":
        return response.status_code
    if expr == "elapsed_ms":
        return round(response.elapsed_ms, 2)
    if expr == "text":
        return response.text
    if expr == "body":
        return response.body
    if expr.lower().startswith("headers."):
        key = expr.split(".", 1)[1].lower()
        for name, value in response.headers.items():
            if name.lower() == key:
                return value
        return MISSING

    path = expr if expr.startswith(("$", "@")) else f"$.{expr.lstrip('.')}"
    root = response.body if response.body is not None else {}
    try:
        matches = _compile(path).find(root)
    except Exception as exc:  # jsonpath_ng raises a variety of parser errors
        raise ExtractError(f"非法 JSONPath 表达式 {expr!r}: {exc}") from exc
    if not matches:
        return MISSING
    if len(matches) == 1:
        return matches[0].value
    return [m.value for m in matches]


def describe(expr: str) -> str:
    """Static syntax check used by the loader (fail fast, at load time)."""
    expr = (expr or "").strip()
    if expr in {"status_code", "elapsed_ms", "text", "body"} or expr.lower().startswith("headers."):
        return expr  # virtual roots, not JSONPath
    path = expr if expr.startswith(("$", "@")) else f"$.{expr.lstrip('.')}"
    try:
        _compile(path)
    except Exception as exc:  # jsonpath_ng raises several parser-specific errors
        raise ExtractError(f"非法 JSONPath 表达式 {expr!r}: {exc}") from exc
    return path
