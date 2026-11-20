"""Thin HTTP layer over requests.

Notable detail: ``requests.Session`` is *not* documented as thread-safe, and
the runner executes same-layer cases concurrently. Each worker thread therefore
gets its own Session via ``threading.local()`` — no shared mutable connection
pool state, no flaky cross-case cookie leakage.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import urljoin

import requests

from flowtest.core.errors import RequestError
from flowtest.core.models import RequestSpec, Response
from flowtest.utils.logger import log

RETRYABLE_STATUS = {500, 502, 503, 504}


class HttpClient:
    def __init__(
        self,
        base_url: str = "",
        default_headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_headers = dict(default_headers or {})
        self.timeout = timeout
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(self.default_headers)
            self._local.session = session
        return session

    def build_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        if not self.base_url:
            raise RequestError(f"用例使用了相对路径 {url!r}，但没有配置 base_url")
        return urljoin(self.base_url + "/", url.lstrip("/"))

    def request(self, spec: RequestSpec) -> Response:
        url = self.build_url(spec.url)
        method = spec.method.upper()
        kwargs: dict[str, Any] = {
            "params": spec.params or None,
            "headers": spec.headers or None,
            "timeout": spec.timeout or self.timeout,
        }
        if spec.body is not None:
            kwargs["json"] = spec.body

        started = time.perf_counter()
        try:
            raw = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise RequestError(f"{method} {url} 请求失败: {type(exc).__name__}: {exc}") from exc
        elapsed_ms = (time.perf_counter() - started) * 1000

        try:
            body = raw.json()
        except ValueError:
            body = None
        log.debug("%s %s -> %s (%.1f ms)", method, url, raw.status_code, elapsed_ms)
        return Response(
            status_code=raw.status_code,
            headers=dict(raw.headers),
            body=body,
            text=raw.text,
            elapsed_ms=elapsed_ms,
            url=url,
            method=method,
        )

    def close(self) -> None:
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None
