import json
import os
import socketserver
import threading
from http.server import BaseHTTPRequestHandler

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Cada prueba usa sus propias carpetas XDG (nunca las del usuario)."""
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                     ("XDG_RUNTIME_DIR", "run")):
        path = tmp_path / sub
        path.mkdir()
        monkeypatch.setenv(var, str(path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NIMBO_LANG", "es")
    yield tmp_path


class FakeRclone:
    """Servidor rc falso sobre socket Unix que responde como rclone."""

    def __init__(self, path):
        self.path = path
        self.calls = []
        self.responses = {}

    def reply(self, method, body, status=200):
        self.responses[method] = (status, body)


@pytest.fixture
def fake_rc(tmp_path):
    sock = tmp_path / "rc.sock"
    fake = FakeRclone(sock)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            params = json.loads(self.rfile.read(length) or b"{}")
            method = self.path.lstrip("/")
            fake.calls.append((method, params))
            status, body = fake.responses.get(method, (200, {}))
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

        def get_request(self):
            request, _ = super().get_request()
            return request, ("local", 0)

    server = Server(str(sock), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield fake
    server.shutdown()
    server.server_close()
    if os.path.exists(sock):
        os.unlink(sock)
