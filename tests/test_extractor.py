"""Unit tests for response value lookup."""

from __future__ import annotations

import pytest

from flowtest.core.context import MISSING
from flowtest.core.errors import ExtractError
from flowtest.core.extractor import describe, lookup
from flowtest.core.models import Response


def response(body, status=200, headers=None):
    return Response(
        status_code=status,
        headers=headers or {"Content-Type": "application/json"},
        body=body,
        text=str(body),
        elapsed_ms=12.345,
    )


def test_jsonpath_against_body_root():
    resp = response({"data": {"token": "abc", "items": [{"id": 1}, {"id": 2}]}})
    assert lookup(resp, "$.data.token") == "abc"
    assert lookup(resp, "$.data.items[0].id") == 1
    assert lookup(resp, "$.data.items[*].id") == [1, 2]


def test_virtual_roots():
    resp = response({"code": 0}, status=201, headers={"X-Trace-Id": "t-1"})
    assert lookup(resp, "status_code") == 201
    assert lookup(resp, "headers.X-Trace-Id") == "t-1"
    assert lookup(resp, "elapsed_ms") == 12.35
    assert lookup(resp, "body") == {"code": 0}


def test_missing_path_returns_sentinel_not_none():
    resp = response({"data": None})
    assert lookup(resp, "$.data") is None
    assert lookup(resp, "$.data.absent") is MISSING


def test_header_lookup_is_case_insensitive():
    resp = response({}, headers={"content-type": "text/plain"})
    assert lookup(resp, "headers.Content-Type") == "text/plain"


def test_invalid_jsonpath_raises_extract_error():
    with pytest.raises(ExtractError):
        lookup(response({}), "$.[")
    with pytest.raises(ExtractError):
        describe("$.[")


def test_describe_skips_virtual_roots():
    assert describe("headers.Content-Type") == "headers.Content-Type"
    assert describe("status_code") == "status_code"
