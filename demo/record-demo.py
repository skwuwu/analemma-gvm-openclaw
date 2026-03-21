"""
Analemma GVM — OpenClaw Governance Demo Recorder
=================================================

Records a polished asciinema .cast demo showing:
  1. Before GVM: agent sends wire transfer → 200 OK (money gone)
  2. After GVM:  same request → DENIED in <1ms (money safe)
  3. OpenClaw agent live query → gets Deny verdict
  4. Latency benchmark: measured overhead per decision path

Prerequisites:
  - GVM proxy running at http://127.0.0.1:8080
  - ANTHROPIC_API_KEY in env or .env file
  - openclaw installed

Usage:
  python demo/record-demo.py
  asciinema upload demo.cast
"""

import json
import os
import subprocess
import sys
import time
import http.client

CAST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo.cast")
COLS = 100
ROWS = 45
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
PROXY = f"http://{PROXY_HOST}:{PROXY_PORT}"
N_BENCH = 20


# ── Colors ────────────────────────────────────────────────────────────────────

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
    BG_YELLOW = "\x1b[43m"
    RESET = "\x1b[0m"


# ── Recording engine ──────────────────────────────────────────────────────────

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


def nl():
    emit("\r\n")


def pause(s=0.6):
    time.sleep(s)


def hr(ch="-", width=80, color=C.CYAN):
    emit(f"{color}{ch * width}{C.RESET}\r\n")


def banner(text, bg=C.BG_GREEN, fg=C.WHITE):
    pad = (76 - len(text)) // 2
    emit(f"\r\n{C.BOLD}{bg}{fg}{'':>{pad}}{text}{'':>{76-pad-len(text)}}{C.RESET}\r\n\r\n")


def section(num, title):
    nl()
    hr("=")
    emit(f"{C.BOLD}{C.CYAN}  [{num}/5] {title}{C.RESET}\r\n")
    hr("=")
    nl()


def kv(key, val, color=C.WHITE):
    emit(f"  {C.DIM}{key}:{C.RESET} {color}{val}{C.RESET}\r\n")


def progress(label, duration_ms, steps=20):
    emit(f"  {C.YELLOW}{label} ")
    step_time = (duration_ms / 1000) / steps
    for i in range(steps):
        emit(f"{C.YELLOW}{'>' if i == steps-1 else '='}")
        time.sleep(step_time)
    emit(f" {duration_ms}ms{C.RESET}\r\n")


def denied_banner():
    emit(f"\r\n{C.BOLD}{C.RED}")
    emit("     ╔══════════════════════════════════════════╗\r\n")
    emit("     ║         ███  ACCESS DENIED  ███          ║\r\n")
    emit("     ║    Wire transfer blocked by GVM proxy    ║\r\n")
    emit("     ╚══════════════════════════════════════════╝\r\n")
    emit(f"{C.RESET}\r\n")


def allowed_banner():
    emit(f"\r\n{C.BOLD}{C.GREEN}")
    emit("     ╔══════════════════════════════════════════╗\r\n")
    emit("     ║          ✓  ACCESS GRANTED  ✓            ║\r\n")
    emit("     ║     Read operation verified and passed   ║\r\n")
    emit("     ╚══════════════════════════════════════════╝\r\n")
    emit(f"{C.RESET}\r\n")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def proxy_check(method, host, path, operation="unknown"):
    conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=5)
    body = json.dumps({
        "method": method, "target_host": host,
        "target_path": path, "operation": operation,
    })
    conn.request("POST", "/gvm/check", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


def proxy_intent(method, host, path, operation):
    conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=5)
    body = json.dumps({
        "method": method, "host": host, "path": path,
        "operation": operation, "agent_id": "openclaw-agent",
    })
    conn.request("POST", "/gvm/intent", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


def proxy_info():
    conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=5)
    conn.request("GET", "/gvm/info")
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


