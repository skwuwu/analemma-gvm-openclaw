# Codespace E2E Test — MCP + Proxy Full Verification

One-click Codespace setup for verifying the complete MCP governance pipeline.

## Setup (Codespace)

```bash
# 1. Create Codespace from the core repo
# Go to: https://github.com/skwuwu/Analemma-GVM → Code → Codespaces → New

# 2. Install Rust (Codespace has Node.js pre-installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source ~/.cargo/env

# 3. Build proxy
cd /workspaces/Analemma-GVM
cargo build --release -p gvm-proxy

# 4. Clone MCP repo
cd /workspaces
git clone https://github.com/skwuwu/analemma-gvm-openclaw.git
cd analemma-gvm-openclaw
```

## Test 1: MCP Policy Check (gvm_policy_check)

Verifies MCP server → proxy `/gvm/check` pipeline.

```bash
# Start proxy
cd /workspaces/Analemma-GVM
./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2
curl -sf http://127.0.0.1:8080/gvm/health && echo " OK"

# MCP policy check via JSON-RPC
cd /workspaces/analemma-gvm-openclaw
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gvm_policy_check","arguments":{"method":"GET","url":"https://api.github.com/repos/skwuwu/Analemma-GVM/issues"}}}' \
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
kill $PROXY_PID 2>/dev/null
```

## Test 2: MCP gvm_fetch (Allow + Deny)

Verifies MCP `gvm_fetch` → intent declaration → policy check → execution.

```bash
cd /workspaces/Analemma-GVM
./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

cd /workspaces/analemma-gvm-openclaw

# Test 2a: gvm_fetch for a Denied action (merge PR)
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gvm_fetch","arguments":{"operation":"github.merge_pr","method":"PUT","url":"https://api.github.com/repos/skwuwu/Analemma-GVM/pulls/1/merge"}}}' \
  | node mcp-server/dist/index.js 2>/dev/null \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    if d.get('id') == 2:
        result = json.loads(d['result']['content'][0]['text'])
        print(f'Decision: {result.get(\"decision\", \"?\")}')
        print(f'Blocked: {result.get(\"blocked\", False)}')
        print(f'Error: {result.get(\"error\", \"none\")}')
"

# Expected: Decision: Deny, Blocked: True
kill $PROXY_PID 2>/dev/null
```

## Test 3: gvm_select_rulesets + Hot-Reload

Verifies ruleset selection → SRR file replacement → proxy hot-reload.

```bash
cd /workspaces/Analemma-GVM
# Start with default SRR only
cat config/srr_network.toml | head -3
./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

cd /workspaces/analemma-gvm-openclaw

# Apply github ruleset via MCP
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gvm_select_rulesets","arguments":{"apply":["github"]}}}' \
  | GVM_CONFIG_DIR=/workspaces/Analemma-GVM/config node mcp-server/dist/index.js 2>/dev/null \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    if d.get('id') == 2:
        result = json.loads(d['result']['content'][0]['text'])
        print(f'Mode: {result.get(\"mode\", \"?\")}')
        for a in result.get('applied', []):
            print(f'  + {a[\"name\"]}: {a[\"rules\"]} rules ({a[\"domains\"]})')
"

# Verify hot-reload: github issue read should now be Allow
curl -sf -X POST http://127.0.0.1:8080/gvm/check \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","target_host":"api.github.com","target_path":"/repos/test/test/issues","operation":"test"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'After reload: {d[\"decision\"]}')"

# Expected: Mode: apply, After reload: Allow
kill $PROXY_PID 2>/dev/null
```

## Test 4: gvm_status + gvm_blocked_summary

Verifies MCP query tools read live proxy state and WAL data.

