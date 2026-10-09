# RNG-001 (Range Trader) — Rejection Summary Report

| Field | Value |
|---|---|
| Report date | 2026-10-09 |
| Program | RNG-001 — Range / Mean-Reversion (Range Trader) |
| Verdict | 🔴 **Rejected (Evidenced) · Archived** — no robust, statistically significant tradable edge |
| Governing rule | ADR 0014 — a strategy earns paper/live only with a robust, statistically significant edge |
| Live impact | None. The Range strategy is kept only as the permanent "honest rejection" benchmark (Evidence Sandbox, user 2) |
| Compiled from | `docs/implementation/evidence/range_rejection/range_evidence.md`, `docs/implementation/evidence/range_entry_logic/RNG_EntryLogic_Study_v0.2.md`, ADR 0033, `docs/design/research_portfolio_lineup.md`, `docs/review/RangeTrader_PaperTrial_RunbookAndPlan_v0.2.md`, `tasks/todo.md` |

This report summarizes existing repository evidence. It does not re-run any study, and every figure below is quoted from the cited source documents.

---

## 1. Executive summary

RNG-001 tested whether `RangeTraderVWAP`, an intraday mean-reversion strategy that buys near support and sells near resistance, has a robust edge. It does not. The rejection rests on four independent legs, each of which fails or is inconclusive on its own:

1. **Out-of-sample collapse.** Every config that passed in-sample failed out-of-sample. The best in-sample profit factor (PF) was 1.37 and its out-of-sample PF was 0.92, a NO-GO.
2. **Statistical insignificance.** The best prior config (102 trades, PF 1.271) has a bootstrap 95% CI on mean per-trade P&L of **[−$19.74, +$57.53]**, which includes zero.
3. **Decaying walk-forward.** PF falls across four consecutive windows, from 1.69 to 0.89. The last window is a loser.
4. **A mechanistic cause.** The entry is structurally adversely selected. It fills into falling knives and misses the rallies. The one plausible fix (VWAP-reclaim confirmation plus a market-regime gate) looked promotable on the full sample but failed out-of-sample and failed the date-clustered bootstrap.

The rejection also survived a data-integrity incident (§5). Phase 1 and Phase 3 numbers had been computed on a biased, incomplete cache. The platform disclosed the fault, rebuilt the data, re-ran the studies, and the verdict held.

---

## 2. What was tested

| Item | Detail |
|---|---|
| Hypothesis | `RangeTraderVWAP` has a robust intraday mean-reversion edge |
| Strategy config (final test) | PLTR, VWAP bands, `entry_sigma=2.0`, `exit_sigma=0.5`, `stop_sigma=3.0` (the best prior config, the only one that ever cleared in-sample) |
| Data | Alpaca IEX 5-minute bars, regular trading hours, 2026-01-02 to 2026-06-12 |
| Method | In-sample/out-of-sample split (§5c), 4-window walk-forward, bootstrap on per-trade P&L, then (2026-07-06) an intraday entry-logic replay study |
| Standard | ADR 0014 (backtests are evaluation ground truth) and the Evidence Engineering methodology |

**Caveat that matters:** intraday history is only about 6 months, which is effectively **one market regime**. The evidence document calls this single-regime caveat "load-bearing". A deeper walk-forward would need more intraday data. The bootstrap on the full trade set is the decisive test, and it is decisive on its own.

---

## 3. Evidence for rejection

### 3.1 In-sample to out-of-sample collapse (§5c, 2026-06-16)

Every in-sample-passing config collapsed out-of-sample. The best case went from IS PF 1.37 to OOS PF 0.92 (**NO-GO**). A config that cannot hold up on data it was not fitted to has no demonstrated edge.

### 3.2 Full-window edge and bootstrap (the decisive test)

| Metric | Value |
|---|---|
| Trades | 102 |
| Profit factor | 1.271 (below the 1.3 bar) |
| Mean per-trade P&L | $15.14 |
| Win rate | 55% |
| Total P&L | $1,545 |
| **Bootstrap 95% CI of mean per-trade P&L** | **[−$19.74, +$57.53]** |

The CI includes zero, so the positive mean is statistically indistinguishable from noise. A PF of 1.27 and a 55% win rate look mildly attractive until the sampling uncertainty is applied.

### 3.3 Walk-forward consistency

| Window | Trades | Profit factor | Mean P&L |
|---|---|---|---|
| 2026-01-02 to 2026-02-11 | 29 | 1.691 | $49.23 |
| 2026-02-11 to 2026-03-23 | 25 | 1.141 | $7.10 |
| 2026-03-23 to 2026-05-02 | 30 | 1.325 | $12.88 |
| 2026-05-02 to 2026-06-12 | 22 | 0.886 | −$6.37 |

