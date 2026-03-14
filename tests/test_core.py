"""Tests for agent-mq core module."""

import json

import core


def test_register():
    result = core.register("sess-001", alias="backend", desc="Backend agent")
    assert result["status"] == "ok"
    assert result["id"] == "sess-001"
    assert result["alias"] == "backend"

    reg_file = core.REGISTRY_DIR / "sess-001.json"
    assert reg_file.exists()
    data = json.loads(reg_file.read_text())
    assert data["alias"] == "backend"
    assert data["desc"] == "Backend agent"
    assert data["tool"] == "claude-code"


def test_register_creates_inbox():
    core.register("sess-002")
    assert (core.INBOX_DIR / "sess-002").is_dir()


def test_send_and_recv():
    core.register("sender-1", alias="alice")
    core.register("receiver-1", alias="bob")

    result = core.send("bob", "hello from alice", "sender-1")
    assert result["status"] == "ok"
    assert result["to"] == "receiver-1"
    msg_id = result["id"]

    messages = core.recv("receiver-1")
    assert len(messages) == 1
    assert messages[0]["payload"] == "hello from alice"
    assert messages[0]["from"] == "sender-1"
    assert messages[0]["id"] == msg_id
    assert messages[0]["_sender_alias"] == "alice"

    # Consumed — second recv should be empty
    messages2 = core.recv("receiver-1")
    assert len(messages2) == 0


def test_send_by_session_id():
    core.register("target-direct")
    result = core.send("target-direct", "direct msg", "someone")
    assert result["to"] == "target-direct"

    messages = core.recv("target-direct")
    assert len(messages) == 1
    assert messages[0]["payload"] == "direct msg"


def test_send_target_not_found():
    try:
        core.send("nonexistent", "msg", "sender")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "not found" in str(e)


def test_recv_peek():
    core.register("peek-test")
    core.send("peek-test", "peek msg", "someone")

    msgs1 = core.recv("peek-test", peek=True)
    assert len(msgs1) == 1
    assert msgs1[0]["payload"] == "peek msg"

    # Still there after peek
    msgs2 = core.recv("peek-test", peek=True)
    assert len(msgs2) == 1
    assert msgs2[0]["payload"] == "peek msg"

    # Consume
    msgs3 = core.recv("peek-test", peek=False)
    assert len(msgs3) == 1
    assert msgs3[0]["payload"] == "peek msg"

    msgs4 = core.recv("peek-test")
    assert len(msgs4) == 0


def test_recv_type_filter():
    core.register("filter-test")
    core.send("filter-test", "text msg", "s1", msg_type="text")
    core.send("filter-test", "task msg", "s1", msg_type="task")
    core.send("filter-test", "query msg", "s1", msg_type="query")

    tasks = core.recv("filter-test", peek=True, msg_type="task")
    assert len(tasks) == 1
    assert tasks[0]["payload"] == "task msg"

    queries = core.recv("filter-test", peek=True, msg_type="query")
    assert len(queries) == 1
    assert queries[0]["payload"] == "query msg"


def test_recv_nonexistent_session():
    messages = core.recv("no-such-session")
    assert messages == []


def test_send_with_reply_to():
    core.register("reply-target")
    result = core.send("reply-target", "response", "replier", reply_to="orig-msg-id")
    msgs = core.recv("reply-target")
    assert msgs[0]["reply_to"] == "orig-msg-id"


def test_send_priority():
    core.register("pri-test")
    core.send("pri-test", "urgent!", "s1", priority="urgent")
    msgs = core.recv("pri-test")
    assert msgs[0]["priority"] == "urgent"


def test_send_invalid_type():
    try:
        core.send("x", "msg", "s", msg_type="invalid")
        assert False, "Should have raised"
    except ValueError as e:
        assert "Invalid type" in str(e)


def test_send_invalid_priority():
    try:
        core.send("x", "msg", "s", priority="critical")
        assert False, "Should have raised"
    except ValueError as e:
        assert "Invalid priority" in str(e)


def test_broadcast():
    core.register("bc-sender", alias="sender")
    core.register("bc-recv1", alias="recv1")
    core.register("bc-recv2", alias="recv2")

    result = core.broadcast("hello everyone", "bc-sender")
    assert result["status"] == "ok"
    assert result["sent"] == 2

    msgs1 = core.recv("bc-recv1")
    assert len(msgs1) == 1
    assert msgs1[0]["payload"] == "hello everyone"
    assert msgs1[0]["broadcast"] is True

    msgs2 = core.recv("bc-recv2")
    assert len(msgs2) == 1
    assert msgs2[0]["payload"] == "hello everyone"

    # Sender should not receive own broadcast
    msgs_sender = core.recv("bc-sender")
    assert len(msgs_sender) == 0


