"""Execution engine: layered DAG + retry + soft assertions + variable flow."""

from __future__ import annotations

import platform
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from flowtest.core.assertor import Assertor
from flowtest.core.client import RETRYABLE_STATUS, HttpClient
from flowtest.core.context import MISSING, Context
from flowtest.core.errors import ExtractError, RequestError, VariableNotFoundError
from flowtest.core.extractor import lookup
from flowtest.core.hooks import HookRegistry
from flowtest.core.models import (
    Attempt,
    Case,
    CaseResult,
    RequestSpec,
    RunResult,
    Status,
    Suite,
    Validation,
)
from flowtest.core.resolver import build_layers
from flowtest.utils.helpers import mask_sensitive, now_iso
from flowtest.utils.logger import log

try:
    from importlib.metadata import version as _pkg_version

    VERSION = _pkg_version("flowtest-framework")
except Exception:  # package not installed yet (running from source)
    VERSION = "0.1.0"


@dataclass
class RunnerConfig:
    parallel: int = 1
    soft: bool = False
    fail_fast: bool = False
    retry_backoff: float = 0.2
    retry_statuses: set[int] = field(default_factory=lambda: set(RETRYABLE_STATUS))


class Runner:
    def __init__(
        self,
        suite: Suite,
        client: HttpClient,
        config: RunnerConfig | None = None,
        variables: dict[str, Any] | None = None,
        hooks: HookRegistry | None = None,
    ) -> None:
        self.suite = suite
        self.client = client
        self.config = config or RunnerConfig()
        self.ctx = Context({**suite.variables, **(variables or {})})
        self.hooks = hooks or HookRegistry()
        self.assertor = Assertor()
        self._results: dict[str, CaseResult] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def run(self) -> RunResult:
        started_at = now_iso()
        t0 = time.perf_counter()
        cases = self.suite.active_cases
        layers = build_layers(cases)
        log.info(
            "执行计划: %d 个用例 / %d 层 / 并发度 %d",
            len(cases), len(layers), self.config.parallel,
        )

        halted = False
        for index, layer in enumerate(layers, start=1):
            log.info("L%d/%d -> %s", index, len(layers), ", ".join(c.id for c in layer))
            if halted:
                for case in layer:
                    self._store(self._skip(case, "fail-fast: 前序用例已失败"))
                continue

            if self.config.parallel > 1 and len(layer) > 1:
                workers = min(self.config.parallel, len(layer))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    list(pool.map(self._run_case, layer))
            else:
                for case in layer:
                    self._run_case(case)

            if self.config.fail_fast and any(
                r.status in (Status.FAILED, Status.ERROR) for r in self._results.values()
            ):
                halted = True
                log.warning("fail-fast 已触发，后续层的用例将被跳过")

        results = [self._results[c.id] for c in cases if c.id in self._results]
        duration_ms = (time.perf_counter() - t0) * 1000
        result = RunResult(
            suite_name=self.suite.name,
            results=results,
            base_url=self.client.base_url,
            started_at=started_at,
            finished_at=now_iso(),
            duration_ms=duration_ms,
            environment={
                "python": platform.python_version(),
                "platform": f"{platform.system()} {platform.release()}",
                "flowtest": VERSION,
                "parallel": self.config.parallel,
                "soft_assert": self.config.soft,
            },
        )
        log.info(
            "执行完成: %d passed / %d failed / %d skipped, 通过率 %.1f%%, 耗时 %.0f ms",
            result.passed, result.failed, result.skipped, result.pass_rate, duration_ms,
        )
        return result

    # ----------------------------------------------------------------- internals

    def _store(self, result: CaseResult) -> None:
        with self._lock:
            self._results[result.case.id] = result

    def _run_case(self, case: Case) -> None:
        bad = [
            dep for dep in case.depends_on
            if dep not in self._results or self._results[dep].status is not Status.PASSED
        ]
        if bad:
            self._store(self._skip(case, f"依赖用例未通过: {', '.join(bad)}"))
            return
        self._store(self._execute(case))

    @staticmethod
    def _skip(case: Case, reason: str) -> CaseResult:
        return CaseResult(case=case, status=Status.SKIPPED, skip_reason=reason)

    def _render(self, case: Case) -> RequestSpec:
        raw = case.request.to_dict()
        raw["headers"] = {**self.suite.headers, **raw["headers"]}
        return RequestSpec.from_dict(self.ctx.render(raw))

    @staticmethod
    def _request_snapshot(spec: RequestSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        data = spec.to_dict()
        data["headers"] = mask_sensitive(data["headers"])
        return data

    def _execute(self, case: Case) -> CaseResult:
        t0 = time.perf_counter()
        attempts: list[Attempt] = []
        max_attempts = case.retry + 1

        for index in range(max_attempts):
            spec: RequestSpec | None = None
            try:
                # Re-render on every attempt so ${{...}} generators produce fresh data.
                spec = self._render(case)
                self.hooks.run_before(case.id, self.ctx, case)
                response = self.client.request(spec)
                # Expect values may reference variables produced by upstream
                # cases, e.g. `expect: ${create_order.amount}`. Render them at
                # execution time, after that upstream case has actually run.
                validations = [
                    Validation(
                        op=v.op,
                        check=v.check,
                        expect=self.ctx.render(v.expect),
                        schema=v.schema,
                        soft=v.soft,
                        message=v.message,
                    )
                    for v in case.validate
                ]
                assertions, all_passed = self.assertor.run(
                    validations, response, self.config.soft
                )
                attempts.append(
                    Attempt(
                        request=self._request_snapshot(spec),
                        response=response.to_dict(),
                        assertions=assertions,
                        elapsed_ms=response.elapsed_ms,
                    )
                )

                # Only transport/5xx problems are retried; an assertion failure is
                # a real product signal and must never be hidden by a retry.
                if response.status_code in self.config.retry_statuses and index < max_attempts - 1:
                    log.warning(
                        "%s 收到可重试状态码 %s，第 %d 次重试",
                        case.id, response.status_code, index + 2,
                    )
                    time.sleep(self.config.retry_backoff * (index + 1))
                    continue

                extracted: dict[str, Any] = {}
                if all_passed:
                    for name, expr in case.extract.items():
                        value = lookup(response, expr)
                        value = None if value is MISSING else value
                        extracted[name] = value
                        self.ctx.set_case(case.id, name, value)
                    status = Status.PASSED
                else:
                    status = Status.FAILED
                    log.warning("%s 断言失败 (%d 条)", case.id, len([a for a in assertions if not a.passed]))
                return CaseResult(
                    case=case, status=status, attempts=attempts, extracted=extracted,
                    elapsed_ms=(time.perf_counter() - t0) * 1000,
                )

            except (RequestError, VariableNotFoundError, ExtractError) as exc:
                log.warning("%s 执行异常: %s", case.id, exc)
                attempts.append(
                    Attempt(
                        request=self._request_snapshot(spec),
                        response=None,
                        error=str(exc),
                        elapsed_ms=(time.perf_counter() - t0) * 1000,
                    )
                )
                if index < max_attempts - 1:
                    time.sleep(self.config.retry_backoff * (index + 1))
                    continue
                return CaseResult(
                    case=case, status=Status.ERROR, attempts=attempts,
                    elapsed_ms=(time.perf_counter() - t0) * 1000,
                    skip_reason=str(exc),
                )

        raise AssertionError("unreachable")

    @property
    def context_snapshot(self) -> dict[str, Any]:
        return self.ctx.snapshot()
