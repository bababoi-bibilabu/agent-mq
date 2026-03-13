#!/usr/bin/env bash
# agent-mq installer
# Detects available AI tools and installs accordingly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MQ_SCRIPT="$SCRIPT_DIR/skills/mq/scripts/mq.py"
VERSION="0.1.0"

echo "agent-mq v${VERSION} installer"
echo "================================"

# Make core script executable
chmod +x "$MQ_SCRIPT"

# ── Create 'mq' alias ──
# Add to PATH via symlink in ~/.local/bin
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/mq" << EOF
#!/usr/bin/env bash
exec python3 "$MQ_SCRIPT" "\$@"
EOF
chmod +x "$BIN_DIR/mq"
echo "[ok] mq command installed to $BIN_DIR/mq"

# Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "[!!] $BIN_DIR is not in your PATH. Add this to your shell profile:"
    echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Claude Code plugin ──
INSTALLED_CC=false
if command -v claude &>/dev/null; then
    echo ""
    echo "Claude Code detected."

    # Check if already installed as plugin
    PLUGIN_DIR="$HOME/.claude/plugins"
    if [ -d "$PLUGIN_DIR" ]; then
        echo "  To install as plugin, run:"
        echo "    claude plugin add $SCRIPT_DIR"
        echo "  Or manually link the skill:"
        echo "    ln -sf $SCRIPT_DIR/skills/mq ~/.claude/skills/mq"
    fi

    # Also ensure skill is available directly
    SKILL_TARGET="$HOME/.claude/skills/mq"
    if [ ! -e "$SKILL_TARGET" ]; then
        mkdir -p "$HOME/.claude/skills"
        ln -sf "$SCRIPT_DIR/skills/mq" "$SKILL_TARGET"
        echo "[ok] Claude Code skill linked to $SKILL_TARGET"
        INSTALLED_CC=true
    else
        echo "[ok] Claude Code skill already exists at $SKILL_TARGET"
        INSTALLED_CC=true
    fi
fi

# ── Codex skill ──
INSTALLED_CODEX=false
if command -v codex &>/dev/null; then
    echo ""
    echo "Codex detected."

    CODEX_SKILL_DIR="$HOME/.agents/skills/mq"
    if [ ! -e "$CODEX_SKILL_DIR" ]; then
        mkdir -p "$HOME/.agents/skills"
        ln -sf "$SCRIPT_DIR/skills/mq" "$CODEX_SKILL_DIR"
        echo "[ok] Codex skill linked to $CODEX_SKILL_DIR"
        INSTALLED_CODEX=true
    else
        echo "[ok] Codex skill already exists at $CODEX_SKILL_DIR"
        INSTALLED_CODEX=true
    fi
fi

# ── Summary ──
echo ""
echo "================================"
echo "Installation complete."
echo ""
echo "Quick start:"
echo "  mq status              # check system status"
echo "  mq auto-register       # register current session"
echo "  mq ls                  # list all sessions"
echo "  mq send <target> 'hi' --from <me>  # send a message"
echo ""

if ! $INSTALLED_CC && ! $INSTALLED_CODEX; then
    echo "No AI tool detected (claude, codex)."
    echo "The 'mq' command is still available for manual use."
    echo "Install skills manually:"
    echo "  Claude Code: ln -sf $SCRIPT_DIR/skills/mq ~/.claude/skills/mq"
    echo "  Codex:       ln -sf $SCRIPT_DIR/skills/mq ~/.agents/skills/mq"
fi
