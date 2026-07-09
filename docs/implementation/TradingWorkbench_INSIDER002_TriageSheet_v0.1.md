# INSIDER-002 — EAD Dataset Triage Sheet (v0.1)

**Date:** 2026-07-09 · **Owner:** Jay Wang · **Status:** Triage recorded — **Reserved** (see Outcome).
**Per the triage gate** (`TradingWorkbench_EAD_DatasetTriage_v0.2.md`): sheet committed before any
study; **no pre-registration is frozen and no study runs** until the trigger below fires.

---

## The one-page triage

```
Dataset:            SEC EDGAR Form 4 exec/officer OPEN-MARKET purchases (code P) — already ingested
                    natively (INSIDER-001 §1: app/altdata/sec/, PIT Event Store, CAP-015/016/017).
                    No new vendor, no new dataset — a NEW HYPOTHESIS over an owned dataset.

Mechanism:          CONFIRMATION / CONDITIONING, not standalone drift. INSIDER-001 rejected
                    "insiders bought → drift" (beta, not alpha). INSIDER-002 asks a different
                    question: does insider buying IMPROVE SELECTION when it CONFIRMS an
                    already-qualified candidate — e.g. (1) existing price momentum, (2) liquidity
                    expansion, (3) post-disclosure price confirmation, (4) cluster/role/materiality
                    filters? The tradable unit is the momentum/microcap candidate; insider activity
                    is a conditioning variable. ⚠ HONEST PRIOR NOTE: this is a *conditional* pass
                    of the distinct-mechanism gate — if the study design degenerates to "insiders
                    bought, so buy" (insider as the selector rather than the conditioner), the
                    mechanism collapses into the rejected class and the gate VETOES it. The frozen
                    pre-registration must make the conditioning structure explicit and testable
                    (candidate set defined WITHOUT insider data; insider only splits it).

PIT anchor:         EDGAR acceptance timestamp (filed_at) — proven trustworthy in INSIDER-001;
                    the Event Store's events_asof() already enforces it. STRONG PASS.

License:            SEC EDGAR is public/free for research AND product use. PASS (commercial path
                    also clean — soft gate 7 satisfied).

Expected sample:    INSIDER-001 processed 2,148 Form 4 buy-events over the 134-name universe →
                    487 conviction hits. The platform now has the DCAP-008 broad small-cap
                    universe (9,040 tickers) and full-universe EDGAR ingestion, so the raw event
                    count is far larger; the binding filter is the INTERSECTION with the
                    momentum/liquidity candidate set. ≥100 benchmarked intersection events is
                    plausible but NOT yet verified — the pre-registration must include a
                    sample-size feasibility check as its first (cheap, data-only) step, and the
                    study does not proceed if the intersection can't reach the gate. PASS
                    (conditional on the feasibility step). OWNER-REQUIRED (2026-07-09 review):
                    before ANY INSIDER-002 study begins, run a feasibility check estimating the
                    intersection count between (1) the qualified NON-insider candidate pool and
                    (2) the insider-confirmed subset; if it cannot plausibly reach >=100
                    benchmarked observations, no full study runs.

Identity mapping:   Security Master (CAP-024) resolution already wired into the Event Store
                    (resolved_security_id). PASS.

Harness type:       Event-study (matched-control engine, reused wholesale from
                    GOVCONTRACT/CONGRESS/LOBBY) with one extension: controls must be matched
                    WITHIN the qualified-candidate set (candidates without insider confirmation),
                    not the broad universe — otherwise the test degenerates back to INSIDER-001.
                    Existing harness fits; the control-pool restriction is a parameter, not a new
                    framework. PASS.

Prior:              LOW and honestly stated: four disclosure-event programs (incl. INSIDER-001
                    itself) rejected with the same "one finding." The counter-prior is specific:
                    conditioning ≠ selection — a signal with no standalone mean effect can still
                    have interaction value inside an already-selected pool. That is a genuinely
                    different statistical claim, untested by INSIDER-001 (which benchmarked
                    against the basket, not within a momentum-qualified pool). Modal expected
                    outcome remains Rejected; the study is worth one shot ONLY because the
                    interaction claim is distinct and the data is free/owned.

Outcome:            RESERVED. All four hard gates pass (mechanism conditionally — see above),
                    but per the locked Strategy Production Sprint sequencing (v0.4) and the
                    2026-07-09 owner decision: (a) do NOT freeze a pre-registration now;
                    (b) TRIGGER = the GAPPER-001 locked replay verdict lands (~early Aug 2026);
                    (c) on trigger, the owner decides whether INSIDER-002 deserves full
                    execution; only then is a pre-registration drafted and frozen.
                    Until then insider data remains rejected_reference_only everywhere.
```

---

## Relationship to the Insider Reference Monitor (product surface)

The **Insider Reference Monitor** (onboarded separately, 2026-07-09) is a *display-only context
surface* under the `rejected_reference_only` invariant. It is NOT part of INSIDER-002 and needs no
triage: the invariant explicitly allows rejected datasets as reference/context. Nothing the monitor
shows may feed ranking, sizing, portfolio construction, or the order path. If INSIDER-002 is later
approved and validated, that changes; until then the monitor's data path and the trading path stay
disjoint (enforced by `app/altdata/reference_only.py` + `check_reference_only_invariant.sh`).
