"""Tests for cloud server (FastAPI + SQLite)."""

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

_tmp_dir = tempfile.mkdtemp()
import server.app as app_module
app_module.DATA_DIR = Path(_tmp_dir)
app_module.DB_PATH = str(Path(_tmp_dir) / "test.db")

from fastapi.testclient import TestClient
from server.app import app

client = TestClient(app)
_auth = {}


@pytest.fixture(autouse=True)
def fresh_db():
    global _auth
    db_path = Path(app_module.DB_PATH)
    if db_path.exists():
        os.remove(db_path)
    app_module.db = app_module.open_db()
    app_module.limiter.reset()
    _auth = {"Authorization": f"Bearer test-token-{uuid.uuid4().hex}"}
    yield
    _auth = {}
    app_module.close_db()


def _account():
    return {"Authorization": f"Bearer test-account-{uuid.uuid4().hex}"}


def _add(name, headers=None, **kw):
    client.post("/api/v1/agents", json={"name": name, **kw}, headers=headers or _auth)


def _send(target, msg="msg", sender="s", headers=None, **kw):
    return client.post("/api/v1/send", json={"target": target, "message": msg, "from": sender, **kw}, headers=headers or _auth)


def _recv(name, headers=None, **params):
    h = headers or _auth
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/v1/recv/{name}{'?' + qs if qs else ''}", headers=h).json()


def _get(path, headers=None):
    return client.get(path, headers=headers or _auth)


# ── Auth ──

def test_endpoints_require_auth():
    assert client.post("/api/v1/agents", json={"name": "x"}).status_code == 401
    assert client.post("/api/v1/send", json={"target": "x", "message": "m", "from": "s"}).status_code == 401
    assert client.get("/api/v1/recv/x").status_code == 401
    assert client.get("/api/v1/agents").status_code == 401


def test_short_token_rejected():
    bad = {"Authorization": "Bearer short"}
    assert client.post("/api/v1/agents", json={"name": "x"}, headers=bad).status_code == 401


# ── Data isolation ──

def test_users_cannot_see_each_others_agents():
    h1 = _account()
    h2 = _account()

    _add("alice", headers=h1)
    _add("bob", headers=h2)

    agents1 = _get("/api/v1/agents", headers=h1).json()
    agents2 = _get("/api/v1/agents", headers=h2).json()

    assert len(agents1) == 1
    assert agents1[0]["name"] == "alice"
    assert len(agents2) == 1
    assert agents2[0]["name"] == "bob"


def test_users_cannot_read_each_others_messages():
    h1 = _account()
    h2 = _account()

    _add("sender", headers=h1)
    _add("target", headers=h1)
    _send("target", "secret", "sender", headers=h1)

    _add("target", headers=h2)

    assert len(_recv("target", headers=h1)) == 1
    assert len(_recv("target", headers=h2)) == 0


# ── Add agent ──

def test_add_agent():
    resp = client.post("/api/v1/agents", json={"name": "backend", "desc": "Backend agent"}, headers=_auth)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "name": "backend"}


def test_add_agent_duplicate_overwrites():
    _add("dup", desc="first")
    _add("dup", desc="second")
    agents = _get("/api/v1/agents").json()
    assert len(agents) == 1
    assert agents[0]["desc"] == "second"


# ── Send ──

def test_send():
    _add("sender1")
    _add("target1")
    resp = _send("target1", "hello", "sender1")
    assert resp.status_code == 200
    assert resp.json()["to"] == "target1"

    msgs = _recv("target1")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "hello"
    assert msgs[0]["from"] == "sender1"


def test_send_target_not_found():
    assert _send("nonexistent").status_code == 404


def test_send_with_reply_to():
    _add("reply-tgt")
    _send("reply-tgt", "reply", "s", reply_to="orig-id")
    assert _recv("reply-tgt")[0]["reply_to"] == "orig-id"


def test_send_empty_message():
    _add("empty-tgt")
    _send("empty-tgt", "", "s")
    assert _recv("empty-tgt")[0]["payload"] == ""


def test_send_unicode():
    _add("uni-tgt")
    payload = "你好世界 🌍 café"
    _send("uni-tgt", payload, "s")
    assert _recv("uni-tgt")[0]["payload"] == payload


# ── Recv ──

def test_recv():
    _add("recv-s")
    _add("recv-t")
    _send("recv-t", "hello", "recv-s")

    msgs = _recv("recv-t")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "hello"
    assert _recv("recv-t") == []


def test_recv_type_filter():
    _add("filter-t")
    _send("filter-t", "text msg", "s", type="text")
    _send("filter-t", "task msg", "s", type="task")

    msgs = _recv("filter-t", type="task")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "task msg"


def test_recv_empty():
    assert _get("/api/v1/recv/no-such").json() == []


# ── Agents list ──

def test_list_agents():
    _add("a1")
    _add("a2")
    agents = _get("/api/v1/agents").json()
    assert len(agents) == 2
    assert {a["name"] for a in agents} == {"a1", "a2"}


# ── Status ──

def test_status():
    _add("stat-s")
    _send("stat-s", "pending", "stat-s")

    data = _get("/api/v1/status").json()
    assert data["sessions"]["total"] == 1
    assert data["messages"]["pending"] == 1

    _recv("stat-s")
    data2 = _get("/api/v1/status").json()
    assert data2["messages"] == {"pending": 0, "delivered": 1}


def test_status_empty():
    data = _get("/api/v1/status").json()
    assert data["sessions"] == {"total": 0}
    assert data["messages"] == {"pending": 0, "delivered": 0}


# ── History ──

def test_history():
    _add("h-s")
    _add("h-r")
    _send("h-r", "for history", "h-s")
    _recv("h-r")

    msgs = _get("/api/v1/history?limit=50").json()
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "for history"


def test_history_empty():
    assert _get("/api/v1/history").json() == []


# ── Rate limiting ──

def test_message_max_length():
    _add("len-tgt")
    resp = _send("len-tgt", "x" * 20_000, "s")
    assert resp.status_code == 413


def test_qps_rate_limit():
    _add("rl-tgt")
    blocked = False
    for i in range(20):
        resp = _send("rl-tgt", f"msg-{i}", "s")
        if resp.status_code == 429:
            blocked = True
            break
    assert blocked
