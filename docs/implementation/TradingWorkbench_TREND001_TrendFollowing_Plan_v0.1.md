# Trading Workbench — Trend Following: Research Plan & Pre-Registration (v0.1)

> ## Research Program `TREND-001`
> | | |
> |---|---|
> | **Strategy family** | Trend Following |
> | **Investment philosophy** | Time-series (absolute) trend — own a name only while *its own* trend is up; stand in cash otherwise |
> | **Research goal** | Does a time-series trend book add value to the **platform** — as standalone risk-adjusted alpha (H1), a diversifier of the cross-sectional momentum book (H2), or a downside-protection / participation sleeve (H3)? |
> | **Status** | **FROZEN (owner sign-off 2026-06-24) — OQ1–OQ4 resolved (§11); ready to build.** Pre-registration locked before any run. |
> | **Owner** | Jay |
> | **ADR** | TBD (assign on a VALIDATED verdict) |
> | **Program #** | the platform's **6th** research program — `MOM-001` 🟢 · `RNG-001` 🔴 · `MF-001` 🟡 · `SEC-001` 🟡 · `LOW-001` 🟡 · **`TREND-001` ⚪ → 🔵 Research** |

| Field | Value |
|---|---|
| Document | **Trend Following research program** — plan + **pre-registered** acceptance criteria. |
| Version | **v0.2 (2026-06-24)** — owner FROZE OQ1–OQ4: signal = **price > 200-day SMA**, **weekly Monday** rebalance, **all in-trend names equal-weight (cash the rest)**, **top-200 liquid** universe. Pre-registration locked; harness build follows. v0.1 was the pre-sign-off draft. |
| Date | 2026-06-24 |
| Strategy | **Trend Following** — the time-series trend complement to cross-sectional momentum; the next Tier-B *investment philosophy* (Strategy Roadmap §3.4). |
| Why it's different | Momentum is **cross-sectional relative strength** (rank names, hold the strongest quintile *all the time*). Trend Following is **time-series absolute trend** (hold a name only while its own price trend is up, else cash) — a different *time-scale, turnover, and market-participation* profile. It naturally de-risks to cash in sustained downtrends, which is exactly where momentum hurts most. |
| Governing | **ADR 0014** (backtests = ground-truth) · the Strategy Roadmap evidence gate · ADR 0019 (Research Engine, read-only). |
| Data | The **survivorship-free SEP store** (`factor_data_full.duckdb`). No new data dependency — reuses the same adjusted-price history and the existing trailing-return primitive. |

---

## 0. Why TREND-001 exists (the business framing)

> Time-series momentum / trend following — that an asset's own recent trend predicts its near-future
> return — is one of the most studied and widely-productized systematic strategies (managed-futures /
> CTA funds run tens of billions on it). For TradingWorkbench it is the natural next philosophy: it
> **reuses price-only infrastructure already built** (trailing returns, the market-regime MA filter),
> it is **trivially explainable** ("ride uptrends, step aside in downtrends"), and it diversifies the
> book on a **different axis** than either Low Volatility (selection) or Sector Rotation (where) — it
> diversifies on *timing / market participation*.

**The momentum relationship (the pair that defines the contrast).** Momentum and Trend Following are
both "winners keep winning," but on orthogonal axes:

> **Cross-sectional Momentum (MOM-001)** asks *"which names are strongest **relative to peers**?"* — it
> is always ~fully invested in the top quintile, even in a bear market (it just owns the
> least-bad names). **Time-series Trend (TREND-001)** asks *"is **this name's own** trend up?"* — and if
> the answer is no for most names, the book sits in cash. The key, pre-registered structural difference
> is **market participation**: trend following's gross exposure *falls* in broad downtrends; momentum's
> does not. That is the source of any diversification / downside value.

**Honest prior (stated up front).** The platform already ships a *market-level* regime filter (SPY vs
its 200-day MA) that moves the momentum book to cash in downtrends — so part of trend following's
downside benefit may **already be captured** at the portfolio level. TREND-001's real question is
therefore sharp: does a **per-name** time-series trend signal add value *beyond* (a) cross-sectional
momentum and (b) the market-level regime filter the platform already has? If it does not, that is a
real, citable rejection (the platform declining a famous strategy on its own honest data). **No
parameter is introduced solely to improve historical performance** (§4).

