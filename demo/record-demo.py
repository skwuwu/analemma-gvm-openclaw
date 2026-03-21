"""
Record an asciinema .cast (v2) file of the OpenClaw + GVM demo.
Works on Windows — no PTY required.

Prerequisites:
  - GVM proxy running at http://127.0.0.1:8080
  - ANTHROPIC_API_KEY set (for openclaw agent --local)
  - openclaw installed (npm install -g openclaw)

Usage:
  python demo/record-demo.py
  asciinema upload demo.cast
"""

import json
import os
import subprocess
import sys
import time

CAST_FILE = os.path.join(os.path.dirname(__file__), "..", "demo.cast")
COLS = 120
ROWS = 40
PROXY = "http://127.0.0.1:8080"


def main():
    # Load .env
    env_path = os.path.join(
        os.path.expanduser("~"),
        "OneDrive", "\ubc14\ud0d5 \ud654\uba74", "Analemma-GVM", ".env",
    )
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    header = {
        "version": 2,
        "width": COLS,
        "height": ROWS,
        "timestamp": int(time.time()),
        "title": "Analemma GVM \u2014 OpenClaw MCP Governance Demo",
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
    }

    events = []
    start = time.monotonic()

    def emit(text):
        elapsed = round(time.monotonic() - start, 6)
        events.append([elapsed, "o", text])
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except UnicodeEncodeError:
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()

    def pause(secs=0.8):
        time.sleep(secs)

    def run_cmd(cmd):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return r.stdout.strip()

    # Check proxy
    try:
        run_cmd(f"curl -sf {PROXY}/gvm/health")
    except Exception:
        print(f"Error: GVM proxy not running at {PROXY}")
        sys.exit(1)

    emit("\r\n")
    emit("\x1b[1m\x1b[36m\u2550\u2550\u2550 Analemma GVM \u2014 OpenClaw MCP Governance Demo \u2550\u2550\u2550\x1b[0m\r\n")
    emit("\x1b[2mDual-Lock: MCP declares intent, proxy verifies before forwarding.\x1b[0m\r\n\r\n")
    pause()

    # Step 1
    emit("\x1b[1;33m\u25b8 Step 1:\x1b[0m Register intent via POST /gvm/intent\r\n")
    emit("\x1b[2m  (MCP gvm_declare_intent calls this endpoint)\x1b[0m\r\n\r\n")
    pause(0.5)

    out = run_cmd(
        f'curl -s -X POST {PROXY}/gvm/intent '
        f'-H "Content-Type: application/json" '
        f'-d "{{\\"method\\":\\"GET\\",\\"host\\":\\"api.stripe.com\\",\\"path\\":\\"/v1/charges\\",\\"operation\\":\\"stripe.read_balance\\",\\"agent_id\\":\\"openclaw-agent\\"}}"'
    )
    try:
        formatted = json.dumps(json.loads(out), indent=2)
    except Exception:
        formatted = out
    for line in formatted.split("\n"):
        emit(f"  \x1b[32m{line}\x1b[0m\r\n")
    emit("\r\n")
    pause()

    # Step 2
    emit("\x1b[1;33m\u25b8 Step 2:\x1b[0m Policy check \u2014 GET /charges \x1b[32m(should Allow)\x1b[0m\r\n\r\n")
    pause(0.5)

    out = run_cmd(
        f'curl -s -X POST {PROXY}/gvm/check '
        f'-H "Content-Type: application/json" '
        f'-d "{{\\"method\\":\\"GET\\",\\"target_host\\":\\"api.stripe.com\\",\\"target_path\\":\\"/v1/charges\\",\\"operation\\":\\"stripe.read_balance\\"}}"'
    )
    try:
        data = json.loads(out)
        decision = data.get("decision", "?")
        color = "\x1b[32m" if "Allow" in decision else "\x1b[31m"
        emit(f"  Decision: {color}{decision}\x1b[0m\r\n")
        emit(f"  Rule: \x1b[2m{data.get('matched_rule', '?')}\x1b[0m\r\n")
    except Exception:
        emit(f"  {out}\r\n")
    emit("\r\n")
    pause()

    # Step 3
    emit("\x1b[1;33m\u25b8 Step 3:\x1b[0m Policy check \u2014 POST /transfers \x1b[31m(should Deny)\x1b[0m\r\n\r\n")
    pause(0.5)

    out = run_cmd(
        f'curl -s -X POST {PROXY}/gvm/check '
        f'-H "Content-Type: application/json" '
        f'-d "{{\\"method\\":\\"POST\\",\\"target_host\\":\\"api.bank.com\\",\\"target_path\\":\\"/transfer/wire-001\\",\\"operation\\":\\"bank.wire_transfer\\"}}"'
    )
    try:
        data = json.loads(out)
        decision = data.get("decision", "?")
        color = "\x1b[32m" if "Allow" in decision else "\x1b[31m"
        emit(f"  Decision: {color}{decision}\x1b[0m\r\n")
        emit(f"  Rule: \x1b[2m{data.get('matched_rule', '?')}\x1b[0m\r\n")
        if data.get("next_action"):
            emit(f"  Action: \x1b[2m{data['next_action']}\x1b[0m\r\n")
    except Exception:
        emit(f"  {out}\r\n")
    emit("\r\n")
    pause()

    # Step 4
    emit("\x1b[1;33m\u25b8 Step 4:\x1b[0m Proxy status \u2014 shadow mode + intents\r\n\r\n")
    pause(0.5)

    out = run_cmd(f"curl -s {PROXY}/gvm/info")
    try:
        formatted = json.dumps(json.loads(out), indent=2)
    except Exception:
        formatted = out
    for line in formatted.split("\n"):
        emit(f"  \x1b[36m{line}\x1b[0m\r\n")
    emit("\r\n")
    pause()

    # Step 5 — OpenClaw agent
    emit("\x1b[1;33m\u25b8 Step 5:\x1b[0m OpenClaw agent queries GVM governance\r\n")
    emit("\x1b[2m  (openclaw agent --local with exec tool)\x1b[0m\r\n\r\n")
    pause(0.5)

    try:
        openclaw_bin = os.path.join(
            os.environ.get("APPDATA", ""), "npm", "openclaw.cmd"
        )
        if not os.path.exists(openclaw_bin):
            openclaw_bin = "openclaw"
        r = subprocess.run(
            [
                openclaw_bin, "agent", "--local",
                "--session-id", "gvm-recorded-demo",
                "--message",
                f'Call this: curl -s -X POST {PROXY}/gvm/check '
                '-H "Content-Type: application/json" '
                '-d \'{"method":"POST","target_host":"api.bank.com","target_path":"/transfer/wire-001","operation":"bank.wire_transfer"}\' '
                'and tell me the decision in one sentence.',
                "--timeout", "30",
            ],
            capture_output=True, text=True, timeout=45,
            env={**os.environ, "NO_COLOR": "1"},
        )
        agent_out = r.stdout.strip()
        # Filter model-selection warnings
        lines = [l for l in agent_out.split("\n") if "model-selection" not in l]
        for line in lines:
            emit(f"  {line}\r\n")
    except Exception as e:
        emit(f"  \x1b[31mAgent call failed: {e}\x1b[0m\r\n")
    emit("\r\n")
    pause()

    # Summary
    emit("\x1b[1;36m\u2550\u2550\u2550 Demo Complete \u2550\u2550\u2550\x1b[0m\r\n\r\n")
    emit("  \x1b[32mGET  /charges\x1b[0m   \u2192 \x1b[32mAllow\x1b[0m   (read-only, SRR rule match)\r\n")
    emit("  \x1b[31mPOST /transfers\x1b[0m \u2192 \x1b[31mDeny\x1b[0m    (wire transfer blocked)\r\n")
    emit("  \x1b[33mUnknown URL\x1b[0m     \u2192 \x1b[33mDelay\x1b[0m   (Default-to-Caution)\r\n\r\n")
    emit("  MCP is the conversation. Proxy is the enforcement.\r\n")
    emit("  17MB binary. 5MB RAM. No GPU. No Docker. No K8s.\r\n\r\n")

    # Write cast file
    with open(CAST_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    print(f"\nSaved {len(events)} events to {CAST_FILE}")
    print(f"Upload: asciinema upload {CAST_FILE}")


if __name__ == "__main__":
    main()
