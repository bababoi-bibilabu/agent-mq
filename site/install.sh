#!/usr/bin/env bash
# agent-mq installer — curl -fsSL https://agent-mq.com/install.sh | bash
set -euo pipefail

REPO="https://github.com/bababoi-bibilabu/agent-mq"
INSTALL_DIR="$HOME/.agent-mq"

echo "agent-mq installer"
echo "==================="

# Clone or update
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --quiet
else
    echo "Cloning agent-mq..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
fi

# Run the repo's install script
bash "$INSTALL_DIR/install.sh"
