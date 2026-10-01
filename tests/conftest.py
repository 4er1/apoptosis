import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest_plugins = ["pytester"]


class FakeGitHub:
    """API de GitHub Issues en miniatura: guarda cada petición para poder asertar sobre ella."""

    def __init__(self):
        self.requests, self.next_number, self.fail_with = [], 1, None

    def calls(self, method, suffix=""):
        return [r for r in self.requests if r["method"] == method and r["path"].endswith(suffix)]


@pytest.fixture
def fake_github(monkeypatch):
    fake = FakeGitHub()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = json.loads(raw) if raw else None
            fake.requests.append({"method": self.command, "path": self.path, "body": body,
                                  "auth": self.headers.get("Authorization")})
            if fake.fail_with:
                self.send_response(fake.fail_with)
                self.end_headers()
                self.wfile.write(b'{"message":"boom"}')
                return
            if self.command == "POST" and self.path.endswith("/issues"):
                n, fake.next_number = fake.next_number, fake.next_number + 1
                out, code = {"number": n, "html_url": f"https://github.com/me/repo/issues/{n}"}, 201
            else:
                out, code = {}, 201 if self.command == "POST" else 200
            data = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_PATCH = _handle

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("APOPTOSIS_GITHUB_API", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setenv("GITHUB_TOKEN", "tok_test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    yield fake
    srv.shutdown()
