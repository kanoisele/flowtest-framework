"""Minimal, explicit hook registry.

Hooks are opt-in and name-based (never arbitrary eval of YAML content): the
DSL can only reference functions that were registered here. That keeps the
framework extensible without turning case files into a code-execution surface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flowtest.core.context import Context
from flowtest.utils.logger import log

HookFn = Callable[[str, Context, Any], None]


class HookRegistry:
    def __init__(self) -> None:
        self._before: dict[str, HookFn] = {}
        self._after: dict[str, HookFn] = {}
        self._install_builtins()

    def register(self, name: str, fn: HookFn, when: str = "before") -> None:
        target = self._before if when == "before" else self._after
        target[name] = fn

    def known(self, when: str = "before") -> list[str]:
        return sorted(self._before if when == "before" else self._after)

    def run_before(self, case_id: str, ctx: Context, payload: Any) -> None:
        for name in getattr(payload, "hooks", []) or []:
            fn = self._before.get(name)
            if fn is None:
                log.warning("用例 %s 引用了未注册的 hook: %s", case_id, name)
                continue
            fn(case_id, ctx, payload)

    def _install_builtins(self) -> None:
        def set_timestamp(case_id: str, ctx: Context, payload: Any) -> None:
            ctx.set(f"{case_id}.started_at", __import__("time").time())

        def log_case(case_id: str, ctx: Context, payload: Any) -> None:
            log.info("准备执行用例: %s (%s 个断言)", case_id, len(payload.validate))

        def assert_no_slow_response(case_id: str, ctx: Context, payload: Any) -> None:
            log.debug("hook: %s 默认超时 %.1fs", case_id, payload.request.timeout)

        self.register("set_timestamp", set_timestamp)
        self.register("log_case", log_case)
        self.register("trace_timeout", assert_no_slow_response)
