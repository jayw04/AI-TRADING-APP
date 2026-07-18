# MR-002 Stage-3 — Execution Package v1.3 (repair cycle 3)

**Supersedes v1.2**, reviewed 2026-07-17 and **WITHHELD** (30 findings; prioritize 1–12).
**Status:** DRAFT — all 30 findings processed: most closed in code+tests, several partial, and the
execution-critical remainder (attestation, final commit, in-image runs, formal input contract)
explicitly open. **No Stage-3 instance has been run.**
**Companion manifest:** `MR002_Stage3_ExecutionPackage_v1.3.json`,
SHA-256 `71dfee911249130210bb6e5cd990c2d8815c543cd25084375dc41e39ddd178da`.

## Prioritized 1–12 — what changed

1. **The real entry point executes** (1, 29). `run_clean_successor` constructs
   `production_corpus_source` — real, reviewable regeneration code over the frozen capture path, DEV
   window only — and runs `orchestrate()` with `resolve_instance`, emitting the clean-run manifest and
   a disposition exit code. Only *execution* stays gated on the verified authorization artifact.
2. **Independent corpus hashing** (2). `orchestrate()` derives the corpus hash itself from the actual
   row bytes (the registered scheme, replicated dependency-free and pinned by a scheme test). A source
   returning altered rows plus the expected hash string is caught; the claimed hash must also agree.
3. **Authorization cross-binding + semantics** (3, 4). `load_authorization` enforces record type,
   version, `decision == "AUTHORIZED"`, `execution_authorized is True`, countersigner, repository, and
   the bound row-manifest protocol + execution-package hash; `cross_validate_authorization` requires
   the authorization and pins to name the *same* commit/tree/image/OCI identities.
4. **Harness preflight gate** (6). A harness PASS now requires a full `evaluate()` PASS against the
   countersigned pins + static manifest; without them the harness cannot pass.
5. **Complete outcome validation** (7). Solver identities, accepted-z byte-equality, finiteness, the
   complete certificate field set with `qualifies` exactly `True`, primal/dual lengths vs the problem,
   and STOP-state structural invariants.
6. **Re-certifiable evidence** (8). Every record preserves the *complete input problem* as exact
   rationals; a missing registered certificate field raises instead of being dropped.
7. **Runner-level canonicalize-once** (9); **sidecar preservation of I/O failures** with an honest
   `evidence_persisted` flag (10); **guarded iterator creation and drain** (11).
8. **Cryptographically self-verifying checkpoint** (12, 13). Strict reader (mid-file corruption,
   unknown events, events-after-terminal all fail); `aggregate_verdict` re-verifies every
   `record_sha256`, content hash, order, class, count, and the single-final-terminal invariant.

## 13–30

Row-manifest schema validation (14); run-manifest provenance + final-checkpoint-bytes binding
(15, 16); fail-closed orchestration (17); executable output-root controls (18); full registry seal,
honestly bounded (19); closed 5-key fingerprint set in both seal and preflight (20); two-way material
config (21); exactly-closed package pin map, native binding delegated to image+attestation (22);
`verify_source` governance/header verification (23); package self-binding closed one level up via the
authorization artifact (24); the certifier-classification case relabelled with its exact claim (25);
full-document persistence verification (26); wording corrected (28).

**Open:** the operator-supplied authorization-hash channel until the signed launch attestation (5);
the production-binding test (27, pinned image); the formal `_qp_matrices` input contract (30); the
final commit + in-image artifacts.

## Test evidence

**113 passed, 1 skipped, exit 0** (`MR002_Stage3_TestReport_v1.0.json`, `admissible_as_final: false`;
dirty tree, production-binding skipped — regenerated at the final commit in the pinned image).
Cascade 48 · preflight 25 · runner/orchestration 41.

*Nothing here runs until the execution countersignature exists. `MR002_Implementation_Erratum_v1.0`
remains suspended; the quarantined `AMENDED PASS` remains non-reusable; preflight closed; performance
not computed; validation and sealed OOS sealed and unread.*
