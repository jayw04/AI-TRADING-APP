# Trading Workbench — Sector Rotation: Research Plan & Pre-Registration (v0.2)

> ## Research Program `SEC-001`
> | | |
> |---|---|
> | **Strategy family** | Sector Rotation |
> | **Investment philosophy** | Relative Strength |
> | **Research goal** | Standalone Alpha (H1) + Diversification (H2) — *does it add value to the **platform**?* |
> | **Status** | **APPROVED — ready to implement** |
> | **Owner** | Jay |
> | **ADR** | TBD (assign on a VALIDATED verdict) |
> | **Program #** | the platform's **4th** research program — after `MOM-001` Momentum 🟢 Approved · `RNG-001` Range 🔴 Rejected · `MF-001` Multi-Factor 🟡 Inconclusive · **`SEC-001` Sector Rotation 🔵 Research** |
>
> _Convention (owner Suggestion 9): every strategy doc begins with this block. Permanent IDs
> (MOM/RNG/MF/SEC/LV/TF/QUALITY-NNN) are platform IP — citable in the whitepaper, patent, and customer
> docs; they feed the future "research dashboard" (Suggestion 10)._

| Field | Value |
|---|---|
| Document | **Sector Rotation research program** — plan + **pre-registered** acceptance criteria. |
| Version | **v0.2 (2026-06-21)** — owner review folded (`Docs/review/comments.md`, 9.6/10 + 10 suggestions): Research Program ID; commercial-value criteria; research-risk table; expanded H2 (corr/return/drawdown); expected outcomes A–D; production path; future-variant family; V1→V2→V3 construction roadmap; the platform-value reframe. Open questions O1–O3 resolved. |
| Date | 2026-06-21 |
| Status | **APPROVED (owner, 2026-06-21) — ready to build.** The plan is frozen; next is `scripts/sector_rotation_research.py` + the run. |
| Strategy | **Sector Rotation** — a sector-level relative-strength / momentum signal; the next Tier-B *investment philosophy* (Strategy Roadmap §3.2). |
| Why it's different | Momentum chooses **WHAT** (which stocks); sector rotation chooses **WHERE** (which sectors). A genuinely different philosophy, not another momentum variant — broadens the platform beyond single-name stock selection. |
| Governing | **ADR 0014** (backtests = ground-truth) · the Strategy Roadmap evidence gate · ADR 0019 (Research Engine, read-only). |
| Data | The **survivorship-free SEP store** (`factor_data_full.duckdb`, 1997–2026) + the **Sharadar `tickers.sector` classification already in the store** (21,719 names, 11 sectors). No new data dependency. |

---

## 1. Hypothesis (frozen)

> **The research question (owner reframe): does Sector Rotation *add value to the TradingWorkbench
> platform*?** — not merely "does it work." The platform is the product; a strategy adds value as a
> standalone offering, a diversifier, OR a clean rejected/inconclusive evidence artifact.

Operationalized as two pre-registered questions (neither moved after seeing results):
- **H1 (standalone):** sector rotation beats an equal-weight benchmark out-of-sample (Sharpe edge whose
  bootstrap CI excludes zero).
- **H2 (diversifier) — three dimensions, don't let Sharpe dominate (Suggestion 3):** sector rotation
  adds value to momentum if **any** of: (a) **correlation** with single-name momentum is low (<0.5);
  (b) a momentum+sector blend raises **return/Sharpe**; (c) the blend **lowers max drawdown** at
  ≈-equal Sharpe. A diversifier that cuts drawdown at flat Sharpe is still valuable.

A **negative** result is a success (recorded, declined) — the Evidence Engineering moat.

## 2. The signal (frozen definition)

For each weekly rebalance date `as_of`:
1. **Sector momentum** = for each of the 11 Sharadar sectors, the **equal-weight average of its
   constituent stocks' 12-1 momentum** (the production lookback: 12-month return skipping the last
   month), over the liquid universe at `as_of`. Point-in-time and survivorship-free (uses
   `universe_asof` + `tickers.sector` + SEP).
2. **Rank sectors** by sector momentum (highest = strongest).

## 3. Construction (frozen, reuses the factor-agnostic backtest)

The platform's `run_momentum_backtest(score_fn=...)` already holds the top-quantile of a per-ticker
score. Sector rotation maps cleanly:

- **`sector_momentum_score(store, as_of)`** → each ticker is scored by **its sector's momentum rank**
  (every stock in the strongest sector gets the top score). The backtest then holds the **top-quantile
  tickers = an equal-weight basket of the strongest sectors' stocks** — i.e. *rotate into the strong
  sectors, hold their names equally*.
- Same harness as Momentum/multi-factor: weekly rebalance, top-quintile, equal-weight, survivorship-free,
  turnover cost. Only the **score** changes (sector momentum vs single-name momentum) — clean A/B.

**Pre-registered parameters (frozen):** lookback **12-1** · **top-quintile (20%)** sectors' stocks ·
equal-weight · weekly rebalance · turnover cost **10 bps** · universe **top-200 liquid** (headline) +
a survivorship-free-breadth appendix · window **1998–2026**.

**Construction roadmap (O1 resolved — owner Suggestion 7, a natural version sequence):**
- **V1 — top-quintile of strong-sectors' stocks** (THIS run; reuses the harness exactly, clean A/B).
- **V2 — pure sector baskets** (hold the top-K sectors equal-weight; a small new basket-backtest) — if V1 is promising.
- **V3 — dynamic sector weighting** (overweight by signal strength / risk-parity) — the mature form.

Each version is its own pre-registered run; this document covers **V1**.

## 4. Pre-registered evidence gate (frozen BEFORE results)

