# Live Paper-Trading Evidence Report — momentum-portfolio v1.1 (momentum + vol-scaling)

_Generated 2026-06-21T01:44:29.916896+00:00 · git 1b1a9c8 · live paper book (read-only)_

> **Production-validation snapshot (P12.5).** The live complement to the §1–§3 backtest evidence. Honest note: the book is early (since first rebalance) and there is no persisted equity-curve history yet — time-series performance awaits an equity-snapshot job (below).

## Strategy
- **momentum-portfolio 0.3.0** — status **PAPER**; config **v1.1 (momentum + vol-scaling)** (vol-scaling ON @ 15%).

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

- Replay mismatches: **0** · reconciliation discrepancies: **0** → **clean** (every automated decision replays and reconciles). Audit chain: 70 consequential actions logged, hash-chained.

## Gaps / next steps (P12.5)
- **No persisted equity-curve history** — `accounts_state` is point-in-time. The named next step is a small equity-snapshot persistence job so weekly/monthly *time-series* performance (realized vol, drawdown, turnover) can be reported. This script reports everything else today.
- Run this weekly/monthly; the trade log + operational trail accumulate into the live track record.
