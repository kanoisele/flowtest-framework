"""Unit tests for the execution engine using a fake HTTP client."""

from __future__ import annotations

from flowtest.core.models import (
    Case,
    RequestSpec,
    Response,
    Status,
    Suite,
    Validation,
)
from flowtest.core.runner import Runner, RunnerConfig


class FakeClient:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = list(responses)
        self.seen: list[RequestSpec] = []
        self.base_url = "http://fake.test"

    def request(self, spec: RequestSpec) -> Response:
        self.seen.append(spec)
        return self.responses.pop(0)

    def close(self) -> None:
        pass


def resp(status: int = 200, body=None) -> Response:
    return Response(
        status_code=status,
        headers={},
        body={} if body is None else body,
        text="",
        elapsed_ms=1.0,
    )


def status_check(expect: int = 200) -> list[Validation]:
    return [Validation(op="eq", check="status_code", expect=expect)]


def suite_of(*cases: Case) -> Suite:
    return Suite(cases=list(cases))


def test_failed_dependency_skips_downstream_cases():
    suite = suite_of(
        Case(id="a", request=RequestSpec(url="/a"), validate=status_check()),
        Case(id="b", depends_on=["a"], request=RequestSpec(url="/b"), validate=status_check()),
    )
    result = Runner(suite, FakeClient([resp(500)])).run()
    assert result.results[0].status is Status.FAILED
    assert result.results[1].status is Status.SKIPPED
    assert "依赖用例未通过" in result.results[1].skip_reason


def test_5xx_is_retried_until_success():
    suite = suite_of(
        Case(id="flaky", retry=2, request=RequestSpec(url="/x"), validate=status_check())
    )
    client = FakeClient([resp(503), resp(503), resp(200)])
    result = Runner(suite, client).run()
    assert result.ok
    assert len(result.results[0].attempts) == 3
    assert len(client.seen) == 3


def test_assertion_failure_is_never_retried():
    suite = suite_of(
        Case(id="bad", retry=3, request=RequestSpec(url="/x"), validate=status_check(201))
    )
    client = FakeClient([resp(200), resp(200), resp(200), resp(200)])
    result = Runner(suite, client).run()
    assert result.results[0].status is Status.FAILED
    assert len(result.results[0].attempts) == 1  # a real failure must not be hidden


def test_extracted_variables_flow_to_downstream_requests():
    suite = suite_of(
        Case(
            id="login",
            request=RequestSpec(url="/login"),
            extract={"token": "$.data.token"},
            validate=[Validation(op="eq", check="$.code", expect=0)],
        ),
        Case(
            id="profile",
            depends_on=["login"],
            request=RequestSpec(
                method="GET", url="/me", headers={"Authorization": "Bearer ${login.token}"}
            ),
            validate=status_check(),
        ),
    )
    client = FakeClient([resp(200, {"code": 0, "data": {"token": "T-9"}}), resp(200)])
    result = Runner(suite, client).run()
    assert result.ok
    assert result.results[0].extracted == {"token": "T-9"}
    assert client.seen[1].headers["Authorization"] == "Bearer T-9"


def test_expect_values_are_rendered_at_execution_time():
    suite = suite_of(
        Case(
            id="producer",
            request=RequestSpec(url="/p"),
            extract={"amount": "$.data.amount"},
            validate=status_check(),
        ),
        Case(
            id="consumer",
            depends_on=["producer"],
            request=RequestSpec(url="/c"),
            validate=[Validation(op="eq", check="$.data.amount", expect="${producer.amount}")],
        ),
    )
    client = FakeClient([
        resp(200, {"data": {"amount": 42}}),
        resp(200, {"data": {"amount": 42}}),
    ])
    assert Runner(suite, client).run().ok


def test_fail_fast_skips_unrelated_downstream_layers():
    suite = suite_of(
        Case(id="a", request=RequestSpec(url="/a"), validate=status_check()),
        Case(id="b", request=RequestSpec(url="/b"), validate=status_check()),
        Case(id="d", depends_on=["b"], request=RequestSpec(url="/d"), validate=status_check()),
    )
    result = Runner(suite, FakeClient([resp(500), resp(200)]), RunnerConfig(fail_fast=True)).run()
    statuses = [r.status for r in result.results]
    assert statuses == [Status.FAILED, Status.PASSED, Status.SKIPPED]
    assert "fail-fast" in result.results[2].skip_reason


def test_run_result_summary():
    suite = suite_of(
        Case(id="a", request=RequestSpec(url="/a"), validate=status_check()),
        Case(id="b", request=RequestSpec(url="/b"), validate=status_check()),
    )
    result = Runner(suite, FakeClient([resp(200), resp(200)])).run()
    assert (result.total, result.passed, result.failed, result.skipped) == (2, 2, 0, 0)
    assert result.pass_rate == 100.0 and result.ok
