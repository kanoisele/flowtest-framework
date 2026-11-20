# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-11-20

### Added

- YAML DSL for data-driven API cases with load-time static validation.
- DAG-based case orchestration: Kahn topological sort, cycle detection,
  layered parallel execution, skip propagation on failed dependencies.
- Namespaced variable context (`${case_id.var}`), typed whole-token rendering
  and `${{func()}}` built-ins for dynamic test data.
- Assertion engine with 20 operators, soft assertions and JSON Schema contract
  validation; missing-path is distinguishable from JSON `null`.
- Transport-level retry for network errors / 5xx only (assertion failures are
  never retried), with per-thread isolated `requests.Session`.
- Built-in zero-dependency demo SUT so the full suite runs offline.
- Single-file offline HTML report with redacted credentials and retry traces.
- CLI: `run` / `demo` / `validate` / `ops` / `init`.
- Framework self-tests (unit + integration), GitHub Actions matrix CI.
