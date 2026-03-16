# Install agent-mq

## CLI

macOS / Linux:

```bash
curl -fsSL https://agent-mq.com/install.sh | bash
```

Windows:

```powershell
irm https://agent-mq.com/install.ps1 | iex
```

## MCP server

Requires: `pip install "mcp[fastmcp]"`

Add to your AI tool's MCP config (e.g. `~/.claude/mcp.json`, `~/.cursor/mcp.json`, etc.):

```json
{
  "mcpServers": {
    "agent-mq": {
      "command": "python3",
      "args": ["~/.agent-mq/skills/mq/scripts/mcp_server.py"]
    }
  }
}
```

## Claude Code plugin

```bash
claude plugin marketplace add https://github.com/bababoi-bibilabu/agent-mq
claude plugin install agent-mq
```

## Manual

```bash
git clone https://github.com/bababoi-bibilabu/agent-mq ~/.agent-mq
cd ~/.agent-mq && bash install.sh
```
