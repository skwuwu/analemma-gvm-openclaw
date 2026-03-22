#!/usr/bin/env bash
# Setup for live use-case demo
# Loads github + slack + web-browsing rulesets and starts the proxy.
#
# Usage:
#   bash demo/setup-live-demo.sh [--proxy-path PATH]
#
# After running this, start the demo:
#   python demo/live-usecase-demo.py --scenario all

set -euo pipefail

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
RULESETS_DIR="$REPO_DIR/rulesets"

# Find GVM proxy binary
PROXY_BIN=""
if [ "${1:-}" = "--proxy-path" ] && [ -n "${2:-}" ]; then
    PROXY_BIN="$2"
elif command -v gvm-proxy &>/dev/null; then
    PROXY_BIN="gvm-proxy"
elif [ -f "$HOME/Analemma-GVM/target/release/gvm-proxy" ]; then
    PROXY_BIN="$HOME/Analemma-GVM/target/release/gvm-proxy"
else
    # Try common Windows path
    WIN_PATH="$(echo "$USERPROFILE" 2>/dev/null || echo "")/OneDrive/바탕 화면/Analemma-GVM/target/release/gvm-proxy.exe"
    if [ -f "$WIN_PATH" ]; then
        PROXY_BIN="$WIN_PATH"
    fi
fi

if [ -z "$PROXY_BIN" ]; then
    echo -e "${RED}Error: gvm-proxy not found.${NC}"
    echo "Build it:  cd Analemma-GVM && cargo build --release"
    echo "Or specify: bash $0 --proxy-path /path/to/gvm-proxy"
    exit 1
fi

echo -e "${BOLD}${CYAN}Analemma GVM -- Live Demo Setup${NC}"
echo ""

# Find or create config dir
CONFIG_DIR=""
for dir in "$HOME/Analemma-GVM/config" "$REPO_DIR/../Analemma-GVM/config" "./config"; do
    if [ -d "$dir" ]; then
        CONFIG_DIR="$(cd "$dir" && pwd)"
        break
    fi
done

if [ -z "$CONFIG_DIR" ]; then
    CONFIG_DIR="$REPO_DIR/config"
    mkdir -p "$CONFIG_DIR"
    echo -e "${YELLOW}Created config dir: $CONFIG_DIR${NC}"
fi

echo -e "  Config dir: ${DIM}$CONFIG_DIR${NC}"
echo -e "  Rulesets:   ${DIM}$RULESETS_DIR${NC}"
echo -e "  Proxy:      ${DIM}$PROXY_BIN${NC}"
echo ""

# Build SRR: _default + github + slack + web-browsing
SRR_FILE="$CONFIG_DIR/srr_network.toml"

echo -e "${YELLOW}Building SRR ruleset...${NC}"

{
    echo "# GVM SRR Rules (live demo)"
    echo "# Generated: $(date -Iseconds)"
    echo "# Rulesets: _default + github + slack + web-browsing"
    echo ""

    for ruleset in _default.toml github.toml slack.toml web-browsing.toml; do
        src="$RULESETS_DIR/$ruleset"
        if [ -f "$src" ]; then
            echo ""
            echo "# -- $ruleset --"
            cat "$src"
            echo -e "  ${GREEN}+${NC} $ruleset"
        else
            echo -e "  ${YELLOW}?${NC} $ruleset (not found, skipping)"
        fi
    done
} > "$SRR_FILE"

echo -e "${GREEN}SRR written: $SRR_FILE${NC}"
echo ""

# Check if proxy is already running
if curl -sf http://127.0.0.1:8080/gvm/health > /dev/null 2>&1; then
    echo -e "${GREEN}Proxy already running. Reloading rules...${NC}"
    curl -sf -X POST http://127.0.0.1:8080/gvm/reload | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print(f'  Rules loaded: {d.get(\"rules\", \"?\")}'  )
except: print('  (reload response not JSON)')
" 2>/dev/null || echo "  (reload call failed)"
    echo ""
    echo -e "${GREEN}Ready. Run the demo:${NC}"
    echo -e "  python demo/live-usecase-demo.py --scenario all"
    exit 0
fi

# Find proxy config
PROXY_CONFIG=""
for cfg in "$CONFIG_DIR/proxy.toml" "$HOME/Analemma-GVM/config/proxy.toml"; do
    if [ -f "$cfg" ]; then
        PROXY_CONFIG="$cfg"
        break
    fi
done

if [ -z "$PROXY_CONFIG" ]; then
    echo -e "${RED}Warning: proxy.toml not found. Proxy may use defaults.${NC}"
    PROXY_ARGS=""
else
    PROXY_ARGS="--config $PROXY_CONFIG"
fi

# Start proxy
echo -e "${YELLOW}Starting GVM proxy...${NC}"
$PROXY_BIN $PROXY_ARGS &
PROXY_PID=$!
echo -e "  PID: $PROXY_PID"

# Wait for health
for i in $(seq 1 15); do
    if curl -sf http://127.0.0.1:8080/gvm/health > /dev/null 2>&1; then
        echo -e "${GREEN}Proxy is healthy.${NC}"
        break
    fi
    sleep 0.5
done

if ! curl -sf http://127.0.0.1:8080/gvm/health > /dev/null 2>&1; then
    echo -e "${RED}Proxy failed to start. Check logs.${NC}"
    kill $PROXY_PID 2>/dev/null
    exit 1
fi

echo ""
echo -e "${GREEN}${BOLD}Setup complete.${NC}"
echo ""
echo -e "  Run the demo:"
echo -e "    ${CYAN}python demo/live-usecase-demo.py --scenario all${NC}"
echo ""
echo -e "  Run individual scenarios:"
echo -e "    ${CYAN}python demo/live-usecase-demo.py --scenario 1${NC}  # GitHub Code Review"
echo -e "    ${CYAN}python demo/live-usecase-demo.py --scenario 2${NC}  # Multi-Service"
echo -e "    ${CYAN}python demo/live-usecase-demo.py --scenario 3${NC}  # Security Audit"
echo ""
echo -e "  Stop proxy when done:"
echo -e "    ${DIM}kill $PROXY_PID${NC}"
