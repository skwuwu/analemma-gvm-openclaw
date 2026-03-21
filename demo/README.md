# Shadow Mode Demo

Demonstrates the dual-lock architecture without OpenClaw installed.

## What it shows

| Scenario | Agent behavior | Result |
|----------|---------------|--------|
| 1 | Declares intent via `/gvm/intent`, then requests | **Allow** |
| 2 | Skips intent, requests directly | **Deny** (shadow strict) |
| 3 | Declares intent for `/get`, requests `/post` | **Deny** (cross-check) |

## Run

```bash
# Terminal 1: start proxy with shadow mode
GVM_CONFIG=demo/proxy-config/proxy.toml gvm-proxy

# Terminal 2: run demo
bash demo/shadow-mode-demo.sh
```

## Requirements

- `gvm-proxy` binary (no OpenClaw, no Docker, no GPU)
- `curl`
- That's it.
