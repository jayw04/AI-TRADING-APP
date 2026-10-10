# RANGE-002 Schema Change Batch Proposal v0.1

| Field | Value |
|---|---|
| Status | **PROPOSAL FOR OWNER REVIEW. Nothing here is implemented, approved, signed or frozen.** No value below is populated: every new field is `UNSET -- owner decision <id>`. |
| Date | 2026-10-10 |
| Base | `origin/main` at `d61f313a`; branch `docs/range002-p1-p2-backlog` (local only) |
| Authority | Owner ruling Q-B4 (2026-10-10): prepare ONE batched schema-change proposal before any real freeze. Q-B2: planning and synthetic fixtures approved; **implementation needs separate authorization.** |
| Revision | Amended 2026-10-10 after the independent review of candidate 5bc2b493 (fix commit 76730911 on `feat/range002-schema-batch`): per-candidate `rank` WITHDRAWN (family-level ordering only), risk-unit validators NOT added, `matching` canonical order, D07/P5 wording, `data.fetch_mode` enumeration proposal (section 4.3) |
| Companion | `RANGE-002_P1_P2_Implementation_Backlog_v0.1.md` (section 8 classification, section 11 accessors, Part III); P0 Decision Register v0.2 section 22 (read from local branch `docs/range002-p0-decision-register`, Workstream A) |
| Data accessed | None. Local file reading only. No network, SDK, key, data or return. |

## 1. Why one batch, and why before any freeze

`DraftSpec` models use `extra="forbid"` and `spec_sha256` covers everything except `signoff` (`DraftSpec.hashable_payload`). Every added or removed key therefore changes the canonical payload and the hash of any spec built afterwards, and makes every existing synthetic payload invalid until updated. Today that costs nothing: no real spec has ever been frozen (all P0 values null), the committed governance manifest is entirely null, and no test pins a spec hash (the only 64-hex literal in `tests/research/range002/spec/` is the SHA-256 of "abc"). After any real freeze, or after documents pin a spec hash, each change would be a re-freeze. The batch therefore lands as one reviewed schema PR (PR-A in the backlog) before any real freeze, and its wording is fixed before the A1 sign-off packet.

## 2. Reconciliation of the field list and counts

Owner list in the directive: "the nine new frozen fields", followed by twelve field paths (superseded, see below). Reconciled against backlog section 8:

