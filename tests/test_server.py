"""Tests for cloud server (FastAPI + RocksDB)."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

# Patch DATA_DIR before importing app
_tmp_dir = tempfile.mkdtemp()

import server.app as app_module

app_module.DATA_DIR = Path(_tmp_dir)
app_module.DB_PATH = str(Path(_tmp_dir) / "test.rocksdb")

from fastapi.testclient import TestClient
from server.app import app


@pytest.fixture(autouse=True)
def fresh_db():
    """Open a fresh DB for each test."""
    app_module.db = app_module.open_db()
    yield
    app_module.close_db()
    db_path = Path(app_module.DB_PATH)
    if db_path.exists():
        shutil.rmtree(db_path)


client = TestClient(app)


# ── Register ──

def test_register():
    resp = client.post("/api/v1/register", json={
        "id": "s1", "alias": "backend", "desc": "Backend agent", "tool": "claude-code",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["id"] == "s1"
    assert data["alias"] == "backend"

    # Verify actually stored in DB
    raw = app_module.db[app_module.CF_REGISTRY]["s1"]
    stored = json.loads(raw)
    assert stored["alias"] == "backend"
    assert stored["desc"] == "Backend agent"
    assert stored["tool"] == "claude-code"
    assert "heartbeat_ts" in stored


def test_register_minimal():
    resp = client.post("/api/v1/register", json={"id": "s2"})
    assert resp.status_code == 200

    # Verify stored with defaults
    raw = app_module.db[app_module.CF_REGISTRY]["s2"]
    stored = json.loads(raw)
    assert stored["id"] == "s2"
    assert stored["alias"] == ""
    assert stored["tool"] == "claude-code"


# ── Send ──

def test_send():
    client.post("/api/v1/register", json={"id": "sender1"})
    client.post("/api/v1/register", json={"id": "target1", "alias": "tgt"})

    resp = client.post("/api/v1/send", json={
        "target": "target1", "message": "hello", "from": "sender1",
        "type": "text", "priority": "normal",
    })
    assert resp.status_code == 200
    assert resp.json()["to"] == "target1"

    # Verify message actually stored and retrievable
    msgs = client.get("/api/v1/recv/target1").json()
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "hello"
    assert msgs[0]["from"] == "sender1"
    assert msgs[0]["type"] == "text"


def test_send_by_alias():
    client.post("/api/v1/register", json={"id": "alias-target", "alias": "myalias"})
    resp = client.post("/api/v1/send", json={
        "target": "myalias", "message": "via alias", "from": "someone",
    })
    assert resp.status_code == 200
    assert resp.json()["to"] == "alias-target"

    # Verify message ended up in the right inbox
    msgs = client.get("/api/v1/recv/alias-target").json()
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "via alias"


def test_send_with_reply_to():
    client.post("/api/v1/register", json={"id": "reply-tgt"})
    client.post("/api/v1/send", json={
        "target": "reply-tgt", "message": "reply", "from": "s",
        "reply_to": "orig-msg-id",
    })

    # Verify reply_to was preserved
    msgs = client.get("/api/v1/recv/reply-tgt").json()
    assert len(msgs) == 1
    assert msgs[0]["reply_to"] == "orig-msg-id"


def test_send_target_not_found():
    resp = client.post("/api/v1/send", json={
        "target": "nonexistent", "message": "msg", "from": "s",
    })
    assert resp.status_code == 404


# ── Recv ──

def test_recv():
    client.post("/api/v1/register", json={"id": "recv-s", "alias": "rsender"})
    client.post("/api/v1/register", json={"id": "recv-t"})
    client.post("/api/v1/send", json={
        "target": "recv-t", "message": "hello", "from": "recv-s",
    })

    resp = client.get("/api/v1/recv/recv-t")
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "hello"
    assert msgs[0]["_sender_alias"] == "rsender"

    # Consumed
    resp2 = client.get("/api/v1/recv/recv-t")
    assert resp2.json() == []


def test_recv_peek():
    client.post("/api/v1/register", json={"id": "peek-t"})
    client.post("/api/v1/send", json={
        "target": "peek-t", "message": "peek", "from": "s",
    })

    resp = client.get("/api/v1/recv/peek-t?peek=true")
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "peek"

    # Still there
    resp2 = client.get("/api/v1/recv/peek-t?peek=true")
    assert len(resp2.json()) == 1
    assert resp2.json()[0]["payload"] == "peek"

    # Consume and verify gone
    client.get("/api/v1/recv/peek-t")
    resp3 = client.get("/api/v1/recv/peek-t")
    assert resp3.json() == []


def test_recv_type_filter():
    client.post("/api/v1/register", json={"id": "filter-t"})
    client.post("/api/v1/send", json={
        "target": "filter-t", "message": "text msg", "from": "s", "type": "text",
    })
    client.post("/api/v1/send", json={
        "target": "filter-t", "message": "task msg", "from": "s", "type": "task",
    })

    resp = client.get("/api/v1/recv/filter-t?peek=true&type=task")
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "task msg"


def test_recv_empty():
    resp = client.get("/api/v1/recv/no-such-session")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Broadcast ──

def test_broadcast():
    client.post("/api/v1/register", json={"id": "bc-s"})
    client.post("/api/v1/register", json={"id": "bc-r1"})
    client.post("/api/v1/register", json={"id": "bc-r2"})

    resp = client.post("/api/v1/broadcast", json={
        "message": "hello all", "from": "bc-s",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] == 2

    msgs1 = client.get("/api/v1/recv/bc-r1").json()
    assert len(msgs1) == 1
    assert msgs1[0]["payload"] == "hello all"
    assert msgs1[0]["broadcast"] is True

    msgs2 = client.get("/api/v1/recv/bc-r2").json()
    assert len(msgs2) == 1
    assert msgs2[0]["payload"] == "hello all"

    # Sender shouldn't receive own broadcast
    msgs_s = client.get("/api/v1/recv/bc-s").json()
    assert len(msgs_s) == 0


# ── Sessions ──

def test_list_sessions():
    client.post("/api/v1/register", json={"id": "ls-1", "alias": "a1"})
    client.post("/api/v1/register", json={"id": "ls-2", "alias": "a2"})

    resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2
    ids = [s["id"] for s in sessions]
    assert "ls-1" in ids
    assert "ls-2" in ids


def test_list_sessions_alive_filter():
    client.post("/api/v1/register", json={"id": "alive-s"})
    client.post("/api/v1/register", json={"id": "stale-s"})

    # Make stale-s stale
    raw = app_module.db[app_module.CF_REGISTRY]["stale-s"]
    data = json.loads(raw)
    data["heartbeat_ts"] = 0
    app_module.db[app_module.CF_REGISTRY]["stale-s"] = json.dumps(data)

    resp = client.get("/api/v1/sessions?alive=true")
    sessions = resp.json()
    ids = [s["id"] for s in sessions]
    assert "alive-s" in ids
    assert "stale-s" not in ids  # filtered out


# ── Resolve ──

def test_resolve():
    client.post("/api/v1/register", json={"id": "res-s", "alias": "findme"})
    resp = client.get("/api/v1/resolve/findme")
    assert resp.status_code == 200
    assert resp.json()["id"] == "res-s"


def test_resolve_not_found():
    resp = client.get("/api/v1/resolve/nonexistent")
    assert resp.status_code == 404


# ── Status ──

def test_status():
    client.post("/api/v1/register", json={"id": "stat-s"})
    client.post("/api/v1/send", json={
        "target": "stat-s", "message": "pending msg", "from": "stat-s",
    })

    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "0.1.0"
    assert data["sessions"]["total"] == 1
    assert data["sessions"]["alive"] == 1
    assert data["messages"]["pending"] == 1

    # Consume and check delivered count
    client.get("/api/v1/recv/stat-s")
    data2 = client.get("/api/v1/status").json()
    assert data2["messages"]["pending"] == 0
    assert data2["messages"]["delivered"] == 1


# ── Heartbeat ──

def test_heartbeat():
    client.post("/api/v1/register", json={"id": "hb-s"})

    # Backdate heartbeat
    raw = app_module.db[app_module.CF_REGISTRY]["hb-s"]
    data = json.loads(raw)
    old_ts = data["heartbeat_ts"]
    data["heartbeat_ts"] = 0
    data["heartbeat"] = "2020-01-01T00:00:00Z"
    app_module.db[app_module.CF_REGISTRY]["hb-s"] = json.dumps(data)

    resp = client.post("/api/v1/heartbeat/hb-s")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify timestamp actually updated
    updated = json.loads(app_module.db[app_module.CF_REGISTRY]["hb-s"])
    assert updated["heartbeat_ts"] > 0
    assert updated["heartbeat"] > "2020-01-01T00:00:00Z"


def test_heartbeat_not_registered():
    resp = client.post("/api/v1/heartbeat/nonexistent")
    assert resp.status_code == 404


# ── Clean ──

def test_clean():
    client.post("/api/v1/register", json={"id": "clean-s"})
    # Send a message to clean-s to verify inbox cleanup
    client.post("/api/v1/send", json={
        "target": "clean-s", "message": "orphan", "from": "clean-s",
    })

    # Make it stale
    raw = app_module.db[app_module.CF_REGISTRY]["clean-s"]
    data = json.loads(raw)
    data["heartbeat_ts"] = 0
    app_module.db[app_module.CF_REGISTRY]["clean-s"] = json.dumps(data)

    resp = client.delete("/api/v1/clean?timeout=1")
    assert resp.status_code == 200
    assert resp.json()["cleaned"] == 1

    # Verify actually removed from DB
    assert app_module.db[app_module.CF_REGISTRY].get("clean-s") is None

    # Verify inbox also cleaned
    inbox_keys = [k for k in app_module.db[app_module.CF_INBOX].keys()
                  if k.startswith("clean-s:")]
    assert inbox_keys == []


# ── Analytics ──

def test_analytics_summary():
    client.post("/api/v1/register", json={"id": "a-s", "tool": "claude-code"})
    client.post("/api/v1/register", json={"id": "a-r", "tool": "codex"})
    client.post("/api/v1/send", json={
        "target": "a-r", "message": "msg", "from": "a-s",
    })

    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 3  # 2 registers + 1 send
    assert data["by_event"]["register"] == 2
    assert data["by_event"]["send"] == 1
    assert data["by_tool"]["claude-code"] == 1
    assert data["by_tool"]["codex"] == 1
