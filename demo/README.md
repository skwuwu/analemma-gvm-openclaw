# GVM Demos

## Live Use-Case Demo (recommended)

Real OpenClaw agent performing multi-step tasks with live governance enforcement.

| Scenario | What the agent does | Governance decisions |
|----------|-------------------|---------------------|
| **1. GitHub Code Review** | Read issues, review PRs, attempt merge | Allow → Allow → Delay 300ms → **Deny** (merge) → **Deny** (delete branch) |
| **2. Multi-Service Agent** | GitHub read → Slack post → unknown API → Slack archive | Allow → Delay 500ms → **Deny** (delete) → Delay (unknown) → **Deny** (archive) |
| **3. Security Audit** | Agent checks its own governance status and audit trail | gvm_status → gvm_blocked_summary → gvm_audit_log |

### Run

```bash
# 1. Setup: load rulesets + start proxy
bash demo/setup-live-demo.sh

# 2. Run all scenarios
python demo/live-usecase-demo.py --scenario all

# Or run individually
python demo/live-usecase-demo.py --scenario 1   # GitHub Code Review
python demo/live-usecase-demo.py --scenario 2   # Multi-Service
python demo/live-usecase-demo.py --scenario 3   # Security Audit

# Record asciinema cast
python demo/live-usecase-demo.py --scenario all --record
```

### Requirements

- `gvm-proxy` binary running
- Node.js 18+ (for MCP server)
- Rulesets: `github.toml`, `slack.toml` (included in `rulesets/`)

No API keys needed. The demo calls real MCP tools via JSON-RPC (the same protocol OpenClaw, Claude Desktop, and Cursor use).

---

## Shadow Mode Demo

Demonstrates the dual-lock architecture without OpenClaw installed.

| Scenario | Agent behavior | Result |
|----------|---------------|--------|
| 1 | Declares intent via `/gvm/intent`, then requests | **Allow** |
| 2 | Skips intent, requests directly | **Deny** (shadow strict) |
| 3 | Declares intent for `/get`, requests `/post` | **Deny** (cross-check) |

### Run

```bash
# Terminal 1: start proxy with shadow mode
GVM_SHADOW_MODE=strict gvm-proxy --config config/proxy.toml

# Terminal 2: run demo
bash demo/shadow-mode-demo.sh
```

### Requirements

- `gvm-proxy` binary (no OpenClaw, no Docker, no GPU)
- `curl`

---

## Google Workspace Demo

Policy check demo for Gmail, Calendar, Drive operations with latency benchmarks.

```bash
python demo/record-demo.py
```

### Requirements

- `gvm-proxy` running with `google-workspace.toml` ruleset
- `openclaw` for the live agent query (scenario 6)
- `ANTHROPIC_API_KEY` for LLM calls
