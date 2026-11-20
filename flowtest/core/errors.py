"""Typed exceptions.

Every failure mode has its own exception so the runner can decide whether a
failure is retryable (transport) or terminal (bad case definition / assertion).
"""


class FlowTestError(Exception):
    """Base class for all FlowTest errors."""


class CaseLoadError(FlowTestError):
    """The YAML DSL is invalid (missing field, unknown operator, bad schema...)."""


class DependencyError(FlowTestError):
    """Missing dependency, duplicate id, or a cycle in the case graph."""


class VariableNotFoundError(FlowTestError):
    """A ${...} token references a variable that was never produced."""


class RequestError(FlowTestError):
    """Transport-level failure (connection refused, timeout, DNS...)."""


class ExtractError(FlowTestError):
    """A JSONPath expression could not be evaluated."""