def test_ls():
    core.register("ls-1", alias="alpha", desc="First")
    core.register("ls-2", alias="beta", desc="Second")

    sessions = core.ls()
    assert len(sessions) == 2
    by_id = {s["id"]: s for s in sessions}
    assert by_id["ls-1"]["alias"] == "alpha"
    assert by_id["ls-1"]["status"] == "alive"
    assert by_id["ls-1"]["pending"] == 0
    assert by_id["ls-2"]["alias"] == "beta"


def test_ls_alive_only():
    core.register("alive-test")
    core.register("stale-test")

    # Make stale-test stale
    reg_file = core.REGISTRY_DIR / "stale-test.json"
    data = json.loads(reg_file.read_text())
    data["heartbeat"] = "2020-01-01T00:00:00Z"
    reg_file.write_text(json.dumps(data))

    sessions = core.ls(alive_only=True)
    ids = [s["id"] for s in sessions]
    assert "alive-test" in ids
    assert "stale-test" not in ids


def test_resolve():
    core.register("resolve-test", alias="finder")
    data = core.resolve("finder")
    assert data["id"] == "resolve-test"
    assert data["alias"] == "finder"


def test_resolve_not_found():
    try:
        core.resolve("nonexistent-alias")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "not found" in str(e)


def test_status():
    core.register("status-test")
    core.send("status-test", "pending msg", "status-test")

    s = core.get_status()
    assert s["version"] == core.VERSION
    assert s["sessions"]["total"] == 1
    assert s["sessions"]["alive"] == 1
    assert s["messages"]["pending"] == 1

    core.recv("status-test")
    s2 = core.get_status()
    assert s2["messages"]["pending"] == 0
    assert s2["messages"]["delivered"] == 1


def test_heartbeat():
    core.register("hb-test")

    # Backdate heartbeat so we can verify it actually updates
    reg_file = core.REGISTRY_DIR / "hb-test.json"
    data = json.loads(reg_file.read_text())
    data["heartbeat"] = "2020-01-01T00:00:00Z"
    reg_file.write_text(json.dumps(data))

    result = core.heartbeat("hb-test")
    assert result["status"] == "ok"

    reg_after = json.loads(reg_file.read_text())
    assert reg_after["heartbeat"] > "2020-01-01T00:00:00Z"
    assert reg_after["heartbeat"].startswith("20")  # valid ISO timestamp


def test_heartbeat_not_registered():
    try:
        core.heartbeat("not-registered")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "not registered" in str(e)


def test_history():
    core.register("hist-sender", alias="hsender")
    core.register("hist-recv", alias="hrecv")
    core.send("hist-recv", "msg for history", "hist-sender")
    core.recv("hist-recv")  # consume → moves to done

    msgs = core.history(limit=50)
    assert any(m["payload"] == "msg for history" for m in msgs)


def test_clean():
    core.register("stale-session")
    # Manually set heartbeat to the past
    reg_file = core.REGISTRY_DIR / "stale-session.json"
    data = json.loads(reg_file.read_text())
    data["heartbeat"] = "2020-01-01T00:00:00Z"
    reg_file.write_text(json.dumps(data))

    result = core.clean(timeout_min=1)
    assert result["cleaned"] == 1
    assert not reg_file.exists()


def test_multiple_messages_ordering():
    core.register("order-test")
    core.send("order-test", "first", "s1")
    core.send("order-test", "second", "s1")
    core.send("order-test", "third", "s1")

    msgs = core.recv("order-test")
    assert len(msgs) == 3
    payloads = [m["payload"] for m in msgs]
    assert payloads == ["first", "second", "third"]


def test_done_directory_receives_consumed():
    core.register("done-test")
    core.send("done-test", "will be consumed", "s1")
    msgs = core.recv("done-test")
    msg_id = msgs[0]["id"]

    done_file = core.DONE_DIR / f"{msg_id}.json"
    assert done_file.exists()
    data = json.loads(done_file.read_text())
    assert data["payload"] == "will be consumed"


def test_path_traversal_register():
    for bad_id in ["../etc/passwd", "foo/bar", "a\\b", "a\0b"]:
        try:
            core.register(bad_id)
            assert False, f"Should have raised for {bad_id!r}"
        except ValueError as e:
            assert "Invalid session ID" in str(e)


def test_path_traversal_recv():
    try:
        core.recv("../../etc")
        assert False, "Should have raised"
    except ValueError:
        pass


def test_path_traversal_send():
    core.register("legit-target")
    try:
        core.send("../evil", "msg", "sender")
        assert False, "Should have raised"
    except ValueError:
        pass
