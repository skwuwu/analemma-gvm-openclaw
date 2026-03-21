#!/usr/bin/env bash
# Analemma GVM — One-line install for OpenClaw
# Usage: curl -fsSL https://raw.githubusercontent.com/skwuwu/analemma-gvm-openclaw/master/install.sh | bash

set -euo pipefail

REPO="https://github.com/skwuwu/analemma-gvm-openclaw.git"
INSTALL_DIR="$HOME/.openclaw/skills/gvm-governance"
MCP_DIR="$INSTALL_DIR/mcp-server"

echo "Installing Analemma GVM for OpenClaw..."

# 1. Clone into OpenClaw skills directory
if [ -d "$INSTALL_DIR" ]; then
  echo "Updating existing installation..."
  cd "$INSTALL_DIR" && git pull --ff-only
else
  echo "Cloning repository..."
  git clone --depth 1 "$REPO" "$INSTALL_DIR"
fi

# 2. Build MCP server
echo "Building MCP server..."
cd "$MCP_DIR"
npm install --production 2>/dev/null
npm run build 2>/dev/null

# 3. Print config snippet
MCP_INDEX="$MCP_DIR/dist/index.js"
echo ""
echo "Done! Add this to your MCP config:"
echo ""
echo "  OpenClaw (~/.openclaw/openclaw.yaml):"
echo "    mcpServers:"
echo "      gvm-governance:"
echo "        command: node"
echo "        args: [\"$MCP_INDEX\"]"
echo ""
echo "  Claude Desktop (claude_desktop_config.json):"
echo "    {\"mcpServers\":{\"gvm-governance\":{\"command\":\"node\",\"args\":[\"$MCP_INDEX\"]}}}"
echo ""
echo "Then start the proxy: gvm-proxy"
