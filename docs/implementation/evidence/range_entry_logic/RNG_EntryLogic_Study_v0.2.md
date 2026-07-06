# RNG Entry-Logic Study — Evidence Package v0.1

| Field | Value |
|---|---|
| Date | 2026-07-06 |
| Version | v0.2 (adds day-level portfolio results, date-clustered bootstrap, promotion-gate scorecard, denominator + activation-timing precision — per owner review) |
| Program | RNG-001 (Range Trader) — entry-logic sub-study (final supporting evidence) |
| Status | Complete · **Archived** as part of RNG-001 |
| Verdict | **Rejected** — no robust tradable edge; RNG-001 rejection stands and is strengthened |
| Live impact | **None.** This result does **not** justify raising levels, enabling new entries, or increasing allocation. The live Range strategy remains unchanged (and may be retired from active paper evaluation). |
| Related | RNG-001 case study + exec summary; CAP-025 (Intraday Replay & Entry-Funnel Diagnostics — the reusable tooling this study produced); ADR 0028 (range auto-select); `range_strategy_research_program` |

**Denominator convention (read before the tables):** `fill%` is a fraction of **candidate-days**
(a name-day that passed selection and had a valid opening range). `win%` and `stop%` are fractions
of **filled trades** (not candidate-days). Per-trade P&L / PF are over **filled trades**. §3.5's
day-level metrics are over **trading days** (the selected top-5 collapsed to one portfolio return
per day). A "candidate-day" is one name on one day; a "trade" is a filled candidate-day.

**Activation timing (precise):** the opening range is built from the six 5-Min bars 09:30–10:00 ET
and **frozen at 10:00 ET**. Orders become eligible at 10:00; the **first actionable bar is the
10:00–10:05 ET bar** (timestamped 10:00). The live system's `range_levels` signal is emitted ~10:05
ET (one bar-close of processing lag after the 10:00 freeze); the replay's next-bar granularity
approximates that — entries are only evaluated on bars timestamped ≥ 10:00, never inside the OR window.

## 1. Question

On 2026-07-06 the live Range Trader (user 2) took **0 trades** on a day when all five
selected names (GOOGL, MU, INTC, AMD, TSLA) touched **both** their buy (opening-range low)
and sell (opening-range high) levels intraday. The naive read — "the levels are mis-placed,
raise buy and sell" — needed testing before any change. Two questions:

1. Is the bottleneck the entry **level height** (raise buy/sell), or the entry **logic**?
2. Can a better entry rule turn the rejected-benchmark Range strategy into a tradable edge?

## 2. Method

Sequence-correct **intraday replay** (not daily OHLC — daily high/low cannot tell you whether
the target was reachable *after* an entry, only that price visited both levels at some point).

- **Data**: the 18-name auto-select universe × **126 trading days** (2026-01-02 → 2026-07-06)
  × **5-Min bars**, backfilled month-chunked from Alpaca (avoids the 10k-page truncation).
- **Levels** (replicating the live template): OR window = first 30 min (09:30–10:00 ET);
  buy = OR low, sell = OR high, stop = OR low × (1 − 0.005); activation at 10:00 ET.
- **Funnel diagnostic** per candidate-day: buy-before/after-activation → fill → target/stop
  -after-entry → exit P&L, classified into a bottleneck table.
- **Variants**: A baseline; B raised-entry (buy = OR low + 20%·OR range); D raise-both
  (+20% both); E-mid (dip to OR low → enter on close ≥ OR midpoint); E-vwap (→ close ≥ intraday
  VWAP); E-vwap+gate (+ only when SPY is above its own VWAP — a market-regime gate).
- **Selection filter**: structural Range Score (ATR% × oscillation(1−Kaufman ER) × class-weight)
  top-5/day — the names the strategy would actually trade.
- **Cost** 5 bps/side. **Fill model** touch-to-fill (A/B/D), reclaim-close (E) — deliberately
  **optimistic**, so the true edge is *no better* than reported.
- **Pre-registered decision rule** (6 conditions) + a **train/test time-split** for OOS robustness.

## 3. Findings

### 3.1 The funnel — the entry is *adversely selected* (all 18, n=2267)

| Outcome | Share |
|---|---|
| Buy touched after activation (=fill) | 46.7% |
| — target after entry (WIN) | 8.3% |
| — stop after entry (reversal) | **29.2%** |
| — no target → EOD flat | 9.1% |
| Target hit **before** entry (missed breakout) | **49.0%** |
| Never re-touched, no target | 4.3% |

