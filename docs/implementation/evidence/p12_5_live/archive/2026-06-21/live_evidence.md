# Live Paper-Trading Evidence Report — momentum-portfolio v1.1 (momentum + vol-scaling)

_Generated 2026-06-21T10:32:22.193957+00:00 · git 9e19b1f · live paper book (read-only)_

> **Production-validation snapshot (P12.5).** The live complement to the §1–§3 backtest evidence — realized trades + a persisting equity curve + the operational/safety/verifiability trail. The book is still early, so live performance is *indicative*, accruing daily.

## Strategy
- **momentum-portfolio 0.3.0** — status **PAPER**; config **v1.1 (momentum + vol-scaling)** (vol-scaling ON @ 15%).

## Performance (live equity curve)

_Accruing — 1 daily snapshot(s) so far; the curve needs >=2 days. The equity-snapshot job persists one point per account near each market close._

## Book (current)
- Equity **$10,208.14** · cash $2,257.89 · gross exposure **78%** ($7,950) · unrealized P&L **$208.16** across 6 positions.

| Ticker | Qty | Market value | Unrealized P&L | % |
|---|---|---|---|---|
| BE | 7 | $2,302 | $364 | +18.8% |
| INTC | 15 | $2,010 | $89 | +4.6% |
| AAOI | 10 | $1,618 | $-263 | -14.0% |
| MU | 1 | $1,134 | $70 | +6.5% |
| MTDR | 9 | $446 | $-37 | -7.7% |
| ADC | 6 | $440 | $-15 | -3.2% |

## Realized trades (4; since 2026-06-15 14:50:09.741512)

| Order | Ticker | Side | Qty | Avg fill | Status |
|---|---|---|---|---|---|
| 7 | AAOI | BUY | 10 | $188.11 | FILLED |
| 8 | MU | BUY | 1 | $1,064.45 | FILLED |
| 9 | INTC | BUY | 15 | $128.05 | FILLED |
| 10 | BE | BUY | 7 | $276.96 | FILLED |

## Operational & safety evidence (the differentiator)

- **Risk gates fired:** 8 orders passed risk, **2 rejected by the risk engine** (+1 by broker) — *the gates demonstrably work, not just exist.*
- **Circuit breaker:** 1 trip(s), 1 reset(s) — the daily-loss breaker fired and recovered under the documented runbook.
- **Fills:** 7 reconciled into the book.

## Verifiability (provable, not just reported)

- Replay mismatches: **0** · reconciliation discrepancies: **0** → **clean** (every automated decision replays and reconciles). Audit chain: 72 consequential actions logged, hash-chained.

## Notes (P12.5)
- **Equity-curve history is now persisted** (the `equity_snapshot` daily job appends one point per account near market close) — the Performance section above accrues into a real live curve.
- Run this weekly/monthly; the equity curve + trade log + operational trail accumulate into the live track record. Turnover/slippage attribution is a later increment.
