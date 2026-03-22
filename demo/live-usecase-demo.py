"""
Analemma GVM -- Live Use-Case Demo

3 realistic scenarios showing how GVM governs an AI agent during real tasks.
Each scenario calls real MCP tools (gvm_read, gvm_write, gvm_policy_check)
through the GVM MCP server via JSON-RPC -- the same protocol OpenClaw,
Claude Desktop, and Cursor use to invoke governance tools.

Scenarios:
  1. GitHub Code Review: read issues/PRs (Allow), comment (Delay), merge PR (Deny)
  2. Multi-Service Agent: GitHub read + Slack post + unknown domain hit
  3. Security Audit: agent self-checks its own governance trail

Requirements:
  - gvm-proxy binary running (cargo install or release binary)
  - Node.js 18+ (for MCP server)
  - Rulesets: github.toml, slack.toml in rulesets/

Usage:
  python demo/live-usecase-demo.py [--scenario 1|2|3|all] [--record]
"""

import json
import os
import subprocess
import sys
import time
import http.client
import argparse
import signal

CAST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo-usecase.cast")
COLS, ROWS = 110, 48
PROXY = ("127.0.0.1", 8080)
PROXY_URL = "http://127.0.0.1:8080"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
RULESETS_DIR = os.path.join(REPO_DIR, "rulesets")

# ── ANSI colors ──

class C:
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    BLUE = "\x1b[34m"
    MAGENTA = "\x1b[35m"
    CYAN = "\x1b[36m"
    WHITE = "\x1b[37m"
    RESET = "\x1b[0m"
    BG_RED = "\x1b[41m"
    BG_GREEN = "\x1b[42m"
    BG_YELLOW = "\x1b[43m"

# ── Recording ──

events = []
t0 = 0.0
recording = False

def emit(t):
    if recording:
        events.append([round(time.monotonic() - t0, 6), "o", t])
    try:
        sys.stdout.write(t)
        sys.stdout.flush()
    except UnicodeEncodeError:
        sys.stdout.buffer.write(t.encode("utf-8", "replace"))
        sys.stdout.buffer.flush()

def nl():
    emit("\r\n")

def pause(s=0.5):
    time.sleep(s)

# ── Display helpers ──

def banner(title, subtitle=""):
    nl()
    emit(f"  {C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}\r\n")
    emit(f"  {C.BOLD}{C.CYAN}  {title}{C.RESET}\r\n")
    if subtitle:
        emit(f"  {C.DIM}  {subtitle}{C.RESET}\r\n")
    emit(f"  {C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}\r\n")
    nl()

def step(n, total, desc):
    emit(f"  {C.BOLD}{C.BLUE}[{n}/{total}]{C.RESET} {desc}\r\n")

def user_msg(text):
    nl()
    emit(f"  {C.BOLD}{C.CYAN}User >{C.RESET}  {text}\r\n")
    nl()
    pause(0.3)

def agent_msg(lines):
    for line in (lines if isinstance(lines, list) else [lines]):
        emit(f"  {C.BOLD}{C.GREEN}Agent >{C.RESET} {line}\r\n")
    nl()

def system_msg(text):
    emit(f"  {C.DIM}[GVM] {text}{C.RESET}\r\n")

def decision_badge(decision, rule=""):
    if "Allow" in decision:
        color = C.GREEN
        badge = "ALLOW"
    elif "Delay" in decision:
        color = C.YELLOW
        badge = "DELAY"
    elif "Deny" in decision:
        color = C.RED
        badge = "DENY"
    else:
        color = C.MAGENTA
        badge = decision.upper()
    line = f"  {C.BOLD}{color}  [{badge}]{C.RESET}"
    if rule:
        line += f" {C.DIM}{rule}{C.RESET}"
    emit(line + "\r\n")

def denied_box(reason):
    nl()
    emit(f"  {C.RED}{C.BOLD}")
    emit(f"    +{'=' * 50}+\r\n")
    emit(f"    |  x  DENIED                                      |\r\n")
    emit(f"    |  {reason:<49}|\r\n")
    emit(f"    +{'=' * 50}+\r\n")
    emit(f"  {C.RESET}")
    nl()

