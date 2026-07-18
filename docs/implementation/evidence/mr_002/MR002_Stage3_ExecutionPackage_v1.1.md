# MR-002 Stage-3 — Execution Package v1.1 (repair cycle 1)

**Supersedes v1.0**, which the owner reviewed on 2026-07-17 and **WITHHELD** (30 findings).
**Status:** DRAFT — the implementation component, stub fixtures, provenance validator, population
runner, and source manifest are prepared and tested. **No Stage-3 instance has been run.**
**Companion manifest:** `MR002_Stage3_ExecutionPackage_v1.1.json`,
SHA-256 `b08b9970656e7868315874353069f8f7d615a2fa8673410d2343e1042b961d51`.

This revision addresses the review directly. The owner directed **blockers 1–6 first, before secondary
hardening** — all six are done, and the 7–30 items rode along or are closed here, with four items that
can only be finished at commit / in the pinned image explicitly left open.

## Blockers 1–6 (directed first cycle)

1. **Solver-scoped, class-identity allowlist.** `NUMERICAL_ALLOWLIST` is keyed on
   `(solver_id, exact class object, exact message)` and matched by `type(exc) is builtins.ValueError`.
   The registered numerical status belongs to **QUADPROG_SQRT only**; a `PIQP_P2` raise of the same
   class/message → `INTEGRITY_DEFECT` → `INVALID_RUN`. A same-named user class and a `ValueError`
   subclass both fail to match. *(findings 1, 2, 14)*
2. **Pre-run provenance/environment validator that fails closed.** `mr002_stage3_preflight.py` —
   source-manifest verification, commit/tree/clean-tree, image + **full** OCI digest, python/ABI,
   package versions, AVX2-present/AVX-512-absent, thread env, `OPENBLAS_CORETYPE`, material config,
   corpus identity, solver/certifier fingerprints, and cascade import hygiene. Pure `evaluate(...)`,
   20 tests, fail-closed on any unverified pin. It is the runner's hard gate. *(finding 3)*
3. **Population runner that enforces STOP.** `mr002_stage3_population_runner.py` — halts immediately on
   any stop-class or outside-table outcome, resolves no later row, flushes+fsyncs partial evidence,
   marks the checkpoint **FAILED/non-resumable**, and makes an aggregate PASS structurally impossible
   after a stop; PASS additionally requires a COMPLETE marker and full count reconciliation; validation
   and OOS windows are refused. 16 integration tests on synthetic rows. *(findings 4, 26)*
4. **Complete source manifest.** `MR002_Stage3_SourceManifest_v1.0.json` byte-binds **all 19**
   load-bearing files (git blob + SHA-256 + bytes) across the cascade numerical path (9), the corpus-
   regeneration path (3), and the execution-package components (7). `exact_repair`/`exact_simplex` are
   deliberately **not** on the cascade path. The preflight verifies the working tree against it.
   *(findings 6, 29)*
5. **7–13 hardening** (rode along): defensive input boundary (no crash on `rec=None`/scalar `t`),
   guarded candidate conversion, certifier return-contract validation + production `SignedGapCertificate`
   check, `Exception` not `BaseException`, `assert`→runtime `Stage3IntegrityError`, `upper ≥ 0` and the
   enumerated model invariants, and a read-only/decoupled `accepted_z`.
6. **Final commit (blocker 5)** is the last step of this cycle; the execution countersignature binds
   that commit + tree externally.

## Secondary hardening (7–30)

Findings 7–17 are closed in code + tests (see the manifest `corrections_from_review_v1` map — every
finding is listed with its fix and the test that pins it). The realism harness is reframed as a
**pre-execution gate** (18), its over-broad "producibility of each enum" claim is **withdrawn and
narrowed** while adding a *real* `CERTIFICATE_NONQUALIFICATION` case (19), a write failure is now fatal
(20), and it binds the full runtime (21). The container spec uses an **immutable digest** and full
hardening (23, 25), the Intel/AMD "bit-for-bit proof" is replaced with an **empirical equivalence
protocol** (24), the test evidence is **preserved** as `MR002_Stage3_TestReport_v1.0.json` (27), the
quarantine checks gain a **positive** import-hygiene gate + fresh-directory/allowlist launcher
requirements (28), and this document's status is stated accurately (30).

## Test evidence

`python -m pytest` over the three Stage-3 test files → **83 passed, 1 skipped, exit 0**
(`MR002_Stage3_TestReport_v1.0.json`). The one skip is the production-binding test, which runs only
where `piqp`/`mpmath` are installed (the pinned image). ⚠ This run is against a **dirty working tree**;
it is regenerated at the final commit.

## Remaining before the execution countersignature

These cannot be closed on the laptop — they need the commit and the pinned image:

1. the **final implementation commit + tree** containing every file above (finding 5);
2. the **full 64-hex OCI config digest**, captured in-image (finding 22 — the recorded
   `sha256:770553aeae6c` is a truncated prefix and the preflight rejects it);
3. the **pinned expected identities** (package versions, callable fingerprints, material config) from a
   clean in-image `gather_env`;
4. a **preserved PASS artifact** from the in-image realism harness at that image (finding 18);
5. the **test report regenerated** at the final committed implementation (finding 27).

## The judgment requested

Whether this repaired implementation faithfully realizes the countersigned design — the §7 decision
table with **solver-scoped** normalization, the frozen numerics imported not re-derived, provenance and
STOP now **enforced** rather than described, the quarantine mechanically severed, and every review
finding either closed or explicitly carried to the commit/in-image step — and whether, once the five
remaining items are supplied, execution should be authorized by a separate execution countersignature.

*Nothing here runs until that countersignature exists. `MR002_Implementation_Erratum_v1.0` remains
suspended; the quarantined `AMENDED PASS` remains non-reusable; preflight closed; performance not
computed; validation and sealed OOS sealed and unread.*
