# MR-002 Workstream B — Increment 4 (operational increment) — prerequisite **P3** submission v1.0

**Authorization:** owner adjudication 2026-07-22 — **D2 AUTHORIZED WITH RESTRICTIONS**, governing
instruction *"proceed with P3 only, then stop for adjudication before starting P4."*

**Boundary held throughout:** synthetic only. No validation-partition access (direct, indirect, or
inferential), no credential release, no performance computation, no P13, no change to any
preregistered model / evaluator / acceptance criterion / trial rule / structural identity, no D3
grant or readiness conclusion. `validation_authorization` remains **false**; the single validation
opening remains **unconsumed**; OOS remains under DENY.

**Status claimed:** P3 is **PRODUCED and submitted for adjudication**. It is *not* self-declared
`SATISFIED` — satisfaction requires independent verification, per the adjudication.

---

## 1. What was built

Four operational capabilities, each a new evaluator module with synthetic-fixture qualification.
The Phase 3A and adjudication packages were **not modified**.

| Capability | Module | Failure mode it closes |
|---|---|---|
| Numeric-runtime identity | `mr002_valoos_runtime.py` | a run whose numeric stack is not the bound one |
| Code identity + refusal | `mr002_valoos_code_identity.py` | executing code that is not the bound code |
| Access boundary + opened-object ledger | `mr002_valoos_access_boundary.py` | reading a sealed partition without authorization |
| No-overwrite publication wrapper | `mr002_valoos_publication.py` | a second run made to look like the first |

Evidence: `evaluator/MR002_Increment4_Qualification.json`,
`evaluator/MR002_Increment4_AccessBoundaryReport.json`, `evaluator/MR002_Increment4_TestLog.txt`,
generator `evaluator/_gen_evidence_inc4.py`, tests `evaluator/test_increment4.py`.

**61 Increment-4 tests pass; full evaluator suite 189 passed** (Inc1 59 + Inc2 35 + Inc3 34 + Inc4 61).
Ruff clean.

## 2. Numeric-runtime identity — and what it does *not* claim

`capture_runtime()` observes python / numpy / scipy / pandas / BLAS / LAPACK / driver / machine /
platform / thread-count env vars / locale / timezone / RNG / seed, and carries the frozen solver
settings (`numpy.linalg.lstsq`, `gelsd/SVD`, `float64`, `rcond=1e-10`, seed `20260711`).
`require_runtime()` FAIL-STOPS on any bound-field mismatch.

Two properties matter more than the happy path:

- **It never fabricates.** A lockfile SHA or container digest is recorded only if the operator
  supplies one; absent, the field stays absent.
- **Placeholder completion is rejected.** `""`, `TBD`, `PENDING`, `PENDING_EVALUATOR_BIND`, `null`
  and empty containers can never satisfy a runtime binding — `INTEGRITY_STOP:NUMERIC_RUNTIME_MANIFEST_INCOMPLETE`.

Accordingly the qualification records this workstation's runtime as a **reference observation** with
`observed_runtime_is_a_bound_instance: false` and the missing fields named
(`dependency_lockfile_sha256`, `container_image_digest`). **P10 remains UNSATISFIED** and belongs to
the runtime producer.

## 3. Code identity + refusal

Refuses `REFUSED_CODE_OR_DATA_IDENTITY` **before any window read** on: module drift, a missing
module, an **unbound module present on disk**, a commit / tree / container mismatch, an absent
binding, or a binding whose fields are unresolved sentinels.

The unbound-module refusal is the load-bearing one: without it, code added to the evaluator directory
after the binding was accepted would execute silently.

`bind_from_directory()` exists to *mint* a binding during qualification and is documented as **not a
verification path**; `require_code_identity()` has no fallback to it. The self-check in the evidence
therefore reports the real module inventory reproducing while `commit`, `tree`, and
`container_image_digest` remain **`PENDING_EVALUATOR_BIND`** — resolving them is **P5** through the
registered §4 procedure and must not be inferred from this tree.

