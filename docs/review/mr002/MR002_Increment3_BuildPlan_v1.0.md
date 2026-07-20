# MR-002 Increment 3 — Build Plan (v1.0, for review; NO code)

**Status: plan only — submitted for review; no production modules or tests written.** Every element
maps to an already-frozen rule (`PR-*`, census `91eec262`) or a Phase-0 owner ruling (`RC-*` /
reason codes, resolution `860c8cde`, binding registry `edb7ff22`). **No new economic decisions.**
Machine-readable qualification matrix: `MR002_Increment3_QualificationMatrix_v1.0.json` (28 tests).

## 1. Module layout (`docs/review/mr002/evaluator/`)

Identity, candidate validation, economic construction, state, execution orchestration, and NAV are
**separate modules** (no collapse). Increment 1 (`report`, `metrics`) and Increment 2 (`costmodel`,
`execution`) are **reused unchanged**.

| module | responsibility |
|---|---|
| `mr002_valoos_portfolio_identity.py` | hash-bind `MR002_Increment3_RuleRegistry_v1.0` (`edb7ff22`) + `Phase0_Resolution` (`860c8cde`) + governing sources; one common NAV identity; fail-closed `REFUSED_CODE_OR_DATA_IDENTITY` (incl. `NAV_IDENTITY_MISMATCH`) |
| `mr002_valoos_candidates.py` | strict `SyntheticCandidate` validation; `registered_sigma_resid` + inverse checks (`CANDIDATE_SIGMA_RESID_INVALID` / `CANDIDATE_INVERSE_VOL_MISMATCH`, rel_tol 1e-12); `ELIGIBLE\|INELIGIBLE` enum; A/B/C `configuration_id` identity |
| `mr002_valoos_construction.py` | eligibility consumption; `1/σ` + within-side normalization; entry-neutral raw targets; position→sector→beta removal cascade; removal/tie-break evidence |
| `mr002_valoos_portfolio_state.py` | held positions; pending exits (dup-suppressed); exits-before-entries; cash + one-position-per-symbol occupancy — **immutable state transitions** |
| `mr002_valoos_exposure.py` | `RAW_TARGET` / `INTENDED_TARGET` / `REALIZED_EXECUTED`; per-name/gross/net/sector/beta; empty-portfolio `N_A_EMPTY_PORTFOLIO` |
| `mr002_valoos_replay.py` | Increment-2 **preview→verify→commit**; realized hard-cap checks (`REALIZED_*_CONSTRAINT`); net-drift `DriftRepairInstruction`; atomic session outcome |
| `mr002_valoos_nav.py` | official-open 7-step valuation; NAV reconciliation; daily return series; `HELD_POSITION_OPEN_MARK_MISSING` |
| `mr002_valoos_pipeline.py` | synthetic end-to-end orchestration; Increment-1 metric/report integration; canonical deterministic report |
| `test_increment3.py`, `_gen_evidence_inc3.py` | 28-test qualification suite + evidence bundle |

## 2. Data contracts (immutable records; frozen dataclasses / canonical dicts)

Exact-float = every computed float serialized via `mr002_valoos_report.encode_float`
(`{display, exact_hex}`, signed-zero preserved, non-finite refuses). Provenance identities carried on
the top-level report: registry `edb7ff22`, resolution `860c8cde`, prereg `b2a042d4`, ledger
`deda5cec`, code + dependency-lock shas, and `synthetic_fixture_only=true`.

