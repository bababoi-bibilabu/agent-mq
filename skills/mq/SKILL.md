---
name: mq
description: "Message queue for cross-session communication between AI coding assistants. Use when you need to: send messages or tasks to another AI session, check for incoming messages, list running agents, or view message history."
license: MIT
compatibility: "Requires Python 3.8+. Works with Claude Code, Codex, Cursor, and any agent that can run bash."
metadata:
  author: farmer
  version: "0.1.0"
  repository: "https://github.com/bababoi-bibilabu/agent-mq"
---

# agent-mq — Inter-Agent Message Queue

AI coding agents communicate through a message queue. Each agent has a name, an inbox directory, and can send/receive messages.

Script: `${SKILL_DIR}/scripts/mq.py` | Alias: `mq`

## Quick Start

```bash
mq add backend --desc "working on API"
mq send backend "please review the auth module" --from frontend --type task
mq recv backend --json
mq ls
```

## Commands

| Command | What it does |
|---------|-------------|
| `mq add <name> [--desc DESC] [--tool TOOL]` | Add this agent to the queue |
| `mq send <target> "msg" --from <me>` | Send a message |
| `mq send <target> "msg" --from <me> --type task --priority urgent` | Send typed, prioritized message |
| `mq recv <name> [--peek] [--json] [--type TYPE]` | Read inbox (filter by type) |
| `mq ls [--json]` | List agents with pending message counts |
| `mq history [--limit 20] [--json]` | View delivered messages |

## Cloud Mode

```bash
mq register --server https://mq.example.com    # create account
mq login --server https://mq.example.com --token <token>  # reconnect
mq logout                                       # back to local
```

## Message Types & Priority

**Types:** `text` (default), `task`, `query`, `response`, `status`
**Priority:** `low`, `normal` (default), `urgent`

## Message Format

`mq recv --json` returns:

```json
[
  {
    "id": "msg-uuid",
    "from": "sender-name",
    "to": "receiver-name",
    "payload": "message text",
    "type": "task",
    "priority": "normal",
    "ts": "2026-03-15T00:00:00Z",
    "reply_to": "optional-parent-msg-uuid"
  }
]
```

## Key Properties

- **Name-based routing**: send and receive by agent name
- **Atomic writes**: `.tmp` then `mv` prevents reading partial messages
- **Consume-on-read**: `recv` moves messages to `done/`; use `--peek` to leave them
- **Zero dependencies**: Pure Python 3 for local mode
