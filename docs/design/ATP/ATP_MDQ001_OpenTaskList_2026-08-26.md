# ATP / MDQ-001 — Open Task List

| Field | Value |
|---|---|
| Document | **Task list for review.** Not a plan, not a governing record, not an authorization. |
| Date | 2026-08-26, **revised in place 2026-08-27** |
| Purpose | Enumerate what remains to be finished in the ATP / MDQ-001 design scope so the owner can confirm the direction before work resumes. |
| Governing plan | `docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_14.md` — **v0.14 remains the sole current plan.** This list does not supersede it and creates no v0.15. |
| Authority conveyed | **NONE.** Every item below is a candidate for work, not authorized work. The 2026-08-26 owner freeze stands. |
| Measurement stamp | Repository facts read from `origin/main` at **`379eca6`**, fetched 2026-08-26 ~15:45Z. Box facts read read-only via SSM at the timestamps given. A deployment SHA is a point-in-time reading, never a property of the box. |

---

## 0. Scope boundary — what this list deliberately excludes

**SEC-001 V3.1 is out of scope for this list and for this session.**

`docs/design/SEC-001 V3.1/TradingWorkbench_SEC001_V3_1_ClassificationLineage_Redesign_Design_Implementation_v1_2_FINAL.md`
(v1.2 FINAL, 2026-08-26) governs that program. Its work packages **WP0A - WP8** and gates
**0a, 0b, 1-8** are executed by a separate session, and its open design review is adjudicated there.
Nothing in this list authorizes, sequences, duplicates, or depends on any of them, and no MDQ/ATP item
below may be used to justify starting one.

The V3.1 design contains **zero references to MDQ, ATP, LOW-001 or DISC-001** (verified by search).
The programs are cleanly separable. The only coupling is bookkeeping, captured as task **D-3** below.

Also out of scope, unchanged from v0.14: reserve-strategy code before its gate opens; MR-002 work of
any kind (TERMINATED 2026-08-22 without an economic verdict); Phase-B streaming unless G10 is
separately opened; live-consumer cutover before the local-cache ADR.

---

## 1. Where things actually stand — 2026-08-27

### 1.1 Closed since this list was written