## 4. Access boundary — fail-closed in every direction

Every read goes through `AccessBoundary.open_object`; there is no second path.

- Absent / unreadable / malformed authorization state → **blocks** (`AUTHORIZATION_STATE_INVALID`).
  An unparseable state is not "no restriction".
- VALIDATION → blocked unless the durable state records `validation_authorization = true` **and** the
  `_rev` matches **and** every expected bound identity matches. The brittle prerequisite digest is
  enforced here: a stale digest blocks with `bound_identity_mismatch:prerequisite_digest`.
- OOS → blocked **unconditionally**. A validation grant is not an OOS grant, and this boundary
  contains no code path that could become one.
- Unregistered object → blocked on every partition.
- Every attempt, **permitted or refused**, is recorded in a hash-chained ledger, so a refusal is
  evidence rather than a silence. Tampering with a ledger row breaks the chain.

The evidence report was produced against the **real adjudicated authorization state**
(`MR002_Phase3BC_ValidationAuthorizationState_v1.0.json`, `false`, `_rev 0`): four sealed/unregistered
attempts, **all refused**, one synthetic read permitted, `validation_reads = 0`, `oos_reads = 0`,
`sealed_reads = 0`, chain verifies. Every registered identifier used is a synthetic placeholder — no
validation or OOS object identity is disclosed or resolved.

## 5. Publication wrapper

Python port of the Run-5 pattern: three vacant destinations, `O_CREAT|O_EXCL` creation, exit ↔
disposition agreement (`PASS`0 / `FAIL`1 / `REFUSED`2 / `INTEGRITY_STOP`3), a third no-overwrite
publication record, read-only locks and SHA-256 on everything written, and read-only post-hoc
verification.

Publication **control** only: it never modifies, retries, or reinterprets a result. An occupied
destination refuses with the prior content preserved and no publication record created; a second
publication to the same paths refuses. `published_at` is supplied by the caller so a publication is
reproducible from its inputs — two independent runs produced **byte-identical** report and
publication hashes.

## 6. Finding — P3 makes the Phase-3A evaluator reference binding stale (affects P5 and D3 C9)

Producing P3 added modules to the evaluator directory. Measured against the tree after this
increment:

- the **21 modules bound in the Phase-3A `GoverningSourceRegistry` show ZERO drift** — no
  previously-bound module was modified;
- **6 files are new and therefore unbound** relative to that reference: the 4 operational modules
  plus `test_increment4.py` and `_gen_evidence_inc4.py`. Under the §4 module-inventory rule (tests
  and generators excluded) this is **21 → 25 bound modules**.

This is an expected consequence of authorized production, not a defect — but it has two governance
effects the owner should note now rather than discover at D3:

1. **P5 must bind the full 25-module inventory**, not re-assert the Phase-3A 21-module reference.
   The Phase-3A binding was explicitly a *reference to be re-verified at evaluator qualification*;
   it is not the §4 binding.
2. **D3 condition C9 ("zero evaluator drift and zero unbound evaluator code") must be evaluated
   against the P5 binding**, not against the Phase-3A reference. Evaluated against the Phase-3A
   reference today, C9 would fail with 4 unbound modules — correctly, since no §4 binding covering
   them exists yet.

The `MR002_Phase3BC_Phase3ALineageProof_v1.0.json` committed at `ea437ce` remains accurate **as of
its own commit** and is unmodified; the D3 submission must recompute lineage against the
then-current tree, which is exactly what condition C8 requires.

## 7. Explicitly not done under this authorization

P4 (§5 acceptance submission) · P5 (§4 pre-access binding / `PENDING_EVALUATOR_BIND`) · P6–P9 and P11
(custodian) · P10 (runtime instance) · P13 · any grant-readiness verifier or conclusion · any D3
grant.

Per the governing instruction, work **stops here for adjudication before P4 begins**.
