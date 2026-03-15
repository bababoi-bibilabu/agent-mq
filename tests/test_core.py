"""Tests for agent-mq core module."""

import json
import time

import pytest
import core


# ── Add ──

def test_add():
    result = core.add("backend", desc="Backend agent")
    assert result == {"status": "ok", "name": "backend"}

    data = json.loads((core.REGISTRY_DIR / "backend.json").read_text())
    assert data["name"] == "backend"
    assert data["desc"] == "Backend agent"
    assert data["tool"] == "claude-code"


def test_add_creates_inbox():
    core.add("worker")
    assert (core.INBOX_DIR / "worker").is_dir()


def test_add_same_name_overwrites():
    core.add("dup", desc="first")
    core.add("dup", desc="second")
    assert json.loads((core.REGISTRY_DIR / "dup.json").read_text())["desc"] == "second"


# ── Send + Recv ──

def test_send_and_recv():
    core.add("alice")
    core.add("bob")

    result = core.send("bob", "hello", "alice")
    assert result["status"] == "ok"
    assert result["to"] == "bob"

    msgs = core.recv("bob")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "hello"
    assert msgs[0]["from"] == "alice"
    assert msgs[0]["id"] == result["id"]

    assert core.recv("bob") == []


def test_send_to_self():
    core.add("solo")
    core.send("solo", "note to self", "solo")
    assert core.recv("solo")[0]["payload"] == "note to self"


def test_send_target_not_found():
    with pytest.raises(RuntimeError, match="not found"):
        core.send("nonexistent", "msg", "sender")


@pytest.mark.parametrize("payload", [
    "",
    "你好世界 🌍 café αβγ \n\ttab",
    'he said "hello" and \\ backslash \n newline',
])
def test_send_special_payloads(payload):
    core.add("special")
    core.send("special", payload, "sender")
    assert core.recv("special")[0]["payload"] == payload


def test_send_with_reply_to():
    core.add("replier")
    core.send("replier", "response", "s", reply_to="orig-id")
    assert core.recv("replier")[0]["reply_to"] == "orig-id"


def test_send_priority():
    core.add("urgent-target")
    core.send("urgent-target", "urgent!", "s", priority="urgent")
    assert core.recv("urgent-target")[0]["priority"] == "urgent"


@pytest.mark.parametrize("field, value, match", [
    ("msg_type", "invalid", "Invalid type"),
    ("priority", "critical", "Invalid priority"),
])
def test_send_invalid_field(field, value, match):
    with pytest.raises(ValueError, match=match):
        core.send("x", "msg", "s", **{field: value})


# ── Recv ──

def test_recv_peek():
    core.add("peek-test")
    core.send("peek-test", "peek msg", "s")

    for _ in range(2):
        msgs = core.recv("peek-test", peek=True)
        assert len(msgs) == 1
        assert msgs[0]["payload"] == "peek msg"

    assert len(core.recv("peek-test")) == 1
    assert core.recv("peek-test") == []


def test_recv_type_filter():
    core.add("filter")
    core.send("filter", "text msg", "s", msg_type="text")
    core.send("filter", "task msg", "s", msg_type="task")

    tasks = core.recv("filter", peek=True, msg_type="task")
    assert len(tasks) == 1
    assert tasks[0]["payload"] == "task msg"


def test_recv_nonexistent():
    assert core.recv("no-such") == []


def test_recv_skips_corrupt_json():
    core.add("corrupt")
    core.send("corrupt", "good msg", "s")
    (core.INBOX_DIR / "corrupt" / "bad.json").write_text("{broken!!!")

    msgs = core.recv("corrupt")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "good msg"


# ── Ls ──

def test_ls():
    core.add("alpha", desc="First")
    core.add("beta", desc="Second")
    core.send("alpha", "pending msg", "beta")

    agents = core.ls()
    assert len(agents) == 2
    by_name = {a["name"]: a for a in agents}
    assert by_name["alpha"]["pending"] == 1
    assert by_name["beta"]["pending"] == 0


def test_ls_empty():
    assert core.ls() == []


# ── History ──

def test_history():
    core.add("h-sender")
    core.add("h-recv")
    core.send("h-recv", "for history", "h-sender")
    core.recv("h-recv")

    msgs = core.history(limit=50)
    assert len(msgs) == 1
    assert msgs[0]["payload"] == "for history"


def test_history_limit():
    core.add("lim-s")
    core.add("lim-r")
    for i in range(5):
        core.send("lim-r", f"msg-{i}", "lim-s")
    core.recv("lim-r")

    assert len(core.history(limit=50)) == 5
    assert len(core.history(limit=2)) == 2


def test_history_reverse_chronological():
    core.add("chrono-s")
    core.add("chrono-r")
    for i in range(3):
        core.send("chrono-r", f"msg-{i}", "chrono-s")
        time.sleep(0.05)
    core.recv("chrono-r")

    msgs = core.history(limit=50)
    assert msgs[0]["payload"] == "msg-2"
    assert msgs[-1]["payload"] == "msg-0"


# ── Ordering / Done ──

def test_multiple_messages_ordering():
    core.add("order")
    for msg in ("first", "second", "third"):
        core.send("order", msg, "s")

    payloads = [m["payload"] for m in core.recv("order")]
    assert payloads == ["first", "second", "third"]


def test_done_directory_receives_consumed():
    core.add("done-test")
    core.send("done-test", "will be consumed", "s")
    msg_id = core.recv("done-test")[0]["id"]

    done_file = core.DONE_DIR / f"{msg_id}.json"
    assert done_file.exists()
    assert json.loads(done_file.read_text())["payload"] == "will be consumed"


# ── Path traversal ──

@pytest.mark.parametrize("bad_name", ["../etc/passwd", "foo/bar", "a\\b", "a\0b", ".."])
def test_path_traversal_add(bad_name):
    with pytest.raises(ValueError, match="Invalid agent name"):
        core.add(bad_name)


def test_path_traversal_recv():
    with pytest.raises(ValueError):
        core.recv("../../etc")


def test_path_traversal_send():
    core.add("legit")
    with pytest.raises(ValueError):
        core.send("../evil", "msg", "s")