## 1. Hypothesis (frozen)

Three pre-registered questions (none move after results):

- **H1 (standalone):** a time-series trend book beats an equal-weight benchmark out-of-sample on
  **risk-adjusted** terms — ΔSharpe whose bootstrap 95% CI excludes zero.
- **H2 (diversifier):** corr(trend, cross-sectional momentum) is **materially below 1** (and ideally
  low), AND a momentum + trend blend lifts Sharpe and/or cuts drawdown vs momentum alone — *measured
  against momentum that already carries the market-regime filter* (so we credit only the incremental,
  per-name timing value).
- **H3 (downside / participation) — the trend-specific question:** does the trend book deliver
  materially **shallower drawdowns** than the benchmark and momentum by reducing gross exposure in
  sustained downtrends, and out-perform in the **worst sub-windows** (bear regimes)? This is trend
  following's signature; it feeds the diversifier verdict even if H1 fails.

A negative result on full-cycle data is a **success** (recorded, declined) — the Evidence Engineering moat.

### 1a. Pre-registered behavior expectation (frozen BEFORE results)

| Dimension | Expectation (pre-registered) | Why |
|---|---|---|
| Raw return (CAGR) | **≈ or slightly below** momentum | sitting in cash during whipsaws costs upside |
| Sharpe | **≥ equal-weight benchmark**; vs momentum uncertain | trend's claim is smoother, risk-managed returns |
| Max drawdown | **much shallower** than momentum (−76%) and the benchmark | de-risking to cash in downtrends (H3) |
| Turnover | **higher than momentum in choppy regimes** (whipsaw), lower in trending ones | trend signals flip on regime changes |
| Gross exposure | **falls in bear markets, ~full in bull markets** | the defining participation property |
| Correlation to momentum | **moderate** (both are "winners win"), but < 1 | shared trend DNA, different axis |

If the actuals contradict these (e.g. trend does *not* cut drawdown beyond the existing regime filter),
that is itself an important finding about this universe/period and the platform's existing machinery.

## 2. The signal (FROZEN — OQ1 resolved)

For each rebalance date `as_of`, per name, a binary **in-trend** flag:
- **FROZEN: price vs moving average** — in-trend iff the **last close (strictly before `as_of`) > its
  200-day SMA**. The canonical managed-futures/CTA trend filter and the **per-name generalization of the
  market-regime filter the platform already runs at the portfolio level** — chosen precisely so the
  "does per-name trend beat the regime filter we already have?" comparison (§5.5) is crisp.

Point-in-time, survivorship-free, computed strictly before `as_of` (no look-ahead). The 200-day window
is frozen (the platform's existing regime-filter window) — no sweep (avoids multiple-comparison
fishing); the 252-day return-sign signal and other windows are explicitly **future variants**.

## 3. Construction (frozen, reuses the factor-agnostic backtest)

Long-only, equal-weight the **in-trend** names; the un-invested fraction sits in **cash** (this is the
participation mechanism — distinct from momentum, which is always ~fully invested):
- **`trend_score(store, as_of)`** → score = the in-trend flag (1 / 0), or for ranking, the trailing
  return among in-trend names; the harness holds **all in-trend names equal-weight** (or the top
  quintile of in-trend names — OQ3), with **cash** for the remainder.
- Reuses the same survivorship-free harness as Momentum / Sector / Low-Vol (weekly or monthly rebalance
  — OQ2; equal-weight; turnover cost). Only the **selection + cash rule** changes — a clean A/B.

**Construction roadmap (the version sequence, mirrors LOW-001):**
- **V1 — equal-weight in-trend names, cash otherwise** (THIS plan; clean A/B, comparable to every other book).
- V2 — **inverse-vol sizing** of the in-trend sleeve (the canonical risk-parity trend construction) — only if V1 is promising.
- V3 — **multi-window trend consensus** (e.g. agreement across 3/6/12-month) — the mature CTA form.

> **Stopping rule (frozen).** If V1 shows **no standalone edge (H1 fails) AND no incremental
> diversifier / downside value beyond the existing regime filter (H2 and H3 both fail)** on full-cycle
> survivorship-free data, Trend Following is **archived** as a citable rejection. The inverse-vol /
> multi-window variants would only be pursued if V1 is *promising but construction-limited*. This bounds
> the program.

