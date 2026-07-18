Review verdict

Execution countersignature remains withheld. Do not commit v1.8 as the final candidate yet.

I independently reconstructed the uploaded package and ran the four test modules:

160 passed, 1 skipped

The skipped test remains the real production-binding test. The supplied report correctly remains development-only, records a dirty tree, and is not admissible as final evidence.

The seven directed cycle-8 tests pass, and their corresponding fixes are present. In particular:

missing evidence_persisted now fails closed;
realism qualification is derived from case records;
the production-binding test ID must appear in the final test manifest;
the verification receipt is compared with the parsed attestation;
invalid authorization calendar dates are rejected;
the attestation has a closed top-level schema, version, and immutable status.

I nevertheless found several remaining issues.

Critical blockers
1. The realism loader does not validate the claimed real implementation identities

load_realism_pass() requires only that binds_real is truthy:

if not d.get("binds_real"):
    raise Stage3RunRefused("REALISM_BINDS_REAL_MISSING")

It does not require:

primary   == QUADPROG_SQRT
fallback  == PIQP_P2
certifier == the registered canonical_qualify path

An artifact containing:

"binds_real": {
  "primary": "FAKE_SOLVER",
  "fallback": "FAKE_FALLBACK"
}

can qualify if the case booleans and hashes look valid.

The loader must enforce an exact closed binds_real structure and values matching the countersigned design. The harness currently emits the intended values, but the consumer must verify them rather than trust Phase B to bind arbitrary bytes.

2. Realism cases are validated only generically, not against their required semantics

The loader now requires all three case-name groups and every case to report pass: true. That is an improvement. It still does not verify the group-specific evidence:

