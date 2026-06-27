# ADR 0030 — Portfolio Construction Engine and the Capability Onboarding lifecycle (PORT-001)

| Field | Value |
|---|---|
| Date | 2026-06-27 |
| Status | **Proposed** (accepted on §0 completion / owner ratification). Governs the frozen plan `docs/implementation/TradingWorkbench_PORT001_ImplementationPlan_v1.0.md`. |
| Phase | PORT-001 onboarding (Portfolio Construction capability) — cross-phase platform architecture |
| Supersedes | — |
| Extends | **0026** (research programs as configuration — adds a portfolio-construction run path), **0014** (backtests are the primary eval ground truth — the reproduction bar), **0020** (daily gross-exposure overlay — the equity sleeve's crash engine rides it) |
| Related | 0002 (single OrderRouter — the live book routes through it), 0005 (activation cooldown — the live book is gated), 0019 (Research Engine subsystem), 0029 (Opportunity Registry — the Registry-split + phased-generalization precedent) |

## Context

PORT-001 ("Risk-Balanced Multi-Asset Portfolio", née Combined Book) is a validated, live paper strategy — but it runs **entirely in the sibling `claude-trading-view` system**, not on TradingWorkbench. We have decided to bring it onto the platform (the frozen v1.0 plan). Doing so surfaces four architectural questions the existing platform does not answer, plus one process question:

1. **Multi-sleeve construction.** Factor Lab's `run_program` (ADR 0026) assumes *one factor → one book* (`_run_quantile` / `_run_participation` / `_run_sector_baskets`). PORT-001 is **two independent sleeves** (crash-protected equity momentum + cross-asset trend) blended at **equal-risk-contribution**. There is no portfolio-construction path in the research engine.
2. **Total-return ETF data.** The cross-asset sleeve trades 8 asset-class ETFs on **total-return** daily bars (distributions matter for IEF/TLT/DBC). The platform's Alpaca bars are **unadjusted**; the sibling used Yahoo total-return. We must source total-return bars without compromising reproducibility.
3. **Registry shape.** The Research Program Registry (`app/research/programs.py`) catalogues *programs* (which produce evidence). PORT-001's onboarding also produces reusable *infrastructure* (a construction engine, a data adapter) that is a different kind of thing.
4. **Promotion discipline.** Migrating a live book risks the classic "migrate first, discover the numbers differ later" failure. We need an objective bar for "the platform reproduces the book" before any live promotion.
5. **Generalization timing.** The construction engine is plausibly reusable by MOM/LOW/SEC. Do we build it general now, or concrete-first?

These are coupled — they all arise from onboarding *one* validated capability under the platform's evidence discipline — so they are decided together here.

**The Capability Onboarding flow this ADR establishes (the one figure):**

```
External Capability ─► Capability Manifest ─► Evidence Reproduction ─► Onboarding Gate
        ─► Capability Registry ─► Paper ─► Continuous Evidence ─► Production ─► Retirement
```

## Decision

1. **Portfolio Construction Engine (PCE).** Add a **multi-sleeve portfolio-construction path** to Factor Lab: `ProgramSpec` gains a sleeve list + a blending config, and `run_program` gains a portfolio branch that runs each sleeve, blends them at **equal-risk-contribution (ERC)**, applies de-risk overlays, and emits the Evidence Package. The PCE is **allocation-policy-agnostic** by design (ERC is the only policy built now). It extends — does not replace — ADR 0026's "programs as configuration." _(Future: allocation policies become **discoverable via a Policy Registry** — ERC / inverse-vol / HRP / equal-weight / explicit risk-budget — mirroring the factor-builder registry. Architecture note only; not built.)_

2. **Total-Return Adapter — a Canonical Data Adapter.** Source total-return ETF bars by **post-processing**: raw Alpaca daily closes + corporate actions → total-return series. **No new external data vendor.** Classify it not merely as a "market-data capability" but as the first **Canonical Data Adapter** — a class of read-only adapters that normalize raw vendor data into a canonical, reproducible form (future peers: a Corporate-Action Adapter, FX normalization, trading-calendar normalization, split adjustment). The adjustment method is recorded in the Evidence Package so the backtest is reproducible (ADR 0014) — not an opaque vendor flag.

3. **Registry split + the Capability Manifest.** The registry distinguishes two kinds of asset: **Research Programs** (MOM/SEC/LOW/INSIDER/**PORT-001** — they *produce evidence* and carry a verdict) and **Platform Capabilities** (Portfolio Construction Engine, Total-Return Adapter, Discovery, Opportunity Registry — they *produce reusable infrastructure*). Every registered capability carries a **Capability Manifest** — the registry's metadata layer: `name · owner · research-id · evidence-package · dependencies (e.g. market-data adapters) · risk-profile · paper-account · version · certificate`. The Manifest is what makes the two-catalog registry queryable and is the structured record the Capability Certificate stamps. PORT-001 registers as a Research Program (`planned` until reproduced); the PCE and Total-Return Adapter register as Platform Capabilities; each gets a Manifest.

4. **Capability Onboarding lifecycle + Onboarding Gate (the platform standard).** Integrating an already-validated capability follows a fixed, **reproduce-first** lifecycle — *Research → Evidence → Migration → Reproduction → **Onboarding Gate** → Paper → Continuous Evidence → Production → Retirement* — with its own maturity ladder (L0–L5). Promotion from reproduction to a live paper book is gated on an **objective Onboarding Gate**: combined Sharpe within ±0.05, MaxDD within ±2.0 pp, **daily-return correlation ≥ 0.98**, target-weight correlation > 0.99, trade-count within tolerance, and **determinism** — *identical inputs must produce identical outputs* (Evidence Package + target weights); a principle, verified by repeated runs, not a fixed run-count. A miss is *attributed* (data / universe / construction), not waived. Passing emits a **versioned Capability Certificate** (`PORT-001 v1.0`), so a later re-onboarding/improvement (`v2.0`) is comparable against the first. This is the SEC-001 / INSIDER-001 / ADR 0014 reproduce-before-promote discipline, generalized.

5. **Concrete-first generalization (YAGNI).** Build the PCE as exactly what PORT-001 needs (two named sleeves, ERC); **lift it to a shared engine only when a second consumer (MOM/LOW/SEC) actually needs it** — mirroring ADR 0029's phased approach to the Opportunity Registry.

## Rationale

**Why extend Factor Lab rather than keep PORT-001 a bespoke strategy.** The sibling system *is* the bespoke version, and the whole point of onboarding is to bring it under the platform's evidence engine, OrderRouter, and registry. Keeping it bespoke on-platform would reproduce the sibling's isolation. Extending `run_program` with a portfolio branch reuses the seeded block-bootstrap evidence (`app/factor_data/evidence.py`), the verdict tree, and the registry that LOW/SEC/TREND already use — the reproduction is then defensible by the same machinery that validated those programs. The cost is that `ProgramSpec` is no longer "one factor"; that is accepted (see Consequences).

**Why post-process to total-return instead of a new vendor.** Three options existed: (A) accept unadjusted Alpaca bars and document the drift, (B) post-process Alpaca closes with distributions, (C) integrate a vendor with native total-return bars (Yahoo/Tiingo/stooq). (A) is rejected because for bonds/commodities the distribution gap is material and would make the reproduction fail for the wrong reason. (C) is rejected because a new external data dependency is a standing surface (key management, rate limits, licensing, another Norton-blocked endpoint on the dev box) that an estimator-from-existing-data avoids — and the platform's bias is to add external dependencies only when nothing else works. (B) reuses data we already pull (Alpaca DCAP-003) plus distributions, is cross-validatable against the sibling, and keeps the adjustment *in the Evidence Package* where ADR 0014 wants reproducibility recorded. The accepted trade-off: post-processing is our code to get right, and the reproduction will not match the sibling's Yahoo series exactly — which is why the Onboarding Gate is a tolerance band with drift attribution, not an equality check.

**Why split the registry.** Programs and capabilities are genuinely different: a program produces a verdict ("does this edge exist?"); a capability produces infrastructure other programs reuse. Conflating them makes the registry a flat list that cannot answer "what can I build on?" vs "what has been validated?". The split is the same realization ADR 0029 made for the Opportunity Registry (a capability) vs the strategies that consume it. It also future-proofs the dashboard the owner uses.

**Why an objective Onboarding Gate.** The dominant migration failure mode is promoting a port that looks similar but trades differently (Sharpe and MaxDD can match while turnover/trade-count diverge). A subjective "looks reproduced" judgment invites exactly that. Objective criteria — especially the **daily-return correlation ≥ 0.98** (proves it is the *same* book, not merely a book with similar summary stats) and **determinism** (proves no hidden nondeterminism in the construction) — make promotion measurable and the reproduction itself an evidence artifact. This is Evidence Engineering applied to migration, not just to research.

**Why concrete-first.** A general "Portfolio Construction Engine for any strategy" is a speculative abstraction until a second consumer's requirements are known; designing for hypothetical MOM/LOW reuse risks the wrong seams. Building PORT-001 concretely and generalizing on the second real consumer is the same discipline ADR 0029 used (Registry read-model first, shared engine later) and the platform's "proven costly" aversion to speculative generality.

## Implementation notes

Per the frozen plan (`TradingWorkbench_PORT001_ImplementationPlan_v1.0.md`), sequenced **reproduce-first**:

- **§0 (this ADR + registration):** `PORT-001` added to `app/research/programs.py` as a `ResearchProgram(status="planned")` with the honest verdict. The **Research-Program-vs-Platform-Capability split + the Capability Manifest schema** are recorded here; the concrete capabilities catalog + Manifest model (a sibling catalog or an extended taxonomy in `programs.py`) lands with the PCE in §2 (no value in an empty capabilities list at §0).
- **§1 — Total-Return Adapter** (`app/market_data/` or `app/factor_data/`): a read-only accessor mirroring the `bar_cache` shape returning total-return series for `SPY, EFA, EEM, TLT, IEF, GLD, DBC, UUP`; cross-validated vs the sibling (drift report). Plus the cross-asset TSMOM sleeve (12-1 long/flat, risk-parity, vol-target 10%).
- **§2 — PCE** in `app/research/factor_lab/`: extend `spec.py` (`ProgramSpec` → sleeves + blending), add a `_run_portfolio` branch in `runner.py`, an ERC optimizer primitive, and **portfolio-level evidence metrics** (sleeve correlation, look-through equity-beta-by-risk). The equity sleeve's crash engine is expressed through the **ADR 0020 daily overlay** (`on_overlay_tick` + vol-target + VIX/breadth), not re-implemented. Run the **Onboarding Gate** here.
- **§4 — live book** (`strategies_user/templates/combined_book.py`): weekly ERC rebalance via `ctx.submit_order` → **OrderRouter** (ADR 0002) → risk engine; correlation-regime de-risk as a whole-book gross multiplier; dedicated paper account, activation-cooldown-gated (ADR 0005); **co-exists** with the sibling.
- **No new CI invariant.** The PCE and adapter are research/market-data layer; nothing touches the order-path or LLM allowlists. The live book (§4) is an ordinary strategy under the existing risk/router invariants.
- **Honest verdict is mandatory** on every artifact: crash-protected **beta** + diversification, **not** alpha (combined α t=0.82 insignificant; stock-selection alpha refuted under PIT).

## Consequences

- **Positive:** PORT-001 comes under the platform's evidence engine + OrderRouter + registry; the onboarding leaves behind **two reusable platform capabilities** (PCE, Total-Return Adapter) — the spec's own "the real product is the construction framework"; the **Capability Onboarding lifecycle + Onboarding Gate + Capability Manifest** become a reusable standard for future onboardings (INSIDER, Discovery outputs, external/partner strategies, third-party quant models) **without changing the platform**. This is the strongest positioning shift in the project: TradingWorkbench becomes a **Capability Integration Platform for quantitative investment systems** — customers bring their own validated strategies and onboard them under one Evidence Engineering lifecycle. The onboarding *workflow* (Capability → Evidence Reproduction → Onboarding Gate → Capability Certificate → Continuous Evidence → Retirement) is the patent/whitepaper asset — preserve this and the ADR history around it. _(Whitepaper, later: "TradingWorkbench treats every investment capability as a managed software asset with a standardized lifecycle covering discovery, validation, onboarding, operation, monitoring, and retirement.")_ Reproduction is defensible by the same seeded-bootstrap machinery as LOW/SEC/TREND.
- **Negative:** `ProgramSpec` is no longer "one factor → one book" — the multi-sleeve extension adds surface to the research engine that every future change must reason about; the Total-Return Adapter is our code to maintain and validate (a wrong distribution splice silently biases the cross-asset sleeve); a "capabilities" registry is a second catalog to keep coherent with the programs one; the reproduction will **not** match the sibling exactly (total-return ≠ Yahoo; DAILY PIT starts 2016) so the gate is a tolerance with drift attribution, not equality — a judgment the band encodes but cannot fully remove.
- **Neutral:** introduces "Portfolio Construction Engine / Total-Return Adapter / Capability Onboarding / Onboarding Gate / Capability Certificate" as platform vocabulary; the sibling and the platform book **co-exist** for a period before the sibling is retired (more operational surface during onboarding, deliberately).

## Alternatives considered (not chosen)

- **Keep PORT-001 bespoke on-platform** (port the sibling scripts as a standalone strategy, skip Factor Lab). Rejected: reproduces the sibling's isolation, gets no evidence-engine reproduction, and the verdict would not be defensible by the platform's machinery. Reconsider only if the Factor-Lab extension proves disproportionately costly relative to the book's value.
- **New total-return data vendor (option C).** Rejected (see Rationale) — a standing external dependency the platform's bias avoids when a post-processing path exists. Reconsider if the distribution-splice proves fragile/unmaintainable or a second cross-asset capability needs broader instruments.
- **Live-first, backfill evidence.** Rejected by the locked reproduce-first decision — it is the migration failure mode the Onboarding Gate exists to prevent.
- **Build a general Portfolio Construction Engine up front.** Rejected (YAGNI) — speculative abstraction before a second consumer's requirements are known. Reconsider when MOM/LOW/SEC actually want multi-sleeve construction.
- **One ADR per sub-decision.** Considered (the "one decision per ADR" norm). Rejected because the five are coupled — they exist only in service of onboarding one capability — mirroring ADR 0006 v2's coupled-decisions precedent. If the **Capability Onboarding lifecycle** is adopted platform-wide beyond PORT-001, it should be lifted into its own standalone ADR + framework doc (a named re-evaluation trigger below).

## Re-evaluation triggers

- **A second portfolio capability** wants multi-sleeve construction → execute decision #5 (generalize the PCE), and revisit the engine's seams against the second consumer's needs before generalizing.
- **The Onboarding Gate cannot be met** for PORT-001 even after drift attribution (the reproduction genuinely diverges) → revisit whether unadjusted-bar drift, universe differences, or a construction gap is the cause, and whether the tolerance band or the data decision (option B → C) must change.
- **The Total-Return Adapter's splice diverges materially from realized total returns** in live operation → revisit option C (a native total-return vendor + its ADR).
- **A second capability is onboarded** via this lifecycle → lift the **Capability Onboarding lifecycle / Onboarding Gate** out of this PORT-001 ADR into a standalone platform-standard ADR + the framework doc the owner flagged.
- **The registry split causes coherence drift** (a capability and a program disagree about state) → tighten the two catalogs into one model or a single source of truth.