## 4. Pre-registered evidence gate (frozen BEFORE results)

| Criterion | Bar |
|---|---|
| **Standalone edge (H1)** | bootstrap 95% CI of **ΔSharpe vs equal-weight** excludes 0 (and positive) |
| **Significance** | paired circular-block bootstrap (2000 resamples, **seed 17**) — same method as SEC-001 / LOW-001 |
| **Consistency** | positive ΔSharpe in **≥ ⌈W/2⌉+1** walk-forward windows |
| **Incremental diversification (H2)** | corr(trend, momentum) **< 1** (ideally < 0.7); blend-vs-momentum ΔSharpe CI excludes 0, OR blend cuts maxDD at ≈-equal Sharpe — **with momentum carrying the regime filter** |
| **Downside protection (H3)** | trend maxDD materially shallower than equal-weight **and** momentum; out-performs in the worst sub-windows; gross-exposure demonstrably falls in bear regimes |
| **Cost-robust** | edge survives 5/10/20/50 bps (trend can be turnover-heavy — this matters more here) |
| **Honest defaults** | equal-weight, single frozen trend window, no in-sample tuning |
| **No-overfit clause** | **No parameter is introduced solely to improve historical performance.** The window, rebalance cadence, and cost are inherited conventions or conservative defaults set before results. |

**Verdict (decision tree) — with pre-registered probabilities + learning objective:**

| Outcome | Trigger | Pre-reg. prob. | What we learn (regardless) | Product impact |
|---|---|---|---|---|
| **A — Validated** | H1 clears (standalone risk-adjusted edge) | **15%** | Per-name trend is standalone alpha on full-cycle data | **Standalone trend book** (a managed-futures-style equity sleeve) |
| **B — Diversifier / Defensive** | H1 fails but H2 or H3 clears *beyond the existing regime filter* | **35%** | Trend is an incremental timing/participation overlay, not standalone | **Participation sleeve** in the risk dial |
| **C — Rejected** | H1, H2, H3 all fail, OR the benefit is fully subsumed by the existing market regime filter | **40%** | The platform's portfolio-level regime filter **already captures** the trend benefit — a famous strategy adds nothing here | **Knowledge asset** (a citable "honest no"; validates the existing machinery) |
| **D — Inconclusive** | borderline / wide CI | **10%** | The liquid universe / window is too narrow to answer | **Research archive** → V2 |

Every outcome produces a citable artifact — that is Evidence Engineering. (Note the deliberately higher
**Rejected** prior: this is the first program where the platform's *own existing feature* — the regime
filter — is a strong competing explanation, which makes the honest-no the modal expectation.)

## 5. Method (what the run will produce)

A new `scripts/trend_research.py` (mirrors `low_vol_research.py` / `sector_rotation_research.py`):
1. **Signal correlation** — trend flag/score vs cross-sectional momentum (monthly cross-sections).
2. **Full-window backtest** — trend vs momentum (regime-filtered) vs equal-weight (CAGR/Sharpe/maxDD/Calmar) + **paired Sharpe-difference bootstrap** (H1).
3. **Walk-forward** sub-windows (consistency + the bear-regime read for H3).
4. **Blend test (H2)** — momentum + trend; ΔSharpe + maxDD vs momentum-alone (momentum carrying the regime filter, to isolate *incremental* value).
5. **Participation analysis (H3)** — gross-exposure time series; maxDD vs benchmarks; performance in the worst sub-windows (2000–02, 2008, 2020, 2022); **a direct A/B vs the existing market-regime filter** (does per-name trend beat the portfolio-level filter?).
6. **Cost sweep** 5/10/20/50 bps (turnover-sensitive).
7. **Evidence package** (`script → JSON → Markdown`, seeded/reproducible) + governance verdict → `docs/implementation/evidence/trend_001_trend_following/`.

## 6. Benchmarks

- **Equal-weight universe** (primary — H1).
- **Momentum v1.1 with the market-regime filter** (the production book — H2/H3 incrementality; the key contrast).
- **The market-regime filter alone** (the competing-explanation A/B — the honest-prior control).
- **SPY** best-effort (the P12 §1 data gap still applies).

