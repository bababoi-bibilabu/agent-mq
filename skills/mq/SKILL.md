---
name: mq
description: "File-based message queue for cross-session communication between AI coding assistants. Use when you need to: send messages or tasks to another AI session, check for incoming messages, list running sessions, coordinate work across multiple sessions, broadcast to all sessions, or set up recurring message polling. Works with Claude Code, Codex, and any CLI-based AI tool."
license: MIT
compatibility: "Requires Python 3.8+. Works with Claude Code, Codex, and any agent that can run bash."
metadata:
  author: farmer
  version: "0.1.0"
  repository: "https://github.com/user/agent-mq"
---

# agent-mq — Inter-Session Message Queue

AI coding sessions communicate through a file-based message queue. Each session has a UUID, an inbox directory, and a heartbeat. Messages are JSON files written atomically (`.tmp` then `mv`).

Script: `${SKILL_DIR}/scripts/mq.py` | Alias: `mq`

## Quick Start

### 1. Get your session ID

**Claude Code:**
```bash
SESSION_ID=$(basename $(ls -t ~/.claude/projects/$(pwd | tr '/' '-')/*.jsonl 2>/dev/null | head -1) .jsonl)
```

**Codex:**
```bash
SESSION_ID=$(uuidgen || python3 -c "import uuid; print(uuid.uuid4())")
```

### 2. Register

```bash
mq register $SESSION_ID --alias "my-name" --desc "what this session does" --tool claude-code
```

Pick an alias that identifies your role. The `--tool` flag identifies which AI tool you are (claude-code, codex, cursor, etc.).

### 3. Set up polling

**Claude Code** — use CronCreate to poll every 5 minutes:
```
Prompt: |
  MQ poll for session {SESSION_ID}:
  1. mq heartbeat {SESSION_ID}
  2. mq recv {SESSION_ID} --json
  3. Process each message: execute tasks, answer questions, or reply
  4. To reply: mq send {sender_uuid} "response" --from {SESSION_ID} --reply-to {msg_id}
  5. No messages → do nothing
```

**Codex** — run heartbeat and check inbox periodically during work.

## Commands

| Command | What it does |
|---------|-------------|
| `mq register <id> --alias NAME --desc DESC --tool TOOL` | Register this session |
| `mq send <target> "msg" --from <me>` | Send message (target can be UUID or alias) |
| `mq send <target> "msg" --from <me> --type task --priority urgent` | Send typed, prioritized message |
| `mq recv <id> [--peek] [--json] [--type TYPE]` | Read inbox (filter by type) |
| `mq broadcast "msg" --from <me>` | Send to all alive sessions |
| `mq ls [--json] [--alive]` | List sessions with status |
| `mq resolve <alias>` | Look up session UUID by alias |
| `mq status` | Quick overview: sessions, pending messages |
| `mq heartbeat <id>` | Update heartbeat timestamp |
| `mq history [--limit 20] [--json]` | View delivered messages |
| `mq clean [--timeout 10]` | Remove stale sessions |
| `mq auto-register [--alias NAME]` | Auto-detect session ID and register |

## Sending Messages

You can send by **UUID** or by **alias** (auto-resolved):

```bash
mq ls                                              # see all sessions
mq send worker-1 "build the auth module" --from $SESSION_ID --type task
mq send <uuid> "what's the indexer status?" --from $SESSION_ID --type query
```

## Message Types & Priority

**Types:** `text` (default), `task`, `query`, `response`, `status`
**Priority:** `low`, `normal` (default), `urgent`

```bash
mq send target "deploy to staging" --from $ME --type task --priority urgent
```

## Broadcast

Send a message to all alive sessions at once:

```bash
mq broadcast "switching to feature branch v2" --from $SESSION_ID --type status
```

## Message Format

`mq recv --json` returns:

```json
[
  {
    "id": "msg-uuid",
    "from": "sender-uuid",
    "to": "my-uuid",
    "payload": "message text",
    "type": "task",
    "priority": "normal",
    "ts": "2026-03-12T00:00:00Z",
    "reply_to": "optional-parent-msg-uuid",
    "_sender_alias": "sender-name"
  }
]
```

## Key Properties

- **Alias routing**: `send` accepts alias names — resolved to UUID automatically
- **Atomic writes**: `.tmp` then `mv` prevents reading partial messages
- **Consume-on-read**: `recv` moves messages to `done/`; use `--peek` to leave them
- **Heartbeat**: 10 min timeout marks session as stale
- **Cross-tool**: Works with any AI coding assistant that can run bash
- **Zero dependencies**: Pure Python 3, no packages needed
