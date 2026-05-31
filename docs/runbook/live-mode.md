# Live-Mode Runbook

> ⚠ **Live mode places real orders against real money.** Defaults intentionally
> favor paper. Treat every step here as production-grade.

> **P5 §1 update — per-account broker_mode.** P5 is reworking live mode from the
> process-wide `WORKBENCH_TRADING_MODE` flag (described below, still accurate for
> the adapter the RiskEngine reads) to a per-account `accounts.mode`
> (`paper`/`live`). As of P5 §1: a red LIVE banner shows whenever the user has
> **any** live account; `OrderRouter.submit()` raises `BrokerModeError` for any
> live account (HTTP 400) **before** the risk engine runs; and live account
> creation via `POST /api/v1/accounts` is refused (the §7 activation wizard owns
> it). **Live order submission is not yet enabled** — so the per-order
> `LiveConfirmModal` flow in "Per-order safeguards" below is dormant until P5 §7;
> in §1 the Order Ticket simply disables submit for a live account. See the P5 §1
> section near the bottom of this file for the full §1 posture.

## Default state

`.env.example` does not set `WORKBENCH_TRADING_MODE`; the app config default
in `app/config.py` is `"paper"`. The frontend ModeBanner is amber for paper
and red for live; if the backend is unreachable it shows a neutral "connecting"
state.

## Enabling live mode

Two conditions must be true:

1. `WORKBENCH_TRADING_MODE=live` is set in `.env` (or in your shell
   environment when running outside Docker).
2. `ALPACA_LIVE_API_KEY` and `ALPACA_LIVE_API_SECRET` are populated.

If `WORKBENCH_TRADING_MODE=live` but the live credentials are blank, the
backend startup raises during the credential-load step (see
`app/brokers/alpaca/credentials.py`). Fix the creds before retrying.

The RiskEngine reads the trading mode from
`OrderRouter.submit()` at evaluation time
(`"paper" if self._adapter.is_paper else "live"`). Switching modes therefore
requires an adapter restart — the backend doesn't hot-swap. A restart is
fine: it's the boundary at which `WORKBENCH_TRADING_MODE` is read.

### Step by step

1. Generate a live API key + secret in Alpaca's live dashboard.
   The live URL is `app.alpaca.markets`, distinct from the paper URL
   `paper-app.alpaca.markets` — double-check before copying creds.
2. Stop the backend: `docker compose down` (or `Ctrl-C` if running
   `scripts/dev.sh` in foreground).
3. Edit `.env`:

   ```
   WORKBENCH_TRADING_MODE=live
   ALPACA_LIVE_API_KEY=YOUR_LIVE_KEY
   ALPACA_LIVE_API_SECRET=YOUR_LIVE_SECRET
   ```

4. Start: `./scripts/dev.sh`.
5. Open the UI. Verify the banner is **RED** and reads "LIVE TRADING".
6. Verify the Dashboard shows your live equity / buying power, not the paper
   numbers.
7. Place a 1-share test order on the cheapest symbol you trust to absorb the
   round-trip cost. Confirm it appears in the Alpaca live dashboard.
8. **Close the test position immediately** before you forget it's there.

## Disabling live mode

1. Stop the backend.
2. Set `WORKBENCH_TRADING_MODE=paper` in `.env` (or simply delete the line —
   the app config default is `paper`).
3. Start. Verify the banner is amber.

## Emergency: an unintended live order

If you submitted a live order you didn't mean to:

1. Open the Orders page and click **Cancel** on the working row.
2. If already filled, open the Positions page and click **Close** on that
   row. The Close action routes through `POST /api/v1/positions/{symbol}/close`,
   which goes through the same OrderRouter as the ticket (ADR 0002).
3. If both fail (broker outage, UI broken): open Alpaca's web dashboard at
   `app.alpaca.markets` and close the position there directly.
