# REVIEW_PACKET_RANGE-002 — reviewer packet for PR #755

| Field | Value |
|---|---|
| Status | **PREPARATION. NOT A REVIEW. NOT AN APPROVAL.** `[MERGE NOT APPROVED]` |
| Reviewer (per owner instruction rev. 2) | **Jay Wang**, non-author code reviewer; dual role (owner / gate-setter) disclosed. Independence for the run is supplied by the validator (陈友潼, PENDING acceptance), whose sign-off the owner may not hold or waive. The ruling text is in the separate draft PR `docs/range002-owner-ruling-code-review`; its merge is the signature. |
| PR | #755 `feat/range002-screen-kernel` → `main` (draft title carries `[MERGE NOT APPROVED]`) |
| Commit under review | `1ecf811b0b4ed7699bb4650c22387e1242f98e74` (48 files, +6,597 / −1) |
| CI evidence | run #1851 (id 38277001415): LIGHT pass · FULL pass (29m18s) · ADR 0043 gate pass · Linux acceptance 1,041 passed, required-test verifier `required=33 collected=33 passed=33 failed=0 skipped=0 missing=0` · Python CI Gate pass. Run #1850 (draft) is red **by design**: CI runs zero jobs on a draft (`ci.yml:63-64`). |
| Established | The change set passes the repository's automated checks on that exact SHA. |
| NOT established | Correctness beyond what the tests encode; independence of review; anything about real data. Nothing here touches market data. |

## 1. Walk-away and reviewer state (from PR timestamps)

| Item | Value |
|---|---|
| PR created (draft) | 2026-10-12T16:22:19Z |
| Marked ready for review | **2026-10-12T16:22:58Z** (GitHub timeline `ready_for_review`) |
| Walk-away (2 h, guard-adjacent) clears | **2026-10-12T18:22:58Z** |
| Evaluated at | 2026-10-12T17:06:45Z → 44 min elapsed, ~76 min remaining: **NOT elapsed** (re-evaluate against the GitHub API timestamp, not this line) |
| Reviews on the PR | 0 · requested reviewers: none at the time of writing |
| GitHub identity that authored the commits and opened the PR | **`jayw04`** — `jayw04 <37512854+jayw04@users.noreply.github.com>` is the author AND committer of every commit on the branch (`1ecf811b`), and the PR was opened by `jayw04`. This is the owner's own account. |
| Consequence, stated plainly | GitHub **will not let `jayw04` approve a PR authored by `jayw04`**, and it will not accept a review *request* to the PR author. The owner-ruling statement "Jay Wang authored none of the guard-adjacent changes" is a ruling about who wrote the code; the repository metadata records the owner's account as author. Both are true at once, and the metadata is what GitHub enforces. |
| Options (owner ruling needed; neither implemented) | **(1)** Re-push the same tree under a separate bot/machine identity (the PR author then differs from the reviewer). **(2)** Keep the commits and record an owner-ruled, comment-based review with a branch-protection exception (the owner's per-file comments below are the review evidence; the exception is the owner's act). |

## 2. Guard-adjacent files: what changed, invariant, proof, riskiest lines

