"""Dependency graph resolution (Kahn topological sort, layered).

Why layers instead of a flat order: cases in the same layer have no dependency
between them, so they can be executed in a thread pool. Cross-layer execution
stays strictly sequential, which makes variable propagation deterministic.

Cycle detection uses a second DFS pass purely to produce a *readable* cycle
path ("a -> b -> c -> a") instead of a generic "cycle detected" error.
"""

from __future__ import annotations

from flowtest.core.errors import CaseLoadError, DependencyError
from flowtest.core.models import Case


def validate_graph(cases: list[Case]) -> None:
    by_id: dict[str, Case] = {}
    for case in cases:
        if not case.id or not str(case.id).strip():
            raise CaseLoadError("存在缺少 id 的用例")
        if case.id in by_id:
            raise CaseLoadError(f"用例 id 重复: {case.id!r}（来源: {by_id[case.id].source} / {case.source}）")
        by_id[case.id] = case
    for case in cases:
        for dep in case.depends_on:
            if dep not in by_id:
                raise DependencyError(
                    f"用例 {case.id!r} 依赖了不存在的用例 {dep!r}（来源: {case.source}）"
                )


def find_cycle(cases: list[Case]) -> list[str]:
    """Return a concrete cycle path, or [] when the graph is acyclic."""
    by_id = {c.id: c for c in cases}
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(node: str) -> list[str]:
        color[node] = 1
        stack.append(node)
        for dep in by_id[node].depends_on:
            if dep not in by_id:
                continue
            if color.get(dep) == 1:
                return stack[stack.index(dep):] + [dep]
            if color.get(dep, 0) == 0:
                found = dfs(dep)
                if found:
                    return found
        stack.pop()
        color[node] = 2
        return []

    for case in cases:
        if color.get(case.id, 0) == 0:
            found = dfs(case.id)
            if found:
                return found
    return []


def build_layers(cases: list[Case]) -> list[list[Case]]:
    """Group cases into executable layers. O(V + E) plus one DFS validation."""
    validate_graph(cases)
    remaining: set[str] = {c.id for c in cases}
    indegree: dict[str, int] = {c.id: len(set(c.depends_on)) for c in cases}
    layers: list[list[Case]] = []

    while remaining:
        layer = [c for c in cases if c.id in remaining and indegree[c.id] == 0]
        if not layer:
            cycle = find_cycle(cases)
            raise DependencyError(f"用例依赖存在环: {' -> '.join(cycle) or '未知环'}")
        layers.append(layer)
        for done in layer:
            remaining.discard(done.id)
            for other in cases:
                if other.id in remaining and done.id in other.depends_on:
                    indegree[other.id] -= 1
    return layers


def describe_plan(cases: list[Case]) -> str:
    """Human-readable DAG used by `flowtest validate`."""
    lines: list[str] = []
    for index, layer in enumerate(build_layers(cases), start=1):
        mode = "并行" if len(layer) > 1 else "串行"
        names = ", ".join(f"{c.id}({c.name or '-'})" for c in layer)
        lines.append(f"  L{index} [{mode}] {names}")
    return "\n".join(lines)
