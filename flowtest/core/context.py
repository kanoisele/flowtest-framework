"""Runtime variable pool and ${...} template rendering.

Design notes (these are the parts worth explaining in an interview):

* Variable keys are namespaced as ``<case_id>.<extract_name>``. That makes the
  data flow explicit: ``${login.token}`` can only come from the ``login`` case.
* A token that is the *entire* string keeps its original Python type, so
  ``expect: ${expected_total}`` stays an int instead of becoming ``"3"``.
* ``${{func(args)}}`` built-ins are resolved before variable substitution,
  which lets a case generate fresh data on every attempt (idempotency tests).
"""

from __future__ import annotations

import os
import random
import re
import string
import time
import uuid
from typing import Any

from flowtest.core.errors import VariableNotFoundError
from flowtest.utils.helpers import md5

_FUNC = re.compile(r"\$\{\{([^{}]+)\}\}")
_TOKEN = re.compile(r"\$\{([^{}]+)\}")
_CALL = re.compile(r"^(\w+)\((.*)\)$", re.S)


class _MissingSentinel:
    def __repr__(self) -> str:
        return "<MISSING>"


MISSING = _MissingSentinel()


class Context:
    def __init__(self, variables: dict[str, Any] | None = None) -> None:
        self._vars: dict[str, Any] = dict(variables or {})

    def set(self, key: str, value: Any) -> None:
        self._vars[key] = value

    def set_case(self, case_id: str, name: str, value: Any) -> None:
        self.set(f"{case_id}.{name}", value)

    def get(self, key: str) -> Any:
        key = key.strip()
        if key in self._vars:
            return self._vars[key]

        # Support dotted access into nested structures: ${login.data.user.id}
        node: Any = self._vars
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, (list, tuple)) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                raise VariableNotFoundError(
                    f"变量 ${{{key}}} 未定义。已可用变量: {', '.join(sorted(self._vars)[:12])}"
                    + (" ..." if len(self._vars) > 12 else "")
                )
        return node

    def snapshot(self) -> dict[str, Any]:
        return dict(self._vars)

    # ------------------------------------------------------------------ render

    def render(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            # A whole-string function call -> return its raw result (may be int).
            match = _FUNC.fullmatch(stripped)
            if match:
                return self._call(match.group(1))
            # A whole-string variable -> preserve the original Python type.
            match = _TOKEN.fullmatch(stripped)
            if match:
                return self.get(match.group(1))
            return self._render_string(value)
        if isinstance(value, dict):
            return {k: self.render(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.render(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.render(v) for v in value)
        return value

    def _render_string(self, text: str) -> str:
        text = _FUNC.sub(lambda m: str(self._call(m.group(1))), text)
        return _TOKEN.sub(lambda m: str(self.get(m.group(1))), text)

    # -------------------------------------------------------------- built-ins

    def _call(self, expr: str) -> Any:
        match = _CALL.match(expr.strip())
        if not match:
            raise VariableNotFoundError(f"内置函数语法错误: ${{{{{expr}}}}}")
        name, raw_args = match.group(1), match.group(2)
        args = [self._coerce(a) for a in raw_args.split(",")] if raw_args.strip() else []
        try:
            fn = getattr(self, f"_fn_{name}")
        except AttributeError as exc:
            raise VariableNotFoundError(f"未知内置函数: {name}()") from exc
        return fn(*args)

    @staticmethod
    def _coerce(raw: str) -> Any:
        raw = raw.strip()
        if not raw:
            return ""
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            return raw[1:-1]
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        return raw

    @staticmethod
    def _fn_uuid() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _fn_timestamp() -> int:
        return int(time.time())

    @staticmethod
    def _fn_timestamp_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _fn_random_int(low: int = 0, high: int = 100) -> int:
        return random.randint(int(low), int(high))

    @staticmethod
    def _fn_random_str(length: int = 8) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=int(length)))

    @staticmethod
    def _fn_md5(text: str = "") -> str:
        return md5(str(text))

    @staticmethod
    def _fn_env(key: str = "", default: str = "") -> str:
        return os.getenv(str(key), str(default))

    @staticmethod
    def _fn_now(fmt: str = "") -> str:
        from datetime import datetime

        return datetime.now().strftime(str(fmt)) if fmt else datetime.now().isoformat(timespec="seconds")