## 7. Out of scope (V1)

Inverse-vol / risk-parity sizing (→ V2); multi-window consensus (→ V3); short legs / true long-short
managed-futures (the platform is long-only paper); macro / cross-asset trend (equities only here);
live/paper activation (gated on a non-rejected verdict + governance + its own account).

## 8. Commercial value

- **Explainability:** *"ride uptrends, step aside in downtrends"* — instantly understandable.
- **Marketability:** managed-futures / CTA is a recognized institutional category; high pedigree.
- **Fit:** slots into the risk-dial story as a **participation sleeve** — complementary to Low Vol (selection) and Sector (where).

### 8a. Trend Following ≠ the existing regime filter (the distinction that must survive review)
The platform already moves the *whole book* to cash when **SPY** is below its 200-day MA. Trend
Following applies the trend test **per name** and sizes participation continuously. H2/H3 are
specifically designed to measure whether the **per-name** signal adds value *beyond* the **market-level**
filter already shipped — if it does not, that is the (likely) honest rejection, and it validates the
existing machinery rather than embarrassing it.

## 9. Research risk register

| Risk | Mitigation |
|---|---|
| Benefit already captured by the market regime filter | the explicit A/B vs the regime filter (§5.5); H2/H3 measured against regime-filtered momentum |
| Whipsaw / turnover destroys the edge net of cost | the 5–50 bps cost sweep is a first-class gate criterion, not an afterthought |
| Look-ahead in the trend flag | strictly-before-`as_of` computation, reused PIT primitives, seeded bootstrap |
| Mostly-cash book looks like "no strategy" | the participation analysis (§5.5) reframes low exposure as the *mechanism*, with the bear-window read |
| Single-window cherry-pick | one frozen window (OQ1); alternatives are pre-declared future variants |

## 10. Production path & research cost

**Lifecycle:** `Hypothesis → Research → Evidence → Governance → Candidate → Paper → Production → Continuous Evidence`.
TREND-001 enters at *Hypothesis* (this plan); on a non-rejected verdict it proceeds through the same
lifecycle SEC-001 and LOW-001 are now in (templated, owner-gated activation).

**Research cost (logged for research-ROI):**

| Resource | Estimate |
|---|---|
| Developer time | ~1 session (plan ✅ + harness ~1–2h + run + evidence package) |
| CPU hours | ~0.2–0.4h (one full 2000–2026 pass + bootstrap; ~LOW-001 class) |
| Dataset | **none new** — the survivorship-free SEP store already in place |
| Complexity | **low** — score = a thin wrapper over trailing return / SMA |
| Reuse % | **~90%** — harness, bootstrap, walk-forward, report scaffold inherited |

### 10a. Research calibration metrics (pre-registered)

| Metric | Pre-registered value | Reasoning |
|---|---|---|
| **Research Confidence** | **Low–Medium** | Strong literature, BUT a strong competing explanation (the existing regime filter) and a long-only equity adaptation of a strategy that classically uses shorts + futures. Lower than LOW-001. |
| **Research Complexity** | **Low** | Thin wrapper over trailing-return / SMA primitives; harness fully inherited. |
| **Research Duration** | **Planned 2026-06-24 → Started _(stamp on build)_ → Completed _(stamp in evidence package)_** | The lifecycle clock for research-ROI. |

Feeds the cross-program **Research Calibration Index** (Confidence → Prediction → Outcome).

## 11. Open questions for the owner (FREEZE before building the harness)

✅ **RESOLVED (owner, 2026-06-24) — pre-registration LOCKED:**

- **OQ1 — Signal:** ✅ **price > 200-day SMA** (per-name generalization of the existing market-regime filter).
- **OQ2 — Rebalance cadence:** ✅ **weekly Monday** (comparable to every other book).
- **OQ3 — Selection within in-trend:** ✅ **hold all in-trend names equal-weight, cash the rest** (purest participation test).
- **OQ4 — Universe:** ✅ **top-200 liquid headline** (broader reserved for V2).

Plan is **FROZEN.** Next: build `scripts/trend_research.py` + tests, run it on 2000–2026, ship the
evidence package + verdict — then (only if non-rejected) a promotion PR mirroring SEC-001 / LOW-001.
