"""Unit tests for variable rendering."""

from __future__ import annotations

import hashlib

import pytest

from flowtest.core.context import Context
from flowtest.core.errors import VariableNotFoundError


def test_whole_token_preserves_original_type():
    ctx = Context({"count": 3, "enabled": True, "name": "admin"})
    assert ctx.render("${count}") == 3
    assert isinstance(ctx.render("${count}"), int)
    assert ctx.render("${enabled}") is True
    assert ctx.render("${name}") == "admin"


def test_nested_structures_are_rendered_recursively():
    ctx = Context({"n": 3})
    rendered = ctx.render({"a": "${n}", "b": ["${n}", "id-${n}", 5], "c": {"d": "${n}"}})
    assert rendered == {"a": 3, "b": [3, "id-3", 5], "c": {"d": 3}}


def test_case_namespaced_variables():
    ctx = Context()
    ctx.set_case("login", "token", "T-123")
    assert ctx.render("Bearer ${login.token}") == "Bearer T-123"
    assert ctx.get("login.token") == "T-123"


def test_dotted_path_into_nested_data():
    ctx = Context({"payload": {"items": [10, 20]}})
    assert ctx.render("${payload.items.1}") == 20


def test_builtin_functions():
    ctx = Context()
    assert len(ctx.render("${{uuid()}}")) == 32
    assert 1 <= ctx.render("${{random_int(1,5)}}") <= 5
    assert ctx.render("${{md5(abc)}}") == hashlib.md5(b"abc").hexdigest()  # noqa: S324
    assert len(ctx.render("${{random_str(12)}}")) == 12
    assert isinstance(ctx.render("${{timestamp()}}"), int)


def test_builtin_functions_are_not_mistaken_for_variables():
    ctx = Context()
    assert ctx.render("prefix-${{random_str(4)}}-suffix").startswith("prefix-")


def test_undefined_variable_raises_with_available_keys():
    ctx = Context({"known": 1})
    with pytest.raises(VariableNotFoundError, match="known"):
        ctx.render("${typo}")


def test_unknown_builtin_raises():
    with pytest.raises(VariableNotFoundError, match="未知内置函数"):
        Context().render("${{no_such_fn()}}")
