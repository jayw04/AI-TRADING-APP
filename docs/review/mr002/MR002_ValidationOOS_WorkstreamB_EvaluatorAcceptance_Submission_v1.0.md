# MR-002 Workstream B — prerequisite **P4**: EvaluatorQualificationPlan §5 acceptance submission v1.0

**Authorization:** P3 adjudication 2026-07-22 — *"P4 — §5 acceptance submission is now authorized to
begin… Proceed with P4 only, then stop for adjudication before P5."*

**Boundary held:** no P5 qualification, no evaluator-binding resolution, no P10, no validation/OOS
value access, no performance computation, no post-hoc change to the acceptance standard. This
submission is the §5 artifact; the adjudication text is not treated as one. `validation_authorization`
remains **false**; the CAS anchor is untouched; the single validation opening remains unconsumed.

**Products:** `evaluator/MR002_P3_AcceptanceRecord.json` ·
`evaluator/MR002_EvaluatorAcceptanceSubmission.json` · generator `evaluator/_gen_evidence_p4.py` ·
tests `evaluator/test_p4_acceptance.py`.

**Full evaluator suite: 204 passed** (Inc1 59 + Inc2 35 + Inc3 34 + Inc4 61 + P4 15). Ruff clean.

---

## 1. P3 evaluation — **ACCEPT_AS_COMPLIANT**, 16/16 checks pass

Verification was **independent re-derivation**, not restatement: digests are recomputed from
**committed git objects**, and the denial chain is **re-executed live** rather than read out of the
P3 report.

| # | Check | Result |
|---|---|---|
| V1 | both P3 commits exist and are ancestors of HEAD | PASS |
| V2 | the four modules' committed digests equal the working-tree digests | PASS |
| V3 | digests claimed by the P3 record reproduce independently | PASS |
| V4 | denial chain re-derives — 4 refusals, `sealed_reads = 0`, chain verifies | PASS |
| V5 | a stale prerequisite digest blocks validation **even with the flag true** | PASS |
| V6 | the workstation runtime is still not a bound instance (P10 open) | PASS |
| V7 | commit/tree/container remain `PENDING_EVALUATOR_BIND` (P5 not begun) | PASS |
| V8 | Phase 3A + adjudication packages unmodified since the adjudication commit | PASS |
| V9 | the CAS anchor is byte-identical to its adjudicated form | PASS |
| V10 | the anchor still records `false` at `_rev 0` | PASS |
| V11 | no Phase-3A-bound file drifted (compared under Phase 3A's own rule) | PASS |
| V11b | the §4 inventory is derived mechanically | PASS |
| V12 | all 22 required gates have a synthetic-fixture result | PASS |
| V13 | all 4 required diagnostics present and classified non-gating | PASS |
| V14 | `trials_N = 5` read from the ledger; a tampered N fails closed | PASS |

**The status transition is proposed, not applied.** `PRODUCED → SATISFIED` is recorded with
`applied_here: false`, effective **on owner adjudication of P4**. The record contains no
grant-capable field, does not modify the anchor, and reports the adjudicated prerequisite digest
alongside a prospective digest that is explicitly labelled a mechanism illustration — the D3
submission must recompute from the then-current register.

## 2. ⚠ Corrigendum — the "25 modules" figure in my P3 submission §6 was wrong

Your adjudication warned: *"P5 must derive the final count mechanically rather than hard-code 25 as
an adjudicated constant."* Deriving it mechanically shows the numeral itself was defective.

- Phase 3A bound **every `.py` file** in the evaluator directory — **tests and generators included**
  (21 files).
- The §4 module rule **excludes** tests and generators.
- My P3 §6 arithmetic added 4 new modules to Phase 3A's 21. Those two counts are **not
  like-for-like**, so "21 → 25" compared one rule's total against another's.

Mechanically derived:

| Rule | At Phase 3A | Now |
|---|---:|---:|
| §4 modules (tests + generators excluded) | 15 | **19** |
| All `.py` files (Phase 3A's own rule) | 21 | 29 |

**The substance of the §6 finding stands unchanged**: zero drift on every Phase-3A-bound file, new
files present, the Phase 3A registry is historical rather than the P5 binding, and P5 must enumerate
the then-current inventory. Only the numeral was wrong. The P3 submission text is left **unmodified**
(it was adjudicated); this record is the corrigendum, per your instruction that no amendment to
`ea437ce` is required and that lineage statements stay scoped to their own commit.

## 3. §5 elements returned

- **Evaluator code identities** — 19 modules with digests and an inventory digest.
  `commit`/`tree`/`container_image_digest` deliberately **`PENDING_EVALUATOR_BIND`**: the
  authoritative binding is P5's §4 procedure and is not resolved here.
- **Container + dependency identity** — dependency lock bound by SHA-256; container digest **ABSENT**
  (P10, runtime producer); numeric runtime is a reference observation only.
- **Report schema** — `mr002_valoos_report.py`, self-hash verifies, plus the Increment-4
  no-overwrite publication wrapper.
- **Synthetic end-to-end evidence** — Increment 1 canonical report, Increment 2 ledger report,
  Increment 3 replay report, Increment 4 access-boundary report, each bound by hash.
- **Every gate's synthetic fixture result** — **22/22** required gates with status, threshold, and
  sample; none missing.
- **Diagnostics** — all 4 present, none classified `GATE`.
- **Refusal-test evidence** — governing-identity chain (Increment 1 semantic-tamper suite), code
  identity (T4-11…T4-17), runtime identity (T4-05…T4-08), access boundary (T4-18…T4-29), publication
  (T4-31…T4-37).
- **Determinism** — byte-identical proofs for Increments 1, 3, and 4.
- **Zero performance** — validation read false, OOS read false, development performance false,
  synthetic only, `sealed_reads = 0`.
- **`trials_N = 5` from the bound identity, not a code constant** — re-demonstrated here: N is read
  from the countersigned ledger, and a tampered N (`5 → 4`) fails closed with
  `REFUSED_CODE_OR_DATA_IDENTITY`.

## 4. On the coverage limit you noted

Your P3 adjudication observed that the denial chain proves enforcement behaviour, not that every
possible access path is covered. This submission does **not** claim coverage. Establishing that the
qualified inventory contains no unbound executable access path remains work for P5 and the later
closed readiness submission; nothing here should be read as discharging it.

## 5. Not done under this authorization

P5 §4 pre-access binding · P6–P9 and P11 custodian evidence · P10 runtime instance · P13 ·
grant-readiness verifier or conclusion · any D3 grant.

Work **stops here for adjudication before P5 begins**.