Of the days that fill, **62.7% reverse to the stop and only 17.8% reach the target.** The entry
selects us *into* the falling knives (price returns to OR low → keeps falling) and *out of* the
rallies (price breaks up, never gives a fill). It is **not an entry-timing problem** you fix by
moving the level — the fade-at-support entry is structurally on the wrong side. Baseline economics:
avg −0.116%/trade, **PF 0.70**, profitable only in up-regimes (up +0.140 / down −0.295 / chop −0.154).

### 3.2 "Raise both" is refuted (selected top-5, n=523)

| Variant | PF | avg P&L | up | down | chop |
|---|---|---|---|---|---|
| A baseline | 0.81 | −0.085 | +0.359 | −0.194 | −0.316 |
| B raised-entry | 0.73 | −0.198 | +0.242 | −0.397 | −0.365 |
| D raise-both | 0.73 | −0.196 | +0.278 | −0.429 | −0.326 |

Raising the entry lifts the fill rate but makes P&L **worse** in every regime — more fills = more
falling knives, exactly as the funnel predicted. The naive operational adjustment is evidenced wrong.

### 3.3 Confirmation is the structural lever (selected top-5, n=523)

| Variant | fill% | win% | stop% | PF | avg P&L | up | down | chop |
|---|---|---|---|---|---|---|---|---|
| E-mid | 27.2 | 47.9 | 16.9 | 1.03 | +0.014 | +0.289 | −0.322 | −0.070 |
| E-vwap | 41.5 | 30.4 | 39.2 | 1.36 | +0.164 | +0.539 | −0.144 | +0.100 |
| **E-vwap+gate** | 36.7 | 32.8 | 35.4 | **1.53** | **+0.217** | +0.514 | +0.008 | +0.072 |

"Buy the reclaim, not the dip" fixes the adverse selection: win-of-fills 16%→48% (mid) / 33%
(vwap), reversal 76%→17%/35%. VWAP-reclaim beats midpoint; the market-regime gate removes the
down-day bleed. **On the full sample E-vwap+gate looks promotable** — PF 1.53, positive in all
three regimes.

### 3.4 …but it fails out-of-sample (E-vwap+gate, time-split)

| Half | PF | avg P&L | up | down | chop |
|---|---|---|---|---|---|
| TRAIN (Jan–Apr) | **0.68** | **−0.169** | +0.219 | −0.436 | −0.317 |
| TEST (Apr–Jul) | 2.68 | +0.524 | +0.743 | +0.728 | +0.241 |

The full-sample edge is an **artifact of the recent rally**. Split by time, the strategy **loses
in the early half and only wins in the late (bull-run) half.** The pooled "all regimes green" hid
this because the late-half rally dominated the averages. E-vwap+gate is the **best variant in both
halves** — the confirmation mechanism is a real structural improvement — but "best" is not
"profitable": in the early half even the best variant bleeds.

### 3.5 Day-level portfolio + date-clustered bootstrap (the decisive test)

Candidate-days on the same day are **not independent** — the five selected names share one market
regime — so per-trade PF overstates significance. Collapsing each day's selected top-5 to one
**equal-weight portfolio return** (idle capital = 0 on non-fills) and bootstrapping **over days**
(date-clustered, 2000 resamples) is the honest test. It is also the form of the owner's promotion
gate ("Bootstrap CI above zero").

| Window | Variant | mean/day | winning-days | fills/day | total | maxDD | worst day | **date-clustered 95% CI** |
|---|---|---|---|---|---|---|---|---|
| FULL 6mo (105d) | A base | −0.044% | 30% | 2.50 | −4.6% | −6.1% | −0.60% | [−0.118%, +0.036%] |
| FULL 6mo (105d) | **E-vwap+gate** | +0.079% | 45% | 1.83 | +8.3% | −3.7% | −0.78% | **[−0.010%, +0.181%]** |
| TRAIN (52d) | E-vwap+gate | −0.055% | 33% | 1.63 | −2.9% | −3.7% | −0.78% | [−0.126%, +0.015%] |
| TEST/rally (53d) | E-vwap+gate | +0.212% | 57% | 2.02 | +11.2% | −0.7% | −0.54% | **[+0.057%, +0.414%]** |

**The per-trade "PF 1.53" does not survive day-level clustering.** On the full sample E-vwap+gate's
day-clustered CI is **[−0.010%, +0.181%] — it spans zero**, and winning-days is **45% (< 50%)**. The
positive mean is entirely a **test-half (rally) effect** (CI strictly above zero only there); the
train half is negative. This is the strongest form of the rejection: even the best variant fails the
"bootstrap CI above zero" bar once within-day correlation is respected.

## 4. Decision-rule scorecard — E-vwap+gate

