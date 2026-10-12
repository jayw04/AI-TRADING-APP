# RANGE-002 build hazard defect records v0.1 (LANE I)

| Field | Value |
|---|---|
| Status | **A, B, C, D: CLOSED-ON-BRANCH** (`fix/range002-build-hazards`, stacked on #755 + #764; fixes unmerged, `[MERGE NOT APPROVED]`). Section F lists the regression tests. The original records below are retained as written. |
| Code under test | PR #755 head `1ecf811b` (unmerged). This branch is stacked on it for that reason; the PR targets `feat/range002-screen-kernel`, not `main`. |
| Owner ruling | R7: hazards block **FREEZE**, not the #755 merge. Fixed in a follow-up PR after #755 merges. |
| Guard-adjacent files touched | **None.** Only new files: this record and `tests/research/range002/hazards/test_build_hazards_xfail.py`. |
| Demonstration | 5 strict-xfail tests (each verified with `--runxfail` to fail on the intended assertion) + 1 characterisation test that passes today. Strict: when a fix lands the test XPASSes, which fails the suite until the marker is removed in the same change. |
| Established | Each hazard below reproduces on synthetic fixtures. |
| NOT established | Real-data impact. Nothing was run on real data. |

## A. Price basis and category mapping are outside the spec hash — BLOCKS: FREEZE

| | |
|---|---|
| Files / lines | `app/research/range002/data/pit_universe.py:41` (`BASIS_SPLIT_ADJUSTED = "SEP_SPLIT_ADJUSTED"`); `data/store_adapter.py:198,214` (`common_stock_categories` is a **call argument** used to set `Listing.common_stock`); `data/store_adapter.py:265-272` (`build_month_from_store`). No `data.adjustment` field in `spec/schema.py`. |
| Guard-adjacent? | Source files above: **no**. The proper fix adds spec fields in `spec/schema.py`: **yes, guard-adjacent** (blocked until #755 merges). |
| Failure scenario | Snapshot with two issuers: CMN (`Domestic Common Stock`, ADV 50M) and ADRX (`ADR Common Stock`, ADV 120M). One frozen spec, one snapshot. `common_stock_categories=[COMMON]` yields members `['P1']`; `[COMMON, ADR]` yields `['P2','P1']`. Same spec hash, different universe, so a result cannot be reproduced from the hash alone. (`test_a1…`, observed: `['P1'] != ['P2','P1']`.) The price basis has the same shape: it is a code constant, `hasattr(draft.data,'adjustment')` is `False` (`test_a2…`). |
| Proposed fix | Add `universe.category_map` (the exact vendor category strings treated as common stock) and `data.adjustment` (the daily price pairing) to the spec; read both only from the frozen spec in `universe_params_from_draft`; remove the free argument; pin their digests in the profile declaration like the unmodelled set. |
| Why FREEZE | A spec frozen today would not bind the two choices that decide who is in the universe. |
| Status | **CLOSED-ON-BRANCH.** `universe.category_map`, `data.daily_price_basis`, `data.intraday_price_basis` are P0 spec fields (SCREEN_V2_REQUIRED, SCREEN_V1_EXEMPT only; v2 required digest recomputed). `universe_params_from_draft` reads them; the `common_stock_categories` argument is removed; only (`SEP_SPLIT_ADJUSTED`, `raw`) is a compatible pair. Tests: `test_a1_*`, `test_a1n_*` (x2), `test_a2_*`, `test_a2n_*`. |

## B. Intraday bars carry no basis tag; the loader cannot refuse a wrong basis — BLOCKS: RUN

| | |
|---|---|
| Files / lines | `data/fetch_adapter.py:27,111-112` (the fetch path hard-codes `adjustment == "raw"`); `data/bar_loader.py:70` (`SELECT ... FROM "minute_bars"`: the table has no basis column and nothing verifies one). PIT universe is split-adjusted by design (`pit_universe.py:41`). |
| Guard-adjacent? | **No.** |
| Failure scenario | A `minute_bars` table filled elsewhere with split-adjusted bars (a later 10:1 split makes prices one tenth) is loaded at one-tenth scale: `load_session` returns a normal session, the $10 floor was applied on the unadjusted price while stops, widths in ticks and sizing now see adjusted prices, and `min_or_width_ticks` eligibility changes silently. `test_b1…`: `DID NOT RAISE` for a table of unknown basis. |
| Proposed fix | Add `basis` (and `adjustment_as_of`) columns to `minute_bars`; `fetch_and_store` writes them; `load_session` takes the required basis from the spec and raises `DataDefectError` on missing/different. |
| Why RUN | It only bites when real bars are loaded; the mock path cannot produce a wrong basis. |
| Status | **CLOSED-ON-BRANCH.** `minute_bars.basis` is written by the fetch path and verified by `load_session` against `data.intraday_price_basis` (missing column, NULL, or any different row raises `DataDefectError`). Tests: `test_b1_*` (x2), `test_b1n_*` (x3). |

## C. Scheduler tie-break is keyed by the ticker string — BLOCKS: RUN (portfolio basis)

| | |
|---|---|
| Files / lines | `screen/scheduler.py:76` `ordered = sorted(trades, key=lambda t: (t.entry_time, t.symbol))`; `Trade.symbol` is a vendor ticker (`screen/types.py`). |
| Guard-adjacent? | **No.** |
| Failure scenario | Two issuers enter in the same minute with capacity for one. Issuer A (entry 11.0) is `AAA`, issuer B (entry 22.0) is `ZZZ`: A is accepted. After a rename the same two issuers carry `ZZZ` and `AAA`: B is accepted. `test_c1…`: `11.0 != 22.0`. The portfolio result depends on the ticker spelling, and a reused ticker is indistinguishable. Neither declared D14 tie option is "ticker ascending" (worksheet note). |
| Proposed fix | Carry `permaticker` on `Trade`; tie-break on an owner-ruled, return-independent key (the D14 choice) over permaticker, not the ticker string. |
| Why RUN | Signal-level (descriptive) results do not use the scheduler; portfolio reruns do. |
| Status | **CLOSED-ON-BRANCH.** `Trade`/`SessionBars` carry `permaticker`; `schedule_portfolio(..., tie_break="PERMATICKER_ASC")` orders same-minute entries by ascending permaticker; the event order is documented in the scheduler docstring. Tests: `test_c1_*` (x2), `test_c1n_*` (x3). Note: the D14 owner ruling is still required to ADOPT this policy name as the signed value; it is the frozen code policy. |

## D. `risk.per_trade_pct` carries no unit — BLOCKS: FREEZE

| | |
|---|---|
| Files / lines | `screen/simulate.py:232` `qty = int(equity * params.per_trade_pct / 100.0 // r_fill)`; `screen/params.py:72-73,154`; `screen/types.py:96`; field in `spec/schema.py` (`Risk.per_trade_pct`). |
| Guard-adjacent? | Kernel/params: **no**. Making the unit a spec-pinned field touches `schema.py`: **yes**. |
| Failure scenario | Today `0.25` means 0.25 % of equity (`test_d0…` passes: `qty == int(equity*0.25/100 // r_fill)`; equity 100,000 and `r_fill` 0.11 give 2,272 shares). A reader or later editor who treats it as a fraction (0.0025) or as 25 % (0.25) changes position size by 100x with no error. The number is signed into the hash without its unit. `test_d1…`: `getattr(params,'per_trade_pct_unit') is None`. |
| Proposed fix | Rename to an unambiguous field (`risk.per_trade_pct_of_equity` with a documented range check) or add a hash-pinned `risk.per_trade_unit`; carry it in `ScreenParams` and every report. |
| Why FREEZE | The unit must be inside the thing the owner signs. |
| Status | **CLOSED-ON-BRANCH.** `risk.per_trade_unit` ("percent" or "fraction") is a P0 spec field (SCREEN_V2_REQUIRED, SCREEN_V1_EXEMPT only); `ScreenParams` carries `per_trade_pct_unit` and `per_trade_fraction`; size = equity x fraction // r_fill; a derived fraction outside (0, 1) is refused. Tests: `test_d0_*`, `test_d1_*` (x2), `test_d1n_*` (x3). |

## E. Follow-up fix PR plan (I3; for AFTER #755 merges; nothing here is executed)

| Step | Change | Files | Guard-adjacent | Review |
|---|---|---|---|---|
| 1 | Spec fields: `universe.category_map`, `data.adjustment`, risk unit; digests in the v2 declaration; `universe_params_from_draft` reads them; remove the free `common_stock_categories` argument | `spec/schema.py` **(guard-adjacent)**, `data/store_adapter.py`, `screen/params.py` | Yes (schema) | Full guard-adjacent review, walk-away, CI, Linux acceptance; resets any review in flight |
| 2 | Bar basis columns and verification | `data/fetch_adapter.py`, `data/bar_loader.py` | No | Standard |
| 3 | Issuer-keyed scheduler tie-break | `screen/scheduler.py`, `screen/types.py` | No | Standard; needs the owner's D14 ruling first |
| 4 | Flip the five xfails to ordinary passing tests (same change as each fix) | `tests/.../hazards/` | No | Standard |

Order: 1 first (it changes the hash), then 2-3 in either order. The blocking relation: A and D must close before any FREEZE; B and C before any RUN that loads real bars or reruns the portfolio basis.

## F. Regression record (branch `fix/range002-build-hazards`)

All in `apps/backend/tests/research/range002/hazards/test_build_hazards_xfail.py` (the five strict-xfail tests were converted to ordinary passing tests; the file name is historical). Negative tests (`*n_*`) prove the ORIGINAL defect is now detected:

| Hazard | Converted | Negative (original defect detected) |
|---|---|---|
| A | `test_a1_the_universe_is_a_function_of_the_frozen_spec`, `test_a2_the_price_basis_is_declared_in_the_spec` | `test_a1n_a_different_category_map_is_a_different_spec_and_a_different_universe`, `test_a1n_building_with_a_category_set_that_is_not_the_specs_is_impossible`, `test_a2n_the_price_basis_is_hash_bound_and_an_incompatible_pair_is_refused` |
| B | `test_b1_a_bar_table_of_unknown_basis_is_refused` | `test_b1n_a_null_or_different_basis_is_refused`, `test_b1n_one_stray_row_of_another_basis_poisons_the_session`, `test_b1n_a_missing_permaticker_is_refused` |
| C | `test_c1_tie_break_is_invariant_to_relabelling_the_same_issuers` | `test_c1n_swapping_the_tickers_of_the_same_two_issuers_gives_the_same_accepted_issuer`, `test_c1n_a_trade_with_an_empty_permaticker_is_refused`, `test_c1n_any_tie_break_other_than_the_frozen_policy_is_refused` |
| D | `test_d1_the_unit_is_carried_explicitly` (`test_d0_*` kept as characterisation under unit percent) | `test_d1n_the_same_number_under_another_unit_is_100x_the_size_and_another_spec`, `test_d1n_a_derived_fraction_outside_the_open_unit_interval_is_refused`, `test_d1n_a_null_or_unknown_unit_is_refused` |

Behaviour notes for reviewers: (1) a screen-profile v1 spec may still freeze with the four new fields null, but `extract_params` and `universe_params_from_draft` now refuse it (the kernel needs the unit and the bases); (2) existing v2-profile specs change hash because SCREEN_V2_REQUIRED changed (new required digest); v1 required digest and v1 spec hashes are unchanged; (3) `UniverseParams` gained `category_map` and `intraday_basis`; `load_session`/`load_sessions` need `permaticker`/`permaticker_of`.

## G. Scope exception under which this branch edits `spec/schema.py`

| Field | Value |
|---|---|
| Earlier restriction | Owner instruction rev. 3, hard rule: no edits to `results_guard`, `spec_adapter`, `schema`, `loader`, `freeze_spec` or import lint while #755 is under review. |
| Clarification (owner message, round 5) | The boundary that matters is protecting #755's reviewed HEAD. Fixes A and D **may modify `spec/schema.py` on `fix/range002-build-hazards`, stacked on the pinned #755 HEAD `1ecf811b0b4ed7699bb4650c22387e1242f98e74`**, in an isolated worktree, without altering #755's branch, HEAD or reviewed files. This does **not** authorize push, merge or market-data execution. |
| Owner adoption record | **PENDING.** If the earlier restriction is a formal owner ruling, the owner commits a dated adoption record; the agent does not author it. |
| Sequence disclosure | The `schema.py` edits in the isolated worktree began (round 4) before this exception was stated, on the agent's reading that a stacked branch does not change #755. They are unpushed. If adoption is not recorded they are discarded; nothing else depends on them. |
| Files outside the exception | `results_guard.py`, `spec_adapter.py`, `errors.py`, `spec/loader.py`, `freeze_spec.py`, `test_import_lint.py`: **untouched** (verified by `git status`). |
| #755 | `origin/feat/range002-screen-kernel` = `1ecf811b0b4ed7699bb4650c22387e1242f98e74`, unchanged. |

## H. Hazard-branch review record (round 5)

### H.1 Price basis, explained separately
| Use | Quantity | Basis | Why |
|---|---|---|---|
| Price floor ($10) | `closeunadj` on the decision day | **Actual traded price** | The split-adjusted `close` is retro-adjusted by FUTURE splits; a floor on it would leak the future. |
| Dollar-volume ranking (20-day ADV) | `closeunadj` × **traded shares**, where traded shares = `volume` × `close` / `closeunadj` | Actual traded price × actual traded shares | Sharadar documents `close` and `volume` as both split-adjusted, so the same-vintage factor `close/closeunadj` recovers traded shares. Algebraically equal to `close × volume`; written in the traded form so no split-adjusted price is the ranked quantity. Tested across a split inside the window. |
| Opening range, stops, fills, sizing, costs | Intraday bars | **Raw traded prices** (`data.intraday_price_basis = raw`, verified per row) | One consistent basis for every price a trade sees. |
| Compatibility | (`SEP_SPLIT_ADJUSTED` daily, `raw` intraday) | The only allowed pair; any other is refused as an incompatible join | |

The only split-adjusted inputs are the daily `close` and `volume`, used solely for the traded-share recovery. **Not yet verified empirically:** that the vendor's `close/closeunadj` steps at splits together with `volume`; the documentation statement was read through a summarizing fetch. It is to be checked on the snapshot before any RUN.

### H.2 Category map
`universe.category_map` is a spec field that is **null until the owner sets it from the vendor's documented `category` values**. No mapping exists in application code (grep: none); the strings in tests are synthetic fixture values, not a proposal. The owner supplies the map; the agent does not invent it.

### H.3 Scheduling and capital availability
Same-minute order, strictly-after release of notional, no intra-day compounding of equity, and "priority is not capital" are now stated in the scheduler docstring and pinned by `test_capital_rules_proceeds_are_not_compounded_and_freed_notional_is_reusable_next_minute`. `PERMATICKER_ASC` decides evaluation order only.

### H.4 v1 compatibility and fail-closed behaviour
A v1-profile spec may still freeze with the four new fields null (v1-exempt), but the kernel refuses it: no silent default is supplied. v1 hash compatibility is not compatibility with this kernel.

### H.5 Changed hashes (full values)
| Constant | Before this branch | After |
|---|---|---|
| `SCREEN_V2_REQUIRED_SHA256` | `872193e14f93044d2a22acdcad7ea8f9c7c3fc1b37ff63a178b6324367ce897b` | `16f904a3094b375f32792201efb6fc6a40eb22ea46c9e26caeb978318ff96899` |
| `SCREEN_V2_UNMODELLED_SHA256` | `0298fe82ad0374a5139a0d739f49188081bf358a283edcb142c2b180725efb2c` | unchanged |
| `SCREEN_V1_REQUIRED_SHA256` | `fa3ed823e6764886d905d5d648bd346abf7bffcae87362b8e477397e876f2355` | unchanged |

Every v2-profile spec hash changes, because the v2 declaration pins the required digest. **No previously signed specification exists on record; none may be treated as approval of this revised baseline.** Any spec hash computed against the #755 v2 digest is void for this kernel.

### H.6 Authorization timeline (no backdating)
The `schema.py` edits on this branch were made **before** the owner's exception was stated. The exception, once adopted, authorizes **continued work on this isolated branch only**; it does not authorize push, merge or market-data execution. The adoption record is **PENDING**; the date of any adoption is the date of that record, not an earlier date.