Three of four windows are profitable, but the edge **monotonically decays** in mean P&L, from $49.23 to $7.10 to $12.88 to −$6.37. The strongest window is the earliest and the latest window loses. That shape matches a fading or overfit effect, not a stable one.

### 3.4 Mechanism: the entry is adversely selected (entry-logic study, 2026-07-06)

The study was triggered when the live Range Trader took **0 trades** on a day when all five selected names touched both their buy and sell levels. The obvious fix, "raise the buy and sell levels", was tested with a sequence-correct intraday replay (not daily OHLC). It used 18 names, 126 sessions and 5-minute bars.

**Funnel (n = 2,267 candidate-days):**

| Outcome | Share |
|---|---|
| Buy touched after activation (fill) | 46.7% |
| Fill then target hit (win) | 8.3% |
| Fill then stop hit (reversal) | **29.2%** |
| Fill then no target, flat at end of day | 9.1% |
| Target hit **before** entry (missed breakout) | **49.0%** |
| Never re-touched, no target | 4.3% |

Of the days that filled, **62.7% reversed to the stop and only 17.8% reached the target.** The fade-at-support entry selects the strategy into falling knives and out of the rallies. Baseline economics were PF 0.70, average −0.116% per trade, profitable only in up-regimes. This is not a level-placement problem. Moving the level cannot fix an entry that sits on the wrong side of the move.

**"Raise the levels" is refuted** (selected top-5, n = 523):

| Variant | PF | Avg P&L |
|---|---|---|
| A: baseline | 0.81 | −0.085 |
| B: raised entry | 0.73 | −0.198 |
| D: raise both | 0.73 | −0.196 |

Raising the entry increases fills but makes results worse in every regime, because more fills means more falling knives.

### 3.5 The one plausible fix also fails

Entering on a reclaim ("buy the reclaim, not the dip") fixes the adverse selection. The best variant, **E-vwap+gate**, enters on a close above intraday VWAP, only when SPY is above its own VWAP. It reached PF 1.53 and +0.217% average P&L on the full sample, with all three regimes green. It then failed two further tests.

**Time split (out-of-sample):**

| Half | PF | Avg P&L |
|---|---|---|
| Train (Jan to Apr) | **0.68** | −0.169 |
| Test (Apr to Jul) | 2.68 | +0.524 |

The full-sample edge is an **artifact of the recent rally**. The strategy loses before the rally and wins only during it.

**Day-level portfolio with date-clustered bootstrap.** Candidate-days on the same day share one market regime, so per-trade PF overstates significance. Collapsing each day to one equal-weight return and bootstrapping over days:

| Window | Mean/day | Winning days | 95% CI (date-clustered) |
|---|---|---|---|
| Full (105 days) | +0.079% | 45% | **[−0.010%, +0.181%]**, spans zero |
| Train (52 days) | −0.055% | 33% | [−0.126%, +0.015%] |
| Test / rally (53 days) | +0.212% | 57% | [+0.057%, +0.414%] |

The CI is strictly positive only in the rally half.

**Against the owner's formal promotion gate**, E-vwap+gate fails 3 of 6 conditions:

| Gate condition | Result |
|---|---|
| Trades > 100 | ✅ (~192) |
| Profit factor > 1.2 | ✅ (1.53 per trade, full sample) |
| Win rate > 50% | ❌ (33% of fills, 45% winning days) |
| Max drawdown no worse than baseline | ✅ (−3.7% vs −6.1%) |
| Positive expectancy | ❌ (−0.055%/day out-of-sample) |
| **Bootstrap CI above zero** | ❌ (spans zero) |

Its decision-rule scorecard fails conditions 2, 3 and 6 once the train/test split is applied. The study classifies this as a **false-positive-reduction case**. Full-sample metrics presented a promotable edge, and a single train/test split exposed it as a rally artifact.

The replay used an optimistic fill model (touch or close fill, no slippage), so the true edge is lower than shown.

---

## 4. Verdict and governance basis

- **Verdict:** Rejected (Evidenced). RNG-001 is the platform's first formally rejected strategy and is archived as a documented, citable "honest no".
- **Basis:** ADR 0014 requires a robust, statistically significant edge. RNG-001 fails the significance test (bootstrap CI spans zero), the stability test (walk-forward decay, OOS collapse), and the robustness test (the best fix is regime-dependent).
- **Dated record:** the §5c NO-GO was on 2026-06-16, and the entry-logic study (2026-07-06) strengthened the rejection.
- **Registry status:** 🔴 Rejected, kept as the permanent benchmark in the research portfolio. It is the "Archived/Rejected" slot in the lineup of Approved alpha, Diversifier sleeve, Rejected strategy, and Capability under validation. `tasks/todo.md` records the archive as **PR #141**, with infrastructure kept (the §5c gate, the oscillation screener, the VWAP±σ variant).

