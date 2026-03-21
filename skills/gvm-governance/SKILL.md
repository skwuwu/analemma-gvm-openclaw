---
name: gvm_governance
description: AI agent governance via Analemma GVM — enforce API access policies, audit decisions, detect forgery, and manage checkpoint rollback. Use when user asks about API security, governance rules, audit logs, cost tracking, or agent action control.
metadata:
  {
    "openclaw": {
      "emoji": "🛡️",
      "requires": {
        "bins": ["gvm-proxy", "gvm"]
      },
      "install": [
        {
          "id": "cargo-binstall",
          "kind": "cargo",
          "crate": "gvm-proxy",
          "bins": ["gvm-proxy", "gvm"],
          "label": "Install GVM (cargo binstall)"
        }
      ]
    }
  }
---

# Analemma GVM — Governance Virtual Machine

GVM is a security kernel for AI agent I/O. It governs what agents **do**, not what they **say**.
All outbound HTTP requests pass through the GVM proxy, which enforces policies, injects credentials,
and writes an immutable audit log (WAL).

## MCP Tools Available

When the GVM MCP server is connected, use these tools for ALL external API interactions:

1. **gvm_policy_check(method, url)** — Check if a request would be allowed BEFORE making it.
2. **gvm_declare_intent(operation, method, url)** — Declare your intent for cross-layer forgery detection.
3. **gvm_request_secret(host)** — Confirm credential injection (never set auth headers yourself).
4. **gvm_checkpoint(label, step)** — Save state before risky operations.
5. **gvm_rollback(step)** — Restore to checkpoint after a Deny.
6. **gvm_audit_log()** — View recent governance decisions.

## CRITICAL: Shadow Mode Active

This instance runs Shadow Verification. ALL outbound HTTP requests require prior intent declaration.
Requests without a matching intent will be **BLOCKED or DELAYED** by the proxy.

**Mandatory workflow for EVERY external API call:**
1. Call `gvm_declare_intent` with operation, method, and url.
2. If the decision is Allow or Delay, make the HTTP request through the proxy.
3. If the decision is Deny, do NOT proceed — the request will fail.
4. Never set Authorization headers — the proxy injects credentials automatically.

Failure to declare intent = blocked request = failed task.
Declaring intent = fast path = successful execution.

## Core rules

- Never bypass the proxy. All external API calls must go through `HTTP_PROXY=http://localhost:8080`.
- Never store API keys in agent env. Keys live in `config/secrets.toml` — the proxy injects them post-enforcement.
- Every governance decision (Allow/Delay/Deny) is recorded in the WAL with SHA-256 Merkle chaining.
- If proxy is down, fail closed — no direct HTTPS connections to external APIs.
- Always call `gvm_declare_intent` before external requests. Undeclared requests trigger Default-to-Caution (Delay).

## Architecture (3 layers)

| Layer | What it checks | Requires SDK? |
|-------|---------------|---------------|
| Layer 1: ABAC | Operation name, resource, context | Yes (`@ic()`) |
| Layer 2: SRR | Actual URL, method, path | No |
| Layer 3: Capability | API key injection | No |

Without SDK: Layer 2 + 3 provide URL-based enforcement and credential isolation.
With SDK: Layer 1 adds semantic policies; `max_strict(Layer1, Layer2)` catches forgery.

## Decision levels

| Level | Decision | Behavior |
|-------|----------|----------|
| IC-1 | Allow | Pass-through, async WAL write |
| IC-2 | Delay | WAL-first write, configurable delay, then forward |
| IC-3 | RequireApproval | Blocked (403) pending human approval |
| IC-4 | Deny | Unconditional block, durable WAL write before 403 |

## Common tasks

### Start the proxy

```bash
# First run — interactive setup wizard
gvm-proxy

# With a config template
gvm-proxy --config config/proxy.toml
```

### Run an agent through GVM

