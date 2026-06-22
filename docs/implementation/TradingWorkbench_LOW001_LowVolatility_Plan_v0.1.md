# Trading Workbench — Low Volatility: Research Plan & Pre-Registration (v0.1)

> ## Research Program `LOW-001`
> | | |
> |---|---|
> | **Strategy family** | Low Volatility |
> | **Investment philosophy** | Defensive / risk-based (the low-volatility anomaly) |
> | **Research goal** | Does a low-volatility book add value to the **platform** — as standalone risk-adjusted alpha (H1), a diversifier of momentum (H2), or a downside-protection sleeve (H3)? |
> | **Status** | **APPROVED (owner, 2026-06-21, 9.7/10) — frozen, ready to build.** Q1–Q3 confirmed (LOW-001 rename · top-200 first · realized vol). v0.2 folds the owner's suggestions. |
> | **Owner** | Jay |
> | **ADR** | TBD (assign on a VALIDATED verdict) |
> | **Program #** | the platform's **5th** research program — `MOM-001` 🟢 · `RNG-001` 🔴 · `MF-001` 🟡 · `SEC-001` 🟡 (Diversifier, construction archived) · **`LOW-001` 🔵 Research** · `TREND-001` planned |
>
> ⚠ **ID note:** the shipped catalog (`app/research/programs.py`) currently labels this `LV-001`. This plan uses **`LOW-001`** to match the owner's roadmap wording; on approval I'll align the catalog (rename `LV-001 → LOW-001`) so the platform IP is consistent. Confirm the preferred label.

| Field | Value |
|---|---|
| Document | **Low Volatility research program** — plan + **pre-registered** acceptance criteria. |
| Version | **v0.3 (2026-06-22)** — second owner review folded (`Docs/review/comments.md`, 9.7→9.9): three **research-calibration metrics** (§10a) — **Research Confidence** (expected, with reason), **Research Complexity** (Low/Med/High), and **Research Duration** (Planned → Started → Completed) — so the platform can later compare *expected vs observed* about its own research process. **v0.2 (2026-06-21)** folded the first review (9.7/10): the **Momentum relationship** (strength vs stability / offensive vs defensive, §0); an explicit **Low-Vol vs Vol-Target** distinction (§8a); a pre-registered **expected-behavior table** (§1a); the **expected-outcome probabilities** + **learning objective** per outcome (§4); a fuller **research-cost** breakdown (§10); and the standardized **research-phase terminology** (§10). v0.1 was the pre-review draft. |
| Date | 2026-06-21 |
| Strategy | **Low Volatility** — hold the lowest-realized-volatility names; the next Tier-B *investment philosophy* (Strategy Roadmap; owner 12-month roadmap item after SEC-001). |
| Why it's different | Momentum is **offensive** (relative strength, trend); low-vol is **defensive** (own the calmer stocks). A genuinely different philosophy — and the one most likely to be *negatively* correlated with momentum, which is exactly what a diversifier needs. |
| Governing | **ADR 0014** (backtests = ground-truth) · the Strategy Roadmap evidence gate · ADR 0019 (Research Engine, read-only). |
| Data | The **survivorship-free SEP store** (`factor_data_full.duckdb`). No new data dependency — reuses the same price history and the existing trailing-vol primitive (`backtest._trailing_vol`). |

---

## 0. Why LOW-001 exists (the business framing, not the technical one)

> The low-volatility anomaly — that low-risk stocks have historically delivered *higher risk-adjusted*
> returns than high-risk stocks — is one of the most durable, widely-productized factors in the industry
> (min-vol ETFs like USMV and SPLV manage tens of billions). For TradingWorkbench it is the natural next
> philosophy: it **reuses the volatility infrastructure already built** (trailing-vol, vol-targeting,
> inverse-vol weighting), it is **trivially explainable** ("own the calmer stocks"), and it is the
> philosophy **most likely to diversify momentum** because it is defensive by construction.

**The momentum relationship (the pair that defines the product).** Momentum and Low Volatility are the
platform's offensive/defensive pair:

> **Momentum** answers *"where is strength?"* — it buys what is already winning (relative strength,
> trend). **Low Volatility** answers *"where is stability?"* — it buys what is calm (low realized risk).
> Together they are the **offensive** and **defensive** halves of an equity portfolio. That is precisely
> why low-vol is the strongest diversifier candidate: it is built to behave *unlike* momentum, especially
> in the drawdowns where momentum hurts most.

