# MCP + OpenClaw Linux E2E Test Guide

Full pipeline: OpenClaw agent → MCP server → GVM proxy → CONNECT tunnel → external API.

## Prerequisites

```bash
# Ubuntu 22.04+ / Codespace
sudo apt-get update && sudo apt-get install -y build-essential pkg-config libssl-dev curl

# Rust (use 1.85 — 1.94 has ICE bug)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source ~/.cargo/env
rustup install 1.85.0 && rustup default 1.85.0

# Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# OpenClaw
npm install -g openclaw@latest

# Python (for uprobe test)
sudo apt-get install -y python3-requests
```

## Build

```bash
# Core proxy
git clone https://github.com/skwuwu/Analemma-GVM.git && cd Analemma-GVM
cargo build --release -j 2
# → target/release/gvm-proxy

# MCP server (prebuilt — no build needed)
cd ..
git clone https://github.com/skwuwu/analemma-gvm-openclaw.git
cd analemma-gvm-openclaw
# dist/ is prebuilt, but rebuild if needed:
# cd mcp-server && npm install && npm run build && cd ..
```

## Test 1: MCP gvm_fetch through CONNECT tunnel

Tests the full MCP → proxy → HTTPS pipeline.

```bash
# Terminal 1: Start proxy with llm-providers + github rulesets
cd ~/Analemma-GVM
cat rulesets/_default.toml > config/srr_network.toml 2>/dev/null || true

# Build SRR with rulesets
python3 -c "
import os
rulesets_dir = os.path.expanduser('~/analemma-gvm-openclaw/rulesets')
parts = []
for f in ['_default.toml', 'llm-providers.toml', 'github.toml', 'google-workspace.toml']:
    path = os.path.join(rulesets_dir, f)
    if os.path.exists(path):
        parts.append(f'# -- {f} --\n' + open(path).read())
open('config/srr_network.toml', 'w').write('\n'.join(parts))
print(f'Loaded {len(parts)} rulesets')
"

./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2
curl -s http://localhost:8080/gvm/health
echo ""

# Terminal 2: MCP server test — gvm_fetch via JSON-RPC
cd ~/analemma-gvm-openclaw
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gvm_policy_check","arguments":{"method":"GET","url":"https://api.github.com"}}}' \
  | node mcp-server/dist/index.js 2>/dev/null \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    if d.get('id') == 2:
        result = json.loads(d['result']['content'][0]['text'])
        print(f'Decision: {result.get(\"decision\", \"?\")}')
        print(f'SRR: {result.get(\"srr_decision\", \"?\")}')
"

# Expected: Decision: Allow

# Cleanup
kill $PROXY_PID 2>/dev/null
```

## Test 2: MCP gvm_select_rulesets + hot-reload

Tests ruleset selection → SRR file replacement → proxy hot-reload.

```bash
cd ~/Analemma-GVM
# Start with empty SRR (only _default)
cat ~/analemma-gvm-openclaw/rulesets/_default.toml > config/srr_network.toml
./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

# Before: gmail should be Default-to-Caution (Delay)
echo "Before ruleset:"
curl -s -X POST http://localhost:8080/gvm/check \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","target_host":"gmail.googleapis.com","target_path":"/gmail/v1/users/me/messages","operation":"test"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'  {d[\"decision\"]}')"

# Apply google-workspace ruleset via MCP
cd ~/analemma-gvm-openclaw
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gvm_select_rulesets","arguments":{"apply":["google-workspace"]}}}' \
  | GVM_CONFIG_DIR=~/Analemma-GVM/config node mcp-server/dist/index.js 2>/dev/null \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    if d.get('id') == 2:
        result = json.loads(d['result']['content'][0]['text'])
        print(f'Applied: {[a[\"name\"] for a in result.get(\"applied\",[])]}')"

# After: gmail read should be Allow
echo "After ruleset:"
curl -s -X POST http://localhost:8080/gvm/check \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","target_host":"gmail.googleapis.com","target_path":"/gmail/v1/users/me/messages","operation":"test"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'  {d[\"decision\"]}')"

echo "Gmail delete (should Deny):"
curl -s -X POST http://localhost:8080/gvm/check \
  -H "Content-Type: application/json" \
  -d '{"method":"DELETE","target_host":"gmail.googleapis.com","target_path":"/gmail/v1/users/me/messages/123","operation":"test"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'  {d[\"decision\"]}')"

# Expected: Before=Delay, After read=Allow, After delete=Deny

kill $PROXY_PID 2>/dev/null
```

