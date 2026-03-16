---
name: mq
description: "Message queue for cross-session communication between AI coding assistants. Use when you need to: send messages or tasks to another AI session, check for incoming messages, list running agents, or view message history."
license: MIT
metadata:
  author: farmer
  version: "0.1.6"
  repository: "https://github.com/bababoi-bibilabu/agent-mq"
---

# agent-mq — Inter-Agent Message Queue

AI coding agents communicate through a message queue. Each agent has a name and can send/receive messages.

## MCP Tools

- `mq_add(name, desc?, tool?)` — add an agent
- `mq_send(target, message, sender, msg_type?, priority?, reply_to?)` — send a message
- `mq_recv(name, peek?, msg_type?)` — receive messages
- `mq_ls()` — list agents
- `mq_history(limit?)` — view message history
- `mq_login(token, server?)` — login to server
- `mq_logout()` — disconnect

## Quick Start

```
mq_login(token: "your-uuid")
mq_add(name: "backend", desc: "working on API")
mq_send(target: "frontend", message: "API types changed", sender: "backend", msg_type: "task")
mq_recv(name: "frontend")
mq_ls()
```

## Message Types & Priority

**Types:** `text` (default), `task`, `query`, `response`, `status`
**Priority:** `low`, `normal` (default), `urgent`

## Message Format

```json
{
  "id": "msg-uuid",
  "from": "sender-name",
  "to": "receiver-name",
  "payload": "message text",
  "type": "task",
  "priority": "normal",
  "ts": "2026-03-15T00:00:00Z"
}
```

## Key Properties

- **Name-based routing**: send and receive by agent name
- **Consume-on-read**: messages removed from inbox when read; use `peek: true` to keep them
- **UUID-based isolation**: agents under the same token share a namespace; different tokens are invisible to each other
