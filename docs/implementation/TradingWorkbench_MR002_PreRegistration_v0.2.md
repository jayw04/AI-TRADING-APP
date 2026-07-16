# MR-002 — Pre-Registration v0.2 (DRAFT) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** → **Planning**
(**Running** on freeze) · **Authority:** owner strategy proposal `Docs/Strategies/Proposed Strategies.txt`
+ owner review `Docs/Strategies/MR002_PreRegistration_Review_and_Recommendations.md` (2026-07-11).
**Supersedes v0.1.**
**Status:** 🟡 **DRAFT v0.2 — NOT FROZEN.** All eight review findings and the recommended Q1–Q5 decisions
are folded in (changelog §14). Freeze is now blocked on exactly two items, both **pre-freeze data
verifications** (§8): **(a)** a genuinely point-in-time earnings schedule and **(b)** point-in-time
historical sector classifications. No backtest code runs, and no data beyond these verifications is
materialized, until FROZEN v1.0.

> **Governance disposition (binding):** RNG-001 remains **Completed · Rejected (Evidenced) · Archived**
> and is not modified. MR-002 is a **new hypothesis** — not a continuation or parameter repair of
> RNG-001's VWAP-deviation fade. RNG-002 is chartered separately, later. Per the review: the hypothesis
> is **not** to be "improved" pre-test — no momentum, volatility, RSI, or market-regime filters may be
> added before the first test; they would weaken the evidentiary value.

## 1. Hypothesis (unchanged from v0.1)

After removing broad-market and sector movements, unusually large company-specific (residual) price moves
frequently represent temporary liquidity pressure rather than information, and **partially reverse over
the following one to five trading sessions**. The mechanism is compensation for providing liquidity; the
edge must come from **breadth and repeatability** (now tested directly by the §10 breadth gates), not
magnitude in any single episode. Differences from RNG-001 are pre-registered: no distance-from-VWAP fade;
market + sector removed before measuring overextension; many small independent trades; information-driven
moves (earnings windows, large gaps) excluded.

## 2. Universe (point-in-time, reconstituted monthly)

Reconstituted on the **first trading day of each month** using only data available at that date:

- **Longs: top 250** US common stocks by trailing 60-session median dollar volume.
  **Shorts: top 150** by the same measure (Q4 — the deeper-liquidity short book replaces the v0.1
  general-collateral assumption; any available hard-to-borrow flag excludes the name from the short side).
- Close price **> $10** on the reconstitution date · trailing 60-session **median dollar volume > $25M**.
- **Common stocks only** — no ETFs, ADRs, preferreds, SPACs, units (Sharadar TICKERS category filters).
- **No recent IPOs:** ≥ 252 prior trading sessions of price history.
- **Sector-proxy availability (Q5):** a stock is eligible only while its **point-in-time** sector has a
  registered sector-ETF proxy trading at that date (XLK/XLF/XLE/XLV/XLI/XLP/XLY/XLU/XLB; XLRE from
  2015-10; XLC from 2018-06). **No mechanical remapping to historical parent ETFs** — a sector without a
  live proxy simply excludes its stocks for that period (mainly Communication Services before XLC).
- A name that leaves the universe mid-month is not force-exited; existing positions run to their normal
  exit, but no new entries.
- **Universe sizes 200 and 300 are post-verdict diagnostics only** — run after the verdict, and they
  cannot affect it (review §4).

Survivorship-freedom is mandatory: membership is computed from point-in-time price/volume history
(Sharadar SEP), never from a current-day constituent list.

## 3. Signal construction (frozen definitions — review §1 corrections applied)

**Sector-relative factor** (removes SPY collinearity): `f_Sector,t = r_Sector,t − r_SPY,t`.

For every stock `i`, estimate the rolling **60-session** OLS model on daily arithmetic total returns:

`r_i,t = α_i + β_m,i · r_SPY,t + β_s,i · f_Sector,t + ε_i,t`

- Betas estimated on sessions `t−60 … t−1` (never including day `t`); the day-`t` residual is
  `ε_i,t = r_i,t − α̂_i − β̂_m,i·r_SPY,t − β̂_s,i·f_Sector,t`.
- Sector mapping uses the stock's **point-in-time** classification (§8 verification); an unresolvable
  sector ⇒ **excluded**, never defaulted (CAP-024 principle).

**Signal (mean-adjusted z-score):** `R5_i,t = Σ_{k=0..4} ε_i,t−k` and

`z_i,t = (R5_i,t − μ_i,t−1) / σ_i,t−1`

Registered normalization rules (all frozen):

