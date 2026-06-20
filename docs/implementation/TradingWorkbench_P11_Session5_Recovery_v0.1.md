# Trading Workbench — P11 §5: Recovery Hardening + Phase Closeout

| Field | Value |
|---|---|
| Document version | **v0.2 — draft + review fold** (2026-06-20). Open questions (§"Open questions") still to confirm before execution. v0.1 was the draft; v0.2 folds the doc review (`comments.md`), all additive operational refinements: a **recovery state machine**, **recovery success criteria**, **recovery metrics/KPIs**, a **recovery timeline diagram**, a **recovery ownership** boundary, an **escalation column** on the incident ladder, **recovery readiness levels**, a consolidated **recovery invariants** block, a **recovery audit-trail** model, and an **evidence table** in the Readiness Report. Scope is unchanged — still prove-don't-rebuild, **no new subsystem** (the review explicitly affirms that restraint). |
| Date | 2026-06-20 |
| Phase | **P11** — Operations & Reliability (**final session**) |
| Session | §5 of 5 (Recovery hardening + phase closeout) |
| Predecessor | P11 §4 — Decision Replay (read-only verifier); merged `bb6d6b0` / PR #181, tag `p11-session4-complete` |
| Successor | **Phase close** — the Operational Readiness Report + a sustained ≥30-day paper window gate. Next phase is no longer *operations* but the **Institutional Platform** layer (deployment · multi-account · permissions · HA · scaling · administration — review's "Looking Beyond P11"); each is its own ADR/phase, out of scope here. |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Turn ADR 0021's last two phased properties — **3 (restart-recoverable)** and **6 (self-healing on partial application)** — from *asserted by construction* into *explicitly tested + runbooked*. Add the **reliability-test classes**, the **incident-severity ladder**, the **production-readiness checklist**, a **tested recovery runbook**, and the phase-closing **Operational Readiness Report**. **No new subsystem, no new persistence** — reuses `replay_runs` / `reconciliation_runs` / ops-state / the feature registry / the scheduler (ADR 0021: "no new subsystem yet"). |
| Estimated wall time | 6–9 hours (reliability test suite + any hardening fixes the tests surface + runbook + severity ladder + readiness checklist + the Readiness Report) |
| Tag on completion | `p11-session5-complete`, then `p11-complete` once the Readiness Report is all-PASS over the paper window |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

> **Recovery demonstrates that previously-implemented operational guarantees remain valid
> under failure conditions.** That one sentence captures the whole of §5: it adds no
> capability — it proves the capabilities already built stay correct when the process
> restarts, an order partially fills, or the broker blinks.

ADR 0021 named six properties every automated actor must satisfy and flagged some as
*phased*. P11 §1–§4 enforced and measured most of them: §2 (observability/idempotency
evidence), §3 (property 4, reconciliation), §4 (property 5, replay). **Two remain stated
more than they are proven:**

- **Property 3 — restart-recoverable.** All state lives in durable stores; on restart the
  scheduler re-registers its jobs and each actor resumes **without duplicate side effects.**
  The mechanism exists (lifespan resume-on-boot re-registers `ENGINE_RUNNABLE_STATUSES`
  strategies; jobs re-register each boot; `max_instances=1`/`coalesce`; the rebalance
  marks-on-attempt; fills are keyed by Alpaca `execution_id`). What's missing is a **test
  that proves a restart mid-cycle does not double-act**, and a **runbook** an operator can
  follow.
- **Property 6 — self-healing on partial application.** An action that partially applies
  (a re-size where only some orders fill) must **converge on a later tick**, never assume
  completion; the gap must be observable. §3 already *detects* the gap (the intent domain:
  `gross_target` vs achieved). What's missing is a **test that proves convergence** (the
  next cycle closes the gap rather than compounding it) and the operator guidance.

