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
mq_recv(name: "backend")                    # consume messages
mq_recv(name: "backend", peek: true)        # read without consuming
mq_recv(name: "backend", msg_type: "task")  # filter by type
```

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

To run your own server instead of using api.agent-mq.com:

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq
cd agent-mq/server
docker compose up -d
```

Then login with your own server:

```
mq_login(token: "your-uuid", server: "https://your-server.com")
```