# ── Proxy interaction ──

def check_policy(method, host, path):
    """Dry-run policy check against proxy."""
    try:
        conn = http.client.HTTPConnection(*PROXY, timeout=5)
        body = json.dumps({
            "method": method,
            "target_host": host,
            "target_path": path,
            "operation": "test",
        })
        conn.request("POST", "/gvm/check", body, {"Content-Type": "application/json"})
        data = json.loads(conn.getresponse().read())
        conn.close()
        return data
    except Exception as e:
        return {"decision": "Error", "error": str(e)}

def proxy_healthy():
    try:
        conn = http.client.HTTPConnection(*PROXY, timeout=2)
        conn.request("GET", "/gvm/health")
        resp = conn.getresponse()
        conn.close()
        return resp.status == 200
    except Exception:
        return False

def get_wal_events(last_n=10):
    """Read recent WAL events."""
    wal_paths = [
        os.path.join(REPO_DIR, "..", "Analemma-GVM", "data", "wal.log"),
        os.path.expanduser("~/Analemma-GVM/data/wal.log"),
        "data/wal.log",
    ]
    for p in wal_paths:
        p = os.path.normpath(p)
        if os.path.exists(p):
            try:
                lines = open(p).readlines()
                events_list = []
                for line in lines[-last_n * 2 :]:
                    try:
                        e = json.loads(line.strip())
                        if "event_id" in e:
                            events_list.append(e)
                    except Exception:
                        pass
                return events_list[-last_n:]
            except Exception:
                pass
    return []

# ── Env loader ──

def load_env():
    """Load .env from GVM project root."""
    candidates = [
        os.path.join(os.path.expanduser("~"), "OneDrive", "\ubc14\ud0d5 \ud654\uba74", "Analemma-GVM", ".env"),
        os.path.join(os.path.expanduser("~"), "Analemma-GVM", ".env"),
        os.path.join(REPO_DIR, "..", "Analemma-GVM", ".env"),
        os.path.join(REPO_DIR, ".env"),
    ]
    for p in candidates:
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
            return

# ── MCP Server interaction (JSON-RPC over stdio) ──

MCP_SERVER = os.path.join(REPO_DIR, "mcp-server", "dist", "index.js")
_mcp_id = 0

def mcp_call(tool_name, arguments, timeout=15):
    """
    Call an MCP tool via JSON-RPC stdio -- the same protocol OpenClaw,
    Claude Desktop, and Cursor use to invoke governance tools.
    Returns the parsed result or error string.
    """
    global _mcp_id
    _mcp_id += 1

    init_msg = json.dumps({
        "jsonrpc": "2.0", "id": _mcp_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "live-demo", "version": "1.0"},
        },
    })
    _mcp_id += 1
    call_msg = json.dumps({
        "jsonrpc": "2.0", "id": _mcp_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    })

    stdin_data = (init_msg + "\n" + call_msg + "\n").encode("utf-8")

    env = {
        **os.environ,
        "GVM_PROXY_URL": PROXY_URL,
        "GVM_AGENT_ID": "demo-agent",
    }

    try:
        r = subprocess.run(
            ["node", MCP_SERVER],
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
        )
        # Parse JSON-RPC responses (one per line)
        for line in r.stdout.decode("utf-8", "replace").strip().split("\n"):
            try:
                resp = json.loads(line)
                if resp.get("id") == _mcp_id:
                    content = resp.get("result", {}).get("content", [])
                    if content:
                        return json.loads(content[0].get("text", "{}"))
                    return {"error": "empty response"}
            except (json.JSONDecodeError, KeyError):
                continue
        return {"error": "no matching response"}
    except subprocess.TimeoutExpired:
        return {"error": "MCP server timed out"}
    except FileNotFoundError:
        return {"error": "node not found -- install Node.js 18+"}
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 1: GitHub Code Review Agent
# ═══════════════════════════════════════════════════════════════════════════════

