# MR-002 DSR Trial-Ledger — Governance Blocker v1.0

**Status:** OPEN BLOCKER. The Deflated Sharpe Ratio (DSR) is the governing significance **gate**
(v0.3-frozen-into-v1.0). DSR requires an exact trial count `N`. The frozen record does **not**
support a single defensible `N`, so — per the owner's DSR ruling ("if the historic record cannot
support an exact defensible N, stop and submit that as a separate governance blocker; do not
guess") — the DSR gate cannot be finalized or implemented until `N` is bound. No sealed data was
read to produce this.

## What the frozen record says

- **v0.3 (governing gate table), verbatim:** "**Trial ledger:** configs A/B/C + the mean-reversion
  family's prior examined variants (RNG-001 and documented sub-studies; informal MR variants logged
  before freeze); a first-class evidence artifact."
- **v0.1:** "`N_trials = 3` (plus any sensitivity explicitly listed in this document — nothing
  else)." — superseded by v0.3's broader ledger.
- **PBO** is separately labeled "**N = 3 — underpowered**" (configs A/B/C) and is a **diagnostic**,
  not a gate. PBO's N=3 is not in question.

## Why N is not defensibly pinnable

1. **A/B/C = 3** is exact (z-entry 1.75 / 2.00 / 2.00-primary… A 1.75 / B 2.00 / C 2.25).
2. **RNG-001 = 1** documented prior study (Completed · Rejected (Evidenced)).
3. **"documented sub-studies"** and **"informal MR variants logged before freeze"** are **not
   enumerated** in any committed artifact found in the census — there is no
   `trial_ledger` file, and the phrase is open-ended.

So `N` could be 3 (A/B/C only), 4 (+RNG-001), or more (+unenumerated sub-studies/informal variants).
The DSR bar (expected-max-Sharpe deflation) rises with `N`; choosing `N` after the fact — or
guessing — would let the analyst tune the significance bar. That is exactly what the preregistration
must prevent.

## Required to resolve (before the DSR gate is executable)

Bind, from the **frozen pre-freeze record only** (no post-freeze additions):
- the **trial-ledger artifact** (path + sha256 + git blob + freeze timestamp);
- the **inclusion rule** (which studies count toward DSR N and why);
- the **complete enumerated trial IDs** and the resulting **exact N**;
- **proof no post-freeze trial was added** (the ledger predates the sealed_at 2026-07-12 seal).

If the pre-freeze record genuinely cannot yield an exact defensible N, the owner must either (a)
rule the DSR ledger = A/B/C (N=3) with a written rationale that the "prior examined variants" clause
is not a countable DSR family, or (b) reconstruct/countersign an explicit trial ledger before
validation access. Either is an owner decision; the analyst must not choose N.

## Effect on v1.0.1

The v1.0.1 preregistration carries the corrected gate battery with **DSR N unbound** (this
blocker). DSR is a PREREQUISITE gate: the evaluator cannot compute it until N is bound. All other
gates are fully specified. Validation/OOS remain sealed; Workstream B remains stopped.
