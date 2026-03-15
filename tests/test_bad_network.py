"""Bad network tests — real HTTP servers that deliberately misbehave."""

import json
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

import pytest
import core


# ── Infrastructure ──

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _handler(do_get):
    """Create a silent handler class from a do_GET function."""
    return type("H", (BaseHTTPRequestHandler,), {
        "do_GET": do_get,
        "do_POST": do_get,
        "log_message": lambda *a: None,
    })


@pytest.fixture
def bad_server(request):
    """Start a real HTTP server with the given handler, patch core to use it."""
    handler = request.param
    port = _free_port()
    srv = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = {"mode": "cloud", "server": f"http://127.0.0.1:{port}", "token": ""}
    with patch.object(core, "load_config", return_value=cfg):
        yield port
    srv.shutdown()


# ── Handlers (one-liners via _handler factory) ──

def _ok_json(self):
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    length = int(self.headers.get("Content-Length", 0))
    body = json.loads(self.rfile.read(length)) if length else {}
    if self.command == "POST":
        resp = {"status": "ok", "id": body.get("id", ""), "alias": body.get("alias", "")}
    else:
        resp = []
    self.wfile.write(json.dumps(resp).encode())

def _empty_body(self):
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", "0")
    self.end_headers()

def _garbage_body(self):
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(b"<html>502 Bad Gateway</html>")

def _drop_connection(self):
    self.connection.close()

def _500_html(self):
    self.send_response(500)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(b"<html>Internal Server Error</html>")

def _slow_partial(self):
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(b'{"ver')
    self.wfile.flush()
    time.sleep(30)

def _huge_json(self):
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(json.dumps({"data": "x" * (1024 * 1024)}).encode())

OkJson        = _handler(_ok_json)
EmptyBody     = _handler(_empty_body)
GarbageBody   = _handler(_garbage_body)
DropConn      = _handler(_drop_connection)
Html500       = _handler(_500_html)
SlowPartial   = _handler(_slow_partial)
HugeJson      = _handler(_huge_json)


# ── Happy path ──

@pytest.mark.parametrize("bad_server", [OkJson], indirect=True)
def test_happy_path(bad_server):
    assert core.ls() == []


@pytest.mark.parametrize("bad_server", [OkJson], indirect=True)
def test_post_roundtrip(bad_server):
    assert core.add("s1", desc="test")["status"] == "ok"


# ── Should raise RuntimeError ──

@pytest.mark.parametrize("bad_server, match", [
    (EmptyBody,    "invalid JSON"),
    (GarbageBody,  "invalid JSON"),
    (DropConn,     None),
    (Html500,      "Internal Server Error"),
], indirect=["bad_server"])
def test_bad_response_raises(bad_server, match):
    with pytest.raises(RuntimeError, match=match):
        core.ls()


def test_connection_refused():
    port = _free_port()
    cfg = {"mode": "cloud", "server": f"http://127.0.0.1:{port}", "token": ""}
    with patch.object(core, "load_config", return_value=cfg):
        with pytest.raises(RuntimeError, match="Cannot reach server"):
            core.ls()


# ── Slow / large ──

@pytest.mark.parametrize("bad_server", [SlowPartial], indirect=True)
def test_slow_response_times_out(bad_server, monkeypatch):
    """Partial response + stall — should not hang forever."""
    from urllib.request import urlopen as real_urlopen

    def short_timeout_urlopen(req, **kw):
        return real_urlopen(req, timeout=1)

    monkeypatch.setattr(core, "urlopen", short_timeout_urlopen)
    with pytest.raises(RuntimeError):
        core.ls()


@pytest.mark.parametrize("bad_server", [HugeJson], indirect=True)
def test_huge_response_works(bad_server):
    result = core.ls()
    assert isinstance(result, dict)  # huge JSON parsed successfully
