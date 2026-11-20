"""Assertion engine.

Two ideas that differentiate a *framework* from a pile of assert statements:

1. An operator registry instead of if/else chains — adding an operator is one
   function, and the loader can validate operator names at load time.
2. Soft assertions: keep evaluating after a failure and report every mismatch
   in one run. On a big response this cuts the debug cycle from N runs to 1.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import jsonschema

from flowtest.core.context import MISSING
from flowtest.core.extractor import lookup
from flowtest.core.models import AssertionResult, Response, Validation

OpFn = Callable[[Any, Any, str], tuple[bool, str]]


def _number(value: Any) -> float:
    return float(value)


def _ok(actual: Any, expect: Any, op: str) -> tuple[bool, str]:
    return True, f"{actual!r} {op} {expect!r}"


def _bad(actual: Any, expect: Any, op: str, extra: str = "") -> tuple[bool, str]:
    tail = f"；{extra}" if extra else ""
    return False, f"校验不成立：{actual!r} {op} {expect!r}{tail}"


class Assertor:
    """Stateless validator. Returns (results, all_passed)."""

    OPS: dict[str, OpFn] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(fn: OpFn) -> OpFn:
            cls.OPS[name] = fn
            return fn

        return decorator

    @classmethod
    def available_ops(cls) -> list[str]:
        return sorted(cls.OPS)

    def run(
        self,
        validations: list[Validation],
        response: Response,
        default_soft: bool = False,
    ) -> tuple[list[AssertionResult], bool]:
        results: list[AssertionResult] = []
        for item in validations:
            result = self._one(item, response)
            results.append(result)
            # Hard assertions short-circuit; soft ones keep collecting evidence.
            if not result.passed and not (item.soft or default_soft):
                break
        return results, all(r.passed for r in results)

    def _one(self, item: Validation, response: Response) -> AssertionResult:
        op = item.op
        if op == "schema":
            return self._schema(item, response)

        fn = self.OPS.get(op)
        if fn is None:
            return AssertionResult(op, item.check, item.expect, None, False, f"未知断言算子: {op}", item.soft)

        actual = lookup(response, item.check) if item.check else MISSING
        if actual is MISSING and op not in {"exists", "not_exists", "is_null"}:
            return AssertionResult(
                op, item.check, item.expect, "<MISSING>", False,
                f"取值路径 {item.check!r} 在响应中不存在", item.soft,
            )
        if actual is MISSING and op == "is_null":
            # A missing path is treated as null for is_null, but stays MISSING
            # for exists/not_exists so those two can tell the difference.
            actual = None

        try:
            passed, message = fn(actual, item.expect, op)
        except (TypeError, ValueError, re.error) as exc:
            passed, message = False, f"断言执行异常 ({type(exc).__name__}): {exc}"
        if item.message:
            message = f"{item.message} | {message}"
        return AssertionResult(op, item.check, item.expect, actual, passed, message, item.soft)

    @staticmethod
    def _schema(item: Validation, response: Response) -> AssertionResult:
        if not item.schema:
            return AssertionResult("schema", "", None, response.body, False, "未提供 JSON Schema", item.soft)
        try:
            jsonschema.validate(response.body, item.schema)
            return AssertionResult("schema", "", "<schema>", "valid", True, "响应符合契约定义", item.soft)
        except jsonschema.ValidationError as exc:
            path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
            return AssertionResult(
                "schema", "", "<schema>", f"{path}: {exc.message}", False,
                f"契约校验失败 @ {path}: {exc.message}", item.soft,
            )
        except jsonschema.SchemaError as exc:
            return AssertionResult("schema", "", None, None, False, f"Schema 本身非法: {exc.message}", item.soft)


# --------------------------------------------------------------------- operators


@Assertor.register("eq")
def _eq(actual, expect, op):
    return (True, f"{actual!r} == {expect!r}") if actual == expect else _bad(actual, expect, op)


@Assertor.register("ne")
def _ne(actual, expect, op):
    return (True, f"{actual!r} != {expect!r}") if actual != expect else _bad(actual, expect, op)


def _compare(actual, expect, op, predicate):
    try:
        a, e = _number(actual), _number(expect)
    except (TypeError, ValueError):
        return False, f"{op} 需要数值，实际 {actual!r} / {expect!r}"
    return (True, f"{actual!r} {op} {expect!r}") if predicate(a, e) else _bad(actual, expect, op)


Assertor.OPS["gt"] = lambda a, e, o: _compare(a, e, o, lambda x, y: x > y)
Assertor.OPS["ge"] = lambda a, e, o: _compare(a, e, o, lambda x, y: x >= y)
Assertor.OPS["lt"] = lambda a, e, o: _compare(a, e, o, lambda x, y: x < y)
Assertor.OPS["le"] = lambda a, e, o: _compare(a, e, o, lambda x, y: x <= y)


@Assertor.register("contains")
def _contains(actual, expect, op):
    try:
        hit = expect in actual
    except TypeError:
        hit = False
    return (True, f"{actual!r} 包含 {expect!r}") if hit else _bad(actual, expect, op)


@Assertor.register("not_contains")
def _not_contains(actual, expect, op):
    try:
        hit = expect not in actual
    except TypeError:
        hit = True
    return (True, f"{actual!r} 不包含 {expect!r}") if hit else _bad(actual, expect, op)


@Assertor.register("in")
def _in(actual, expect, op):
    try:
        hit = actual in expect
    except TypeError:
        hit = False
    return (True, f"{actual!r} 属于 {expect!r}") if hit else _bad(actual, expect, op, "expect 需为可迭代对象")


@Assertor.register("not_in")
def _not_in(actual, expect, op):
    try:
        hit = actual not in expect
    except TypeError:
        hit = False
    return (True, f"{actual!r} 不属于 {expect!r}") if hit else _bad(actual, expect, op)


@Assertor.register("regex")
def _regex(actual, expect, op):
    hit = re.search(str(expect), str(actual)) is not None
    return (True, f"{actual!r} 匹配 /{expect}/") if hit else _bad(actual, expect, op)


@Assertor.register("startswith")
def _startswith(actual, expect, op):
    hit = str(actual).startswith(str(expect))
    return (True, f"{actual!r} 以 {expect!r} 开头") if hit else _bad(actual, expect, op)


@Assertor.register("endswith")
def _endswith(actual, expect, op):
    hit = str(actual).endswith(str(expect))
    return (True, f"{actual!r} 以 {expect!r} 结尾") if hit else _bad(actual, expect, op)


@Assertor.register("len_eq")
def _len_eq(actual, expect, op):
    try:
        hit = len(actual) == int(expect)
    except (TypeError, ValueError):
        hit = False
    return (True, f"len({actual!r}) == {expect}") if hit else _bad(actual, expect, op)


@Assertor.register("len_ge")
def _len_ge(actual, expect, op):
    try:
        hit = len(actual) >= int(expect)
    except (TypeError, ValueError):
        hit = False
    return (True, f"len({actual!r}) >= {expect}") if hit else _bad(actual, expect, op)


@Assertor.register("is_null")
def _is_null(actual, expect, op):
    return (True, "值为 null") if actual is None else _bad(actual, None, op)


@Assertor.register("not_null")
def _not_null(actual, expect, op):
    return (True, f"值非 null ({actual!r})") if actual is not None else _bad(actual, None, op)


@Assertor.register("exists")
def _exists(actual, expect, op):
    return (True, "路径存在") if actual is not MISSING else _bad("<MISSING>", None, op)


@Assertor.register("not_exists")
def _not_exists(actual, expect, op):
    return (True, "路径不存在") if actual is MISSING else _bad(actual, None, op)


@Assertor.register("type")
def _type(actual, expect, op):
    name = "none" if actual is None else type(actual).__name__
    hit = name.lower() == str(expect).lower()
    return (True, f"类型为 {name}") if hit else _bad(name, expect, op)
