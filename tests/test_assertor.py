"""Unit tests for the assertion engine."""

from __future__ import annotations

import pytest

from flowtest.core.assertor import Assertor
from flowtest.core.models import Response, Validation


def response(body, status=200):
    return Response(status_code=status, headers={}, body=body, text=str(body), elapsed_ms=5.0)


@pytest.mark.parametrize(
    "op,actual,expect,expected",
    [
        ("eq", 1, 1, True), ("eq", 1, 2, False), ("ne", 1, 2, True),
        ("gt", 5, 3, True), ("gt", 2, 3, False), ("ge", 3, 3, True),
        ("lt", 2, 3, True), ("le", 3, 3, True),
        ("contains", "hello world", "world", True),
        ("contains", [1, 2, 3], 2, True),
        ("contains", {"a": 1}, "a", True),
        ("not_contains", "abc", "z", True),
        ("in", 2, [1, 2, 3], True), ("not_in", 9, [1, 2, 3], True),
        ("regex", "ORD-AB12", r"^ORD-[A-Z0-9]+$", True),
        ("regex", "bad", r"^\d+$", False),
        ("startswith", "Bearer x", "Bearer", True),
        ("endswith", "a.json", ".json", True),
        ("len_eq", [1, 2], 2, True), ("len_ge", [1, 2, 3], 2, True),
        ("type", 5, "int", True), ("type", [1], "list", True),
        ("not_null", "x", None, True),
    ],
)
def test_operators(op, actual, expect, expected):
    results, passed = Assertor().run(
        [Validation(op=op, check="$.v", expect=expect)], response({"v": actual})
    )
    assert passed is expected
    assert len(results) == 1


def test_null_operator_distinguishes_json_null_from_missing_path():
    assert Assertor().run(
        [Validation(op="is_null", check="$.v")], response({"v": None})
    )[1] is True
    assert Assertor().run(
        [Validation(op="exists", check="$.v")], response({"v": None})
    )[1] is True
    assert Assertor().run(
        [Validation(op="exists", check="$.missing")], response({"v": 1})
    )[1] is False
    assert Assertor().run(
        [Validation(op="not_exists", check="$.missing")], response({"v": 1})
    )[1] is True


def test_hard_assertion_short_circuits_but_soft_collects_all():
    validations = [
        Validation(op="eq", check="$.v", expect=2),
        Validation(op="eq", check="$.v", expect=3),
    ]
    results, passed = Assertor().run(validations, response({"v": 1}))
    assert len(results) == 1 and passed is False

    results, passed = Assertor().run(validations, response({"v": 1}), default_soft=True)
    assert len(results) == 2 and passed is False
    assert all(not r.passed for r in results)


def test_schema_validation_reports_json_path():
    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "integer"}},
    }
    ok_results, ok = Assertor().run([Validation(op="schema", schema=schema)], response({"id": 1}))
    assert ok and "符合契约" in ok_results[0].message

    bad_results, bad = Assertor().run(
        [Validation(op="schema", schema=schema)], response({"id": "oops"})
    )
    assert bad is False and "契约校验失败" in bad_results[0].message


def test_unknown_operator_is_reported_as_a_result_not_an_exception():
    results, passed = Assertor().run(
        [Validation(op="typo_op", check="$.v", expect=1)], response({"v": 1})
    )
    assert passed is False and "未知断言算子" in results[0].message


def test_missing_path_produces_clear_message():
    results, passed = Assertor().run(
        [Validation(op="eq", check="$.nope", expect=1)], response({"v": 1})
    )
    assert passed is False and "不存在" in results[0].message
