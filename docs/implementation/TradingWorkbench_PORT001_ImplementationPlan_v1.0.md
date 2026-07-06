# PORT-001 — Capability Onboarding Implementation Plan (Session Zero)

| Field | Value |
|---|---|
| Document version | **v1.1 — FROZEN for execution** (2026-06-27; all 4 OQs resolved; ADR-0030-review refinements folded) |
| Date | 2026-06-27 |
| Program | **PORT-001** — product name **"Risk-Balanced Multi-Asset Portfolio"** (formerly "Combined Book") |
| Capability class | Portfolio Construction (multi-sleeve ERC + crash/correlation overlays) |
| Type | **Capability Onboarding** — integrating a validated sibling capability into the platform (sibling `claude-trading-view` → TradingWorkbench) |
| Source spec | `Docs/Strategies/Combined Book Strategy.md` (the capability spec; §12 done-definition) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Onboard the live two-sleeve Combined Book onto the platform: Factor-Lab ProgramSpec + Evidence Package → Onboarding Gate → Registry → OrderRouter paper execution → Continuous Evidence → retire sibling. **Reproduce-first.** |
| Estimated wall time | **Multi-session** (~6 sessions; see §Phases). This Session-Zero doc ships no code — it produces the plan + the `planned` Registry entry + the governing ADR. |
| Tag on completion | `port001-session0-complete` (plan frozen + ADR accepted + Registry `planned` entry) |
| Out of scope (this Session Zero) | Any sleeve/Factor-Lab/strategy code; the λ≈0.5 correlation-aware tilt; full-universe vs top-20 calibration; retiring the sibling. |

> **Changes since v0.1** (owner review 9.95/10): reframed migration → **Capability Onboarding**; added the objective **Onboarding Gate** + **Migration Fidelity scorecard** + Capability Certificate; elevated the **Portfolio Construction Engine** + **Total-Return Adapter** to named platform capabilities; Registry split (Programs vs Capabilities); **OQ-4 resolved**.
>
> **Changes since v0.2** (final review 10/10): added the **Capability Onboarding Maturity** ladder (L0–L5, distinct from strategy maturity); **Onboarding Gate** gains **trade-count** + **determinism** criteria; **Migration Fidelity** framed as a permanent dashboard with a composite score; renamed Migration Certificate → **Capability Certificate**; PCE noted **allocation-policy-agnostic** + future Opportunity-Registry compatibility; Total-Return Adapter classified a peer **Market Data Capability**; added the platform-asset framing sentence + the determinism principle; strengthened the whitepaper/patent note (**Capability Integration Platform** + a future Platform-Lifecycle chapter).
>
> **Changes v0.3 → v1.0 (FROZEN):** OQ-1 resolved — product name **"Risk-Balanced Multi-Asset Portfolio"** (PORT-001 remains the capability ID). OQ-3 resolved — the dedicated Workbench paper account is **provisioned at §4** (placeholder until then; does not block the reproduce-first §0–§3). All four OQs are now resolved → the plan is frozen and ready to execute.

> **Platform-asset framing.** TradingWorkbench treats investment capabilities as **reusable software assets** that can be independently researched, onboarded, validated, monitored, and retired under a common **Evidence Engineering lifecycle**. PORT-001 is the first capability onboarded this way; the *lifecycle* it runs through is the durable asset.

---

## Why this exists

The Combined Book (PORT-001) is the owner's flagship paper strategy, but it runs **entirely in the sibling `claude-trading-view` system** — its own scripts, risk stack, and Windows-Task orchestration — **not** as a TradingWorkbench capability routed through Factor Lab / the OrderRouter / the Evidence Engine. The capability spec (`Combined Book Strategy.md` §12) is explicit and honest about this gap and defines a **six-point done-definition** for the migration. This document is the executable plan that closes it.

The research is **complete** (and its verdict is honest: crash-protected *beta* + diversification, **not** alpha — stock-selection alpha was refuted under point-in-time data, spec §6.4). So this is **engineering, not research**. Research already answered *"does the strategy work?"*; onboarding answers a different question: ***"can the platform reproduce it?"***

---

## The Capability Onboarding lifecycle (PORT-001 is the first instance)

> _Per the owner review (highest recommendation): the pattern here is reusable well beyond the Combined Book — INSIDER, Discovery Lab, Sector Rotation, or externally-developed strategies can all follow it. We define it once, as a standard, and run PORT-001 through it._

This is **Capability Onboarding** — integrating an *already-validated* capability into the Evidence Engineering platform — not merely "moving code." The standard lifecycle:

