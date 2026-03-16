#!/usr/bin/env python3
"""agent-mq MCP server — message queue tools for AI coding assistants."""

from mcp.server.fastmcp import FastMCP

import core

mcp = FastMCP("agent-mq", json_response=True)


@mcp.tool()
def mq_add(name: str, desc: str = "", tool: str = "claude-code") -> dict:
    """Add this agent to the message queue."""
    return core.add(name, desc, tool)


@mcp.tool()
def mq_send(target: str, message: str, sender: str, msg_type: str = "text", priority: str = "normal", reply_to: str = "") -> dict:
    """Send a message to a target agent by name."""
    return core.send(target, message, sender, msg_type, priority, reply_to or None)


@mcp.tool()
def mq_recv(name: str, peek: bool = False, msg_type: str = "") -> list:
    """Check inbox for messages. Consumed on read unless peek=True."""
    return core.recv(name, peek, msg_type or None)


@mcp.tool()
def mq_ls() -> list:
    """List all registered agents."""
    return core.ls()


@mcp.tool()
def mq_history(limit: int = 20) -> list:
    """View delivered message history."""
    return core.history(limit)


@mcp.tool()
def mq_login(server: str, token: str) -> dict:
    """Login to a cloud server with an existing token."""
    core.save_config({"mode": "cloud", "server": server.rstrip("/"), "token": token})
    return {"status": "ok", "mode": "cloud", "server": server}


@mcp.tool()
def mq_logout() -> dict:
    """Switch back to local mode."""
    core.save_config({"mode": "local", "server": "", "token": ""})
    return {"status": "ok", "mode": "local"}


if __name__ == "__main__":
    mcp.run()