| # | Condition | Full sample | With OOS split |
|---|---|---|---|
| 1 | Improves fill rate materially | ❌ (quality play, fewer fills) | — |
| 2 | Profitable after costs | ✅ (PF 1.53) | ❌ (train PF 0.68) |
| 3 | Not reliant on favorable period | ✅ (regimes green) | ❌ (loses pre-rally) |
| 4 | Target-after-entry improves | ✅ (16→33%) | ✅ |
| 5 | Reversal-loss doesn't worsen | ✅ (76→35%) | ✅ |
| 6 | Survives multiple regimes/periods | ✅ (pooled) | ❌ (train ≠ test) |

Passes 5/6 on the full sample; **the train/test split fails 2, 3, 6 → Rejected.**

### 4.1 Against the owner's formal promotion gate (`range_strategy_research_program`)

| Gate condition | E-vwap+gate | Pass? |
|---|---|---|
| Trades > 100 | ~192 filled (selected) | ✅ |
| Profit Factor > 1.2 | 1.53 per-trade (full sample) | ✅ |
| Win Rate > 50% | 33% of fills / 45% winning-days | ❌ |
| MaxDD not worse than baseline | −3.7% vs A −6.1% | ✅ |
| Expectancy positive | +0.079%/day full, **−0.055%/day train (OOS)** | ❌ |
| **Bootstrap CI above zero** | **[−0.010%, +0.181%] spans zero** | ❌ |

Fails **3 of 6** gate conditions — Win Rate, out-of-sample Expectancy, and the load-bearing
**Bootstrap CI**. **Not promotable.**

## 5. Verdict

**No robust tradable edge, even with VWAP-confirmed entry and a market-regime gate.** The
confirmation mechanism genuinely fixes the structural flaw (adverse selection) but produces only
a **period-dependent** profit — it pays in bull runs and loses before them. RNG-001's "rejected /
no tradable edge" verdict **stands and is strengthened**, now with a mechanistic explanation. No
change to the live Range strategy.

This is a **False-Positive-Reduction case study**: the full-sample metrics (PF 1.53, all regimes
green) *presented* a promotable edge; a single train/test split caught it as a rally artifact.
Pair with RNG-001 as a flagship "the discipline caught the false positive" example.

## 6. Caveats / limitations

- **Fill model is optimistic** (touch/close fill, no slippage) → the true edge is *lower* than shown.
- **Selection is a structural reconstruction** (ATR%×oscillation×class-weight), not the live
  evidence-first ranking (which would be circular to backtest).
- **Small per-regime-per-half samples** — the within-half regime numbers are noisy; the load-bearing
  signal is the half-level PF (0.68 vs 2.68).
- **6-month window** — longer history would sharpen the OOS test and cover more regimes.
- **Single confirmation threshold / gate definition**, not swept — deliberately, to limit the
  overfit surface (and the OOS split shows even this modest surface overfit the rally).

## 7. Reproduction

Backend-container scripts (run against the 5-Min bar cache):

- `apps/backend/scripts/research/range/backfill_intraday.py` — month-chunked 5-Min backfill (18 names).
- `apps/backend/scripts/research/range/range_funnel.py` — funnel diagnostic + bottleneck table.
- `apps/backend/scripts/research/range/range_variant_study.py` — variant A/B/D/E replay, selection
  filter, regime split, train/test OOS split, day-level portfolio + date-clustered bootstrap.

## 8. Follow-on direction

1. **Close RNG-001 stronger.** This sub-study is the **final supporting evidence** for RNG-001,
   which now rests on four independent legs: (a) the original strategy rejection, (b) the entry-mode
   comparison, (c) the corrected data-integrity re-run (ADR-0033), and (d) — here — a *mechanistic*
   explanation of **why** the entry fails plus the rejection of a plausible fix. Mark RNG-001
   **Completed · Rejected (Evidenced) · Archived.**
2. **Stop tuning Range.** More levels/buffers/thresholds/gates are data mining; this study shows the
   danger directly (the full-sample VWAP+gate looked promotable; the OOS split killed it). No further
   RNG-001 parameter work.
3. **Preserve the tooling as a capability — CAP-025 (Intraday Replay & Entry-Funnel Diagnostics).**
   The intraday sequence replay, entry/target/stop funnel, post-activation fill diagnostics,
   target-before-entry detection, regime split, and train/test time-split should be standard for any
   future intraday strategy. Charter: `docs/implementation/evidence/cap_025/`.
4. **If the VWAP-confirmation idea is pursued, it is a NEW strategy, not a Range patch** — an
   *Opening-Range Reclaim / Momentum-Confirmation* mechanic (candidate program **ORM-001**), opened
   only with (a) a materially **longer test window** than six months and (b) **pre-registered rules
   before testing**. It must not resurface as "Range Trader with a tweak."