```
Research → Evidence → Migration → Reproduction → [ONBOARDING GATE] → Paper → Continuous Evidence → Production → Retirement
  (done)   (sibling)   (port)     (Workbench EP)   (objective ✓)     (co-exist)   (dashboard)      (later)    (sibling off)
```

Two properties make it disciplined:
- **Reproduce-first** — the platform must independently reproduce the sibling's evidence *before* the live book is promoted (eliminates the "migrate first, discover differences later" failure mode). This is Evidence Engineering applied to migration.
- **Objective promotion** — promotion is gated on a measurable **Onboarding Gate** (§Gate), not a judgment call.

PORT-001 runs through this lifecycle; the lifecycle itself is a candidate **platform standard** ("Capability Onboarding Framework") worth its own doc + a whitepaper section (§Notes #8). _(Standalone framework doc = a follow-up, not this Session Zero.)_

**Capability Onboarding Maturity** (distinct from strategy/Capability Maturity — onboarding has its own ladder):

| Level | Gate |
|---|---|
| **L0** | Research complete (the capability is validated in its origin system) |
| **L1** | Evidence reproduced (Workbench Evidence Package built) |
| **L2** | Onboarding Gate passed (objective criteria — §Gate) |
| **L3** | Paper operational (live on a Workbench paper account, co-existing) |
| **L4** | Continuous Evidence (monitors feed the Evidence Dashboard) |
| **L5** | Production-Qualified (promoted; origin system retired) |

> **Determinism principle.** Capability onboarding is **deterministic**: identical inputs must produce identical Evidence Packages and identical target portfolios. This is the reproducibility floor under the Onboarding Gate (and is itself a gate criterion — §Gate "determinism").

---

## Locked decisions (owner)

1. **Reproduce-first** (2026-06-27). Build the Factor-Lab ProgramSpec and reproduce the sibling's headline as a Workbench **Evidence Package before the live book** (SEC-001 / INSIDER-001 / ADR 0014 discipline). The live book is gated on the **Onboarding Gate** (§Gate) passing.
2. **Total-return via post-processing (no new vendor)** (2026-06-27). Splice distributions into Alpaca closes to build total-return series; no new external dependency. Built as a **reusable Total-Return Adapter** platform capability (§Capabilities), not a PORT-001-private hack.
3. **Port the current live config first (λ = 0)** (2026-06-27). Migrate exactly what is live; the researched λ≈0.5 correlation-aware tilt (spec §11 #1) is a **later** improvement, so the reproduction target equals the live book.
4. **Reproduce the current production universe first** (2026-06-27, OQ-4 resolved). Do **not** change the universe and the platform simultaneously — **one variable at a time**. Match the sibling's pinned mid+large+mega universe + its top-20 small-account construction for the reproduction; full-universe vs top-20 is a *later research* lever (spec §11 #5), not part of onboarding.

---

## Prerequisites & current platform state (grounded — reuse vs. gaps)

**Reusable platform seams (verified in code):**

| Need | Reuse | Where |
|---|---|---|
| Weekly-rebalance portfolio strategy (diff target vs held → OrderRouter → risk) | `momentum-portfolio` / `sector-rotation` / `low-volatility` share one pattern | `strategies_user/templates/momentum_portfolio.py`; `app/strategies/{base,context}.py`; `app/orders/router.py` |
| **Equity sleeve crash engine** (vol-target + VIX/breadth regime cut, de-risk-only) | **Maps 1:1 onto the ADR-0020 daily overlay** (`on_overlay_tick` + `desired_gross`) | `app/strategies/overlay/__init__.py`; `app/factor_data/regime.py` |
| Fractional/notional multi-symbol orders, turnover bands, rank hysteresis | Already in the momentum template | `momentum_portfolio.py` |
| Factor-Lab programs (ProgramSpec → `run_program` → verdict tree) | LOW/SEC/TREND are configs | `app/research/factor_lab/{spec,runner,configs,registry}.py` |
| Evidence Engine (seeded block-bootstrap CIs, paired-Sharpe) | Reused by every program | `app/factor_data/evidence.py` |
| Research Program Registry | Program catalog | `app/research/programs.py`; API `app/api/v1/evidence.py` |
| Equity PIT data (universe, prices, market cap) | Sharadar SEP/SF1/DAILY, DuckDB | `app/factor_data/` + `data/factor_data_full.duckdb` |
| ETF daily bars | Alpaca `BarCache` (unadjusted) | `app/market_data/bar_cache.py` |
| `^VIX` | FMP, `index_prices`, percentile-only | `scripts/ingest_vix.py`; `app/factor_data/regime.py` |

**The real gaps (the engineering this plan delivers):**
- **G1 — Multi-sleeve ERC is not in Factor Lab.** `run_program` is one factor → one book. PORT-001 = two sleeves blended at equal-risk-contribution → the **Portfolio Construction Engine** (§Capabilities).
- **G2 — The cross-asset TSMOM sleeve is new** (8 ETFs, 12-1 long/flat, risk-parity, vol-targeted — a per-asset trend sleeve, not a Sharadar cross-section).
- **G3 — Total-return ETF bars** (resolved by decision #2 → the **Total-Return Adapter**).
- **G4 — Portfolio-level evidence/risk** (look-through equity-beta concentration; sleeve-correlation regime) not in the Evidence Package or risk engine.

---

## Platform capabilities this onboarding introduces (reusable, not PORT-001-private)

Two durable assets fall out of PORT-001 — the spec's own point that *"the real product is the construction framework."* Build them as named platform capabilities so MOM/LOW/SEC and future dividend/bond/ETF strategies reuse them.

### Portfolio Construction Engine (PCE) — new platform capability
The multi-sleeve construction subsystem the Factor Lab gains. It is what makes PORT-001 *different* from LOW/MOM/SEC (which are single-sleeve):

```
   Sleeve A (equity momentum + crash overlay)  ┐
                                               ├─►  ERC blend (~40/60)  ─►  De-risk overlays  ─►  Combined book  ─►  Evidence
   Sleeve B (cross-asset TSMOM, 8 ETFs)        ┘     (equal-risk-contribution)   (vol-target · VIX/breadth · corr-regime)
```
Registry capability class: **Portfolio Construction** (alongside Discovery, Opportunity Registry). Generalization stance: **build PORT-001 concretely first; lift the PCE to a shared engine only when a second consumer needs it** (YAGNI, consistent with ADR 0029's phased Registry).

- **Allocation-policy agnostic.** Today the PCE blends sleeves at **ERC**; it is designed so the allocation policy is a pluggable input — future policies (inverse-vol, equal-weight, HRP, explicit risk-budget) drop in without changing the engine. _(ERC only is built now; the others are not in scope.)_
- **Future Opportunity-Registry compatibility (vision, no implementation).** Future portfolio capabilities may source their candidate universes through the **Opportunity Registry** (ADR 0029) while retaining independent portfolio-construction logic. PORT-001 does **not** consume it today (it uses its own pinned universe).

### Total-Return Adapter — new Market Data Capability
Decision #2 as a reusable layer, not a one-off — a **peer platform capability** alongside Discovery, Opportunity Registry, and Portfolio Construction:
```
Market Data Layer  ─►  Total-Return Adapter (Alpaca closes + distributions)  ─►  consumers (PORT-001 today; future dividend/bond/ETF strategies)
```

---

## Phases (each a session; mapped to the spec §12 done-definition)

> Governing order = **reproduce-first**. §1–§3 produce the validated Evidence Package; only after the **Onboarding Gate** passes does §4 stand up the live book.

- **§0 — This document (Session Zero, no code).** Ships: this plan (freeze at v1.0 after OQ-1/OQ-3); a **`PORT-001` Registry entry** (`status="planned"`, honest verdict); and the governing **ADR** (§ADR). → done #3 (initial).
- **§1 — Total-Return Adapter + cross-asset TSMOM sleeve** *(G2, G3)*. The adapter (decision #2, reusable) + the 8-ETF sleeve (research parity with `cross_asset_momentum.py`), cross-validated vs the sibling. Est 5–8h, walk-away ≥1h.
- **§2 — Portfolio Construction Engine + ERC + reproduction** *(G1, G4; heavy)*. Extend `ProgramSpec` (sleeves + blending) + a `_run_portfolio` branch; an **ERC optimizer**; portfolio-level evidence metrics (sleeve corr, look-through beta). **Reproduce the sibling headline → run the Onboarding Gate (§Gate).** Est 8–12h, walk-away ≥2h.
- **§3 — Evidence Package + Registry verdict + Capability Certificate** *(done #1,#2,#3)*. Register the Evidence Package + honest verdict; emit the **Lifecycle Fidelity dashboard** + the **versioned Capability Certificate** (§Certificate). Est 3–5h, walk-away ≥1h.
- **§4 — Live `combined_book` template + Workbench paper account** *(done #4)*. `strategies_user/templates/combined_book.py` (weekly ERC rebalance; crash engine via `on_overlay_tick`; corr-regime gross multiplier) on a dedicated paper account (OQ-3), activation-gated, **co-existing** with the sibling. Est 6–9h, walk-away ≥2h.
- **§5 — Continuous Evidence** *(done #5)*. Correlation-regime / look-through / reconciliation monitors → the Evidence Dashboard (the `live_evidence.py` weekly pattern). Est 4–6h.
- **§6 — Retire sibling** *(done #6)*. Gated on sustained agreement (co-exist). Owner-timed.

---

## The Onboarding Gate (objective promotion criteria)

> _Owner review: make the reproduce-first gate stricter and objective. §2 does not promote to §4 until ALL pass._

| Criterion | Threshold | Source |
|---|---|---|
| Combined Sharpe | within **±0.05** of sibling | Evidence Package vs spec headline (0.84) |
| Combined MaxDD | within **±2.0 pp** of sibling | vs −11.9% |
| Daily-return correlation (sibling vs Workbench) | **≥ 0.98** | OQ-2 — proves it's the *same book*, not just similar stats |
| Weight correlation (per-rebalance target weights) | **> 0.99** | target-book agreement |
| Annual turnover | within tolerance (set in §2) | construction parity |
| **Trade count / frequency** | within tolerance | execution sanity — Sharpe + MaxDD can match while *execution* doesn't; matching trade frequency catches that |
| **Determinism** | exact | **identical inputs → identical outputs** (Evidence Package + target weights) — a principle, verified by repeated runs (not a fixed run-count); the §Lifecycle determinism principle |

A miss → diagnose + attribute the drift (data, universe, or construction) before any promotion. Drift is *attributed*, not waved through.

## Lifecycle Fidelity dashboard (§3 output — the onboarding's own evidence)

A **permanent dashboard** with a composite **fidelity score** (e.g., *PORT-001 — Fidelity 96.7%*) that drills into: **Sharpe · CAGR · MaxDD · tracking error · turnover · trade count · gross/exposure · sleeve correlation · weight difference · daily-return correlation · drawdown difference.** Framed as **Lifecycle Fidelity** — compare the book across its whole lifecycle (**Capability → Research → Workbench → Live**), not just sibling → Workbench — so drift is attributable to the stage that introduced it. Customer-legible at a glance; feeds the Evidence Dashboard and the Capability Certificate.

## Capability Certificate (ties to Capability Onboarding Maturity)

Every onboarding emits a **versioned Capability Certificate** — a platform-status stamp (not a "migration" artifact; it scales to any capability's lifecycle state). Versioning (`v1.0`) lets a later re-onboarding/improvement (`v2.0`) be compared against the first. It is stamped onto the capability's **Capability Manifest** (the registry metadata layer defined in **ADR 0030 §3**: name · owner · research-id · evidence-package · dependencies · risk-profile · paper-account · version · certificate).

| Capability Certificate — PORT-001 **v1.0** | Status |
|---|---|
| Research | ✓ Completed |
| Evidence reproduced (L1) | _(set at §2)_ |
| Onboarding Gate (L2) | _(Passed/Failed at §2)_ |
| Paper (L3) | _(Running at §4)_ |
| Continuous Evidence (L4) | _(Operational at §5)_ |
| Production-Qualified (L5) | Pending |

---

## Registry — Research Programs vs Platform Capabilities

> _Owner review #5: the registry today holds **programs**; soon it holds **capabilities** too. Distinguish them so it scales._

- **Research Programs** (validated/rejected investment instances): MOM-001, SEC-001, LOW-001, TREND-001, INSIDER-001, **PORT-001**.
- **Platform Capabilities** (reusable assets): **Portfolio Construction Engine**, **Total-Return Adapter**, Discovery, **Opportunity Registry** (ADR 0029).

PORT-001 registers as a Research Program; the PCE + Total-Return Adapter register as Platform Capabilities. (Implementation: extend `app/research/programs.py` taxonomy, or a sibling capabilities catalog — decided in §0/ADR.)

---

## ADR required (drafted in §0)

One ADR governs the new architecture (proposed title): **"Portfolio Construction Engine in Factor Lab (multi-sleeve ERC) + Total-Return Adapter; Capability Onboarding lifecycle."** It records: the multi-sleeve ERC extension (builds on ADR 0026); the **Total-Return Adapter** (decision #2, ADR 0014 reproducibility); the registry split (Research Programs vs Platform Capabilities); the **Capability Onboarding lifecycle + Onboarding Gate** as the platform standard; and the engine-generalization (YAGNI) stance.

---

## OQ — Resolved-decisions log (all closed; plan frozen)

1. ~~Product name~~ — **RESOLVED**: **"Risk-Balanced Multi-Asset Portfolio"** (PORT-001 remains the capability ID). The construction-framework-flavoured name, matching the spec's "the real product is the construction."
2. **Reproduction tolerance** — **RESOLVED**: Sharpe **±0.05**, MaxDD **±2.0 pp**, daily-return correlation **≥ 0.98**, weight correlation **> 0.99**, plus trade-count + determinism (all in §Gate). _Turnover tolerance is set concretely in §2 against the observed sibling figure._
3. ~~Workbench paper account~~ — **RESOLVED**: **provisioned at §4** (placeholder until the live book). The sibling keeps PAPER2; the Workbench gets its own dedicated, per-user-isolated account when §4 begins. Does **not** block the reproduce-first §0–§3.
4. ~~Equity universe~~ — **RESOLVED** (decision #4): reproduce the current production universe + top-20 construction first; full-universe is a later research lever.

---

## What this Session Zero does NOT do

1. Write any sleeve, Factor-Lab/PCE, adapter, or strategy code (that is §1+).
2. Apply the λ≈0.5 correlation-aware tilt (deferred; a post-onboarding improvement).
3. Stand up the live Workbench book or provision its account (§4, gated on the §2 Onboarding Gate).
4. Touch the sibling system (it runs throughout co-exist; retired only in §6).
5. Build a *general* Portfolio Construction Engine for MOM/LOW/SEC (PORT-001 concrete first; generalize later).
6. Change the universe (decision #4 — current production universe first; full-universe vs top-20 is later research).
7. Author the standalone **Capability Onboarding Framework** doc + whitepaper section (a follow-up — §Notes #8).

---

## Notes & gotchas

1. **The crash engine ≈ the existing daily overlay.** Don't re-implement vol-target + VIX/breadth — express the equity sleeve's L1/L3 layers through `on_overlay_tick` (ADR 0020/0022), keeping live ≈ research.
2. **Evidence parity is byte-stable.** Use the seeded `factor_data/evidence.py` block-bootstrap (matched bespoke harnesses for LOW/SEC/TREND) so the reproduction is defensible.
3. **Reproduction won't be exact** — total-return post-processing ≠ Yahoo, and DAILY PIT starts 2016 (spec §10 #6). The **Onboarding Gate** sets the band; *attribute* the drift (data/universe/construction), don't chase an exact match.
4. **Look-through risk is the honest headline.** ~13% equity-sleeve capital but ~60–89% of risk (spec §6.2) — the Evidence Package must surface it (G4). It is the capability's most important disclosure.
5. **Co-exist, don't cut over.** Sibling stays live until sustained agreement (SEC-001/INSIDER-001 retirement bar). §6 is owner-timed.
6. **Account-identity fragility.** The sibling lost its book to an accidental account repoint (spec §7). The §4 account provisioning must include the account-identity guard.
7. **No alpha claims.** Every artifact carries the honest verdict — risk-managed beta, alpha refuted under PIT.
8. **Whitepaper / patent note (owner review).** The novel, defensible asset is **not** ERC or the Combined Book — it is the **Capability Onboarding workflow**: *External Capability → Evidence Reproduction → Onboarding Gate → Continuous Evidence → Capability Certificate → Retirement*. It makes TradingWorkbench a **Capability Integration Platform** ("integration" — an ongoing platform capability — not "migration," which sounds temporary): it can host multiple independent investment capabilities (Combined Book, Insider, Discovery Lab outputs, external/partner strategies, third-party quant models) under one evidence discipline. **Patent:** this workflow is the unique claim — discuss with patent counsel on the next filing. **Whitepaper:** the architecture (currently Discovery → Research → Operation) should eventually gain a **Platform Lifecycle** chapter adding *Onboarding* and *Retirement* (Discovery → Research → Onboarding → Operation → Retirement). _(Later, not now.)_

---

*v1.1 — 2026-06-27 — **FROZEN for execution** (final review 10/10; ADR-0030-review refinements folded: Lifecycle Fidelity, principle-based determinism, versioned Capability Certificate + Capability Manifest pointer to ADR 0030). Filename kept at `…v1.0.md` (the frozen-plan anchor referenced by §0/§1 commits, ADR 0030, and memory); the version field is authoritative. Execute: §0 ✓ → §1 ✓ → §2 (PCE + reproduction → Onboarding Gate) → §3 → §4 → §5 → §6.*
