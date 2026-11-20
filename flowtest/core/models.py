"""Plain data models shared by loader, runner and reporter.

Kept dependency-free (dataclasses only) on purpose: the reporter can serialize
them without importing the HTTP layer, and unit tests can build them by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class RequestSpec:
    method: str = "GET"
    url: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    timeout: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "params": dict(self.params),
            "headers": dict(self.headers),
            "body": self.body,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequestSpec:
        return cls(
            method=str(data.get("method", "GET")).upper(),
            url=str(data.get("url", "")),
            params=dict(data.get("params") or {}),
            headers=dict(data.get("headers") or {}),
            body=data.get("body"),
            timeout=float(data.get("timeout", 10.0)),
        )


@dataclass
class Validation:
    op: str
    check: str = ""
    expect: Any = None
    schema: dict[str, Any] | None = None
    soft: bool = False
    message: str = ""

    def label(self) -> str:
        if self.op == "schema":
            return "schema"
        return f"{self.check} {self.op} {self.expect!r}"


@dataclass
class Case:
    id: str
    name: str = ""
    description: str = ""
    request: RequestSpec = field(default_factory=RequestSpec)
    depends_on: list[str] = field(default_factory=list)
    extract: dict[str, str] = field(default_factory=dict)
    validate: list[Validation] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    retry: int = 0
    enabled: bool = True
    hooks: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class Suite:
    name: str = "flowtest suite"
    base_url: str = ""
    cases: list[Case] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    path: Path | None = None

    @property
    def active_cases(self) -> list[Case]:
        return [c for c in self.cases if c.enabled]


@dataclass
class Response:
    status_code: int
    headers: dict[str, str]
    body: Any
    text: str
    elapsed_ms: float
    url: str = ""
    method: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "headers": dict(self.headers),
            "body": self.body,
            "text": self.text,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "url": self.url,
            "method": self.method,
        }


@dataclass
class AssertionResult:
    op: str
    check: str
    expect: Any
    actual: Any
    passed: bool
    message: str = ""
    soft: bool = False


@dataclass
class Attempt:
    """One single HTTP attempt of a case (a case may have several on retry)."""

    request: dict[str, Any]
    response: dict[str, Any] | None
    assertions: list[AssertionResult] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass
class CaseResult:
    case: Case
    status: Status
    attempts: list[Attempt] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    skip_reason: str = ""

    @property
    def last(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def failed_assertions(self) -> list[AssertionResult]:
        if not self.last:
            return []
        return [a for a in self.last.assertions if not a.passed]


@dataclass
class RunResult:
    suite_name: str
    results: list[CaseResult]
    base_url: str
    started_at: str
    finished_at: str
    duration_ms: float
    environment: dict[str, Any] = field(default_factory=dict)

    def count(self, status: Status) -> int:
        return sum(1 for r in self.results if r.status is status)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return self.count(Status.PASSED)

    @property
    def failed(self) -> int:
        return self.count(Status.FAILED) + self.count(Status.ERROR)

    @property
    def skipped(self) -> int:
        return self.count(Status.SKIPPED)

    @property
    def pass_rate(self) -> float:
        executed = self.total - self.skipped
        return (self.passed / executed * 100) if executed else 0.0

    @property
    def ok(self) -> bool:
        return self.failed == 0