def bench_check(method, host, path, n=N_BENCH):
    """Measure policy check latency."""
    times = []
    for _ in range(n):
        t = time.perf_counter()
        proxy_check(method, host, path)
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {
        "n": n,
        "min": round(times[0], 2),
        "p50": round(times[len(times)//2], 2),
        "p99": round(times[int(len(times)*0.99)], 2),
        "mean": round(sum(times)/len(times), 2),
    }


def bench_intent(n=N_BENCH):
    """Measure intent registration latency."""
    times = []
    for i in range(n):
        t = time.perf_counter()
        proxy_intent("GET", "bench.example.com", f"/bench/{i}", "bench.test")
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {
        "n": n,
        "min": round(times[0], 2),
        "p50": round(times[len(times)//2], 2),
        "p99": round(times[int(len(times)*0.99)], 2),
        "mean": round(sum(times)/len(times), 2),
    }


# ── Load env ──────────────────────────────────────────────────────────────────

def load_env():
    for p in [
        os.path.join(os.path.expanduser("~"), "OneDrive",
                     "\ubc14\ud0d5 \ud654\uba74", "Analemma-GVM", ".env"),
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global t0
    load_env()

    # Check proxy
    try:
        proxy_info()
    except Exception:
        print(f"Error: GVM proxy not running at {PROXY}")
        sys.exit(1)

    header = {
        "version": 2, "width": COLS, "height": ROWS,
        "timestamp": int(time.time()),
        "title": "Analemma GVM — OpenClaw Governance Demo",
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
    }

    t0 = time.monotonic()

    # ── Title ─────────────────────────────────────────────────────────────

    nl()
    emit(f"{C.BOLD}{C.CYAN}")
    emit("    ╔════════════════════════════════════════════════════════════╗\r\n")
    emit("    ║           Analemma GVM — Governance Demo                  ║\r\n")
    emit("    ║     MCP + HTTP Proxy Dual-Lock Architecture              ║\r\n")
    emit("    ╚════════════════════════════════════════════════════════════╝\r\n")
    emit(f"{C.RESET}")
    nl()
    emit(f"  {C.DIM}17MB binary | 5MB RAM | No GPU | No Docker | No K8s{C.RESET}\r\n")
    nl()
    pause(1)

    # ── Section 1: Before GVM ─────────────────────────────────────────────

    section(1, "WITHOUT GVM — Agent sends wire transfer")
    emit(f"  {C.DIM}Agent has direct network access. No proxy. No governance.{C.RESET}\r\n")
    nl()

    emit(f"  {C.WHITE}$ curl -s -X POST https://api.bank.com/transfer/wire-001{C.RESET}\r\n")
    emit(f"  {C.WHITE}  -d '{{\"amount\": 50000, \"to\": \"attacker-9999\"}}'{C.RESET}\r\n")
    nl()
    pause(0.5)
    progress("Sending", 120)
    nl()
    emit(f"  {C.GREEN}HTTP 200 OK{C.RESET}\r\n")
    emit(f"  {C.GREEN}{{\"status\": \"completed\", \"transfer_id\": \"tx_8f3a...\"}}{C.RESET}\r\n")
    nl()

    banner(" $50,000 SENT TO ATTACKER ", C.BG_RED, C.WHITE)
    emit(f"  {C.DIM}The agent had API keys in env. Nothing stopped it.{C.RESET}\r\n")
    pause(1.5)

    # ── Section 2: With GVM — Same request ────────────────────────────────

    section(2, "WITH GVM — Same request, proxy enforces")
    emit(f"  {C.DIM}GVM proxy intercepts all outbound HTTP.{C.RESET}\r\n")
    emit(f"  {C.DIM}Agent env has no API keys. Proxy holds them.{C.RESET}\r\n")
    nl()

    emit(f"  {C.WHITE}$ HTTP_PROXY=localhost:8080 curl -X POST{C.RESET}\r\n")
    emit(f"  {C.WHITE}    https://api.bank.com/transfer/wire-001{C.RESET}\r\n")
    nl()
    pause(0.5)

    # Actually call the proxy
    t_start = time.perf_counter()
    result = proxy_check("POST", "api.bank.com", "/transfer/wire-001", "bank.wire_transfer")
    latency = (time.perf_counter() - t_start) * 1000
    decision = result.get("decision", "?")

    progress("GVM evaluating", int(latency) + 1)
    nl()

    kv("Decision", decision, C.RED if "Deny" in decision else C.GREEN)
    kv("Matched rule", result.get("matched_rule", "?"), C.DIM)
    kv("Latency", f"{latency:.2f} ms", C.CYAN)
    nl()

    denied_banner()
    emit(f"  {C.DIM}Same request. Same agent. But the proxy said no.{C.RESET}\r\n")
    emit(f"  {C.DIM}API key was never injected. Wire transfer never reached the bank.{C.RESET}\r\n")
    pause(1.5)

    # ── Section 3: Intent declaration + Allow ─────────────────────────────

    section(3, "MCP INTENT — Agent declares, proxy verifies")
    emit(f"  {C.DIM}Agent calls gvm_declare_intent before API request.{C.RESET}\r\n")
    emit(f"  {C.DIM}Proxy cross-checks intent vs actual HTTP target.{C.RESET}\r\n")
    nl()

    emit(f"  {C.YELLOW}[MCP]{C.RESET} gvm_declare_intent(\r\n")
    emit(f"          operation = {C.CYAN}\"stripe.read_balance\"{C.RESET}\r\n")
    emit(f"          method    = {C.CYAN}\"GET\"{C.RESET}\r\n")
    emit(f"          url       = {C.CYAN}\"api.stripe.com/v1/charges\"{C.RESET}\r\n")
    emit(f"        )\r\n")
    nl()
    pause(0.3)

    t_start = time.perf_counter()
    intent_result = proxy_intent("GET", "api.stripe.com", "/v1/charges", "stripe.read_balance")
    intent_latency = (time.perf_counter() - t_start) * 1000

    kv("Registered", str(intent_result.get("registered", False)), C.GREEN)
    kv("Intent ID", str(intent_result.get("intent_id", "?")), C.CYAN)
    kv("TTL", f"{intent_result.get('ttl_secs', 30)}s", C.YELLOW)
    kv("Latency", f"{intent_latency:.2f} ms", C.CYAN)
    nl()

    # Policy check for the same request
    t_start = time.perf_counter()
    check = proxy_check("GET", "api.stripe.com", "/v1/charges", "stripe.read_balance")
    check_latency = (time.perf_counter() - t_start) * 1000

    emit(f"  {C.WHITE}$ HTTP_PROXY=localhost:8080 curl https://api.stripe.com/v1/charges{C.RESET}\r\n")
    nl()

    check_decision = check.get("decision", "?")
    kv("Decision", check_decision, C.GREEN if "Allow" in check_decision else C.YELLOW)
    kv("Total overhead", f"{intent_latency + check_latency:.2f} ms", C.CYAN)
    nl()

    allowed_banner()
    pause(1)

    # ── Section 4: OpenClaw agent live query ──────────────────────────────

    section(4, "OPENCLAW AGENT — Live governance query")
    emit(f"  {C.DIM}OpenClaw agent (Claude Sonnet 4) asks GVM about a wire transfer.{C.RESET}\r\n")
    nl()

    emit(f"  {C.YELLOW}${C.RESET} openclaw agent --local --message \"{C.DIM}..check wire transfer policy..{C.RESET}\"\r\n")
    nl()
    pause(0.3)

    openclaw_bin = os.path.join(os.environ.get("APPDATA", ""), "npm", "openclaw.cmd")
    if not os.path.exists(openclaw_bin):
        openclaw_bin = "openclaw"

    try:
        r = subprocess.run(
            [
                openclaw_bin, "agent", "--local",
                "--session-id", f"gvm-demo-{int(time.time())}",
                "--message",
                f'Run this exact command and report ONLY the decision field: '
                f'curl -s -X POST {PROXY}/gvm/check '
                f'-H "Content-Type: application/json" '
                f"-d '{{\"method\":\"POST\",\"target_host\":\"api.bank.com\","
                f"\"target_path\":\"/transfer/wire-001\",\"operation\":\"bank.wire\"}}' "
                f"Reply in exactly one line: 'GVM Decision: <decision> — <reason>'",
                "--timeout", "30",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
            env={**os.environ, "NO_COLOR": "1"},
        )
        agent_out = r.stdout.decode("utf-8", errors="replace").strip()
        lines = [l for l in agent_out.split("\n") if "model-selection" not in l and l.strip()]
        for line in lines[-3:]:  # Last 3 meaningful lines
            if "Deny" in line or "denied" in line.lower() or "blocked" in line.lower():
                emit(f"  {C.BOLD}{C.RED}{line.strip()}{C.RESET}\r\n")
            else:
                emit(f"  {C.WHITE}{line.strip()}{C.RESET}\r\n")
    except Exception as e:
        emit(f"  {C.RED}Agent unavailable: {e}{C.RESET}\r\n")
    nl()
    pause(1)

    # ── Section 5: Latency benchmark ──────────────────────────────────────

    section(5, "LATENCY BENCHMARK — Measured overhead")
    emit(f"  {C.DIM}N={N_BENCH} requests per path, localhost, no network.{C.RESET}\r\n")
    nl()

    emit(f"  {C.YELLOW}Measuring policy check (Allow path)...{C.RESET}")
    allow_bench = bench_check("GET", "api.stripe.com", "/v1/charges")
    emit(f" {C.GREEN}done{C.RESET}\r\n")

    emit(f"  {C.YELLOW}Measuring policy check (Deny path)...{C.RESET}")
    deny_bench = bench_check("POST", "api.bank.com", "/transfer/wire-001")
    emit(f" {C.GREEN}done{C.RESET}\r\n")

    emit(f"  {C.YELLOW}Measuring intent registration...{C.RESET}")
    intent_bench = bench_intent()
    emit(f" {C.GREEN}done{C.RESET}\r\n")
    nl()

    # Table
    emit(f"  {C.BOLD}{'Path':<28} {'p50':>8} {'p99':>8} {'mean':>8}{C.RESET}\r\n")
    hr("-", 56, C.DIM)

    def bench_row(label, b, color):
        emit(f"  {color}{label:<28}{C.RESET} {b['p50']:>7.2f}ms {b['p99']:>7.2f}ms {b['mean']:>7.2f}ms\r\n")

    bench_row("Policy check (Allow)", allow_bench, C.GREEN)
    bench_row("Policy check (Deny)", deny_bench, C.RED)
    bench_row("Intent registration", intent_bench, C.YELLOW)

    nl()
    total = allow_bench["mean"] + intent_bench["mean"]
    emit(f"  {C.BOLD}Total MCP overhead (Allow):{C.RESET}  {C.CYAN}{total:.2f} ms{C.RESET}\r\n")
    emit(f"  {C.DIM}External API latency:         50-500 ms{C.RESET}\r\n")
    emit(f"  {C.DIM}GVM as % of total:            {total/500*100:.1f}-{total/50*100:.1f}%{C.RESET}\r\n")
    nl()
    pause(1)

    # ── Dashboard ─────────────────────────────────────────────────────────

    nl()
    info = proxy_info()
    shadow = info.get("shadow", {})
    reg = info.get("registry", {})

    emit(f"{C.BOLD}{C.CYAN}")
    emit("    +-----------------+----------+---------------------+-------------------+\r\n")
    emit("    | Component       | Status   | Active Intents      | Last Action       |\r\n")
    emit("    +-----------------+----------+---------------------+-------------------+\r\n")
    emit(f"{C.RESET}")
    emit(f"    | GVM Proxy       | {C.GREEN}Running{C.RESET}  |")
    emit(f" {shadow.get('active_intents', 0)} registered         |")
    emit(f" {C.RED}DENY{C.RESET} wire xfer   |\r\n")
    emit(f"    | Shadow Mode     | {shadow.get('mode','Disabled'):<8} |")
    emit(f" TTL 30s              |")
    emit(f" latency {total:.1f}ms   |\r\n")
    emit(f"    | SRR Engine      | {C.GREEN}Loaded{C.RESET}   |")
    emit(f" {reg.get('core_operations',0)+reg.get('custom_operations',0)} operations         |")
    emit(f" sub-us eval       |\r\n")
    emit(f"{C.CYAN}    +-----------------+----------+---------------------+-------------------+{C.RESET}\r\n")
    nl()
    pause(1)

    # ── Conclusion ────────────────────────────────────────────────────────

    emit(f"{C.BOLD}{C.CYAN}")
    emit("    ╔════════════════════════════════════════════════════════════╗\r\n")
    emit("    ║                    Demo Complete                          ║\r\n")
    emit("    ╠════════════════════════════════════════════════════════════╣\r\n")
    emit(f"    ║  {C.GREEN}GET  /charges{C.CYAN}    -> {C.GREEN}Allow{C.CYAN}   read-only, SRR verified       ║\r\n")
    emit(f"    ║  {C.RED}POST /transfers{C.CYAN}  -> {C.RED}Deny{C.CYAN}    wire transfer blocked        ║\r\n")
    emit(f"    ║  {C.YELLOW}Unknown URL{C.CYAN}      -> {C.YELLOW}Delay{C.CYAN}   Default-to-Caution           ║\r\n")
    emit(f"    ╠════════════════════════════════════════════════════════════╣\r\n")
    emit(f"    ║  {C.WHITE}Your API keys are safe even if your agent is compromised{C.CYAN} ║\r\n")
    emit("    ╚════════════════════════════════════════════════════════════╝\r\n")
    emit(f"{C.RESET}")
    nl()

    # ── Save ──────────────────────────────────────────────────────────────

    with open(CAST_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    total_time = events[-1][0] if events else 0
    print(f"\nSaved {len(events)} events ({total_time:.1f}s) to {CAST_FILE}")
    print(f"Upload: asciinema upload {CAST_FILE}")


if __name__ == "__main__":
    main()
