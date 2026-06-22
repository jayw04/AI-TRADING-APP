# Trading Workbench — Sector Rotation V2 (Pure Sector Baskets): Research Plan & Pre-Registration (v0.2)

> ## Research Program `SEC-001` — **V2**
> | | |
> |---|---|
> | **Strategy family** | Sector Rotation |
> | **Investment philosophy** | Relative Strength (sector-level) |
> | **Research goal** | Does **pure sector-basket construction** turn the V1 **diversifier** into a **standalone edge** (H1), while preserving the diversification (H2)? |
> | **Status** | **APPROVED (owner, 2026-06-21) — frozen, ready to build.** v0.2 folds the owner's 4 suggestions; Q1–Q3 resolved to the recommended values (K=3 · H3 read-only · all-sector-baskets primary). |
> | **Owner** | Jay |
> | **Predecessor** | `SEC-001` **V1** — verdict **B (Diversifier)** (2000–2026, n=200): Sharpe 0.51 / CAGR +10.36% / maxDD −64.8%, but H1 standalone ΔSharpe **+0.16, CI [−0.03, 0.366]** just spanned zero. Evidence: `docs/implementation/evidence/sec_001_sector_rotation/`. |
> | **ADR** | TBD (assign on a VALIDATED verdict) |
> | **Program #** | `MOM-001` Momentum 🟢 · `RNG-001` Range 🔴 · `MF-001` Multi-Factor 🟡 · **`SEC-001` Sector Rotation 🟡 (V1 = B; this is V2)** |

| Field | Value |
|---|---|
| Document | **Sector Rotation V2** — plan + **pre-registered** acceptance criteria. The §3 V1→V2→V3 roadmap, now at V2. |
| Version | **v0.3 (2026-06-22)** — second owner-review pass folded (`Docs/review/comments.md`, 9.8/10): added the structured **research-cost table** (§10, suggestion B). ⚠ The other two Round-1 suggestions — **pre-registered outcome probabilities** (A) and **learning-objective-per-outcome** (C) — are **deliberately not back-filled**: SEC-001 V2 has since *run* (verdict **B confirmed**, construction archived per the stopping rule), and inventing a "forecast" after the results are known would be a false pre-registration that undermines the Evidence Engineering moat. They live as a forward template in LOW-001 §4 / §10a instead. **v0.2 (2026-06-21)** folded the first review: **§0 Why V2 exists** (S1), a **stopping rule** (S2), the **commercial-value × outcome table** (S3), and the **patent-language no-overfit clause** (S4). Q1–Q3 resolved to recommendations. v0.1 was the pre-review draft. |
| Date | 2026-06-21 |
| Strategy | **Pure sector baskets** — hold the top-K strongest sectors as **diversified, sector-neutral equal-weight baskets** (not the top-quintile *stocks* of strong sectors, as V1 did). |
| Why V2 now | V1's H1 CI **[−0.03, 0.366]** missed zero by a hair. The V2 thesis: V1 mixed the sector signal with **single-stock selection noise** (top-quintile of strong sectors = concentrated, idiosyncratic). Diversifying *within* each sector should shrink return variance → **tighten the Sharpe CI** → potentially turn B (diversifier) into A (standalone edge). That is a falsifiable, pre-registered hypothesis, not a fishing expedition. |
| Governing | **ADR 0014** (backtests = ground-truth) · the Strategy Roadmap evidence gate · ADR 0019 (Research Engine, read-only). |
| Data | The **survivorship-free SEP store** (`factor_data_full.duckdb`) + the **Sharadar `tickers.sector` classification already in the store** (11 sectors). **No new data dependency** — identical inputs to V1, so V1↔V2 is a clean A/B. |

---

## 0. Why V2 exists (the business framing, not the technical one)

> Sector Rotation V1 demonstrated that the investment **philosophy** has diversification value but fell
> slightly short of standalone statistical significance. **V2 is not an optimization exercise; it is an
> attempt to isolate whether portfolio _construction_, rather than the underlying sector _signal_,
> limited V1's standalone performance.**

