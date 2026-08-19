# MR-002 Gate N1 — Adjudication Addendum v1.0

**Program:** MR-002 / SPQ-1 · **Gate:** N1 · **Date:** 2026-08-19
**Amends:** `MR002_N1_ProspectiveRegistration_v1.0`, SEALED identity
`7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af`
**Status:** owner-adjudicated. Binding on the N1 rerun.

---

## 0. What this addendum is

Three interpretation questions surfaced during N1 execution that the sealed registration did not
settle, plus one conditional selection ruling. The owner adjudicated them on 2026-08-19. This
addendum codifies that adjudication **before** the clean rerun, so the wording cannot be
reinterpreted afterwards against the numbers.

It changes **no** solver profile, **no** candidate set, **no** criterion, and **no** corpus. It
creates no new registration. The sealed registration stands; this records how three of its clauses
are to be read, and one discretionary choice the registration itself reserved to the owner.

**The provisional run of 2026-08-19 is superseded.** It is retained as engineering evidence marked
`PROVISIONAL_N1_EXECUTION`, and it is **not** the formal N1 execution.

---

## 1. D1 — provenance of a generator's terminal condition · **ACCEPTED**

### The defect

Sealed §2.5.2 assigns library provenance to "a frame whose module resolves under a registered
solver-library root". Measured: for PIQP and Clarabel **no such frame ever exists** — both surface
their terminal status by raising from a thin wrapper of ours
(`scripts.mr002_piqp.solve_piqp`, `scripts.mr002_characterize_native_qp.solve_clarabel`). Read
literally, every one of their terminations becomes `WRAPPER_ORIGIN` → `SYSTEM_INTEGRITY_DEFECT` →
`INVALID_RUN`, and **all three candidates fail C1** — the 12:49Z failure reproduced by
specification, for a reason unrelated to solver quality.

### The ruling

> Library-boundary status provenance is the operative interpretation.

### Required mechanics (binding)

1. A recognized terminal status **must be read from the library's enum/status object, never from
   message text.**
2. The explicit registered boundary **belongs to the frozen solver profile** — it is profile
   configuration, and adding to it after observing a failure is a profile change, prohibited on the
   same footing as retuning `max_iter`.
3. An exception owned by **our** code → `SYSTEM_INTEGRITY_DEFECT`.
4. A **solver-owned** terminal condition → `NO_CERTIFIED_CANDIDATE`.
5. Unattributable provenance → `UNREGISTERED_TERMINATION_REASON`.
6. **Zero unregistered reasons remains mandatory for advancement.**

Mechanic 3 is the one that must not erode: the sealed record exists precisely to prevent the
opposite error — silently downgrading our own wrapper bugs into ordinary solver failures.

---

## 2. D3 — canonical shuffle invariance · **ACCEPTED as method-level bounded invariance**

### The defect

Sealed C0 requires candidates to be "canonically shuffle-invariant" and C4 requires "byte-identical".
Measured: **no** generator is byte-identical under coordinate permutation — **including Solver A**
(285 exact of 11,667 permuted solves). Under the literal reading the admissible set is **empty** and
N1 cannot select any Solver B, for a property unrelated to the economic solution.

### The ruling — codified wording

> **Canonical shuffle invariance is a method-semantic property, evaluated under the
> already-registered equivalence machinery, not bitwise equality of standalone solver internals.**

Precisely:

1. Repeated execution with identical canonical input and environment **must remain byte-deterministic
   where the registration explicitly requires byte determinism.**
2. **Coordinate permutation may alter floating arithmetic.**
3. After canonical unpermutation, the **accepted method disposition** and the **accepted economic
   allocation** must remain **equivalent under the registered bound**.
4. Standalone **B** differences on instances where **A certifies** — so B cannot affect production —
   are **diagnostic, not a method failure**.
5. **Where B is actually decisive** because A produces no certified candidate, permutation of that
   instance **must not alter the method disposition or the accepted allocation beyond the bound.**

### Measurement obligation created by clause 5

Clause 5 is a **separate condition**, not a consequence of the aggregate. The provisional run
reported method-level disposition changes only in aggregate (13 across ~11,700 permuted cascade
runs) without isolating the B-decisive instances. The rerun **must** report, separately:

- `B_decisive_instances` — instances where A produces no certified candidate;
- `B_decisive_disposition_changed` — of those, how many change disposition under permutation
  (**must be 0**);
- `B_decisive_allocation_beyond_bound` — of those, how many change accepted allocation beyond the
  registered bound (**must be 0**);
- the aggregate figures, retained as diagnostic context under clause 4.

Clauses 1–3 are evaluated exactly as the provisional run did; only the reporting granularity for
clause 5 is new.

---

## 3. Condition 8 — the authoritative v1 baseline · **RULED**