§5 is deliberately a **proving + documenting** session, not a building one. ADR 0021 is
explicit that recovery is *per-action discipline plus small shared helpers*, not a new
"Recovery Engine" (that's YAGNI until a second consumer needs shared order
diffing/batching/retry). So §5's output is mostly **tests, a tested runbook, and the
phase-closeout artifacts** — plus only the *minimal* hardening fixes the tests actually
surface.

### Guiding invariant (non-negotiable)

> **Recovery never adds an order path, and never auto-corrects.** Every order a recovering
> actor induces still flows through `OrderRouter.submit()` and the full risk engine (ADR
> 0002); a detected discrepancy alerts (ADR 0021 property 4), it does not silently emit a
> corrective order. Self-healing means *the actor's own next scheduled tick converges* — not
> a new out-of-band repair path. **Operations never changes investment decisions** (Direction
> §5): recovery makes the existing decision execute safely, it never picks a different trade.

### Fail-safe asymmetry (the recovery posture)

Recovery inherits ADR 0004's asymmetry: **a false stop is cheap, a false action can be
ruinous.** On any ambiguity during recovery — uncertain whether a cycle applied, broker
unreachable, fingerprint incomplete — the actor degrades toward *less* action (skip the
tick, re-evaluate next cycle), never toward re-firing. Restart-recovery that is unsure
**waits**; it never re-submits to "make sure."

### Recovery state machine (the operational lifecycle)

Every incident moves through one consistent lifecycle — the model dashboards, runbooks, and
the severity ladder all map onto:

```
Normal ─▶ Incident ─▶ Detection ─▶ Recovery ─▶ Verification ─▶ Operational
                       (§2–§4         (resume-      (replay /        (back to
                        signals)      on-boot /     reconcile        Normal,
                                      next tick)    confirms)        evidenced)
```

- **Detection** is the §2–§4 signals (a metric/audit/health change), never a human noticing.
- **Recovery** is the actor's own durable-state resume or next scheduled tick — **not** an
  out-of-band repair (the guiding invariant).
- **Verification** closes the loop: replay (§4) / reconciliation (§3) confirms the recovered
  state is correct *before* it is declared Operational.

**Recovery timeline (at a glance):**

```
Failure ─▶ Detection ─▶ Alert ─▶ Next scheduled tick ─▶ Verification ─▶ Healthy
```

### Recovery ownership (crisp boundary)

- **Recovery owns:** *restart* (resume from durable state), *convergence* (close the
  partial-fill gap next tick), *validation* (verify the recovered state), *monitoring*
  (surface incidents).
- **Recovery does NOT own:** *strategy decisions*, *portfolio allocation*, or *order
  generation* — those are the alpha/portfolio layers (Direction §5: Operations never changes
  investment decisions). Recovery makes the existing decision execute safely; it never picks
  a different trade.

### Recovery invariants (the consolidated reference)

Every recovery path upholds all five — the single place an operator or reviewer can check the
guarantees:

