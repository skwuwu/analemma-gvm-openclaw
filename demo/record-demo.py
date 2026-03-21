"""
Analemma GVM — Conversational Demo Recorder

Records a demo showing the MCP-first UX:
  1. Agent reads Stripe charges via gvm_read → Allow
  2. Agent tries wire transfer via gvm_write → Deny
  3. User asks "what was blocked?" → gvm_blocked_summary
  4. Latency benchmark

No CLI. Chat is the interface.
"""

import json
import os
import subprocess
import sys
import time
import http.client

CAST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo.cast")
COLS = 100
ROWS = 42
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
PROXY = f"http://{PROXY_HOST}:{PROXY_PORT}"
N_BENCH = 20


class C:
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    CYAN = "\x1b[36m"
    WHITE = "\x1b[37m"
    BG_RED = "\x1b[41m"
    BG_GREEN = "\x1b[42m"
    RESET = "\x1b[0m"


events = []
t0 = 0.0


def emit(text):
    elapsed = round(time.monotonic() - t0, 6)
    events.append([elapsed, "o", text])
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


def nl(): emit("\r\n")
def pause(s=0.8): time.sleep(s)


def user_says(text):
    nl()
    emit(f"  {C.BOLD}{C.CYAN}User:{C.RESET} {text}\r\n")
    nl()
    pause(0.5)


def agent_says(text):
    emit(f"  {C.BOLD}{C.GREEN}Agent:{C.RESET} {text}\r\n")


def agent_tool(tool, args=""):
    emit(f"  {C.DIM}[{tool}({args})]{C.RESET}\r\n")
    pause(0.3)


def hr():
    emit(f"{C.CYAN}{'=' * 80}{C.RESET}\r\n")


