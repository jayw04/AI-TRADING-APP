# Symbol mapping gaps

> **Placeholder.** This runbook is reserved by [P0 Checklist §9.2](../implementation/TradingWorkbench_P0_Checklist_v0.1.md) and references `Implementation Plan v0.2 §19`. That doc hasn't landed in the repo yet — content lives here once the symbol-mapping subsystem comes online in P1.

## What this will cover (P1+)

When Alpaca returns a ticker we don't have in our local `symbols` table — because of corporate actions (ticker change, M&A, delisting), a new IPO not yet ingested, or a typo in a TradingView alert — the backend needs a deterministic policy:

1. **Detection** — where the gap surfaces (order placement, fill ingestion, position reconciliation, TradingView webhook).
2. **Classification** — is the symbol genuinely unknown, renamed, or just stale in our cache?
3. **Resolution** — auto-create with `active=false`, prompt the trader, or hard-reject the order.
4. **Audit** — every gap event gets a row in `audit_log` with enough context to back-fill `symbols` later.

## Why this is its own runbook

Symbol mapping is one of those quiet sources of incidents in trading systems — the trader places an order for `META` but the system silently uses an old `FB` row; corporate actions go un-replayed; reconciliation reports drift. The right answer is rarely "auto-create and move on" — it's "log, halt the affected path, ask the human."

## Operator actions you might run someday

Stubbed out so the file isn't empty:

```bash
# (placeholder) inspect recent gap events
sqlite3 data/workbench.sqlite \
  "SELECT ts, action, target_id, payload_json FROM audit_log
   WHERE action LIKE 'symbol.gap.%' ORDER BY ts DESC LIMIT 20;"

# (placeholder) backfill a single symbol after a corporate action
# python scripts/symbol_admin.py upsert META --name "Meta Platforms" --exchange NASDAQ
```

These commands don't exist yet. Update this file when they do.