The platform's value claim is that it can distinguish alpha from overlay from failure. RNG-001 is the demonstration of the "failure" case.

---

## 5. Data-integrity incident and the verdict surviving it (ADR 0033)

On 2026-06-30 the intraday bar cache was found to have **silently truncated** cold multi-year fetches at the provider's 10,000-row page limit, then written zero-byte `.empty` markers for every un-returned day. The Range top-5 and SPY caches held about 250 non-contiguous sessions, with 2024 and 2026 almost entirely missing and roughly 800 to 970 bogus markers per symbol. **Range Phase 1 and Phase 3 numbers had been computed on that biased ~⅓ sample.**

- The fault was caught and disclosed in an **Evidence Correction Report**.
- The cache was rebuilt in monthly chunks and the affected studies were re-run.
- **The RNG-001 verdict held** after the re-run.
- The incident led to ADR 0033 (Historical Data Integrity), which says: "Research must fail because the hypothesis is wrong, not because the data is incomplete."

**Status caveat from ADR 0033:** its points 1 to 3 (scope `.empty` markers to the returned range, treat an exactly-page-limit response as possibly truncated, chunk cold fetches) were recorded as **not yet implemented** in the writer at the time of the ADR. The monthly-chunk rebuild script is the mitigation. Point 4 (`dataset_health` coverage assertion) is implemented. This report did not re-verify the current code state. The entry-logic study avoided the issue by backfilling month-chunked.

---

## 6. Limitations of the evidence

- **Single regime, about 6 months.** Intraday history is short, so out-of-sample depth is limited. This is the main reason a "never works" claim would be too strong. The accurate claim is "no demonstrated robust edge".
- **Config scope.** The decisive bootstrap used one best config on PLTR. The entry-logic study used a broader 18-name universe with a structural (ATR% × oscillation × class-weight) selection filter, not the live evidence-first ranking.
- **Different samples give different PFs.** The decisive PLTR run has PF 1.271 and the broad-universe baseline has PF 0.70 to 0.81. Both are below the bar, but they are not directly comparable.
- **Optimistic fills.** Costs are 5 bps per side, with no slippage in the replay. Real performance would be lower.
- **Small per-regime samples.** Within-half regime figures are noisy. The half-level PF (0.68 vs 2.68) is the signal that carries weight.

None of these gaps points toward a hidden edge. The optimistic fill model biases against rejection, and the short window limits power in both directions.

---

## 7. Consequences and what remains allowed

| Topic | Decision |
|---|---|
| Live Range strategy | Unchanged. The study explicitly does **not** justify raising levels, enabling new entries, or increasing allocation |
| Further Range tuning | **Stopped.** More levels, buffers, thresholds or gates are data mining. The VWAP+gate result shows the danger directly |
| Operational use | Range Trader runs on paper (user 2, `range@local.dev`) as an **execution and operations validation**, not an edge test. Losing days and zero-trade days are expected outcomes (runbook: "Yes, expected, RNG-001 is rejected") |
| Reuse of VWAP-confirmation idea | Only as a **new** strategy (candidate ORM-001, Opening-Range Reclaim / Momentum Confirmation), with a materially longer test window and rules **pre-registered before testing**. It must not return as "Range Trader with a tweak" |
| Reopening | ADR 0037 auto-checks previously rejected patterns before a research line reopens. The ATP plan's `RANGE-SIP-OBS-001` is a measurement program and is explicitly **not** authorization to restart RNG-001. Any candidate claiming a "new economic mechanism" must pass a non-equivalence test in its pre-registration |
| Preserved tooling | CAP-025 (Intraday Replay and Entry-Funnel Diagnostics): sequence replay, funnel, regime split and train/test split, standard for any future intraday strategy |

---

## 8. Reproduction pointers

- Rejection evidence: `docs/implementation/evidence/range_rejection/range_evidence.{md,json}`
- Entry-logic study: `docs/implementation/evidence/range_entry_logic/RNG_EntryLogic_Study_v0.2.md`
- Study scripts: `apps/backend/scripts/research/range/{backfill_intraday,range_funnel,range_variant_study}.py`
- Cache rebuild: `scripts/research/rebuild_5min_cache.py`
- Data-integrity ADR: `docs/adr/0033-historical-data-integrity.md`
- Operations: `docs/runbook/range-trader-daily-operations.md`, `docs/review/RangeTrader_PaperTrial_RunbookAndPlan_v0.2.md`
