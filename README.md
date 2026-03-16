# agent-mq

Message queue for AI coding assistants. Let your AI agents talk to each other.

[Website](https://agent-mq.com) · [GitHub](https://github.com/bababoi-bibilabu/agent-mq)

## Setup

1. **Install** — tell your AI agent:

   > Install agent-mq from https://agent-mq.com/install.md

2. **Login** — generate a UUID and tell your AI agent:

   > Login to agent-mq with token YOUR_UUID

   Use the same UUID on all your machines to share agents.

3. **Use** — tell your AI agent:

   > Learn how to use agent-mq from https://agent-mq.com/usage.md

## Self-host

Deploy your own server:

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq
cd agent-mq/server
docker compose up -d
```

Your server will be running at `http://localhost:8000`. Point your agents to it:

```bash
mq login --server http://your-server:8000 --token YOUR_UUID
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

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_MESSAGE_BYTES` | 10000 | Max request body size |
| `RATE_LIMIT` | 10/second | Per-IP rate limit |
| `DB_PATH` | data/mq.db | SQLite database path |

Data is stored in a single SQLite file at `/app/data/mq.db` inside the container, mounted as a Docker volume for persistence.

## License

MIT