```bash
cd /workspaces/Analemma-GVM
> data/wal.log
./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

# Generate some WAL events
for i in 1 2 3; do
  curl -sf -X POST http://127.0.0.1:8080/gvm/check \
    -H "Content-Type: application/json" \
    -d '{"method":"GET","target_host":"api.github.com","target_path":"/repos/t/t/issues","operation":"test"}' > /dev/null
done
curl -sf -X POST http://127.0.0.1:8080/gvm/check \
  -H "Content-Type: application/json" \
  -d '{"method":"DELETE","target_host":"api.github.com","target_path":"/repos/t/t/git/refs/heads/main","operation":"test"}' > /dev/null

cd /workspaces/analemma-gvm-openclaw

# gvm_status
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gvm_status","arguments":{}}}' \
  | node mcp-server/dist/index.js 2>/dev/null \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    if d.get('id') == 2:
        result = json.loads(d['result']['content'][0]['text'])
        print(f'Proxy: {result.get(\"proxy\")} | Shadow: {result.get(\"shadow_mode\")}')
"

# Expected: Proxy: running
kill $PROXY_PID 2>/dev/null
```

## Test 5: Live Demo Script

Runs the full use-case demo (policy checks via real MCP JSON-RPC calls).

```bash
cd /workspaces/Analemma-GVM

# Load rulesets
python3 -c "
import os
rulesets = '/workspaces/analemma-gvm-openclaw/rulesets'
parts = []
for f in ['_default.toml', 'github.toml', 'slack.toml', 'web-browsing.toml']:
    path = os.path.join(rulesets, f)
    if os.path.exists(path):
        parts.append('# -- ' + f + ' --\n' + open(path).read())
open('config/srr_network.toml', 'w').write('\n'.join(parts))
print(f'{len(parts)} rulesets loaded')
"

./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

cd /workspaces/analemma-gvm-openclaw
python3 demo/live-usecase-demo.py --scenario all

# Expected:
#   Scenario 1: Allow, Allow, Delay, Deny, Deny
#   Scenario 2: Allow, Delay, Deny, Delay, Deny
#   Scenario 3: proxy running + audit stats

kill $PROXY_PID 2>/dev/null
```

## Test 6: MCP + Proxy + eBPF Uprobe (requires root)

Full pipeline: MCP gvm_fetch → proxy CONNECT → uprobe SSL_write_ex capture → SRR policy check.
This is the realistic user use-case with all layers active.

