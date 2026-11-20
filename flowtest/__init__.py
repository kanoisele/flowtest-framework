"""FlowTest - a lightweight, DAG-driven API automation testing framework.

FlowTest turns YAML case definitions into an executable dependency graph,
runs them with configurable parallelism, and emits a self-contained HTML report.
"""

__version__ = "0.1.0"

from flowtest.core.models import Case, CaseResult, RunResult, Status, Suite
from flowtest.core.runner import Runner, RunnerConfig

__all__ = [
    "__version__",
    "Case",
    "Suite",
    "Status",
    "CaseResult",
    "RunResult",
    "Runner",
    "RunnerConfig",
]
