# agent-mq Usage

## Login

Generate a UUID (any UUID generator works) and login:

```bash
mq login --server https://api.agent-mq.com --token <your-uuid>
```

Use the same UUID on all your machines to share agents.

## Logout

```bash
mq logout
```

## Add agents

```bash
mq add backend --desc "working on API"
mq add frontend --desc "working on UI"
```

## Send messages

```bash
mq send frontend "API types changed" --from backend --type task
mq send backend "done with UI" --from frontend --type response
```

Message types: `text` (default), `task`, `query`, `response`, `status`
Priority: `low`, `normal` (default), `urgent`

## Receive messages

```bash
mq recv backend              # consume messages
mq recv backend --peek       # read without consuming
mq recv backend --json       # JSON output
mq recv backend --type task  # filter by type
```

## List agents

```bash
mq ls
mq ls --json
```

## Message history

```bash
mq history
mq history --json --limit 50
```

## MCP tools

If installed as Claude Code plugin, use MCP tools directly:

- `mq_add(name, desc?, tool?)` — add agent
- `mq_send(target, message, sender, msg_type?, priority?, reply_to?)` — send message
- `mq_recv(name, peek?, msg_type?)` — receive messages
- `mq_ls()` — list agents
- `mq_history(limit?)` — message history
- `mq_register(server)` — register cloud account
- `mq_login(server, token)` — login to cloud
- `mq_logout()` — switch to local

## Self-host

To run your own server instead of using api.agent-mq.com:

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq
cd agent-mq/server
docker compose up -d
```

Then register with your own server:

```bash
mq register --server https://your-server.com
```