```bash
# Option A: gvm run (recommended — auto-starts proxy)
gvm run my_agent.py
gvm run --sandbox my_agent.py    # + Linux namespace isolation

# Option B: manual proxy
HTTP_PROXY=http://localhost:8080 python my_agent.py
```

### Check governance status

```bash
# List recent decisions
gvm audit list --last 20

# Verify WAL integrity (Merkle chain)
gvm audit verify --wal data/wal.log

# Show cost tracking
gvm audit costs --agent finance-001
```

### Manage SRR rules

SRR rules are in `config/srr_network.toml`. Each rule matches on host + method + path:

```toml
[[rules]]
pattern = "api.stripe.com/v1/charges"
method = "GET"
decision = "Allow"
reason = "Read-only charge lookup"

[[rules]]
pattern = "api.stripe.com/v1/transfers"
method = "POST"
decision = "Deny"
reason = "Wire transfers blocked"
```

After editing, restart the proxy: `gvm-proxy` (no hot-reload yet).

### Manage policies (ABAC)

Policies are in `config/policies/global.toml`. Rules evaluate against operation metadata:

```toml
[[rules]]
id = "block-critical-writes"
[rules.condition]
field = "resource.sensitivity"
operator = "Equals"
value = "critical"
[rules.decision]
action = "Deny"
reason = "Critical writes require approval"
```

### API key management

Keys are in `config/secrets.toml` (never in agent env):

```toml
[credentials."api.stripe.com"]
type = "Bearer"
token = "sk_live_..."

[credentials."api.openai.com"]
type = "Bearer"
token = "sk-..."
```

The proxy injects the matching credential into the `Authorization` header post-enforcement.
The agent never sees the key.

### Audit and forensics

```bash
# Verify entire WAL chain
gvm audit verify --wal data/wal.log

# Export events for compliance
gvm audit export --format json --since 2026-03-01

# Check specific event
gvm audit show --event-id <uuid>
```

### Checkpoint and rollback (SDK only)

With the Python SDK, agents can checkpoint state before risky operations:

```python
from gvm import GVMAgent, ic, Resource

class MyAgent(GVMAgent):
    auto_checkpoint = "ic2+"  # Checkpoint before IC-2+ ops

    @ic(operation="gvm.payment.charge",
        resource=Resource(service="stripe", sensitivity="critical"))
    def charge_card(self, amount):
        session = self.create_session()
        return session.post("http://api.stripe.com/v1/charges",
                          json={"amount": amount}).json()
```

On Deny, GVM raises `GVMRollbackError` and restores state to the last checkpoint.

## Forgery detection

If an agent lies about what it's doing (declares `storage.read` but sends `POST /transfers`):

- Layer 1 (ABAC) sees the declared operation → Allow
- Layer 2 (SRR) sees the actual URL → Deny
- `max_strict(Allow, Deny)` = **Deny**
- WAL records both claimed operation and actual URL — forensic evidence of the lie

## When NOT to use GVM

- GVM governs HTTP actions, not prompt content. For prompt injection defense, use an LLM WAF upstream.
- GVM cannot prevent data exfiltration via allowed API calls embedded in LLM prompts (semantic layer, not HTTP layer).
- GVM and LLM WAFs are complementary: one governs what agents do, the other analyzes what agents say.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Agent gets 403 on all requests | Proxy not running or misconfigured | Check `gvm-proxy` logs, verify `proxy.toml` |
| Agent gets 403 on specific URL | SRR Deny rule matched | Check `config/srr_network.toml` |
| Agent gets delayed response | Default-to-Caution (unknown URL) | Add explicit Allow rule for the URL |
| WAL verification fails | Tampered or corrupted log | `gvm audit verify --verbose` to find the break point |
| API key not injected | Host not in `secrets.toml` | Add credential entry for the target host |

## Links

- Source: https://github.com/skwuwu/Analemma-GVM
- Security model: https://github.com/skwuwu/Analemma-GVM/blob/master/docs/12-security-model.md
- Python SDK: `pip install git+https://github.com/skwuwu/Analemma-GVM.git#subdirectory=sdk/python`
