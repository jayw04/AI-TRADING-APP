# MR-002 Stage-3 — Execution Package v1.2 (repair cycle 2)

**Supersedes v1.1**, reviewed 2026-07-17 and **WITHHELD** (35 findings; the owner independently
reproduced 98 passed / 1 skipped and confirmed v1.1 was materially better, but a tested *component*, not
the real orchestration). **Status:** DRAFT. **No Stage-3 instance has been run.**
**Companion manifest:** `MR002_Stage3_ExecutionPackage_v1.2.json`,
SHA-256 `408fe48b20a73299e45e6c527fee5c31890819f6e8eb72e989089a5dcad40956`.

The review's core finding was correct: v1.1 bound a component, not an executable clean successor. This
cycle closes the prioritized blockers 1–12 and the secondary items 13–35, and states plainly what is
intrinsically image-/commit-level and therefore still open.

## Prioritized blockers 1–12

1. **Real orchestration (`orchestrate`).** Corpus source → verify the **regenerated corpus hash
   directly** → `run_population` → reconcile → write the run manifest → emit the run-level disposition.
   A **dry-run integration test** exercises this exact path on a tiny synthetic corpus with the real
   cascade decision logic. The *physical* corpus regeneration stays under the authorized run.
2. **Countersigned pins loaded programmatically.** `load_expected_pins` parses a countersigned artifact
   and requires *every* pin; `run_clean_successor` supplies a full `ExpectedPins` — no empty defaults.
3. **Static manifest, not self-referential.** `load_static_manifest` loads the **committed** manifest,
   hash-verifies it against the authorization artifact, and verifies the checkout against *that*.
   `build_manifest` is never the runtime source of expected values.
4. **Authorization is a verified artifact.** `load_authorization` checks the artifact's own SHA-256
   (supplied via an independent channel) plus its bound commit/tree/image/OCI/manifest/pins — a bare
   env var no longer satisfies the gate.
5. **Image/OCI identity** — narrowed: expected comes from the countersigned pins (independent of the
   observed env channel), a **full** OCI digest is required, and a signed launch attestation is the
   remaining piece (documented as open).
6. **Per-row numerical evidence.** Every record carries the input content hash, accepted `z` + dual as
   **exact rationals**, `z`/`lam` SHA-256, and the certificate's residual/interval fields, under a
   round-trip-verifiable `record_sha256` — a future reviewer can re-certify a row.
7. **Structural outcome validation.** `validate_outcome()` rejects any malformed "qualified" outcome →
   `MALFORMED_OUTCOME` → STOP.
8. **Exception preservation.** Any resolver/iterator/I-O exception → a FAILED terminal with
   `{exception_class, message_sha256, traceback_sha256}` and a non-resumable checkpoint.
9–10. **Checkpoint refusal.** A preexisting FAILED / COMPLETE / nonempty / trailing-partial checkpoint
   is refused before a single row is resolved.
11. **Mandatory count.** `n_expected` is the row-identity manifest length, bound before row 0; zero-row
   and truncated inputs cannot self-certify.
12. **Row-identity manifest.** Canonical ordered `{row_id, content_hash}`; the runner enforces unique
   IDs, exact order, per-row content hash, and one-to-one correspondence.

## Secondary 13–35

Closed in code + tests: checked/one-shot git (13), `verify_source` completeness incl. byte-length (14),
positive import allowlist (16), regenerated-corpus hashing (17), closed package-pin set (18),
canonicalize-once (20), frozen `Attempt` arrays (21), sealable `_REAL` (22), harness runtime-gated
verdict (24), full-evidence output hash (25), corrected candidate-kind labelling (26), atomic harness
persistence (27), the real-entry dry-run (29), rejection of malformed qualified outcomes (30), and the
resolver/I-O failure battery (31). Narrowed honestly: fingerprint scope (19), governance-artifact
binding (15), and the "protections" that are now **executable gates** rather than prose (35). The docs
no longer overstate completion (33, 34). Acknowledged as open: the production-binding test (28) and the
test report's final admissibility (32).

## Test evidence

`pytest` over the three Stage-3 test files → **98 passed, 1 skipped, exit 0**
(`MR002_Stage3_TestReport_v1.0.json`, marked `admissible_as_final: false`). The skip is the
production-binding test, which runs only in the pinned image.

## Remaining before the execution countersignature (intrinsically image-/commit-level)

1. the physical corpus regeneration wired into `run_clean_successor`, executed only under the
   authorized run (finding 1 residual);
2. the final implementation commit + tree (finding 5);
3. the full 64-hex OCI config digest + a signed launch attestation (findings 5, 22);
4. the countersigned expected-pins + execution-authorization artifacts (findings 2, 4);
5. an in-image realism-harness PASS artifact at the pinned image (findings 18, 28);
6. a final test report — clean tree, pinned image, production-binding test **run** (findings 28, 32);
7. the formally-enumerated model input contract derived from `_qp_matrices` (finding 23).

## The judgment requested

Whether the clean-successor implementation and its enforcement gates are now correct and complete
enough that, once the seven image-/commit-level items are supplied, execution should be authorized by a
separate execution countersignature.

*Nothing here runs until that countersignature exists. `MR002_Implementation_Erratum_v1.0` remains
suspended; the quarantined `AMENDED PASS` remains non-reusable; preflight closed; performance not
computed; validation and sealed OOS sealed and unread.*
