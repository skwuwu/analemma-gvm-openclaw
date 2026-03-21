# Analemma GVM — OpenClaw + MCP Server

AI agent governance for [OpenClaw](https://openclaw.ai), [Claude Desktop](https://claude.ai), Cursor, Windsurf, and any MCP-compatible client.

**One MCP server, every agent platform.**

## Zero Infrastructure

GVM is a single static binary. No containers, no GPU, no Kubernetes.

| | GVM Proxy | NemoClaw (NeMo Guardrails) | Container-based (OpenShell) |
|---|---|---|---|
| **Binary** | Single **17MB** (measured, release build) | Python runtime + embedding models (~2GB) | Docker images (500MB+) |
| **Memory** | ~5MB RSS | 512MB-2GB (embedding inference) | 256MB+ per container |
| **GPU** | Not needed | Required (embedding/classification) | Depends |
| **K8s** | Not needed | Recommended | Required |
| **Startup** | <1s | 10-30s (model loading) | 5-15s (image pull + start) |
| **Install** | `cargo binstall gvm-proxy` | pip + model downloads + config | docker pull + orchestration |
| **Runtime deps** | None | Python, CUDA, torch | Docker daemon, kubelet |

GVM fits in the same resource envelope as a reverse proxy (nginx, envoy) — because that's what it is, plus governance logic.

### What you need

| Component | Requirement |
|-----------|-------------|
| GVM proxy | Any OS, ~50MB disk, ~5MB RAM |
| MCP server | Node.js 18+ (for JSON-RPC stdio bridge) |
| Network | Localhost only (proxy ↔ MCP ↔ agent on same machine) |
| GPU | Not needed. Ever. |
| Docker | Not needed (optional `--contained` mode for production) |
| External services | None (WAL is local file, vault is in-memory AES-256-GCM) |

## Dual-Lock Architecture

```
OpenClaw Gateway / Claude Desktop / Cursor
    |
    ├─ gmail MCP server
    ├─ github MCP server
    ├─ gvm-governance MCP server  ← this package
    |   |
    |   ├─ gvm_policy_check(method, url)       → Allow/Delay/Deny
    |   ├─ gvm_declare_intent(operation, ...)   → register intent for forgery detection
    |   ├─ gvm_request_secret(host)             → confirm credential injection
    |   ├─ gvm_checkpoint(label, step)          → save state for rollback
    |   ├─ gvm_rollback(step)                   → restore to checkpoint
    |   └─ gvm_audit_log(last_n)                → view governance decisions
    |
    └─ [HTTP_PROXY=localhost:8080] ← GVM proxy (enforcement layer)
```

**Layer 1 — MCP tools (cooperative):** Agent calls `gvm_declare_intent` before API requests. The proxy cross-checks declared intent against actual HTTP target. This enables forgery detection without SDK integration.

**Layer 2 — HTTP proxy (forced):** All outbound HTTP goes through the GVM proxy regardless of whether the agent uses MCP tools. Undeclared requests trigger Default-to-Caution (Delay). Denied URLs return 403. The agent never holds API keys.

**Result:** If the agent cooperates via MCP → smooth operation with full audit trail. If the agent skips MCP (prompt injection, bugs) → the proxy catches it anyway.

## MCP Tools

| Tool | Purpose | When to use |
|------|---------|-------------|
| `gvm_policy_check` | Dry-run policy evaluation | Before any external API call |
| `gvm_declare_intent` | Register operation for forgery detection | After policy check passes |
| `gvm_request_secret` | Confirm credential auto-injection | When calling authenticated APIs |
| `gvm_checkpoint` | Save agent state | Before risky operations (IC-2+) |
| `gvm_rollback` | Restore to checkpoint | After a Deny, instead of restarting |
| `gvm_audit_log` | View recent decisions | Investigating governance events |

## Quick Start

### 1. Install GVM

```bash
cargo binstall gvm-proxy gvm-cli
```

### 2. Configure MCP server

**OpenClaw** — add to `~/.openclaw/openclaw.yaml`:

```yaml
mcpServers:
  gvm-governance:
    command: node
    args: ["/path/to/analemma-gvm-openclaw/mcp-server/dist/index.js"]
    env:
      GVM_PROXY_URL: "http://127.0.0.1:8080"
      GVM_AGENT_ID: "openclaw-agent"
```

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gvm-governance": {
      "command": "node",
      "args": ["/path/to/analemma-gvm-openclaw/mcp-server/dist/index.js"],
      "env": {
        "GVM_PROXY_URL": "http://127.0.0.1:8080",
        "GVM_AGENT_ID": "claude-desktop"
      }
    }
  }
}
```

**Cursor / Windsurf** — same JSON format in their MCP settings.

### 3. Start GVM proxy + agent

```bash
# Terminal 1: start proxy
gvm-proxy