| record | primary key | required fields (abbrev.) | exact-float | provenance |
|---|---|---|---|---|
| `SyntheticCandidate` | `candidate_id` | permanent_security_id, signal_origin_session, decision_session, symbol, side, registered_signal_value(=z), registered_sigma_resid(>0), sector_id, beta, eligibility_status∈{ELIGIBLE,INELIGIBLE}, eligibility_evidence_identity, configuration_id∈{A,B,C}, official_next_open_price, trailing_adv_dollars (+opt registered_inverse_vol_weight) | z, σ, β, price, ADV | eligibility_evidence_identity, configuration_id |
| `HeldPosition` | `position_id` (unique `symbol`) | symbol, side, shares, entry_session, entry_date, entry_open_price, entry_notional, sector_id, beta, permanent_security_id, signal_origin_session, configuration_id | prices, notional | originating candidate_id |
| `PendingExit` | `position_id` | symbol, scheduled_exit_session, decision_session, decision_type∈{EXIT_DECISION,TIME_STOP_SCHEDULED_AT_ENTRY}, reason, shares (dup-suppressed) | — | position_id |
| `RawTarget` | `candidate_id` | side, symbol, z, raw_inverse_vol_weight(=1/σ), sector_id, beta | weight | candidate_id |
| `IntendedOrder` | `candidate_id` | side, symbol, intended_shares, intended_notional, target_weight, official_next_open_price, sector_id, beta, binding_constraint\|null, permanent_security_id, signal_origin_session | notional, weight, price | candidate_id |
| `ExecutionPreview` | `(candidate_id, session)` | intended_shares, adv_cap_shares, nav_cap_shares, preview_filled_shares, clipped_shares, cash_from_clip, official_open_price | notional, price | order ref — **dry-run, no commit** |
| `RealizedPosition` | `position_id` | symbol, side, realized_shares, realized_notional, entry_open_price, sector_id, beta | notional, price | position_id |
| `ExposureSnapshot` | `(state_label, session)` | state_label∈{RAW_TARGET,INTENDED_TARGET,REALIZED_EXECUTED}, per_name{sym→MV/NAV}, gross(÷NAV), net(÷gross), sector_gross{}, sector_net{}, signed_beta_numerator, normalized_beta\|N_A_EMPTY_PORTFOLIO, cash | all ratios | session |
| `ConstraintDecision` | `(constraint, stage, session)` | constraint∈{per_name,sector_net,sector_gross,beta}, stage∈{INTENDED,REALIZED}, raw_value, construction_constrained_value, executed_value, binding_rule(bool), removed_or_clipped_amount, cash_remainder, disposition(PASS\|code) | values | session |
| `RemovalEvent` | `(session, iteration)` | removed_candidate_id, reason(SMALLEST_ABS_Z), tie_break∈{none,signal_origin_session,permanent_security_id}, z, signal_origin_session, permanent_security_id, freed_capacity_to_cash | z, cash | candidate_id |
| `DriftRepairInstruction` | `session` | net_drift_fraction_of_gross, band(0.05), breached(bool), larger_side, reduction_order(smallest \|entry z\|→oldest position→permanent id), scheduled_next_open | drift | session (net-drift ONLY) |
| `SessionReplayResult` | `session` | disposition∈{COMMITTED,REFUSED}, stop_code\|null, ledger_events(Inc-2 17-field), realized_positions, exposure_snapshots[3], constraint_decisions, removal_events, drift_repair\|null, nav_record, atomicity_committed(bool) | via nested | session |
| `DailyNAVRecord` | `session` | nav_prev, nav, daily_return, cash, gross, positions_valued, open_marks_used | nav, return | session |

## 3. Atomicity design (PREVIEW → VERIFY → COMMIT)

State is **immutable**: each `SessionReplayResult` is derived from an immutable prior state
`S_{s-1}`; the **only writer** is `commit`.

```
process_session(S_{s-1}, candidates_s, market_s):
  1. exits    = state.due_exits(S_{s-1}, s)            # exits-before-entries; pending carried, dup-suppressed
  2. intended = construction.build(S_{s-1}, candidates_s)   # INTENDED_TARGET on a COPY (cascade binds here)
  3. preview  = execution.preview(intended, market_s)  # PURE dry-run: exact Inc-2 mechanics, NO mutation
  4. realized = exposure.realized(S_{s-1}, exits, preview)
  5. verify   = exposure.check_hard_caps(realized)     # per-name/gross/sector/beta
        if verify.fails: return SessionReplayResult(REFUSED, stop_code=REALIZED_*_CONSTRAINT,
                                                     evidence=preview+snapshots)   # S_s := S_{s-1}
  6. drift    = exposure.net_drift(realized)           # net-dollar only -> DriftRepairInstruction (no stop)
  7. S_s      = commit(S_{s-1}, exits, preview.fills, costs, nav)   # ONLY writer; builds new immutable state
     return SessionReplayResult(COMMITTED, ..., nav_record)
```

A **REFUSED** session returns `S_s := S_{s-1}` unchanged — because `preview` is a pure function and
`commit` never runs, a failed preview cannot mutate **cash, positions, pending exits, the ledger,
NAV, or the daily-return series** (asserted directly by T3-25). This is evaluator atomicity, not a
claim about live-broker fill cancellation.

## 4. Increment boundaries (reaffirmed)

Increment 3 **consumes** synthetic upstream facts and **does not compute**: residuals, z-scores,
`sigma_resid`, eligibility histories (earnings/merger/split/delisting/gap/liquidity), PIT sector
history, or real prices/ADV. No vendor or sealed adapters; no `evaluator_prototype` import. The report
records `validation_data_read = oos_data_read = development_performance_computed = false`,
`synthetic_fixture_only = true` (T3-28). Sector construction consumes `sector_id`; the volatility
overlay (PR-26) and residual model (PR-25) remain out of scope.

## 5. Qualification (28 tests — full mapping in the JSON)

Covers identity tampering, candidate/sigma/inverse failures, A/B/C-only-threshold parity, within-side
normalization, entry neutrality, the position→sector→beta cascade + smallest-|z| removal + tie-breaks
+ no-renormalization, pending/dup/occupancy state, NAV-identity mismatch, ADV asymmetry, realized
sector/beta fail-closed, realized net-drift repair, empty portfolio, held-position missing mark,
open-to-open NAV arithmetic, first-window prior NAV, preview-failure atomicity, deterministic replay
hash, signed-zero/non-finite, and the no-real-data boundary. Every expected value is independently
hand- or numpy/scipy-derived.

## 6. Stop point

Submit only this plan. No production modules or tests until reviewed. On plan acceptance, Increment 3
is built as one focused, fully-tested qualification package (loader → candidates → construction →
state → exposure → replay → NAV → pipeline → 28-test suite → evidence). Validation/OOS SEALED;
real-data / performance NOT authorized.