| Criterion | Bar |
|---|---|
| **Standalone edge (H1)** | bootstrap 95% CI of **ΔSharpe vs equal-weight** excludes 0 (and positive) |
| **Significance** | paired circular-block bootstrap (2000 resamples, seed 17) — same method as the P14 multi-factor re-test |
| **Consistency** | positive ΔSharpe in **≥ ⌈(W/2)⌉+1** walk-forward windows (not one lucky regime) |
| **Diversification (H2)** | corr(sector-rotation, single-name-momentum) **< 0.5**; and momentum+sector blend ΔSharpe vs momentum-alone CI excludes 0 |
| **Cost-robust** | edge survives 5/10/20/50 bps turnover cost |
| **Honest defaults** | equal-weight, no in-sample tuning, no factor-timing |

**Verdict:** **VALIDATED** (→ governance → paper as Strategy #2 candidate) only if H1 *or* H2 clears its
bar decisively; **REJECTED** if both CIs span zero; **INCONCLUSIVE** if borderline (wide CI) — recorded
honestly either way.

## 5. Method (what the run will produce)

Mirrors the P14 multi-factor re-test (`scripts/multifactor_retest.py`) — a new
`scripts/sector_rotation_research.py`:
1. **Factor-correlation** — sector-rotation score vs single-name momentum (monthly cross-sections).
2. **Full-window backtest** — sector rotation vs momentum vs equal-weight (CAGR/Sharpe/maxDD/Calmar) +
   **paired Sharpe-difference bootstrap** (the decisive H1 test).
3. **Walk-forward** sub-windows (consistency).
4. **Blend test (H2)** — momentum + sector composite via the composite engine; ΔSharpe vs momentum-alone.
5. **Cost sweep** 5/10/20/50 bps.
6. **Evidence package** (`script → JSON → Markdown`, seeded/reproducible) + governance verdict.

## 6. Benchmarks

- **Equal-weight universe** (primary — H1).
- **Momentum v1.1** (the production book — H2 complementarity).
- **SPY** best-effort (the data gap noted in P12 §1 still applies).

## 7. Resolved decisions (owner, 2026-06-21)

- **O1 — construction:** ✅ **V1 = top-quintile of strong-sectors' stocks** (reuses the harness); V2
  pure baskets + V3 dynamic weighting are the version roadmap (§3).
- **O2 — horizon:** ✅ **12-1, frozen — do NOT optimize** ("consistency is worth more than another
  0.02 Sharpe"). Pre-register one horizon; no sweep.
- **O3 — universe:** ✅ **top-200 liquid** headline + the survivorship-free-breadth appendix.

## 8. Out of scope (v1) + the rotation family (Suggestion 6)

Out of scope for V1: risk-parity/vol-weighted sizing (→ V3), macro/regime-conditioned rotation (a
larger hypothesis), live/paper activation (gated on VALIDATED + governance + its own account, P5 §7).

**But the philosophy generalizes into a whole research family** — one strategy becomes many:
**Sector Rotation (`SEC-001`) → ETF Rotation → Industry Rotation → Country Rotation → Theme Rotation.**
Each is a future `SEC-00N`/own-ID research program reusing this exact harness with a different
grouping key.

## 9. Why this is the right next strategy

Per the owner's review: build **diverse philosophies**, and Sector Rotation is the favorite —
institutions use it, customers grasp it instantly, and it's genuinely orthogonal to single-name
momentum. Whatever the verdict, it strengthens the platform story: *the platform can discover, validate,
**reject**, and operate diverse strategy classes under one governance framework.*

## 10. Expected outcomes (decision tree — Suggestion 4)

| Outcome | Trigger | Action |
|---|---|---|
| **A — Validated** | H1 clears (standalone edge, CI excludes 0) | → governance → **Paper Strategy #2 candidate** (own account) |
| **B — Diversifier** | H1 fails but H2 clears (low corr / blend lifts return or cuts drawdown) | → **blend candidate** (momentum + sector overlay), evidence-gated |
| **C — Rejected** | both H1 and H2 span zero | → **evidence package → knowledge base** (a clean "honest no", like Range Trader) |
| **D — Inconclusive** | borderline / wide CI | → **research debt → future ADR** (revisit with more data / V2) |

Every outcome produces a citable artifact — that is Evidence Engineering.

## 11. Commercial-value criteria (Suggestion 1 — highest priority)

Alpha ≠ product. Beyond "is there an edge," measure **is it commercially useful?**

- **Explainability:** can a customer understand it in one sentence? (Sector Rotation: *"hold the
  strongest sectors" — yes, trivially.* A great Sharpe that's impossible to explain is a poor product.)
- **Marketability:** institutions already use sector rotation → high recognition.
- **Fit:** does it slot into the three-profile / risk-dial product story?

Scientific success → commercial success → product success are **distinct gates**; record all three.

## 12. Research risk register (Suggestion 2)

| Risk | Mitigation |
|---|---|
| Too correlated with Momentum | the H2 blend + correlation analysis |
| Weak standalone alpha | the H2 diversifier gate (value even if H1 fails) |
| High turnover | the 5/10/20/50 bps cost sweep |
| Sector concentration | a sector-concentration line in the evidence report |
| Regime dependency | the walk-forward sub-windows |

## 13. Production path (Suggestion 5)

`Research → Evidence → Governance → Paper Account → 90-day Evidence → Production Candidate` — the same
lifecycle the momentum Risk Profiles are in now. Connects this research to the product roadmap.

## 14. Research cost (Suggestion 8 — for future research-ROI tracking)

Estimated: **~2 sessions** — backtest harness ~1 hour · the research run + analysis ~1 day · the
evidence package/report ~1 day. (Logged so research ROI can be compared across programs over time.)
