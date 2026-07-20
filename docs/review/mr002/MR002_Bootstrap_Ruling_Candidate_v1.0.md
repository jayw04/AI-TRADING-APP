# MR-002 authoritative-bootstrap ruling **candidate** v1.0 (owner decides)

This is a **candidate**, not a ruling. It summarizes `MR002_Bootstrap_Source_Census_v1.0.json` and
recommends a disposition. No code is changed and no rule is set until the owner rules.

## The contradiction

| dimension | FROZEN v0.3 design (→ v1.0 signed frozen) | ValidationOOS chain (PhasePlan v0.2 → v1.0.3 + Increment 1) |
|-----------|-------------------------------------------|-------------------------------------------------------------|
| method | **stationary bootstrap** | non-circular **moving-block** |
| replications | **10,000** | 2,000 |
| seed | **20260711** | 42 |
| block rule | **expected** block length **5 sessions** | **fixed** L = **21** sessions |
| sensitivity | **10-session** block-length sensitivity | **none (dropped)** |
| statistic | 95% one-sided lower bound, mean daily net return | 95% one-sided percentile lower bound, daily mean net return |

These differ in resampling distribution, dependence assumption, replication count, random stream,
and the dropped sensitivity check — any of which can move the CI and therefore the bootstrap gate.

## What the census establishes

1. The **owner-signed frozen v1.0** document and its sealed-manifest freeze candidate contain **no
   moving-block text**; they freeze the v0.3 design **unchanged**. The prior gate-source census
   already established "the v0.3 gate table, frozen UNCHANGED into v1.0" as the governing authority.
2. Moving-block/L21/2000/seed42 appears **only** in the ValidationOOS review chain, first in
   **PhasePlan v0.2**, self-justified as "seed 42 matches the platform convention" — **not** a
   reference to any owner decision superseding v0.3.
3. **No owner decision record** addresses the bootstrap. `DecisionRecord_v1.0` has no bootstrap
   D-decision. `Finalization_v1.0`'s `estimator_bootstrap_unchanged=true` is "unchanged" **relative
   to the ValidationOOS chain**, not relative to v0.3.
4. This is the **same transcription-drift class** as the gate-battery mis-anchoring the earlier
   census corrected — that census fixed the gate table but did not separately audit the bootstrap,
   so the substitution survived. The moving-block spec also silently **dropped** the registered
   10-session block-length sensitivity.

## Recommended ruling (for owner adjudication)

**ADOPT the v0.3 stationary bootstrap as governing** and treat moving-block/L21/2000/seed42 as an
un-authorized post-freeze substitution to be corrected — because there is no owner decision
superseding v0.3, and the frozen v1.0 lineage nowhere specifies moving-block.

Concretely, if the owner concurs:
- Issue a **narrow ValidationOOS prereg correction (→ v1.0.4)** restoring the bootstrap to: stationary
  bootstrap on net daily portfolio returns · 10,000 replications · seed **20260711** · **expected**
  block length **5 sessions** · **10-session** block-length sensitivity · 95% one-sided lower bound on
  mean daily net return — machine-diff-proven to change no other gate/date/fold/cost/estimator/
  D-decision.
- Rebuild the **Increment-1 bootstrap primitive to v1.2** against that restored rule (stationary
  resampling with geometric-block draw, expected L = 5, 10,000 reps, seed 20260711, one-sided 95% LB),
  plus the 10-session block-length sensitivity as a reported robustness check.

**Alternative (requires an explicit new owner decision):** if the owner instead wishes to *formally
adopt* the moving-block procedure, that must be a **new, signed decision record** that explicitly
supersedes the v0.3 stationary rule (with rationale for the changed distribution, replication count,
seed, and the dropped sensitivity) — it cannot stand on the silent "matches the platform convention"
carry.

## Boundary

Until the owner rules, the bootstrap primitive is **GOVERNANCE-BLOCKED**, the bootstrap CI gate is
**NOT EXECUTABLE**, and Increment 1 stays open. No sealed data read; no performance computed.
