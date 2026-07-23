# DSR Trial Ledger — momentum-daily Equal-Weight Production-Sizing Validation — v1.0

**Date:** 2026-07-22 · **Governs:** `PREREG_EqualWeight_Production_Validation_v1.0.md` §7 D (DSR).
**Machine record:** `TrialLedger_v1.0.json` (built deterministically by `build_trial_ledger.py`).
**Content SHA-256:** `b7d9d71591cc449a1768f33a3f3f5e0dcdf8ae518710ecec13422f0a0a98eb6d`

## Conservative rule (owner 2026-07-22)

Include **every materially related experiment** in the momentum lineage whose result was seen before
the next design choice. Exclude **only** pure mechanical reproductions with no new performance
interpretation (documented). Uncertain/missing trials are counted **conservatively** (high). The
effective count may exceed the number of named strategies; it may fall below the included count **only
through a documented dependence/scope adjustment**, never silently.

## Counts (FROZEN at v1.0)

| quantity | value |
|---|---|
| raw rows | **47** |
| **included in trial count** | **45** |
| excluded (mechanical repro) | 2 |
| **effective DSR trial count** | **45** (== included; no dependence discount claimed) |

## Composition of the 45 included

| block | n | trials |
|---|---|---|
| Stage 2 — rebalance policy | 4 | Weekly(v0.9) · Trade-on-change · Daily-conditional · Biweekly |
| Stage 3 — construction grid | 12 | N{5,8,10} × {equal,hybrid} × {nocap,cap} |
| Stage 4 — regime | 4 | Binary · Buffered · Graduated · None-control |
| Inception threshold (Step 5) | 4 | Policy M/H × {proxy 5A, actual-book 5B} |
| Weighting-defect impact study | 6 | variants C,D × {equal-pinned, equal-free, production-capped} |
| MOM-002 Broad Momentum (related) | 12 | top_n{5,10,15,20} v1 + ×{no-cap,0.3} v2 |
| Factor screen (upstream) | 3 | momentum(sel) · low-vol · reversal |

**Excluded (2):** the two `A_defective_hybrid` reference arms of the impact study — mechanical
reproductions of the already-counted Stage-3/4 hybrid winner, no new configuration.

## ⚠ Two flagged adjudications (owner may issue a DOCUMENTED REDUCTION → v1.1)

Both are included by the conservative default (which counts high). Reducing either requires an
explicit documented scope/dependence adjustment — never a silent drop.

1. **MOM-002 (12 trials).** A *related-but-distinct* research program (Broad Momentum, closed
   rejected) that explored the name-count dimension for momentum. Included conservatively. The owner
   may rule it a separate lineage that should NOT count toward this strategy's DSR — a documented
   scope reduction of −12 (→ 33).
2. **Factor screen (3 trials).** The upstream momentum-vs-low-vol-vs-reversal selection. Counted as
   the 3 named factors (conservative for the uncertain sub-config count). The exact artifact was not
   located; the owner may **raise** it (if each factor carried sub-configs) or, with documentation,
   rule the cross-strategy screen out of this DSR's scope (−3, → 42 or, with MOM-002 also out, 30).

**The direct momentum-daily lineage alone (Stage 2/3/4 + inception + impact) = 30 included.** The
frozen conservative count is **45**; the documented-reduction floor, if the owner scopes out both
flagged blocks, is **30**.

## DSR usage

The §7 D gate requires `DSR: P(adjusted Sharpe > 0) ≥ 0.95` computed with **this** trial count. The
Deflated Sharpe Ratio deflates by the number of trials that could have produced the best-looking
result, so a **higher** count is the harder (safer) gate — which is why the conservative direction is
to over-, not under-count. The frozen `N = 45` is used unless the owner issues a documented reduction.