- `μ` and `σ` are the rolling mean and standard deviation of the 5-session cumulative residual, computed
  on windows **ending at `t−1`** — the current-day signal never enters its own normalization.
- Exactly **60 complete five-day observations** required (overlapping windows); fewer ⇒ ineligible that day.
- Standard deviation uses **`ddof=1`**.
- Returns are **arithmetic total returns** (dividend-adjusted).
- Any missing observation in the stock's window ⇒ ineligible that day.
- **No winsorization** (none is frozen).

## 4. Entry, exit, and execution (frozen — Q3 resolved)

**Timing:** signals computed after the close of session `t`; entries and exits execute at the **next
session's open** (`t+1` open), with costs per §9. Close-to-close execution is **diagnostic only**.

**Gap filter (execution-day gap):** the entry order is **cancelled at the `t+1` open** if
`|Open_t+1 / Close_t − 1| ≥ 6%`.

**Long entry — all must hold at close `t`:** `z ≤ −Z_entry` · stock in the **bottom 10%** of that day's
eligible residual z-scores · no earnings event within the **[t−2, t+2]** exclusion window under the §8
PIT-calendar rule · no *announced* merger/split/delisting/major-corporate-action (announcement-date-based,
never outcome-based — §8) · execution-day gap filter passes · liquidity envelope (§9) satisfied.

**Short entry — mirror:** `z ≥ +Z_entry` · top 10% of eligible scores · short universe + borrow rules
(§2) · same event, gap, and liquidity exclusions.

**Exit — first occurrence of:** `|z|` returns inside **±0.35** · **5 sessions** elapsed · residual
extends beyond **±3.5** *and* the market or sector confirms (SPY or the sector ETF moves the same
direction ≥ 1σ of its own 60-session daily vol that day) — the hypothesis-failure stop · an earnings or
prohibited event enters the next-session window · mandatory portfolio-risk reduction (§5). Exits also
execute at the next open. **No tight ordinary price stop** (pre-registered).

**Corporate-action and market-microstructure edge cases (registered — review §2):**

- **Halts:** if a stock is halted at the scheduled execution open, the order executes at the first
  available regular-session print after resumption that day; if none, the entry is cancelled / the exit
  rolls to the next session's open.
- **Missing next open** (suspension, data gap): entries are cancelled; exits execute at the first
  available session open thereafter.
- **Delistings:** positions in delisted securities are valued at the final available price or announced
  cash consideration; delisted names are **never silently dropped** from the P&L series.
- Exclusions begin at the **public announcement date** of a corporate action — a stock is never excluded
  retroactively because it *eventually* merged or delisted.

## 5. Portfolio construction (frozen, deterministic — review §3 applied)

**Gross exposure is a 100% MAXIMUM, not a target.** The strategy holds cash rather than force marginal
trades; unused capital remains cash, and **no return is credited to cash** in the primary result (a
cash-yield variant may be reported as a labelled secondary).

**Deterministic daily algorithm (in order):**

1. Process **exits first**, then entries. One position per symbol; **no pyramiding**; a symbol exited at
   the `t+1` open cannot be re-entered at that same open.
2. Build candidate sides from §4. Raw weight per name ∝ 1/σ_resid (its 60-session 5-day residual vol —
   equal residual-risk contribution), normalized within each side.
3. **Dollar-neutral books:** long gross = short gross = min(feasible long side, feasible short side,
   50% of NAV). The larger side scales down to match the smaller; **no forced trade is ever added solely
   to satisfy neutrality**.
4. Apply constraints in this **registered reduction order**: (i) position cap **1.5% of gross** →
   (ii) sector caps → (iii) beta limit → (iv) volatility overlay. Freed capacity goes to cash, not
   redistribution. If constraints are infeasible, remove the **least extreme** candidate (smallest |z|)
   first and re-apply.
5. Existing positions remain at **fixed shares until exit** — no daily re-marking to target weights —
   except mandatory reductions from (ii)–(iv), which do trade and do incur §9 costs.

**Registered limits:** sector **net** exposure ≤ **5% of gross** per sector (dollar-based) · sector
**gross** exposure ≤ 20% · portfolio **beta** (from the §3 β̂_m estimates, dollar-weighted) ≤ **0.10 per
unit of gross** · max position 1.5% of gross · no position > 3% of projected portfolio risk.

**Volatility overlay (secondary, not primary):** the **primary result is the unscaled strategy** (≤1.0×
gross cap). The **8% annualized vol target is reported as a secondary portfolio transformation**:
scale-down **only** (factor = min(1, 8% / realized 63-day vol), computed from returns through the prior
session, capped at 1.0, never levering up), applied as a whole-portfolio scalar whose rebalancing trades
incur full §9 costs. All §10 gates read on the **primary (unscaled)** result.

