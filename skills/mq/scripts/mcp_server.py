#!/usr/bin/env python3
"""agent-mq MCP server — exposes message queue operations as MCP tools.

Runs as stdio server for Claude Code / Codex / OpenClaw plugins.
Supports both local (file-based) and cloud (HTTP relay) modes.
"""

from mcp.server.fastmcp import FastMCP

import core

mcp = FastMCP("agent-mq", json_response=True)


@mcp.tool()
def mq_register(session_id: str, alias: str = "", desc: str = "", tool: str = "claude-code") -> dict:
    """Register a session with the message queue. Call this at session start."""
    return core.register(session_id, alias, desc, tool)


@mcp.tool()
def mq_send(target: str, message: str, sender: str, msg_type: str = "text", priority: str = "normal", reply_to: str = "") -> dict:
    """Send a message to a target session. Target can be a session ID or alias."""
    return core.send(target, message, sender, msg_type, priority, reply_to or None)


@mcp.tool()
def mq_recv(session_id: str, peek: bool = False, msg_type: str = "") -> list:
    """Receive messages from a session's inbox. Consumed on read unless peek=True."""
    return core.recv(session_id, peek, msg_type or None)


@mcp.tool()
def mq_broadcast(message: str, sender: str, msg_type: str = "text", priority: str = "normal") -> dict:
    """Broadcast a message to all alive sessions (except sender)."""
    return core.broadcast(message, sender, msg_type, priority)


@mcp.tool()
def mq_ls(alive_only: bool = False) -> list:
    """List all registered sessions with status and pending message counts."""
    return core.ls(alive_only)


@mcp.tool()
def mq_resolve(alias: str) -> dict:
    """Resolve a session alias to its full session data."""
    return core.resolve(alias)


@mcp.tool()
def mq_status() -> dict:
    """Get overall message queue status: session counts, pending/delivered messages."""
    return core.get_status()


@mcp.tool()
def mq_heartbeat(session_id: str) -> dict:
    """Update a session's heartbeat timestamp to keep it alive."""
    return core.heartbeat(session_id)


@mcp.tool()
def mq_history(limit: int = 20) -> list:
    """View delivered message history (local mode only)."""
    return core.history(limit)


@mcp.tool()
def mq_clean(timeout_min: int = 10) -> dict:
    """Remove sessions that haven't sent a heartbeat within timeout."""
    return core.clean(timeout_min)


if __name__ == "__main__":
    mcp.run()
