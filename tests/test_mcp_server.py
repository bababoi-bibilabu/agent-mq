"""Tests for MCP server — real stdio protocol via mcp.client."""

import asyncio
import json
import os
from pathlib import Path

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

SCRIPT = str(Path(__file__).parent.parent / "skills" / "mq" / "scripts" / "mcp_server.py")


def _session(tmp_dir):
    env = os.environ.copy()
    env["AGENT_MQ_DATA_DIR"] = tmp_dir
    return StdioServerParameters(command="python3", args=[SCRIPT], env=env)


def _parse(result):
    assert not result.isError, f"Tool error: {result.content}"
    if len(result.content) == 1:
        return json.loads(result.content[0].text)
    return [json.loads(c.text) for c in result.content]


def _as_list(data):
    return [data] if isinstance(data, dict) else data


def test_list_tools(tmp_path):
    async def _test():
        async with stdio_client(_session(str(tmp_path))) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                assert names == {"mq_add", "mq_send", "mq_recv", "mq_ls", "mq_history", "mq_login", "mq_logout"}

    asyncio.run(_test())


def test_add(tmp_path):
    async def _test():
        async with stdio_client(_session(str(tmp_path))) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                result = _parse(await s.call_tool("mq_add", {"name": "backend", "desc": "test"}))
                assert result == {"status": "ok", "name": "backend"}
        assert (tmp_path / "registry" / "backend.json").exists()
        assert (tmp_path / "inbox" / "backend").is_dir()

    asyncio.run(_test())


def test_send_and_recv(tmp_path):
    async def _test():
        async with stdio_client(_session(str(tmp_path))) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                _parse(await s.call_tool("mq_add", {"name": "sender"}))
                _parse(await s.call_tool("mq_add", {"name": "receiver"}))

                send = _parse(await s.call_tool("mq_send", {
                    "target": "receiver", "message": "hello via mcp", "sender": "sender",
                }))
                assert send["to"] == "receiver"

                msgs = _as_list(_parse(await s.call_tool("mq_recv", {"name": "receiver"})))
                assert len(msgs) == 1
                assert msgs[0]["payload"] == "hello via mcp"

                assert _as_list(_parse(await s.call_tool("mq_recv", {"name": "receiver"}))) == []

    asyncio.run(_test())


def test_recv_peek(tmp_path):
    async def _test():
        async with stdio_client(_session(str(tmp_path))) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                _parse(await s.call_tool("mq_add", {"name": "peek-t"}))
                _parse(await s.call_tool("mq_send", {"target": "peek-t", "message": "peek msg", "sender": "s"}))

                for _ in range(2):
                    msgs = _as_list(_parse(await s.call_tool("mq_recv", {"name": "peek-t", "peek": True})))
                    assert len(msgs) == 1
                    assert msgs[0]["payload"] == "peek msg"

                assert len(_as_list(_parse(await s.call_tool("mq_recv", {"name": "peek-t"})))) == 1
                assert _as_list(_parse(await s.call_tool("mq_recv", {"name": "peek-t"}))) == []

    asyncio.run(_test())


def test_ls(tmp_path):
    async def _test():
        async with stdio_client(_session(str(tmp_path))) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                _parse(await s.call_tool("mq_add", {"name": "alpha"}))
                _parse(await s.call_tool("mq_add", {"name": "beta"}))

                agents = _as_list(_parse(await s.call_tool("mq_ls", {})))
                assert len(agents) == 2
                assert {a["name"] for a in agents} == {"alpha", "beta"}

    asyncio.run(_test())
