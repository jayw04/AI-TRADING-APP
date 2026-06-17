# Range Trader — §5c Backtest Test Results & Findings

| Field | Value |
|---|---|
| Document version | v0.3 (adds §10 — Phases 1–4, σ-sweep, full §5c OOS, partial-exit; **conclusion: shelve**) — for review |
| Date | 2026-06-16 |
| Phase | P10 — Range Trader paper activation |
| Related | Gate v1.0 (`..._5c_Backtest_PreReg_v1.0.md`); gate `scripts/range_5c_gate.py`; daily screen `scripts/screen_range_candidates.py`; intraday screen `scripts/screen_intraday_oscillation.py` (#139); VWAP variant `strategies_user/templates/range_trader_vwap.py` (#140) |
| Verdict (fixed-level) | **No candidate activatable** — all INCONCLUSIVE (too few trades). |
| Verdict (after improvements) | Trade count **solved** (20→63–98). But **every IS-passing config fails OOS** (deep-entry IS 1.24/OOS 0.85; partial-exit IS 1.37/OOS 0.92) → no robust edge. **Recommendation: SHELVE** (reviewer's Step 4). §5d remains blocked. See §10. |
| Purpose | Capture the data, the strategy + level logic, and the actual results so we can decide how to improve. |

---

## 1. TL;DR

I ran the §5c gate on the top §5b range-bound candidates with real Alpaca 5-min bars. **All runs are INCONCLUSIVE** — the strategy generates only **13–23 in-sample round-trips** (the gate's floor for a verdict is 30; ≥50 for a clean GO). **Tightening the entry/exit band did not raise the trade count** (it stayed flat or fell). Out-of-sample profit factor is unstable (0.00–2.61). So fixed-level fade-the-range on these daily-range-screened large-caps does not produce a statistically meaningful, robust intraday edge.

One earlier "problem" turned out to be a **measurement artifact**, now fixed: a 23.8–71.8h "hold time" was wall-clock duration spanning overnight/weekend gaps (the EOD exit fills at the next session's open under next-bar settle). Measured in **bars held**, the positions are ~1 trading session (76 bars), not multi-day. (Fix: `bar_count_held`, PR #138.)

---

## 2. Data used

| Item | Value |
|---|---|
| Source | Alpaca **IEX** feed, 5-minute bars (`_alpaca_fetch_bars`), filtered to **regular trading hours** 09:30–16:00 ET |
| Symbols tested | UBER, SPGI, DASH (full); MELI, TT (wide-band only) — the calmest §5b candidates |
| Full data span (UBER) | 2026-01-02 → 2026-06-12, **112 sessions, 8,762 bars** |
| In-sample (IS) window | 2026-01-02 → 2026-04-30 (UBER: **82 sessions, 6,396 RTH bars**) |
| Out-of-sample (OOS) window | 2026-05-01 → 2026-06-12 (walk-forward; non-overlapping) |
| Data coverage | 100% of expected RTH bars on the tested windows (no holes) |
| Cost model | commission **$0/share**; slippage **5 bps (0.05%)** per fill; spread implicit in IEX bar prices |
| Fill model | market orders submitted on bar *N* fill at bar *N+1* open (harness `_settle_pending_orders`) |
| Reproducibility | gate v0.3 (`scripts/range_5c_gate.py`); strategy `range_trader.py` v0.1.0 |

> ⚠ IEX is a thin free-tier feed — treat marginal numbers as indicative. Norton SSL is beaten by the truststore fix (ADR 0017), so the dev box *can* fetch this data.

---

## 3. Strategy logic (what is being tested)

`range_trader.py` (v0.1.0) — **fade-the-range mean reversion**, one symbol, 5-min bars, fixed price levels:

- **Entry (buy):** when price dips **to/below `entry_price`** (near support / lower band).
- **Exit / take-profit (sell):** when price rises **to/above `exit_price`** (near resistance / upper band).
- **Hard stop (sell):** when price falls **to/below `stop_price`** — and the range is then treated as **broken** for the rest of the ET day (`_stopped_today`, no further entries that day).
- **Time gates (by `bar.t` ET):** no entries in the first `no_trade_open_minutes` (default 5) after 09:30; **force-flat** any position in the last `hard_exit_before_close_minutes` (default 5) before 16:00.
- **Sizing:** risk-based — `risk_per_trade_pct` (default 1%) of equity ÷ (entry − stop), capped at `max_position_qty`.
- **Caps:** at most `max_trades_per_day` (default 4) entries; **one position at a time** per symbol; a per-symbol in-flight flag prevents double-entry on a redelivered bar.
- **Stop type:** **synthetic** (evaluated per bar → market SELL), not a broker-native stop. No intra-bar/overnight gap protection; the EOD flatten is the overnight guard.
- **Level invariant:** `stop < entry < exit` (`_levels_ok`); bad levels are logged and no-op.

**Key structural consequence:** because it holds **one position at a time** and typically **rides to the EOD time-exit** when `exit_price` isn't reached intraday, the strategy produces **at most ~1 round-trip per session**. Over ~82 IS sessions that ceilings round-trips around ~20 — which is why trade counts land at 13–23 regardless of level width.

---

## 4. Level-derivation logic (what levels were used)

Two stages:

1. **§5b screen** (`screen_range_candidates.py`, offline daily bars): pick range-bound names by **ADX(14) < 20**, price having **touched both band edges ≥ 2×** within 1% (and still inside the band), **band width ≥ 4%**, **avg daily $ volume ≥ $20M**. Suggested levels = 25th / 75th / 10th percentile of recent daily closes (entry / exit / stop).
2. **§5c levels** (this test): to avoid look-ahead, levels were re-derived from the **IS window's own** 5-min RTH closes, at three band widths:

| Band label | entry quantile | exit quantile | stop quantile | intent |
|---|---|---|---|---|
| wide | 0.25 | 0.75 | 0.10 | the §5b default |
| tight | 0.40 | 0.60 | 0.25 | narrower → aim for more intraday round-trips |
| tighter | 0.45 | 0.55 | 0.35 | narrowest tested |

---

## 5. Gate criteria (the bar each run must clear)

Pre-registered (gate v1.0/v0.3; see the pre-reg doc). GO requires **all** of: IS trades ≥ 50 (30–49 = GO-WARNING w/ Owner signoff; <30 = **INCONCLUSIVE**); profit factor ≥ 1.3; win rate ≥ 45%; avg win/avg loss ≥ 1.0; expectancy ≥ 0.15R; max drawdown ≤ 8%; **OOS PF ≥ max(1.0, 0.8×IS PF)**; p95 **bars held** ≤ 117 (~1.5 sessions); stop flattens (no stuck position); data coverage ≥ 97%; (optional) robustness under ±0.5% level perturbation.

---

## 6. Results

### 6a. Per-symbol × band (IS 2026-01-02..04-30, OOS 2026-05-01..06-12)

| Symbol | Band | Levels (e / x / s) | IS trades | IS PF | OOS PF | p95 bars held | Verdict |
|---|---|---|---|---|---|---|---|
| UBER | wide | 72.80 / 79.99 / 70.98 | 23 | 0.96 | 0.11 | 76 (~1.0 sess) | INCONCLUSIVE |
| UBER | tight | 74.12 / 75.90 / 72.80 | 22 | 1.31 | 2.61 | 76 | INCONCLUSIVE |
| UBER | tighter | 74.51 / 75.40 / 73.73 | 18 | 1.16 | 1.20 | 45 | INCONCLUSIVE |
| SPGI | wide | 423.19 / 484.38 / 412.83 | 19 | 1.34 | 0.48 | 76 | INCONCLUSIVE |
| SPGI | tight | 430.89 / 442.56 / 423.19 | 16 | 0.47 | 0.00 | 76 | INCONCLUSIVE |
| SPGI | tighter | 434.04 / 439.54 / 428.58 | 16 | 0.53 | 0.00 | 76 | INCONCLUSIVE |
| DASH | wide | 163.39 / 204.74 / 154.90 | 17 | 0.50 | 0.55 | 76 | INCONCLUSIVE |
| DASH | tight | 172.00 / 180.55 / 163.39 | 19 | 0.99 | 1.27 | 76 | INCONCLUSIVE |
| DASH | tighter | 174.62 / 177.90 / 169.24 | 15 | 0.53 | 0.21 | 75 | INCONCLUSIVE |

### 6b. Wider candidate sweep (wide band only) — for completeness

MELI: 20 trades, IS PF 1.04, OOS 0.22 — INCONCLUSIVE. TT: 13 trades, IS PF 0.61, OOS 0.00 — INCONCLUSIVE. (Plus UBER/SPGI/DASH above.)

### 6c. The hold-time metric correction

UBER wide originally read **p95 hold = 23.8h** on wall-clock duration → looked like overnight "swing drift". Measured in **bars** it is **76 bars ≈ 1.0 session** → the position is intraday; the 23.8h was the EOD exit filling at the next session's open (next-bar settle) with the overnight gap counted as "hold". All exits were strategy SELLs; median wall-clock hold ~21h, but bar-count ~76 → confirms artifact, not behavior. (Fix: `bar_count_held`, PR #138.)

---

## 7. Findings

1. **Trade count is the binding constraint.** Every config is INCONCLUSIVE because IS round-trips are 13–23, well under 30 (and far under the 50 we'd want for confidence).
2. **Tighter levels do not help.** Narrowing the band kept the count flat or *reduced* it (UBER 23→22→18; SPGI 19→16→16). The ceiling is structural — one position at a time + ride-to-EOD ⇒ ~1 round-trip/session ⇒ ~20 trades over the window — not a function of band width.
3. **OOS is unstable.** OOS PF ranges 0.00–2.61 across configs with no consistency; the few attractive cells (e.g. UBER tight OOS 2.61) sit on ~22 trades, i.e. noise.
4. **The symbols don't intraday-oscillate enough.** §5b screened for *daily* range-bound large-caps; those don't reverse within a 5-min session often enough to feed a fade-the-range book. Daily-range ≠ intraday-mean-reverting.
5. **The drift alarm was a metric bug, now fixed.** Positions are ~1 session in bars; wall-clock over-counted across non-trading gaps.

---

## 8. Improvement directions (for review — pick what to pursue)

These are hypotheses, not decisions:

- **A. Different universe.** Screen for **intraday** mean-reversion (higher-beta / choppier names, ETFs like sector funds, or names with frequent intraday reversals), not daily-range large-caps. The single biggest lever.
- **B. Different screen metric.** Replace "daily ADX<20 + daily band touches" with an **intraday oscillation** measure — e.g. count of intraday crossings of a band, intraday range/ATR, or mean-reversion half-life on 5-min bars.
- **C. Allow more round-trips per session.** Re-enter after a take-profit within the same session (today it effectively does one ride-to-EOD). This raises trade count without changing the universe — but only if price actually re-oscillates.
- **D. Adaptive / intraday-anchored levels.** Fixed levels over months can't track a drifting price. Consider session-anchored levels (opening-range, prior-day high/low, VWAP ± k·σ) recomputed daily, rather than static percentiles of a long window.
- **E. Shorter, genuinely range-bound windows.** Validate on weeks where a tight range demonstrably holds — but note this trades away sample size (the ≥30/≥50 trade bars get harder).
- **F. Reconsider fit.** It's a legitimate outcome that fade-the-range isn't the right strategy for this universe/regime; the gate is doing its job by refusing to activate on noise.

My read: **A + B together** (intraday-oscillation screen over a choppier universe) is the highest-leverage next step; **C** is a cheap strategy tweak worth trying in parallel; **D** is the bigger redesign if fixed levels remain unviable.

---

## 9. Reproduction

```bash
cd apps/backend
# single run (with robustness + evidence)
.venv/Scripts/python.exe scripts/range_5c_gate.py UBER \
    --entry 74.12 --exit 75.90 --stop 72.80 \
    --is 2026-01-02 2026-04-30 --oos 2026-05-01 2026-06-12 \
    --robustness --json evidence/UBER_5c.json
# levels were derived as IS-window 5-min RTH close quantiles (e/x/s):
#   wide 0.25/0.75/0.10 · tight 0.40/0.60/0.25 · tighter 0.45/0.55/0.35
```

Needs Alpaca 5-min reachable (truststore/ADR 0017). Gate exit codes: 0 GO / 0 GO-WARNING / 1 NO-GO / 2 INCONCLUSIVE.

---

## 10. Improvement work (review-driven: Phases 1–4 + σ-sweep)

Following the review of v0.1, we ran the recommended sequence. Headline: the
**trade-count constraint is solved** (≈20 → 63–98 trades), but **no configuration
clears the §5c edge bar** (best is PLTR IS PF 1.24 < 1.3; XLE shows no edge).

### Phase 1 — intraday-oscillation screener (`screen_intraday_oscillation.py`, #139)

Replaced the *daily*-range screen with intraday metrics on 5-min bars: VWAP
crossings/day, lag-1 return autocorrelation (momentum-exclusion filter — at
intraday MR half-lives the true autocorr is only weakly negative + noisy, so it
rejects clearly *positive/trending*, not "requires strong negative"), AR(1)
mean-reversion **half-life** (the primary MR signal, target 30–120 min), and
liquidity. Run (45d) → **PASS: XLF, QQQ, XLE, PLTR**; fails were half-life >120m
(HOOD, IWM, ARKK) or crossings <6 (TSLA, AMD, SMH, XBI).

### Phase 2 — unchanged gate on the new universe (fixed levels)

Still **16–22 IS trades → INCONCLUSIVE** for XLF/QQQ/XLE/PLTR. **Key finding:**
the universe was *not* the binding constraint — **fixed levels over a long
window** are (a static entry level is only touched on the subset of days price
visits it, so entries fire ~0.2–1×/session regardless of intraday chop).

### Phases 3 + 4 — VWAP±σ variant with same-day re-entry (`range_trader_vwap.py`, #140)

`RangeTraderVWAP` replaces the three fixed levels with **session-VWAP bands**
recomputed every bar (entry = VWAP − entry_σ·σ, exit = VWAP − exit_σ·σ, stop =
VWAP − stop_σ·σ; σ = running std of price − VWAP). The band tracks price, so an
entry exists most days and price round-trips the band repeatedly (re-entry).
IS backtest (default σ 1/0/2):

| Symbol | trades | PF | win% | avgW/avgL |
|---|---|---|---|---|
| PLTR | 89 | 0.73 | 40% | 1.07 |
| XLF | 98 | 0.39 | 44% | 0.50 |
| XLE | 92 | 0.60 | 49% | 0.63 |

→ **Trade count solved** (≥50 cleared), but **edge negative** at default σ.

### σ-sweep (exploratory; IS only — not OOS-validated)

| Symbol | entry/exit/stop σ | trades | PF | win% | avgW/avgL |
|---|---|---|---|---|---|
| PLTR | −1 / VWAP / −2 | 89 | 0.73 | 40% | 1.07 |
| PLTR | −1.5 / VWAP / −2.5 | 73 | 0.71 | 44% | 0.91 |
| **PLTR** | **−2 / VWAP / −3** | **66** | **1.24** | 48% | 1.32 |
| PLTR | −1 / +0.5σ / −2 | 82 | 0.74 | 35% | 1.36 |
| XLE | −1 / VWAP / −2 | 92 | 0.60 | 49% | 0.63 |
| XLE | −1.5 / VWAP / −2.5 | 79 | 0.44 | 49% | 0.45 |
| XLE | −2 / VWAP / −3 | 63 | 0.46 | 56% | 0.37 |
| XLE | −1 / +0.5σ / −2 | 82 | 0.60 | 41% | 0.84 |

**Deeper entries help** (PLTR PF 0.73 → 1.24 as entry goes −1σ → −2σ: a more
stretched price reverts more reliably). But the best is **PLTR IS PF 1.24, still
< 1.3**, and IS-only — OOS not yet checked. **XLE never develops an edge.**

### Conclusion & recommendation

- The review's Phases 1–4 worked **structurally**: oscillation screen + dynamic
  VWAP levels + re-entry took us from ~20 INCONCLUSIVE trades to 63–98. The
  pipeline (screen → gate → variant) is sound and committed.
- **No config clears §5c.** The closest (PLTR, deep −2σ entry, IS PF 1.24) is
  below the 1.3 bar and unvalidated OOS; XLE has no edge. A 5-min VWAP-revert
  book on these names does not show a robust edge in this regime.
- **Recommended:** (1) a full §5c run (IS+OOS+robustness) on **PLTR deep-entry**
  to see if even 1.24 survives OOS — if not, stop chasing σ (curve-fit risk the
  review flagged); (2) otherwise this is a legitimate "shelve / rethink the
  strategy" outcome — the gate is correctly refusing to activate on a
  sub-threshold edge. Do **not** lower the gate to fit the result.

### Step 1 — full §5c on PLTR deep-entry (IS + OOS + robustness)

| Window | trades | PF |
|---|---|---|
| IS | 66 | 1.24 (< 1.3) |
| OOS | 21 | **0.85** |

**NO-GO** — IS PF below 1.3 *and* OOS PF 0.85 collapses (OOS floor = max(1.0,
0.8×IS) = 1.0). The faint IS edge does not survive out-of-sample.

### Step 3 — partial-reversion exit (reviewer's best idea: exit at VWAP − 0.5σ)

| Config (entry/exit/stop σ) | win% | IS trades | IS PF | OOS trades | OOS PF |
|---|---|---|---|---|---|
| 2 / VWAP / 3 | 48% | 66 | 1.24 | 21 | 0.85 |
| **2 / VWAP−0.5σ / 3** | 56% | 79 | **1.37** | 23 | **0.92** |
| 2 / VWAP−1.0σ / 3 | 58% | 85 | 1.26 | 24 | 0.83 |

The hypothesis was right *in-sample*: a partial-reversion target lifts win rate
(48%→56%) and **IS PF to 1.37 — clears the 1.3 bar**. **But OOS PF is still 0.92
(< 1.0 floor)** — it collapses out-of-sample, like every other config.

### Final conclusion — SHELVE (reviewer's Step 4)

**Every configuration that clears the in-sample bar fails out-of-sample**
(deep-entry IS 1.24/OOS 0.85; partial-exit IS 1.37/OOS 0.92). That is the
curve-fit signature the OOS criterion exists to catch. There is **no robust
intraday mean-reversion edge** for this strategy on this universe in this regime.

Per the review's pre-committed Step 4 (PF still < 1.3 OOS → shelve), and to avoid
the curve-fit trap (don't keep sweeping σ; don't lower the gate): **shelve
RangeTrader activation.** The gate did its job — it prevented activating a weak,
non-robust edge. What's kept and reusable: the §5c gate, the bar-count drift
metric, the intraday-oscillation screener, and the VWAP±σ variant (all merged /
PR'd) — solid infrastructure for a future strategy.

Optional before fully shelving (low expected value): add the Step-2 diagnostics
(exit_reason_counts, entry funnel, MFE/MAE) to *explain* the OOS failure — but
they won't change the decision, since the OOS collapse is consistent across
configs.

### Learn diagnostic (PLTR partial-exit 2/0.5σ/3, IS — "to learn, not to rescue")

A light post-hoc pass on the 79 IS trades (no harness instrumentation — entry
hour, P&L sign, bars held only):

| Entry hour (ET) | trades | win% | total P&L |
|---|---|---|---|
| 10:00 | 49 | 61% | +316 |
| 11:00 | 8 | 38% | −330 |
| 12:00 | 6 | 67% | +225 |
| 13:00 | 8 | 38% | −246 |
| 14:00 | 6 | 33% | +1172 (one outlier) |
| 15:00 | 2 | 100% | +510 |

Hold time: wins ≈ 9 bars (~45m), losses ≈ 8 bars (~40m).

What we learn: it's essentially a **first-hour fade** — 62% of trades fire at
10:00 ET (after the σ warm-up + no-trade-open window) and that hour carries the
positive expectancy; **midday (11:00/13:00) loses**; later hours are thin/noisy.
Holds are short (~45m), so the partial-exit target is hit quickly (not the
ride-to-EOD pattern). A **time-of-day filter (trade only the first ~90 min)** is
a reusable insight for future intraday strategies — but it's IS-only and doesn't
change the OOS verdict. The fuller exit_reason/MFE/MAE instrumentation (needs
harness changes) is deferred to the next strategy that warrants it.
