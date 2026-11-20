"""Unit tests for the dependency graph."""

from __future__ import annotations

import pytest

from flowtest.core.errors import CaseLoadError, DependencyError
from flowtest.core.models import Case
from flowtest.core.resolver import build_layers, describe_plan, find_cycle


def case(cid: str, deps: tuple[str, ...] = ()) -> Case:
    return Case(id=cid, depends_on=list(deps))


def test_layered_topological_order():
    cases = [
        case("a"), case("b", ("a",)), case("c", ("a",)),
        case("d", ("b", "c")), case("e"),
    ]
    layers = build_layers(cases)
    assert [[c.id for c in layer] for layer in layers] == [
        ["a", "e"], ["b", "c"], ["d"],
    ]


def test_single_case():
    assert [[c.id for c in layer] for layer in build_layers([case("only")])] == [["only"]]


def test_cycle_is_detected_and_reported_with_path():
    cases = [case("a", ("c",)), case("b", ("a",)), case("c", ("b",))]
    cycle = find_cycle(cases)
    assert cycle and cycle[0] == cycle[-1]
    with pytest.raises(DependencyError, match="环"):
        build_layers(cases)


def test_missing_dependency():
    with pytest.raises(DependencyError, match="不存在"):
        build_layers([case("a", ("ghost",))])


def test_duplicate_case_id():
    with pytest.raises(CaseLoadError, match="重复"):
        build_layers([case("a"), case("a")])


def test_describe_plan_marks_parallel_layers():
    output = describe_plan([case("a"), case("b"), case("c", ("a", "b"))])
    assert "L1 [并行]" in output
    assert "L2 [串行]" in output
