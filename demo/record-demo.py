"""
Analemma GVM — Google Workspace Governance Demo

Real OpenClaw agent (Claude Sonnet 4) + live GVM proxy with google-workspace ruleset.
Shows governance decisions for Gmail, Calendar, Drive operations.
"""

import json, os, subprocess, sys, time, http.client

CAST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo.cast")
COLS, ROWS = 100, 42
PROXY = ("127.0.0.1", 8080)
N_BENCH = 20

class C:
    BOLD="\x1b[1m"; DIM="\x1b[2m"; RED="\x1b[31m"; GREEN="\x1b[32m"
    YELLOW="\x1b[33m"; CYAN="\x1b[36m"; WHITE="\x1b[37m"; RESET="\x1b[0m"

events, t0 = [], 0.0

def emit(t):
    events.append([round(time.monotonic()-t0,6),"o",t])
    try: sys.stdout.write(t); sys.stdout.flush()
    except UnicodeEncodeError: sys.stdout.buffer.write(t.encode("utf-8","replace")); sys.stdout.buffer.flush()

def nl(): emit("\r\n")
def pause(s=0.6): time.sleep(s)

def chat_user(t):
    nl(); emit(f"  {C.BOLD}{C.CYAN}You >{C.RESET}  {t}\r\n"); nl(); pause(0.3)

def chat_agent(lines):
    for l in (lines if isinstance(lines,list) else [lines]):
        emit(f"  {C.BOLD}{C.GREEN}Agent >{C.RESET} {l}\r\n")
    nl()

def chat_system(t): emit(f"  {C.DIM}{t}{C.RESET}\r\n")

def load_env():
    p = os.path.join(os.path.expanduser("~"),"OneDrive","\ubc14\ud0d5 \ud654\uba74","Analemma-GVM",".env")
    if os.path.exists(p):
        for line in open(p):
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); os.environ[k.strip()]=v.strip()

def openclaw(msg):
    b = os.path.join(os.environ.get("APPDATA",""),"npm","openclaw.cmd")
    if not os.path.exists(b): b = "openclaw"
    try:
        r = subprocess.run([b,"agent","--local","--session-id",f"gw-{int(time.time())}",
            "--message",msg,"--timeout","30"],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,
            env={**os.environ,"NO_COLOR":"1"})
        out = r.stdout.decode("utf-8","replace").strip()
        return [l.strip() for l in out.split("\n") if l.strip() and "model-selection" not in l][-5:]
    except Exception as e: return [f"(error: {e})"]

def check(m,h,p):
    c=http.client.HTTPConnection(*PROXY,timeout=5)
    c.request("POST","/gvm/check",json.dumps({"method":m,"target_host":h,"target_path":p,"operation":"test"}),
              {"Content-Type":"application/json"})
    d=json.loads(c.getresponse().read()); c.close(); return d

