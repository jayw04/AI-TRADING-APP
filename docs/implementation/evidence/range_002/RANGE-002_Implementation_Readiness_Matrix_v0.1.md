# RANGE-002 Implementation Readiness Matrix and PR Execution Plan v0.1

| Field | Value |
|---|---|
| Status | **PLANNING DOCUMENT. DRAFT FOR OWNER REVIEW. Nothing here authorizes implementation, a push, a merge, a real freeze, an enrollment, data access, a backtest or any run.** 0 decisions approved, no signatures. |
| Date | 2026-10-10 |
| Starting SHA | Original matrix: `origin/main` **a72dd119**; current main for all later updates and for ENG-A1 planning: **80bdb200** (contains the #746 docs). `origin/main` a72dd119 (PR #745 docs merged; `apps/backend` is byte-identical to `d61f313a`, verified: `git diff --stat d61f313a a72dd119 -- apps` is empty) |
| Branch | `docs/range002-impl-readiness` (local, created from a72dd119; PR #746's branch untouched) |
| Data accessed | None. Local file reading, and the repository's own offline lint/test scripts were previously run by me on candidates; no SDK, key, network, data, registry, enrollment or freeze in this work |
| Sources | Merged code under `apps/backend/app/research/range002/{spec,governance}`; `scripts/research/range002/freeze_spec.py`; schema candidate **76730911** (`feat/range002-schema-batch`, local); Backlog v0.1 Parts I-IV and Schema Change Batch Proposal (branch `docs/range002-p1-p2-backlog`, head 97dd7edc); Agent A's `RANGE-002_OD_Followups_v0.1.md` at **e5bd0bfc** (K1-K7); P0 Decision Register v0.2 (merged) |
| Convention | "Recommendation (not a decision)" marks proposals. File:line citations are to `origin/main` a72dd119 unless stated |

> **ERRATUM AND PRECEDENCE (Stage 3 owner disposition, C1/F1). The final ENG-A1 contract (`RANGE-002_EP1_Implementation_Contract_and_Review_Package_v0.1.md`) and the final Q-B2 decision sheet (`RANGE-002_ENG-A1_QB2_Decision_Sheet_v0.1.md`) GOVERN ENG-A1 implementation scope. Wherever this matrix describes ENG-A1 differently, the contract and the sheet prevail.**
>
> **Excluded from ENG-A1 / Q-B2:** calendar implementation; `data/calendar.py` (no `data/` package is created); any modification of existing lint-list files, including the REVIEWED lists in `test_import_lint.py`; and the `pandas-market-calendars` dependency. The matrix text below that says "harness and calendar", lists `data/calendar.py`, lists the REVIEWED lists in `test_import_lint.py`, or refers to the existing `pandas-market-calendars` library as part of ENG-A1 (the ENG-A1 row in section 2.1, the recommendation text in section 2.2, the first row of the section 6 plan, and the ENG-A1 row of the section 10.3 dependency matrix) is the **pre-split description and does not apply to ENG-A1**. Calendar work remains separately governed as **ENG-A1b** and is not part of Q-B2.
>
> **Unchanged:** the ENG-A1 boundary is the exact seven-file scope stated in the contract and the sheet, and the planned mutation count is eighteen (M1-M18, planned and not executed). Nothing in this erratum authorizes implementation, a push, a merge, or any P0 decision; P0 remains NO-GO with 0 approved decisions and blank signatures.

---

**Naming.** "ENG-A1" (engineering package A1) is the working name of the first engineering candidate; "ENG-A1b" is the calendar part and "ENG-A2" the schema and accessors part. It was called "EP-1 / EP-1b / EP-2" in earlier drafts; the filenames retain "EP1" for stability and are not renamed again. ENG-A1 is unrelated to **Addendum A1** (the governing-design addendum, unsigned): the prefix ENG marks an engineering package, and the text says "Addendum A1" whenever it means the addendum. ENG-A1 is the first part of the backlog's "PR-A".

## 1. C1 Reconciliation of schema and contracts

### 1.1 The four layers (never mix them)

| Layer | Meaning | Items |
|---|---|---|
| **(a) MERGED** requirements and behaviour on main | Code that runs today | Spec schema with `extra="forbid"`, required keys, no defaults; **66 unset P0 leaves** that block a freeze; `p5.account_id` is a required P0 field; `spec_sha256` covers everything except `signoff`; freeze refuses without an owner-approved manifest (genesis + P3 limits equal to the spec's); guard `authorize` (all checks in 1.3); hash-chained run registry with enrollment; holdout token store; exposure ledger; `Verdict` enum; audit-pack header; P5 refused outright |
| **(b) PROPOSED schema candidate** | Local, unmerged, reviewed | 76730911: 20 owner-valued new leaves + `p5.account_binding` replacing `p5.account_id` + 2 fixed `controls.stage1_criteria` members; per-family exit param vocabulary; `population.matching` canonical order; **no per-candidate rank**. Unset P0 leaves: **86** |
| **(c) OWNER-DIRECTED but UNSIGNED** | Direction given, nothing signed | Option B for P5 (PROPOSED / NOT APPROVED; owner direction, unsigned); batched schema PR before any freeze (Q-B4); read-side capability gate as Level 1 direction subject to the data-isolation review (Q-B1); G10 comparator policy directions (pre-P3a binding, revalidation before P4, no new `Verdict` member, failed G10 does not alter P4 statistics); `data.fetch_mode` left undefined; D19 within-family tie-break escalated, not decided; D06 new controls need individual definitions and independent review; the six owner-only values (budget cap D03, lineage constants OD-1, redundancy set OD-3, diagnostic windows D13, halt evidence D05 5h, risk units D05 5j) |
| **(d) Implementation needing EXPLICIT P0 APPROVAL** | Cannot start as binding work without a signed decision | Merging the schema candidate; any value for an unset P0 field; the params adapter on real values; real freeze; registry enrollment; manifest approval; the G10 binding field; any code that reads real data or runs P3/P4; the loader's real pulls; the executor |

### 1.2 Enumeration: 66 required leaves on main versus 86 in the candidate

Method: for each of `origin/main` (code identical to d61f313a) and candidate 76730911, import `draft_skeleton()`, validate with `parse_draft`, and list `unset_p0_fields()` (null or blank leaves; `registration.trial_ledger_id` is exempt via `_NON_P0_NULLABLE`, `signoff` is checked separately). Results: main 66, candidate 86; skeleton leaves 107 versus 129.

**Main (a), the 66 required leaves:** `controls.naive_orb.definition`, `controls.random_entry.invalid_draw_policy`, `controls.random_entry.repetitions`, `controls.random_entry.seed`, `costs.accounting_mode`, `costs.components`, `data.fetch_mode`, `data.vendor`, `diagnostics.taxonomy`, `execution.ack_latency_ms`, `execution.bar_timestamp_convention`, `execution.crossed_before_arm_policy`, `execution.eod_lead_s`, `execution.order_reservation_policy`, `execution.order_type`, `execution.stop_protection_policy`, `execution.submit_latency_ms`, `execution.tie_break`, `execution.vendor_delay_ms`, `exit.halfday_offset_min`, `exits.candidates`, `exits.complexity_order`, `exits.selection.eligibility.min_pf`, `exits.selection.eligibility.min_trades`, `exits.selection.score`, `exits.selection.stop_test`, `exits.selection.tie_tolerance_r`, `fill.halt_policy`, `fill.slippage_model`, `gates.basis`, `gates.max_dd`, `gates.trade_unit`, `gates.win_rate`, `gates.yearly`, `governance.economic_thesis_sha`, `governance.exposure_signed`, `governance.registry_genesis_id`, `governance.roles`, `p3.criteria`, `p3.max_p3a_attempts`, `p3.max_p3b_attempts`, **`p5.account_id`**, `p5.cost_ratio_contract`, `p5.degradation_tolerance`, `p5.shadow_acceptance`, `registration.related_programs`, `risk.daily_loss_limit`, `risk.fill_risk_tolerance`, `risk.gross_cap`, `risk.max_concurrent`, `risk.max_participation`, `risk.per_name_cap`, `risk.per_trade_pct`, `signal.min_or_width_ticks`, `signal.or_completeness_rule`, `stats.alpha_one_sided`, `stats.bootstrap.block_len`, `stats.bootstrap.ci_type`, `stats.bootstrap.confidence_level`, `stats.bootstrap.method`, `stats.bootstrap.reps`, `stats.bootstrap.seed`, `stats.hypothesis_family`, `stats.regime.criterion`, `stats.regime.definition`, `universe.n`.

**Candidate (b) delta, 66 + 21 - 1 = 86:**
- Removed (1): `p5.account_id`.
- Added owner-valued (20): `data.adjustment`, `data.minute_reconciliation.volume_tolerance_frac`, `data.minute_reconciliation.reference`, `data.coverage_min`, `data.exclusion_bound`, `risk.initial_equity`, `risk.equity_basis`, `risk.over_budget_rule`, `controls.random_entry.population.unit`, `.instants`, `.matching`, `controls.time_shuffle.method`, `.min_shift_days`, `.reps`, `controls.no_information.kind`, `.lo`, `.hi`, `.reps`, `controls.stage1_criteria.negative_control_mode`, `.negative_control_alpha`.
- Added, tracked separately (1): `p5.account_binding` (conditional option B).
- Fixed, non-owner, not counted as unset (2): `controls.stage1_criteria.invariants`, `.on_fail`.

Per-section check (main -> candidate unset): controls 4 -> 16, data 2 -> 7, risk 7 -> 10, p5 4 -> 4 (swap), all other sections unchanged; total 66 -> 86.

**P5 position (stated once, kept consistent):** `p5.account_id` **is the current merged requirement** and stays so until the candidate is approved and merged. `p5.account_binding` is **conditional on option B**, which is PROPOSED / NOT APPROVED. If option B is not approved, `p5.account_id` stays and the account-timing conflict (D07 sheet, register s22) remains an open owner item.

**Compatibility finding:** PR #740 is not on main (main code is unchanged since d61f313a); its relation to `schema.py` and `loader.py` must be re-checked at rebase time. A G10 policy field (section 5) would make the count 87 (K6).

### 1.3 Merged contract reference (what the guard enforces today)

`authorize` order, from `governance/results_guard.py` (a72dd119): refuse `budget_reset_authorization` and `independence_authorization` first (always); trusted spec/registry/ledger/store types; frozen+signed spec; manifest genesis approved and equal to registry and spec genesis; partition/phase closed sets; P5 refused outright (`:673`); D17/D19 fields set for development and holdout partitions; phase order from registry rows and predecessor artefacts (`_check_phase_order`, `:439`, called at `:693`); partition range free of R2, spec exposed windows and the signed ledger (`_check_free_range` `:384`, `:709`; `_check_exposure_binding` `:408`, `:727`); an OPEN registry row matching spec/phase/partition (`:736`); P3A/P3B attempt budget (`_check_attempt_limit` `:538`, `:756`); holdout unopened and valid token (`:578`, `:760`); `mark_holdout_authorized` durably before the two-phase token consume (`:764-765`); `mark_capability_issued` before the capability is returned (`:768`). Freeze (`scripts/research/range002/freeze_spec.py` `freeze` `:60`): refuses an existing output, an unapproved manifest (`require_genesis`, `require_limits`), unset P0 fields, mismatching genesis/limits, or missing sign-off.

---

## 2. C2 Review of PRs A-H

Common gates for every PR below: (1) no implementation starts without a separate written authorization (Q-B2); (2) synthetic fixtures only; (3) the guard-coverage proof (backlog 1.4) and both test layers (unit on private kernels, public-interface integration through `authorize` with the governance test seams); (4) backend FULL CI per PR, no change to `ci.yml`/`constraints/**`; (5) **no push, PR or merge without explicit owner authorization**, a stated reviewer, and the repository walk-away interval (at least 1 hour; longer for governance-adjacent changes); (6) an independent reviewer who did not author the PR.

### 2.1 Readiness matrix

| PR | Files / modules affected | Functional boundary | Depends on (PRs) | P0 decisions | Synthetic fixtures | Expected acceptance evidence | Independent review required | Push/merge gate |
|---|---|---|---|---|---|---|---|---|
| **ENG-A1** (proposed split: harness and calendar) | new `tests/research/range002/_guard_harness.py`, `_causal.py` (look-ahead helper), `engine/_causality.py` (binding helper), `data/calendar.py`; REVIEWED lists in `test_import_lint.py` | No schema or hash change; no returns; pure calendar and test utilities | none | none for the code; calendar half-day offset value D05 5g is injected, not read | DST weeks, half days, closure day, library-missing simulation; synthetic gated function pair | Harness negative-test generator demonstrated; mutation test: a look-ahead variant fails `assert_causal`; calendar fixtures with independently computed expectations | Second person recomputes calendar expectations; validator reviews the harness | Owner authorization to implement; reviewer named; walk-away |
| **ENG-A2** (proposed split: schema and accessors) | `spec/schema.py`, `spec/loader.py`, new `spec/engine_params.py`, `spec/__init__.py`, `_fixtures.py` and all spec/governance tests that consume `complete_payload` | Spec contract: new required keys, `SpecView` frozen section accessors, `to_engine_params`; hash payload changes pre-freeze | ENG-A1 (harness); candidate 76730911 as the base | Schema-batch approval (Q-B4 follow-up); option B (D07) to include `p5.account_binding`, else keep `p5.account_id`; D19 vocabulary and tie-break; OpenValue shape rulings if included | Complete synthetic payloads; every OpenValue untightened case; copy/forge attempts on views | All 959+ range002 tests green; each new path in `UnsetP0FieldsError`; hash changes per path; `to_engine_params` fails closed on untightened sections | Independent validator on the schema (register Record C-P5 requires it); security reviewer on view minting | Owner approval of the exact field list and of option B; PR #740 ordering resolved (rebase second); never between a real freeze and its sign-off packet |
| **B** | `engine/{or_signal,arming,fill_model,risk_sizer,ticks,trade_log}.py`, `stats/costs.py` | Per-symbol-day entry path to a trade record; one gated public entry `evaluate_symbol_day` | ENG-A2 | D05 (shapes), D14 (shapes), D15 | Boundary, timestamp-convention, gap, same-bar, cap-binding bars | Hand-computed fills; `path_ambiguous` flags; look-ahead test green | Validator reviews fill model and sizer against hand fixtures; trading expert reviews rules vs WP2.2 | As common |
| **C** | `engine/{exits,position_sim,portfolio_clock}.py` | E1-E4 state machine and single chronological scheduler; gated `simulate_day` | B | D19 (candidate vocabulary, tie-break escalation E-1), D14 tie-break | Exit-case days, two-symbol collision, reservation release | Net R over multiple exit fills equals hand sum; byte-identical `trades.csv` hash across reruns; future-perturbation test | Second person authors independent expected outputs (B-18) | As common |
| **D** | `stats/{bootstrap,_seeds,multiplicity,selection}.py` | Three bootstrap methods behind one interface; `select_exit` + `max_stat_bootstrap`; no data | ENG-A2 | D06 (shapes only), D02, D17 (shape) | Zero-mean and planted-effect synthetic series | Seed determinism; null-size calibration; max-stat conservatism; `record_selection` accepts the record | **Statistical validator (D08)** on every method and the studentization (O-8) | As common; numpy use needs the dependency review (Q-B6) |
| **E** | `stats/gates.py`, `audit/{audit_pack,sealed_store}.py`, `engine/pipeline.py` | G0-G10 evaluator with UNDEFINED handling; two-stage run; Level 1 seal | C, D | D06/OD-2 (stage-1 criteria), D04/D10/D12 shapes (G6-G8), G10 policy (section 5) | Boundary trade counts and PF; control pass/fail runs | Pipeline cannot unseal before the selection record; failing control leaves strategy outputs unread; header accepted by `parse_audit_pack_header` | Validator on gates and the sealed pipeline; **contract review if anything touches verdict semantics (K2)** | As common; the sealed store must state its Level 1 limit |
| **F** | `controls/*`, `stats/{funnel,walk_forward,splits,redundancy}.py`, `tests/.../fixtures/` | Controls, funnel, diagnostics, independent fixtures | C, D | D06 definitions for time-shuffle, no-information, stage 1 (each needs its own definition, acceptance behaviour and independent statistical review), D13 naive ORB, D12 | Uptrend/downtrend/non-breaking day, infeasible draws | Controls never qualify by a future cross; denominators preserved | Statistical validator per control | As common; controls without an approved definition stay unimplemented |
| **G** | `data/{fetch_plan,sip_loader,integrity,chunk_journal,manifest,minute_classes,coverage,bar_store}.py`, `data/_fakes` | Loader core against fakes; gated `read_bars`; no vendor contact | ENG-A2 | Q-B1 review; D03 budget (O-1); D05 5a, `data.minute_reconciliation`, `data.coverage_min`, `data.exclusion_bound`; D11 `fetch_mode` | Truncated, empty month, vendor gap, wrong feed, crash/resume | Section 9.8 negative tests; zero repeat calls on resume | **Data-isolation review (backlog section 15) by the validator before merge** | As common; no real client is ever constructed in the PR |
| **H** | `data/{identity_map,pit_universe,corp_actions}.py` | PIT monthly universe, identity, basis tags on a synthetic DuckDB | ENG-A2 (G soft) | OD-1 (D03 sub-item), `data.adjustment`, O-6 | Ticker reuse, rename, delisted, unmapped, lineage refusals | Look-ahead perturbation changes no universe; no merged series across permatickers | Validator on look-ahead and lineage handling | As common |

### 2.2 Recommendation: which synthetic-only package to implement first (after separate approval)

Recommendation (not a decision): **ENG-A1 (guard harness, binding helper, look-ahead utility, floor-free calendar)**.
Reasons: it needs no owner decision, changes no hash and no schema, does not conflict with PR #740 or the schema candidate, produces the negative-test and look-ahead tooling that every later PR's required evidence depends on, and the calendar fixes the confirmed `eval_calendar` floor problem. ENG-A2 is the true prerequisite for B-H, but it is gated on the schema approval, option B, and shape rulings, so it should follow ENG-A1 rather than block it. After ENG-A1 and ENG-A2, B then C then D (parallel with C) then E and F, with G and H after the Q-B1 review. All of this is subject to the common gates above.

---

## 3. C3 Validation of security and fail-closed contracts

Each row states what the merged code does (a), the gap or risk found, and the test or gate that must exist before dependent work ships. "Level 1" means accidental-misuse protection, not defence against code execution in the process.

| # | Contract | Merged behaviour (a), with citation | Gap or risk found | Required evidence / next step |
|---|---|---|---|---|
| 1 | **Enrollment versus freeze** | Enrollment creates a registry with a fresh UUIDv4 genesis (`run_registry.RunRegistry.enroll_new` `:304`; no CLI exists). Freeze requires the committed owner-approved manifest and `spec.governance.registry_genesis_id` equal to the manifest's, plus P3 limits equal (`freeze_spec.freeze` `:60-78`). `authorize` additionally requires the registry in use to carry the same genesis (`results_guard.py` N1 block) | **Freeze never checks that a registry with that genesis exists or is enrolled.** A spec can be frozen against a manifest genesis that no registry carries; it fails closed later at `authorize` (`RegistryGenesisMismatchError`), but only after the freeze and sign-off packet are done. Also the manifest is a committed file read from the executing checkout (accepted Level 1 limit) | Ordering rule for the ceremony: enroll first, then the owner records the genesis in the manifest by reviewed git change, then draft, then freeze. Add a documented check (a pre-freeze script step or test) that the enrolled registry's genesis equals the manifest's. Not a code change authorized here |
| 2 | **Protected-window capability** | `ResultsCapability` carries `spec_sha256, phase, partition, date_range, citable`; unforgeable by convention; validity = own run OPEN in its registry (`require_capability`) | The decorator does not compare the capability with call inputs (spec hash, requested window); an engine entry that skips the binding could run spec A's parameters under spec B's capability, or read dates outside `capability.date_range` | Mandatory binding helper in every gated entry and in `read_bars` (ENG-A1); negative tests: other spec hash, other partition, window outside range, closed run |
| 3 | **Run registry and attempt budgets** | Hash-chained, append-only; P3A/P3B budgets pre-registered in the manifest, equal to the spec, counted per genesis and phase across all windows and spec hashes; consumed when `capability_issued` is written (`_check_attempt_limit` `:538`, `mark_capability_issued` `:643`/`:768`); refusals before that consume nothing; no reset (`budget_reset_authorization` refused first) | Raising a limit by editing the committed manifest is allowed by design (process control; the run row records the manifest sha256 but later rows are not compared: NF3). Register v0.2 proposes 1/1 limits (not approved) | Owner decision of limits before the first P3 authorization; the manifest change is a reviewed git change; document that a limit edit is detectable only by git history |
| 4 | **Results guard and exposure ledger** | R2 window hard-coded (`R2_EXCLUDED_WINDOW`); partition ranges must not overlap R2, spec `exposed` windows or the signed ledger; ledger sha must equal `governance.exposure_signed.exposure_ledger_sha256` (`:408`) | Ledger content is the owner's D01 audit, which is not done; `exposure_signed` is `OpenValue` | Keep D01 as P0 gate item; schema shape for `exposure_signed` is a tightening candidate |
| 5 | **Holdout replay prevention** | Registry is the authority: refuses a second authorization for the same spec hash or an overlapping holdout window of any spec hash; durable `holdout_authorized` mark precedes the two-phase token consume; no automatic restoration (`:578`, `:764-765`) | A crash after the mark leaves the window consumed with no recovery code (design-only recovery); `holdout_conflict` windows depend on recorded windows | Recovery procedure stays Level 2 design-only; no P4 code before the recovery design is approved |
| 6 | **Missing-evidence classification** | Merged code classifies by exception type: `SpecNotFrozen/NotSigned/Incomplete`, `Predecessor*` (missing, mismatch, binding), `AttemptLimit*`, `ExposureOverlap`, `Holdout*`, `RegistryGenesisMismatch`, `ManifestNotApproved`. Refusals before `capability_issued` consume nothing; failures after it count | There is **no classification for data or comparator-evidence defects** found after authorization (no registry field for it); `Verdict` is not recorded in the registry (K2) | See section 4 classification table; new checks belong to later E/P5 code and a contract review |
| 7 | **G10 integration** | Verdict enum and registry status are separate; P5 refused outright; `gates.redundancy_corr_max` is a fixed 0.85 equality | See K1-K7 (section 5) | Plan clarification (K1), a hashed binding field before the first P3a authorization (K3/K4), a revalidation hook before P4 (K5) |
| 8 | **Level 1 vs Level 2** | Documented limits in the guard docstring and acceptance findings | Anything requiring OS-level fencing (holdout bytes, sealed results, anchoring) is not delivered by these modules | Do not describe the guard as containing data; data-isolation review precedes G/H merge |

---

## 4. Missing-evidence classification (proposed; not implemented)

Recommendation (not a decision). Classify by when the gap is found and by what it blocks. A refusal before `mark_capability_issued` consumes nothing; after it the attempt and, for P4, the window are consumed.

| When found | Example | Classification | Effect | Mechanism today |
|---|---|---|---|---|
| Before authorization, input absent or invalid | Predecessor pack missing; spec unsigned; genesis mismatch; comparator series hash mismatch | REFUSED (named error) | Nothing consumed; fix and retry | Existing exceptions (comparator case needs K5 hook: procedural until built) |
| After authorization, before results unseal | Stage-1 control fails; engine invariant fails | `INCONCLUSIVE_ENGINE`; strategy outputs stay unread | Attempt consumed; defect-only rerun needs separate recovery authorization | Verdict enum supports it; registry records only RunStatus, so the verdict must be written by E-code (K2) |
| After authorization, data defect | Coverage below threshold discovered during a run | `INCONCLUSIVE_DATA` | Attempt consumed | As above |
| After P4 results, comparator evidence found missing | G10 inputs gone | G10 = UNDEFINED, run not eligible for advancement; P4 statistics unchanged; re-evaluation offline from pinned evidence only | Holdout window already consumed (K7) | Procedural until the P5/P6 consultation of the gate report exists |
| Evidence tampered or hash mismatch | Manifest or pack rewritten | Fail closed, `INCONCLUSIVE_TECHNICAL` or refusal | As above | Hash checks exist for predecessor packs; Level 1 limit applies |

---

## 5. G10 comparator-policy integration (Agent A's K1-K7, e5bd0bfc)

| ID | Conflict or gap (from e5bd0bfc) | Readiness impact | Resolution path (all unsigned) |
|---|---|---|---|
| K1 | Plan s5.1 says "All gates must pass" but the owner direction is that a failed G10 does not alter P4 statistics and only prevents advancement | Docs: plan clarification sentence | Plan amendment, owner/validator sign-off |
| K2 | No enforcement point for "prevents advancement"; registry has no verdict; `verdict.py` is imported by neither registry nor guard | Affects PR E and the later P5/P6 code; no present exposure because P5 is refused | New checks at P5 activation and P6 pack; contract review before any verdict-semantics change |
| K3 | Nowhere to bind a comparator-policy SHA-256 today | Requires a schema (or manifest) change | G10-C1 (formerly "Option 1" in this document): hashed spec field `governance.comparator_policy_sha256` (strongest); changes the proposed leaf count from 86 to 87 |
| K4 | "Before first P3a authorization" is mechanical only for a hashed spec field | Choose the binding before the schema batch lands | Fold into the same pre-freeze schema batch if G10-C1 is approved |
| K5 | No revalidation hook before P4 | Procedural until a guard argument/check is added | New evidence argument in `authorize` (later, separate contract review) |
| K6 | Sequencing with schema candidate and PR #740 | Raises the proposed required leaves from 86 to 87 if G10-C1 is added (the 66 on main is unaffected); touches `schema.py`, view and adapter | Same pre-freeze batch, rebase order recorded |
| K7 | Missing evidence found after P4 cannot be repaired by rerun | Revalidation before P4 must be a hard pre-authorization step | Treat K5 as blocking for any P4 authorization (not for P2/P3 work) |

Naming (G10 binding choices): this document's earlier "Option 1/2/3" (the three binding places in e5bd0bfc B.6) are renamed **G10-C1** (hashed spec field), **G10-C2** (governance manifest key) and **G10-C3** (sign-off packet pin). "Option B" elsewhere in this document means only the P5 account-binding option (register s22), never a G10 choice. G10 binding choices are named G10-C1, G10-C2 and G10-C3 everywhere; no "Option A/B" wording is used for G10 in this document.

Readiness conclusion for G10: **PR E can implement the gate-report structure with G10 as UNDEFINED/PASS/FAIL on synthetic comparator series**, but its real binding (field, hook) is BLOCKED on the owner's comparator policy, the G10-C1/C2/C3 binding choice and the K1 plan clarification.

---

## 6. Prioritized PR execution plan

Order, with the blocking item for each. Nothing starts without the separate authorization (Q-B2).

| Priority | Step | Mode | Blocking item to start |
|---|---|---|---|
| 1 | **ENG-A1** harness, binding helper, look-ahead helper, calendar | READY (synthetic only) | Separate written authorization only |
| 2 | **ENG-A2** schema candidate + accessors (rebase on whatever #740 does) | READY once approved | Owner approval of the exact field list, option B decision, D19 vocabulary/tie-break, shape rulings; PR #740 ordering |
| 3 | **B** engine core | READY (synthetic only) after ENG-A2 | ENG-A2 merged; D05/D14/D15 shapes |
| 4 | **D** statistics and selection (parallel with B/C) | READY (synthetic only) after ENG-A2 | ENG-A2; D06 shapes; numpy review |
| 5 | **C** exits and scheduler | READY after B | O-9 vocabulary/tie-break escalation |
| 6 | **G** loader core (fakes) | READY after ENG-A2 | Q-B1 data-isolation review; Q-B1 adapter route |
| 7 | **H** PIT universe | READY after ENG-A2 | Q-B1 review; OD-1 sub-item |
| 8 | **E** gates, audit pack, sealed pipeline | READY after C, D | Stage-1 criteria (D06/OD-2); G10 binding choice; G6-G8 shapes |
| 9 | **F** controls, funnel, diagnostics | READY after C, D | D06 control definitions with independent statistical review |
| - | Everything real (freeze, enrollment, pulls, P3/P4, executor) | BLOCKED | P0 sign-off, host, vendor, authorization; not part of this plan |

---

## 7. Unresolved questions

1. Is PR #740 merged elsewhere or still open, and what exactly does it change in `schema.py`/`loader.py`? (Not visible on main.)
2. Is option B approved (and signed), or does `p5.account_id` stay? Until then the two states must not be mixed.
3. D19 within-family tie-break (E-1) and parameter vocabulary (E-2).
4. G10: comparator policy content, binding choice G10-C1/C2/C3, K1 plan amendment, K5 hook sequencing.
5. Should the freeze ceremony include a mandatory registry-existence check (finding C3 #1)?
6. Split of PR A into ENG-A1/ENG-A2: accepted?
7. numpy declaration (Q-B6) and PR D timing.
8. Names of the independent validator and trading-expert reviewer (D08) so the review requirements can be assigned.
9. Attempt limits (register proposes 1/1, unapproved) before the first P3 authorization.
10. Reproducibility and lock-integrity control: enhanced B2 (independent hash-integrity verification) or the B3 fallback; PR #744 is on HOLD (section 10). Which control is accepted decides which packages can claim reproducibility evidence.

## 8. Evidence

Starting SHA a72dd119 (apps tree equal to d61f313a); enumeration scripts and JSON outputs were run offline from the scratchpad against d61f313a (main code) and 76730911 (candidate) with `draft_skeleton()`/`parse_draft()`; candidate test results on 76730911: 959 passed, 10 skipped, ruff and mypy clean; code citations as listed in section 1.3 and section 3; Agent A's K1-K7 read from e5bd0bfc.

## 9. Not authorized by this document

No implementation commit to code; no push, PR or merge; no real freeze; no enrollment; no manifest change; no data access, vendor or SDK call; no backtest; no filling of any owner value; no change to any gate, threshold, limit or window.

---

## 10. Update: reproducibility and lock-integrity controls (owner ruling after the B2 run)

### 10.1 What was reported (relayed by the coordinator; I have not seen the B2 run itself)

The B2 verification showed seeded pin reproducibility 4/4, but a **corrupted lock hash passed undetected**. B2 is **NOT ACCEPTED as implemented**. Preferred: **enhanced B2 with independent hash-integrity verification**; **B3 is the fallback**. PR #744 is on HOLD. I do not describe B2 or B3 beyond this; their design is owned elsewhere.

### 10.2 What I can verify from the repository (read-only)

- The CI lock gate `scripts/check_dependency_locks.py` (the offline PR check, `ci.yml:303`) verifies that **every pinned entry in `constraints/*.txt` carries at least one `--hash=sha256:` line** (docstring item 4; error path "pinned entr(y/ies) without a sha256 hash"). That is a presence check. It does not verify that a hash value is the correct digest of the artifact. The only correctness check is `--recompile` (item 6; byte-identical re-resolution), which needs network and uv and runs nightly (`ci.yml:592`), not on every PR. So a corrupted hash value would pass the offline PR gate, which is consistent with the B2 finding. This is my reading of the script, offered as supporting context, not as a finding about B2.
- `numpy==2.2.6`, `pandas==2.3.3`, `pyarrow==19.0.1`, `duckdb==1.5.5`, `pandas-market-calendars==5.4.0` are already pinned with hashes in `constraints/backend-py312.txt`. `hypothesis` is not pinned.

### 10.3 Dependency matrix: which packages need reproducibility or lock-integrity controls first

"Needs control first" means: the package's acceptance evidence includes a reproducibility claim (recorded dependency versions, lock hash, or cross-run byte-identity), or the package adds or changes a dependency.

| Package | Adds or changes a dependency? | Reproducibility claim in its evidence? | Needs lock-integrity control before it can claim that evidence? |
|---|---|---|---|
| ENG-A1 harness, calendar | No (existing `pandas-market-calendars`) | Calendar outputs depend on the library version | Not to start. Record the library version in test output; no lock-hash claim |
| ENG-A2 schema, accessors | No | Hash determinism of the spec (pure Python, no dependency effect) | No |
| B engine core | No | Byte-identical trade log across reruns | No (own code), but cross-environment claims wait on the control |
| C exits, scheduler | No | Byte-identical `trades.csv` across reruns and `PYTHONHASHSEED` | No for in-process determinism; yes for any claim across environments |
| D statistics, selection | **Only if numpy is chosen (Q-B6).** numpy is already locked as a transitive pin; declaring it as a direct dependency edits `apps/backend/pyproject.toml` and therefore the lock inputs (and `constraints/**` if regenerated: global FULL CI). numpy `Generator` streams are not guaranteed across versions, so seeded results then depend on the exact locked numpy | Seed determinism across environments | **Yes if numpy** (needs a trusted lock-hash verification so the recorded numpy version/hash is meaningful). **No if stdlib `random`** (stream stable across Python versions for the calls used); the stdlib variant can proceed without waiting |
| E gates, audit pack, sealed pipeline | No | The audit pack and execution manifest record code SHAs and, per plan, dependency/lock identity | **Yes for the reproducibility fields**: recording a lock hash that can be silently wrong would weaken the evidence. Pack logic can be built; the lock-hash field stays non-claiming until the control is accepted |
| F controls, funnel | No | Seeded controls reproducible | Same as D regarding the RNG choice |
| G loader, manifest | No | Data manifest records the loader git SHA, lock-file hash and library versions (RA L-MAN-1) | **Yes for those fields**; real runs also need the research host and are BLOCKED anyway |
| H PIT universe | No | Deterministic universe build | No |
| CI lock gate / `constraints/**` / PR #744 | It is the control itself | n/a | Not part of A-H; on HOLD; any change is global (flags every project) |

Consequence: **no package among A-H is blocked from synthetic implementation by the B2 finding if no new dependency is added and the stdlib RNG is used**. The finding gates (1) a numpy-based PR D, (2) the reproducibility fields of PR E and PR G manifests, and (3) any cross-environment byte-identity claim. ENG-A1 remains the recommended first package.

### 10.4 What remains blocked, and by what

| Package | Blocked by P0 decisions | Blocked by reproducibility controls | Blocked by schema authorization |
|---|---|---|---|
| ENG-A1 | none | no | no (separate implementation authorization only) |
| ENG-A2 | option B (D07), D19 vocabulary/tie-break, OpenValue shapes | no | **yes** (the schema batch itself) |
| B | D05, D14, D15 shapes | no (cross-env claims only) | yes (via ENG-A2) |
| C | D19, D14 tie-break | no (cross-env claims only) | yes (via ENG-A2) |
| D | D06 shapes, D02, D17 shape | **numpy variant only** | yes (via ENG-A2) |
| E | D06/OD-2 stage-1 criteria, D04/D10/D12 shapes, G10 policy and binding (C1/C2/C3) | **reproducibility fields** | yes (via ENG-A2; plus 87th leaf if G10-C1) |
| F | D06 control definitions (each with independent statistical review), D13, D12 | numpy variant only | yes (via ENG-A2) |
| G | Q-B1 data-isolation review, D03 budget, D05 5a, D11 | **manifest reproducibility fields** | yes (via ENG-A2) |
| H | OD-1, `data.adjustment`, O-6 | no | yes (via ENG-A2) |

### 10.5 Counts kept distinct (verified, no correction)

Currently required (main, a72dd119): **66** unset P0 leaves. Proposed (candidate 76730911): **86**. Possible with the G10-C1 field: **87**, which is a separate proposal and not part of 86. These three numbers are not interchangeable and none of them changed in this update.

### 10.6 Unchanged restrictions

No implementation, no push, no real freeze, enrollment, data access or backtest, and no change to any gate, threshold, limit or window.