## 6. Frozen parameter policy (exactly three configurations)

| Config | Entry `Z_entry` | Exit z | Max hold | Role |
|---|---|---|---|---|
| A | 1.75 | 0.35 | 5 sessions | neighborhood sensitivity |
| **B (PRIMARY)** | **2.00** | 0.35 | 5 sessions | **the verdict configuration** |
| C | 2.25 | 0.35 | 5 sessions | neighborhood sensitivity |

The verdict is read on **B only**. No other combinations are run. The multiple-testing burden is tracked
by the **trial ledger** (§10, DSR) — not assumed to be 3.

## 7. Testing sequence (frozen order — review §4 contradictions resolved)

1. **Development (first 50%):** A, B, and C run for **implementation verification only** — no winner
   selection, no gate is read here. Development results appear in the evidence package as diagnostics.
2. **Walk-forward validation (next 25%):** A, B, and C; **five contiguous, non-overlapping folds**.
   B remains primary; A/C determine the **parameter-neighborhood stability gate** (which applies to
   validation, not development). "≥60% positive folds" = **at least 3 of 5 folds** with positive net
   returns on B.
3. **Sealed OOS (final 25%):** **B only, exactly once**, after freeze. All OOS diagnostics use B.
   Any post-hoc change is a new program (**MR-003**, §12 Q1) with a new untouched sealed period.
4. **Stationary/moving-block bootstrap** (§10 spec) on net daily portfolio returns.
5. **Regime decomposition:** bull / bear / sideways / high-vol / low-vol attribution.
6. **Cost sensitivity:** 0.5× / 1× / 2× grid + 30 bps/side severe diagnostic + **breakeven cost** headline.
7. **PBO (diagnostic only) + Deflated Sharpe (gate, with the trial ledger).**
8. **Paper-trading verification before any production discussion** (CEE from day one).

**Drawdown sample definitions:** the "maximum drawdown" gate reads on **validation + sealed OOS
combined** (development excluded); sealed-OOS max drawdown is **also reported separately**.

## 8. Pre-freeze data verifications (the two remaining FREEZE BLOCKERS) + data plan

| # | Verification | Rule being verified |
|---|---|---|
| **V1** | **PIT earnings schedule.** The exclusion `[t−2, t+2]` uses *future* earnings dates, which is valid only if the schedule was **known at `t`**. Verify Sharadar EVENTS (or an alternative calendar) provides announcement timestamps / as-known-at dates. **Registered rule: option 1** — use only schedules known at `t`. If no genuinely PIT calendar exists, the fallback (restrict exclusion to events that already occurred through `t`) must be **explicitly re-approved by the owner before freeze**, because it materially changes entries. | §4 earnings exclusion |
| **V2** | **PIT sector classification.** Mapping historical returns with a company's *current* sector is classification look-ahead. Verify a point-in-time sector history (Sharadar TICKERS is a current snapshot — a PIT source or a documented, owner-approved approximation with measured reclassification rates is required). **This is a freeze blocker, not a manifest disclosure.** | §3 sector factor + §2 eligibility |

| Input | Source | Note |
|---|---|---|
| Stock daily prices/volume | **Sharadar SEP** (dividend-adjusted) | survivorship-free, PIT |
| Universe metadata | Sharadar TICKERS | category/type filters |
| Sector classification | **pending V2** | PIT source required |
| Earnings dates | **pending V1** (Sharadar EVENTS candidate) | PIT-known-at-t required |
| Corporate actions | Sharadar ACTIONS | announcement-date-based (§4) |
| SPY + sector ETF returns | Yahoo adjusted close (research-grade, TREND precedent) | no SFP access |

**Data Availability Gate (first execution step after freeze):** SEP depth/coverage for the top-250/150
construction across the full window; ETF proxy history; EVENTS/ACTIONS coverage; realized window and
monthly universe counts recorded in the manifest. If coverage forces a window materially shorter than
~10 years, stop and re-review (power).

## 9. Cost model & capacity (Q2 resolved + review §8)

- **Base:** **10 bps/side** (spread + impact, all-in) · short borrow **50 bps/yr** on short market
  value, accrued daily.
- **Mandatory stress (pass gate):** **2×** — 20 bps/side · borrow-uncertainty stress **300 bps/yr**
  (replaces the v0.1 2×-borrow stress).
