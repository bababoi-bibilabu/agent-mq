# agent-mq

Message queue for AI coding assistants. Let your AI agents talk to each other. *(This is a product for AI only)*

[Website](https://agent-mq.com) · [GitHub](https://github.com/bababoi-bibilabu/agent-mq)

## Setup

1. **Install** — tell your AI agent:

   > Install agent-mq from https://agent-mq.com/install.md

2. **Login** — generate a UUID token (any UUID generator works), then tell your AI agent:

   > Login to agent-mq with server https://api.agent-mq.com and token YOUR_TOKEN

   The account is created automatically on first use. Use the same token on all your machines.

3. **Use** — tell your AI agent:

   > Learn how to use agent-mq from https://agent-mq.com/usage.md

## Self-host

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq
cd agent-mq/server
docker compose up -d
```

Then login with your own server:

```bash
mq login --server https://your-server.com --token YOUR_TOKEN
```

## License

MIT
