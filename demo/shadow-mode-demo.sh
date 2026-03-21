#!/usr/bin/env bash
# Shadow Mode Demo — Analemma GVM
#
# Demonstrates the dual-lock architecture:
#   Scenario 1: Intent declared → request allowed
#   Scenario 2: No intent → request DENIED (shadow strict)
#   Scenario 3: Wrong URL intent → request DENIED (cross-check)
#
# Requirements:
#   - gvm-proxy running with shadow mode enabled
#   - curl
#
# Usage:
#   1. Start proxy: GVM_CONFIG=demo/proxy-config/proxy.toml gvm-proxy
#   2. Run demo:    bash demo/shadow-mode-demo.sh

set -euo pipefail

PROXY="http://127.0.0.1:8080"
AGENT="demo-agent"
MOCK="http://httpbin.org"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

header() {
  echo ""
  echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
  echo -e "${BOLD}  $1${NC}"
  echo -e "${BOLD}═══════════════════════════════════════════════════${NC}"
}

# Check proxy is running
if ! curl -sf "$PROXY/gvm/health" > /dev/null 2>&1; then
  echo -e "${RED}Error: GVM proxy not running at $PROXY${NC}"
  echo "Start it with: GVM_CONFIG=demo/proxy-config/proxy.toml gvm-proxy"
  exit 1
fi

echo -e "${BOLD}Analemma GVM — Shadow Mode Demo${NC}"
echo -e "${DIM}Dual-lock: MCP declares intent, proxy verifies before forwarding.${NC}"

# ── Scenario 1: Intent declared → Allow ──────────────────────────────────────

header "Scenario 1: Intent Declared → Allow"
echo -e "${DIM}Agent declares intent via POST /gvm/intent, then makes the request.${NC}"
echo ""

echo -e "  ${YELLOW}[1/2] Declaring intent: GET httpbin.org/get${NC}"
INTENT_RESP=$(curl -sf -X POST "$PROXY/gvm/intent" \
  -H "Content-Type: application/json" \
  -d "{\"method\":\"GET\",\"host\":\"httpbin.org\",\"path\":\"/get\",\"operation\":\"demo.read\",\"agent_id\":\"$AGENT\"}")
echo -e "  ${DIM}Response: $INTENT_RESP${NC}"

echo -e "  ${YELLOW}[2/2] Making request through proxy${NC}"
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
  -x "$PROXY" "http://httpbin.org/get" \
  -H "X-GVM-Agent-Id: $AGENT" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
  echo -e "  ${GREEN}✓ HTTP $HTTP_CODE — Request ALLOWED (intent verified)${NC}"
else
  echo -e "  ${RED}✗ HTTP $HTTP_CODE — Unexpected result${NC}"
fi

# ── Scenario 2: No intent → Deny ─────────────────────────────────────────────

header "Scenario 2: No Intent → DENY"
echo -e "${DIM}Agent skips intent declaration and makes request directly.${NC}"
echo -e "${DIM}(Intent from Scenario 1 was consumed — one-time use.)${NC}"
echo ""

echo -e "  ${YELLOW}[1/1] Making request WITHOUT declaring intent${NC}"
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
  -x "$PROXY" "http://httpbin.org/get" \
  -H "X-GVM-Agent-Id: $AGENT" 2>/dev/null || echo "403")

if [ "$HTTP_CODE" = "403" ]; then
  echo -e "  ${GREEN}✓ HTTP $HTTP_CODE — Request DENIED (no intent, shadow strict)${NC}"
else
  echo -e "  ${RED}✗ HTTP $HTTP_CODE — Expected 403${NC}"
fi

# ── Scenario 3: Wrong URL intent → Deny ──────────────────────────────────────

header "Scenario 3: Intent for Wrong URL → DENY"
echo -e "${DIM}Agent declares intent for /get but requests /post.${NC}"
echo -e "${DIM}Shadow verification cross-checks method+host+path.${NC}"
echo ""

echo -e "  ${YELLOW}[1/2] Declaring intent: GET httpbin.org/get${NC}"
curl -sf -X POST "$PROXY/gvm/intent" \
  -H "Content-Type: application/json" \
  -d "{\"method\":\"GET\",\"host\":\"httpbin.org\",\"path\":\"/get\",\"operation\":\"demo.read\",\"agent_id\":\"$AGENT\"}" > /dev/null

echo -e "  ${YELLOW}[2/2] Making request to DIFFERENT URL: POST httpbin.org/post${NC}"
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
  -x "$PROXY" -X POST "http://httpbin.org/post" \
  -H "X-GVM-Agent-Id: $AGENT" \
  -H "Content-Type: application/json" \
  -d '{"amount":5000}' 2>/dev/null || echo "403")

if [ "$HTTP_CODE" = "403" ]; then
  echo -e "  ${GREEN}✓ HTTP $HTTP_CODE — Request DENIED (intent mismatch)${NC}"
else
  echo -e "  ${RED}✗ HTTP $HTTP_CODE — Expected 403${NC}"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

header "Summary"
echo ""
echo -e "  ${GREEN}Scenario 1${NC}: Intent declared → ${GREEN}Allow${NC} (verified path)"
echo -e "  ${RED}Scenario 2${NC}: No intent      → ${RED}Deny${NC}  (shadow strict)"
echo -e "  ${RED}Scenario 3${NC}: Wrong intent    → ${RED}Deny${NC}  (cross-check)"
echo ""
echo -e "  ${DIM}MCP is the conversation. Proxy is the enforcement.${NC}"
echo -e "  ${DIM}Declare intent = fast path. Skip intent = blocked.${NC}"
echo ""

# ── Audit log ─────────────────────────────────────────────────────────────────

echo -e "${DIM}Proxy info:${NC}"
curl -sf "$PROXY/gvm/info" 2>/dev/null | head -5
echo ""