- **Severe diagnostic (reported, not gated):** 30 bps/side.
- **Long-only and short-only P&L attribution** reported at every cost tier.
- **Reference backtest NAV: $10M.** Order size capped at **2% of trailing 20-session median dollar
  volume**; orders above the cap are **clipped, not delayed**; unfilled notional remains cash.
- **Capacity reporting:** the maximum scalable NAV at which **95% of orders remain below the cap**, plus
  diagnostic runs at **$10M / $25M / $50M / $100M**.
- Binding rejection rule: a short-horizon strategy that passes only under zero-cost or close-price
  execution **must be rejected**.

## 10. Verdict framework & pass gates (LOCKED at freeze)

Verdict reads on **config B, primary (unscaled) result, net of base costs, at the $10M reference NAV**,
on the samples named per gate.

**Bootstrap specification (registered):** **stationary bootstrap** on net daily portfolio returns —
**10,000 replications** · fixed registered seed **20260711** · expected block length **5 trading days**
(preserves the serial dependence of 5-day holds) · **10-day block-length sensitivity** · statistic =
**95% one-sided lower confidence bound for mean daily net return**.

**✅ Approved (standalone)** — ALL of:

| Gate | Requirement | Sample |
|---|---|---|
| Net Sharpe | ≥ 0.70 | sealed OOS |
| Net Calmar | ≥ 0.75 | sealed OOS |
| Max drawdown (net) | ≤ 15% | validation + sealed OOS (sealed also reported separately) |
| Positive walk-forward folds | ≥ 3 of 5 | validation |
| Bootstrap lower bound (95%, one-sided) | > 0 | sealed OOS |
| Cost stress | profitable at 2× costs + 300 bps borrow | sealed OOS |
| Parameter stability | A and C profitable (net) | validation |
| Deflated Sharpe | ≥ 95% significance, using the **trial ledger** | sealed OOS |
| Net annualized return | ≥ 3% at the registered gross cap | sealed OOS |
| **Breadth** | ≥ 500 completed trades · ≥ 100 distinct entry dates · ≥ 100 long trades · ≥ 100 short trades | sealed OOS |
| Trade concentration | top-10 trades ≤ 20% of total positive trade P&L · single stock ≤ 10% of total positive P&L | sealed OOS |
| Yearly concentration | max positive annual P&L ÷ **sum of all positive annual P&L** ≤ 35% | validation + sealed OOS |
| Regime concentration | no single regime > 60% of positive P&L (same denominator convention) | validation + sealed OOS |
| Capacity | positive net edge at $10M under the 2% participation cap | sealed OOS |

**PBO is a diagnostic, not a gate** (review §5): computed and reported with an explicit "N=3 —
underpowered" warning; it cannot pass or fail the program. **Trial ledger (registered, for DSR):** the
effective trial count includes configs A/B/C **and** the mean-reversion family's prior examined variants
(RNG-001 and its documented sub-studies; any informal MR variants must be logged here before freeze).
The ledger is a first-class evidence-package artifact.

**🟡 Diversifier (B)** — fails Approved, but ALL of: net sealed-OOS Sharpe ≥ 0.40 · bootstrap lower
bound > 0 · |corr| ≤ 0.30 vs the MOM-001 canonical book on overlapping dates · cost-stress, DSR, breadth,
and all concentration gates still pass.

