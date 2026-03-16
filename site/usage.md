# agent-mq Usage

## Login

Generate a UUID and login:

```
mq_login(token: "your-uuid")
```

Use the same UUID on all your machines to share agents.

## Add agents

```
mq_add(name: "backend", desc: "working on API")
mq_add(name: "frontend", desc: "working on UI")
```

## Send messages

```
mq_send(target: "frontend", message: "API types changed", sender: "backend", msg_type: "task")
```

Message types: `text` (default), `task`, `query`, `response`, `status`
Priority: `low`, `normal` (default), `urgent`

## Receive messages

```
mq_recv()                          # all messages across all agents
mq_recv(name: "backend")           # only backend's messages
mq_recv(msg_type: "task")          # filter by type
```

Messages are consumed on read.

## Polling for messages

agent-mq does not push messages to agents. Set up periodic polling to check for new messages:

- **Claude Code**: Use CronCreate to poll every 5 minutes:
  ```
  Prompt: "Check for new messages with mq_recv() and process any tasks"
  ```
- **Other tools**: Schedule `mq_recv()` at your preferred interval.

## List agents

```
mq_ls()
```

## Message history

```
mq_history(limit: 50)
```

## Logout

```
mq_logout()
```

## Self-host

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq
cd agent-mq/server
docker compose up -d
```

Then login with your own server:

```
mq_login(token: "your-uuid", server: "https://your-server.com")
```
