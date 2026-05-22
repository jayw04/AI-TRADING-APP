# Live-Mode Runbook

> ⚠ **Live mode places real orders against real money.** Defaults intentionally
> favor paper. Treat every step here as production-grade.

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
- The submit button picks up a `[LIVE]` prefix and a rose ring.
- Every Submit click in live mode opens `LiveConfirmModal`, which requires
  three independent confirmations:
  1. Checkbox: "I understand this is a live order."
  2. Checkbox: "I understand orders cannot be un-sent once accepted."
  3. Type the symbol exactly.
- There is intentionally no "remember my acknowledgement" affordance.

## Backend RiskEngine in live mode

The RiskEngine is **identical** between paper and live — the only mode-aware
check is the explicit `MODE_MISMATCH` guard that compares the trading mode
against `Account.mode`. Tightening for live trading happens by editing the
risk_limits row; see [`risk-limits.md`](risk-limits.md).

## Returning to paper at end of session

Always switch back to paper unless you intend to leave working live orders
open across sessions. Forgetting causes the "I thought I was in paper" class
of accident, which is the entire reason the banner is red and the modal
exists.