# Terminal 2: start agent (OpenClaw, Claude Desktop, etc.)
# The MCP server starts automatically as a child process
```

### 4. Install OpenClaw skills (optional)

```bash
# Copy skills into managed skills directory
cp -r skills/* ~/.openclaw/skills/
```

This teaches the OpenClaw agent how to use the MCP tools properly.

## Build from source

```bash
cd mcp-server
npm install
npm run build
```

## Repository layout

```
mcp-server/
  src/index.ts        # MCP server — 7 governance tools over JSON-RPC stdio
  dist/               # Compiled output (after npm run build)
  package.json
  tsconfig.json
skills/
  gvm-governance/
    SKILL.md           # OpenClaw skill — agent instructions + Shadow Mode rules
  gvm-audit/
    SKILL.md           # /gvm-audit slash command
rulesets/
  registry.json        # Skill-to-ruleset mapping (auto-detection)
  _default.toml        # Fallback: localhost Allow, unknown → Default-to-Caution
  github.toml          # api.github.com rules
  gmail.toml           # gmail.googleapis.com rules
  slack.toml           # slack.com/api rules
  discord.toml         # discord.com/api rules
  notion.toml          # api.notion.com rules
  trello.toml          # api.trello.com rules
  openai.toml          # api.openai.com rules
  gemini.toml          # generativelanguage.googleapis.com rules
  spotify.toml         # api.spotify.com rules
  weather.toml         # wttr.in, open-meteo.com rules
demo/
  shadow-mode-demo.sh  # Standalone demo (curl only, no OpenClaw needed)
  README.md
README.md
```

## Why MCP + Proxy (not just one)

| Approach | Cooperative? | Forced? | Forgery detection? |
|----------|-------------|---------|-------------------|
| MCP only | Yes | No — agent can skip tools | No |
| Proxy only | No | Yes — all HTTP intercepted | No — no semantic layer |
| **MCP + Proxy** | **Yes** | **Yes** | **Yes — cross-layer** |

MCP alone trusts the agent to call tools. A prompt-injected agent can skip them.
Proxy alone catches URL violations but can't cross-check semantic intent.
Together, they provide the dual-lock: cooperate if honest, enforce if compromised.

## Performance: MCP Path Latency

### Step-by-step breakdown (Allow path)

```
Agent decides to call Stripe API
  │
  ├─ 1. gvm_declare_intent (MCP tool call)
  │    ├─ stdio JSON-RPC serialize/deserialize    ~0.05 ms
  │    ├─ POST /gvm/check (dry-run policy check)  ~0.15 ms  localhost HTTP
  │    └─ POST /gvm/intent (register intent)      ~0.15 ms  localhost HTTP + mutex + Vec push
  │    subtotal:                                   ~0.35 ms
  │
  ├─ 2. HTTP request through proxy
  │    ├─ Shadow verify (IntentStore.verify)       ~0.01 ms  in-memory lookup, no I/O
  │    ├─ SRR + ABAC policy evaluation             <0.01 ms  compiled regex, sub-μs
  │    ├─ API key injection                         <0.01 ms  header insert
  │    └─ Forward to upstream                      50-500 ms network-dependent
  │    subtotal:                                   ~0.03 ms  GVM overhead
  │
  Total GVM overhead (Allow):                      ~0.4 ms
  External API latency:                            50-500 ms
  GVM as % of total:                               0.1-0.8%
```

### Deny path (WAL-durable)

```
  gvm_declare_intent                               ~0.35 ms  (same as Allow)
  Shadow verify + SRR → Deny decision              ~0.01 ms
  WAL fsync (durable audit record before 403)      ~3.8 ms   intentional — audit first
  Total:                                           ~4.2 ms
```

The 3.8 ms Deny overhead is a deliberate design choice — the denial record must be durable before the 403 response. Cilium/Envoy use fire-and-forget logging; GVM blocks until the audit entry is fsynced. For AI agent actions (wire transfers, credential access), 3.8 ms of audit durability is worth it.

### Comparison

| Path | SDK (Python `@ic`) | MCP + Proxy | Difference |
|------|-------------------|-------------|------------|
| **Allow** | ~0.28 ms | ~0.4 ms | +0.12 ms (intent registration) |
| **Deny** | ~3.8 ms | ~4.2 ms | +0.4 ms (intent + check) |
| **Shadow Deny** (no intent) | N/A | ~0.01 ms + 403 | Instant rejection |

Benchmark source: [Daytona sandbox measurements](https://github.com/skwuwu/analemma-gvm-daytona/blob/master/bench/results.md) (N=50, real cloud environment).

### What MCP adds vs loses

| Capability | SDK (Python `@ic`) | MCP + Proxy | Trade-off |
|-----------|-------------------|-------------|-----------|
| **SRR URL matching** | Automatic (proxy) | Automatic (proxy) | Identical |
| **ABAC policy eval** | Automatic (`@ic()` headers) | `gvm_declare_intent` call | MCP: agent must cooperate |
| **Cross-layer forgery** | Automatic (`max_strict`) | Intent-vs-URL cross-check | MCP: undeclared = Tier 1 only |
| **API key isolation** | Automatic (proxy) | Automatic (proxy) | Identical |
| **Merkle audit chain** | Automatic (proxy) | Automatic (proxy) | Identical |
| **Checkpoint** | `auto_checkpoint="ic2+"` | `gvm_checkpoint` manual call | MCP: explicit, not automatic |
| **Rollback on Deny** | `GVMRollbackError` auto-raised | `gvm_rollback` manual call | MCP: no exception flow |
| **Fail-close** | Proxy down = no network | Proxy down = no network | Identical |
| **Rate limiting** | Per-agent (header-based) | Per-agent (`X-GVM-Agent-Id`) | Identical |
| **Language support** | Python only | Any MCP client | MCP: universal |
| **Integration effort** | Add `@ic()` to functions | Configure MCP server | MCP: zero code changes |

**Summary:** MCP trades automatic SDK integration for universal platform compatibility. The proxy enforcement layer (SRR, key isolation, Merkle audit, fail-close) is identical — it doesn't depend on MCP or SDK. The difference is in the cooperative layer: SDK does it automatically via decorators; MCP relies on the agent calling tools, with the proxy as safety net.

### When to use which

| Scenario | Recommended | Reason |
|----------|-------------|--------|
| Python agent, deep integration | SDK (`@ic` + `GVMAgent`) | Automatic forgery detection, auto-checkpoint |
| OpenClaw / Claude Desktop / Cursor | MCP server | Universal, zero code changes |
| Multi-language environment | MCP server | Language-agnostic |
| Maximum security (production) | SDK + `--sandbox` | Automatic + namespace isolation + seccomp |
| Quick evaluation | MCP server | Install in 2 minutes, no code changes |

## System requirements

| Component | SDK approach | MCP approach |
|-----------|-------------|-------------|
| GVM proxy | `cargo binstall gvm-proxy` | `cargo binstall gvm-proxy` |
| Runtime | Python 3.9+ | Node.js 18+ |
| SDK | `pip install gvm` | Not needed |
| MCP server | Not needed | This package (`npm run build`) |
| Agent platform | Any (manual `HTTP_PROXY`) | OpenClaw, Claude Desktop, Cursor, Windsurf, etc. |
| OS | Any | Any |
| Linux isolation | `--sandbox` flag (optional) | `--sandbox` flag (optional) |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GVM_PROXY_URL` | `http://127.0.0.1:8080` | GVM proxy base URL |
| `GVM_AGENT_ID` | `mcp-agent` | Agent identity for WAL records |
| `GVM_TENANT_ID` | — | Tenant identity (multi-tenant) |

## Core repository

Source and docs: [skwuwu/Analemma-GVM](https://github.com/skwuwu/Analemma-GVM)
Docker image: `ghcr.io/skwuwu/analemma-gvm:latest`
