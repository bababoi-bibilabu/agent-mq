# agent-mq

Message queue for AI coding assistants. Enables cross-session communication between Claude Code, Codex, and any CLI-based AI tool.

## Why

Multiple AI coding sessions can't talk to each other. agent-mq gives them a shared message queue — no servers, no dependencies, just files.

## Features

- **Cross-tool**: Claude Code, Codex, Cursor, or any tool that runs bash
- **Zero dependencies**: Pure Python 3, no packages needed
- **Alias routing**: Send by name, not UUID
- **Message types**: `text`, `task`, `query`, `response`, `status`
- **Priority**: `urgent`, `normal`, `low`
- **Broadcast**: Send to all alive sessions
- **Local + Cloud**: File-based by default, `mq login` to switch to cloud
- **Simple polling**: Agents poll at their own frequency, no held connections

## Install

**Claude Code:**
```bash
claude plugin install agent-mq
```

**Codex:**
```bash
$skill-installer agent-mq
```

**Manual:**
```bash
git clone <repo-url> ~/.agent-mq
cd ~/.agent-mq && bash install.sh
```

## Usage

```bash
mq register <session-id> --alias "backend" --desc "working on API"
mq send frontend "API types changed" --from <my-id> --type task
mq recv <my-id> --json
mq ls
mq broadcast "switching branch" --from <my-id> --type status
mq status
```

## Cloud Mode

```bash
mq login --server https://mq.example.com    # switch to cloud
mq status                                     # now uses server
mq logout                                     # back to local
```

## Architecture

### Local Mode (default)

```
~/.claude/mq/
├── registry/           Session metadata (JSON per session)
├── inbox/<uuid>/       Per-session message directories
└── done/               Consumed messages
```

Messages written atomically (`.tmp` → `mv`). Consume-on-read by default.

### Cloud Mode

```
Client ──HTTP──> Server (FastAPI + RocksDB)
                   ├── /api/v1/send         Authenticated API
                   ├── /api/v1/recv/{id}    Supports long poll (?wait=30)
                   └── /api/v1/analytics    Anonymous metadata only
```

- **Long poll**: `GET /api/v1/recv/{id}?wait=30` — server holds the connection until a message arrives or timeout. Near real-time without persistent connections.
- **No outbound requests**: Server never calls external URLs. Zero DoS/SSRF surface.
- **Analytics**: Event counts and tool distribution. Message content is never logged.

## License

MIT
