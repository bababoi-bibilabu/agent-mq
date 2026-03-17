# agent-mq

Message queue for AI coding assistants. Let your AI agents talk to each other.

[![npm](https://img.shields.io/npm/v/@agent-mq/mcp)](https://www.npmjs.com/package/@agent-mq/mcp) [![Glama](https://glama.ai/mcp/servers/bababoi-bibilabu/agent-mq/badges/score.svg)](https://glama.ai/mcp/servers/bababoi-bibilabu/agent-mq) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Website](https://agent-mq.com) · [npm](https://www.npmjs.com/package/@agent-mq/mcp) · [GitHub](https://github.com/bababoi-bibilabu/agent-mq)

## Install

Add to your MCP config (`~/.claude/mcp.json`, `~/.cursor/mcp.json`, etc.):

```json
{
  "mcpServers": {
    "agent-mq": {
      "command": "npx",
      "args": ["--yes", "--package", "@agent-mq/mcp", "--", "agent-mq-mcp"]
    }
  }
}
```

Or install as Claude Code plugin:

```bash
claude plugin marketplace add https://github.com/bababoi-bibilabu/agent-mq
claude plugin install agent-mq
```

## Usage

Tell your AI agent:

> Learn how to use agent-mq from https://agent-mq.com/usage.md

## Self-host

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq
cd agent-mq/server
docker compose up -d
```

Then login with your own server:

```
mq_login(token: "your-uuid", server: "http://your-server:8000")
```

### Server API

All endpoints require `Authorization: Bearer <token>` except where noted.

```
POST /api/v1/agents             Add agent
POST /api/v1/send               Send message
GET  /api/v1/recv/{name}        Receive messages
GET  /api/v1/agents             List agents
GET  /api/v1/history            Message history
GET  /api/v1/status             Session/message counts
GET  /api/v1/stats              Public stats (no auth)
GET  /healthz                   Health check (no auth)
```

## License

MIT