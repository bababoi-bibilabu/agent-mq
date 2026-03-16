# agent-mq

[Website](https://agent-mq.com) · [GitHub](https://github.com/bababoi-bibilabu/agent-mq)

Message queue for AI coding assistants. Enables cross-agent communication between Claude Code, Codex, Cursor, and any CLI-based AI tool.

## Install

```bash
curl -fsSL https://agent-mq.com/install.sh | bash
```

## Usage

```bash
mq add backend --desc "working on API"
mq add frontend --desc "working on UI"

mq send frontend "API types changed" --from backend --type task
mq recv frontend --json
mq ls
mq history
```

## Cloud Mode

```bash
mq register --server https://api.agent-mq.com    # create account, get token
mq login --server https://api.agent-mq.com --token <token>  # reconnect
mq add backend                                    # now uses cloud
mq logout                                         # back to local
```

## Architecture

### Local Mode (default)

```
~/.claude/mq/
├── registry/     Agent metadata (JSON per agent)
├── inbox/<name>/ Per-agent message directories
└── done/         Consumed messages
```

Messages written atomically (`.tmp` → `mv`). Consume-on-read by default.

### Cloud Mode

```
Client ──HTTP──> Server (FastAPI + SQLite)
                   ├── POST /api/v1/register       Create account (no auth)
                   ├── POST /api/v1/agents         Add agent
                   ├── POST /api/v1/send           Send message
                   ├── GET  /api/v1/recv/{name}    Receive messages
                   ├── GET  /api/v1/agents         List agents
                   ├── GET  /api/v1/agents/{name}  Get agent details
                   ├── GET  /api/v1/status         Session/message counts
                   ├── GET  /api/v1/history        Message history
                   ├── GET  /api/v1/analytics/summary  Usage stats
                   └── GET  /healthz               Health check (no auth)
```

- **Token auth**: Register to get a token. All operations scoped to your account.
- **Data isolation**: Each user's agents and messages are completely separate.
- **Rate limiting**: Per-IP QPS limit via slowapi. 10KB message size cap.
- **No outbound requests**: Server never calls external URLs.

## MCP Tools

| Tool | Description |
|------|-------------|
| `mq_add` | Add an agent |
| `mq_send` | Send a message |
| `mq_recv` | Receive messages |
| `mq_ls` | List agents |
| `mq_history` | View message history |
| `mq_register` | Register cloud account |
| `mq_login` | Login to cloud server |
| `mq_logout` | Switch to local mode |

## Self-host

```bash
cd server
docker compose up -d
```

## License

MIT
