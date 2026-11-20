"""Unit tests for DSL loading and load-time static validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtest.core.errors import CaseLoadError
from flowtest.core.loader import check_suite, load_suite, load_suite_lenient

EXAMPLES = Path(__file__).resolve().parents[1] / "flowtest" / "examples" / "testcases"


def write(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "cases.yaml"
    target.write_text(text, encoding="utf-8")
    return target


def test_bundled_suite_loads_cleanly():
    suite = load_suite(EXAMPLES)
    assert len(suite.active_cases) == 17
    assert check_suite(suite) == []
    schema_checks = [v for c in suite.active_cases for v in c.validate if v.op == "schema"]
    assert schema_checks and all(v.schema for v in schema_checks)


def test_variables_can_be_overridden_from_cli():
    suite = load_suite(EXAMPLES, extra_vars={"admin_user": "override"})
    assert suite.variables["admin_user"] == "override"
    assert suite.base_url == ""


def test_base_url_can_be_overridden():
    suite = load_suite(EXAMPLES, base_url="http://example.test")
    assert suite.base_url == "http://example.test"


def test_unknown_operator_is_rejected(tmp_path):
    path = write(tmp_path, """cases:
  - id: a
    request:
      url: /x
    validate:
      - check: status_code
        op: no_such_op
        expect: 200
""")
    with pytest.raises(CaseLoadError, match="未知断言算子"):
        load_suite(path)


def test_undefined_variable_reference_is_rejected(tmp_path):
    path = write(tmp_path, """cases:
  - id: a
    request:
      url: /x
    validate:
      - check: status_code
        op: eq
        expect: 200
      - check: $.value
        op: eq
        expect: ${never_produced}
""")
    with pytest.raises(CaseLoadError, match="未定义且无人产出"):
        load_suite(path)


def test_valid_dataflow_passes(tmp_path):
    path = write(tmp_path, """cases:
  - id: producer
    request:
      url: /x
    extract:
      value: $.data.value
    validate:
      - check: status_code
        op: eq
        expect: 200
  - id: consumer
    depends_on: [producer]
    request:
      url: /y
      json:
        v: ${producer.value}
    validate:
      - check: $.value
        op: eq
        expect: ${producer.value}
""")
    assert check_suite(load_suite(path)) == []


def test_dependency_cycle_is_rejected(tmp_path):
    path = write(tmp_path, """cases:
  - id: a
    depends_on: [b]
    request: {url: /a}
    validate: [{check: status_code, op: eq, expect: 200}]
  - id: b
    depends_on: [a]
    request: {url: /b}
    validate: [{check: status_code, op: eq, expect: 200}]
""")
    with pytest.raises(CaseLoadError, match="环"):
        load_suite(path)


def test_lenient_mode_returns_all_problems_without_raising(tmp_path):
    path = write(tmp_path, """cases:
  - id: a
    request:
      url: /x
    validate:
      - check: status_code
        op: typo
        expect: 200
      - check: $.x
        op: eq
        expect: ${missing_var}
""")
    suite, problems = load_suite_lenient(path)
    assert suite is None
    assert len(problems) >= 2


def test_disabled_cases_are_excluded(tmp_path):
    path = write(tmp_path, """cases:
  - id: case_on
    request: {url: /a}
    validate: [{check: status_code, op: eq, expect: 200}]
  - id: case_off
    enabled: false
    request: {url: /b}
    validate: [{check: status_code, op: eq, expect: 200}]
""")
    suite = load_suite(path)
    assert [c.id for c in suite.active_cases] == ["case_on"]
    assert len(suite.cases) == 2
