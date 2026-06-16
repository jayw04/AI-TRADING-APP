# Range Trader — §5c Backtest Pre-Registration & GO/NO-GO Gate

| Field | Value |
|---|---|
| Document version | **v1.0** (frozen for execution) — pre-registration, frozen before any results are seen |
| Date | 2026-06-16 |
| Phase | P10 — Range Trader paper activation |
| Session | §5c of the paper-activation plan |
| Predecessor | v0.1 (PR #135) → v0.2 → v0.3 (three review rounds); §5b screen (PR #134) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Pre-register the backtest acceptance criteria for a chosen symbol/levels and provide the enforcing GO / GO-WARNING / NO-GO / INCONCLUSIVE gate, so RangeTrader is activated only on evidence. |
| Estimated wall time | 2–3 hours (level selection from §5b → run IS/OOS + robustness → apply gate → record evidence) |
| Out of scope | Picking the symbol (operator, from §5b); LIVE; multi-symbol; **loosening** thresholds after results |

> **Governing decisions:** ADR 0014 (backtests are the eval ground truth) and Finding 4 of the paper-activation plan (acceptance criteria are **pre-registered** — written down *before* running, tightened-only afterward).

> **Review history:** v0.2 added cost model, expectancy, hold-time, OOS PF ≥ max(1.0, 0.8×IS), the ≥50/30–49/<30 trade bands, market-session source, stop semantics, duplicate-bar invariant, data schemas, evidence package. v0.3 added `git_commit`, a data-coverage criterion, the robustness trade-count floor, `random_seed`, and the explicit `GO-WARNING` verdict. **v1.0 (final review):** coverage floor raised to **97%** (5-min intraday); GO-WARNING signoff named the **Owner**; trade-level schema gains `bar_count_held`; audit keys off the evidence JSON `verdict`, not the exit code; market-regime recording noted as a future enhancement.

---

## 1. Why this session exists

The §5b screen (PR #134) produces *candidates* — range-bound names with suggested fade-the-range levels. A screen is not a verdict: a candidate can look range-bound on a daily chart and still be unprofitable to trade intraday once **costs**, the hard stop, and a thin edge are accounted for. §5c is the gate between "looks plausible" and "may go live on paper."

The trap §5c guards against is **goalpost-moving**: the level/param sweep makes it trivially easy to find *some* configuration that looks good in-sample. If the thresholds are chosen *after* seeing results, the gate is theatre. So the thresholds are pre-registered here, frozen, and enforced by a pure function (`evaluate_gate`) that cannot see the data it judges.

## 2. What this session ships

- This **pre-registration document** — frozen thresholds + cost model + run procedure + data schemas + the Activation Evidence Package.
- `apps/backend/scripts/range_5c_gate.py` — a pure `evaluate_gate()` enforcing the criteria, plus a CLI that runs the production `Backtester` on real RTH 5-min bars for an in-sample + out-of-sample window (and optional ±0.5% robustness perturbations) and prints **GO / GO-WARNING / NO-GO / INCONCLUSIVE**, persisting an evidence JSON.
- `apps/backend/tests/scripts/test_range_5c_gate.py` — tests for every criterion and verdict state.

## 3. Prerequisites

1. **§5b screen run** and a candidate symbol + `entry`/`exit`/`stop` chosen (PR #134; `scripts/screen_range_candidates.py`). Levels must satisfy `stop < entry < exit` (the template's `_levels_ok`).
2. **PR #92 backtest harness** merged + version-pinned (✅ on `main`).
3. **Real intraday bars reachable** — the IS/OOS runs fetch 5-min IEX bars from `data.alpaca.markets` (Norton SSL blocks this on the dev box; run where reachable — WSL/CI/another machine — or via the truststore fix, ADR 0017).
4. Risk fixes #114 (daily-loss) and #120 (breaker monitor) deployed (✅).

## 4. Cost Model (explicit assumptions)

A 5-minute mean-reversion edge lives or dies on costs, so the backtest's cost assumptions are stated here rather than left implicit. The harness (`BacktestConfig`) applies:

| Cost | Assumption | Source |
|---|---|---|
| **Commission** | **$0.00 / share** | Alpaca paper/live equities are commission-free. |
| **Slippage** | **5.0 bps (0.05%) per fill**, on every entry and exit | `BacktestConfig.slippage_bps` default; configurable via `--slippage-bps`. |
| **Spread** | Implicit in the **IEX 5-min bar** prices (fills modeled at bar price ± slippage) | IEX feed; no separate half-spread is added. |

Thresholds in §5 are applied to **net-of-slippage** results. The IEX feed is thin, so a marginal PASS should still be treated with suspicion (Note 2) and is cross-checked by the data-coverage criterion (§5 #11).

## 5. Pre-registered acceptance criteria (FROZEN)

All criteria are over the **in-sample (IS)** window unless noted. Defaults live in `GateThresholds`.

| # | Metric | Threshold | Rationale |
|---|---|---|---|
| 1 | Round-trip trades (IS) | **≥ 50** GO-eligible / **30–49 GO-WARNING** / **< 30 INCONCLUSIVE** | 30 is the bare minimum; 50–100 gives real confidence. See verdict governance below. |
| 2 | Profit factor (IS) | **≥ 1.3** | Edge must survive costs. |
| 3 | Win rate (IS) | **≥ 45%** | Mean-reversion can win <50% if winners ≥ losers — paired with #4/#5. |
| 4 | Avg win / avg loss (IS) | **≥ 1.0** | With the hard stop defining the loss, winners must at least match losers. |
| 5 | Expectancy (IS) | **≥ 0.15R** | `win%·avgWin − loss%·avgLoss`, in R (≈ `expectancy$ / |avgLoss|`). Catches weak per-trade edge that PF alone hides. |
| 6 | Max drawdown (IS) | **≤ 2 × risk_per_trade_pct × max_trades_per_day** (default **8%**) | Drawdown bounded by stop discipline. |
| 7 | OOS profit factor | **≥ max(1.0, 0.8 × IS PF)** | Anti curve-fit **and** anti "barely profitable OOS". |
| 8 | Hold time (IS, p95) | **≤ 1 regular session (6.5h)** | Intraday must not drift into a swing book via a bug. |
| 9 | Stop behavior | every modeled stop-out flattens; **no position left open** | The stop is the whole risk story. |
| 10 | Robustness (optional, `--robustness`) | worst PF ≥ 0.8 × IS PF **and** worst trade-count ≥ 0.8 × IS trade-count, under ±0.5% level perturbation | A level set whose edge **or activity** collapses under a 0.5% nudge is fragile. |
| 11 | Data coverage (per window) | **received / expected RTH bars ≥ 97%** | 5-min intraday needs tighter coverage than daily — a missing few % of bars disproportionately affects entry triggers. Below the floor → data problem, re-run (not a result). |

### Verdict governance (the 30–49 zone)

| IS trades | Verdict | Meaning |
|---|---|---|
| **≥ 50** and all criteria pass | **GO** | Eligible to activate. |
| **30–49** and all criteria pass | **GO-WARNING** | Eligible, **but Owner signoff required** (thin sample). The signoff authority is the platform **Owner** (Jay Wang / GlobalComplyAI), not a delegated operator. |
| **≥ 30** and any criterion fails | **NO-GO** | Do not activate. |
| **< 30** | **INCONCLUSIVE** | Not enough evidence to pass *or* fail; widen the window / re-screen. |

CLI exit codes: GO = 0, GO-WARNING = 0 (eligible), NO-GO = 1, INCONCLUSIVE = 2. **Audit consumers must key off the evidence JSON `verdict` field** (`"GO" | "GO-WARNING" | "NO-GO" | "INCONCLUSIVE"`), not the exit code — the code collapses GO and GO-WARNING to 0.

**Conservative-by-default:** thresholds may be **tightened** after the fact, never loosened. A loosening requires a written, dated amendment to this doc with rationale, *before* re-running — otherwise it is goalpost-moving and void.

## 6. Run procedure

1. **Sanity (offline):** `scripts/backtest_range_trader_synthetic.py` — confirms harness + template behave on a constructed range. A smoke, not a gate input.
2. **Choose windows:** an IS window and a later, non-overlapping OOS window (walk-forward). At 4 trades/day, ~13+ active IS sessions are needed for ≥ 50 round-trips.
3. **Run the gate:**

   ```bash
   cd apps/backend
   .venv/Scripts/python.exe scripts/range_5c_gate.py <SYMBOL> \
       --entry <E> --exit <X> --stop <S> \
       --is <IS_START> <IS_END> --oos <OOS_START> <OOS_END> \
       --robustness --json evidence/<SYMBOL>_5c.json
   ```

   Runs the production `Backtester` on real RTH 5-min bars for both windows (+ ±0.5% perturbations with `--robustness`), applies the pre-registered criteria, prints the per-criterion table + verdict, and writes the evidence JSON. Exit: **0 GO / 0 GO-WARNING / 1 NO-GO / 2 INCONCLUSIVE**.
4. **Cross-check with the sweep** (`scripts/backtest_range_trader_sweep.py`).
5. **Record** the evidence JSON + verdict (§11).

## 7. Market-session source

Session determination is the §9A Market Session Model (on `main`): `pandas_market_calendars` (XNYS — holidays, early closes) with a curated-list fallback; cross-checked against the Alpaca clock for the authoritative live open/close; all math in **`America/New_York`** (DST-correct). Backtests filter to **RTH (09:30–16:00 ET)**. The §5c **expected-bar count** (§5 #11) is derived from this calendar (78 bars/full day, 42/half-day), so coverage accounts for holidays and early closes.

## 8. Execution & state semantics

**Stop execution — synthetic, not broker-native.** The template evaluates `price ≤ stop_price` per 5-min bar and submits a **market SELL** through the risk engine (plan §3D). Consequences: **no intra-bar / overnight gap protection** (a fast gap-down fills below `stop_price`); the **EOD forced flatten** is the overnight guard; a broker-native stop-market is a future enhancement, out of scope.

**Duplicate-bar invariant.** *One completed bar → at most one entry; a redelivered bar must not create a second entry.* Enforced by the template's per-symbol in-flight flag (`_pending`), cleared on fill and reconciled each bar (plan §3B, PR #126).

## 9. Robustness test

`--robustness` re-runs the IS window with each level perturbed **±0.5%** (entry, exit, stop independently; perturbations breaking `stop < entry < exit` are skipped). It passes only if **both** hold across all perturbations:
- worst perturbed **profit factor ≥ 0.8 × IS PF**, and
- worst perturbed **trade count ≥ 0.8 × IS trade count** (so PF can't "survive" merely because the perturbation stopped trading).

## 10. Data schemas (for auditability)

**Trade-level** (`BacktestTrade`): `entry_time, exit_time, symbol, entry_price, exit_price, stop_price, qty, pnl, duration_seconds, bar_count_held (derived = duration_seconds // bar_seconds — easier to read than seconds for a 5-min book), exit_reason ∈ {exit_signal, stop, eod, backtest_end}`.

**Backtest-run:** `symbol, entry/exit/stop, is_window, oos_window, strategy_version, gate_version, git_commit, random_seed, data_source, slippage_bps, expected_bars, received_bars, data_coverage, timestamp`.

**Gate-evaluation** (persisted by `--json`): per criterion `{criterion, passed, detail (threshold vs actual)}`, plus `warnings`, the machine-readable `verdict` string, and the run metadata above (incl. `git_commit`, `random_seed`, per-window `data_coverage`) — so a decision is reproducible to the exact commit months later, and audit tooling reads `verdict` directly.

## 11. Activation Evidence Package

The permanent record of **why a strategy was activated**, written on a GO/GO-WARNING and kept:

- chosen symbol; chosen levels (entry/exit/stop)
- IS metrics; OOS metrics; robustness runs (PF + trade count)
- per-window data coverage (expected/received bars)
- full gate output (per-criterion + `verdict`) — the `--json` evidence file
- `strategy_version` (`RangeTrader.version`), `gate_version`, and **`git_commit`** (code can change without a version bump)
- `random_seed`, `data_source`, `slippage_bps`
- Owner approval and activation timestamp; for **GO-WARNING**, the explicit Owner signoff

Recording template:

```
Symbol / levels:   <SYM>  entry=<E> exit=<X> stop=<S>  (stop<entry<exit: yes)
Windows:           IS <start>..<end>   OOS <start>..<end>
Params:            risk_per_trade_pct=<>  max_trades_per_day=<>  timeframe=5Min  slippage_bps=<>
Versions:          strategy=<>  gate=<>  git_commit=<>  random_seed=<>  data_source=alpaca_iex_5min
Data coverage:     IS expected=<> received=<> (<>%)   OOS expected=<> received=<> (<>%)
IS:                trades=<>  PF=<>  win=<>%  avgW/avgL=<>  expectancy=<>R  maxDD=<>%  p95_hold=<>h
OOS:               PF=<>   (floor = max(1.0, 0.8×IS PF) = <>)
Robustness:        worst PF=<> (>= <>)   worst trades=<> (>= <>)
Stop behavior:     all trades closed? <yes/no>
VERDICT:           <GO | GO-WARNING | NO-GO | INCONCLUSIVE>   (exit code <0|0|1|2>)
Owner approval:    <Owner> / <YYYY-MM-DD>   (GO-WARNING signoff: <Owner>)
Evidence JSON:     <path>
```

## 12. Walk-away discipline

The gate code (`range_5c_gate.py` + tests) is analysis tooling — routine PR, **≥ 1 hour** walk-away. The *activation decision* it informs (§5d) is owner-gated and happens in regular market hours.

## 13. What this session does NOT do

- Does **not** pick the symbol or levels — operator's call from §5b.
- Does **not** activate anything — §5d registers + starts the strategy after a GO / signed-off GO-WARNING.
- Does **not** fetch or commit market data.
- Does **not** change the RangeTrader template or the harness.
- Does **not** add a broker-native stop (synthetic stop only).
- Does **not** permit loosening thresholds after results — tighten-only, dated amendment.
- Does **not** cover LIVE (real money).
- Does **not** record **market regime** at activation (e.g. SPY vs 200DMA, VIX percentile). This is a worthwhile future enhancement for explaining later performance, but it belongs in portfolio governance, not this gate. Noted for a future version.

## 14. Notes & gotchas

1. **Pre-registration is the whole point.** Editing §5 after a run is the failure mode this doc prevents. Tighten-only, dated, with rationale.
2. **IEX free tier is thin.** Treat a marginal PASS (PF 1.31; robustness at the floor; coverage just above 97%) with suspicion; lean on OOS + the sweep.
3. **Enough sessions for ≥ 50 trades.** At 4 trades/day, ~13+ active IS sessions. Too short → GO-WARNING (30–49) or INCONCLUSIVE (<30) — correct outcomes, not failures to "fix" by loosening.
4. **Levels are validated.** The gate refuses `stop < entry < exit` violations up front.
5. **Bounds track params.** If `risk_per_trade_pct` / `max_trades_per_day` change at activation, pass them so #6/#8 match the live config.
6. **Expectancy uses |avgLoss| as the R proxy** — valid because the hard stop makes the average loss ≈ one risk unit; if losses are dominated by gap-throughs well beyond the stop, revisit.
7. **Coverage is calendar-aware** — expected bars come from the §9A trading calendar (holidays/half-days), so a low coverage number means missing *bars within trading days*, i.e. a real data hole, not a weekend. The 97% floor is intraday-specific (daily bars would tolerate 95%).
8. **`git_commit` over `strategy_version`** — the version is coarse; the commit is exact. Both are recorded; the commit is the reproducibility anchor.
9. **Audit reads `verdict`, not the exit code** — GO and GO-WARNING both exit 0; only the JSON distinguishes them.