**Honest prior (this is a re-test, and we say so up front).** The P10 factor study (PR #142) already
found low-volatility **negative** on the **top-200 liquid mega-cap universe over 2016–2026** — but that
window is a single momentum-favoring regime with almost no bear market, and mega-caps are the *worst*
universe for the low-vol anomaly (it lives in the broader market). **LOW-001 is the proper test:** the
full **survivorship-free 2000–2026 history**, which includes the dot-com unwind, 2008, the 2020 COVID
crash, and 2022 — the regimes where low-vol is supposed to earn its keep. If it fails *there*, that is a
real, citable rejection; if it succeeds, it is a genuinely diversifying defensive book. **No parameter is
introduced solely to improve historical performance** (§4).

## 1. Hypothesis (frozen)

Three pre-registered questions (none move after results):

- **H1 (standalone):** a low-vol book beats an equal-weight benchmark out-of-sample on **risk-adjusted**
  terms — ΔSharpe whose bootstrap 95% CI excludes zero. *(Low-vol's pitch is Sharpe, not raw return.)*
- **H2 (diversifier):** corr(low-vol, single-name momentum) is low or **negative** (defensive vs
  offensive); and a momentum+low-vol blend lifts Sharpe and/or cuts drawdown.
- **H3 (downside protection) — the low-vol-specific question:** does the low-vol book deliver materially
  **shallower drawdowns** than the benchmark and momentum, and outperform in the **worst sub-windows**
  (bear regimes)? This is low-vol's signature; it feeds the diversifier verdict even if H1 fails.

A negative result on full-cycle data is a **success** (recorded, declined) — the Evidence Engineering moat.

### 1a. Pre-registered behavior expectation (frozen BEFORE results — owner suggestion)

Stating what we *expect* before running is a calibration discipline: after the run we compare prediction
vs actual. Based on the low-vol literature and the offensive/defensive logic above:

| Dimension | Expectation (pre-registered) | Why |
|---|---|---|
| Raw return (CAGR) | **slightly lower** than momentum | defensive names give up some upside |
| Sharpe | **higher** than the equal-weight benchmark | the anomaly's whole claim is *risk-adjusted* |
| Max drawdown | **much lower** than momentum (−76%) and the benchmark | the signature low-vol property (H3) |
| Turnover | **lower** than momentum | volatility ranks are more stable than price-trend ranks |
| Correlation to momentum | **negative to low** (< 0.3) | offensive vs defensive (H2) |

If the actuals contradict these (e.g. low-vol does *not* cut drawdown), that is itself an important
finding about this universe/period.

## 2. The signal (frozen definition)

For each rebalance date `as_of`:
1. **Realized volatility** = the **trailing 252-trading-day standard deviation of daily returns**, per
   name, computed strictly before `as_of` (no look-ahead — reuses `backtest._trailing_vol`'s discipline).
2. **Low-vol score** = **−volatility** (lowest realized vol → highest score), over the liquid universe.
   Point-in-time, survivorship-free.

**Frozen, single definition — no sweep.** Total realized volatility, 252-day, ranked ascending. Low-beta
(BAB) and shorter/longer vol windows are explicitly **future variants**, not pre-registered here (avoids
multiple-comparison fishing). 252 days mirrors the platform's 12-month convention.

## 3. Construction (frozen, reuses the factor-agnostic backtest)

Maps cleanly onto `run_momentum_backtest(score_fn=...)` — the identical clean A/B used for SEC-001 and
multi-factor:
- **`low_vol_score(store, as_of)`** → each ticker scored by −(trailing 252-day realized vol); the harness
  holds the **top-quintile = the lowest-vol names**, equal-weight.
- Same harness as Momentum / Sector / multi-factor: weekly rebalance, top-quintile, equal-weight,
  survivorship-free, turnover cost. Only the **score** changes — clean A/B.

**Pre-registered parameters (frozen):** signal **252-day realized vol** · **top-quintile (20%)** lowest-vol ·
equal-weight · weekly rebalance · turnover cost **10 bps** · universe **top-200 liquid** (headline) ·
window **2000–2026** · paired circular-block bootstrap (2000 resamples, **seed 17**).

**Construction roadmap (the version sequence, mirrors SEC-001):**
- **V1 — equal-weight low-vol quintile** (THIS plan; clean A/B, comparable to every other book).
- V2 — **broader universe** (the low-vol anomaly lives outside mega-caps) — only if V1 is promising-but-thin.
- V3 — **inverse-vol weighting within the quintile** (the canonical min-vol construction) — the mature form.

> **Stopping rule (frozen).** If V1 shows **no standalone edge (H1 fails) AND no defensive/diversifier
> value (H2 and H3 both fail)** on full-cycle survivorship-free data, Low Volatility is **archived** as a
> citable rejection — the broader-universe / min-vol-weighting variants would only be pursued if V1 is
> *promising but universe-limited* (H3 defensive value present but H1 thin). This bounds the program and
> prevents an open-ended search.

## 4. Pre-registered evidence gate (frozen BEFORE results)

| Criterion | Bar |
|---|---|
| **Standalone edge (H1)** | bootstrap 95% CI of **ΔSharpe vs equal-weight** excludes 0 (and positive) |
| **Significance** | paired circular-block bootstrap (2000 resamples, seed 17) — same method as SEC-001 / P14 |
| **Consistency** | positive ΔSharpe in **≥ ⌈W/2⌉+1** walk-forward windows |
| **Diversification (H2)** | corr(low-vol, momentum) **< 0.5** (expected negative); blend ΔSharpe vs momentum-alone CI excludes 0, OR blend cuts maxDD at ≈-equal Sharpe |
| **Downside protection (H3)** | low-vol maxDD materially shallower than equal-weight **and** momentum; out-performs in the worst sub-windows |
| **Cost-robust** | edge survives 5/10/20/50 bps |
| **Honest defaults** | equal-weight, single frozen vol window, no in-sample tuning |
| **No-overfit clause (patent language)** | **No parameter is introduced solely to improve historical performance.** The vol window (252d), quintile, weighting, and cost are inherited conventions or conservative defaults set before results. |

**Verdict (decision tree) — with pre-registered probabilities + learning objective:**

The **probabilities** are a forecast, recorded *before* results so we can compare prediction vs actual
(research calibration — owner suggestion A); they are guesses, and being "wrong" is the point. The
**learning objective** states what we learn *regardless of outcome* (owner suggestion C) — because
Evidence Engineering is learning, not just deployment.

| Outcome | Trigger | Pre-reg. prob. | What we learn (regardless) | Product impact |
|---|---|---|---|---|
| **A — Validated** | H1 clears (standalone risk-adjusted edge) | **15%** | Low-vol is a standalone defensive alpha on full-cycle data | **Standalone defensive strategy** (min-vol book / new Risk-Profile flavor) |
| **B — Diversifier / Defensive** | H1 fails but H2 or H3 clears | **50%** | Low-vol is an *overlay/diversifier*, not standalone — the defensive complement to momentum | **Portfolio overlay** (a defensive sleeve in the risk dial) |
| **C — Rejected** | H1, H2, H3 all fail/negative | **25%** | The #142 negative **generalizes** to full breadth/cycle — low-vol genuinely doesn't pay here | **Knowledge asset** (a citable "honest no" at full breadth) |
| **D — Inconclusive** | borderline / wide CI | **10%** | The liquid universe is too narrow to answer — the anomaly needs broader breadth (→ V2) | **Research archive** → broader-universe V2 |

Every outcome produces a citable artifact — that is Evidence Engineering. (The evidence package records
the *actual* outcome next to this forecast.)

## 5. Method (what the run will produce)

A new `scripts/low_vol_research.py` (mirrors `sector_rotation_research.py`):
1. **Factor-correlation** — low-vol score vs single-name momentum (monthly cross-sections; expect negative).
2. **Full-window backtest** — low-vol vs momentum vs equal-weight (CAGR/Sharpe/maxDD/Calmar) + **paired Sharpe-difference bootstrap** (H1).
3. **Walk-forward** sub-windows (consistency + the bear-regime read for H3).
4. **Blend test (H2)** — momentum + low-vol; ΔSharpe + maxDD vs momentum-alone.
5. **Downside analysis (H3)** — maxDD vs benchmarks; performance in the worst sub-windows (2000–02, 2008, 2020, 2022).
6. **Cost sweep** 5/10/20/50 bps.
7. **Evidence package** (`script → JSON → Markdown`, seeded/reproducible) + governance verdict → `docs/implementation/evidence/low_001_low_volatility/`.

## 6. Benchmarks

- **Equal-weight universe** (primary — H1).
- **Momentum v1.1** (the production book — H2/H3 complementarity; the defensive-vs-offensive contrast).
- **SPY** best-effort (the P12 §1 data gap still applies).

## 7. Out of scope (V1)

Low-beta / BAB construction (→ future variant); inverse-vol / min-variance optimization within the quintile (→ V3); broader/small-cap universe (→ V2); macro/regime-conditioned vol targeting; live/paper activation (gated on VALIDATED + governance + its own account, P5 §7).

## 8. Commercial value (Suggestion-aligned)

- **Explainability:** *"own the calmer stocks"* — instantly understandable.
- **Marketability:** min-vol is a multi-tens-of-billions ETF category (USMV, SPLV); high recognition.
- **Fit:** slots into the risk-dial story as a **defensive sleeve** — the natural complement to the offensive momentum book.

### 8a. Low Volatility ≠ Volatility Targeting (a distinction customers will confuse — owner suggestion)

The platform already ships a **volatility-target overlay** (the Risk Profiles' "risk dial"). Low Volatility
is a *different mechanism* and must be described as such:

| | Volatility Targeting (shipped, v1.1) | **Low Volatility (LOW-001)** |
|---|---|---|
| What it changes | **Position sizing** — scales gross exposure up/down to hit a vol target | **Stock selection** — picks *which names* to hold |
| Holdings | the **same** momentum names | a **different** portfolio (the calmest names) |
| Mechanism | a risk **overlay** on an existing book | a standalone **factor** / book |
| Question it answers | "how much should we hold?" | "what should we hold?" |

They are complementary, not redundant: one could run a low-vol *selection* and *also* vol-target its
exposure. H2/H3 measure the value of the **selection** distinct from the **scaling** v1.1 already does.

## 9. Research risk register

| Risk | Mitigation |
|---|---|
| Confirms the #142 negative (no edge on liquid universe) | the full-cycle window + the H3 downside read + the broader-universe V2 path |
| Low-vol ≈ a bond/rate proxy (regime-dependent) | walk-forward sub-windows across rate regimes |
| Overlaps the existing vol-target overlay | H2/H3 measure *selection* value distinct from the *scaling* overlay already in v1.1 |
| Mega-cap universe handicaps the anomaly | stated up front; broader-universe V2 is the pre-registered next step if V1 is thin |
| Crowding / valuation of low-vol | a citable caveat in the evidence package (not a backtest artifact) |

## 10. Production path & research cost

**Lifecycle (the standardized Evidence Engineering phase terminology — owner suggestion, matches the
whitepaper + patent):**

`Hypothesis → Research → Evidence → Governance → Candidate → Paper → Production → Continuous Evidence`

LOW-001 enters at *Hypothesis* (this plan) and, on a VALIDATED verdict, proceeds through the same
lifecycle the momentum Risk Profiles are in now.

**Research cost (logged for research-ROI tracking across programs — owner suggestion B):**

| Resource | Estimate |
|---|---|
| Developer time | ~1 session (plan ✅ + harness ~1–2h + run + evidence package) |
| CPU hours | ~0.2–0.4h (one full 2000–2026 backtest pass + bootstrap; ~SEC-001 V2 class) |
| Storage | negligible (one JSON + MD evidence package; reuses the existing store) |
| Dataset | **none new** — the survivorship-free SEP store already in place |
| Complexity | **low** — score = a thin wrapper over the existing `_trailing_vol` primitive |
| Reuse % | **~90%** — harness, bootstrap, walk-forward, report scaffold all inherited from SEC-001 |

The high reuse % is the point: LOW-001 is the cheapest Tier-B philosophy to charter, which is exactly why
it's next — and a data point that motivates the **Factor Lab** generalization (where the next program is
*configuration*, not a new script).

### 10a. Research calibration metrics (pre-registered — owner Round-2 suggestions A/B/C)

These describe **the research effort itself**, not the strategy. Recorded *before* results so the platform
can later compare *expected vs observed* — Evidence Engineering evaluating its own process, not just the
books it produces. (The evidence package stamps the observed values next to these forecasts.)

| Metric | Pre-registered value | Reasoning |
|---|---|---|
| **Research Confidence** | **Medium** | Strong, well-documented academic literature (the low-vol anomaly is one of the most durable factors), but a *prior mixed result* (the #142 negative on the narrow universe) and a broader, regime-spanning history that has not yet been tested here. Not Low (the literature is real), not High (we have a contradicting prior to overturn). |
| **Research Complexity** | **Low** | The score is a thin wrapper over the existing `_trailing_vol` primitive; the harness, bootstrap, walk-forward, and report scaffold are all inherited (~90% reuse). No new data dependency. |
| **Research Duration** | **Planned 2026-06-21 → Started _(stamp on build)_ → Completed _(stamp in evidence package)_** | The lifecycle clock for research-ROI / enterprise reporting. Planned-vs-Completed elapsed time is the metric customers will eventually compare against Research Value. |

Later, **Research Value / Research Cost → Research ROI**, and **expected Confidence vs observed outcome →
research calibration**, both roll up from these fields across the registry.

## 11. Resolved decisions (owner, 2026-06-21)

- **Q1 — ID:** ✅ **`LOW-001`** — rename the catalog's `LV-001 → LOW-001` (done on build).
- **Q2 — universe:** ✅ **top-200 liquid headline** (comparable to every other book); broader universe reserved for **V2** only if V1 is promising-but-thin.
- **Q3 — signal:** ✅ **total realized volatility (252d)**, single frozen signal; low-beta (BAB) a future variant.

Plan is **frozen**. Next: rename `LV-001 → LOW-001` in the catalog, build `scripts/low_vol_research.py` + tests, run it, ship the evidence package.
