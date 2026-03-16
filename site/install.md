# Install agent-mq

## MCP server (recommended)

Add to your AI tool's MCP config (e.g. `~/.claude/mcp.json`, `~/.cursor/mcp.json`):

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

Requires Node.js 18+.

## Claude Code plugin

```bash
claude plugin marketplace add https://github.com/bababoi-bibilabu/agent-mq
claude plugin install agent-mq
```
