# Analemma GVM

**Drop-in API firewall for AI agents.**

Install one skill. Your agent is protected.

`17MB binary` · `~5MB memory` · `~0.4ms overhead` · `no GPU / containers required`

---

## What it looks like

**Allow vs Deny** — same agent, same Stripe API, different operations:

<p align="center">
  <img src="assets/02-allow-flow.png" alt="GVM Allow and Deny flow" width="680">
</p>

**Shadow Deny** — intent not declared, request blocked automatically:

<p align="center">
  <img src="assets/01-shadow-deny.png" alt="GVM Shadow Deny" width="680">
</p>

**Security dashboard** — ask your agent, no CLI needed:

<p align="center">
  <img src="assets/03-dashboard.png" alt="GVM Security Dashboard" width="680">
</p>

No terminal. No CLI. The agent handles governance through MCP tools.

---

## Quick Start

```bash
# 1. Install proxy binary
cargo binstall gvm-proxy

# 2. Install skill (prebuilt — no build step)
git clone https://github.com/skwuwu/analemma-gvm-openclaw.git \
  ~/.openclaw/skills/gvm-governance
```

Done. The MCP server automatically launches the proxy.

<details>
<summary><b>OpenClaw config</b></summary>

The skill auto-loads from `~/.openclaw/skills/`. Add MCP server:
```json
{
  "mcp": {
    "servers": {
      "gvm-governance": {
        "command": "node",
        "args": ["~/.openclaw/skills/gvm-governance/mcp-server/dist/index.js"]
      }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Desktop / Cursor / Windsurf</b></summary>

```json
{
  "mcpServers": {
    "gvm-governance": {
      "command": "node",
      "args": ["~/.openclaw/skills/gvm-governance/mcp-server/dist/index.js"]
    }
  }
}
```
</details>

---

## MCP Tools

**API calls** — agent uses these for all external requests:

| Tool | What it does | Example |
|------|-------------|---------|
| `gvm_fetch` | HTTP request with governance | `gvm_fetch("stripe.read", "GET", "https://api.stripe.com/v1/charges")` |
| `gvm_read` | GET shorthand | `gvm_read("github.list_prs", "https://api.github.com/repos/o/r/pulls")` |
| `gvm_write` | POST shorthand | `gvm_write("slack.send", "https://slack.com/api/chat.postMessage", body)` |

One call = intent declaration + policy check + execution. No separate steps.

**State management:**

| Tool | What it does |
|------|-------------|
| `gvm_policy_check` | Dry-run: will this request be allowed? |
| `gvm_checkpoint` | Save state before risky operations |
| `gvm_rollback` | Restore to checkpoint after a Deny |

**Ask your agent** — no CLI, no terminal:

| Tool | Try asking your agent |
|------|----------------------|
| `gvm_status` | "Is GVM running?" "What's my security status?" |
| `gvm_blocked_summary` | "What was blocked today?" "Security summary for the last hour" |
| `gvm_audit_log` | "Show recent denied requests" "Last 10 governance decisions" |
| `gvm_load_rulesets` | "Load rules for my installed skills" |

---

## How it works

```
Agent (OpenClaw / Claude / Cursor)
  │
  ├─ gvm_fetch("stripe.read", GET, /charges)    ← one tool call
  │     ├─ policy check (Allow/Deny?)
  │     ├─ intent registration (Shadow Mode)
  │     ├─ HTTP via proxy (credential injection)
  │     └─ WAL audit record (Merkle-chained)
  │
  └─ Response returned to agent