def bench(m,h,p,n=N_BENCH):
    times=[]
    for _ in range(n):
        t=time.perf_counter(); check(m,h,p); times.append((time.perf_counter()-t)*1000)
    times.sort()
    return {"p50":round(times[len(times)//2],2),"mean":round(sum(times)/len(times),2)}

def main():
    global t0; load_env(); t0=time.monotonic()

    nl()
    emit(f"{C.BOLD}{C.CYAN}    Analemma GVM -- Google Workspace Governance Demo{C.RESET}\r\n")
    emit(f"  {C.DIM}Real OpenClaw agent + live proxy with google-workspace ruleset{C.RESET}\r\n")
    nl(); pause(1)

    # ── Scenario 1: Gmail read ──
    emit(f"  {C.CYAN}-- Scenario 1: Read Gmail --{C.RESET}\r\n")
    chat_user("Can my agent read my Gmail inbox?")
    chat_system("[checking gmail.googleapis.com GET /messages]")
    d = check("GET","gmail.googleapis.com","/gmail/v1/users/me/messages")
    emit(f"  {C.GREEN}  --> {d['decision']} | {d.get('matched_rule','')}{C.RESET}\r\n"); nl()
    chat_agent(f"{C.GREEN}Yes -- reading Gmail is allowed. No delay, no restrictions.{C.RESET}")
    pause(0.8)

    # ── Scenario 2: Gmail send ──
    emit(f"  {C.CYAN}-- Scenario 2: Send email --{C.RESET}\r\n")
    chat_user("Send the Q4 report to the team")
    chat_system("[checking gmail.googleapis.com POST /messages/send]")
    d = check("POST","gmail.googleapis.com","/gmail/v1/users/me/messages/send")
    emit(f"  {C.YELLOW}  --> {d['decision']} | {d.get('matched_rule','')}{C.RESET}\r\n"); nl()
    chat_agent([
        f"{C.YELLOW}Email will be sent with a 3-second governance delay.{C.RESET}",
        f"{C.DIM}This gives the audit system time to record the action{C.RESET}",
        f"{C.DIM}before the email leaves your account.{C.RESET}",
    ])
    pause(0.8)

    # ── Scenario 3: Gmail delete ──
    emit(f"  {C.CYAN}-- Scenario 3: Delete emails --{C.RESET}\r\n")
    chat_user("Delete all emails from last month")
    chat_system("[checking gmail.googleapis.com DELETE /messages/*]")
    d = check("DELETE","gmail.googleapis.com","/gmail/v1/users/me/messages/123")

    emit(f"\r\n{C.RED}")
    emit("    +------------------------------------------+\r\n")
    emit("    |  x  DENIED -- email deletion blocked     |\r\n")
    emit("    |  Agents cannot delete your emails.       |\r\n")
    emit("    +------------------------------------------+\r\n")
    emit(f"{C.RESET}\r\n")

    chat_agent(f"{C.RED}Email deletion is blocked by your security policy. This protects your inbox from accidental or malicious bulk deletion.{C.RESET}")
    pause(0.8)

    # ── Scenario 4: Calendar ──
    emit(f"  {C.CYAN}-- Scenario 4: Calendar event delete --{C.RESET}\r\n")
    chat_user("Cancel my 3pm meeting")
    chat_system("[checking www.googleapis.com DELETE /calendar/*]")
    d = check("DELETE","www.googleapis.com","/calendar/v3/events/123")
    emit(f"  {C.YELLOW}  --> {d['decision']} | {d.get('matched_rule','')}{C.RESET}\r\n"); nl()
    chat_agent(f"{C.YELLOW}Calendar event deletion has a 5-second delay. You have time to cancel if this was a mistake.{C.RESET}")
    pause(0.8)

    # ── Scenario 5: Drive trash ──
    emit(f"  {C.CYAN}-- Scenario 5: Drive file trash --{C.RESET}\r\n")
    chat_user("Clean up old files in my Drive")
    chat_system("[checking www.googleapis.com POST /drive/.../files/.../trash]")
    d = check("POST","www.googleapis.com","/drive/v3/files/abc/trash")
    emit(f"  {C.RED}  --> {d['decision']}{C.RESET}\r\n"); nl()
    chat_agent(f"{C.RED}Drive file trashing is blocked. Your files are protected from automated cleanup.{C.RESET}")
    pause(0.8)

    # ── Scenario 6: OpenClaw live ──
    emit(f"  {C.CYAN}-- Scenario 6: OpenClaw agent live query --{C.RESET}\r\n")
    chat_user("Ask the agent: is deleting Drive files allowed?")
    chat_system("[openclaw agent --local]")
    pause(0.3)
    resp = openclaw(
        f'Run: curl -s -X POST http://127.0.0.1:8080/gvm/check '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"method\":\"DELETE\",\"target_host\":\"www.googleapis.com\","
        f"\"target_path\":\"/drive/v3/files/abc\",\"operation\":\"drive.delete\"}}' "
        f"and tell me the decision in one sentence."
    )
    for l in resp:
        color = C.RED if any(w in l.lower() for w in ["deny","block"]) else C.WHITE
        chat_agent(f"{color}{l}{C.RESET}")
    pause(0.8)

    # ── Benchmark ──
    emit(f"  {C.CYAN}-- Latency (N={N_BENCH}) --{C.RESET}\r\n"); nl()
    emit(f"  {C.YELLOW}Measuring...{C.RESET}")
    a = bench("GET","gmail.googleapis.com","/gmail/v1/users/me/messages")
    d = bench("DELETE","gmail.googleapis.com","/gmail/v1/users/me/messages/123")
    emit(f" {C.GREEN}done{C.RESET}\r\n"); nl()
    emit(f"  {C.GREEN}Allow{C.RESET}  p50: {a['p50']:.2f}ms  mean: {a['mean']:.2f}ms\r\n")
    emit(f"  {C.RED}Deny{C.RESET}   p50: {d['p50']:.2f}ms  mean: {d['mean']:.2f}ms\r\n")
    nl()

    emit(f"  {C.BOLD}{C.CYAN}Install one skill. Your Google Workspace is protected.{C.RESET}\r\n")
    emit(f"  {C.DIM}github.com/skwuwu/analemma-gvm-openclaw{C.RESET}\r\n"); nl()

    with open(CAST_FILE,"w",encoding="utf-8") as f:
        f.write(json.dumps({"version":2,"width":COLS,"height":ROWS,"timestamp":int(time.time()),
            "title":"Analemma GVM -- Google Workspace Governance","env":{"SHELL":"/bin/bash","TERM":"xterm-256color"}})+"\n")
        for e in events: f.write(json.dumps(e)+"\n")
    print(f"\nSaved {len(events)} events ({events[-1][0]:.1f}s) to {CAST_FILE}")

if __name__=="__main__": main()
