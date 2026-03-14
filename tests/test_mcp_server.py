"""Tests for MCP server — real stdio protocol via mcp.client.

Each test starts the MCP server as a subprocess and communicates
over stdio using the MCP SDK client, verifying actual protocol behavior.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

SCRIPT = str(Path(__file__).parent.parent / "skills" / "mq" / "scripts" / "mcp_server.py")


def _make_session(tmp_dir):
    """Create MCP client session parameters with isolated temp dir."""
    env = os.environ.copy()
    env["AGENT_MQ_DATA_DIR"] = tmp_dir
    return StdioServerParameters(command="python3", args=[SCRIPT], env=env)


def _parse(result):
    """Extract data from a CallToolResult.

    FastMCP with json_response=True puts each list item as a separate
    content block. Dicts come as a single content block.
    """
    assert not result.isError, f"Tool returned error: {result.content}"
    if len(result.content) == 1:
        return json.loads(result.content[0].text)
    # Multiple content blocks → list of items
    return [json.loads(c.text) for c in result.content]


def _run(coro):
    asyncio.run(coro)


# ── Tool Discovery ──

def test_list_tools(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                expected = {
                    "mq_register", "mq_send", "mq_recv", "mq_broadcast",
                    "mq_ls", "mq_resolve", "mq_status", "mq_heartbeat",
                    "mq_history", "mq_clean",
                }
                assert expected == names

    _run(_test())


def test_tools_have_descriptions(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                for tool in tools.tools:
                    assert tool.description, f"{tool.name} has no description"
                    assert len(tool.description) > 10, f"{tool.name} description too short"

    _run(_test())


# ── Register ──

def test_register(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = _parse(await session.call_tool("mq_register", {
                    "session_id": "reg-1", "alias": "proto-test", "desc": "MCP protocol test",
                }))
                assert result["status"] == "ok"
                assert result["id"] == "reg-1"
                assert result["alias"] == "proto-test"

        # Verify file was actually created
        assert (tmp_path / "registry" / "reg-1.json").exists()
        assert (tmp_path / "inbox" / "reg-1").is_dir()

    _run(_test())


# ── Send + Recv full cycle ──

def test_send_and_recv(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                _parse(await session.call_tool("mq_register", {
                    "session_id": "sender", "alias": "sender-alias",
                }))
                _parse(await session.call_tool("mq_register", {
                    "session_id": "receiver", "alias": "receiver-alias",
                }))

                # Send by alias
                send_result = _parse(await session.call_tool("mq_send", {
                    "target": "receiver-alias",
                    "message": "hello via mcp protocol",
                    "sender": "sender",
                }))
                assert send_result["status"] == "ok"
                assert send_result["to"] == "receiver"

                # Recv
                messages = _parse(await session.call_tool("mq_recv", {
                    "session_id": "receiver",
                }))
                # Single message → _parse returns dict (one content block)
                if isinstance(messages, dict):
                    messages = [messages]
                assert len(messages) == 1
                assert messages[0]["payload"] == "hello via mcp protocol"
                assert messages[0]["_sender_alias"] == "sender-alias"

                # Consumed — second recv empty
                result2 = await session.call_tool("mq_recv", {"session_id": "receiver"})
                msgs2 = _parse(result2)
                if isinstance(msgs2, dict):
                    msgs2 = [msgs2]
                assert msgs2 == [] or len(msgs2) == 0

    _run(_test())


def test_send_with_type_and_priority(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "typed-tgt"}))
                _parse(await session.call_tool("mq_send", {
                    "target": "typed-tgt", "message": "urgent task",
                    "sender": "s1", "msg_type": "task", "priority": "urgent",
                }))

                result = await session.call_tool("mq_recv", {"session_id": "typed-tgt"})
                msg = _parse(result)
                if isinstance(msg, list):
                    msg = msg[0]
                assert msg["type"] == "task"
                assert msg["priority"] == "urgent"
                assert msg["payload"] == "urgent task"

    _run(_test())


def test_send_empty_reply_to_becomes_none(tmp_path):
    """Empty string reply_to from MCP should be treated as None."""
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "rt-tgt"}))
                _parse(await session.call_tool("mq_send", {
                    "target": "rt-tgt", "message": "msg", "sender": "s", "reply_to": "",
                }))
                result = await session.call_tool("mq_recv", {"session_id": "rt-tgt"})
                msg = _parse(result)
                if isinstance(msg, list):
                    msg = msg[0]
                assert "reply_to" not in msg

    _run(_test())


# ── Recv options ──

def test_recv_peek(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "peek-t"}))
                _parse(await session.call_tool("mq_send", {
                    "target": "peek-t", "message": "peek msg", "sender": "s",
                }))

                # Peek — message stays
                msg = _parse(await session.call_tool("mq_recv", {
                    "session_id": "peek-t", "peek": True,
                }))
                if isinstance(msg, dict):
                    msg = [msg]
                assert len(msg) == 1
                assert msg[0]["payload"] == "peek msg"

                # Still there after peek
                msg2 = _parse(await session.call_tool("mq_recv", {
                    "session_id": "peek-t", "peek": True,
                }))
                if isinstance(msg2, dict):
                    msg2 = [msg2]
                assert len(msg2) == 1

                # Consume
                msg3 = _parse(await session.call_tool("mq_recv", {
                    "session_id": "peek-t",
                }))
                if isinstance(msg3, dict):
                    msg3 = [msg3]
                assert len(msg3) == 1

                # Gone — empty list returns [] from content[0]
                result4 = await session.call_tool("mq_recv", {"session_id": "peek-t"})
                msgs4 = _parse(result4)
                if isinstance(msgs4, dict):
                    msgs4 = [msgs4]
                assert msgs4 == []

    _run(_test())


def test_recv_type_filter(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "filter-t"}))
                _parse(await session.call_tool("mq_send", {
                    "target": "filter-t", "message": "text msg", "sender": "s", "msg_type": "text",
                }))
                _parse(await session.call_tool("mq_send", {
                    "target": "filter-t", "message": "task msg", "sender": "s", "msg_type": "task",
                }))

                result = await session.call_tool("mq_recv", {
                    "session_id": "filter-t", "peek": True, "msg_type": "task",
                })
                msg = _parse(result)
                if isinstance(msg, dict):
                    msg = [msg]
                assert len(msg) == 1
                assert msg[0]["payload"] == "task msg"

    _run(_test())


def test_recv_empty_type_no_filter(tmp_path):
    """Empty string msg_type from MCP should be treated as None (no filter)."""
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "mt-tgt"}))
                _parse(await session.call_tool("mq_send", {
                    "target": "mt-tgt", "message": "typed msg", "sender": "s", "msg_type": "task",
                }))
                # Empty string msg_type should NOT filter — message should come through
                result = await session.call_tool("mq_recv", {
                    "session_id": "mt-tgt", "peek": True, "msg_type": "",
                })
                msg = _parse(result)
                if isinstance(msg, dict):
                    msg = [msg]
                assert len(msg) == 1
                assert msg[0]["payload"] == "typed msg"
                assert msg[0]["type"] == "task"

    _run(_test())


# ── Broadcast ──

def test_broadcast(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "bc-s"}))
                _parse(await session.call_tool("mq_register", {"session_id": "bc-r1"}))
                _parse(await session.call_tool("mq_register", {"session_id": "bc-r2"}))

                result = _parse(await session.call_tool("mq_broadcast", {
                    "message": "broadcast msg", "sender": "bc-s",
                }))
                assert result["status"] == "ok"
                assert result["sent"] == 2

                # Recipients got it
                msg1 = _parse(await session.call_tool("mq_recv", {"session_id": "bc-r1"}))
                if isinstance(msg1, dict):
                    msg1 = [msg1]
                assert len(msg1) == 1
                assert msg1[0]["payload"] == "broadcast msg"

                # Sender didn't get it
                result_s = await session.call_tool("mq_recv", {"session_id": "bc-s"})
                msgs_s = _parse(result_s)
                if isinstance(msgs_s, dict):
                    msgs_s = [msgs_s]
                assert msgs_s == []

    _run(_test())


# ── Ls ──

def test_ls(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {
                    "session_id": "ls-1", "alias": "alpha",
                }))
                _parse(await session.call_tool("mq_register", {
                    "session_id": "ls-2", "alias": "beta",
                }))
                result = await session.call_tool("mq_ls", {})
                sessions = _parse(result)
                if isinstance(sessions, dict):
                    sessions = [sessions]
                assert len(sessions) == 2
                ids = {s["id"] for s in sessions}
                assert "ls-1" in ids
                assert "ls-2" in ids

    _run(_test())


def test_ls_alive_only(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "alive-1"}))
                _parse(await session.call_tool("mq_register", {"session_id": "stale-1"}))

        # Backdate stale-1 to make it stale
        import json as j
        reg = tmp_path / "registry" / "stale-1.json"
        d = j.loads(reg.read_text())
        d["heartbeat"] = "2020-01-01T00:00:00Z"
        reg.write_text(j.dumps(d))

        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("mq_ls", {"alive_only": True})
                sessions = _parse(result)
                if isinstance(sessions, dict):
                    sessions = [sessions]
                ids = {s["id"] for s in sessions}
                assert "alive-1" in ids
                assert "stale-1" not in ids

    _run(_test())


# ── Resolve ──

def test_resolve(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {
                    "session_id": "res-1", "alias": "findme",
                }))
                data = _parse(await session.call_tool("mq_resolve", {"alias": "findme"}))
                assert data["id"] == "res-1"

    _run(_test())


def test_resolve_not_found(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("mq_resolve", {"alias": "nonexistent-xyz"})
                assert result.isError

    _run(_test())


# ── Status ──

def test_status(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "stat-1"}))
                status = _parse(await session.call_tool("mq_status", {}))
                assert status["version"] == "0.1.0"
                assert status["mode"] == "local"
                assert status["sessions"]["total"] == 1
                assert status["sessions"]["alive"] == 1

    _run(_test())


# ── Heartbeat ──

def test_heartbeat(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "hb-1"}))

                # Backdate heartbeat via file
                import json as j
                reg = tmp_path / "registry" / "hb-1.json"
                d = j.loads(reg.read_text())
                d["heartbeat"] = "2020-01-01T00:00:00Z"
                reg.write_text(j.dumps(d))

                result = _parse(await session.call_tool("mq_heartbeat", {"session_id": "hb-1"}))
                assert result["status"] == "ok"

                # Verify timestamp actually updated
                d2 = j.loads(reg.read_text())
                assert d2["heartbeat"] > "2020-01-01T00:00:00Z"

    _run(_test())


def test_heartbeat_not_registered(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("mq_heartbeat", {"session_id": "not-reg-xyz"})
                assert result.isError

    _run(_test())


# ── History ──

def test_history(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _parse(await session.call_tool("mq_register", {"session_id": "h-sender"}))
                _parse(await session.call_tool("mq_register", {"session_id": "h-recv"}))
                _parse(await session.call_tool("mq_send", {
                    "target": "h-recv", "message": "for history", "sender": "h-sender",
                }))
                # Consume
                _parse(await session.call_tool("mq_recv", {"session_id": "h-recv"}))

                result = await session.call_tool("mq_history", {"limit": 50})
                history = _parse(result)
                if isinstance(history, dict):
                    history = [history]
                assert any(m["payload"] == "for history" for m in history)

    _run(_test())


# ── Clean ──

def test_clean(tmp_path):
    async def _test():
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Register a session then backdate its heartbeat to make it stale
                _parse(await session.call_tool("mq_register", {"session_id": "clean-1"}))
                _parse(await session.call_tool("mq_register", {"session_id": "clean-2"}))

        # Backdate clean-1 to make it stale
        import json as j
        reg = tmp_path / "registry" / "clean-1.json"
        d = j.loads(reg.read_text())
        d["heartbeat"] = "2020-01-01T00:00:00Z"
        reg.write_text(j.dumps(d))

        # Clean with 1 min timeout — only stale session removed
        async with stdio_client(_make_session(str(tmp_path))) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = _parse(await session.call_tool("mq_clean", {"timeout_min": 1}))
                assert result["status"] == "ok"
                assert result["cleaned"] == 1

        # Verify stale session actually removed, alive session still exists
        assert not reg.exists()
        assert (tmp_path / "registry" / "clean-2.json").exists()

    _run(_test())