4. Stop the backend (`docker compose down`).
5. Set `WORKBENCH_TRADING_MODE=paper` before restarting.
6. Audit `audit_log` for everything that happened during the live session:

   ```bash
   docker compose exec backend python -c "
   import asyncio
   from sqlalchemy import select
   from app.db.models.audit_log import AuditLog
   from app.db.session import get_sessionmaker
   async def main():
       factory = get_sessionmaker()
       async with factory() as s:
           rows = (await s.execute(
               select(AuditLog).order_by(AuditLog.id.desc()).limit(50)
           )).scalars().all()
           for r in rows:
               print(r.ts, r.action, r.target_id, r.payload_json)
   asyncio.run(main())
   "
   ```

   Or, more simply, query the SQLite file directly from outside the container.

## Per-order safeguards (frontend)

Layered on top of the backend RiskEngine:

- The ModeBanner is red and pulses gently.
- The OrderTicket header shows a red **Live** pill.
- **(P5 §1)** When the selected account is live, the OrderTicket shows a red
  "LIVE ACCOUNT" warning and the submit button is **disabled** ("Submit (live
  disabled)") — live submission isn't enabled yet, so the ticket refuses up
  front rather than round-tripping to a backend that will 400.
- **(Dormant until P5 §7)** The `LiveConfirmModal` typed-confirmation flow —
  two acknowledgement checkboxes plus typing the symbol exactly, with no
  "remember my acknowledgement" affordance — returns when real live submission
  ships. It is not wired into the ticket in P5 §1.

## Backend RiskEngine in live mode

The RiskEngine is **identical** between paper and live — the only mode-aware
check is the explicit `MODE_MISMATCH` guard that compares the trading mode
against `Account.mode`. Tightening for live trading happens by editing the
risk_limits row; see [`risk-limits.md`](risk-limits.md).

## P5 §1 posture (per-account broker_mode)

What is live-aware as of P5 §1, independent of the `WORKBENCH_TRADING_MODE`
flag above:

- **`accounts.mode`** (`AccountMode` enum) types each account paper/live.
  **`accounts.broker_mode_locked_at`** records when an account was activated to
  live (set by the §7 wizard; declared now, unread in §1).
- **`risk_limits.broker_mode`** scopes each limits row paper/live; the
  RiskEngine resolves limits filtered by the account's mode, so a live trade
  only matches live-scoped limits. Existing rows backfilled to `paper`. If a
  live account has no live-scoped limits, the engine rejects with
  `NO_LIMITS_CONFIGURED` — fail loud, never silently apply paper limits to live.
- **OrderRouter refuses live before the risk engine** with `BrokerModeError`
  ("Live trading is not yet enabled. See P5 §2 release notes."), structured-logged
  as `order_router_refused_live`. The orders API maps it to HTTP 400.
  Hash-chained audit-logging of the live path lands in P5 §8.
- **Account creation:** `POST /api/v1/accounts` creates paper accounts (201);
  live → 400 (deferred to the §7 wizard); duplicate `(user, broker, mode)` → 409.

To exercise the §1 surfaces manually (the API refuses live creation by design),
inject a live account row directly, refresh the browser to see the red banner +
disabled ticket, then delete it:

```bash
apps/backend/.venv/Scripts/python.exe - <<'PY'
import sqlite3
c = sqlite3.connect("apps/backend/data/workbench.sqlite")
c.execute(
    "INSERT INTO accounts(user_id, broker, mode, label, broker_mode_locked_at, created_at)"
    " VALUES (1, 'alpaca', 'live', 'Test Live', datetime('now'), datetime('now'))"
)
c.commit()
# ...verify in the UI, then:
c.execute("DELETE FROM accounts WHERE label='Test Live'")
c.commit()
PY
```

## Returning to paper at end of session

Always switch back to paper unless you intend to leave working live orders
open across sessions. Forgetting causes the "I thought I was in paper" class
of accident, which is the entire reason the banner is red and the modal
exists.