**Power rule (registered before testing — replaces v0.1's MDE-only formulation):** minimum relevant
Sharpe **0.40** · required power **80%** · confidence **95%**. Then:

- Positive observed Sharpe, CI spans zero, **and** power < 80% to detect Sharpe 0.40 →
  **Power-Limited · Inconclusive**.
- CI spans zero **with** ≥ 80% power to detect Sharpe 0.40 → **🔴 Rejected**.
- Negative observed Sharpe → **🔴 Rejected**, regardless of the power computation.

**🔴 Rejected** additionally fires when any mandatory gate fails with adequate power, or the zero-cost
rejection rule (§9) fires. The key decision metric remains **credible net return after robustness and
cost gates — never highest backtested CAGR**.

## 11. Evidence package (`evidence/mr_002/`, seeded & reproducible)

Pre-reg (frozen) · harness code + registered seed · run manifest (data snapshot hashes, realized window,
monthly universe counts, V1/V2 verification records, PIT-exclusion log) · **trial ledger** · results:
Performance (CAGR, Sharpe, Sortino, Calmar, maxDD — primary unscaled + the 8% overlay as secondary) ·
Trade quality (win rate, payoff, expectancy, trade count, long/short attribution) · Robustness (folds,
bootstrap CI + 10-day-block sensitivity, A/C neighbors, PBO-as-diagnostic) · Costs (gross vs net,
0.5×/1×/2×/severe, breakeven) · Stability (annual + regime attribution) · Concentration (top
trades/dates/sectors/names) · Capacity ($10–100M grid, max scalable NAV) · Validation (DSR + ledger,
power computation) · Evidence Brief + registry/`programs.py` entry.

## 12. Owner decisions — RESOLVED per the 2026-07-11 review

- **Q1 · ID & revisions:** keep **MR-002**. A substantive post-sealed-OOS change becomes **MR-003** (a
  new, unmistakable research trial). MR-002 document versions are only for pre-OOS corrections,
  non-substantive doc changes, or identical-strategy reproduction.
- **Q2 · Costs:** 10 bps/side base · 20 bps/side mandatory stress · 2% ADV cap · **added:** 30 bps/side
  severe diagnostic, 50 bps/yr base borrow, **300 bps/yr** borrow stress, long/short P&L attribution.
- **Q3 · Execution:** next-session open confirmed; gap filter = **execution-day gap**
  `|Open_t+1/Close_t − 1| < 6%`, order cancelled at the open otherwise; next-close is diagnostic only.
- **Q4 · Hard-to-borrow:** longs top-250, **shorts top-150**; exclude any available HTB flags; 300 bps
  borrow sensitivity.
- **Q5 · Sector history:** **no mechanical parent-ETF remapping**; stocks are excluded while their PIT
  sector lacks a live registered ETF proxy (mainly Communication Services pre-XLC). PIT sector
  verification remains blocker **V2**.

## 13. Stopping rule & lifecycle

One primary design; one sealed test; **no parameter adjustment after viewing sealed OOS results** — a
substantive revision is **MR-003** with a fresh pre-registration and untouched test period. No paper
promotion unless Approved or Diversifier clears; paper requires CEE from day one and the standard
promotion protocol. If Rejected: archive with the evidence brief (CAP-011). Registry entry at freeze.

## 14. Changelog v0.1 → v0.2 (review findings folded)

1. **Signal:** sector factor → sector-relative `f = r_Sector − r_SPY` (collinearity); z-score now
   mean-adjusted with `μ, σ` through `t−1`; ddof=1, 60 complete obs, arithmetic returns, missing ⇒
   ineligible, no winsorization — all registered.
2. **PIT:** earnings exclusion requires a known-at-`t` calendar (V1); corporate-action exclusions are
   announcement-dated; halts/missing-opens/delisting valuation registered; **PIT sector classification
   promoted to freeze blocker (V2)**.
3. **Construction:** 100% gross is a **maximum**; full deterministic algorithm registered (exits-first,
   no pyramiding, no same-open re-entry, fixed shares, dollar-neutral matched-to-smaller-side, cash
   uncredited, least-extreme removal, reduction order); sector net ≤5%/gross ≤20%; beta ≤0.10/gross;
   **8% vol target demoted to a secondary scale-down-only overlay** — primary result is unscaled.
4. **Test sequence:** A/B/C in development (verification) and validation (stability gate); sealed OOS =
   B once; 5 contiguous folds (≥3/5); drawdown-sample definitions; universe 200/300 → post-verdict
   diagnostics.
5. **PBO removed as a gate** (N=3 underpowered; kept as labelled diagnostic); **DSR keeps its gate but
   with a trial ledger** including the RNG-001 family, not an assumed N=3.
6. **Bootstrap registered:** stationary, 10,000 reps, seed 20260711, expected block 5d (+10d
   sensitivity), 95% one-sided lower bound on mean net daily return. **Power rule registered:** minimum
   relevant Sharpe 0.40 / 80% power / 95% confidence with the three-way verdict mapping.
7. **Breadth & economic-significance gates added** (≥500 trades, ≥100 dates/long/short; top-10 ≤20%;
   single stock ≤10%; net annualized return ≥3%); yearly-concentration denominator fixed to positive
   annual P&L; concentration gates read validation + sealed OOS.
8. **Capacity registered at $10M NAV**, clip-not-delay, 95%-under-cap max-scalable-NAV headline,
   $10/25/50/100M diagnostics.
9. **Q1–Q5 resolved** per the review (§12); v0.1's five open questions are closed.

---

*Draft v0.2 → run pre-freeze verifications V1 (PIT earnings calendar) + V2 (PIT sector history) → owner
sign-off → **FROZEN v1.0** → Data Availability Gate → development sample. The hypothesis itself is
unchanged and must remain so through the first test.*