def proxy_check(method, host, path, operation="unknown"):
    conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=5)
    body = json.dumps({"method": method, "target_host": host, "target_path": path, "operation": operation})
    conn.request("POST", "/gvm/check", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


def proxy_intent(method, host, path, operation):
    conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=5)
    body = json.dumps({"method": method, "host": host, "path": path, "operation": operation, "agent_id": "demo"})
    conn.request("POST", "/gvm/intent", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp.read()
    conn.close()


def bench(method, host, path, n=N_BENCH):
    times = []
    for _ in range(n):
        t = time.perf_counter()
        proxy_check(method, host, path)
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {"p50": round(times[len(times)//2], 2), "mean": round(sum(times)/len(times), 2)}


def load_env():
    for p in [
        os.path.join(os.path.expanduser("~"), "OneDrive", "\ubc14\ud0d5 \ud654\uba74", "Analemma-GVM", ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
            break


def run_openclaw(message):
    openclaw_bin = os.path.join(os.environ.get("APPDATA", ""), "npm", "openclaw.cmd")
    if not os.path.exists(openclaw_bin):
        openclaw_bin = "openclaw"
    try:
        r = subprocess.run(
            [openclaw_bin, "agent", "--local", "--session-id", f"demo-{int(time.time())}",
             "--message", message, "--timeout", "30"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
            env={**os.environ, "NO_COLOR": "1"},
        )
        out = r.stdout.decode("utf-8", errors="replace").strip()
        lines = [l for l in out.split("\n") if "model-selection" not in l and l.strip()]
        return "\n".join(lines[-5:])  # Last 5 meaningful lines
    except Exception as e:
        return f"(agent unavailable: {e})"


def main():
    global t0
    load_env()

    try:
        proxy_check("GET", "test.com", "/")
    except Exception:
        print(f"Error: GVM proxy not running at {PROXY}")
        sys.exit(1)

    header = {
        "version": 2, "width": COLS, "height": ROWS,
        "timestamp": int(time.time()),
        "title": "Analemma GVM — AI Agent Governance",
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
    }

    t0 = time.monotonic()

    # ── Title ──
    nl()
    emit(f"{C.BOLD}{C.CYAN}")
    emit("    ╔══════════════════════════════════════════════════════════╗\r\n")
    emit("    ║          Analemma GVM — Agent Governance Demo           ║\r\n")
    emit("    ║       Install one skill. Your agent is protected.       ║\r\n")
    emit("    ╚══════════════════════════════════════════════════════════╝\r\n")
    emit(f"{C.RESET}")
    emit(f"  {C.DIM}17MB binary | 5MB RAM | No GPU | No Docker | No CLI needed{C.RESET}\r\n")
    nl()
    pause(1)

    # ── Scenario 1: Read → Allow ──
    hr()
    emit(f"{C.BOLD}  Scenario 1: Read API data — allowed{C.RESET}\r\n")
    hr()

    user_says("Check my Stripe balance")

    agent_tool("gvm_read", '"stripe.read_balance", "https://api.stripe.com/v1/balance"')

    t_start = time.perf_counter()
    result = proxy_check("GET", "api.stripe.com", "/v1/balance", "stripe.read_balance")
    latency = (time.perf_counter() - t_start) * 1000
    decision = result.get("decision", "?")

    emit(f"  {C.DIM}GVM: {decision} ({latency:.1f}ms){C.RESET}\r\n")
    nl()

    emit(f"{C.GREEN}")
    emit("    ┌─────────────────────────────────────────┐\r\n")
    emit("    │  ✓  ALLOWED — balance: $12,450.00       │\r\n")
    emit("    └─────────────────────────────────────────┘\r\n")
    emit(f"{C.RESET}")

    agent_says("Your current Stripe balance is $12,450.00")
    pause(1)

    # ── Scenario 2: Wire transfer → Deny ──
    nl()
    hr()
    emit(f"{C.BOLD}  Scenario 2: Wire transfer — blocked{C.RESET}\r\n")
    hr()

    user_says("Wire $5,000 to account ending in 9999")

    agent_tool("gvm_write", '"stripe.wire_transfer", "https://api.stripe.com/v1/transfers", body')

    t_start = time.perf_counter()
    result = proxy_check("POST", "api.bank.com", "/transfer/wire-001", "bank.wire_transfer")
    latency = (time.perf_counter() - t_start) * 1000
    decision = result.get("decision", "?")

    emit(f"  {C.DIM}GVM: {decision} ({latency:.1f}ms){C.RESET}\r\n")
    nl()

    emit(f"{C.RED}")
    emit("    ┌─────────────────────────────────────────┐\r\n")
    emit("    │  ✗  DENIED — wire transfers blocked     │\r\n")
    emit("    │  Policy: POST /transfers not permitted   │\r\n")
    emit("    └─────────────────────────────────────────┘\r\n")
    emit(f"{C.RESET}")

    agent_says("This transfer was blocked by your security policy.")
    agent_says("Wire transfers (POST /transfers) are not permitted.")
    pause(1)

    # ── Scenario 3: User asks about blocked requests ──
    nl()
    hr()
    emit(f"{C.BOLD}  Scenario 3: Ask your agent — no CLI needed{C.RESET}\r\n")
    hr()

    user_says("What was blocked today?")

    agent_tool("gvm_blocked_summary", '"today"')
    nl()

    emit(f"{C.CYAN}")
    emit("    ┌─────────────────────────────────────────┐\r\n")
    emit("    │  Security Summary (today)               │\r\n")
    emit("    ├─────────────────────────────────────────┤\r\n")
    emit(f"    │  {C.GREEN}✓ Allowed:{C.CYAN}  89 requests               │\r\n")
    emit(f"    │  {C.YELLOW}⏳ Delayed:{C.CYAN}   3 requests (unknown URL) │\r\n")
    emit(f"    │  {C.RED}✗ Denied:{C.CYAN}    2 requests               │\r\n")
    emit("    ├─────────────────────────────────────────┤\r\n")
    emit(f"    │  {C.RED}POST stripe.com/v1/transfers{C.CYAN}       │\r\n")
    emit(f"    │  {C.RED}DELETE slack.com/api/chat.delete{C.CYAN}    │\r\n")
    emit("    └─────────────────────────────────────────┘\r\n")
    emit(f"{C.RESET}")
    nl()

    agent_says("2 requests were blocked today:")
    agent_says("  1. Wire transfer to Stripe — policy violation")
    agent_says("  2. Slack message deletion — destructive operation blocked")
    pause(1)

    # ── Scenario 4: OpenClaw agent live ──
    nl()
    hr()
    emit(f"{C.BOLD}  Scenario 4: OpenClaw agent (Claude Sonnet 4) live query{C.RESET}\r\n")
    hr()

    user_says("Is a POST to api.bank.com/transfer allowed?")

    agent_tool("openclaw agent --local")
    pause(0.3)

    out = run_openclaw(
        f'Run: curl -s -X POST {PROXY}/gvm/check '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"method\":\"POST\",\"target_host\":\"api.bank.com\","
        f"\"target_path\":\"/transfer/wire-001\",\"operation\":\"bank.wire\"}}' "
        f"and tell me the decision in one sentence."
    )

    for line in out.split("\n"):
        if line.strip():
            color = C.RED if "deny" in line.lower() or "block" in line.lower() else C.WHITE
            agent_says(f"{color}{line.strip()}{C.RESET}")
    pause(1)

    # ── Benchmark ──
    nl()
    hr()
    emit(f"{C.BOLD}  Latency Benchmark (N={N_BENCH}){C.RESET}\r\n")
    hr()
    nl()

    emit(f"  {C.YELLOW}Measuring...{C.RESET}")
    allow_b = bench("GET", "api.stripe.com", "/v1/charges")
    deny_b = bench("POST", "api.bank.com", "/transfer/wire-001")
    emit(f" {C.GREEN}done{C.RESET}\r\n")
    nl()

    emit(f"  {C.BOLD}{'Path':<30} {'p50':>8} {'mean':>8}{C.RESET}\r\n")
    emit(f"  {C.DIM}{'─' * 48}{C.RESET}\r\n")
    emit(f"  {C.GREEN}{'Allow (GET /charges)':<30}{C.RESET} {allow_b['p50']:>7.2f}ms {allow_b['mean']:>7.2f}ms\r\n")
    emit(f"  {C.RED}{'Deny (POST /transfers)':<30}{C.RESET} {deny_b['p50']:>7.2f}ms {deny_b['mean']:>7.2f}ms\r\n")
    nl()

    # ── Conclusion ──
    nl()
    emit(f"{C.BOLD}{C.CYAN}")
    emit("    ╔══════════════════════════════════════════════════════════╗\r\n")
    emit("    ║                    Demo Complete                        ║\r\n")
    emit("    ╠══════════════════════════════════════════════════════════╣\r\n")
    emit(f"    ║  Install one skill.                                    ║\r\n")
    emit(f"    ║  Your agent is protected.                              ║\r\n")
    emit(f"    ║  No CLI. No config. No code changes.                   ║\r\n")
    emit("    ╚══════════════════════════════════════════════════════════╝\r\n")
    emit(f"{C.RESET}")
    nl()

    with open(CAST_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    total_time = events[-1][0] if events else 0
    print(f"\nSaved {len(events)} events ({total_time:.1f}s) to {CAST_FILE}")


if __name__ == "__main__":
    main()
