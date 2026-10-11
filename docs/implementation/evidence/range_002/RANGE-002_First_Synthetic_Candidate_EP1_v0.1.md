# RANGE-002 First synthetic-only implementation candidate: ENG-A1 (v0.1)

| Field | Value |
|---|---|
| Status | **PLANNING DOCUMENT. DRAFT FOR OWNER REVIEW. Nothing here is implemented, authorized, pushed or merged.** 0 decisions approved. |
| Date | 2026-10-10 |
| Starting SHA | `origin/main` **80bdb200** (not a72dd119, which predates #746) |
| Base | `origin/main` **80bdb200** (contains the #746 docs). Verified: `git diff --stat 80bdb200 d61f313a -- apps` is empty, so the code on main is still the d61f313a code. Local branch `docs/range002-impl-readiness`, on top of 9d2e9189 |
| Data accessed | None (local reading; one offline run of the repository's own `ci_classify_changes.py` on a path list) |
| Companion | Implementation Readiness Matrix v0.1 (this branch), sections 2 and 10 |

**Naming.** "ENG-A1" (engineering package A1) is the working name of the first engineering candidate; "ENG-A1b" is the calendar part and "ENG-A2" the schema and accessors part. It was called "EP-1 / EP-1b / EP-2" in earlier drafts; the filenames retain "EP1" for stability and are not renamed again. ENG-A1 is unrelated to **Addendum A1** (the governing-design addendum, unsigned): the prefix ENG marks an engineering package, and the text says "Addendum A1" whenever it means the addendum. ENG-A1 is the first part of the backlog's "PR-A".

**Governing text.** Where this document and the ENG-A1 contract (`RANGE-002_EP1_Implementation_Contract_and_Review_Package_v0.1.md`) differ, the contract governs.

## 1. Re-confirmation, with one revision

**Re-confirmed:** ENG-A1 stays the first synthetic-only candidate. **Revised:** the calendar is split out, so the first package is smaller and independent of the open data-adapter question.

| Package | Content | Why |
|---|---|---|
| **ENG-A1 (first)** | Guard test harness, capability binding helper, look-ahead test utility, and their tests | Needs no P0 decision, no schema or hash change, no dependency, no `data/` package. Produces the negative-test and look-ahead tooling that every later PR's required evidence depends on |
| **ENG-A1b (next)** | Floor-free exchange calendar (`data/calendar.py`) with DST, half-day, holiday fixtures | Independent of ENG-A1; creates the `data/` package, which falls under the Q-B1 conditional approval (data-isolation review) and needs reviewed-pure lint entries, so it should not block ENG-A1 |

## 2. Governing decisions for ENG-A1

- **P0 decisions needed: none.** ENG-A1 reads no spec value, picks no parameter, and records no owner decision. (ENG-A1b injects the half-day offset D05 5g as a parameter and stores no value.)
- **Authorizations needed (not P0 decisions):** the separate written implementation authorization (Q-B2); named reviewers (D08 roles are still unnamed in the register); later push and merge gates (section 9).
- **Not needed for ENG-A1:** option B (D07), the schema batch approval, D19, D06, G10, Q-B1 (ENG-A1 creates no `data/` module), Q-B6 (no dependency).

## 3. Exact code scope

New files only; no existing file is edited.

| File | Content | Public surface |
|---|---|---|
| `apps/backend/app/research/range002/engine/__init__.py` | Empty package marker | none |
| `apps/backend/app/research/range002/engine/_causality.py` | Capability binding helper and one named error | No public callables. One public exception class `CapabilityBindingError(GovernanceError)` with no public methods (allowed by the lint); the helper itself is underscore-private, e.g. `_bind(capability: object, *, spec_sha256, allowed_phases, expected_run_id=None, requested_range=None) -> None`: first calls the merged `results_guard.require_capability` (genuine capability and run still OPEN; its refusal propagates unchanged), then checks `spec_sha256`, `phase in allowed_phases`, that the capability's partition is a **member** of the guard's existing `PHASE_PARTITIONS[phase]` (read from the guard at call time, never copied), `expected_run_id` when given, and `capability.date_range.contains(requested_range)` when a range is given. It reads attributes from the object `require_capability` returns, imports only public governance names, never constructs, copies, caches, returns or revives a capability, and uses no public constants built by a call (R-A2). The contract document `RANGE-002_EP1_Implementation_Contract_and_Review_Package_v0.1.md` governs wherever this row differs |
| `apps/backend/tests/research/range002/_guard_harness.py` | Reusable negative-test generator: given a gated function and a callable that builds valid arguments, runs the matrix in section 4; `EXPECTED_GATED` enumeration check; lint non-vacuity check (strip the decorator from a copy of the source and assert the lint flags it) | Test utilities; tests are not linted |
| `apps/backend/tests/research/range002/_causal.py` | `assert_causal(run_fn, bars, cut)`: runs once on true data and once with every record whose `available_at > cut` replaced by adversarial values, then asserts all outputs with `decision_at <= cut` are identical; includes a deliberately look-ahead variant used to prove the helper fails when it should | Test utilities |
| `apps/backend/tests/research/range002/engine/__init__.py`, `test_causality_binding.py` | Unit tests of `_bind` and the harness | tests |
| `apps/backend/tests/research/range002/governance/test_binding_helper.py` | Public-interface integration test (placed beside `governance/conftest.py` to reuse its seams without cross-package imports) | tests |

No change to `test_import_lint.py` is needed for ENG-A1 (no public callable is added to the app tree); this is why the REVIEWED lists are untouched. Confirm by running the lint in the PR.

## 4. Tests (synthetic only)

**Fixtures:** the existing governance seams (`load_synthetic_view`, `new_registry`, the synthetic signed ledger and manifest path); a tiny in-test function decorated with `requires_capability` that calls `_bind`; synthetic bar/record tuples with `available_at` and `decision_at` for the look-ahead utility. No file, vendor, archive or Sharadar data.

**Unit (private kernel and harness):**
- `_bind` accepts a matching capability; refuses another spec hash, a phase outside `allowed_phases`, a partition removed from the phase table (reachable only through the isolated monkeypatch described in the contract, since `authorize` issues only partitions the table assigns to the phase), a different run id when `expected_run_id` is given, a requested range outside `capability.date_range`, and a range straddling the boundary by one day.
- Harness matrix against a synthetic gated function: no capability; `None`; a look-alike object with copied attributes; `copy.copy`, `copy.deepcopy` and `pickle` of a real capability (each must raise `InvalidCapabilityError`); a capability whose run is closed; a capability for a different spec hash; a capability for a different partition; out-of-range input.
- Harness self-checks (mutation): removing the decorator from a synthetic module is flagged; adding an unlisted public function fails the enumeration check; a look-ahead variant fails `assert_causal`.
- Determinism: seeded property loops use stdlib `random.Random(seed)` only.

**Public-interface integration (through the real guard):** build the synthetic frozen spec, enroll a test registry, open a run, call `authorize(phase=P2, partition=REPLAY_RNG001, requested_range inside the R2 window, ...)`, then call the synthetic gated function with the issued capability: success; then close the run and assert the same call is refused; then repeat with a capability issued for a different run/spec and assert refusal. This exercises the merged contract end to end without touching production manifests.

## 5. Dependencies

No new dependency. Stdlib only (`inspect`, `copy`, `pickle`, `random`, `ast`, `dataclasses`), plus existing pytest. No numpy, no hypothesis, no pandas, no network or file I/O beyond `tmp_path`. RNG: stdlib `random`. Therefore `constraints/**`, root manifests and `ci.yml` are untouched, and the B2 lock-integrity hold does not gate ENG-A1.

## 6. Exact independent-review requirement

The reviewer must not be the author. Required before any push request:
1. **Security-adjacent review of `_causality._bind`** against `results_guard.py` semantics: it must not weaken, duplicate or bypass the guard, must read only public capability slots, and must not import underscore-private governance names (lint R-B).
2. **Validator confirmation of the negative-test matrix** against the bypasses documented in the lint docstring and the guard docstring (look-alike, copy/pickle, closed run, other spec, other partition, out-of-range input); mutation evidence attached.
3. **Look-ahead helper review**: demonstrates that a deliberately look-ahead function fails; adversarial values include both extreme and reordered records.
4. Evidence attached to the PR: pytest output, `ruff check`, `ruff format --check`, `mypy app/research/range002`, `check_research_plane_isolation.py`, lint non-vacuity test result.
The D08 independent validator is not yet named in the register, so a named reviewer must be supplied by the owner (blocker B1).

## 7. CI cost classification

`ci_classify_changes.py`, run offline (local script, JSON path list, no network) on the exact ENG-A1 path list (the two new app files `engine/__init__.py` and `engine/_causality.py`, and the five new test files `_guard_harness.py`, `_causal.py`, `engine/__init__.py`, `engine/test_causality_binding.py`, `governance/test_binding_helper.py`): `backend_code=true`, `mcp_server_code=false`, `mcp_workbench_code=false`, `agent_code=false`, `adr0043_gate=true`. So the PR triggers the LIGHT pass (ruff, mypy, fast invariant scripts including the research-plane isolation check) and the **backend FULL pass** (pytest and coverage gates): FULL is needed because the change is under `apps/backend/**`. Run on this document alone the classifier returns all five flags false (docs only: LIGHT, no FULL). The first earlier run on a slightly different list (which wrongly included an unchanged `test_import_lint.py`) gave the same flags. `adr0043_gate=true` is the classifier's conservative backend attribution, not a claim that ENG-A1 touches the order path. No global pattern is matched (`ci.yml`, root manifests and `constraints/**` are not touched), so no other project is flagged. A docs-only change (like this document) flags nothing beyond LIGHT. Runtime impact is small (no heavy fixtures, no bootstrap).

## 8. Interaction with open work

| Item | Files | Overlap with ENG-A1 | Merge-order effect |
|---|---|---|---|
| **#740** role separation (`8792e043`) | `spec/__init__.py`, `spec/loader.py`, `spec/schema.py`, `scripts/research/range002/freeze_spec.py`, new `tests/.../spec/test_signoff_roles.py` | **None** by file. ENG-A1's integration test uses `load_synthetic_view` and `complete_payload` dynamically (no hardcoded fields) and the synthetic sign-off identifiers are already distinct | Either order works. After #740 merges, rerun the ENG-A1 integration test (sign-off role validation applies to the synthetic freeze) |
| **Schema candidate 76730911** | `spec/schema.py`; tests `spec/_fixtures.py`, `test_hashing.py`, `test_schema.py`, `test_round4_spec.py`, `test_schema_batch.py`; checklist doc | **None** by file. ENG-A1 consumes `complete_payload` through the governance conftest, which keeps working on either side of the schema change | Either order works. Recommendation (not a decision): merge ENG-A1 before the schema candidate so the schema PR's evidence can use the harness |
| Register / docs branches | docs only | None | None |

Residual risk: if either #740 or the schema candidate changes `governance/conftest.py` helpers, ENG-A1's integration test must be rebased; neither touches that file today (checked from `8792e043 --stat` and from the candidate's file list).

## 9. Exact authorizations the owner must give (separate gates)

1. **Implement locally** (Q-B2): "Implement ENG-A1 as specified in RANGE-002_First_Synthetic_Candidate_EP1_v0.1.md on a new local branch, synthetic fixtures only, no new dependency, no push." The Q-B2 ruling is needed for engine/loader work; because ENG-A1 adds an `engine/` package marker and `engine/_causality.py`, the owner should state in writing that this ruling covers ENG-A1 (Recommendation: yes, ENG-A1 contains no strategy kernel and no real data path).
2. **Push** (separate): after local completion and review evidence, "Push branch X to open a PR for ENG-A1", naming the reviewer.
3. **Merge** (separate): after independent review and the walk-away interval (at least 1 hour; recommend 2 hours, as this is guard-adjacent), "Merge PR N". CI green is necessary, not sufficient.
None of these three authorizations implies another.

## 10. Blockers

| # | Blocker | Needed for |
|---|---|---|
| B1 | Independent reviewer / validator not named (D08 roles unnamed) | The review requirement in section 6 |
| B2 | Separate written implementation authorization (Q-B2), explicitly covering the `engine/` package marker | Starting ENG-A1 |
| B3 | Push and merge authorizations | Publishing and merging |
| B4 | Owner confirmation of the ENG-A1 / ENG-A1b split | Scope |
| - | NOT blockers for ENG-A1: P0 decisions, schema approval, option B, D19, D06, G10, Q-B1, Q-B6, lock-integrity hold (#744) | |

## 11. What this document does not authorize

No implementation, no branch creation for ENG-A1, no push, no PR, no merge, no real freeze, enrollment, data access, vendor call or backtest, and no change to any gate, threshold, limit or window.
