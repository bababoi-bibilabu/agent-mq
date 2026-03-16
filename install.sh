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

# ── Link skill for AI tools ──
if [ -d "$HOME/.claude" ]; then
    SKILL_TARGET="$HOME/.claude/skills/mq"
    if [ ! -e "$SKILL_TARGET" ]; then
        mkdir -p "$HOME/.claude/skills"
        ln -sf "$SCRIPT_DIR/skills/mq" "$SKILL_TARGET"
        echo "[ok] Claude Code skill linked"
    fi
fi

if [ -d "$HOME/.agents" ]; then
    SKILL_TARGET="$HOME/.agents/skills/mq"
    if [ ! -e "$SKILL_TARGET" ]; then
        mkdir -p "$HOME/.agents/skills"
        ln -sf "$SCRIPT_DIR/skills/mq" "$SKILL_TARGET"
        echo "[ok] Codex skill linked"
    fi
fi

# ── Done ──
echo ""
echo "================================"
echo "Installation complete."
echo ""
echo "Next: generate a UUID and login:"
echo "  mq login --server https://api.agent-mq.com --token YOUR_UUID"
echo ""
echo "Then:"
echo "  mq add backend"
echo "  mq send backend 'hi' --from frontend"
echo "  mq recv backend"