| Count | What | Reconciliation |
|---|---|---|
| 9 | Orphan values of class (a) | O-2, O-3, O-4, O-5, O-9, O-10, O-11, O-12, O-18 |
| 20 | Owner-valued new LEAF paths those nine produce (11 new keys/objects) | O-2 -> 1 (`data.adjustment`); O-3 -> 2 (`risk.initial_equity`, `risk.equity_basis`); O-4 -> 2 (`data.minute_reconciliation.volume_tolerance_frac`, `.reference`); O-5 -> 2 (`data.coverage_min`, `data.exclusion_bound`); O-9 -> 0 new keys (validators on the existing `params`; the first draft's `rank` is WITHDRAWN); O-10 -> 5 (`controls.stage1_criteria.negative_control_mode`, `.negative_control_alpha`; `controls.random_entry.population.unit`, `.instants`, `.matching`); O-11 -> 3 (`controls.time_shuffle.method`, `.min_shift_days`, `.reps`); O-12 -> 4 (`controls.no_information.kind`, `.lo`, `.hi`, `.reps`); O-18 -> 1 (`risk.over_budget_rule`) |
| 1 + 1 removed | P5 binding correction (owner chose option B) | add `p5.account_binding`; remove `p5.account_id` |
| 6 | Extra owner decisions with NO spec field (class (d)) | O-1 budget cap (D03), O-7 lineage constants (OD-1), O-13 redundancy set (OD-3), O-15 diagnostic windows (D13), O-16 halt evidence (OD-4), O-17 risk units (D05 5j). Not populated, not in the schema |
| 3 | Plan-fixed constants (class (b)), no schema effect | O-6, O-8, O-14 (plus sub-items O-1b, O-3a) |

So the batch is 20 owner-valued leaf paths plus the P5 change (21 added leaf paths, 1 removed), plus two fixed non-owner members of `controls.stage1_criteria` (`invariants`, `on_fail`). The first draft counted 12 'new field paths' including `rank`; that count is superseded. One refinement relative to backlog section 8.2: `data.coverage_min` is `float | None` with an equality validator (a non-null value must be exactly 0.98) instead of a pre-filled `_eq(0.98)`, so that it is UNSET until the owner confirms it and the 98% design threshold still cannot be loosened by anyone.

## 3. Rules for every field in the batch

- **No defaults.** The key is required; the skeleton emits `null` (nested objects emit their keys with `null` leaves). `FrozenSpec.from_draft` then refuses to freeze until the owner supplies the value (existing `_walk_unset` behaviour; no change to the unset machinery).
- **Hash impact.** Every field below is hashed: `spec_sha256` of any spec created after the change differs from one created before. Setting or changing the value later also changes the hash. No existing frozen spec exists to migrate.
- **Validators** run only on non-null values (the existing pattern, e.g. `Bootstrap._conf_ok`).
- **Value ownership.** The owner supplies the value through the decision named; no preparer, agent or test may choose it. Synthetic test values live only in `tests/.../spec/_fixtures.py` and are marked `SYNTH`.
- **Mandatory annotation** in `schema.py`: each field carries a `# P0: <decision id>` comment, as the existing fields do.

## 4. Field specifications

Status of every row: `UNSET -- owner decision <id>`.

| # | Path | Documented meaning | Type | Validator (on non-null values) | Owner decision | Status |
|---|---|---|---|---|---|---|
| 1 | `data.adjustment` | Price basis of stored intraday bars; the single basis used for OR, stop and fill prices (plan WP1.6, R-mixing rule) | `Literal["raw","split_adjusted","split_dividend_adjusted"] \| None` | closed vocabulary; spinoff-adjusted is not offered because Sharadar `open/close` are not spinoff-adjusted | D03 (vendor) with D05 | UNSET -- owner decision D03/D05 |
| 2 | `data.minute_reconciliation` | Evidence rule separating `NO_TRADE_MINUTE` from `DATA_GAP`: how closely stored bar volume must match the independent daily volume | object `{volume_tolerance_frac: float \| None, reference: Literal["sep_daily_volume"] \| None}` | `0 <= volume_tolerance_frac < 1`; `reference` closed | D05 5a | UNSET -- owner decision D05 5a (value needs a return-blind measurement after P0) |
| 3 | `data.coverage_min` | Minimum overall symbol-day coverage for the P1 exit gate and G9 | `float \| None` | if set, must equal `0.98` (design v0.4 threshold; prevents loosening) | D03 (confirmation of the design constant) | UNSET -- owner decision D03 |
| 4 | `data.exclusion_bound` | Maximum fraction of eligible symbol-days that may be excluded as `VENDOR_NO_HISTORY` or `IDENTITY_UNMAPPED` before coverage is reported | `float \| None` | `0 <= x < 1` | D03 / Q-P1-4 | UNSET -- owner decision D03 (Q-P1-4) |
| 5 | `risk.initial_equity` | Starting account equity for the simulation, USD | `float \| None` | `> 0`, finite | D05 5j | UNSET -- owner decision D05 5j |
| 6 | `risk.equity_basis` | Whether sizing and the daily-loss limit use a fixed initial equity or equity marked at the prior close | `Literal["static","marked_daily"] \| None` | closed vocabulary | D05 5j | UNSET -- owner decision D05 5j |
| 7 | `risk.over_budget_rule` | Action when actual risk after fill exceeds the budget by more than `risk.fill_risk_tolerance` | `Literal["reduce_to_budget","protective_exit"] \| None` | closed vocabulary | D05 5c | UNSET -- owner decision D05 5c |
| 8 | `controls.stage1_criteria` | Mechanical pass rule for the WP4.0 stage-1 control check (a failing check yields `INCONCLUSIVE_ENGINE`, strategy results stay sealed) | object `{invariants: ["no_entry_before_1000","flat_at_close","ledger_reconciles","no_future_bar_access"] (fixed tuple), negative_control_mode: Literal["invariants_only","invariants_plus_negative_control_test"] \| None, negative_control_alpha: float \| None, on_fail: "INCONCLUSIVE_ENGINE" (fixed)}` | `invariants` and `on_fail` equality validators; `0 <= alpha < 0.5`; `alpha == 0.0` if and only if mode is `invariants_only` (so no conditional nulls are needed) | D06 with OD-2 | UNSET -- owner decision D06/OD-2 |
| 9 | `controls.random_entry.population` | Causal assignment population and matching for the random-entry baseline (WP2.5, WP2.7A, design 5.3) | object `{unit: Literal["symbol_day_at_1000"] \| None, instants: Literal["uniform_entry_window_minutes"] \| None, matching: tuple of Literal["symbols","window","trade_count","capital","risk_budget"] \| None}` | `matching` non-empty, no repeats, listed in the canonical order symbols, window, trade_count, capital, risk_budget (so one choice has one hash) | D06 | UNSET -- owner decision D06 |
| 10 | `controls.time_shuffle` | Time-shuffle negative control definition (WP2.5): which causal procedure | object `{method: Literal["cyclic_day_shift","within_symbol_permutation"] \| None, min_shift_days: int \| None, reps: int \| None}` | `reps >= 1`; `min_shift_days >= 1` if method is `cyclic_day_shift`, else `0` | D06 | UNSET -- owner decision D06 |
| 11 | `controls.no_information` | No-information trigger definition (WP2.5) | object `{kind: Literal["uniform_or_width_multiple"] \| None, lo: float \| None, hi: float \| None, reps: int \| None}` (lo/hi in OR-width multiples above OR high) | `0 <= lo < hi`, finite; `reps >= 1` | D06 | UNSET -- owner decision D06 |
| 12 | `exits.candidates[*].rank` | **WITHDRAWN.** The governing plan orders complexity by FAMILY (`exits.complexity_order`); a per-candidate rank would silently add a within-family tie-break rule. Key not added; a `rank` key is refused by `extra="forbid"`. | - | - | The within-family tie-break is an unset ESCALATION, owner approval at D19 (options: unresolved tie is INCONCLUSIVE; first in candidate-list order; smaller parameter) | UNSET -- owner approval D19 (E-1); fail closed: `select_exit` must refuse an unresolved within-family tie |
| 13 | `p5.account_binding` (replaces `p5.account_id`) | Hashed record that the paper account does not exist at freeze and is bound later by a separate P5 activation record naming the same `spec_sha256` | `Literal["deferred_to_p5_activation"] \| None` | closed single-value vocabulary | D07 | UNSET -- owner decision D07 |

Per-family validators on the existing `exits.candidates[*].params` (no new key; the parameter NAMES are preparer proposals awaiting D19 confirmation, escalation E-2): `time` accepts `{}`; `fixed_r` accepts `{k_r: float > 0}`; `trailing` accepts `{trail_r: float > 0}`; `scale_out` accepts `{remainder: "eod"|"trail"}` plus `trail_r > 0` only when `remainder == "trail"`. The +1R activation and the 50% scale quantity remain plan-fixed (A1 Amendment 1, plan WP2.2A) and are not parameters. Unknown parameter names are refused. This closes the schema comment "parameter vocabulary per family is part of the open D19 decision."

### 4.1 Risk-unit validators: NOT in this batch (deviation from the first draft)

The first draft proposed range validators for the existing `risk.*` fields (percent of equity, fractions, participation). The candidate does NOT add them. Units are the owner decision D05 5j; a validator fixes a unit and would pre-empt that decision. The candidate adds only the three new risk keys and a test asserting that the existing risk fields stay unconstrained. When the owner states the units under D05 5j, range validators can be added in a later schema change before the freeze (they would not change the hash of an unchanged value). UNSET -- owner decision D05 5j.

### 4.2 Not in this batch

The `OpenValue` fields whose shape is undefined (backlog section 11.2: `signal.or_completeness_rule`, `fill.slippage_model`, `fill.halt_policy`, `costs.components`, `execution.stop_protection_policy/tie_break/order_reservation_policy`, `controls.random_entry.invalid_draw_policy`, `controls.naive_orb.definition`, `stats.hypothesis_family`, `stats.regime.*`, `p3.criteria`, `gates.trade_unit/yearly/win_rate/max_dd`) need their shapes decided by the owner before they can be typed. Recommendation (not a decision): ship them in the SAME PR if the shape rulings arrive before PR-A is opened; otherwise ship them in a second schema PR that is also before any freeze. Either way no real freeze happens between the two.

### 4.3 Proposal only: enumeration for `data.fetch_mode` (D11); NOT in the candidate

Owner direction: `data.fetch_mode` stays undefined. The field remains `string or null`, unset, blocking the freeze. The enumeration below is the preparer's proposal, based on the supported acquisition design (ruling C5: a new RANGE-002 monthly-chunked, fail-closed SIP loader; `BarCache` is not modified). No value is a default; null is unset.

| Proposed value | Meaning | Fail-closed behaviour |
|---|---|---|
| `monthly_chunked_sip` | The RANGE-002 loader: explicit feed `sip`, one request unit per symbol batch and calendar month, no `limit` argument, pagination consumed to exhaustion, a response of exactly the page cap treated as possibly truncated, idempotent resume with an append-only chunk journal, SHA-256 data manifest | Any feed other than `sip`, an entitlement or rate-limit failure, a truncation suspicion, a chunk that fails integrity checks, or a manifest mismatch stops the chunk (`FAILED`/`QUARANTINED`); there is no fallback feed, no retry beyond the finite budget, and no `.empty` marker |
| (not offered) `bar_cache` | The shared `BarCache` | Never valid: hardcodes IEX and `limit=10000` (ruling C5) |
| (not offered) `auto`/`default` | Implicit selection | Never valid: R9, no implicit default |

Partition handling (research principal for development months, broker principal for holdout months) is a runtime mode derived from the spec's partition windows and the boundary design, not a second `fetch_mode` value, because the principal is a custody fact and not a research hypothesis. Alternative the owner may prefer: two values (`monthly_chunked_sip_research`, `monthly_chunked_sip_broker`), which would put the custody split inside the hashed spec. Either way the validator is a closed `Literal`, and any other string is refused. This tightening would be a schema change that lands in the same pre-freeze batch if the owner approves it. UNSET -- owner decision D11.

### 4.4 D06 control definitions: hashing does not approve values

`controls.time_shuffle`, `controls.no_information`, `controls.stage1_criteria` and `controls.random_entry.population` record a chosen definition in the hash and make the freeze fail closed while unset. The vocabularies are preparer proposals. Each control needs, before any value is entered, an individual written definition, its acceptance behaviour (what passes, what fails, what the run does on failure) and independent statistical review by the D08 validator. A field in a frozen spec shows that the owner chose a value, not that the choice is sound.

## 5. P5 binding correction (option B)

Owner choice: option B of P0 Decision Register v0.2 section 22 (hashed deferral marker plus a separate P5 activation record). Wording coordinated with that section and its Record C-P5; the register still labels it "PROPOSED / NOT APPROVED" until the owner's signed record exists, so the register text needs the owner's ruling noted, not rewritten by this document.

- **Problem** (register 22.1): `schema.py` declares `p5.account_id: str | None  # P0: D07`, the skeleton sets `None`, and `FrozenSpec.from_draft` refuses to freeze with an unset P0 field, while D07 and plan WP5.1 create the account only in P5, after P4.
- **Change:** remove `p5.account_id`; add `p5.account_binding: Literal["deferred_to_p5_activation"] | None  # P0: D07`. This is the literal the register names ("a closed value such as `deferred_to_p5_activation`"); fixing the vocabulary to this single value is this document's proposal for the owner to confirm, and any additional value would be a schema addition made before the freeze.
- **Freeze tool:** no change (the marker is an ordinary P0 value, as the register states).
- **Hash:** the marker is hashed and stable; the real account id is never in the spec. Limit found by the independent review: only the dedicated field is closed. The `OpenValue` fields (`p5.degradation_tolerance`, `p5.cost_ratio_contract`, `p5.shadow_acceptance`, `governance.roles`, and others) accept any JSON, including an account id, so the P5 activation record must be the sole account authority and no code may read an account id from the spec (escalation E-3, owner decision under D07/D16).
- **P5 activation record (design deferred to the P5 PR, recorded here only as constraints):** a separate append-only record, created only after a P4 `PASS_HISTORICAL_PENDING_PROSPECTIVE` verdict and written owner approval, naming the same `spec_sha256`, the account id, the owner approval reference and the time. The guard already refuses P5 outright (`PaperApprovalNotImplementedError`); the later P5 PR must add the check that the record exists and its `spec_sha256` equals the capability's. Its home (registry row or signed file) is designed with the P5 work.
- **Documents to touch** (docs, not code): plan v0.5 Appendix A `p5` block and WP5.1; decision sheet D07 and A1 Amendment 3 wording if they mention an account id in the spec; register section 22, Record C-P5 and 26.4 (to record the owner's choice).
- **Tests:** see section 6; `tests/.../spec/_fixtures.py` line `"p5.account_id": "SYNTH-ACCT"` becomes `"p5.account_binding": "deferred_to_p5_activation"`; a test that `p5.account_id` is now an unknown key and is rejected by `extra="forbid"`; a test that any other string for the marker is refused.

## 6. Tests to update or add (PR-A)

All synthetic payloads change because of `extra="forbid"`:

1. `schema.py` `draft_skeleton()` emits the 13 new paths with null leaves and drops `p5.account_id`.
2. `tests/research/range002/spec/_fixtures.py`: add synthetic `SYNTH` values for each new path to `_P0_VALUES` (so `P0_PATHS`, which drives `test_schema.py::test_unset_lists_all` (`set(unset) == set(P0_PATHS)`) and the parametrized hash-change test in `test_hashing.py`, follow automatically); update `CANDIDATES` params to the family vocabulary (no rank).
3. Files that consume `complete_payload`/`draft_skeleton` and must still pass unchanged logic: `spec/test_{schema,strict,freeze,freeze_hardening,hashing,manifest,round4_spec}.py`, `governance/{conftest,test_spec_integration,test_round5_manifest_attempts,test_import_lint}.py`.
4. New tests per field: rejects each invalid value in section 4; accepts `null` in a draft; `FrozenSpec.from_draft` names each new path in `UnsetP0FieldsError`; changing each field changes `spec_sha256`; a `rank` key refused (family-level ordering only); per-family param vocabulary; unknown key rejection (including `p5.account_id`); coverage_min equality (0.98 accepted, 0.97 and 0.99 rejected); stage-1 alpha/mode coupling.
5. `scripts/research/range002/freeze_spec.py`: no logic change expected; confirm by running its existing tests with the new payload.
6. Import lint: new validator helper functions in `schema.py` are underscore-private or classmethod validators already covered by the existing reviewed entries pattern; any new public name needs a `REVIEWED_PURE` entry (the PR must run `test_import_lint.py`).
7. Docs: plan Appendix A and the decision sheets/register updated in the same PR or an immediately preceding docs-only PR.

## 7. Migration notes

None required: no real spec has been frozen, the committed manifest (`RANGE-002_governance_manifest.json`) is entirely null and does not pin a spec hash, and no document pins a spec hash yet (the sign-off packet pins document hashes, not the spec hash, until a real freeze). Order of operations: owner approves this proposal (Q-B4 follow-up) -> separate implementation authorization (Q-B2) -> PR-A -> only then any real spec draft.

## 8. What this proposal does not do

It does not populate or default any field, choose any option, change any gate threshold or fixed value, freeze or sign a spec, alter the governance manifest, or implement code. It does not authorize any run.