### The ambiguity

§4.4 requires the regenerated v1 dispositions to reproduce "the recorded" ones exactly. Two records
exist and **disagree with each other by one instance**, independently of anything N1 did:

| Record | Result | What it is |
|---|---|---|
| `MR002_Stage3FallbackSelection_Audit_v1.0.json` | `F_Q` = 5 rows {800, 1328, 2140, 2296, 2765} ⇒ 3890 / 5 | a **fallback-candidate-selection** bakeoff; P2 won under the old conditional-coverage + standalone tiebreak |
| `MR002_Stage3_GovernedDevQualification_v1.0.json` | 3891 / 4 | the **governed v1 development qualification** |

### The ruling

> **§4.4 asks what the v1 METHOD ACCEPTED. The authoritative referent is therefore the governed v1
> development qualification, 3891 PRIMARY_QUALIFIED / 4 FALLBACK_QUALIFIED.** The bakeoff was a
> candidate-selection artifact and is not the preservation baseline.

### Prohibited

> "Both records exist; choose 3890/5 because N1 currently reproduces it."

The one differing row **must not** be adjusted to make the numbers agree.

### Required reconciliation (development-only)

1. Identify the exact differing instance.
2. Identify the exact pushed source / runtime / certifier identities used by the governed 3891/4
   qualification.
3. Reproduce that instance under those exact identities.
4. Determine whether the governed 3891/4 record **is reproducible**, or whether it contains a
   **demonstrable record-generation defect**.

If 3891/4 reproduces under its bound identities, that is the v1 baseline and N1 compares against it.
If independent immutable evidence proves the governed record erroneous, a **formal correction record
is written first**; only then may 3890/5 become the corrected baseline.

No validation or OOS information is needed or authorized for any of this.

### Reconciliation OUTCOME (executed 2026-08-19)

**The governed 3891/4 record reproduces EXACTLY. There is no record-generation defect, and no
correction record is required.**

Replaying the development window with Stage-3 routed through the countersigned v1 seam — the
governed qualification's own device, with observation added and nothing re-derived:

| config | invocations | reproduced | governed | match |
|---|---|---|---|---|
| A | 1427 | 1426 P / 1 F | 1426 P / 1 F | **yes** |
| B | 1535 | 1532 P / 3 F | 1532 P / 3 F | **yes** |
| C | 933 | 933 P / 0 F | 933 P / 0 F | **yes** |
| **total** | **3895** | **3891 P / 4 F** | **3891 P / 4 F** | **yes** |

Supporting identity check: the runner hash recorded by the governed qualification
(`b1f990e2…`, 24,002 bytes) is the **CRLF rendering of the same file** whose LF Git blob is
`57d0fcac…` (23,453 bytes) — representation-only, **zero content drift**, consistent with the
2026-08-18 source-identity correction. The runner is not implicated.

### Why both records were honest — the finding that matters

**The two records were never measuring the same instances.**

| | population |
|---|---|
| bakeoff corpus (registered, hash `1d23193…`) | instances produced by the **selection capture device** (raw → sqrt → tscaled, then an LP diagnostic) |
| governed qualification | instances produced by the **v1 cascade itself** (QUADPROG_SQRT → PIQP_P2) |

Each device's accepted point feeds forward into the next session's state, so the sequences diverge.
Measured overlap:

- config A: **1171 of 1427 (82%)** of the replay's instances do **not** occur in the bakeoff corpus
- config B: **1417 of 1535 (92%)**
- config C: **274 of 933 (29%)**
- **overall: 2862 of 3895 = 73% disjoint**

All four v1 fallback invocations in the replay land on instances **absent from the bakeoff corpus**.

So 3890/5 and 3891/4 are both correct, about different populations. Neither is defective, and the
one-instance difference was never a reproduction failure.

> **Neither record is called wrong.** The fallback-selection audit and the governed development
> qualification are **not interchangeable preservation referents**. The former governs N1
> candidate-selection evidence; the latter governs v1-method preservation. Differences between their
> decisive Stage-3 instances do not by themselves constitute a contradiction.

Whether any genuine **within-replay** mismatch remains is a question the clean rerun answers. Until
it does, the historical discrepancy is attributed to comparing different evidence populations and
purposes — not to a defect in either record.

### Evidence hierarchy

| Selection evidence | Preservation evidence |
|---|---|
| frozen 3,895-instance Stage-3 corpus | governed development replay |
| C1–C6 | regenerated v1 baseline under its exact bound identities |
| standalone and cascade generator behaviour | v2 replay under the pushed implementation |
| A / B / R certificate agreement | allocation and disposition equivalence, session by session |
| bakeoff equivalence evidence, **including the 3892 trivial + 3 by-bound result**, retained as valid and scoped | downstream A/B/C economic reconciliation |