```bash
cd /workspaces/Analemma-GVM

# Load github ruleset
python3 -c "
import os
rulesets = '/workspaces/analemma-gvm-openclaw/rulesets'
parts = []
for f in ['_default.toml', 'github.toml']:
    path = os.path.join(rulesets, f)
    if os.path.exists(path): parts.append(open(path).read())
open('config/srr_network.toml', 'w').write('\n'.join(parts))
print(f'{len(parts)} rulesets loaded')
"

./target/release/gvm-proxy --config config/proxy.toml &
PROXY_PID=$!
sleep 2

# Register uprobe on SSL_write_ex (requires root)
LIBSSL=$(python3 -c "import _ssl; print(_ssl.__file__)" | xargs ldd | grep libssl | awk '{print $3}')
OFFSET=$(nm -D $LIBSSL | grep "T SSL_write_ex" | awk '{print $1}')

if [ -n "$OFFSET" ]; then
    sudo bash -c "
    mount -t tracefs tracefs /sys/kernel/tracing 2>/dev/null
    echo > /sys/kernel/tracing/trace
    echo 'p:gvm_ssl $LIBSSL:0x$OFFSET buf=+0(%si):string' > /sys/kernel/tracing/uprobe_events
    echo 1 > /sys/kernel/tracing/events/uprobes/gvm_ssl/enable
    " 2>/dev/null && echo "uprobe: attached to $LIBSSL" || echo "uprobe: skipped (no root)"
    UPROBE_ATTACHED=true
else
    echo "uprobe: skipped (SSL_write_ex not found)"
    UPROBE_ATTACHED=false
fi

cd /workspaces/analemma-gvm-openclaw

# Step 1: MCP gvm_read — read GitHub issues (Allow)
echo ""
echo "=== Step 1: MCP gvm_policy_check (read issues → Allow) ==="
python3 scripts/mcp_call.py gvm_policy_check '{"method":"GET","url":"https://api.github.com/repos/skwuwu/Analemma-GVM/issues"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'Decision: {d.get(\"decision\")}')"

# Step 2: Make actual HTTPS request through proxy (uprobe captures plaintext)
echo ""
echo "=== Step 2: HTTPS through proxy (uprobe captures) ==="
HTTPS_PROXY=http://127.0.0.1:8080 python3 -c "
import requests
r = requests.get('https://api.github.com/repos/skwuwu/Analemma-GVM', timeout=10)
print(f'Status: {r.status_code}, Repo: {r.json().get(\"name\", \"?\")}')" 2>/dev/null || echo "(request failed — expected if no network)"

# Step 3: MCP gvm_fetch — merge PR (Deny + blocked)
echo ""
echo "=== Step 3: MCP gvm_fetch (merge PR → Deny) ==="
python3 scripts/mcp_call.py gvm_fetch '{"operation":"github.merge_pr","method":"PUT","url":"https://api.github.com/repos/t/t/pulls/1/merge"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'Decision: {d.get(\"decision\")}, Blocked: {d.get(\"blocked\")}')"

# Step 4: MCP gvm_fetch — delete branch (Deny + blocked)
echo ""
echo "=== Step 4: MCP gvm_fetch (delete branch → Deny) ==="
python3 scripts/mcp_call.py gvm_fetch '{"operation":"github.delete_branch","method":"DELETE","url":"https://api.github.com/repos/t/t/git/refs/heads/old"}' \
  | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'Decision: {d.get(\"decision\")}, Blocked: {d.get(\"blocked\")}')"

# Step 5: Verify uprobe captured plaintext
if [ "$UPROBE_ATTACHED" = "true" ]; then
    echo ""
    echo "=== Step 5: uprobe TLS plaintext captures ==="
    sudo cat /sys/kernel/tracing/trace 2>/dev/null | grep gvm_ssl | tail -5 | sed 's/.*buf="//'

    # Cleanup uprobe
    sudo bash -c "
    echo 0 > /sys/kernel/tracing/events/uprobes/gvm_ssl/enable
    echo > /sys/kernel/tracing/uprobe_events
    " 2>/dev/null
fi

# Step 6: Verify proxy policy check with uprobe operation tag
echo ""
echo "=== Step 6: Proxy SRR decisions (uprobe context) ==="
for check in \
  '{"method":"GET","target_host":"api.github.com","target_path":"/repos/t/t/issues","operation":"uprobe"}:read_issues' \
  '{"method":"PUT","target_host":"api.github.com","target_path":"/repos/t/t/pulls/1/merge","operation":"uprobe"}:merge_pr' \
  '{"method":"DELETE","target_host":"api.github.com","target_path":"/repos/t/t/git/refs/heads/main","operation":"uprobe"}:delete_branch'
do
  BODY="${check%%:*}"
  LABEL="${check##*:}"
  DECISION=$(curl -sf -X POST http://127.0.0.1:8080/gvm/check \
    -H "Content-Type: application/json" -d "$BODY" \
    | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('decision','?'))")
  echo "  $LABEL: $DECISION"
done

# Expected:
#   Step 1: Decision: Allow
#   Step 2: Status: 200 + uprobe captures "GET /repos/skwuwu/Analemma-GVM HTTP/1.1"
#   Step 3: Decision: Deny, Blocked: True
#   Step 4: Decision: Deny, Blocked: True
#   Step 5: HTTP plaintext lines (if uprobe attached)
#   Step 6: read_issues=Allow, merge_pr=Deny, delete_branch=Deny

kill $PROXY_PID 2>/dev/null
```

## Expected Results

| Test | What it verifies | Expected |
|------|-----------------|----------|
| 1 | MCP policy check | Decision: Allow |
| 2 | MCP gvm_fetch deny | Decision: Deny, Blocked: True |
| 3 | Ruleset hot-reload | Applied + Allow after reload |
| 4 | Status + audit | Proxy: running |
| 5 | Full demo script | Allow/Delay/Deny per scenario |
| 6 | MCP + proxy + uprobe | Allow (read), Deny (merge/delete), plaintext captured |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `cargo build` OOM | Use `-j 2` to limit parallelism |
| MCP server not found | Check `mcp-server/dist/index.js` exists (prebuilt) |
| Proxy 8080 in use | `lsof -i :8080` and kill existing process |
| SRR parse error | Check for CRLF/LF mixing in .toml files |
| Node.js not found | Codespace should have Node.js 18+ pre-installed |