```

**Shadow Mode:** the proxy rejects any HTTP request without prior MCP intent.
If the agent uses `gvm_fetch` → intent is automatic. If the agent bypasses
(prompt injection, `exec curl`) → no intent → blocked.

**Why two layers?**

| Approach | Cooperative? | Forced? | Forgery detection? |
|----------|-------------|---------|-------------------|
| MCP only | Yes | No — agent can skip tools | No |
| Proxy only | No | Yes — all HTTP intercepted | No — no semantic layer |
| **MCP + Proxy** | **Yes** | **Yes** | **Yes — cross-layer** |

---

## Preset Rulesets

10 rulesets covering top OpenClaw skills. Pattern: **read → Allow, write → Delay, delete → Deny**.

| Ruleset | Skills covered | Domains |
|---------|---------------|---------|
| `github.toml` | github, gh-issues, coding-agent | api.github.com |
| `gmail.toml` | gmail, himalaya | gmail.googleapis.com |
| `slack.toml` | slack | slack.com/api |
| `discord.toml` | discord | discord.com/api |
| `notion.toml` | notion | api.notion.com |
| `openai.toml` | openai-image-gen, openai-whisper-api | api.openai.com |
| `trello.toml` | trello | api.trello.com |
| `gemini.toml` | gemini | googleapis.com |
| `spotify.toml` | spotify-player | api.spotify.com |
| `weather.toml` | weather | wttr.in |

Unmatched domains → Default-to-Caution (300ms delay + audit log).

---

## Security tiers

| Tier | Setup | Bypass possible? |
|------|-------|-----------------|
| **Shadow only** | Install skill (any OS) | Yes — direct TCP bypasses proxy |
| **Shadow + sandbox** | `gvm run --sandbox` (Linux) | **No** — kernel enforces proxy |
| **Shadow + Docker** | `gvm run --contained` (any OS) | Docker-dependent |

```bash
# Tier 1: Any OS (default — MCP auto-starts proxy with shadow=strict)
git clone ... ~/.openclaw/skills/gvm-governance

# Tier 2: Linux production (kernel isolation)
gvm run --sandbox my_agent.py

# Tier 3: macOS/Windows production (Docker isolation)
gvm run --contained my_agent.py
```

Tier 1 is enough for cooperative agents. Tier 2 for production where prompt injection is a real threat.

---

## Performance

| Path | Overhead | What happens |
|------|---------|-------------|
| **Allow** | ~0.4 ms | Policy check + intent + forward |
| **Deny** | ~4.2 ms | Policy check + WAL fsync + 403 |
| **Shadow Deny** | ~0.01 ms | No intent → instant 403 |

External API latency: 50-500 ms. GVM overhead: 0.1-0.8% of total.

---

## Zero Infrastructure

| | GVM | NemoClaw | Container-based |
|---|---|---|---|
| **Binary** | **17MB** | ~2GB | 500MB+ |
| **Memory** | **~5MB** | 512MB-2GB | 256MB+ |
| **GPU** | No | Required | Depends |
| **Startup** | <1s | 10-30s | 5-15s |

<details>
<summary><b>OS compatibility</b></summary>

| Feature | Linux | macOS | Windows |
|---------|-------|-------|---------|
| Proxy + SRR + WAL + Merkle | Yes | Yes | Yes |
| MCP Shadow Mode | Yes | Yes | Yes |
| `--sandbox` (namespace + seccomp + eBPF) | **Yes** | No | No |
| `--contained` (Docker) | Yes | Yes | Yes |
</details>

<details>
<summary><b>SDK vs MCP comparison</b></summary>

| Capability | SDK (`@ic`) | MCP |
|-----------|------------|-----|
| SRR URL matching | Automatic | Automatic |
| Cross-layer forgery | Automatic | Shadow Mode |
| API key isolation | Automatic | Automatic |
| Checkpoint | `auto_checkpoint="ic2+"` | `gvm_checkpoint` |
| Language | Python only | Any MCP client |
| Code changes | Add `@ic()` | Zero |
</details>

---

## Repository layout

```
mcp-server/           MCP server — 10 governance tools (JSON-RPC stdio)
skills/               OpenClaw skills (SKILL.md)
rulesets/             10 preset SRR rulesets + auto-detection registry
demo/                 Demo scripts
```

## Core repository

Source and docs: [skwuwu/Analemma-GVM](https://github.com/skwuwu/Analemma-GVM)
