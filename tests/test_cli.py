"""Tests for CLI (mq.py) — real subprocess with isolated temp directory.

Each test gets its own temp dir via pytest tmp_path, so tests are fully
independent and can run in any order.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "skills" / "mq" / "scripts" / "mq.py")


def _run(tmp, *args):
    """Run mq.py CLI in isolated temp directory."""
    env = os.environ.copy()
    env["AGENT_MQ_DATA_DIR"] = str(tmp)
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, timeout=10, env=env,
    )
    return result.returncode, result.stdout, result.stderr


# ── Registration ──

def test_register(tmp_path):
    rc, out, _ = _run(tmp_path, "register", "sess-1", "--alias", "backend", "--desc", "Test session")
    assert rc == 0
    assert "registered" in out
    assert "backend" in out
    assert (tmp_path / "registry" / "sess-1.json").exists()


def test_register_creates_inbox(tmp_path):
    _run(tmp_path, "register", "sess-inbox")
    assert (tmp_path / "inbox" / "sess-inbox").is_dir()


# ── Send + Recv ──

def test_send_and_recv_full_cycle(tmp_path):
    _run(tmp_path, "register", "sender-1", "--alias", "alice")
    _run(tmp_path, "register", "receiver-1", "--alias", "bob")

    rc, out, _ = _run(tmp_path, "send", "bob", "hello from alice", "--from", "sender-1")
    assert rc == 0
    assert "sent" in out
    assert "bob" in out

    rc, out, _ = _run(tmp_path, "recv", "receiver-1")
    assert rc == 0
    assert "hello from alice" in out
    assert "from=alice" in out  # sender alias shown in formatted output

    # Message consumed — second recv empty
    rc, out, _ = _run(tmp_path, "recv", "receiver-1")
    assert "hello from alice" not in out


def test_send_by_session_id(tmp_path):
    _run(tmp_path, "register", "direct-target")
    rc, out, _ = _run(tmp_path, "send", "direct-target", "direct msg", "--from", "someone")
    assert rc == 0

    rc, out, _ = _run(tmp_path, "recv", "direct-target", "--json")
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["payload"] == "direct msg"


def test_send_target_not_found(tmp_path):
    rc, _, err = _run(tmp_path, "send", "nonexistent-target", "msg", "--from", "s")
    assert rc != 0
    assert "not found" in err


def test_send_missing_from(tmp_path):
    rc, _, err = _run(tmp_path, "send", "target", "msg")
    assert rc != 0
    assert "--from" in err


def test_send_invalid_type(tmp_path):
    rc, _, err = _run(tmp_path, "send", "x", "msg", "--from", "s", "--type", "bogus")
    assert rc != 0
    assert "invalid choice" in err.lower() or "bogus" in err.lower()


def test_send_with_type_and_priority(tmp_path):
    _run(tmp_path, "register", "typed-target")
    rc, out, _ = _run(tmp_path, "send", "typed-target", "urgent task", "--from", "s1",
                       "--type", "task", "--priority", "urgent")
    assert rc == 0
    assert "task:urgent" in out


# ── Recv options ──

def test_recv_json(tmp_path):
    _run(tmp_path, "register", "json-recv")
    _run(tmp_path, "send", "json-recv", "json payload", "--from", "s")
    rc, out, _ = _run(tmp_path, "recv", "json-recv", "--json")
    assert rc == 0
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["payload"] == "json payload"


def test_recv_peek(tmp_path):
    _run(tmp_path, "register", "peek-target")
    _run(tmp_path, "send", "peek-target", "peek msg", "--from", "s")

    # Peek — message stays
    rc, out, _ = _run(tmp_path, "recv", "peek-target", "--peek")
    assert "peek msg" in out

    rc, out, _ = _run(tmp_path, "recv", "peek-target", "--peek")
    assert "peek msg" in out

    # Consume
    rc, out, _ = _run(tmp_path, "recv", "peek-target")
    assert "peek msg" in out

    # Now gone
    rc, out, _ = _run(tmp_path, "recv", "peek-target", "--json")
    assert json.loads(out) == []


def test_recv_type_filter(tmp_path):
    _run(tmp_path, "register", "filter-target")
    _run(tmp_path, "send", "filter-target", "text msg", "--from", "s", "--type", "text")
    _run(tmp_path, "send", "filter-target", "task msg", "--from", "s", "--type", "task")

    rc, out, _ = _run(tmp_path, "recv", "filter-target", "--peek", "--type", "task", "--json")
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["payload"] == "task msg"


# ── Broadcast ──

def test_broadcast(tmp_path):
    _run(tmp_path, "register", "bc-sender")
    _run(tmp_path, "register", "bc-r1")
    _run(tmp_path, "register", "bc-r2")
    rc, out, _ = _run(tmp_path, "broadcast", "hello all", "--from", "bc-sender")
    assert rc == 0
    assert "broadcast" in out
    assert "2 session" in out  # exactly 2 recipients

    # Recipients got the message
    _, out1, _ = _run(tmp_path, "recv", "bc-r1", "--json")
    msgs1 = json.loads(out1)
    assert len(msgs1) == 1
    assert msgs1[0]["payload"] == "hello all"

    _, out2, _ = _run(tmp_path, "recv", "bc-r2", "--json")
    msgs2 = json.loads(out2)
    assert len(msgs2) == 1
    assert msgs2[0]["payload"] == "hello all"

    # Sender didn't get it
    _, out_s, _ = _run(tmp_path, "recv", "bc-sender", "--json")
    assert json.loads(out_s) == []


# ── Ls ──

def test_ls(tmp_path):
    _run(tmp_path, "register", "ls-1", "--alias", "alpha")
    _run(tmp_path, "register", "ls-2", "--alias", "beta")
    rc, out, _ = _run(tmp_path, "ls")
    assert rc == 0
    assert "ls-1" in out
    assert "ls-2" in out
    assert "alpha" in out


def test_ls_json(tmp_path):
    _run(tmp_path, "register", "ls-1", "--alias", "one")
    _run(tmp_path, "register", "ls-2", "--alias", "two")
    rc, out, _ = _run(tmp_path, "ls", "--json")
    assert rc == 0
    data = json.loads(out)
    assert len(data) == 2
    by_id = {s["id"]: s for s in data}
    assert by_id["ls-1"]["alias"] == "one"
    assert by_id["ls-2"]["alias"] == "two"
    assert by_id["ls-1"]["status"] == "alive"


# ── Resolve ──

def test_resolve(tmp_path):
    _run(tmp_path, "register", "resolve-sess", "--alias", "findme")
    rc, out, _ = _run(tmp_path, "resolve", "findme")
    assert rc == 0
    assert "resolve-sess" in out


def test_resolve_json(tmp_path):
    _run(tmp_path, "register", "resolve-sess", "--alias", "findme")
    rc, out, _ = _run(tmp_path, "resolve", "findme", "--json")
    assert rc == 0
    data = json.loads(out)
    assert data["id"] == "resolve-sess"


def test_resolve_not_found(tmp_path):
    rc, _, err = _run(tmp_path, "resolve", "nonexistent-alias-xyz")
    assert rc != 0
    assert "not found" in err


# ── Status ──

def test_status(tmp_path):
    _run(tmp_path, "register", "status-sess")
    _run(tmp_path, "send", "status-sess", "pending msg", "--from", "status-sess")
    rc, out, _ = _run(tmp_path, "status")
    assert rc == 0
    assert "agent-mq" in out
    assert "local" in out
    # Verify actual counts rendered, not just labels
    assert "1 alive" in out
    assert "1 pending" in out


# ── Heartbeat ──

def test_heartbeat(tmp_path):
    _run(tmp_path, "register", "hb-sess")

    # Backdate heartbeat
    import json as j
    reg = tmp_path / "registry" / "hb-sess.json"
    d = j.loads(reg.read_text())
    d["heartbeat"] = "2020-01-01T00:00:00Z"
    reg.write_text(j.dumps(d))

    rc, _, _ = _run(tmp_path, "heartbeat", "hb-sess")
    assert rc == 0

    # Verify timestamp actually updated
    d2 = j.loads(reg.read_text())
    assert d2["heartbeat"] > "2020-01-01T00:00:00Z"


def test_heartbeat_not_registered(tmp_path):
    rc, _, err = _run(tmp_path, "heartbeat", "not-registered-xyz")
    assert rc != 0
    assert "not registered" in err


# ── History ──

def test_history(tmp_path):
    _run(tmp_path, "register", "hist-s")
    _run(tmp_path, "register", "hist-r")
    _run(tmp_path, "send", "hist-r", "for history", "--from", "hist-s")
    _run(tmp_path, "recv", "hist-r")  # consume → done

    rc, out, _ = _run(tmp_path, "history")
    assert rc == 0
    assert "for history" in out


def test_history_json(tmp_path):
    _run(tmp_path, "register", "h-s")
    _run(tmp_path, "register", "h-r")
    _run(tmp_path, "send", "h-r", "history payload", "--from", "h-s")
    _run(tmp_path, "recv", "h-r")

    rc, out, _ = _run(tmp_path, "history", "--json")
    assert rc == 0
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["payload"] == "history payload"


# ── Clean ──

def test_clean(tmp_path):
    _run(tmp_path, "register", "stale-sess")
    # Backdate heartbeat
    import json as j
    reg = tmp_path / "registry" / "stale-sess.json"
    d = j.loads(reg.read_text())
    d["heartbeat"] = "2020-01-01T00:00:00Z"
    reg.write_text(j.dumps(d))

    rc, out, _ = _run(tmp_path, "clean", "--timeout", "1")
    assert rc == 0
    assert "cleaned" in out
    assert not reg.exists()  # actually removed


# ── Config / Version / Help ──

def test_version(tmp_path):
    rc, out, _ = _run(tmp_path, "version")
    assert rc == 0
    assert "0.1.0" in out


def test_config(tmp_path):
    rc, out, _ = _run(tmp_path, "config")
    assert rc == 0
    assert "local" in out
    assert "data:" in out
    assert str(tmp_path) in out


def test_no_command_shows_help(tmp_path):
    rc, out, err = _run(tmp_path)
    combined = out + err
    assert "mq" in combined.lower()


def test_logout(tmp_path):
    rc, out, _ = _run(tmp_path, "logout")
    assert rc == 0
    assert "local mode" in out