## Test 3: OpenClaw agent through GVM proxy

Tests the real OpenClaw → HTTPS_PROXY → CONNECT tunnel → LLM API pipeline.

```bash
cd ~/Analemma-GVM

# Load llm-providers ruleset
python3 -c "
parts = []
for f in ['_default.toml', 'llm-providers.toml']:
    path = f'$HOME/analemma-gvm-openclaw/rulesets/{f}'
    import os; path = os.path.expanduser(f'~/analemma-gvm-openclaw/rulesets/{f}')
    if os.path.exists(path): parts.append(open(path).read())
open('config/srr_network.toml', 'w').write('\n'.join(parts))
"

> data/wal.log
./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

# Set API key (replace with your key)
export ANTHROPIC_API_KEY="sk-ant-..."  # or set in .env

# Run OpenClaw agent through proxy
export HTTPS_PROXY=http://127.0.0.1:8080
export HTTP_PROXY=http://127.0.0.1:8080

openclaw agent --local \
  --session-id "linux-e2e-test" \
  --message "Say hello in one sentence." \
  --timeout 30 2>&1 | grep -v "model-selection"

echo ""
echo "=== CONNECT log ==="
grep "CONNECT tunnel" /tmp/gvm-proxy.log 2>/dev/null || \
  grep "CONNECT" data/wal.log 2>/dev/null | head -3

# Expected: Agent responds + CONNECT api.anthropic.com logged

kill $PROXY_PID 2>/dev/null
```

## Test 4: Shadow Mode intent enforcement

Tests that requests without MCP intent declaration are blocked.

```bash
cd ~/Analemma-GVM

# Start proxy with Shadow Mode strict
GVM_SHADOW_MODE=strict ./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

# Register intent
echo "With intent:"
curl -s -X POST http://localhost:8080/gvm/intent \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","host":"api.github.com","path":"/","operation":"github.read","agent_id":"test"}' \
  | python3 -c "import sys,json; print(f'  registered: {json.loads(sys.stdin.read()).get(\"registered\")}')"

# Without intent (should be denied by Shadow strict)
echo "Without intent:"
HTTPS_PROXY=http://127.0.0.1:8080 python3 -c "
import requests
try:
    r = requests.get('https://httpbin.org/get', timeout=5)
    print(f'  Status: {r.status_code}')
except Exception as e:
    print(f'  Blocked: {e}')
" 2>&1

# Expected: With intent = registered, Without intent = blocked/403

kill $PROXY_PID 2>/dev/null
```

## Test 5: eBPF uprobe TLS capture (requires root)

Tests SSL_write_ex plaintext capture on HTTPS requests.

```bash
# Find SSL_write_ex offset
LIBSSL=$(python3 -c "import _ssl; print(_ssl.__file__)" | xargs ldd | grep libssl | awk '{print $3}')
OFFSET=$(nm -D $LIBSSL | grep "T SSL_write_ex" | awk '{print $1}')
echo "libssl: $LIBSSL offset: 0x$OFFSET"

# Register uprobe + capture
sudo bash -c "
echo > /sys/kernel/tracing/trace
mount -t tracefs tracefs /sys/kernel/tracing 2>/dev/null
echo 'p:gvm_ssl $LIBSSL:0x$OFFSET buf=+0(%si):string' > /sys/kernel/tracing/uprobe_events
echo 1 > /sys/kernel/tracing/events/uprobes/gvm_ssl/enable
"

# Make HTTPS requests
python3 -c "
import requests
requests.get('https://api.github.com/repos/skwuwu/Analemma-GVM')
requests.post('https://httpbin.org/post', json={'amount': 5000})
"

# Check captures
echo "=== Captured TLS plaintext ==="
sudo cat /sys/kernel/tracing/trace | grep gvm_ssl | sed 's/.*buf="//'

# Expected:
#   GET /repos/skwuwu/Analemma-GVM HTTP/1.1
#   POST /post HTTP/1.1

# Cleanup
sudo bash -c "
echo 0 > /sys/kernel/tracing/events/uprobes/gvm_ssl/enable
echo > /sys/kernel/tracing/uprobe_events
"
```

## Test 6: Full pipeline (MCP + proxy + uprobe + OpenClaw)

Combined test: all layers active simultaneously.

