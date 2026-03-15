"""Tests for core.py cloud mode — request construction, auth, and error handling."""

import json
import socket
import ssl
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

import pytest
import core


# ── Helpers ──

def _cloud_cfg(token="tok123"):
    return {"mode": "cloud", "server": "http://test:8000", "token": token}


def _mock_resp(data=None, *, raw=None, read_side_effect=None):
    resp = MagicMock()
    if read_side_effect:
        resp.read.side_effect = read_side_effect
    elif raw is not None:
        resp.read.return_value = raw
    else:
        resp.read.return_value = json.dumps(data).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _req(mock):
    return mock.call_args[0][0]


def _body(mock):
    return json.loads(_req(mock).data.decode())


# ── Request construction (parametrized) ──

_REQUESTS = [
    ("add", {"args": ("s1",), "kwargs": {"desc": "d", "tool": "codex"},
                  "url": "/agents", "method": "POST",
                  "body": {"name": "s1", "desc": "d", "tool": "codex"}}),
    ("send", {"args": ("t1", "hello", "s1"), "kwargs": {"msg_type": "task", "priority": "urgent"},
              "url": "/send", "method": "POST",
              "body_contains": {"target": "t1", "message": "hello", "from": "s1", "type": "task"}}),
]


@pytest.mark.parametrize("func_name, spec", _REQUESTS, ids=[r[0] for r in _REQUESTS])
@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_request_construction(mock_urlopen, mock_cfg, func_name, spec):
    mock_urlopen.return_value = _mock_resp({})
    getattr(core, func_name)(*spec["args"], **spec["kwargs"])

    req = _req(mock_urlopen)
    assert req.full_url == f"http://test:8000/api/v1{spec['url']}"
    assert req.method == spec["method"]
    if "body" in spec and spec["body"]:
        assert _body(mock_urlopen) == spec["body"]
    if "body_contains" in spec:
        body = _body(mock_urlopen)
        for k, v in spec["body_contains"].items():
            assert body[k] == v


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_send_reply_to_in_body(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp({})
    core.send("t1", "reply", "s1", reply_to="orig-id")
    assert _body(mock_urlopen)["reply_to"] == "orig-id"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_send_no_reply_to_when_none(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp({})
    core.send("t1", "msg", "s1")
    assert "reply_to" not in _body(mock_urlopen)


@pytest.mark.parametrize("func, args, url_part", [
    ("recv", ("session1",), "/recv/session1"),
    ("ls", (), "/agents"),
])
@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_get_requests(mock_urlopen, mock_cfg, func, args, url_part):
    mock_urlopen.return_value = _mock_resp([] if func in ("recv", "ls") else {})
    getattr(core, func)(*args)
    req = _req(mock_urlopen)
    assert req.method == "GET"
    assert url_part in req.full_url


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_recv_query_params(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp([])
    core.recv("s1", peek=True, msg_type="task")
    url = _req(mock_urlopen).full_url
    assert "peek=true" in url
    assert "type=task" in url


# ── Auth ──

@patch.object(core, "load_config", return_value=_cloud_cfg(token="my-secret"))
@patch("core.urlopen")
def test_auth_header_present(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp({})
    core.ls()
    assert _req(mock_urlopen).get_header("Authorization") == "Bearer my-secret"


@patch.object(core, "load_config", return_value=_cloud_cfg(token=""))
@patch("core.urlopen")
def test_no_auth_header_when_no_token(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp({})
    core.ls()
    assert "Authorization" not in _req(mock_urlopen).headers


# ── Cloud-specific ──

@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_history_cloud_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp([])
    core.history(limit=30)
    req = _req(mock_urlopen)
    assert req.method == "GET"
    assert "/history" in req.full_url
    assert "limit=30" in req.full_url


# ── Error handling ──

@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_http_error_extracts_json_detail(mock_urlopen, mock_cfg):
    err_resp = MagicMock()
    err_resp.read.return_value = json.dumps({"detail": "session not found"}).encode()
    err_resp.headers = {"content-type": "application/json"}
    mock_urlopen.side_effect = HTTPError("url", 404, "Not Found", err_resp.headers, err_resp)
    with pytest.raises(RuntimeError, match="session not found"):
        core.send("target", "msg", "sender")


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_http_error_falls_back_to_reason(mock_urlopen, mock_cfg):
    err_resp = MagicMock()
    err_resp.read.return_value = b"plain text"
    err_resp.headers = {"content-type": "text/plain"}
    mock_urlopen.side_effect = HTTPError("url", 500, "Internal Server Error", err_resp.headers, err_resp)
    with pytest.raises(RuntimeError, match="Internal Server Error"):
        core.send("target", "msg", "sender")


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_http_error_corrupt_json_body(mock_urlopen, mock_cfg):
    err_resp = MagicMock()
    err_resp.read.return_value = b"{corrupt"
    err_resp.headers = {"content-type": "application/json"}
    mock_urlopen.side_effect = HTTPError("url", 500, "Internal Server Error", err_resp.headers, err_resp)
    with pytest.raises(RuntimeError, match="Internal Server Error"):
        core.ls()


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_url_error(mock_urlopen, mock_cfg):
    mock_urlopen.side_effect = URLError("Connection refused")
    with pytest.raises(RuntimeError, match="Cannot reach server"):
        core.ls()


@patch.object(core, "load_config", return_value={"mode": "cloud", "server": "", "token": ""})
def test_no_server_configured(mock_cfg):
    with pytest.raises(RuntimeError, match="not configured"):
        core.ls()


# ── Network failures ──

@pytest.mark.parametrize("exc", [
    socket.timeout("timed out"),
    ConnectionResetError("Connection reset by peer"),
])
@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_network_exceptions_wrapped(mock_urlopen, mock_cfg, exc):
    mock_urlopen.side_effect = exc
    with pytest.raises(RuntimeError, match="Network error"):
        core.ls()


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_read_timeout_during_response(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _mock_resp(read_side_effect=socket.timeout("Read timed out"))
    with pytest.raises(RuntimeError, match="Network error"):
        core.ls()


@pytest.mark.parametrize("exc", [
    URLError(socket.gaierror(8, "Name or service not known")),
    URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED]")),
])
@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_url_error_variants(mock_urlopen, mock_cfg, exc):
    mock_urlopen.side_effect = exc
    with pytest.raises(RuntimeError, match="Cannot reach server"):
        core.ls()


@pytest.mark.parametrize("body", [b"", b"<html>502 Bad Gateway</html>"])
@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_invalid_response_body(mock_urlopen, mock_cfg, body):
    mock_urlopen.return_value = _mock_resp(raw=body)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        core.ls()


# ── Validation before cloud ──

@pytest.mark.parametrize("field, value", [("msg_type", "invalid"), ("priority", "invalid")])
def test_validation_before_cloud(field, value):
    with pytest.raises(ValueError):
        core.send("t", "m", "s", **{field: value})


# ── Config edge cases ──

def test_load_config_missing_file(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(core, "CONFIG_FILE", Path(td) / "no_such_file.json")
        cfg = core.load_config()
        assert cfg == {"mode": "local", "server": "", "token": ""}


def test_load_config_corrupt_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "config.json"
        p.write_text("{invalid!!!")
        monkeypatch.setattr(core, "CONFIG_FILE", p)
        assert core.load_config()["mode"] == "local"


def test_load_config_strips_trailing_slash(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "config.json"
        p.write_text(json.dumps({"mode": "cloud", "server": "http://example.com/", "token": "t"}))
        monkeypatch.setattr(core, "CONFIG_FILE", p)
        assert core.load_config()["server"] == "http://example.com"