This distinction is the whole point. If V2 (which changes *only* construction) clears the standalone
bar that V1 missed, we will have learned something real and reusable: that diversified basket
construction — not signal-mining — was the binding constraint. If it does not, we will have bounded the
sector-rotation philosophy honestly and can stop refining it (see the **stopping rule**, §3). Either way
the result is a citable evidence artifact, not a tuned backtest. **No parameter in this plan is
introduced solely to improve historical performance** (§4).

## 1. Hypothesis (frozen)

The platform question is unchanged: **does Sector Rotation add value to the platform?** V2 sharpens *how* we ask it, because V1 already answered "yes, as a diversifier." V2 asks whether a cleaner construction makes it a **standalone** offering.

Three pre-registered questions (none will move after seeing results):

- **H1 (standalone):** pure sector baskets beat an equal-weight benchmark out-of-sample — ΔSharpe whose bootstrap 95% CI **excludes zero**. *(The headline question: does H1 clear where V1's missed?)*
- **H2 (diversifier), three dimensions (don't let Sharpe dominate):** sector rotation adds value to momentum if **any** of — (a) **correlation** with single-name momentum < 0.5; (b) a momentum+sector blend raises **return/Sharpe**; (c) the blend **lowers max drawdown** at ≈-equal Sharpe. *(V1 already cleared this; V2 confirms it survives the construction change.)*
- **H3 (construction isolation) — NEW for V2:** does pure-basket construction **improve risk-adjusted return vs V1's stock-level construction**? I.e., was the single-stock noise hurting? Measured as ΔSharpe(V2 − V1) with a paired bootstrap CI, on the identical signal/window/universe.

A **negative or inconclusive** result is still a success (recorded, declined / version-debt) — the Evidence Engineering moat.

## 2. The signal (frozen — **identical to V1**, per owner decision O2: do NOT re-optimize)

For each rebalance date `as_of`:
1. **Sector momentum** = for each of the 11 Sharadar sectors, the **equal-weight average of its constituent stocks' 12-1 momentum** (252-day lookback, 21-day skip — the production lookback). Point-in-time, survivorship-free (`universe_asof` + `tickers.sector` + SEP). **Byte-for-byte the V1 `sector_momentum_score` signal** — only the *construction* changes, so any difference is attributable to construction alone.
2. **Rank sectors** by sector momentum (highest = strongest).

## 3. Construction (frozen) — the V2 change

V1 reused `run_momentum_backtest(score_fn=...)`, which holds a flat **equal-weight across all held names**. That overweights sectors with more constituents and concentrates into whichever names happen to sit in strong sectors. **V2 replaces this with sector-neutral baskets:**

- Select the **top-K strongest sectors**.
- Each selected sector is held as an **equal-weight basket of all its liquid-universe constituents** at `as_of`.
- The portfolio is **equal-weight across the K baskets** → a name's weight = `(1/K) · (1/n_sector)`. This is **sector-neutral**: each held sector gets an equal sleeve regardless of its name count, and idiosyncratic single-stock risk is diversified away within each sleeve.

**Pre-registered parameters (frozen):**

| Parameter | Value | Note |
|---|---|---|
| Signal | 12-1 sector momentum | identical to V1, **not** re-optimized (O2) |
| **K (sectors held)** | **3** (headline) | top ~tercile of 11; diversified enough to test "pure" baskets. **{2, 4} reported as a labeled robustness band, NOT a decision variable** (no K-tuning). |
| Within-sector weight | equal-weight | honest default |
| Across-sector weight | equal (1/K) | **sector-neutral** — the V2 essence |
| Rebalance | **match V1's cadence** | so V1↔V2 isolates construction; a **monthly** variant reported as a turnover sensitivity |
| Cost | 10 bps headline | sweep 5/10/20/50 bps |
| Universe | top-200 liquid (headline) | + survivorship-free-breadth appendix |
| Window | **2000–2026** | match V1 |

**Construction roadmap (where V2 sits):**
- V1 — top-quintile of strong-sectors' stocks ✅ done (verdict B).
- **V2 — pure sector baskets (THIS doc).**
- V3 — dynamic sector weighting (overweight by signal strength / risk-parity) — only if V2 is promising.

> **Stopping rule (frozen — owner Suggestion 2).** If V2 fails to improve on V1 **and** H3 shows no
> meaningful construction benefit (ΔSharpe(V2−V1) CI spans zero), the platform will consider Sector
> Rotation **construction complete and archive the research program.** A V3 will be pursued **only** if
> V2 produces clear evidence that construction changes are the limiting factor. Future work beyond that
> would require a *fundamentally different hypothesis* (e.g. regime-conditioned or macro-overlaid
> rotation), not additional parameter tuning. This bounds the program and protects against an infinite
> refinement loop.

## 4. Pre-registered evidence gate (frozen BEFORE results)

| Criterion | Bar |
|---|---|
| **Standalone edge (H1)** | bootstrap 95% CI of **ΔSharpe vs equal-weight** excludes 0 (and positive) |
| **Significance** | paired circular-block bootstrap (2000 resamples, **seed 17** — same method as V1 / the P14 multi-factor re-test) |
| **Consistency** | positive ΔSharpe in **≥ ⌈W/2⌉+1** walk-forward windows |
| **Diversification (H2)** | corr(sector, momentum) **< 0.5**; and momentum+sector blend ΔSharpe vs momentum-alone CI excludes 0 (≥ one of the three H2 dimensions) |
| **Construction isolation (H3)** | report ΔSharpe(V2−V1) + paired CI; **directional finding, not a pass/fail gate** (informs V3) |
| **Cost-robust** | edge survives 5/10/20/50 bps |
| **Honest defaults** | equal-weight, sector-neutral, no in-sample tuning, no K-timing |
| **No-overfit clause (patent language)** | **No parameter is introduced solely to improve historical performance.** Every frozen parameter (signal 12-1, K=3, equal-weight, sector-neutral, cost 10bps) is either inherited unchanged from V1 or set to the conservative/diversifying default *before* seeing results. |

**Verdict (decision tree):**

| Outcome | Trigger | Action |
|---|---|---|
| **A — Validated standalone** | H1 clears (CI excludes 0) | → governance → **Paper Strategy #2 candidate** (own account). *The headline win: construction turned B→A.* |
| **B — Diversifier (confirmed)** | H1 still fails but H2 clears | → **blend / sector-overlay candidate**, evidence-gated; consider **V3 dynamic weighting** as the next lever |
| **C — Rejected** | both H1 and H2 span zero | → evidence package → knowledge base (clean "honest no") |
| **D — Inconclusive** | borderline / wide CI | → research debt → revisit (more data / V3) |

Plus an explicit **H3 read**: if V2 ≈ V1 (ΔSharpe(V2−V1) CI spans zero) the construction doesn't matter and we stop refining construction; if V2 > V1 decisively, single-stock noise *was* the drag and V3 is worth it; if V2 < V1, V1's stock-selection was adding alpha — a finding in itself.

## 5. Method (what the run will produce)

A new `scripts/sector_rotation_v2_research.py` (mirrors `sector_rotation_research.py`, adds the basket backtester):
1. **Basket backtester** — sector-neutral top-K baskets (the only genuinely new code; reuses store/universe/momentum/cost primitives). Pure functions, unit-tested.
2. **Factor-correlation** — sector score vs single-name momentum (monthly cross-sections).
3. **Full-window backtest** — V2 baskets vs **two benchmarks** (see §6) vs momentum (CAGR/Sharpe/maxDD/Calmar) + **paired Sharpe-difference bootstrap** (H1).
4. **Head-to-head V1 vs V2 panel** (H3) — reuse V1's evidence JSON; paired ΔSharpe(V2−V1) CI.
5. **Walk-forward** sub-windows (consistency).
6. **Blend test (H2)** — momentum + V2-sector composite; ΔSharpe vs momentum-alone.
7. **Cost sweep** 5/10/20/50 bps + the monthly-cadence turnover sensitivity.
8. **Evidence package** (`script → JSON → Markdown`, seeded/reproducible) + governance verdict → `docs/implementation/evidence/sec_001_v2_pure_baskets/`.

## 6. Benchmarks (V2 adds a sharper control)

- **All-sector equal-weight baskets** (**primary H1 control, NEW**) — hold *all 11* sectors sector-neutral. This isolates **"rotate into K strong sectors" vs "hold every sector"** — the cleanest possible test of the rotation signal, free of any stock-selection or sector-count artifact.
- **Equal-weight universe** (V1's benchmark — kept for continuity / direct V1↔V2 comparison).
- **Momentum v1.1** (the production book — H2 complementarity).
- **SPY** best-effort (the P12 §1 data gap still applies).

## 7. Out of scope (V2)

Risk-parity / vol-weighted / signal-strength sizing (→ V3); macro/regime-conditioned rotation (a larger hypothesis); sector ETFs as baskets (a future cross-check — gated on ETF price data, only ~1998+ and not survivorship-free, so synthetic baskets from the existing survivorship-free universe are the honest primary); live/paper activation (gated on VALIDATED + governance + own account, P5 §7).

## 8. Commercial-value criteria (carried from V1)

- **Explainability:** *"hold the strongest sectors, equally weighted"* — even simpler than V1 (no per-stock story). A pure-basket product is trivially explainable.
- **Marketability:** institutions run exactly this; sector-basket rotation is a recognized category.
- **Fit:** slots into the risk-dial product story as a standalone book OR a momentum overlay.

**Outcome → product impact (Suggestion 3 — ties research directly to commercialization):**

| Verdict | Product impact |
|---|---|
| **A — Validated standalone** | **Standalone strategy** — a new book / Risk-Profile family, the platform's 2nd commercial offering |
| **B — Diversifier** | **Portfolio overlay** — a momentum+sector blend / sector tilt, sold as a risk-reducing add-on |
| **C — Rejected** | **Knowledge asset** — a citable "honest no" that strengthens the Evidence Engineering moat |
| **D — Inconclusive** | **Research archive** — version-debt; revisited only with a new hypothesis (per the stopping rule) |

Scientific success → commercial success → product success are **distinct gates**; the run records all three.

## 9. Research risk register

| Risk | Mitigation |
|---|---|
| Pure baskets dilute the edge (diversification removes the alpha) | H3 V1-vs-V2 panel measures this directly |
| Still too correlated with momentum | H2 corr + blend |
| K is implicitly tuned | K frozen at 3; {2,4} only as labeled robustness, not a decision variable |
| Higher turnover from basket reconstitution | cost sweep + monthly-cadence sensitivity |
| Sector concentration at K=3 | sector-exposure line in the report; the all-sector-baskets benchmark contextualizes it |
| Regime dependency | walk-forward sub-windows |

## 10. Production path & cost

`Research → Evidence → Governance → Paper Account → 90-day Evidence → Production Candidate` (same lifecycle as the momentum Risk Profiles). **Estimated cost: ~1–1.5 sessions** — the basket backtester is the only new code (~2–3 hours); the run + analysis + evidence package ~1 day. Cheaper than V1 because the signal, harness primitives, and report scaffold already exist.

**Research cost (logged for research-ROI tracking across programs — owner suggestion B):**

| Resource | Estimate |
|---|---|
| Developer time | ~1–1.5 sessions (plan ✅ + basket backtester ~2–3h + run + evidence package) |
| CPU hours | ~0.2–0.4h (one full 2000–2026 backtest pass + paired bootstrap + the V1↔V2 panel) |
| Storage | negligible (one JSON + MD evidence package; reuses the existing store) |
| Dataset | **none new** — identical inputs to V1 (survivorship-free SEP + Sharadar `tickers.sector`) |
| Complexity | **Medium** — the sector-neutral basket backtester is genuinely new code (vs LOW-001's thin score wrapper), though everything around it is inherited |
| Reuse % | **~85%** — signal, store, universe, bootstrap, walk-forward, and report scaffold all inherited from V1 |

## 11. Resolved decisions (owner, 2026-06-21)

- **Q1 — K:** ✅ **K = 3** frozen headline; {2, 4} reported as a labeled robustness band only (no K-tuning).
- **Q2 — H3 gate-vs-read:** ✅ **Read-only** — informs V3 and feeds the **stopping rule** (§3); not a go/no-go gate. (The owner's Suggestion 2 stopping rule is built directly on H3 being a read.)
- **Q3 — primary benchmark:** ✅ **All-sector equal-weight baskets** is the primary H1 control (sharpest isolation of the rotation signal); the equal-weight universe is reported alongside for V1 continuity.

Plan is **frozen**. Next: build `scripts/sector_rotation_v2_research.py` + tests, run it, ship the evidence package.