```bash
cd ~/Analemma-GVM

# 1. Load rulesets
python3 -c "
import os
rulesets = os.path.expanduser('~/analemma-gvm-openclaw/rulesets')
parts = [open(os.path.join(rulesets, f)).read() for f in
         ['_default.toml', 'llm-providers.toml', 'github.toml', 'google-workspace.toml']
         if os.path.exists(os.path.join(rulesets, f))]
open('config/srr_network.toml', 'w').write('\n'.join(parts))
print(f'{len(parts)} rulesets loaded')
"

# 2. Start proxy with Shadow Mode
> data/wal.log
GVM_SHADOW_MODE=strict ./target/release/gvm-proxy --config config/proxy.toml > /tmp/gvm-full.log 2>&1 &
PROXY_PID=$!
sleep 2

# 3. Register uprobe (if root available)
LIBSSL=$(python3 -c "import _ssl; print(_ssl.__file__)" 2>/dev/null | xargs ldd 2>/dev/null | grep libssl | awk '{print $3}')
OFFSET=$(nm -D $LIBSSL 2>/dev/null | grep "T SSL_write_ex" | awk '{print $1}')
if [ -n "$OFFSET" ]; then
    sudo bash -c "
    mount -t tracefs tracefs /sys/kernel/tracing 2>/dev/null
    echo > /sys/kernel/tracing/trace
    echo 'p:gvm_ssl $LIBSSL:0x$OFFSET buf=+0(%si):string' > /sys/kernel/tracing/uprobe_events
    echo 1 > /sys/kernel/tracing/events/uprobes/gvm_ssl/enable
    " 2>/dev/null && echo "uprobe: attached" || echo "uprobe: skipped (no root)"
else
    echo "uprobe: skipped (libssl not found)"
fi

# 4. Run OpenClaw agent through proxy
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
export HTTPS_PROXY=http://127.0.0.1:8080
export HTTP_PROXY=http://127.0.0.1:8080

echo "=== OpenClaw agent ==="
openclaw agent --local \
  --session-id "full-e2e-$(date +%s)" \
  --message "What is 2+2? Answer in one word." \
  --timeout 30 2>&1 | grep -v "model-selection"

echo ""
echo "=== Proxy CONNECT log ==="
grep "CONNECT tunnel" /tmp/gvm-full.log 2>/dev/null | tail -3

echo ""
echo "=== WAL events ==="
python3 -c "
import json
for line in open('data/wal.log'):
    try:
        e = json.loads(line)
        if 'event_id' in e:
            t = e.get('transport') or {}
            print(f'{e.get(\"decision\",\"?\"):20} | {t.get(\"method\",\"?\"):8} {t.get(\"host\",\"?\")}')
    except: pass
" | tail -5

if [ -n "$OFFSET" ]; then
    echo ""
    echo "=== uprobe TLS captures ==="
    sudo cat /sys/kernel/tracing/trace 2>/dev/null | grep gvm_ssl | sed 's/.*buf="//' | head -5
    sudo bash -c "echo 0 > /sys/kernel/tracing/events/uprobes/gvm_ssl/enable; echo > /sys/kernel/tracing/uprobe_events" 2>/dev/null
fi

echo ""
echo "=== Summary ==="
echo "Proxy:   $(curl -sf http://localhost:8080/gvm/health | python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get(\"status\",\"?\"))' 2>/dev/null)"
echo "WAL:     $(wc -l < data/wal.log) events"
echo "CONNECT: $(grep -c 'CONNECT tunnel' /tmp/gvm-full.log 2>/dev/null) tunnels"

kill $PROXY_PID 2>/dev/null
```

## Expected Results

| Test | Result |
|------|--------|
| 1. MCP policy check | Decision: Allow for github.com |
| 2. Ruleset hot-reload | Before: Delay → After: Allow (gmail read), Deny (gmail delete) |
| 3. OpenClaw + CONNECT | Agent responds + api.anthropic.com CONNECT logged |
| 4. Shadow Mode | With intent: registered, Without intent: blocked |
| 5. uprobe capture | GET /repos/... and POST /post plaintext captured |
| 6. Full pipeline | All of the above simultaneously |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| rustc ICE (panic) | `rustup default 1.85.0` |
| uprobe not found | `sudo mount -t tracefs tracefs /sys/kernel/tracing` |
| OpenClaw timeout | Check ANTHROPIC_API_KEY is set |
| CONNECT 502 | Proxy not built with CONNECT support (rebuild from latest) |
| SRR parse error | Check for mixed CRLF/LF or em-dash in .toml files |
