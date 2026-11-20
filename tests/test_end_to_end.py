"""Integration tests: run the whole example suite against the built-in SUT.

This is the part that makes CI meaningful — the framework is validated by
actually testing a real HTTP service, not only by mocking itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtest.core.client import HttpClient
from flowtest.core.errors import RequestError
from flowtest.core.loader import load_suite
from flowtest.core.resolver import build_layers
from flowtest.core.runner import Runner, RunnerConfig
from flowtest.report.html import write_report

EXAMPLES = Path(__file__).resolve().parents[1] / "flowtest" / "examples" / "testcases"


def test_full_example_suite_is_green(demo_url, tmp_path):
    suite = load_suite(EXAMPLES, base_url=demo_url)
    client = HttpClient(base_url=demo_url, default_headers=suite.headers)
    result = Runner(suite, client, RunnerConfig(parallel=3)).run()
    client.close()

    assert result.total == 17
    assert result.ok, [r.case.id for r in result.results if not r.status.value == "passed"]
    assert result.skipped == 0

    report = write_report(result, tmp_path / "report.html")
    html = report.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "100.0" in html  # pass rate
    assert "***REDACTED***" in html  # request headers are redacted
    assert "重试轨迹" in html  # flaky case retry trace is rendered
    assert "FlowTest" in html


def test_bundled_examples_form_a_five_layer_dag(demo_url):
    suite = load_suite(EXAMPLES, base_url=demo_url)
    assert len(suite.active_cases) == 17
    assert len(build_layers(suite.active_cases)) == 5


def test_relative_url_without_base_url_fails_fast():
    client = HttpClient(base_url="")
    with pytest.raises(RequestError, match="base_url"):
        client.build_url("/health")
