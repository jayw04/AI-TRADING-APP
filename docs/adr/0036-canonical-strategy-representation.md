# ADR 0036 — Canonical Strategy Representation

| Field | Value |
|---|---|
| Date | 2026-07-04 |
| Status | Accepted (owner-directed 2026-07-04) |
| Phase | Cross-phase (live paper lineup / research governance) |
| Supersedes | — |
| Related | 0031 (per-strategy paper account isolation), 0021 (operational-reliability contract) |

## Context

The live paper lineup accumulated three separate momentum books — `momentum-portfolio`
(Balanced, 15% vol target), `momentum-conservative` (10%), and `momentum-growth` (20%) — each on
its own isolated paper account (users 1, 3, 4). They share the **same ranking engine, the same
universe, the same rebalance cadence, and the same alpha source**; they differ only in the
vol-target gross scaling applied by the overlay.

The platform's own measurement proves they are not distinct research programs: the Portfolio
Analytics Engine (CAP-021) measured pairwise correlation **≈ 1.00** and holdings overlap **≈ 100%**;
MOM-002 found that reshaping the *same* momentum factor does not create independent evidence; and
FI-001 confirmed that diversification requires *distinct factors*, not re-scalings of one. The
research question these three books were provisioned to answer — *"does changing the volatility
target materially change the strategy?"* — has been answered: **no; vol targeting changes risk, not
alpha.**

Running three near-identical books as separate live "research programs" therefore (a) misrepresents
one validated alpha as three, contradicting the platform's own Evidence-Engineering honesty; (b)
triples the rebalance/data/operational cost for a single signal; and (c) muddies attribution. We
need a governing principle for how validated alphas map to live accounts, so this does not recur as
future strategies gain risk-profile variants.

## Decision

**Each unique validated alpha source has exactly one canonical live production account.** Risk-profile
variants (e.g. different volatility targets) are **selectable operational configurations** of that one
strategy — deployment presets, like a fund's Conservative/Moderate/Aggressive allocations — **not
independent research programs and not separate live accounts.** A variant earns its own program and
account only when evidence shows it is a *distinct alpha* (materially different holdings / a
correlation materially below ~1.0), not merely a different risk setting.

## Rationale

- **The evidence gates the representation.** The platform's headline discipline is that a live book's
  most visible attribute is its research *verdict*. Three books that the platform's own analytics score
  at corr ≈ 1.00 / 100% overlap are, by that same evidence, one program. Representing them as three
  contradicts the methodology the platform exists to demonstrate.
- **This is positive evidence, not a cleanup of a mistake.** Provisioning the three vol-variants in
  Phase 1 correctly answered a real question (does the vol dial change behavior?). Concluding that study
  and collapsing to one canonical book is the *mature* outcome — many quant shops present
  Conservative/Balanced/Growth as three independent strategies; stating plainly that they are one
  strategy at three risk settings *increases* credibility.
- **Cost and attribution.** One account per alpha removes 2× redundant weekly rebalances (compute, data,
  order flow) and keeps performance attribution clean (which program produced which result).
- **The risk dial is preserved as configuration, not as separate accounts** — the vol target remains a
  first-class, selectable parameter of the canonical strategy, so nothing is lost operationally.

Trade-off accepted: the live lineup no longer shows the three vol targets *side by side as separate
accounts*. That side-by-side "risk dial" demonstration was a legitimate Phase-1 asset, but the question
it answered is closed; the same point is now made more honestly by exposing the vol target as a preset
on one book plus the preserved history of the archived variants.

## Implementation notes

- **Account mapping:** one PAPER account per validated alpha. MOM-001 (momentum) → the single
  `momentum-portfolio` book (user 1, Balanced 15% as the default preset). The distinct diversifier
  programs already hold their own accounts (LOW-001 user 6, SEC-001 user 5, combined-book user 7) and
  RNG-001 the sandbox (user 2) — this ADR does not change those.
- **Risk profile = parameter:** the vol target is a strategy parameter of the canonical book, not a
  reason to provision a new account. Presets: Conservative 10% / **Balanced 15% (default)** / Growth 20%.
- **First application (this ADR's driving change):** `momentum-conservative` (id 4, user 3) and
  `momentum-growth` (id 5, user 4) are **deactivated → IDLE, not deleted** — positions, equity curves,
  trade history, and operational logs are preserved as the completed-research record ("Archived after
  research completion — consolidated into canonical MOM-001"). See the Research Decision
  `evidence/mom_001/MOM001_RiskProfile_Consolidation_v1.0.md`.
- **Relationship to ADR 0031:** ADR 0031 established *per-strategy paper account isolation* (each live
  strategy gets its own account so risk/cash don't co-mingle). ADR 0036 refines *what counts as a
  strategy for that mapping*: one account per unique **alpha**, not per **risk variant**. The two are
  complementary — isolation still holds for every canonical book.
- No code/schema change is required to establish the principle; it governs provisioning and the
  registry. Deactivation uses the existing `POST /strategies/{id}/stop` path (status → IDLE, history
  preserved).

## Consequences

- **Positive:** the live lineup honestly reflects the research (one alpha = one book); ~2× lower
  momentum operating cost; clean attribution; a stated principle that prevents the same sprawl as future
  strategies gain risk presets.
- **Negative:** the platform loses the at-a-glance, three-account live comparison of vol targets. A
  future viewer who wanted to see 10/15/20% running simultaneously as separate books no longer can
  (mitigated: the preset is selectable, and the archived books' history remains inspectable).
- **Neutral:** every future strategy must now declare its canonical representation and treat risk
  presets as configuration; provisioning reviews gain one more question ("is this a distinct alpha or a
  risk setting?").

## Alternatives considered (not chosen)

1. **Status quo — one account per vol variant.** Rejected: contradicts the corr ≈ 1.00 / 100%-overlap
   evidence, implies three alphas where there is one, and triples cost for no incremental evidence.
   Reconsider only if a variant is shown to be a distinct alpha.
2. **Delete the risk profiles entirely.** Rejected: the vol dial is a real, useful deployment lever
   (the fund-allocation analogy). Keep it — as configuration, not as separate accounts.
3. **Keep all three but relabel them a single "program" in the registry while leaving three live
   accounts.** Rejected: cosmetic — it fixes the label but not the 2× cost, the redundant order flow, or
   the attribution ambiguity.

## Re-evaluation triggers

- **A risk-profile variant is shown to be a distinct alpha** — e.g. a vol-target or construction change
  that drops cross-variant holdings correlation materially below ~1.0 (say < 0.8) on the platform's own
  Portfolio Analytics. Then it earns its own program ID and account.
- **A customer, regulatory, or capital-segregation requirement** genuinely needs separate live accounts
  per risk profile (distinct mandates), overriding the research-representation argument.
- **The vol-target overlay is retired or replaced** such that "risk profile" no longer means "same
  holdings, scaled gross" — revisit what a canonical representation should expose.
