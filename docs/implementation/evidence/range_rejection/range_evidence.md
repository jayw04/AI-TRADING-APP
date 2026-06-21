# Range Trader — Rejection Evidence (REJECTED)

_git 9e43abe · PLTR VWAP {'entry_sigma': 2.0, 'exit_sigma': 0.5, 'stop_sigma': 3.0} · 2026-01-02..2026-06-12 · alpaca_iex_5min RTH (intraday history ~6 months = ONE regime — walk-forward is depth-limited; the single-regime caveat is load-bearing)_

> Completes the §5c research program (walk-forward + bootstrap) and records the governance verdict. Archived as the platform's **first formally-rejected strategy** — the Evidence Engineering thesis in action: *the platform validated AND declined a strategy.*

## Hypothesis
_RangeTraderVWAP has a robust intraday mean-reversion edge_ — tested on the best prior config (the only one that ever cleared IS).

## 1. Full-window edge + bootstrap (decisive)

- **102 trades** · profit factor **1.271** · mean per-trade P&L **$15.14** · win rate 55% · total $1,545.
- **Bootstrap 95% CI of mean per-trade P&L: [$-19.74, $57.53]** — INCLUDES zero → no demonstrable edge.

## 2. Walk-forward consistency

| Window | Trades | Profit factor | Mean P&L |
|---|---|---|---|
| 2026-01-02..2026-02-11 | 29 | 1.691 | $49.23 |
| 2026-02-11..2026-03-23 | 25 | 1.141 | $7.1 |
| 2026-03-23..2026-05-02 | 30 | 1.325 | $12.88 |
| 2026-05-02..2026-06-12 | 22 | 0.886 | $-6.37 |

Profitable (PF>1) windows: **3/4**.

## Verdict: **REJECTED**

Prior: §5c (2026-06-16): every IS-passing config collapsed OOS (best IS PF 1.37 -> OOS 0.92 = NO-GO).

_Per ADR 0014: a strategy earns paper/live only with a robust, statistically-significant edge. Range Trader does not clear that bar — recorded as a documented, citable 'honest no.' Intraday history is ~6 months (one regime); a deeper walk-forward would need more intraday data, but the bootstrap on the full trade set is the load-bearing test and it is decisive._
