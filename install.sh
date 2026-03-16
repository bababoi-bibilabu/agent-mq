#!/usr/bin/env bash
# agent-mq installer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MQ_SCRIPT="$SCRIPT_DIR/skills/mq/scripts/mq.py"
VERSION="0.1.0"

echo "agent-mq v${VERSION} installer"
echo "================================"

# ── Create 'mq' command ──
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/mq" << EOF
#!/usr/bin/env bash
exec python3 "$MQ_SCRIPT" "\$@"
EOF
chmod +x "$BIN_DIR/mq"
echo "[ok] mq command installed to $BIN_DIR/mq"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "[!!] $BIN_DIR is not in your PATH. Add to your shell profile:"
    echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Done ──
echo ""
echo "================================"
echo "Installation complete."
echo ""
echo "Next: generate a UUID and login:"
echo "  mq login --server https://api.agent-mq.com --token YOUR_UUID"
echo ""
echo "To add MCP server to your AI tool, add to its MCP config:"
echo "  {"
echo "    \"mcpServers\": {"
echo "      \"agent-mq\": {"
echo "        \"command\": \"python3\","
echo "        \"args\": [\"$MQ_SCRIPT\"]"
echo "      }"
echo "    }"
echo "  }"
echo ""
echo "Or install as Claude Code plugin:"
echo "  claude plugin marketplace add https://github.com/bababoi-bibilabu/agent-mq"
echo "  claude plugin install agent-mq"
