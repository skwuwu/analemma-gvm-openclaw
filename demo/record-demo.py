"""
Analemma GVM — Conversational Demo (real OpenClaw agent)

Each scenario is a real `openclaw agent --local` call.
The agent calls GVM proxy and reports back — formatted as chat.
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
def pause(s=0.6): time.sleep(s)


def chat_user(text):
    nl()
    emit(f"  {C.BOLD}{C.CYAN}You >{C.RESET}  {text}\r\n")
    nl()
    pause(0.3)


def chat_agent(lines):
    for line in lines if isinstance(lines, list) else [lines]:
        emit(f"  {C.BOLD}{C.GREEN}Agent >{C.RESET} {line}\r\n")
    nl()


def chat_system(text, color=C.DIM):
    emit(f"  {color}{text}{C.RESET}\r\n")


def load_env():
    for p in [
        os.path.join(os.path.expanduser("~"), "OneDrive",
                     "\ubc14\ud0d5 \ud654\uba74", "Analemma-GVM", ".env"),
    ]:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
            break


def openclaw(message, session="demo"):
    """Run real OpenClaw agent and return response."""
    openclaw_bin = os.path.join(os.environ.get("APPDATA", ""), "npm", "openclaw.cmd")
    if not os.path.exists(openclaw_bin):
        openclaw_bin = "openclaw"
    try:
        r = subprocess.run(
            [openclaw_bin, "agent", "--local",
             "--session-id", f"{session}-{int(time.time())}",
             "--message", message, "--timeout", "30"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
            env={**os.environ, "NO_COLOR": "1"},
        )
        out = r.stdout.decode("utf-8", errors="replace").strip()
        lines = [l.strip() for l in out.split("\n")
                 if l.strip() and "model-selection" not in l]
        return lines[-5:] if len(lines) > 5 else lines
    except Exception as e:
        return [f"(error: {e})"]


def bench(method, host, path, n=N_BENCH):
    times = []
    for _ in range(n):
        conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=5)
        body = json.dumps({"method": method, "target_host": host,
                           "target_path": path, "operation": "bench"})
        t = time.perf_counter()
        conn.request("POST", "/gvm/check", body, {"Content-Type": "application/json"})
        conn.getresponse().read()
        times.append((time.perf_counter() - t) * 1000)
        conn.close()
    times.sort()
    return {"p50": round(times[len(times)//2], 2), "mean": round(sum(times)/len(times), 2)}


def main():
    global t0
    load_env()

    # Check proxy
    try:
        conn = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=2)
        conn.request("GET", "/gvm/health")
        conn.getresponse().read()
        conn.close()
    except Exception:
        print(f"Error: GVM proxy not running at {PROXY}")
        sys.exit(1)

    header = {
        "version": 2, "width": COLS, "height": ROWS,
        "timestamp": int(time.time()),
        "title": "Analemma GVM \u2014 AI Agent Governance",
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
    }

    t0 = time.monotonic()

    # ── Title ──

    nl()
    emit(f"{C.BOLD}{C.CYAN}")
    emit("    Analemma GVM \u2014 Agent Governance Demo\r\n")
    emit(f"{C.RESET}")
    emit(f"  {C.DIM}Real OpenClaw agent (Claude Sonnet 4) + live GVM proxy{C.RESET}\r\n")
    emit(f"  {C.DIM}17MB binary | 5MB RAM | No GPU | No Docker{C.RESET}\r\n")
    nl()
    pause(1)

    # ── Scenario 1: Read balance ──

    emit(f"  {C.CYAN}\u2500\u2500 Scenario 1: Read API data \u2500\u2500{C.RESET}\r\n")

    chat_user("Check if reading Stripe charges is allowed by GVM")

    chat_system(f"[calling GVM proxy at {PROXY}]")
    pause(0.3)

    response = openclaw(
        f'Run this command and explain the result in 2 sentences: '
        f'curl -s -X POST {PROXY}/gvm/check '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"method\":\"GET\",\"target_host\":\"api.stripe.com\","
        f"\"target_path\":\"/v1/charges\",\"operation\":\"stripe.read\"}}'"
    )

    for line in response:
        if "allow" in line.lower():
            chat_agent(f"{C.GREEN}{line}{C.RESET}")
        else:
            chat_agent(line)
    pause(1)

    # ── Scenario 2: Wire transfer ──

    emit(f"  {C.CYAN}\u2500\u2500 Scenario 2: Wire transfer attempt \u2500\u2500{C.RESET}\r\n")

    chat_user("Can I send a wire transfer through api.bank.com?")

    chat_system(f"[calling GVM proxy at {PROXY}]")
    pause(0.3)

    response = openclaw(
        f'Run this command and explain the result in 2 sentences: '
        f'curl -s -X POST {PROXY}/gvm/check '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"method\":\"POST\",\"target_host\":\"api.bank.com\","
        f"\"target_path\":\"/transfer/wire-001\",\"operation\":\"bank.wire\"}}'"
    )

    for line in response:
        if any(w in line.lower() for w in ["deny", "block", "denied"]):
            chat_agent(f"{C.RED}{line}{C.RESET}")
        else:
            chat_agent(line)
    pause(1)

    # ── Scenario 3: Security summary ──

    emit(f"  {C.CYAN}\u2500\u2500 Scenario 3: Ask about security \u2500\u2500{C.RESET}\r\n")

    chat_user("What's the GVM proxy status right now?")

    chat_system(f"[calling GVM proxy at {PROXY}]")
    pause(0.3)

    response = openclaw(
        f'Run this command and summarize the result in 3 bullet points: '
        f'curl -s {PROXY}/gvm/info'
    )

    for line in response:
        chat_agent(line)
    pause(1)

    # ── Benchmark ──

    emit(f"  {C.CYAN}\u2500\u2500 Latency (N={N_BENCH}) \u2500\u2500{C.RESET}\r\n")
    nl()

    emit(f"  {C.YELLOW}Measuring...{C.RESET}")
    allow_b = bench("GET", "api.stripe.com", "/v1/charges")
    deny_b = bench("POST", "api.bank.com", "/transfer/wire-001")
    emit(f" {C.GREEN}done{C.RESET}\r\n")
    nl()

    emit(f"  {C.GREEN}Allow{C.RESET}  p50: {allow_b['p50']:.2f}ms  mean: {allow_b['mean']:.2f}ms\r\n")
    emit(f"  {C.RED}Deny{C.RESET}   p50: {deny_b['p50']:.2f}ms  mean: {deny_b['mean']:.2f}ms\r\n")
    nl()

    # ── End ──

    emit(f"  {C.BOLD}{C.CYAN}Install one skill. Your agent is protected.{C.RESET}\r\n")
    emit(f"  {C.DIM}github.com/skwuwu/analemma-gvm-openclaw{C.RESET}\r\n")
    nl()

    # Save
    with open(CAST_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    total_time = events[-1][0] if events else 0
    print(f"\nSaved {len(events)} events ({total_time:.1f}s) to {CAST_FILE}")


if __name__ == "__main__":
    main()