| Item | Outcome |
|---|---|
| 08-26 governed partition | ✅ **SEALED** — 395/395, EOD + freeze→verify→mirror, S3 custody verified independently |
| Corpus | **five sealed days**: 08-19, 08-20, 08-21, 08-25, 08-26 |
| D-2 / D-3 state sync + SEC-001 §J correction | ✅ merged (#692, squash `52cf292f…`) |
| E-1 runtime self-report repair | 🏁 **MERGED** — Amendment 8, #693 `50be5921…`, squash **`47715b4e…`**, run 1659 green on the exact pre-merge head. ⛔ Merging authorized nothing operational; the next owner gate is **DEPLOYMENT** |

### 1.2 Running now

**2026-08-27 acquisition** — three-proof standard met **under the pre-repair five-gate control** (READY 5/5 at 12:32:09Z and 13:14:46Z;
natural start proven by causality: timer `LastTriggerUSec` == service `ExecMainStartTimestamp` ==
09:25:01 EDT). ⛔ **Not a governed partition until** terminal completeness + EOD + freeze→verify→mirror
+ independent S3 custody verification.

⚠ Produced by the **deployed five-gate** control. It says nothing about deployment identity — the
`07a9233` / `ada7a5be…` divergence is still live and unrepaired by design.

### 1.3 ⭐ What changed in the plan, and why

The 08-26 list put **B-1 (build the K calculators)** first once the freeze lifted. The freeze did lift —
and the entire window since was consumed by the self-report repair, legitimately, under owner
authorization, after production falsified the declaration-only identity model. It grew from "extend one
module" into a 21-file governed Amendment.

**B-1 has still not started.** Meanwhile the deployment chain ahead of LOW-001 has grown to eight
serialized steps with owner checkpoints at several of them.

⇒ **The adjustment: B-1 no longer sits behind the deployment chain — it runs in parallel.** The
deployment chain has no deadline. The verdict does, and K1/K3 are the only deterministic path to it.

## 2. Critical path to the G3 verdict — the actual deliverable

This is the section that decides whether MDQ-001 produces a verdict or an expensive corpus.

**The window is fixed and the clock is running.** D0 = 2026-08-19. Review window
**[2026-08-19, 2026-10-18)**. Period holdout **2026-10-06 through 2026-10-17 inclusive** — the last 12
days are quarantined from all exploratory access. Corpus to date: **08-19, 08-20, 08-21, 08-25**, plus
08-26 in flight. Six trading days have elapsed since D0; five captured; 08-24 is the sole loss and is
closed as a non-event. 08-22 and 08-23 were the weekend — there is no unexplained gap.

| # | Task | State | Note |
|---|---|---|---|
| **B-1** | **Build the K1 / K3 / K5 / K6 calculators.** | **NOT BUILT** | Verified against `origin/main@379eca6`: `app/research/capture/admissibility.py` exists (this is what adjudicated D0), but **no K-value calculator module exists anywhere under `apps/backend/app/`**. This is the largest open engineering item in the scope and it is on the critical path. |
| **B-2** | Run the offline section 7.1 admissibility check **first**, per partition, then the calculators | not started | A K-value computed over an inadmissible partition is not evidence, it is a number. |
| **B-3** | Freeze K5's minimum admissible fill count `N_min` **before** evidence accrues | **CLOSED — verified frozen** | `N_min` = **50** is frozen at registration section 8 (sign-off block: `K5 minimum fills N_min: [X] 50`); section 157 confirms signing freezes the `N_min` floor, and section 8.4.3 re-affirms it unchanged. No action. The residual word *proposed* inside the signed checkbox is drafting residue, not an open choice. |
| **B-4** | K5 discrimination ruling — can K5 as frozen ever return FAIL, and does a non-discriminating PASS count toward the GO floor? | **CLOSED — verified SIGNED 2026-08-20**, registration section 8.4 | Both halves are answered, and more strongly than this list first assumed: **K5 as frozen cannot return FAIL** (no-quote fills are excluded from *both* numerator and denominator, so the ratio approaches 100% by construction), and section 8.4.2 item 4 rules that **a non-discriminating K5 PASS does not count toward the GO floor**. The PASS is preserved on the record; only its contribution is qualified. |
| **B-5** | Decide K2: it is **NOT EVALUABLE** in Phase A unless the owner opens **G10** and authorizes the bounded Phase-B streaming module inside the review window | owner decision | NOT EVALUABLE is neither FAIL nor a basis for GO, and per registration section 55 such criteria **leave the keep/cancel denominator entirely** — K2 cannot count toward Cancel either. Deciding late forecloses it. |
| **B-6** | **Verdict reachability — recompute the GO floor against what can actually be earned** | ⚠ **new, and raised by closing B-3/B-4** | See the arithmetic below. This is the item most worth an owner read today. |
| **B-7** | Continue corpus accrual on the governed collector identity; value-extraction outputs remain inadmissible to the MDQ verdict | ongoing | Sections 4.10.1, 7.2. |

### B-6 in full — the GO floor now rests on K1 and K3

The ratified floor is **at least 2 of K1-K6 both evaluable AND PASS**. Closing B-3 and B-4 against the
governed registration removes more of the field than the plan text makes obvious. **K2 and K4 are not
equivalent levers** and must not be described as if they were:

| Path | Current character | What can still change it |
|---|---|---|
| **K1** | **P0 load-bearing engineering** | Build the calculator/evaluator |
| **K3** | **P0 load-bearing engineering** | Build the calculator/evaluator |
| **K2 / G10** | **Owner-controlled expiring option** | Decide **and** implement Phase B early enough for 20 consecutive sessions |
| **K4 / Stage 0** | **Data-sufficiency-constrained expiring option** | Obtain a conforming dataset **and** reach a Stage-0 execution in-window |
| **K5** | **Reporting only for GO** | Nothing — foreclosed by signed section 8.4 |
| **K6** | **Event-contingent option** | A qualifying occurrence must naturally enter the corpus |

⚖ **Owner ruling 2026-08-26.** K2/G10 is opened by *decision*; K4 is bound by a *data-sufficiency
contract*. **The 250-trustworthy-PIT-event-day requirement may not be waived to rescue MDQ
evaluability.** The owner may prioritize work that could make Stage 0 feasible; **"open K4" is not an
available instruction.**

**Precise statement of the consequence** — the earlier absolute phrasing in this list overstated it,
because K2/K4/K6 have not yet irreversibly disappeared:

> Under the current state, if either K1 or K3 fails or is NOT EVALUABLE, GO becomes unreachable **unless
> at least one presently non-contributing path first becomes legitimately contributing in-window** — K2
> through a timely G10/Phase-B run, K4 through a conforming Stage-0 execution, or K6 through a naturally
> captured qualifying occurrence. **No such path may be created retroactively after its evidentiary
> window closes.**

#### B-6a — the K2 calendar is a hard, computed deadline

K2 requires **20 consecutive sessions**. The frozen review date is Sunday **2026-10-18**, so the last
usable session is Friday **2026-10-16**. There are **exactly 20 NYSE sessions from Monday 2026-09-21
through Friday 2026-10-16**, with no NYSE holiday inside the interval (Labor Day 09-07 precedes it;
NYSE trades Columbus Day 10-12). Verified by computation, not assumed.

⇒ **2026-09-21 is the absolute latest K2 measurement-start date**, and it carries **zero** implementation
or qualification slack. It is therefore **not** the decision date: a distinct **G10 owner-decision
deadline belongs in early-to-mid September.**

#### B-6b — ⚠ ruling needed BEFORE G10 is decided

Any 20-session window ending 10-16 necessarily overlaps the period holdout: **9 of the 20 sessions fall
inside 2026-10-06 through 10-17.** The overlap is unavoidable — the holdout is the tail of the review
window.

Reading the registration this appears to be a **non-conflict**: Ruling 4 defines the predicate as
`exploratory_access_allowed`, and the section 8.1 quarantine language is scoped to **discovery /
exploration**. Verdict computation of a frozen K criterion is not exploratory access.

⛔ **But the distinction is load-bearing and easy to invert.** If K2 measurement were treated as an
exploratory read, only 11 sessions would remain usable, **K2 would be structurally impossible**, the G10
lever would already be dead, and the 09-21 deadline moot. One explicit sentence of ruling now beats
discovering it in October.

**Direction question for review.** B-1 is unbuilt with roughly seven trading weeks left before the
holdout opens on 2026-10-06 — and B-6 shows K1 and K3 are very likely the *only* criteria that can
carry the verdict. That makes the K1 and K3 calculators not merely the largest item but the load-bearing
one. If the direction is right, B-1 should start as soon as the freeze lifts, ahead of any optional item
in sections 4 and 5, and K1/K3 should be built first within it.

---

## 3. Blocked on an owner ruling — not on work

| # | Task | Asked | State |
|---|---|---|---|
| **C-1** | **DISC-001 holdout-honouring question** | 2026-08-19, re-asked 2026-08-20 | still unanswered. Blocks the DISC-MDQ direction. |
| **C-2** | Broad DISC-MDQ feature library | — | **HELD** pending the repeated population census (census run 3/3: GAP 0, MOM-CORE 5, MOM-NEAR 0, OVERSOLD 0). Do not write feature code before the census populates. If families stay empty, disposition them NOT EVALUABLE rather than widening the universe post hoc. |
| **C-3** | Continue accumulating DISC snapshots and repeating the census | ongoing | The only sanctioned DISC-MDQ activity. |
| **C-4** | CEE — further sessions are **population-gated** | Session 001 CLOSED NOT EVALUABLE at n=17 | Median SIP-minus-IEX shortfall difference 0.00 bps implies tail suppression, not a level shift. No promotion. Cite *NBIS excluded 08-19* as embargo proof, never `denials=0`. |

---

## 4. Custody and governance debt

| # | Task | State | Note |
|---|---|---|---|
| **D-1** | Take the box wrapper `/opt/workbench/mdq/mdq_run.sh` and the three systemd units (`mdq-sample`, `mdq-eod`, `mdq-freeze`) into versioned custody | open — **confirmed absent from `origin/main`** | Owner: fold into the next ops-governance change, **not** a standalone PR. These files enforce the universe hash pin, the free-space floor and the slot grid, and none of them is in Git. |
| **D-2** | Apply the 2026-08-26 state sync to v0.14 in place | drafted this session | ONE CURRENT PLAN rule — no v0.15. |
| **D-3** | Correct v0.14 **section J** — it still describes SEC-001 V3 as an **ACTIVE crawl** with coverage token `5b26ffa2...` **UNSPENT** | stale and materially wrong | V3-RC is **STOP / REDESIGN**, the token is **SPENT / CONSUMED**, and V3.1 is the successor candidate whose design is under owner review with **WP0A not yet authorized**. Section J should carry a status correction and a pointer to the V3.1 design — **not** a copy of it, and not an account of its open review items. |
| **D-4** | Branch hygiene: on `research/mr002-validation2-lineage` the MDQ files are untracked and three local copies **differ** from the governed `origin/main` blobs — `MDQ-001_Rulings_2026-08-20.md`, `mdq_preflight_readiness.sh` (pre-review, lacks the `sha256sum` backslash fix), `mdq_collector.py` (pre-D0) | open hazard | Never hash or run the worktree copy; always read the `origin/main` blob. A stale local copy shadowing a governed file has already produced a wrong fingerprint once. |
| **D-5** | ABT canary citation — the controller `50541e29...` and the **37/37** figure remain **owner-provided, citation pending** | open | Add in place to v0.14 when the ABT record enters durable custody. Does not itself justify a new version. |

---

## 5. Cross-program — LOW-001, on HOLD

| # | Task | State |
|---|---|---|
| **E-1** | Runtime self-report repair — deploy it, then prove **three-source identity** | frozen until the partition seals |
| **E-2** | LOW-001 Run 2 (`run2_b3a_proof.sh`) | **HOLD** |

**The gate is conjunctive, not sequential.** Sealing the 08-26 partition does **not** release Run 2.
The activation-proof no-transition window opens only after E-1 is deployed *and* its three-source
identity is proven. This matters because leg 3 — the LOW-001 template — **does not self-report a
version**; on 2026-08-25 it was silent, and silence is not confirmation. Three-source identity is
therefore *currently unachievable by reading the box*; it requires E-1 to land first.

Today's 13:35-14:00Z Run-2 window closed unused. Strategy 8 remains IDLE; Dynamic PIT is CLOSED.

---

## 6. Dated deadlines — these expire whether or not we act

| Date | Sessions left (from 08-27) | Item | Consequence |
|---|---:|---|---|
| early-to-mid Sept | — | **G10 owner decision** | Later leaves no implementation slack before 09-21 |
| **2026-09-10** | 10 | Factor-refresh corroboration evidence **expires** | Regenerate or the stale-corroboration control loses its basis |
| **2026-09-21** | **17** | **Absolute latest K2 measurement start** | 09-21 → 10-16 is exactly 20 sessions. Start later and **K2 is foreclosed permanently** |
| **2026-10-05** | 27 | Last session before the period holdout opens | B-1 must be finished and exercised before it |
| **2026-10-16** | 36 | Last usable session in the review window | Friday; 10-18 is a Sunday |
| **2026-10-18** | — | Review window **closes** | The G3 verdict is computed on whatever corpus and calculators exist then |

⚠ Recomputed 2026-08-27 (Labor Day 09-07 excluded), not carried forward from the previous list.

## 7. Items I could not verify — confirm before acting on them

Stated as unverified rather than asserted, deliberately.

~~1. **B-3** — whether `N_min` for K5 is actually frozen in registration section 8.~~
**RESOLVED 2026-08-26** by reading the governed registration: frozen at **50**. See B-3.

~~2. **B-4** — whether the PX-2 ruling text answers both halves of the question.~~
**RESOLVED 2026-08-26**: signed 2026-08-20 at registration section 8.4, and it answers both halves —
K5 cannot FAIL, and its PASS does not count toward the GO floor. Consequence folded into **B-6**.

3. Whether any per-day governed record is expected for a **routine successful** capture day such as
   08-26, or whether the state sync plus the partition itself is the complete record. 08-25 got its own
   record (#684) because it was a **recovery**; 08-19, 08-20 and 08-21 did not.

---

## 8. Proposed order, for the owner to confirm or correct

```text
P0 - DEADLINE-BEARING, start now, in parallel with everything below
  B-1   build K1 and K3 calculators, run behind the section 7.1 admissibility check
  B-5   force the G10 decision onto the calendar   (17 sessions to 2026-09-21)
  K4    measure whether the data gap has ANY realistic closure path
        (the 250-event-day contract is NOT waivable - measure, do not "open")
  B-6b  rule holdout-scope vs K2 measurement BEFORE G10 is decided

P1 - SERIALIZED, no deadline, must not consume the calculator window
  #693 merged 47715b4e                         <- DONE
    -> separately authorized exact deployment  <- NEXT OWNER GATE
    -> verify the deployed control VERSION, then the first governing READY 6/6
    -> independently review + close the production deployment-identity evidence
    -> fresh no-transition window
    -> prospective S8.6 checks 1-12
    -> rollback-baseline restore iff genuine 12/12
    -> frozen B3a proof on the SAME runtime

P2
  D-1   wrapper + systemd units into versioned custody (fold into an ops-governance change)
  D-4   branch hygiene on research/mr002-validation2-lineage
```

**Why the order inverted.** The 08-26 list sequenced B-1 first and the repair second; the repair went
first because production forced it. Repeating that sequencing error would put the one deadline-bearing
deliverable behind the remaining deadline-free deployment chain and its owner checkpoints.

⛔⛔ **No post-deployment "READY 5/5" step exists.** Once the repaired control is deployed it **is** the
six-gate control; its governing verdict is `READY - all six gates pass`, and `--diagnostic` cannot emit
READY. Five-gate READYs in this record are pre-deployment evidence under the old control.

C-1 remains an owner ruling that can be issued at any point and blocks downstream DISC-MDQ work.
