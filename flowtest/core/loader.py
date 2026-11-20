"""YAML DSL loader with load-time static validation.

The loader is deliberately strict: unknown operators, broken JSONPath, missing
schema files and dependency cycles are all reported *before* a single HTTP
request is sent. Shifting errors left is the single biggest quality win in a
test framework — a typo in case #47 should not waste a 10-minute run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from flowtest.core.assertor import Assertor
from flowtest.core.errors import CaseLoadError, FlowTestError
from flowtest.core.extractor import describe
from flowtest.core.hooks import HookRegistry
from flowtest.core.models import Case, RequestSpec, Suite, Validation
from flowtest.core.resolver import find_cycle, validate_graph

CASE_SUFFIXES = {".yaml", ".yml"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
VALID_OPS = set(Assertor.available_ops()) | {"schema"}
_VAR_REF = re.compile(r"\$\{([^{}]+)\}")


def _collect_refs(value: Any) -> set[str]:
    """Find every ${...} reference in a nested structure (${{func()}} excluded)."""
    found: set[str] = set()
    if isinstance(value, str):
        found.update(m.group(1).strip() for m in _VAR_REF.finditer(value))
    elif isinstance(value, dict):
        for key, item in value.items():
            found |= _collect_refs(key) | _collect_refs(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found |= _collect_refs(item)
    return found


def iter_case_files(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(f for f in path.iterdir() if f.suffix.lower() in CASE_SUFFIXES)
    raise CaseLoadError(f"用例路径不存在: {path}")


def _resolve_ref(ref: str, case_file: Path, root: Path) -> Path:
    """Resolve schema_file relative to CWD, suite root, project root, ... in order."""
    candidates = [
        Path(ref),
        root / ref,
        case_file.parent / ref,
        root.parent / ref,
        case_file.parent.parent / ref,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise CaseLoadError(f"引用文件不存在: {ref!r}（用例来源 {case_file.name}）")


def _parse_validation(raw: dict[str, Any], case_file: Path, root: Path, case_id: str) -> Validation:
    if not isinstance(raw, dict):
        raise CaseLoadError(f"用例 {case_id!r} 的 validate 条目必须是映射")
    op = str(raw.get("op", "eq")).strip()
    schema: dict[str, Any] | None = None
    if op == "schema":
        value = raw.get("schema_file") or raw.get("schema")
        if isinstance(value, str):
            schema_path = _resolve_ref(value, case_file, root)
            try:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CaseLoadError(f"{schema_path.name} 不是合法 JSON: {exc}") from exc
        elif isinstance(value, dict):
            schema = value
    return Validation(
        op=op,
        check=str(raw.get("check") or "").strip(),
        expect=raw.get("expect"),
        schema=schema,
        soft=bool(raw.get("soft", False)),
        message=str(raw.get("message") or ""),
    )


def _parse_case(raw: dict[str, Any], case_file: Path, root: Path) -> Case:
    if not isinstance(raw, dict):
        raise CaseLoadError(f"{case_file.name}: cases 的每个元素必须是映射")
    case_id = str(raw.get("id") or "").strip()
    req_raw = dict(raw.get("request") or {})
    body = req_raw.pop("json", None)
    if body is None:
        body = req_raw.pop("data", None)
    if body is None:
        body = req_raw.pop("body", None)
    spec = RequestSpec(
        method=str(req_raw.pop("method", "GET")).upper(),
        url=str(req_raw.pop("url", "")).strip(),
        params=req_raw.pop("params", {}) or {},
        headers=req_raw.pop("headers", {}) or {},
        body=body,
        timeout=float(req_raw.pop("timeout", 10.0)),
    )
    validations = [
        _parse_validation(v, case_file, root, case_id or "<no-id>")
        for v in (raw.get("validate") or [])
    ]
    return Case(
        id=case_id,
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        request=spec,
        depends_on=[str(d) for d in (raw.get("depends_on") or [])],
        extract={str(k): str(v) for k, v in (raw.get("extract") or {}).items()},
        validate=validations,
        tags=[str(t) for t in (raw.get("tags") or [])],
        retry=int(raw.get("retry", 0) or 0),
        enabled=bool(raw.get("enabled", True)),
        hooks=[str(h) for h in (raw.get("hooks") or [])],
        source=case_file.name,
    )


def check_suite(suite: Suite) -> list[str]:
    """Collect every problem instead of stopping at the first one."""
    problems: list[str] = []
    cases = suite.active_cases
    try:
        validate_graph(cases)
        cycle = find_cycle(cases)
        if cycle:
            problems.append(f"用例依赖存在环: {' -> '.join(cycle)}")
    except FlowTestError as exc:
        problems.append(str(exc))

    known_ids = {c.id for c in cases}
    known_hooks = set(HookRegistry().known())
    # Static data-flow check: every ${...} must be either a suite variable or a
    # value exported by another case. Typos are caught before any HTTP call.
    produced = set(suite.variables) | {f"{c.id}.{name}" for c in cases for name in c.extract}
    for case in cases:
        where = f"[{case.source}::{case.id}]"
        refs = _collect_refs(case.request.to_dict()) | _collect_refs(
            [v.expect for v in case.validate]
        )
        for ref in sorted(refs - produced):
            problems.append(
                f"{where} 引用了未定义且无人产出的变量 ${{{ref}}}"
                "（检查 suite.variables 或上游用例的 extract / depends_on）"
            )
    for case in cases:
        where = f"[{case.source}::{case.id}]"
        if not case.request.url:
            problems.append(f"{where} request.url 不能为空")
        if case.request.method not in HTTP_METHODS:
            problems.append(f"{where} 非法 HTTP method: {case.request.method!r}")
        if case.retry < 0:
            problems.append(f"{where} retry 不能为负数")
        for dep in case.depends_on:
            if dep not in known_ids:
                problems.append(f"{where} 依赖的用例 {dep!r} 不存在或已禁用")
        for name, expr in case.extract.items():
            try:
                describe(expr)
            except Exception as exc:
                problems.append(f"{where} extract.{name} 的 JSONPath 非法: {expr!r} ({exc})")
        if not case.validate:
            problems.append(f"{where} 没有任何断言（该用例只会检查请求能否发出）")
        for item in case.validate:
            if item.op not in VALID_OPS:
                problems.append(f"{where} 未知断言算子 {item.op!r}，可用: {', '.join(sorted(VALID_OPS))}")
            elif item.op == "schema" and not item.schema:
                problems.append(f"{where} schema 断言缺少 schema_file / schema")
            elif item.op != "schema" and not item.check:
                problems.append(f"{where} {item.op} 断言缺少 check 取值路径")
            elif item.check:
                try:
                    describe(item.check)
                except Exception as exc:
                    problems.append(f"{where} check 的 JSONPath 非法: {item.check!r} ({exc})")
        for hook in case.hooks:
            if hook not in known_hooks:
                problems.append(f"{where} 未注册的 hook {hook!r}，可用: {', '.join(sorted(known_hooks))}")
    return problems


def load_suite(
    path: str | Path,
    base_url: str | None = None,
    extra_vars: dict[str, Any] | None = None,
) -> Suite:
    """Load a single YAML file or a directory of case files into one Suite."""
    target = Path(path)
    files = iter_case_files(target)
    if not files:
        raise CaseLoadError(f"在 {target} 下没有找到 .yaml / .yml 用例文件")

    root = target if target.is_dir() else target.parent
    name = target.name if target.is_dir() else target.stem
    cases: list[Case] = []
    variables: dict[str, Any] = {}
    headers: dict[str, str] = {}
    file_base_url = ""

    for case_file in files:
        try:
            data = yaml.safe_load(case_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CaseLoadError(f"{case_file.name} YAML 解析失败: {exc}") from exc
        if not isinstance(data, dict):
            raise CaseLoadError(f"{case_file.name} 顶层必须是映射")
        name = data.get("name") or name
        file_base_url = file_base_url or str(data.get("base_url") or "")
        variables.update(data.get("variables") or {})
        headers.update(data.get("headers") or {})
        for raw in data.get("cases") or []:
            cases.append(_parse_case(raw, case_file, root))

    suite = Suite(
        name=str(name),
        base_url=base_url or file_base_url,
        cases=cases,
        variables={**variables, **(extra_vars or {})},
        headers=headers,
        path=target,
    )
    problems = check_suite(suite)
    if problems:
        raise CaseLoadError("用例集静态校验未通过:\n  - " + "\n  - ".join(problems))
    return suite


def load_suite_lenient(path: str | Path, **kwargs) -> tuple[Suite | None, list[str]]:
    """For `flowtest validate`: report all problems without raising."""
    try:
        return load_suite(path, **kwargs), []
    except CaseLoadError as exc:
        return None, [line.strip("- ").strip() for line in str(exc).splitlines()[1:]] or [str(exc)]
