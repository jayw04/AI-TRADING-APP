# Trading Workbench — P11 Operational Readiness Report (v0.1, DRAFT)

| Field | Value |
|---|---|
| Document version | **v0.1 — drafted at §5, attestation PENDING** (2026-06-20). The structure + evidence mapping land with §5 code/tests/docs; the **sustained-window attestation** (the PASS column) is filled only after ≥30 consecutive paper days. Until then this is the *template + current snapshot*, not the phase-close certificate. |
| Phase | **P11** — Operations & Reliability |
| Purpose | The phase-exit attestation (Direction §6): each operational capability is **operationally proven, not just coded.** All-PASS over the sustained window is the bar for `p11-complete`. |
| Governing | ADR 0021 (six-property contract), Direction v1.0 §6 (Definition of Done) |

---

## Executive summary (at-a-glance — filled at window close)

> *Snapshot 2026-06-20 (pre-window): code-complete, window not yet started — values below are
> the targets the window must hold, not yet attested.*

| | Status |
|---|---|
| **Operational readiness** | ☐ PASS (at window close) |
| Major incidents (P1/P2) | 0 |
| Recovery success | 100% (`recovery_success ÷ (success+failures)`) |
| Replay consistency | 100% |
| Reconciliation | PASS |
| Scheduler health | PASS |

## How to read this report

Each capability advances through **readiness levels** — the report records *maturity*, not a
binary:

```
Implemented ─▶ Tested ─▶ Operational ─▶ Proven   (Proven = ≥30 paper days, no unresolved P1/P2)
```

- **Implemented** — code on `main`.
- **Tested** — automated tests assert the behavior.
- **Operational** — running against the live paper book, emitting KPIs within target.
- **Proven** — sustained over the ≥30-day window with no unresolved P1/P2 incidents.

`p11-session5-complete` is tagged at **Tested/Operational**; `p11-complete` only at **Proven**.

### Recovery maturity trend (stability over time, not a single point)

The window demonstrates *sustained* health — each week's KPIs are recorded so "Proven" reflects a
trend, not one lucky snapshot (review fold):

| Week | Incidents (P1/P2) | Recovery success | Replay consistency | Scheduler | Status |
|---|---|---|---|---|---|
| Week 1 | — | — | — | — | ☐ |
| Week 2 | — | — | — | — | ☐ |
| Week 3 | — | — | — | — | ☐ |
| Week 4 | — | — | — | — | ☐ |
| **Close** | **0** | **100%** | **100%** | **PASS** | **☐ Proven** |

## Readiness table (snapshot 2026-06-20 — pre-window)

| Capability | Level (now) | PASS (at window close) | Evidence |
|---|---|---|---|
| **Replay** | Tested | ☐ | `replay_runs` rows `n_mismatched=0`; `tests/services/test_replay.py` |
| **Recovery (restart)** | Tested | ☐ | `tests/strategies/test_engine.py::test_resume_on_boot_no_double_act`; `recovery_*` metrics |
| **Recovery (partial-fill)** | Tested | ☐ | `tests/strategies/test_momentum_portfolio.py::test_overlay_partial_fill_converges_next_tick` |
| **Reconciliation** | Operational | ☐ | `reconciliation_runs` `result="pass"`; `tests/services/test_reconciliation.py` |
| **Alerts** | Operational | ☐ | `REPLAY_MISMATCH` / `RECONCILIATION_DISCREPANCY` audit + metric paths; on-call scenarios |
| **Scheduler reliability** | Operational | ☐ | §2 KPI dashboard, scheduler success > 99.9% |
| **Audit integrity** | Operational | ☐ | `scripts/verify_audit_integrity.py` clean |

*(PASS boxes are checked at window close, each against a concrete run/test/dashboard — never an
assertion.)*

## Exit-gate metrics (Definition of Done)

The window must hold **all** of these over ≥30 consecutive paper days:

| Exit metric | Gate | Source |
|---|---|---|
| Replay success | 100% | `replay_consistency_ratio` |
| Scheduler success | > 99.9% | `scheduler_job_events_total` |
| Duplicate executions | 0 | duplicate `order` rows (invariant) |
| Recovery tests (restart + partial-fill) | PASS | the §5 test suite |
| Reconciliation accuracy | 100% | `reconciliation_runs.result` |
| Fail-open detection | 100% | `overlay_actions_total{outcome="fail_open"}` observability |

## Incident log (P1/P2 must be zero/resolved at close)

| Date | Sev | Incident | Resolution | Status |
|---|---|---|---|---|
| — | — | *(none recorded yet)* | — | — |

## Recovery audit-trail model

Every recovery event answers four questions, sourced from existing telemetry (no new store):

| Question | Source |
|---|---|
| What failed? | the §2–§4 detecting signal (metric/audit) + the on-call severity |
| What recovered? | `recovery_*` metrics; resume-on-boot summary log; the converging actor tick |
| How long? | `recovery_duration_seconds` |
| Evidence? | `replay_runs` / `reconciliation_runs` / audit log row ids |

## Attestation (to be signed at phase close)

> On _________ (date), P11 is declared **operationally trustworthy**: the readiness table is
> all-PASS and the exit-gate metrics held over ≥30 consecutive paper days with no unresolved
> P1/P2 incidents. `p11-complete` tagged at `__________` (commit).

*Until signed, P11 is code-complete (`p11-session5-complete`) but not phase-complete.*
