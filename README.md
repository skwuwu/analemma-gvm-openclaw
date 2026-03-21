# Analemma GVM — OpenClaw + MCP Server

AI agent governance for [OpenClaw](https://openclaw.ai), [Claude Desktop](https://claude.ai), Cursor, Windsurf, and any MCP-compatible client.

**One MCP server, every agent platform.**

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
  src/index.ts        # MCP server — 6 governance tools over JSON-RPC stdio
  dist/               # Compiled output (after npm run build)
  package.json
  tsconfig.json
skills/
  gvm-governance/
    SKILL.md           # OpenClaw skill — agent instructions for MCP tool usage
  gvm-audit/
    SKILL.md           # /gvm-audit slash command
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

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GVM_PROXY_URL` | `http://127.0.0.1:8080` | GVM proxy base URL |
| `GVM_AGENT_ID` | `mcp-agent` | Agent identity for WAL records |
| `GVM_TENANT_ID` | — | Tenant identity (multi-tenant) |

## Core repository

Source and docs: [skwuwu/Analemma-GVM](https://github.com/skwuwu/Analemma-GVM)
Docker image: `ghcr.io/skwuwu/analemma-gvm:latest`
