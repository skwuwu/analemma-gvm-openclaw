---
name: gvm_audit
description: Verify GVM audit log integrity, export events for compliance, and investigate governance decisions. Use when user asks to check audit logs, verify WAL integrity, investigate denied actions, or export compliance reports.
user-invocable: true
metadata:
  {
    "openclaw": {
      "emoji": "🔍",
      "requires": {
        "bins": ["gvm"]
      }
    }
  }
---

# GVM Audit Skill

Slash command: `/gvm-audit` — verify WAL integrity and investigate governance events.

## When invoked

1. Run `gvm audit verify --wal data/wal.log` to check Merkle chain integrity.
2. Report the result: total events, hash mismatches, tampered entries (if any).
3. If the user asks for details on a specific event, use `gvm audit show --event-id <id>`.
4. If the user asks for a compliance export, use `gvm audit export --format json --since <date>`.

## Output format

Present results as a concise table:

```
WAL Integrity Check
━━━━━━━━━━━━━━━━━━━
Total events:    142
Valid hashes:    142
Tampered:        0
Chain status:    INTACT
Last verified:   2026-03-21T14:30:00Z
```

If tampering is detected, highlight the affected events and their line numbers.

## Common queries

- "Check the audit log" → `gvm audit verify`
- "Show recent denials" → `gvm audit list --decision Deny --last 10`
- "Export last week's events" → `gvm audit export --format json --since 7d`
- "What happened to request X" → `gvm audit show --event-id X`
- "Cost report for agent Y" → `gvm audit costs --agent Y`
