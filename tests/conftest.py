"""Shared fixtures for the framework's own test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtest.mock.demo_server import start_demo_server, stop_demo_server

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "flowtest" / "examples" / "testcases"
TESTCASES = ROOT / "testcases"


@pytest.fixture(scope="session")
def demo_url():
    """One in-process SUT shared by all integration tests."""
    server, url = start_demo_server(0)
    yield url
    stop_demo_server(server)