1. **Never duplicate orders** (idempotency: single-flight + mark-on-attempt + `execution_id`).
2. **Never bypass `OrderRouter`** (ADR 0002 — recovery induces no out-of-band order path).
3. **Never auto-remediate** (ADR 0021 property 4 — detect + alert; the owner acts).
4. **Never modify audit history** (the hash-chained log is evidence, append-only).
5. **Always converge through scheduled execution** (self-heal = the actor's own next tick).

## What this session ships

1. **Restart-recovery test suite** — proves property 3: a backend restart mid-cycle
   re-registers strategies + jobs from durable state and **does not double-act** (no
   duplicate rebalance, no duplicate overlay re-size, no duplicate breaker action). Exercises
   the idempotency guards (`max_instances=1`/`coalesce`, mark-on-attempt, `execution_id`
   fill keying) under a simulated restart.
2. **Partial-fill self-heal test suite** — proves property 6: a re-size whose orders only
   partially fill leaves an observable intended-vs-achieved gap (§3 intent domain) and the
   **next cycle converges** the book toward target rather than assuming completion or
   compounding the gap.
3. **Reliability-test classes** — a named taxonomy (chaos · restart · recovery · replay ·
   failover) documenting what each class covers, which §5 implements, and which are
   explicitly deferred (with the reason).
4. **Incident-severity ladder** (P1–P4) — P1 duplicate order · P2 broker mismatch · P3
   replay failure · P4 delayed scheduler — each mapped to its detecting signal (§2–§4
   metric/audit), operator response, and runbook scenario.
5. **Tested recovery runbook** (`docs/runbook/recovery.md`) — restart and partial-fill
   procedures **validated by being followed**; plus the severity ladder and the
   production-readiness checklist.
6. **Operational Readiness Report** (`docs/implementation/TradingWorkbench_P11_OperationalReadinessReport_v0.1.md`)
   — the one-page phase-exit attestation (Replay · Recovery · Reconciliation · Alerts ·
   Scheduler · Audit, each PASS/FAIL) + the Definition-of-Done exit-gate metrics.
7. **Recovery metrics** (additive Prometheus, not a subsystem) — `recovery_attempts_total`,
   `recovery_success_total`, `recovery_failures_total`, and a `recovery_duration_seconds`
   histogram, emitted by the existing restart/convergence paths (resume-on-boot + the
   convergence tick). They make recovery *measurable over time* using §2's metric conventions;
   no new persistence — trends derive from these counters. A `recovery` KPI row joins the §2
   dashboard (Restart PASS · Convergence PASS · Replay PASS · Scheduler PASS).
8. **Recovery success criteria** (per recovery type — complements PASS/FAIL): the explicit
   definition of "recovered" the tests assert against (table below).
9. **Minimal hardening fixes** — only what the tests surface (e.g. a missing guard or a
   non-idempotent edge). Risk-adjacent → the ≥95% coverage bar; each fix audit-logged if
   consequential.

### Recovery success criteria (what "recovered" means)

| Recovery type | Success criterion (the test asserts) |
|---|---|
| **Restart** | no duplicate execution (no re-fired rebalance / re-size / breaker action; no dup `order` rows) |
| **Partial fill** | the intended-vs-achieved gap is **reduced** on the next cycle (converges, never compounds) |
| **Scheduler** | all jobs restored single-flight on boot (resume-on-boot re-registers; no stale/missing job) |
| **Replay** | no mismatch (`replay_consistency_ratio == 1.0` over the recovered window) |
| **Reconciliation** | no unresolved discrepancy (broker ⇄ local aligned, or the drift is owner-acknowledged) |

## Prerequisites

- **P11 §1–§4 merged**: the feature registry + ops-state (§1), `automation_runs_total` +
  measured health (§2), `reconciliation_runs` + the **intent domain** (§3, the partial-fill
  *detector* §5's convergence test builds on), `replay_runs` + the replay verifier (§4).
- The existing restart machinery: lifespan resume-on-boot (`ENGINE_RUNNABLE_STATUSES`),
  per-boot job re-registration, single-flight scheduling, the rebalance mark-on-attempt
  guard, and `fills.execution_id` idempotency.
- ADR 0021 **accepted** (it is — 2026-06-19); ADR 0002 (single router), ADR 0004 (breaker).

## ADR 0021 property coverage at end of P11 (the closeout map)

| Property | Enforced by | Status entering §5 |
|---|---|---|
| 1. Idempotent within period | single-flight + mark-on-attempt | ✅ (evidence §2) |
| 2. Fail-safe, never fail-dangerous | overlay fail-open / breaker-only-halts | ✅ (evidence §2) |
| 3. **Restart-recoverable** | durable state + resume-on-boot | **§5 proves + runbooks** |
| 4. Reconciled against broker truth | §3 reconciliation (alert-only) | ✅ (§3) |
| 5. Replayable | §4 replay verifier | ✅ (§4) |
| 6. **Self-healing on partial application** | converge-next-tick + §3 intent gap | **§5 proves + runbooks** |

§5 closes the two bold rows → all six properties move from *asserted* to *enforced +
measured + tested*.

## Reliability-test classes (the taxonomy)

A **test class** is a category of failure-injection; naming them keeps "we tested recovery"
honest about *what* was tested. §5 scopes them deliberately:

| Class | Injects | §5? | Notes |
|---|---|---|---|
| **Restart** | process restart mid-cycle | ✅ | property 3 — the core §5 build |
| **Recovery** | resume from durable state, assert no double-act | ✅ | property 3 — the assertion half |
| **Replay** | re-verify decisions post-incident | ✅ (reuse §4) | the CLI is the post-incident tool |
| **Chaos** | random broker/data outage during a cycle | partial | fault-injection at the adapter seam in tests (fail-open path); **not** in production |
| **Failover** | swap to a standby instance | ❌ deferred | the platform is single-instance/local-first; no standby exists (would be its own ADR) |

Each in-scope class trades to an objective goal (§0: Recoverable). Out-of-scope classes are
named so their absence is explicit, not silently assumed covered.

## Incident-severity ladder

The operator's triage map — each severity ties a *symptom* to its *detecting signal* (built
in §2–§4) and a *runbook scenario*:

| Sev | Incident | Detecting signal | Response | Escalation |
|---|---|---|---|---|
| **P1** | **Duplicate order / double-act** | `automation_runs` double-fire; `skip_idempotent` absent; duplicate `order` rows | **Stop-and-investigate.** Halt the actor; confirm the idempotency guard; reconcile (§3); never assume self-correct. | **Immediate** operator intervention |
| **P2** | **Broker ⇄ local mismatch** | `reconciliation_discrepancies_total` (§3); `RECONCILIATION_DISCREPANCY` audit | Investigate via §3 runbook; reconcile manually; **never auto-fix**. | **Same business day** |
| **P3** | **Replay failure / mismatch** | `replay_verifications_total{verdict="mismatch"}` (§4); `REPLAY_MISMATCH` audit | Fix the *producing* code path (§4 runbook); never edit the audit log. | **Next scheduled maintenance** |
| **P4** | **Delayed / missed scheduler tick** | scheduler success < 99.9% (§2); stale-job health | Check Docker/host; resume-on-boot re-registers; converge next cycle. | **Monitor only** |

The Definition of Done requires **no unresolved P1/P2** over the ≥30-day paper window.

## Detailed work

### §A — Restart-recovery tests (property 3)

- **No-double-act across restart.** Drive an actor to mid-cycle, simulate a restart
  (re-run the resume-on-boot path against the durable state), assert: strategies re-register
  from `ENGINE_RUNNABLE_STATUSES`; jobs re-register single-flight; **the same period's work
  does not re-execute** (the weekly rebalance mark-on-attempt holds; the overlay's
  already-applied guard holds; no duplicate `order` rows).
- **Resume is best-effort.** One broken strategy on boot logs `strategy_resume_failed_on_boot`
  and does not abort the others or the boot (existing behavior — pinned by test).
- **Fill idempotency.** A fill re-delivered after restart (same Alpaca `execution_id`) does
  not create a duplicate `fills` row (existing unique key — pinned by test).

### §B — Partial-fill self-heal tests (property 6)

- **Gap is observable.** A re-size where only some orders fill → §3 intent domain reports
  `gross_drift` (intended `gross_target` vs achieved) — the gap is *recorded*, never silently
  treated as complete.
- **Convergence, not compounding.** The actor's **next** scheduled tick moves the book
  *toward* target from the partially-applied state (turnover/hysteresis respected), and a
  fully-applied state is a no-op (idempotent) — not a re-trade. Assert the gap shrinks across
  ticks rather than oscillating or doubling.
- **Fail-safe under outage mid-fill.** If the broker goes unreachable between orders, the
  actor degrades toward less action (skips, re-evaluates next tick) — it never re-submits to
  force completion.

### §C — Reliability-test classes + chaos seam

Implement the restart/recovery/replay classes (§A/§B + the §4 CLI). For **chaos**, add a
fault-injection seam *in tests only* at the broker-adapter boundary (raise/timeout on a
fraction of calls) to exercise the fail-open paths; document that chaos is a test construct,
never enabled against a live book.

### §D — Incident-severity ladder + runbook scenarios

Encode the P1–P4 ladder above; each severity gets (or links) an on-call scenario. P3/P2
already have scenarios (§4/§3); add **P1 (duplicate order)** and **P4 (delayed scheduler)**
scenarios. (No new `AuditAction` is expected; if a fix in §7 adds one, the AuditAction→
playbook invariant applies.)

### §E — Tested recovery runbook (`docs/runbook/recovery.md`)

The restart and partial-fill procedures, **tested by being followed** (CLAUDE.md: runbooks
are tested by following them). Each procedure: symptom → check (which §2–§4 signal) →
action → verification. Cross-links the §3/§4 on-call scenarios and the severity ladder.

### §F — Production-readiness checklist

A per-automated-actor checklist (code · tests · metrics · replay · runbook · alert ·
dashboard) — the bar a new automated actor must clear before it ships. Lives in the runbook;
referenced by the Readiness Report.

### §G — Operational Readiness Report (phase closeout)

The one-page attestation (Direction §6): Replay · Recovery · Reconciliation · Alerts ·
Scheduler · Audit each PASS/FAIL, plus the exit-gate metrics (replay 100% · scheduler >99.9%
· duplicate-exec 0 · recovery tests PASS · reconciliation 100% · fail-open detection 100%).
**All-PASS sustained over ≥30 consecutive paper days with no unresolved P1/P2** is the bar
for `p11-complete` — distinct from `p11-session5-complete` (the code/tests/docs land first;
the report's sustained-window attestation closes the phase).

**Readiness levels (not just PASS).** Each capability advances through a state, so the report
records *maturity*, not a binary — the sustained paper window is what earns the top level:

```
Implemented ─▶ Tested ─▶ Operational ─▶ Proven  (after ≥30 paper days, no unresolved P1/P2)
```

**Evidence table (audit-friendly).** Every PASS cites the artifact that backs it, so an
auditor can trace the claim — not take it on faith:

| Item | Evidence (example) |
|---|---|
| Replay | `replay_runs` #25 (`n_mismatched=0`) |
| Restart | recovery test `#14` (no double-act) |
| Partial fill | recovery test `#15` (gap reduced next cycle) |
| Scheduler | §2 KPI dashboard (success > 99.9%) |
| Reconciliation | `reconciliation_runs` #82 (no unresolved discrepancy) |
| Audit | `verify_audit_integrity.py` clean |

**Recovery audit-trail model.** Every recovery event answers four questions — *what failed ·
what recovered · how long · evidence* — sourced from the existing telemetry
(`recovery_*` metrics + the §3/§4 run tables + audit log), so the model is defined now even
where a richer record lands later. No new audit action is added unless a §9 hardening fix
needs one.

### §H — Recovery metrics

Add `recovery_attempts_total`, `recovery_success_total`, `recovery_failures_total`, and a
`recovery_duration_seconds` histogram (§2 buckets), emitted by the resume-on-boot path and
the convergence tick. These are **additive observability** (Prometheus counters, ADR 0021 "no
new subsystem"), feeding the `recovery` KPI row and the trend view. A recovery "event" is
bounded explicitly (a restart-resume pass; a convergence cycle that closed a non-zero gap) so
`success`/`failure` are well-defined, not hand-wavy.

## Manual smoke

1. **Restart no-double-act:** with a strategy ACTIVE mid-week, restart the backend → it
   resumes (`strategy_registered`), the weekly rebalance does **not** re-fire (mark-on-attempt
   held), no duplicate `order` rows, `/ops/state` healthy.
2. **Partial-fill convergence:** simulate a re-size partial fill → §3 reports the intent gap;
   the next cycle reduces it; a clean state is a no-op. **No orders outside `OrderRouter`.**
3. **Readiness Report:** run the §2–§4 KPIs over a paper window → fill the report; confirm
   each row's PASS is backed by a metric/test, not an assertion.

## Walk-away discipline

**≥ 2 hours.** §5 is risk-adjacent (it exercises the order-inducing actors' restart and
partial-fill behavior and must provably never double-act or auto-correct) and closes the
phase. Any hardening fix touches the automation/idempotency seam → audit/risk bar + ≥95%
coverage on changed risk-adjacent code.

## What this session does NOT do

- **No Recovery/Execution subsystem** — ADR 0021 is explicit this is per-action discipline +
  small helpers until a second consumer needs shared order diffing/batching/retry. §5 tests
  and documents; it does not build a new engine.
- **No new persistence** — reuses `replay_runs` / `reconciliation_runs` / ops-state / the
  feature registry / the scheduler.
- **No auto-remediation** — recovery self-heals via the actor's *own next tick* + alert-only
  reconciliation; it never adds an out-of-band corrective order path (a bounded, owner-gated
  auto-remediation remains a future ADR — ADR 0021 re-evaluation trigger).
- **No failover / HA** — single-instance/local-first; a standby is its own ADR + phase.
- **No production chaos** — fault injection is a test-only construct at the adapter seam.
- **No enabling of the default-off overlays** — §5 makes operation *safe + proven*, not
  *enabled*; enabling stays a separate backtest-gated owner decision (§5 overlay = NO-GO).
- **No order/risk-engine change, no new external dependency.**

## Open questions — to confirm before execution

1. **Restart simulation depth** — re-invoke the resume-on-boot code path against a seeded
   durable state (cheaper, deterministic, no container churn), vs. an integration test that
   actually restarts the backend container? *Lean: the code-path re-invocation for CI
   determinism, + one documented manual container-restart smoke in the runbook.*
2. **Partial-fill modeling** — drive convergence through the real overlay/rebalance logic
   with a stub broker that fills a configurable fraction, vs. a synthetic gap injected at the
   intent layer? *Lean: stub-broker fractional fill, so the convergence is proven through the
   real diff/turnover code, not a synthetic shortcut.*
3. **`p11-session5-complete` vs `p11-complete`** — tag §5 when code/tests/docs land, and tag
   the phase only after the ≥30-day all-PASS paper window? *Lean: yes — two tags; the report
   is drafted at §5 and attested at phase close so "done" stays evidence-backed, not asserted.*
4. **Chaos scope** — broker-adapter fault injection only, or also data-source (factor store)
   outage? *Lean: broker-adapter for §5 (the order-inducing seam); data-source fail-open is
   already covered by the regime-filter fail-open tests.*

## Notes & gotchas

1. **Prove, don't rebuild.** The recovery mechanisms mostly already exist (resume-on-boot,
   single-flight, mark-on-attempt, `execution_id`). §5's value is the *test that proves they
   hold under restart/partial-fill* + the *runbook* — resist the urge to refactor the
   machinery; only fix what a test actually catches.
2. **Self-heal = next tick, never a repair path.** Convergence is the actor re-evaluating on
   its own schedule from durable state. The moment "self-heal" becomes an out-of-band order,
   it is an un-gated automated order path — exactly what ADR 0021/0002 forbid.
3. **Idempotency is the load-bearing property.** Restart-recovery is *safe* only because
   re-fires are no-ops (property 1). The restart tests are really idempotency tests under a
   restart; if a fix is needed, it is almost always "add/repair an already-applied guard,"
   not "add restart logic."
4. **Two tags, one phase.** `p11-session5-complete` is code-complete; `p11-complete` waits on
   the sustained paper window. Don't conflate them — the Readiness Report's credibility is the
   sustained-window evidence.
5. **`docs/` vs `Docs/` git-add case quirk** (bit §1–§4): the tracked path is lowercase
   `docs/`; verify `git diff --cached --name-only` before committing the runbook + this doc +
   the Readiness Report.
6. **Runbooks are tested by being followed** (CLAUDE.md): the recovery runbook is not done
   until someone (or a test) has executed each procedure end-to-end.