primary_qualified/*

Should require:

expected         PRIMARY_QUALIFIED
disposition      PRIMARY_QUALIFIED
primary_solver   QUADPROG_SQRT
primary_enum     QUALIFIED
fallback_invoked false
accepted_by      QUADPROG_SQRT
stop             false
fallback_qualified/*

Should require:

expected         FALLBACK_QUALIFIED
disposition      FALLBACK_QUALIFIED
primary_enum     NUMERICAL_STATUS_NONQUALIFICATION
fallback_solver  PIQP_P2
fallback_enum    QUALIFIED
fallback_invoked true
accepted_by      PIQP_P2
stop             false
certifier_classification/*

Should require:

expected_primary_enum CERTIFICATE_NONQUALIFICATION
primary_enum          CERTIFICATE_NONQUALIFICATION

At present, a case may be named primary_qualified/x, state pass: true, but contain an unrelated disposition and still qualify. The consumer is still trusting each case’s own pass assertion.

Create a validate_realism_case() function that derives each case verdict from its durable fields.

3. The final test report still does not prove each collected test passed

The loader requires:

at least 100 collected test IDs;
all four required modules;
the production-binding test ID;
production_binding_outcome == "passed";
zero reported skips;
overall exit code zero.

However, collected_test_ids is only a list of names. It contains no per-test outcomes.

A fabricated report can list 120 test IDs—including the production-binding test—while the independent scalar fields claim success. The report’s own claims remain internally trusted.

The final report should preserve a machine-readable test-result map or JUnit-style record:

{
  "test_id": "...::test_name",
  "outcome": "passed",
  "duration_seconds": 0.012
}

Then require:

exactly one result per test ID;
no duplicates;
every result is passed;
passed count equals the number of records;
skipped and failed counts are derived rather than trusted;
the production-binding test’s own record is passed.
4. The final test report is not tied to the countersigned runtime identities

load_final_test_report() does not require the report to state and match:

commit;
tree;
image digest;
OCI config digest;
source-manifest SHA-256;
expected-pins SHA-256;
execution-package SHA-256;
Python ABI and package identities.

Phase B proves only that it binds those report bytes. It does not prove the tests represented by those bytes ran against the Phase-B implementation and image.

The final in-image report must carry these identities, and the loader must compare them with Phase B and the attestation.

5. The verification receipt does not require or match the launch nonce

The receipt schema permits:

run_nonce

but does not require it. It also does not compare receipt run_nonce with attestation run_nonce.

That allows a successful receipt from a different launch context to be associated with the same attestation bytes, particularly if receipt handling is reused or copied.

Require:

receipt["run_nonce"] == attestation["run_nonce"]

and make run_nonce mandatory.

The same applies to verified_at: either require and validate it, or remove it from the recognized schema. Optional governance fields create ambiguity.

6. The verification receipt version is not enforced

version appears in RECEIPT_ALLOWED_KEYS, but the loader does not require:

version == 1.0

It also has no immutable/final status field.

A missing version passes, and a future incompatible version can also pass as long as it uses recognized keys.

Require a closed receipt schema with:

record_type   MR002_STAGE3_LAUNCH_VERIFICATION_RECEIPT
version       1.0
record_status IMMUTABLE

and exact required keys.

7. Verification-tool identity remains incomplete

The receipt validates verification_tool_sha256, but the attestation contains only a textual verification_tool value. Nothing proves the hash in the receipt corresponds to the tool named in the attestation.

Phase B also does not independently bind the verification tool binary.

The attestation or Phase B should carry:

verification_tool_path_or_id
verification_tool_sha256
verification_tool_version

and the receipt must exactly match those fields. Otherwise, an arbitrary tool hash can be reported as successful.

High-severity findings
8. Successful realism persistence remains less robust than refusal persistence

The PASS path now persists evidence_persisted: true, which fixes the directed issue. But it still:

catches only OSError;
has no emergency sidecar after real solver execution;
ignores the byte SHA returned by _atomic_write_json;
verifies a semantic reserialization hash instead of the actual governed-byte hash;
prints the preliminary document before persistence succeeds.

The preflight-refusal path has stronger handling: it catches Exception, checks the actual file hash, and attempts an emergency sidecar.

Both paths should use one shared persistence function returning:

{
  "sha256": "...",
  "file_fsync_verified": true,
  "rename_completed": true,
  "directory_fsync_verified": true
}

A failure after real numerical cases is at least as important to preserve as a preflight refusal.

9. The realism harness still uses two runtime observations

The harness runs preflight with one gather_env() result, then calls runtime_block(), which gathers the environment again.

The comment that the gate’s observed environment is “inside preflight_report” remains inaccurate: rep.summary() contains check results, not the complete Env snapshot evaluated.

This is acknowledged as open in-image work, but it remains a mandatory pre-countersignature deliverable.

10. The run entry discards the parsed verification receipt and artifact records

The receipt is now passed the parsed attestation, but the returned receipt is still discarded:

load_verification_receipt(...)

The parsed realism and final-test records are also discarded.

Consequently, the run manifest binds their hashes but cannot preserve useful semantic fields such as:

receipt key ID;
signature algorithm;
receipt nonce;
verification tool hash;
realism case inventory;
production-binding test ID and result;
test count.

Retain the parsed objects and include a minimal normalized semantic summary in the run manifest, in addition to their byte hashes.

11. The attestation is not compared with the observed command or mount

The attestation structurally contains:

exact command;
output mount identity;
launcher identity;
run nonce.

The entry still does not compare these claims to observed process or mount state. This is honestly open on the launcher side, but it remains part of the authenticity boundary.

The verification receipt must attest not only signature validity but also that the launcher generated the attestation from observed launch state.

12. Phase B still does not directly bind the input-contract artifact

The contract is indirectly bound through the Phase-A manifest and package. Given its execution-critical role, direct Phase-B inclusion remains preferable:

input_contract_sha256
input_contract_byte_length

The contract artifact and conformance tests are otherwise materially stronger.

13. Phase B still uses flat artifact hashes

The flat format is acknowledged as partial. It should be replaced or supplemented by structured entries carrying:

canonical path;
record type;
version;
SHA-256;
byte length;
required semantic result.

This would eliminate ambiguity and make cross-validation generic rather than maintaining separate parallel arguments.

Documentation and evidence issues
14. The expression-level contract derivation remains open

The contract and validator agree, but that does not independently prove the declared clauses exhaust every assumption made by the numerical code.

The required derivation should map individual expressions and slices to contract clauses. This remains necessary before execution countersignature.

15. The source manifest is still a development-tree artifact

The Phase-A manifest verifies the uploaded working-tree set, but the package remains uncommitted and the report identifies the source commit as the earlier countersign commit while the tree is dirty.

The final sequence must still include:

commit the finalized implementation;
regenerate Phase A from that exact clean commit;
build the pinned image;
execute the complete in-image tests with zero skips;
execute the realism harness;
produce and cryptographically verify the attestation;
create Phase B;
countersign Phase B;
execute only against that exact binding.
Directed-cycle findings disposition
Cycle-8 issue 1 — missing persistence field          CLOSED
Cycle-8 issue 2 — empty/aggregate-only cases         PARTIALLY CLOSED
Cycle-8 issue 3 — production-binding test proof      PARTIALLY CLOSED
Cycle-8 issue 4 — receipt/attestation matching       PARTIALLY CLOSED
Cycle-8 issue 5 — parsed attestation retained        CLOSED
Cycle-8 issue 6 — invalid authorization dates        CLOSED
Cycle-8 issue 7 — attestation closed schema          CLOSED

“Issue 2,” “issue 3,” and “issue 4” are improved and their named tests pass, but the tests cover only the explicitly listed defect, not the complete semantic contract.

Overall disposition
Execution Package v1.8                    NOT READY FOR FINAL COMMIT
Development tests                         PASS — 160 passed, 1 skipped
Ruff                                      REPORTED CLEAN
Source-manifest verification              REPORTED ZERO DEFECTS
Decision-table implementation             PASS
Corpus provenance integration             PASS AT DEVELOPMENT LEVEL
Realism persistence field                 FIXED
Realism case semantic validation          INCOMPLETE
Final test per-test evidence               INCOMPLETE
Receipt schema and nonce binding           INCOMPLETE
Verification-tool binding                 INCOMPLETE
Single-snapshot runtime evidence           OPEN IN IMAGE
Directory-fsync durability                OPEN IN IMAGE
Structured Phase B                         OPEN
Expression-level derivation               OPEN
Final commit/tree                          NOT PROVIDED
Pinned image/full OCI identity             NOT PROVIDED
In-image realism PASS                      NOT PROVIDED
Final zero-skip report                     NOT PROVIDED
Signed attestation and receipt             NOT PROVIDED
Execution countersignature                 NOT ISSUED
Stage-3 execution                          NOT AUTHORIZED
Performance                               NOT COMPUTED
Validation/OOS                            SEALED AND UNREAD

The next repair should prioritize findings 1–7 above. They are still localized to artifact semantics and receipt validation; no registered corpus execution is needed.
---

# Delta review — allowlist correction (2026-07-18)

## Verdict: AUTHORIZED (single allowlist correction)

The stop gate behaved correctly: it refused before any realism case executed and preserved the
failure artifact. The proposed addition is technically justified — importing an approved submodule
necessarily loads its parent package namespace; treating the bare package as an unapproved
numerical module is a false positive, not evidence of an unauthorized implementation dependency.

## Authorized change

Add exactly `"app.research.mr002"` to `ExpectedPins.approved_modules`. No wildcard, prefix-based
acceptance, recursive-package rule, or additional module may be introduced.

## Required tests (all delivered)

- bare parent package `app.research.mr002` accepted
- all previously approved submodules accepted
- unknown sibling `app.research.mr002.<unexpected>` rejected
- similarly prefixed packages rejected
- arbitrary `app.research` module rejected
- positive-allowlist rule preserved: parent-namespace approval implies no child-module approval

## Governance consequence (executable-code change, even though one line)

    8a87280 implementation freeze        SUPERSEDED FOR QUALIFICATION
    68a270e Phase-A evidence commit      SUPERSEDED
    qual:1.0 / qual:1.1 images           DIAGNOSTIC ONLY
    168-pass in-image report             VALID DIAGNOSTIC EVIDENCE, NOT FINAL
    realism FAIL artifact                PRESERVE IMMUTABLY

## Required sequence after the fix

1. Make only the allowlist change and its focused tests.
2. Run the full development suite and lint.
3. Submit the exact diff for delta review.
4. Commit a new frozen implementation candidate.
5. Regenerate Phase A on Linux from that clean commit.
6. Build a new pinned image and capture new full image and OCI identities.
7. Re-run verify_source; require zero defects.
8. Re-run the complete in-image suite; require zero failures and zero skips.
9. Re-run the realism harness from a fresh output directory.
10. Preserve both the prior FAIL artifact and the new result; never overwrite the former.

## Scope limits — NOT authorized

Any broader allowlist change; wildcard or prefix matching; changes to solver, certifier, cascade,
tolerances, or corpus logic; registered 3,895-row execution; performance computation; validation
or OOS access.

    One-line allowlist delta            AUTHORIZED
    Focused regression tests            REQUIRED
    New implementation commit           REQUIRED
    New Phase-A manifest                REQUIRED
    New pinned-image qualification      REQUIRED
    Registered Stage-3 execution        NOT AUTHORIZED
    Validation / OOS                    SEALED AND UNREAD