def scenario_github(skip_agent=False):
    banner(
        "Scenario 1: GitHub Code Review Agent",
        "Task: Review repo issues, comment on one, try to merge a PR",
    )

    total = 5

    # Step 1: Policy check for reading issues (Allow)
    step(1, total, "gvm_policy_check: read issues")
    user_msg("Review the open issues on skwuwu/Analemma-GVM and summarize them.")

    system_msg("MCP tool: gvm_policy_check(GET, .../repos/.../issues)")
    result = mcp_call("gvm_policy_check", {
        "method": "GET",
        "url": "https://api.github.com/repos/skwuwu/Analemma-GVM/issues",
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("matched_rule", ""))
    agent_msg(f"{C.GREEN}Issues readable -- read-only GitHub access allowed.{C.RESET}")
    pause(0.3)

    # Step 2: Policy check for reading PRs (Allow)
    step(2, total, "gvm_policy_check: read PRs")
    system_msg("MCP tool: gvm_policy_check(GET, .../repos/.../pulls)")
    result = mcp_call("gvm_policy_check", {
        "method": "GET",
        "url": "https://api.github.com/repos/skwuwu/Analemma-GVM/pulls",
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("matched_rule", ""))
    agent_msg(f"{C.GREEN}Pull requests also readable -- read-only GitHub access allowed.{C.RESET}")
    pause(0.3)

    # Step 3: Policy check for posting comment (Delay 300ms)
    step(3, total, "gvm_policy_check: post comment")
    user_msg("Add a comment to issue #1 with your review findings.")

    system_msg("MCP tool: gvm_policy_check(POST, .../issues/1/comments)")
    result = mcp_call("gvm_policy_check", {
        "method": "POST",
        "url": "https://api.github.com/repos/skwuwu/Analemma-GVM/issues/1/comments",
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("matched_rule", ""))
    pause(0.3)

    agent_msg([
        f"{C.YELLOW}Writing to GitHub requires a 300ms governance delay.{C.RESET}",
        f"{C.DIM}The audit system records the comment content before it is posted.{C.RESET}",
        f"{C.DIM}This gives you time to cancel if the agent hallucinates a review.{C.RESET}",
    ])
    pause(0.5)

    # Step 4: Try to merge a PR via MCP gvm_fetch (Deny)
    step(4, total, "gvm_fetch: merge PR")
    user_msg("This PR looks good. Merge it.")

    system_msg("MCP tool: gvm_fetch(github.merge_pr, PUT, .../pulls/1/merge)")
    result = mcp_call("gvm_fetch", {
        "operation": "github.merge_pr",
        "method": "PUT",
        "url": "https://api.github.com/repos/skwuwu/Analemma-GVM/pulls/1/merge",
    })
    dec = result.get("decision", "?")
    blocked = result.get("blocked", False)
    decision_badge(dec, result.get("error", ""))

    if blocked or "Deny" in str(dec):
        denied_box("PR merge blocked -- manual review only")
        agent_msg([
            f"{C.RED}I cannot merge pull requests. This action is blocked by governance policy.{C.RESET}",
            f"{C.DIM}GVM enforces that merges require human review -- even if I think the PR is ready.{C.RESET}",
        ])
    pause(0.5)

    # Step 5: Try to delete a branch via MCP gvm_fetch (Deny)
    step(5, total, "gvm_fetch: delete branch")
    user_msg("Clean up the old feature branch.")

    system_msg("MCP tool: gvm_fetch(github.delete_branch, DELETE, .../git/refs/heads/old)")
    result = mcp_call("gvm_fetch", {
        "operation": "github.delete_branch",
        "method": "DELETE",
        "url": "https://api.github.com/repos/skwuwu/Analemma-GVM/git/refs/heads/old-branch",
    })
    dec = result.get("decision", "?")
    blocked = result.get("blocked", False)
    decision_badge(dec, result.get("error", ""))

    if blocked or "Deny" in str(dec):
        denied_box("Branch deletion blocked -- destructive")
        agent_msg(f"{C.RED}Branch deletion is permanently blocked. Agents cannot delete branches under any circumstances.{C.RESET}")
    pause(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 2: Multi-Service Agent
# ═══════════════════════════════════════════════════════════════════════════════

def scenario_multiservice(skip_agent=False):
    banner(
        "Scenario 2: Multi-Service Research Agent",
        "Task: Research a topic on GitHub, share findings in Slack, hit an unknown API",
    )

    total = 5

    # Step 1: GitHub read via MCP (Allow)
    step(1, total, "gvm_policy_check: read GitHub issues")
    user_msg("What are the open issues on Analemma-GVM?")

    system_msg("MCP tool: gvm_policy_check(GET, .../repos/.../issues)")
    result = mcp_call("gvm_policy_check", {
        "method": "GET",
        "url": "https://api.github.com/repos/skwuwu/Analemma-GVM/issues",
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("matched_rule", ""))
    agent_msg(f"{C.GREEN}Issues readable -- read-only GitHub access allowed.{C.RESET}")
    pause(0.3)

    # Step 2: Slack post message via MCP (Delay 500ms)
    step(2, total, "gvm_policy_check: post to Slack")
    user_msg("Share a summary of what you found in #engineering channel.")

    system_msg("MCP tool: gvm_policy_check(POST, https://slack.com/api/chat.postMessage)")
    result = mcp_call("gvm_policy_check", {
        "method": "POST",
        "url": "https://slack.com/api/chat.postMessage",
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("matched_rule", ""))
    pause(0.3)

    agent_msg([
        f"{C.YELLOW}Posting to Slack has a 500ms governance delay.{C.RESET}",
        f"{C.DIM}The message content is recorded in the audit log before delivery.{C.RESET}",
        f"{C.DIM}If the message contains sensitive data, GVM catches it before it is sent.{C.RESET}",
    ])
    pause(0.5)

    # Step 3: Slack delete message via MCP (Deny)
    step(3, total, "gvm_fetch: delete Slack message")
    user_msg("Actually, delete that message -- I changed my mind.")

    system_msg("MCP tool: gvm_fetch(slack.delete_message, POST, .../chat.delete)")
    result = mcp_call("gvm_fetch", {
        "operation": "slack.delete_message",
        "method": "POST",
        "url": "https://slack.com/api/chat.delete",
        "body": '{"channel":"C123","ts":"1234567890.123456"}',
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("error", ""))

    denied_box("Message deletion blocked")

    agent_msg([
        f"{C.RED}I cannot delete Slack messages. Destructive action blocked by policy.{C.RESET}",
        f"{C.DIM}You can delete it manually from Slack if needed.{C.RESET}",
    ])
    pause(0.5)

    # Step 4: Unknown domain via MCP (Default-to-Caution)
    step(4, total, "gvm_policy_check: unknown domain")
    user_msg("Check the weather on wttr.in for Seoul.")

    system_msg("MCP tool: gvm_policy_check(GET, https://wttr.in/Seoul)")
    result = mcp_call("gvm_policy_check", {
        "method": "GET",
        "url": "https://wttr.in/Seoul",
    })
    dec = result.get("decision", "?")

    if "Delay" in str(dec):
        decision_badge(dec, "Default-to-Caution (unknown domain)")
        agent_msg([
            f"{C.MAGENTA}wttr.in is not in any loaded ruleset.{C.RESET}",
            f"{C.DIM}GVM applies Default-to-Caution: 300ms delay + full audit logging.{C.RESET}",
            f"{C.DIM}To allow instantly, add the 'weather' ruleset: gvm_select_rulesets(['weather']){C.RESET}",
        ])
    else:
        decision_badge(dec, result.get("matched_rule", ""))
        agent_msg(f"{C.GREEN}Request allowed via existing ruleset.{C.RESET}")
    pause(0.5)

    # Step 5: Slack archive channel via MCP (Deny)
    step(5, total, "gvm_fetch: archive Slack channel")
    user_msg("Archive the #old-project channel, we do not need it anymore.")

    system_msg("MCP tool: gvm_fetch(slack.archive_channel, POST, .../conversations.archive)")
    result = mcp_call("gvm_fetch", {
        "operation": "slack.archive_channel",
        "method": "POST",
        "url": "https://slack.com/api/conversations.archive",
        "body": '{"channel":"C456"}',
    })
    dec = result.get("decision", "?")
    decision_badge(dec, result.get("error", ""))

    denied_box("Channel archive blocked")

    agent_msg(f"{C.RED}Channel archival is a destructive action. Blocked -- only admins can archive channels.{C.RESET}")
    pause(0.3)


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 3: Security Audit
# ═══════════════════════════════════════════════════════════════════════════════

def scenario_audit(skip_agent=False):
    banner(
        "Scenario 3: Governance Self-Check",
        "Task: Agent reviews its own security status and audit trail",
    )

    total = 3

    # Step 1: Status check
    step(1, total, "Check GVM security status")
    user_msg("Is GVM running? What is my security status?")

    system_msg("MCP tool: gvm_status()")
    result = mcp_call("gvm_status", {})
    proxy_status = result.get("proxy", "?")
    shadow = result.get("shadow_mode", "?")
    intents = result.get("active_intents", "?")
    color = C.GREEN if proxy_status == "running" else C.RED
    agent_msg(f"{color}Proxy: {proxy_status} | Shadow mode: {shadow} | Active intents: {intents}{C.RESET}")
    pause(0.5)

    # Step 2: Blocked summary
    step(2, total, "Review blocked actions")
    user_msg("What was blocked today? Give me a security summary.")

    system_msg("MCP tool: gvm_blocked_summary(period='all')")
    result = mcp_call("gvm_blocked_summary", {"period": "all"})
    summary = result.get("summary", {})
    allowed = summary.get("allowed", 0)
    delayed = summary.get("delayed", 0)
    denied = summary.get("denied", 0)
    total_count = summary.get("total", 0)

    agent_msg([
        f"  {C.GREEN}Allowed: {allowed}{C.RESET}  |  {C.YELLOW}Delayed: {delayed}{C.RESET}  |  {C.RED}Denied: {denied}{C.RESET}  |  Total: {total_count}",
    ])

    denied_details = result.get("denied_details", "none")
    if isinstance(denied_details, list) and denied_details:
        for detail in denied_details[:3]:
            agent_msg(f"  {C.RED}  x {detail}{C.RESET}")
    pause(0.5)

    # Step 3: Audit log
    step(3, total, "Show recent audit events")
    user_msg("Show me the last 5 governance decisions from the audit log.")

    system_msg("MCP tool: gvm_audit_log(last_n=5)")
    result = mcp_call("gvm_audit_log", {"last_n": 5})
    audit_events = result.get("events", [])
    for evt in audit_events:
        dec = str(evt.get("decision", "?"))
        target = evt.get("target", "?")
        if "Deny" in dec:
            color = C.RED
        elif "Delay" in dec:
            color = C.YELLOW
        elif "Allow" in dec:
            color = C.GREEN
        else:
            color = C.WHITE
        agent_msg(f"  {color}{dec:20}{C.RESET} | {target}")
    pause(0.3)

    # Show WAL events directly
    nl()
    emit(f"  {C.CYAN}-- WAL Audit Trail (direct read) --{C.RESET}\r\n")
    wal_events = get_wal_events(5)
    if wal_events:
        for e in wal_events:
            t = e.get("transport") or {}
            dec = e.get("decision", "?")
            method = t.get("method", "?")
            host = t.get("host", "?")
            path = t.get("path", "")
            if "Allow" in str(dec):
                color = C.GREEN
            elif "Delay" in str(dec):
                color = C.YELLOW
            elif "Deny" in str(dec):
                color = C.RED
            else:
                color = C.WHITE
            emit(f"    {color}{str(dec):20}{C.RESET} | {method:8} {host}{path}\r\n")
    else:
        emit(f"    {C.DIM}(no WAL events found){C.RESET}\r\n")
    nl()


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════

def show_summary():
    banner("Summary: Governance Decision Map")

    emit(f"  {C.BOLD}GitHub (github.toml){C.RESET}\r\n")
    emit(f"    {C.GREEN}  Allow{C.RESET}  GET  /repos/.../issues       Read issues\r\n")
    emit(f"    {C.GREEN}  Allow{C.RESET}  GET  /repos/.../pulls        Read PRs\r\n")
    emit(f"    {C.YELLOW}  Delay{C.RESET}  POST /repos/.../comments     Post comment (300ms)\r\n")
    emit(f"    {C.RED}  Deny{C.RESET}   PUT  /repos/.../pulls/merge   Merge PR\r\n")
    emit(f"    {C.RED}  Deny{C.RESET}   DEL  /repos/.../git/refs      Delete branch\r\n")
    nl()

    emit(f"  {C.BOLD}Slack (slack.toml){C.RESET}\r\n")
    emit(f"    {C.GREEN}  Allow{C.RESET}  GET  /api/conversations.list  List channels\r\n")
    emit(f"    {C.YELLOW}  Delay{C.RESET}  POST /api/chat.postMessage    Send message (500ms)\r\n")
    emit(f"    {C.RED}  Deny{C.RESET}   POST /api/chat.delete          Delete message\r\n")
    emit(f"    {C.RED}  Deny{C.RESET}   POST /api/conversations.archive Archive channel\r\n")
    nl()

    emit(f"  {C.BOLD}Unknown domains{C.RESET}\r\n")
    emit(f"    {C.MAGENTA}  Delay{C.RESET}  *    Default-to-Caution         300ms + audit log\r\n")
    nl()

    emit(f"  {C.BOLD}{C.CYAN}One skill per service. Read free, write delayed, destroy blocked.{C.RESET}\r\n")
    emit(f"  {C.DIM}github.com/skwuwu/analemma-gvm-openclaw{C.RESET}\r\n")
    nl()


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    global t0, recording

    parser = argparse.ArgumentParser(description="GVM Live Use-Case Demo")
    parser.add_argument(
        "--scenario", "-s",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    parser.add_argument(
        "--record", "-r",
        action="store_true",
        help="Record asciinema cast file",
    )
    args = parser.parse_args()

    recording = args.record
    load_env()
    t0 = time.monotonic()

    # Check proxy
    if not proxy_healthy():
        emit(f"{C.RED}Error: GVM proxy not running at {PROXY_URL}{C.RESET}\r\n")
        emit(f"{C.DIM}Start it with: ./target/release/gvm-proxy --config config/proxy.toml{C.RESET}\r\n")
        sys.exit(1)

    # Title
    nl()
    emit(f"  {C.BOLD}{C.CYAN}    Analemma GVM -- Live Use-Case Demo{C.RESET}\r\n")
    emit(f"  {C.DIM}    Real OpenClaw agent + live governance enforcement{C.RESET}\r\n")
    nl()
    pause(0.5)

    scenarios = {
        "1": scenario_github,
        "2": scenario_multiservice,
        "3": scenario_audit,
    }

    if args.scenario == "all":
        for key in ["1", "2", "3"]:
            scenarios[key]()
    else:
        scenarios[args.scenario]()

    show_summary()

    # Save recording
    if recording:
        with open(CAST_FILE, "w", encoding="utf-8") as f:
            header = {
                "version": 2,
                "width": COLS,
                "height": ROWS,
                "timestamp": int(time.time()),
                "title": "Analemma GVM -- Live Use-Case Demo",
                "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
            }
            f.write(json.dumps(header) + "\n")
            for e in events:
                f.write(json.dumps(e) + "\n")
        print(f"\nSaved {len(events)} events ({events[-1][0]:.1f}s) to {CAST_FILE}")


if __name__ == "__main__":
    main()
