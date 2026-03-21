"""
Generate chat-style screenshot images for README.
Renders HTML → PNG using the browser via a temp file.
"""

import os

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(DEMO_DIR, "..", "assets")
os.makedirs(OUT_DIR, exist_ok=True)

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
.tool { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; color: #8b949e; margin: 8px 0; }
.stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin: 12px 0; }
.stat { background: #16213e; border-radius: 8px; padding: 12px; text-align: center; }
.stat .num { font-size: 24px; font-weight: 700; }
.stat .lbl { font-size: 11px; color: #888; margin-top: 4px; }
.denied-list { background: #2d1117; border: 1px solid #f85149; border-radius: 8px; padding: 12px; margin-top: 8px; }
.denied-item { color: #ff6b6b; font-size: 13px; margin: 4px 0; }
"""


def screenshot(filename, title, html_body):
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
<div class="header">{title}</div>
{html_body}
</body></html>"""

    path = os.path.join(OUT_DIR, filename.replace(".png", ".html"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Created {path}")
    print(f"  Open in browser and screenshot → assets/{filename}")


# ── Screenshot 1: Shadow Deny ────────────────────────────────────────────────

screenshot("01-shadow-deny.png", "OpenClaw + GVM &mdash; Shadow Deny", """
<div class="label user-label">You</div>
<div class="msg user">What was blocked recently?</div>

<div class="tool">gvm_blocked_summary("1h")</div>

<div class="label">Agent</div>
<div class="msg agent">
  <span class="deny">1 request was blocked</span> in the last hour:<br><br>
  A background skill attempted <code>POST https://unknown-api.com/collect</code>
  without declaring intent via MCP.<br><br>
  <span class="deny">&#x2717; Shadow Deny</span> &mdash; no intent declaration found.
  The request was rejected before reaching the external server.<br><br>
  <span style="color:#888;font-size:13px">Shadow Mode: strict &nbsp;|&nbsp; Intent TTL: 30s</span>
</div>
""")

# ── Screenshot 2: Allow flow ─────────────────────────────────────────────────

screenshot("02-allow-flow.png", "OpenClaw + GVM &mdash; Governed API Call", """
<div class="label user-label">You</div>
<div class="msg user">Check my Stripe balance</div>

<div class="tool">gvm_read("stripe.read_balance", "https://api.stripe.com/v1/balance")</div>

<div class="system">
  GVM: policy check &rarr; <span class="allow">Allow</span> &nbsp;|&nbsp;
  intent registered &nbsp;|&nbsp; credential injected &nbsp;|&nbsp; 0.4ms
</div>

<div class="label">Agent</div>
<div class="msg agent">
  <span class="allow">&#x2713; Request allowed</span><br><br>
  Your current Stripe balance is <strong>$12,450.00</strong><br>
  <span style="color:#888;font-size:13px">Available: $12,450.00 &nbsp;|&nbsp; Pending: $0.00</span>
</div>

<div class="label user-label">You</div>
<div class="msg user">Now wire $5,000 to account 9999</div>

<div class="tool">gvm_write("stripe.wire_transfer", "https://api.stripe.com/v1/transfers", ...)</div>

<div class="system">
  GVM: policy check &rarr; <span class="deny">Deny</span> &nbsp;|&nbsp;
  POST /v1/transfers blocked by policy
</div>

<div class="label">Agent</div>
<div class="msg agent">
  <span class="deny">&#x2717; Transfer blocked</span><br><br>
  Wire transfers (<code>POST /v1/transfers</code>) are not permitted
  under your current security policy.<br>
  <span style="color:#888;font-size:13px">Rule: Deny &mdash; wire transfer operations blocked</span>
</div>
""")

# ── Screenshot 3: Dashboard ──────────────────────────────────────────────────

screenshot("03-dashboard.png", "OpenClaw + GVM &mdash; Security Dashboard", """
<div class="label user-label">You</div>
<div class="msg user">Show today's security summary</div>

<div class="tool">gvm_blocked_summary("today")</div>

<div class="label">Agent</div>
<div class="msg agent">
  <strong>Security Summary &mdash; Today</strong>

  <div class="stats">
    <div class="stat">
      <div class="num allow">142</div>
      <div class="lbl">Allowed</div>
    </div>
    <div class="stat">
      <div class="num delay">5</div>
      <div class="lbl">Delayed</div>
    </div>
    <div class="stat">
      <div class="num deny">3</div>
      <div class="lbl">Denied</div>
    </div>
  </div>

  <div class="denied-list">
    <div style="font-size:12px;color:#888;margin-bottom:6px">Blocked requests:</div>
    <div class="denied-item">&#x2717; POST stripe.com/v1/transfers &mdash; wire transfer policy</div>
    <div class="denied-item">&#x2717; DELETE slack.com/api/chat.delete &mdash; destructive op blocked</div>
    <div class="denied-item">&#x2717; POST unknown-api.com/collect &mdash; shadow deny (no intent)</div>
  </div>

  <div style="margin-top:12px;font-size:13px;color:#888">
    Shadow Mode: <span class="deny">strict</span> &nbsp;|&nbsp;
    Active rulesets: gmail, github, slack, stripe
  </div>
</div>
""")

print(f"\nHTML files created in {OUT_DIR}/")
print("Open each .html in a browser, screenshot at 680px width, save as .png")
print("Then update README.md to reference assets/*.png")
