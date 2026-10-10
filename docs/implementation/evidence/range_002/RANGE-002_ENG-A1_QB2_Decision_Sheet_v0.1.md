# RANGE-002 ENG-A1: Q-B2 decision sheet (v0.1)

| Field | Value |
|---|---|
| Status | **DECISION SHEET, DOCUMENTATION ONLY. DRAFT FOR OWNER REVIEW.** ENG-A1 is a PROPOSED implementation candidate, not an approved development task. Nothing is implemented, no ENG-A1 branch exists, nothing is pushed or merged. 0 P0 decisions approved; the only owner ruling recorded as given is the narrow Plan section 8 exception (relayed); Q-B2 implementation not given; every signature line is blank |
| Date | 2026-10-10 |
| Base | `origin/main` **1c305b8f** (#747 docs). Checked: `git diff --stat 80bdb200 origin/main -- apps` is empty, so the code on main is unchanged since d61f313a. This sheet is intended to travel with the Stage 3 package once that package is rebuilt on main; it will be added there later. It is not tied to any particular working branch. This sheet has been updated to match the final contract text (18 mutations; `TypeError` versus `CapabilityBindingError`; defense-in-depth partition membership); any earlier documentation review of an older text does not apply to it |
| Governing detail | `RANGE-002_EP1_Implementation_Contract_and_Review_Package_v0.1.md` (part of the same Stage 3 package) governs; this sheet summarizes it for the owner. ("EP1" in filenames is the earlier draft name; the package is ENG-A1.) ENG-A1 is unrelated to Addendum A1 |
| Data accessed | None |

Convention: **planned** means described here and not yet written; **executed** means a test or check has actually run. Today **nothing in this sheet is executed**: no ENG-A1 code or test exists. Every test name below is planned.

## 1. Exact proposed code scope (seven new files, no existing file edited)

| # | Path | Kind |
|---|---|---|
| 1 | `apps/backend/app/research/range002/engine/__init__.py` | app, empty package marker (zero statements) |
| 2 | `apps/backend/app/research/range002/engine/_causality.py` | app, private `_bind` plus one exception class `CapabilityBindingError` |
| 3 | `apps/backend/tests/research/range002/_guard_harness.py` | test utility (negative-test generator, enumeration and lint non-vacuity checks) |
| 4 | `apps/backend/tests/research/range002/_causal.py` | test utility (`assert_causal`) |
| 5 | `apps/backend/tests/research/range002/engine/__init__.py` | test package marker |
| 6 | `apps/backend/tests/research/range002/engine/test_causality_binding.py` | unit tests |
| 7 | `apps/backend/tests/research/range002/governance/test_binding_helper.py` | real-guard integration and anti-bypass tests |

Two app files plus five test files. **The seven-file scope is exact:** no change to existing application files, `results_guard.py`, any other governance module, schemas, manifests or dependency locks (`constraints/**`) without renewed owner authorization. `engine/` contains exactly files 1 and 2: no strategy kernel, no order, fill or price concept, no market-data path. No change to `test_import_lint.py` is needed (no public callable is added to the app tree).

## 2. Authoritative boundaries

- The merged **`require_capability`** (and `authorize`) remain the only source of authorization. `_bind` calls `require_capability` and propagates its refusal unchanged; it adds checks of the caller's expectations (spec hash, phase, partition membership, optional run id, requested range) but **no authorization mechanism**: it grants nothing and its success enables nothing by itself. Refusal order: `require_capability` first (its `InvalidCapabilityError` is propagated unchanged); then explicit argument type checks (step 1b) that raise `TypeError` for wrong argument types (a programming defect, not a refusal; checked after the capability, so a closed-run capability passed with wrong types still raises `InvalidCapabilityError`); then `CapabilityBindingError` for validly typed but unauthorized inputs. Partition membership is **defense in depth, not an independent authorization boundary** (the guard and the registry already pin spec, phase and partition), and a phase missing from the table refuses with `CapabilityBindingError`, never a leaked `KeyError`.
- **`PHASE_PARTITIONS`** (governance model) stays the authoritative phase-to-partition table. `_bind` reads it at call time through a module alias, owns no table, no partition literal and no date window, and the table values are frozensets so the check is membership.
- `_bind` returns `None`; it never constructs, copies, caches, returns or revives a capability.

## 3. Mutation plan: 18 mutations, named killing tests (all PLANNED, none executed)

M1-M12 are the original twelve, preserved (the mutations are unchanged; only the killing-test wording of M1, M8 and M9 (direct `_bind` calls), M4 (isolated copied-table monkeypatch, defense in depth) and M11 (look-ahead dependent only in a later pre-cut output, with a causal control) was made more precise); **M13-M18 are additions** (M13 and M14 from the first audit findings, M15-M17 from the findings on a missing table phase, argument types and broad exception handling, M18 for the ordering of the capability check before the type checks). Numbering is stable. A mutant found equivalent is a plan defect, to be amended before any push request.

| # | Mutation | Planned killing test |
|---|---|---|
| M1 | remove the `require_capability` call (run state) | `test_bind_direct_closed_run_raises` (direct `_bind` call) |
| M2 | remove the spec-hash comparison | `test_bind_refuses_other_spec_hash` |
| M3 | remove the phase check | `test_bind_refuses_phase_not_in_allowed_phases` |
| M4 | remove the partition check (defense in depth; no real capability can reach this branch) | `test_bind_refuses_partition_removed_from_phase_table_monkeypatch` (isolated pytest `monkeypatch` replacing the module attribute with a **copied** table from which the capability's partition is removed; production table untouched; companion `test_phase_partitions_unchanged_after_monkeypatch`). This test proves only that `_bind` follows the module attribute at call time; agreement with what the guard issues is proved by the unpatched test in section 4 |
| M5 | `contains` replaced by `overlaps` | `test_bind_refuses_range_straddling_boundary_by_one_day` |
| M6 | remove the range check | `test_bind_refuses_range_outside_capability_range` |
| M7 | remove the `expected_run_id` comparison | `test_bind_refuses_cross_run_capability` |
| M8 | memoize a successful result (module-level dict keyed by `(id(capability), spec_sha256, allowed_phases, expected_run_id, requested_range)`; a hit returns `None` before step 1) | `test_bind_direct_success_then_run_closed_raises_again` (direct `_bind`; the **same capability object** and an **identical argument tuple** on both calls; call 1 succeeds; the run is then closed through the registry; **call 2 must raise `InvalidCapabilityError`**; nothing clears module state in between) |
| M9 | swallow `CapabilityBindingError` and return | `test_bind_direct_refusal_propagates_original_exception` (direct; the refusal case raises `CapabilityBindingError`) |
| M10 | harness: drop one matrix case | `test_harness_fails_when_a_matrix_case_is_missing` |
| M11 | `assert_causal`: compare only the first output | `test_assert_causal_detects_lookahead_in_a_later_precut_output` (causal control passes the same fixture; failure message names the first differing position, index 1 or greater) |
| M12 | `assert_causal`: skip the adversarial replacement | `test_assert_causal_fails_on_lookahead_function_with_adversarial_replacement` |
| M13 (addition) | copy the phase/partition mapping into `_bind` | `test_bind_follows_monkeypatched_phase_partitions` and `test_causality_module_contains_no_partition_literals` |
| M14 (addition) | read attributes BEFORE calling `require_capability` | `test_bind_non_capability_inputs_raise_invalidcapability_not_attributeerror` (None, a string, a dict, a look-alike with a wrong hash; exact exception type asserted) |
| M15 (addition) | index the table directly (`PHASE_PARTITIONS[phase]`) instead of `.get` plus refusal | `test_bind_refuses_when_phase_missing_from_table_with_capabilitybindingerror` (copied table lacking the capability's phase; must raise `CapabilityBindingError`, never `KeyError`) |
| M16 (addition) | remove the step 1b argument type checks | `test_bind_wrong_argument_types_raise_typeerror` (parametrized over each argument; includes `allowed_phases` given as a bare string, which the mutant would evaluate as a substring test) |
| M17 (addition) | wrap the body in `except Exception` and re-raise as `CapabilityBindingError` | `test_bind_original_refusals_propagate_unchanged` (closed-run capability still raises `InvalidCapabilityError`; wrong types still raise `TypeError`) and `test_causality_module_has_no_broad_except` (AST) |
| M18 (addition) | run the step 1b type checks BEFORE step 1 | `test_bind_closed_run_with_wrong_argument_types_raises_invalidcapability_not_typeerror` (**parametrized over each of the four arguments separately**: `spec_sha256`, `allowed_phases`, `requested_range`, `expected_run_id`; a closed-run capability passed with that one wrong-typed argument must raise `InvalidCapabilityError`, not `TypeError`; **second case**, also parametrized: a `None` capability with a wrong-typed argument must raise `InvalidCapabilityError`; the wrong types are ones step 1b actually rejects, for example `spec_sha256=123`, `allowed_phases` as a bare string, `requested_range` as a tuple, `expected_run_id=123`; per-argument parametrization is needed because a mutant that moves only one type check ahead of step 1 would otherwise survive) |

PR evidence must also list the actual test names (one-to-one) with the mutator output, and **for every mutant record BOTH the intended killing test AND the first test/assertion that actually failed under that mutant** (a mutant can fail an unrelated test first, for example M1 can fail the ordering test incidentally); a surviving mutant blocks the push request.

## 4. Real-guard integration and anti-bypass tests (PLANNED)

- **Lifecycle** (`test_authorize_use_close_invalidate`): through the real `authorize(P2, REPLAY_RNG001, range inside R2)`, use a capability; close the run; the same use is refused; a second use is still refused.
- **Cross-run** (`test_cross_run_capability_refused`): two runs on the same synthetic spec; run A's capability refused when run B is expected.
- **Anti-bypass:** `test_causality_module_has_no_minting_references` (AST: no `authorize`, `ResultsCapability`, `_ISSUE`, `_BOUND_REGISTRIES`, `mark_*`, `open_run`, `close_run`, `enroll_new`, `HoldoutTokenStore`; only public name `CapabilityBindingError`); `test_bind_forged_inputs_raise` (forged, look-alike, `None`, string, dict); `test_undecorated_caller_flagged_by_lint`; `test_refused_authorize_yields_no_capability_to_bind`; `test_phase_partitions_not_rebound_under_app` (exempts the one definition and the two import bindings by AST shape); `test_engine_package_contains_only_marker_and_causality`.
- **Unpatched agreement with the real guard** (`test_bind_agrees_with_guard_issued_capabilities_unpatched`): no monkeypatch; the genuine capability from the real `authorize` for exactly `(P2, REPLAY_RNG001)`, `(P3A, DEVELOPMENT_SELECTION)`, `(P3B, DEVELOPMENT_CONFIRMATION)` and `(P4, HOLDOUT)` passes `_bind` (the issuing helper passes an explicit `requested_range` inside the R2 window for `(P2, REPLAY_RNG001)`, because the guard demands one: `results_guard.py:705-709`; the existing governance suite issues this pair in `test_results_guard.py:295-309`, call at lines 298-306), and the test fails if any of the four is missing (`P5` is refused outright by the guard; other combinations are refused earlier; `P3A`/`P3B`/`P4` need the attempt limits and predecessor evidence that the synthetic seams provide). Companion: `test_phase_partitions_is_one_object_across_model_guard_registry`.
- **Lint pattern:** `test_lint_accepts_governance_model_public_attribute_read` (the module-alias read of the public `PHASE_PARTITIONS`); `test_causality_module_text_avoids_lint_trap_words` (raw source, comments included, avoids the words the lint flags and the partition names).
- **Error classes:** `test_bind_unauthorized_valid_types_raise_capabilitybindingerror`; `test_bind_wrong_argument_types_raise_typeerror`; `test_causality_module_has_no_broad_except`; the ordering test `test_bind_closed_run_with_wrong_argument_types_raises_invalidcapability_not_typeerror` (closed-run capability with wrong types raises `InvalidCapabilityError`).
- Rejection matrix (copy, deepcopy, pickle, forged, closed run, other spec, other partition, out-of-range) via the harness.
- Look-ahead: `assert_causal` passes a causal function and fails a deliberately look-ahead one.
- The merged governance suites must remain green.

## 5. Constraints

Synthetic-only fixtures (existing governance seams and in-test records). **No new dependency**: stdlib and existing pytest only; RNG is stdlib `random`. No market data, no network, no file I/O beyond `tmp_path`. **No schema change and no change to the results guard** or any governance module (the monkeypatch is test-local and auto-restored).

## 6. Reviewer arrangements

| Role | May certify | May NOT certify |
|---|---|---|
| **Engineering reviewer** (not the author; to be named by the owner) | Design and semantics of `_bind`; that it calls `require_capability` and re-implements nothing; typing and lint conformance; completeness of the planned tests and the 18-mutation evidence; that the PR matches this sheet | Independence or validation in the D08 sense; any P0 or governance sign-off; that the research design is valid |
| **D08 independent validator** | The formal validation record (independence, adequacy of the negative-test matrix and mutation evidence as validation evidence) | Nothing before appointment |

**Owner's reviewer ruling.** The independent engineering reviewer must be a **separately assigned person or instance with no authoring responsibility for the ENG-A1 code**. A qualified human is preferred; if an AI agent is assigned, its independence limitations must be documented and **independent CI evidence** is required. The position is **VACANT until a qualified reviewer accepts**. The AI documentation reviewer (6.1) is only a **supporting technical reviewer**: it may review diffs, run local tests and evaluate mutation coverage, and it is **not the sole reviewer satisfying Q-B2**.

The formal D08 independent-validator appointment is **unresolved: names are blank**. An engineering review must never be described as D08 validation. The owner must name the engineering reviewer before a push request.

### 6.1 The independent documentation review (precondition (a)): what it is and is not

It is an **AI-agent documentation review** of the exact decision sheet, identified by the reviewed commit or review pass. It is **not** D08 independent validation, **not** engineering validation of code (none exists), and it **cannot certify** Linux acceptance, GitHub-hosted CI results, hostile in-process behaviour, or research validity. Its role is limited to checking the sheet's internal consistency, its fidelity to the contract and the merged code facts it cites, and the absence of overstated claims.

## 7. Required checks (from `ci.yml` and the classifier)

Classifier (offline run on the exact seven paths): `backend_code=true`, `mcp_server_code=false`, `mcp_workbench_code=false`, `agent_code=false`, **`adr0043_gate=true`**. **Backend FULL is needed.** Checks: `ruff check .`; `ruff format --check` (local evidence); `mypy`; `check_research_plane_isolation.py` and the other fast invariant scripts; backend FULL `pytest -q --cov --cov-branch` with the branch-coverage scripts; the **ADR 0043 coverage step** (because `adr0043_gate=true`; it is the classifier's conservative backend attribution, not a claim that ENG-A1 touches the order path); the **RANGE-002 Linux acceptance step** (path filter `range002` matches; `ci_verify_required_tests.py` against `range002_required_linux_tests.json`): **no manifest entry is added, changed or removed**, and no listed test is renamed or skipped; `Python CI Gate`. Status today: **none executed** (no code exists).

## 8. Walk-away

Two hours between "ready for review" and any merge of the eventual code PR (guard-adjacent; the repository minimum is one hour).

## 9. Three separate approvals (none implies another)

**Plan section 8 sequencing exception: narrow owner ruling (GIVEN, relayed).** "ENG-A1 may be considered for implementation ahead of the normal Plan section 8 sequence solely as a synthetic-only causality-binding helper and test package. This ruling does not authorize implementation now, is not approval of a trading engine, additional research phases or any formal P0 decision, and remains subject to the final Q-B2 local-implementation authorization (exact seven-file scope, engineering-review requirements); it permits no change to existing guard code, governance modules, schemas, manifests, dependency locks or real market-data access." **Q-B2 implementation remains unapproved until separately authorized.** The seven-file boundary and the original twelve mutations M1-M12 are unchanged by this ruling (the plan now contains 18 mutations, see section 3).

Wording templates for the owner to adapt; each requires the owner's own signature and date.

1. **Local implementation (Q-B2).** *Acknowledged deviation:* this is a documented deviation from the Plan section 8 sequencing, for which the merged backlog requires an explicit owner ruling; **ENG-A1 is a synthetic test/helper package, not an approved engine.** Approval 1 may be given only when **both preconditions** hold: (a) a completed independent documentation review of the exact decision sheet (reference to the reviewed commit/pass: ______; this is an AI-agent documentation review with the limitations listed in section 6.1), and (b) a named engineering reviewer who is NOT the author of the code (need not be the D08 validator; name currently blank). Wording: "I authorize implementing ENG-A1 exactly as specified in `RANGE-002_EP1_Implementation_Contract_and_Review_Package_v0.1.md` and `RANGE-002_ENG-A1_QB2_Decision_Sheet_v0.1.md`, on a new local branch, the seven listed files only, synthetic fixtures only, no new dependency, no market data, no schema or results-guard change, no push. This approval covers the `engine/` package marker. It does not authorize a push, a pull request or a merge. I acknowledge that this is a documented deviation from the Plan section 8 sequencing and that ENG-A1 is a synthetic test/helper package, not an approved engine. The seven-file scope is exact: no change to any existing application file, `results_guard.py`, schema, manifest or dependency lock without renewed authorization. Preconditions satisfied: independent documentation review of this exact sheet (reviewed commit/pass reference: ______); engineering reviewer (not the code's author): ______. Signed: ______ Date: ______"
2. **Push and open PR.** "I authorize pushing branch ______ and opening a pull request for ENG-A1. The engineering reviewer is ______. This does not authorize a merge. Signed: ______ Date: ______"
3. **Squash-merge.** "I authorize squash-merging PR ______ for ENG-A1 after the review evidence, green required checks and the two-hour walk-away. Signed: ______ Date: ______"

## 10. Preconditions and blockers

| # | Item | State |
|---|---|---|
| 1 | Q-B2 local-implementation approval (approval 1) | Not given |
| 2 | Independent engineering reviewer: a separately assigned person/instance with no authoring responsibility for the ENG-A1 code (need not be the D08 validator) | **VACANT** until a qualified reviewer accepts (name blank) |
| 2a | Independent documentation review of the exact, UPDATED decision sheet (reference to the reviewed commit/pass; AI-agent review, limitations in 6.1) | Required before approval 1. **No earlier review applies to this updated text**; the reference placeholder in approval 1 is to be filled only with the fresh review of this exact text |
| 2b | Plan section 8 sequencing exception | **GIVEN in narrow form** (ruling text in section 9). **Q-B2 local-implementation authorization itself: NOT given**; implementation remains unapproved until separately authorized |
| 3 | D08 independent validator appointed | Unresolved; names blank (needed only for a formal validation record) |
| 4 | Q-B1 | Needed only for ENG-A1b (`data/calendar.py`), not for ENG-A1 |
| 5 | Open PR #740 (role separation, `8792e043`) | **No file overlap** with ENG-A1 (it edits `spec/__init__.py`, `loader.py`, `schema.py`, `freeze_spec.py`, and adds `test_signoff_roles.py`). Merge order either way; **rerun the ENG-A1 integration test after #740 merges** |
| 6 | Schema candidate `76730911` | **No file overlap**. Merge order either way; recommend ENG-A1 before the schema candidate so its evidence can use the harness |
| 7 | Push and merge approvals (approvals 2 and 3) | Not given |

## 11. What ENG-A1 does NOT unlock

It unlocks no research work: not ENG-A1b (calendar, blocked by Q-B1), not ENG-A2 (schema; separate approval and option B), not any engine kernel, loader, universe, statistics, gate, control or pipeline package, not any real freeze, enrollment, manifest approval, P0 decision, data access, vendor call, backtest, P3/P4 run or P5. It does not satisfy or replace the D08 validator appointment, change any gate, threshold, limit or window, or authorize the schema batch. Approving ENG-A1 does not approve any later package.
