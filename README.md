# Analemma GVM — OpenClaw Skills

[OpenClaw](https://openclaw.ai) skills for AI agent governance via [Analemma GVM](https://github.com/skwuwu/Analemma-GVM).

## What these skills do

| Skill | Type | Description |
|-------|------|-------------|
| `gvm-governance` | Auto-loaded | Teaches the agent how to enforce API policies, manage SRR rules, handle credentials, and use checkpoint/rollback |
| `gvm-audit` | `/gvm-audit` | Slash command to verify WAL integrity, investigate denials, and export compliance reports |

## Install

### Option 1: Clone into managed skills

```bash
git clone https://github.com/skwuwu/analemma-gvm-openclaw.git \
  ~/.openclaw/skills/gvm
```

### Option 2: ClawHub (when published)

```bash
clawhub install gvm-governance
clawhub install gvm-audit
```

### Option 3: Workspace-local

```bash
# Inside your agent workspace
mkdir -p skills
cp -r path/to/analemma-gvm-openclaw/skills/* skills/
```

## Prerequisites

GVM proxy and CLI must be installed:

```bash
cargo binstall gvm-proxy gvm-cli
```

Or build from source:

```bash
git clone https://github.com/skwuwu/Analemma-GVM.git && cd Analemma-GVM
cargo install --path .
```

## How it works

```
 OpenClaw Agent          GVM Proxy (:8080)          External API
 ┌──────────┐    HTTP     ┌──────────────────┐  HTTPS  ┌──────────┐
 │ Any task  │───PROXY───>│ Policy + audit   │────────>│ Stripe   │
 │ via chat  │            │ Key injection    │         │ Gmail    │
 └──────────┘             └──────────────────┘         └──────────┘
```

1. OpenClaw agent receives a task (e.g., "send the Q4 report via email")
2. Agent calls external APIs through `HTTP_PROXY=http://localhost:8080`
3. GVM proxy evaluates SRR rules + ABAC policies → Allow / Delay / Deny
4. Allowed requests get credentials injected; denied requests return 403
5. Every decision is WAL-recorded with SHA-256 Merkle chaining

The agent never holds API keys. The proxy holds them and injects post-enforcement.

## Configuration

Configure in `~/.openclaw/openclaw.json`:

```json5
{
  "skills": {
    "entries": {
      "gvm_governance": {
        "enabled": true
      },
      "gvm_audit": {
        "enabled": true
      }
    }
  }
}
```

## Why GVM for OpenClaw?

OpenClaw gives agents the ability to **act** — run commands, call APIs, manage files.
GVM ensures those actions are **governed**:

- **Credential isolation**: Agent never sees API keys (proxy injects them)
- **Graduated enforcement**: Allow / Delay / Deny — not binary
- **Forgery detection**: Agent says "read" but does "transfer"? `max_strict` catches the lie
- **Tamper-proof audit**: Merkle-chained WAL — every decision is cryptographically linked
- **Checkpoint rollback**: Denied at step 3 of 4? Resume from checkpoint, don't restart

Without GVM, an OpenClaw agent with API access is one prompt injection away from
sending wire transfers with your Stripe key. With GVM, the agent can't even see the key,
wire transfers are structurally blocked, and the attempt is permanently recorded.

## Core repository

Source and docs: [skwuwu/Analemma-GVM](https://github.com/skwuwu/Analemma-GVM)
