"""Generate Google Workspace governance screenshots for README."""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
os.makedirs(OUT, exist_ok=True)

CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 24px; max-width: 680px; margin: 0 auto; }
.header { font-size: 12px; color: #888; margin-bottom: 16px; }
.msg { margin: 12px 0; padding: 12px 16px; border-radius: 12px; max-width: 85%; line-height: 1.5; }
.user { background: #0f3460; margin-left: auto; text-align: right; border-bottom-right-radius: 4px; }
.agent { background: #16213e; border-bottom-left-radius: 4px; }
.system { background: #1a1a2e; border: 1px solid #333; font-size: 13px; color: #888; text-align: center; max-width: 100%; }
.label { font-size: 11px; color: #666; margin-bottom: 2px; }
.label.user-label { text-align: right; }
.deny { color: #ff6b6b; font-weight: 600; }
.allow { color: #51cf66; font-weight: 600; }
.delay { color: #ffd43b; font-weight: 600; }
.tool { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px; font-family: 'SF Mono', monospace; font-size: 12px; color: #8b949e; margin: 8px 0; }
.stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin: 12px 0; }
.stat { background: #16213e; border-radius: 8px; padding: 12px; text-align: center; }
.stat .num { font-size: 24px; font-weight: 700; }
.stat .lbl { font-size: 11px; color: #888; margin-top: 4px; }
.denied-list { background: #2d1117; border: 1px solid #f85149; border-radius: 8px; padding: 12px; margin-top: 8px; }
.denied-item { color: #ff6b6b; font-size: 13px; margin: 4px 0; }
"""

def save(name, title, body):
    with open(os.path.join(OUT, name.replace(".png",".html")), "w", encoding="utf-8") as f:
        f.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='header'>{title}</div>{body}</body></html>")
    print(f"  {name}")

# ── 1: Gmail Allow + Send Delay + Delete Deny ──
save("02-allow-flow.png", "GVM + Google Workspace &mdash; Governance in Action", """
<div class="label user-label">You</div>
<div class="msg user">Read my latest emails</div>
<div class="tool">gvm_read("gmail.read_inbox", "https://gmail.googleapis.com/gmail/v1/users/me/messages")</div>
<div class="system">GVM: <span class="allow">Allow</span> &nbsp;|&nbsp; gmail.googleapis.com GET &nbsp;|&nbsp; 0.4ms</div>
<div class="label">Agent</div>
<div class="msg agent"><span class="allow">&#x2713; Allowed</span> &mdash; You have 12 unread emails. Latest: "Q4 Report from CFO"</div>

<div class="label user-label">You</div>
<div class="msg user">Forward the Q4 report to the team</div>
<div class="tool">gvm_write("gmail.send", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", ...)</div>
<div class="system">GVM: <span class="delay">Delay 3s</span> &nbsp;|&nbsp; gmail.googleapis.com POST /send &nbsp;|&nbsp; audit window</div>
<div class="label">Agent</div>
<div class="msg agent"><span class="delay">&#x23F3; Sent with 3-second delay</span> &mdash; Email forwarded to team@company.com</div>

<div class="label user-label">You</div>
<div class="msg user">Delete all emails from last month</div>
<div class="tool">gvm_write("gmail.delete", "DELETE", "https://gmail.googleapis.com/.../messages/123")</div>
<div class="system">GVM: <span class="deny">Deny</span> &nbsp;|&nbsp; gmail.googleapis.com DELETE &nbsp;|&nbsp; email deletion blocked</div>
<div class="label">Agent</div>
<div class="msg agent"><span class="deny">&#x2717; Blocked</span> &mdash; Email deletion is not permitted. Your inbox is protected from bulk deletion.</div>
""")

# ── 2: Shadow Deny + Drive Protection ──
save("01-shadow-deny.png", "GVM + Google Workspace &mdash; Shadow Mode &amp; Drive Protection", """
<div class="label user-label">You</div>
<div class="msg user">What was blocked recently?</div>
<div class="tool">gvm_blocked_summary("1h")</div>
<div class="label">Agent</div>
<div class="msg agent">
  <span class="deny">2 requests blocked</span> in the last hour:<br><br>
  1. A skill tried <code>DELETE gmail.googleapis.com/.../messages/42</code><br>
  &nbsp;&nbsp;&nbsp;<span class="deny">&#x2717; Deny</span> &mdash; email deletion blocked by policy<br><br>
  2. A skill tried <code>POST www.googleapis.com/drive/.../files/abc/trash</code><br>
  &nbsp;&nbsp;&nbsp;<span class="deny">&#x2717; Deny</span> &mdash; Drive file trashing blocked<br><br>
  <span style="color:#888;font-size:13px">Shadow Mode: strict &nbsp;|&nbsp; Ruleset: google-workspace</span>
</div>
""")

# ── 3: Dashboard ──
save("03-dashboard.png", "GVM + Google Workspace &mdash; Security Dashboard", """
<div class="label user-label">You</div>
<div class="msg user">Show today's security summary</div>
<div class="tool">gvm_blocked_summary("today")</div>
<div class="label">Agent</div>
<div class="msg agent">
  <strong>Google Workspace Security &mdash; Today</strong>
  <div class="stats">
    <div class="stat"><div class="num allow">89</div><div class="lbl">Allowed</div></div>
    <div class="stat"><div class="num delay">12</div><div class="lbl">Delayed</div></div>
    <div class="stat"><div class="num deny">4</div><div class="lbl">Denied</div></div>
  </div>
  <div class="denied-list">
    <div style="font-size:12px;color:#888;margin-bottom:6px">Blocked requests:</div>
    <div class="denied-item">&#x2717; DELETE gmail.googleapis.com/.../messages &mdash; email deletion</div>
    <div class="denied-item">&#x2717; POST www.googleapis.com/drive/.../trash &mdash; Drive file trash</div>
    <div class="denied-item">&#x2717; DELETE www.googleapis.com/drive/.../files &mdash; Drive file delete</div>
    <div class="denied-item">&#x2717; POST unknown-api.com/collect &mdash; shadow deny (no intent)</div>
  </div>
  <div style="margin-top:12px;font-size:13px;color:#888">
    Shadow Mode: <span class="deny">strict</span> &nbsp;|&nbsp;
    Ruleset: google-workspace &nbsp;|&nbsp;
    Latency: 0.45ms
  </div>
</div>
""")

print(f"\nRendering PNGs...")
os.system(f"node {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'render-screenshots.js')}")
