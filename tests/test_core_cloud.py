"""Tests for core.py cloud mode — all _api calls mocked.

These tests verify:
1. Correct HTTP method, URL, headers, and request body construction
2. Proper parameter mapping (peek, type filter, alive filter, etc.)
3. Error handling (HTTPError, URLError, missing server config)
4. Auth header presence/absence based on token

They do NOT re-assert mocked response values — that would be testing
the mock, not the code.
"""

import json
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

import core


def _make_response(data):
    """Create a mock urlopen response."""
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _cloud_cfg(token="tok123"):
    return {"mode": "cloud", "server": "http://test:8000", "token": token}


def _req(mock_urlopen):
    """Extract the Request object from the mock."""
    return mock_urlopen.call_args[0][0]


def _body(mock_urlopen):
    """Extract parsed JSON body from the mock."""
    return json.loads(_req(mock_urlopen).data.decode())


# ── Request construction ──

@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_register_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.register("s1", alias="a", desc="test", tool="codex")

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/register"
    assert req.method == "POST"
    body = _body(mock_urlopen)
    assert body == {"id": "s1", "alias": "a", "desc": "test", "tool": "codex"}


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_send_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.send("target1", "hello", "sender1", msg_type="task", priority="urgent")

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/send"
    assert req.method == "POST"
    body = _body(mock_urlopen)
    assert body["target"] == "target1"
    assert body["message"] == "hello"
    assert body["from"] == "sender1"
    assert body["type"] == "task"
    assert body["priority"] == "urgent"
    assert "reply_to" not in body  # not sent when None


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_send_request_with_reply_to(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.send("t1", "reply", "s1", reply_to="orig-id")
    assert _body(mock_urlopen)["reply_to"] == "orig-id"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_recv_request_defaults(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response([])
    core.recv("session1")

    req = _req(mock_urlopen)
    assert req.method == "GET"
    assert "/recv/session1" in req.full_url
    assert "peek=false" in req.full_url
    assert "type=" not in req.full_url  # no type filter by default


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_recv_request_peek_with_type(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response([])
    core.recv("s1", peek=True, msg_type="task")

    req = _req(mock_urlopen)
    assert "peek=true" in req.full_url
    assert "type=task" in req.full_url


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_broadcast_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.broadcast("hi all", "sender1", msg_type="task", priority="urgent")

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/broadcast"
    assert req.method == "POST"
    body = _body(mock_urlopen)
    assert body["message"] == "hi all"
    assert body["from"] == "sender1"
    assert body["type"] == "task"
    assert body["priority"] == "urgent"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_ls_request_default(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response([])
    core.ls()

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/sessions"
    assert req.method == "GET"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_ls_request_alive(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response([])
    core.ls(alive_only=True)
    assert "alive=true" in _req(mock_urlopen).full_url


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_resolve_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.resolve("finder")

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/resolve/finder"
    assert req.method == "GET"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_status_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.get_status()

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/status"
    assert req.method == "GET"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_heartbeat_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.heartbeat("s1")

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/heartbeat/s1"
    assert req.method == "POST"


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_clean_request(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.clean(timeout_min=30)

    req = _req(mock_urlopen)
    assert req.full_url == "http://test:8000/api/v1/clean?timeout=30"
    assert req.method == "DELETE"


# ── Cloud-specific behavior ──

@patch.object(core, "load_config", return_value=_cloud_cfg())
def test_history_cloud_returns_empty(mock_cfg):
    """history() returns [] in cloud mode without making any HTTP call."""
    result = core.history()
    assert result == []


# ── Auth header ──

@patch.object(core, "load_config", return_value=_cloud_cfg(token="my-secret"))
@patch("core.urlopen")
def test_auth_header_present_when_token_set(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.get_status()
    assert _req(mock_urlopen).get_header("Authorization") == "Bearer my-secret"


@patch.object(core, "load_config", return_value=_cloud_cfg(token=""))
@patch("core.urlopen")
def test_no_auth_header_when_no_token(mock_urlopen, mock_cfg):
    mock_urlopen.return_value = _make_response({})
    core.get_status()
    assert "Authorization" not in _req(mock_urlopen).headers


# ── Error handling ──

@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_http_error_extracts_json_detail(mock_urlopen, mock_cfg):
    err_body = json.dumps({"detail": "session not found"}).encode()
    err_resp = MagicMock()
    err_resp.read.return_value = err_body
    err_resp.headers = {"content-type": "application/json"}
    mock_urlopen.side_effect = HTTPError(
        "http://test:8000/api/v1/send", 404, "Not Found", err_resp.headers, err_resp
    )
    try:
        core.send("target", "msg", "sender")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "session not found" in str(e)


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_http_error_falls_back_to_reason(mock_urlopen, mock_cfg):
    """When error response is not JSON, fall back to HTTP reason."""
    err_resp = MagicMock()
    err_resp.read.return_value = b"plain text error"
    err_resp.headers = {"content-type": "text/plain"}
    mock_urlopen.side_effect = HTTPError(
        "http://test:8000/api/v1/send", 500, "Internal Server Error",
        err_resp.headers, err_resp,
    )
    try:
        core.send("target", "msg", "sender")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "Internal Server Error" in str(e)


@patch.object(core, "load_config", return_value=_cloud_cfg())
@patch("core.urlopen")
def test_url_error(mock_urlopen, mock_cfg):
    mock_urlopen.side_effect = URLError("Connection refused")
    try:
        core.get_status()
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "Cannot reach server" in str(e)


@patch.object(core, "load_config", return_value={"mode": "cloud", "server": "", "token": ""})
def test_no_server_configured(mock_cfg):
    try:
        core.get_status()
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "not configured" in str(e)


# ── Validation before cloud call ──

def test_send_validates_type_before_cloud():
    """Type validation happens before cloud check — no HTTP call made."""
    try:
        core.send("t", "m", "s", msg_type="invalid")
        assert False
    except ValueError:
        pass


def test_send_validates_priority_before_cloud():
    try:
        core.send("t", "m", "s", priority="invalid")
        assert False
    except ValueError:
        pass
