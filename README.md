# agent-mq

Message queue for AI coding assistants. Enables cross-session communication between Claude Code, Codex, Cursor, and any CLI-based AI tool.

## Why

Multiple AI coding sessions can't talk to each other. agent-mq gives them a shared message queue — no servers needed, just files.

## Install

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq ~/.agent-mq
cd ~/.agent-mq && bash install.sh
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
mq register --server https://mq.example.com    # create account, get token
mq login --server https://mq.example.com --token <token>  # reconnect
mq add backend                                  # now uses cloud
mq logout                                       # back to local
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
Client ──HTTP──> Server (FastAPI + RocksDB)
                   ├── POST /api/v1/register    Create account
                   ├── POST /api/v1/agents      Add agent (auth required)
                   ├── POST /api/v1/send        Send message (auth required)
                   ├── GET  /api/v1/recv/{name}  Receive messages (auth required)
                   └── GET  /api/v1/agents      List agents (auth required)
```

- **Token auth**: Register to get a token. All operations scoped to your account.
- **Data isolation**: Each user's agents and messages are completely separate.
- **Rate limiting**: Per-IP QPS limit. Configurable message size cap.
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

## License

MIT
