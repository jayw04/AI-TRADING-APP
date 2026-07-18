# MR-002 Stage-3 — Allowlist Delta Submission for Delta Review (v1.0, 2026-07-18)

Submitted under the owner's 2026-07-18 delta-review authorization: the single allowlist
correction for the `cascade_import_hygiene` false positive on the bare parent package
`app.research.mr002`, plus the required focused regression tests. Nothing else.

## The exact change

`apps/backend/scripts/mr002_stage3_preflight.py` — `ExpectedPins.approved_modules` gains
exactly one member, the bare package name `"app.research.mr002"` (with a two-line constraint
comment). Matching remains exact-name frozenset membership: no wildcard, no prefix rule, no
recursive-package rule, no other module added. `load_expected_pins` in the population runner
constructs `ExpectedPins` without overriding `approved_modules`, and the pins artifact schema
does not carry it, so this dataclass default is the single point of change — the countersigned
pins JSON (`MR002_Stage3_ExpectedPins_DRAFT_v1.0.json`, sha256 `c81faabb…`) needs no edit.

Full diff: `MR002_Stage3_AllowlistDelta_20260718.patch` (sha256
`c08b5dfa37796fae680ff2e825db1ee8d257c9006db5ba40c45da62401b38603`).

## Required focused tests (all present, all passing)

In `apps/backend/tests/research/test_mr002_stage3_preflight.py`:

| Requirement | Test |
|---|---|
| bare parent package `app.research.mr002` accepted | `test_delta_bare_parent_package_accepted` |
| all previously approved submodules accepted (exact 12, none dropped) | `test_delta_all_previously_approved_submodules_still_accepted` |
| unknown sibling `app.research.mr002.<unexpected>` rejected | `test_delta_unknown_sibling_under_parent_rejected` |
| similarly prefixed packages rejected (`mr002_shadow`, `mr002x.stage3_cascade`) | `test_delta_similarly_prefixed_packages_rejected` |
| arbitrary `app.research` module rejected | `test_delta_arbitrary_app_research_module_rejected` |

Positive-allowlist rule preserved: the sibling-rejection test loads the approved parent AND an
unapproved child in the same import set and requires `cascade_import_hygiene` to FAIL —
parent-namespace approval implies no child approval.

## Development suite + lint

- Full 4-module Stage-3 suite (`test_mr002_stage3_cascade_dispA`, `_preflight`,
  `_population_runner`, `_input_contract`): **172 passed, 1 skipped, exit 0**
  (prior baseline 167+1s, +5 delta tests; the 1 skip is the known production-binding
  test requiring piqp/mpmath — it runs in-image and must PASS there with zero skips).
- `ruff check` on both changed files: clean.

## File identities (working tree, LF bytes)

| File | sha256 | git blob |
|---|---|---|
| `apps/backend/scripts/mr002_stage3_preflight.py` | `9c749d73415baa9220a5c348b6c845c179ed007739f9d48ca3517bd71f94e6a7` | `1425f5ef7cb42f6a74347fc3a5602b1a8418b7f9` |
| `apps/backend/tests/research/test_mr002_stage3_preflight.py` | `deafe0b0f77f7e6e8191c109b4f9984b9b4f310e7d12bf75928b2c6f6d549ecd` | `844d335c007066ea67a07ee577da6c67092f5ebb` |

## Evidence preservation (completed BEFORE the change)

All current-instance evidence copied off the box (`i-0c90cfe795220c4bc`) and hash-verified;
preservation manifest `.mr002out/imagequal_20260718/MR002_EvidencePreservation_PreDelta_v1.0.json`
(sha256 `8d5ca0e7867fd29d5501388b8f6c3e5da9d1ff16e7902f3bde13eea18d236317`); all preserved files
set read-only; the prior realism FAIL artifact (sha256 `18437f3c…`) will never be overwritten —
the re-run uses a fresh output directory. Verified matches: FAIL artifact `18437f3c…` (box ==
laptop), pins draft `c81faabb…` (box == laptop), in-image suite log `c203a325…`, Phase-A
stop-gate artifact `98f755b9…`.

## Governance consequences acknowledged

`8a87280` freeze SUPERSEDED FOR QUALIFICATION · `68a270e` Phase-A evidence SUPERSEDED ·
qual:1.0/1.1 images DIAGNOSTIC ONLY · 168-pass in-image report VALID DIAGNOSTIC, NOT FINAL ·
realism FAIL artifact PRESERVED IMMUTABLY. Not touched (verified by the diff): solver,
certifier, cascade, tolerances, corpus logic. Not performed: registered 3,895-row execution,
performance computation, validation/OOS access (sealed and unread).

## Awaiting

Delta-review verdict on this exact diff. On approval: new frozen implementation commit →
Linux Phase-A regen from the clean commit → new pinned image with its own full digests →
verify_source zero defects → in-image suite zero fail/zero skip → realism harness from a
fresh output directory, preserving the prior FAIL artifact alongside the new result.
