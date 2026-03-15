"""Tests for CLI (mq.py) — real subprocess with isolated temp directory."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "skills" / "mq" / "scripts" / "mq.py")


def _run(tmp, *args):
    env = os.environ.copy()
    env["AGENT_MQ_DATA_DIR"] = str(tmp)
    r = subprocess.run([sys.executable, SCRIPT, *args],
                       capture_output=True, text=True, timeout=10, env=env)
    return r.returncode, r.stdout, r.stderr


# ── Add ──

def test_add(tmp_path):
    rc, out, _ = _run(tmp_path, "add", "backend", "--desc", "Test agent")
    assert rc == 0
    assert "added backend" in out
    assert (tmp_path / "registry" / "backend.json").exists()


def test_add_creates_inbox(tmp_path):
    _run(tmp_path, "add", "worker")
    assert (tmp_path / "inbox" / "worker").is_dir()


# ── Send + Recv ──

def test_send_and_recv(tmp_path):
    _run(tmp_path, "add", "alice")
    _run(tmp_path, "add", "bob")

    rc, out, _ = _run(tmp_path, "send", "bob", "hello from alice", "--from", "alice")
    assert rc == 0
    assert "sent" in out and "bob" in out

    rc, out, _ = _run(tmp_path, "recv", "bob")
    assert rc == 0
    assert "hello from alice" in out
    assert "from=alice" in out

    _, out, _ = _run(tmp_path, "recv", "bob")
    assert "hello from alice" not in out


def test_send_target_not_found(tmp_path):
    rc, _, err = _run(tmp_path, "send", "nonexistent", "msg", "--from", "s")
    assert rc != 0
    assert "not found" in err


def test_send_missing_from(tmp_path):
    rc, _, err = _run(tmp_path, "send", "target", "msg")
    assert rc != 0
    assert "--from" in err


def test_send_with_type_and_priority(tmp_path):
    _run(tmp_path, "add", "typed")
    rc, out, _ = _run(tmp_path, "send", "typed", "urgent task", "--from", "s",
                       "--type", "task", "--priority", "urgent")
    assert rc == 0


# ── Recv options ──

def test_recv_json(tmp_path):
    _run(tmp_path, "add", "jr")
    _run(tmp_path, "send", "jr", "json payload", "--from", "s")
    _, out, _ = _run(tmp_path, "recv", "jr", "--json")
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["payload"] == "json payload"


def test_recv_peek(tmp_path):
    _run(tmp_path, "add", "peek")
    _run(tmp_path, "send", "peek", "peek msg", "--from", "s")

    for _ in range(2):
        _, out, _ = _run(tmp_path, "recv", "peek", "--peek")
        assert "peek msg" in out

    _, out, _ = _run(tmp_path, "recv", "peek")
    assert "peek msg" in out

    _, out, _ = _run(tmp_path, "recv", "peek", "--json")
    assert json.loads(out) == []


# ── Ls ──

def test_ls(tmp_path):
    _run(tmp_path, "add", "alpha")
    _run(tmp_path, "add", "beta")
    rc, out, _ = _run(tmp_path, "ls")
    assert rc == 0
    assert "alpha" in out and "beta" in out


def test_ls_json(tmp_path):
    _run(tmp_path, "add", "one")
    _run(tmp_path, "add", "two")
    _, out, _ = _run(tmp_path, "ls", "--json")
    names = {a["name"] for a in json.loads(out)}
    assert names == {"one", "two"}


# ── History ──

def test_history(tmp_path):
    _run(tmp_path, "add", "hs")
    _run(tmp_path, "add", "hr")
    _run(tmp_path, "send", "hr", "for history", "--from", "hs")
    _run(tmp_path, "recv", "hr")

    rc, out, _ = _run(tmp_path, "history")
    assert rc == 0
    assert "for history" in out


def test_history_json(tmp_path):
    _run(tmp_path, "add", "hs")
    _run(tmp_path, "add", "hr")
    _run(tmp_path, "send", "hr", "history payload", "--from", "hs")
    _run(tmp_path, "recv", "hr")

    _, out, _ = _run(tmp_path, "history", "--json")
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["payload"] == "history payload"


# ── Login / Logout ──

def test_logout(tmp_path):
    rc, out, _ = _run(tmp_path, "logout")
    assert rc == 0
    assert "local mode" in out


def test_no_command_shows_help(tmp_path):
    _, out, err = _run(tmp_path)
    assert "mq" in (out + err).lower()
