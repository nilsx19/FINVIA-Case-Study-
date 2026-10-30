"""Web frontend server: serves the static UI in ``web/`` and a small JSON API.

Run with ``python app.py`` and open http://127.0.0.1:8000. Only the Python standard
library is used, so no extra packages are needed. All calculations live in
``pe_waterfall``; this file only handles HTTP.
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pe_waterfall import api
from pe_waterfall.models import InputError

WEB_DIR = Path(__file__).parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
POST_ROUTES = {"/api/calculate": api.calculate, "/api/irr": api.cashflow_irr}
MAX_BODY_BYTES = 1_000_000


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        path = self.path.split("?", 1)[0]
        if path == "/api/defaults":
            self._send_json(HTTPStatus.OK, api.defaults())
        elif path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]  # whitelist: no path traversal possible
            self._send(HTTPStatus.OK, (WEB_DIR / filename).read_bytes(), content_type)
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        handler = POST_ROUTES.get(self.path.split("?", 1)[0])
        if handler is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY_BYTES:
                raise InputError("Request is too large.")
            payload = json.loads(self.rfile.read(length) or b"null")
            self._send_json(HTTPStatus.OK, handler(payload))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body is not valid JSON."})
        except InputError as err:  # user-facing validation message
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(err)})
        except (ArithmeticError, ValueError) as err:  # e.g. numbers too large for Decimal
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"These inputs cannot be calculated ({err})."})

    def log_message(self, format, *args) -> None:  # noqa: A002 - keep the console quiet
        pass


def make_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribution waterfall & fee calculator (web UI)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    server = make_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}"
    print(f"Waterfall calculator running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