CI result for every test below: part of the Linux acceptance step, **1,041 passed, 0 failed, 0 skipped** on `1ecf811b` (#1851). Names are pytest functions under `apps/backend/tests/research/range002/`.

### 2.1 `governance/results_guard.py` (+30)
- **Changed:** a `profile` field is carried on the guard view and the capability; `_KNOWN_PROFILES = {"full","screen"}`; `_SCREEN_PROFILE_ALLOWED = {(P2, REPLAY_RNG001), (P3A, DEVELOPMENT_SELECTION)}`; two refusals.
- **Invariant:** a screen-profile spec can never authorise P3B, P4/HOLDOUT, P5/PAPER or anything new, and an unknown profile never reaches state-changing code.
- **Proof:** `governance/test_screen_profile.py::test_screen_spec_refused_for_every_other_phase`, `::test_unknown_or_missing_profile_on_a_view_is_refused`, `::test_screen_spec_authorises_p2_replay_and_p3a_and_binds_profile`, `::test_unsigned_exposure_ledger_still_refused_for_screen_p3a`, `::test_screen_p3a_completion_does_not_satisfy_a_full_specs_phase_order`, `::test_closed_run_capability_of_a_screen_spec_is_not_reusable`.
- **Read first:**
  1. `results_guard.py:389` `if spec.profile not in _KNOWN_PROFILES:` — fail-closed ordering; confirm it runs before any registry write.
  2. `results_guard.py:696` `if spec.profile == "screen" and (phase, partition) not in _SCREEN_PROFILE_ALLOWED:` — the only reachability gate; confirm it sits before `mark_capability_issued`.
  3. `results_guard.py:814` `profile=spec.profile,` — the capability's profile must come from the same view that was checked.
- **Reviewer question:** a screen P3A capability is `citable=True` and consumes the shared P3A attempt budget and exposure. Intended?

### 2.2 `governance/spec_adapter.py` (+5) and `spec/loader.py` (+2)
- **Changed:** `profile` is added to the guard view fields, its constructor and `to_guard_view`; `SpecView.profile` is derived from the declaration.
- **Invariant:** the profile the guard sees is exactly the profile inside the hashed spec.
- **Proof:** `test_screen_spec_freezes_with_exempt_fields_null_and_loads_as_screen`, `test_profile_is_inside_the_hash_and_full_hash_is_unchanged`, `test_unknown_or_altered_profile_declaration_is_refused`.
- **Read first:**
  1. `loader.py:175` `profile="full" if spec.profile is None else spec.profile.name,`
  2. `spec_adapter.py:119` `profile: str = "full",` — a **defaulted** parameter: confirm the default is the strict direction (it is `full`) and that no caller can reach `screen` by omission.
  3. `spec_adapter.py:187` `profile=view.profile,`

### 2.3 `spec/schema.py` (+193 / −1)
- **Changed:** `profile` declaration models (v1 `ScreenProfileDecl`, v2 `ScreenProfileDeclV2`), `SCREEN_V1_*` and `SCREEN_V2_*` field lists with pinned digests, `unset_p0_fields` honours the profile's required list, `hashable_payload` omits `profile` when absent.
- **Invariant:** full-profile hashes are byte-identical to before; a screen spec's required list is an exact, hash-pinned partition of the P0 fields; nothing the guard reads is deferrable.
- **Proof:** `test_required_and_exempt_partition_the_p0_field_set_exactly`, `test_same_content_without_profile_is_the_full_profile_and_refuses`, `test_missing_required_value_refused_by_name`, `test_full_profile_frozen_file_carries_no_profile_key`, `test_skeleton_is_unchanged_and_has_no_profile`, and for v2: `test_v2_partitions_the_p0_fields_exactly_and_derives_from_v1`, `test_nothing_the_guard_or_kernel_reads_is_deferred_or_unmodelled`, `test_v2_spec_freezes_and_is_authorised_for_p3a_by_the_real_guard`, `test_v2_hash_differs_from_v1_and_pins_the_unmodelled_set`, `test_a_v2_spec_missing_a_guard_read_field_is_refused_at_freeze`.
- **Read first:**
  1. `schema.py:43` `_NON_P0_NULLABLE = frozenset({"registration.trial_ledger_id", "profile"})` — widens what the unset-walk skips.
  2. `schema.py:716` `payload.pop("profile", None)` — the line that keeps full-profile hashes unchanged.
  3. `schema.py:725` `SCREEN_V1_REQUIRED if self.profile.version == 1 else SCREEN_V2_REQUIRED` — the only place the required list is selected; the `else` branch means any future version would silently take v2's list (the declaration models pin versions 1 and 2, so it is unreachable today).
- **Reviewer question:** v2 defers `stats.*`/`controls.*`; a later spec that sets them has a different hash. Accept, or require them at freeze?

### 2.4 `scripts/research/range002/freeze_spec.py` (+2)
- **Changed:** omit a null `profile` from the frozen payload.
- **Invariant:** a full-profile frozen file is unchanged byte for byte.
- **Proof:** `test_full_profile_frozen_file_carries_no_profile_key`.
- **Read first:** `freeze_spec.py:94-95` — it must mirror `schema.py:716` exactly or hashes diverge between freeze and load.

### 2.5 `governance/errors.py` (+8)
- **Changed:** `ProfileNotRecognizedError`, `ProfileNotAuthorizedError`.
- **Invariant:** refusals are typed and distinct. No logic.
- **Read first:** `errors.py:253`, `errors.py:257` (class bodies only).

### 2.6 `tests/.../governance/test_import_lint.py` (+13) — **a trust list**
- **Changed:** 13 entries added to `REVIEWED_PURE` for the new `data.*` and `screen.*` pure functions.
- **Invariant:** only reviewed callables are exempt from `@requires_capability`. **Adding an entry is a reviewed change to this file** (its own docstring says so).
- **Proof:** `governance/test_import_lint.py::test_real_range002_tree_complies` (and `test_round6_pr3::test_nf6_the_real_tree_is_clean`).
- **Read first:** each of the 13 `f"{PKG}.data.…` / `screen.…` entries against the function body: *no price/return value may flow out*. In particular `data.manifest:verify_snapshot_files` and `data.store_adapter:open_snapshot` (open a connection) deserve the closest read.

### 2.7 `tests/.../spec/test_schema.py` (+9)
- **Changed:** `_OPTIONAL_NON_P0 = {("DraftSpec","profile")}` — the single field allowed a default.
- **Invariant:** R9 (no developer-chosen defaults) still holds for every P0 field.
- **Proof:** `spec/test_schema.py::test_no_field_has_a_default`.

## 3. Non-guard files in the same PR (context only)
`screen/*` (kernel, stats, scheduler, criteria, selection, coverage), `data/*` (identity map, PIT universe, manifest, store adapter, bar loader, mock fetch adapter), `scripts/…/pit_coverage_ro.py`, tests, and 3 lines of `.gitignore`. They are capability-gated by construction (`test_capability_after_closure.py` sweeps 19 entry points), but they are **not** the review's trust boundary.

## 4. Known limits, stated plainly
- Authorship of the pre-existing guard edits in this tree is **unknown**; the PR is committed under the owner's GitHub account.
- Python privacy and the import lint are developer safeguards, not an access boundary (module docstrings say so).
- The kernel carries a new baseline (SKIP at/after the EOD cutoff); a RUN needs a spec hash frozen against it.

## 5. Reviewer action needed
Per the owner's instruction the review request goes to Jay Wang once the ruling PR exists and this packet is complete. It cannot be satisfied through GitHub's review mechanism while the PR author is `jayw04` (section 1); the owner must choose option (1) or (2). Until then: **NEEDS-OWNER**.

## 6. Per-file review comments (to be filled in by the reviewer)
The ruling requires one comment per file: invariant, proving test, lines read, verdict. **A bare approval does not satisfy the gate.** Verdict values: `ACCEPT` / `ACCEPT-WITH-FIXES` / `REJECT` / `NOT READ`. Pre-filled "proving test" and "lines to read" are the author's pointers (sections 2.x), not the reviewer's finding.

| File | Invariant (reviewer's words) | Proving test (name) | Lines read (ranges) | Verdict | Notes |
|---|---|---|---|---|---|
| `governance/results_guard.py` | | | | | |
| `governance/spec_adapter.py` | | | | | |
| `spec/schema.py` | | | | | |
| `spec/loader.py` | | | | | |
| `scripts/research/range002/freeze_spec.py` | | | | | |
| `tests/.../governance/test_import_lint.py` | | | | | |
| *(extra, not in the ruling)* `governance/errors.py` | | | | | |
| *(extra, not in the ruling)* `tests/.../spec/test_schema.py` | | | | | |

Reviewer: ______________________  Date (UTC): ______________  Commit reviewed: `1ecf811b`…

## 7. Reviewer assignments (compact; the owner names reviewers; no appointment is invented)

Legend: **Author exclusions** apply to every row: the code author is Claude Code (agent); the commits are recorded under `jayw04` until any re-creation (a different GitHub identity is needed for GitHub to accept an approval); no agent session is an eligible reviewer; 梁云鹏 (liaison) holds no sign-off of any kind. Nothing here contacts anyone. A new head SHA restarts CI, the review and the walk-away (R4).

| PR / pinned head (full) | What it changes | Required qualifications | Exclusions beyond the common ones | Review scope | Governing independence requirement | Assigned |
|---|---|---|---|---|---|---|
| **#755** `1ecf811b0b4ed7699bb4650c22387e1242f98e74` (CI #1851 green; head changes on re-creation) | Guard-adjacent: `results_guard`, `spec_adapter`, `schema`, `loader`, `freeze_spec`, import lint; plus kernel/data (non-guard) | Reads Python governance code and pytest; can judge screen-profile reachability, hash binding, fail-closed ordering | Not the author account; the review is not a validator sign-off | Per-file comments on the six named files (invariant / proving test / lines read / verdict) using section 6; a bare approval does not satisfy the gate | Owner ruling #756 points 2-5: non-author reviewer, dual role disclosed, per-file evidence, 2-hour walk-away; run independence is supplied separately by the validator (not waivable by the owner) | Named in the ruling: Jay Wang. **Others: owner to name.** |
| **#759** `279e5a813c4445bf40e836a3338dcfa255424902` (CI on this head: running; evidence for code at `ccc71455…` is historical) | DENY-default authorization checker + question/snapshot/fetch-scope drafts; **not** guard-adjacent | Python reading; able to judge whether vendor-terms statements are accurate to the cited pages | Not the author account; owner is the sender of vendor questions, so owner review is of accuracy, not of permission | DENY logic (no path reads absence as consent); accuracy of sections A-G; staged scope minimality | No gate sign-off; a standard non-author review. The vendor-use *decision* is the owner's act, recorded in Git | **Owner to name** |
| **#760** `b1a38d8e7290425b1206bb90e347caace04a17f2` (CI #1859 green, unchanged) | Identity probe harness + hash-pinned pre-registration; **not** guard-adjacent | Python and methodological reading (labels, blocking rule, non-vacuity, fail-closed controls) | Not the author account | Probe scope; pre-registration binding (SHA-256 `116a0601ff29374a38c4290cc355c506374c7137d420c908a15b76e91e3a17fc`); negative controls; CLI authorization gate | The validator (陈友潼, PENDING acceptance = VACANT) must see the pre-registration **before any probe output exists** | Code review: **owner to name.** Methodological: validator, once accepted |
| **Hazard-fix PR** (`fix/range002-build-hazards`, stacked on #755 `1ecf811b…`; **not pushed, no PR**) | Edits `spec/schema.py` (**guard-adjacent**) plus kernel/data/tests; closes hazards A-D | As #755, plus judgement of new P0 fields' hash binding and profile digests | Not the author account; its reviewer need not be #755's, but must review its own final head | A-D diffs, converted regression tests, retained negative tests, v2 digests; no change to #755's reviewed files | Same as #755 (guard-adjacent): per-file evidence, exact-SHA CI, walk-away; advisory input from 肖学焦 on the per-trade unit (no gate) | **Owner to name** |

Pending regardless of assignment: validator 陈友潼 and 方炳雄 acceptance records; PR #740 merged before any sign-off counts GENUINE (R3).
