"""A tiny in-process book/order API used as the System Under Test.

Pure standard library on purpose: cloning the repo and running `flowtest demo`
needs no Docker, no database and no external service. It is started in a daemon
thread by the CLI and shut down after the run.

Besides happy paths it exposes deliberately awkward behaviour (401, 404, 400,
a flaky 503 endpoint) so the example suite can demonstrate negative cases,
contract validation and retry logic without external dependencies.
"""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BOOKS = [
    {"id": 101, "title": "软件测试的艺术", "author": "Glenford J. Myers", "price": 59.0, "stock": 12},
    {"id": 102, "title": "Python 测试驱动开发", "author": "Harry J.W. Percival", "price": 89.0, "stock": 5},
    {"id": 103, "title": "持续交付", "author": "Jez Humble", "price": 78.5, "stock": 0},
]


class DemoState:
    def __init__(self) -> None:
        self.tokens: set[str] = set()
        self.orders: dict[str, dict] = {}
        self.flaky_hits = 0
        self.lock = threading.Lock()


STATE = DemoState()


def _ok(data, msg: str = "ok") -> dict:
    return {"code": 0, "msg": msg, "data": data}


def _err(code: int, msg: str) -> dict:
    return {"code": code, "msg": msg, "data": None}


class DemoHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # keep CI output clean
        pass

    # ------------------------------------------------------------------ helpers

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _authed(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and auth[7:] in STATE.tokens

    def _parts(self) -> tuple[str, dict]:
        parsed = urlparse(self.path)
        return parsed.path.rstrip("/") or "/", {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # -------------------------------------------------------------------- routes

    def do_GET(self) -> None:
        path, query = self._parts()

        if path == "/health":
            self._send(200, _ok({"status": "UP", "version": "1.0.0"}))
            return

        if path == "/api/flaky":
            # Every 3rd request succeeds: a deterministic way to demo retries.
            with STATE.lock:
                STATE.flaky_hits += 1
                hit = STATE.flaky_hits
            if hit % 3 != 0:
                self._send(503, _err(50301, "service temporarily unavailable"))
            else:
                self._send(200, _ok({"attempt": hit, "status": "RECOVERED"}))
            return

        if path == "/api/books":
            keyword = str(query.get("keyword", "")).lower()
            page = max(1, int(query.get("page", 1)))
            size = max(1, min(50, int(query.get("size", 10))))
            items = [b for b in BOOKS if keyword in b["title"].lower() or keyword in b["author"].lower()]
            self._send(200, _ok({"total": len(items), "page": page, "size": size, "items": items}))
            return

        if path.startswith("/api/books/"):
            book_id = path.rsplit("/", 1)[-1]
            found = next((b for b in BOOKS if str(b["id"]) == book_id), None)
            if found:
                self._send(200, _ok(found))
            else:
                self._send(404, _err(40401, "book not found"))
            return

        if path == "/api/users/me":
            if not self._authed():
                self._send(401, _err(40100, "unauthorized"))
            else:
                self._send(200, _ok({"id": 1, "username": "admin", "role": "admin"}))
            return

        if path.startswith("/api/orders/"):
            order_id = path.rsplit("/", 1)[-1]
            order = STATE.orders.get(order_id)
            if order:
                self._send(200, _ok(order))
            else:
                self._send(404, _err(40402, "order not found"))
            return

        self._send(404, _err(40400, "route not found"))

    def do_POST(self) -> None:
        path, _ = self._parts()
        body = self._body()

        if path == "/api/login":
            if body.get("username") == "admin" and body.get("password") == "123456":
                token = uuid.uuid4().hex
                with STATE.lock:
                    STATE.tokens.add(token)
                self._send(200, _ok({
                    "token": token,
                    "expires_in": 3600,
                    "user": {"id": 1, "username": "admin"},
                }, "login success"))
            else:
                self._send(401, _err(40101, "invalid credentials"))
            return

        if path == "/api/orders":
            if not self._authed():
                self._send(401, _err(40100, "unauthorized"))
                return
            book_id = body.get("book_id")
            quantity = body.get("quantity", 1)
            book = next((b for b in BOOKS if str(b["id"]) == str(book_id)), None)
            if not book:
                self._send(400, _err(40001, "invalid book_id"))
                return
            if not isinstance(quantity, int) or quantity < 1 or quantity > book["stock"]:
                self._send(400, _err(40002, "invalid quantity or out of stock"))
                return
            order_id = "ORD-" + uuid.uuid4().hex[:10].upper()
            order = {
                "order_id": order_id,
                "book_id": book["id"],
                "title": book["title"],
                "quantity": quantity,
                "amount": round(book["price"] * quantity, 2),
                "status": "CREATED",
            }
            with STATE.lock:
                STATE.orders[order_id] = order
            self._send(201, _ok(order, "order created"))
            return

        self._send(404, _err(40400, "route not found"))

    def do_DELETE(self) -> None:
        path, _ = self._parts()
        if path.startswith("/api/orders/"):
            if not self._authed():
                self._send(401, _err(40100, "unauthorized"))
                return
            order_id = path.rsplit("/", 1)[-1]
            order = STATE.orders.get(order_id)
            if not order:
                self._send(404, _err(40402, "order not found"))
                return
            with STATE.lock:
                order["status"] = "CANCELLED"
            self._send(200, _ok({"order_id": order_id, "status": "CANCELLED"}, "order cancelled"))
            return
        self._send(404, _err(40400, "route not found"))


def start_demo_server(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, name="flowtest-demo", daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def stop_demo_server(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()