The 3892+3 result is **retained, not marked erroneous**. It is valid evidence about v1/v2 equivalence
*within the bakeoff population*. It simply does not carry the stronger claim that v2 preserves the
governed v1 development replay.

### ⛔ The selection / preservation firewall

> **Solver B is selected using the sealed N1 selection rule ONLY.** Preservation then asks whether
> that already-selected method is behaviour-preserving. The preservation replay **must not** modify
> the selection result.

If preservation fails, the result is **not** "pick a different B based on replay returns." It is:

> **N1 cannot advance under the selected method.**

Selecting a solver on replay economics would be selecting on returns, which is precisely what the
program's prohibition on using historical returns to choose Solver B forbids.

### Consequence for the rerun — the two gates run on different populations

- **Selection (C0, C1–C6)** stays on the frozen bakeoff corpus exactly as sealed §5.1 requires.
  Selection needs a fixed, hash-pinned population and has one.
- **Preservation (§4.4)** cannot be evaluated on the bakeoff corpus against a baseline measured on
  the replay. Per this ruling — *"that is the v1 baseline and N1 must compare against it"* — the
  preservation gate is evaluated **on the replay**: run the v2 method through the same A/B/C
  development replay and compare, per Stage-3 invocation, the accepted allocation against v1's,
  plus the economic differential (run hash, NAV curve, daily returns, exits, reductions, costs,
  borrow) that the Phase 3C differential already exercises.

This is a **stronger** preservation test than the corpus comparison it replaces: it compares
economic outcomes over the actual development window rather than Stage-3 points on a selection
population.

---

## 4. P1 / P2 tie · **CONDITIONALLY ADJUDICATED**

The sealed registration made a tie surviving C6 an owner adjudication item and prohibited inventing
a seventh mechanical tiebreak. The owner exercises that discretion **in advance**:

> If, after the clean rerun and baseline reconciliation, PIQP_P1 and PIQP_P2 both pass C1–C4 and
> remain tied under C5/C6, **Solver B = PIQP_P2**.

This is an **owner discretionary adjudication of the registered tie**, explicitly **not** a new C7
criterion, and explicitly **not** a resurrection of the v1 `51 < 59` standalone-nonqualification
tiebreak, which the sealed registration deliberately removed.

Stated basis — **minimum-change continuity**:

- identical package and dependency complexity;
- runtime indistinguishable;
- P2 is already the established PIQP profile in the prior MR-002 chain;
- P2 reproduces the v1 accepted allocations trivially on all 3,895 instances, whereas P1 requires
  three bound-based equivalence demonstrations.

**This does not mean P1 failed.** Both passed. When the registered criteria deliberately leave two
technically adequate choices tied, the owner chooses the smaller behavioural delta.

Consequence: **no further owner checkpoint is required for P1/P2 selection** if the valid rerun
reproduces the tie.

---

## 5. Execution custody · binding on the rerun

The N1 census cannot become governing evidence unless the implementation that produced it is
identifiable. Before the final rerun:

1. **Commit** the exact N1 resolver / census / reference / equivalence execution code.
2. Change **no** solver profile, candidate set, criterion, or corpus.
3. **Bind its Git blobs** in the N1 execution evidence.
4. **Execute from that pushed commit** in `mr002-research:v1.4`.
5. Rerun the **full registered corpus**.

One clean rerun after D1, D3 and §2's measurement obligation are codified is sufficient.

### Evidence custody split

| Destination | Content |
|---|---|
| **S3** (record SHA-256, bytes, bucket/key, VersionId, read-back verification) | full 3,895-row census · large shuffle matrices · detailed candidate traces · similarly large raw output |
| **Git** (governing) | N1 verdict/summary · selected candidate · C1–C6 table · equivalence summary · difference-vs-v1 summary · corpus hash · bulk-evidence manifest pointing to S3 · exact source/runtime identities · disposition |

`.mr002out/` **stays** "scratch — never evidence". It is not to become a governance store.

---

## 6. Disposition of N1 as of this addendum

**`N1_PENDING_BASELINE_RECONCILIATION`.**

- Not `N1_STOP`: after D1 and D3, **no candidate hard gate has failed**.
- Not `N1_ADVANCE`: preservation against the **authoritative** v1 baseline is not yet established.

Conditional outcome, requiring no further owner input on selection: if the governed v1 baseline is
established, equivalence passes against it, zero advance conditions fail, and P1/P2 remain tied —

> **Solver B = PIQP_P2 · Disposition = N1_ADVANCE**

Return with the final N1 record identity and evidence manifest for closure adjudication and the N2
decision.

**N2: NOT YET AUTHORIZED. Validation / OOS: still prohibited.**
