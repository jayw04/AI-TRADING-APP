# Range Trader — §5c Backtest Pre-Registration & GO/NO-GO Gate

| Field | Value |
|---|---|
| Document version | v0.1 (pre-registration — frozen before any results are seen) |
| Date | 2026-06-16 |
| Phase | P10 — Range Trader paper activation |
| Session | §5c of the paper-activation plan |
| Predecessor | `TradingWorkbench_RangeTrader_PaperActivation_v0.1.md` (v0.4); §5b screen (PR #134) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Pre-register the backtest acceptance criteria for a chosen symbol/levels and provide the enforcing GO/NO-GO gate, so RangeTrader is activated only on evidence. |
| Estimated wall time | 2–3 hours (level selection from §5b → run IS/OOS backtests → apply gate → record) |
| Out of scope | Picking the symbol (that's the operator, from §5b); LIVE; multi-symbol; changing thresholds after seeing results |

> **Governing decisions:** ADR 0014 (backtests are the eval ground truth) and Finding 4 of the paper-activation plan (acceptance criteria are **pre-registered** — written down *before* running, tightened-only afterward).

---

## 1. Why this session exists

The §5b screen (PR #134) produces *candidates* — range-bound names with suggested fade-the-range levels. A screen is not a verdict: a candidate can look range-bound on a daily chart and still be unprofitable to trade intraday once costs, the hard stop, and a thin edge are accounted for. §5c is the gate between "looks plausible" and "may go live on paper."

The trap §5c guards against is **goalpost-moving**: the level/param sweep makes it trivially easy to find *some* configuration that looks good in-sample. If the thresholds are chosen *after* seeing results, the gate is theatre. So the thresholds are pre-registered here, frozen, and enforced by a pure function that cannot see the data it judges.

## 2. What this session ships

- This **pre-registration document** — the frozen thresholds + the run procedure + a results-recording template.
- `apps/backend/scripts/range_5c_gate.py` — a pure `evaluate_gate()` enforcing the thresholds, plus a CLI that runs the production `Backtester` on real RTH 5-min bars for an in-sample and out-of-sample window and prints **GO / NO-GO** (exits non-zero on NO-GO).
- `apps/backend/tests/scripts/test_range_5c_gate.py` — tests for every criterion (pass and each failure mode).

## 3. Prerequisites

1. **§5b screen run** and a candidate symbol + `entry`/`exit`/`stop` chosen (PR #134; `scripts/screen_range_candidates.py`). Levels must satisfy `stop < entry < exit` (the template's `_levels_ok`).
2. **PR #92 backtest harness** merged + version-pinned (✅ on `main`: synthetic / alpaca / sweep scripts).
3. **Real intraday bars reachable** — the IS/OOS runs fetch 5-min IEX bars from `data.alpaca.markets` (Norton SSL blocks this on the dev box; run where reachable — WSL/CI/another machine — or via the truststore fix, ADR 0017).
4. Risk fixes #114 (daily-loss) and #120 (breaker monitor) deployed (✅).

## 4. Pre-registered acceptance criteria (FROZEN)

All criteria are computed over the **in-sample (IS)** window unless noted. The OOS check uses a separate, later window. **GO requires every row to pass.** Defaults live in `GateThresholds`.

| # | Metric | Threshold | Rationale |
|---|---|---|---|
| 1 | Round-trip trades (IS) | **≥ 30** | Below this the stats are noise; a "great" 5-trade backtest means nothing. |
| 2 | Profit factor (IS) | **≥ 1.3** | Edge must survive costs; 1.0–1.3 is too thin for an intraday book. |
| 3 | Win rate (IS) | **≥ 45%** | Mean-reversion can win <50% if winners ≥ losers — paired with #4. |
| 4 | Avg win / avg loss (IS) | **≥ 1.0** | With the hard stop defining the loss, winners must at least match losers. |
| 5 | Max drawdown (IS) | **≤ 2 × risk_per_trade_pct × max_trades_per_day** (default **8%**) | Drawdown must be bounded by stop discipline, not exceed it. |
| 6 | OOS profit factor | **≥ 0.8 × IS profit factor** | Guards against curve-fit levels (walk-forward split). |
| 7 | Stop behavior | every modeled stop-out flattens; **no position left open** | The stop is the whole risk story — verify it fires in the sim. |

**Conservative-by-default:** these may be **tightened** after the fact (e.g. raising min PF), never loosened. A loosening requires a written amendment to this doc with rationale, dated, before re-running — otherwise it is goalpost-moving and void.

Drawdown bound note: with the RangeTrader template defaults (`risk_per_trade_pct = 1%`, `max_trades_per_day = 4`) the bound is `2 × 0.01 × 4 = 0.08`. If the activation uses different params, pass them to the gate so the bound tracks them.

## 5. Run procedure

1. **Sanity (offline):** `scripts/backtest_range_trader_synthetic.py` — confirms the harness + template behave on a constructed range (3 sessions: win / stop-out / time-exit). Not a gate input; a smoke that the machinery is sound.
2. **Choose windows:** an IS window and a later, non-overlapping OOS window (walk-forward). Aim for enough sessions that IS yields ≥ 30 round-trips.
3. **Run the gate:**

   ```bash
   cd apps/backend
   .venv/Scripts/python.exe scripts/range_5c_gate.py <SYMBOL> \
       --entry <E> --exit <X> --stop <S> \
       --is <IS_START> <IS_END> --oos <OOS_START> <OOS_END>
   ```

   It runs the production `Backtester` on real RTH 5-min bars for both windows, applies the pre-registered criteria, and prints a per-criterion PASS/FAIL table + the GO/NO-GO verdict (exit 0 = GO, 1 = NO-GO).
4. **Cross-check with the sweep** (`scripts/backtest_range_trader_sweep.py`) — the walk-forward sweep over level/param choices supports criterion #6 (OOS ≈ IS) and surfaces whether the chosen levels are a fragile peak.
5. **Record** the verdict, the full metrics, params, and windows (below) as the activation evidence.

## 6. Results-recording template (fill in on run)

```
Symbol:            <SYM>
Levels:            entry=<E>  exit=<X>  stop=<S>   (stop<entry<exit: yes)
IS window:         <start>..<end>     OOS window: <start>..<end>
Params:            risk_per_trade_pct=<>  max_trades_per_day=<>  timeframe=5Min
IS metrics:        trades=<>  PF=<>  win=<>%  avgW/avgL=<>  maxDD=<>%
OOS metrics:       PF=<>  (floor = 0.8×IS PF = <>)
Stop behavior:     all trades closed? <yes/no>
VERDICT:           <GO | NO-GO>     (gate exit code: <0|1>)
Decided by / date: <operator> / <YYYY-MM-DD>
```

## 7. Walk-away discipline

The gate code (`range_5c_gate.py` + tests) is analysis tooling — routine PR, **≥ 1 hour** walk-away. The *activation decision* it informs (§5d) is owner-gated and happens in regular market hours; activation itself is not part of this session.

## 8. What this session does NOT do

- Does **not** pick the symbol or the levels — that is the operator's call from §5b.
- Does **not** activate anything — §5d registers + starts the strategy after a GO.
- Does **not** fetch or commit market data.
- Does **not** change the RangeTrader template or the harness.
- Does **not** permit loosening the thresholds after results — only tightening, via a dated amendment.
- Does **not** cover LIVE (real money).

## 9. Notes & gotchas

1. **Pre-registration is the whole point.** If you find yourself editing §4 after a run, stop — that's the failure mode this doc exists to prevent. Tighten-only, dated, with rationale.
2. **IEX free tier is thin.** The alpaca 5-min feed is indicative, not precise; treat a marginal PASS (e.g. PF 1.31) with suspicion and lean on the OOS + sweep cross-checks.
3. **Enough sessions for ≥ 30 trades.** With `max_trades_per_day = 4`, 30 round-trips needs ~8+ active trading sessions in the IS window — pick the window accordingly, or the trade-count criterion (correctly) fails.
4. **Levels are validated.** `range_5c_gate.py` refuses `stop < entry < exit` violations up front (the template would otherwise log + no-op them).
5. **Drawdown bound tracks params.** If you change `risk_per_trade_pct` / `max_trades_per_day` at activation, pass them so criterion #5's bound matches the live config.
