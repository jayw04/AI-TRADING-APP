# RANGE-002 build hazard defect records v0.1 (LANE I)

| Field | Value |
|---|---|
| Status | **DEFECT RECORDS + strict-xfail demonstrations. NO FIXES.** `[MERGE NOT APPROVED]` |
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

## B. Intraday bars carry no basis tag; the loader cannot refuse a wrong basis — BLOCKS: RUN

| | |
|---|---|
| Files / lines | `data/fetch_adapter.py:27,111-112` (the fetch path hard-codes `adjustment == "raw"`); `data/bar_loader.py:70` (`SELECT ... FROM "minute_bars"`: the table has no basis column and nothing verifies one). PIT universe is split-adjusted by design (`pit_universe.py:41`). |
| Guard-adjacent? | **No.** |
| Failure scenario | A `minute_bars` table filled elsewhere with split-adjusted bars (a later 10:1 split makes prices one tenth) is loaded at one-tenth scale: `load_session` returns a normal session, the $10 floor was applied on the unadjusted price while stops, widths in ticks and sizing now see adjusted prices, and `min_or_width_ticks` eligibility changes silently. `test_b1…`: `DID NOT RAISE` for a table of unknown basis. |
| Proposed fix | Add `basis` (and `adjustment_as_of`) columns to `minute_bars`; `fetch_and_store` writes them; `load_session` takes the required basis from the spec and raises `DataDefectError` on missing/different. |
| Why RUN | It only bites when real bars are loaded; the mock path cannot produce a wrong basis. |

## C. Scheduler tie-break is keyed by the ticker string — BLOCKS: RUN (portfolio basis)

| | |
|---|---|
| Files / lines | `screen/scheduler.py:76` `ordered = sorted(trades, key=lambda t: (t.entry_time, t.symbol))`; `Trade.symbol` is a vendor ticker (`screen/types.py`). |
| Guard-adjacent? | **No.** |
| Failure scenario | Two issuers enter in the same minute with capacity for one. Issuer A (entry 11.0) is `AAA`, issuer B (entry 22.0) is `ZZZ`: A is accepted. After a rename the same two issuers carry `ZZZ` and `AAA`: B is accepted. `test_c1…`: `11.0 != 22.0`. The portfolio result depends on the ticker spelling, and a reused ticker is indistinguishable. Neither declared D14 tie option is "ticker ascending" (worksheet note). |
| Proposed fix | Carry `permaticker` on `Trade`; tie-break on an owner-ruled, return-independent key (the D14 choice) over permaticker, not the ticker string. |
| Why RUN | Signal-level (descriptive) results do not use the scheduler; portfolio reruns do. |

## D. `risk.per_trade_pct` carries no unit — BLOCKS: FREEZE

| | |
|---|---|
| Files / lines | `screen/simulate.py:232` `qty = int(equity * params.per_trade_pct / 100.0 // r_fill)`; `screen/params.py:72-73,154`; `screen/types.py:96`; field in `spec/schema.py` (`Risk.per_trade_pct`). |
| Guard-adjacent? | Kernel/params: **no**. Making the unit a spec-pinned field touches `schema.py`: **yes**. |
| Failure scenario | Today `0.25` means 0.25 % of equity (`test_d0…` passes: `qty == int(equity*0.25/100 // r_fill)`; equity 100,000 and `r_fill` 0.11 give 2,272 shares). A reader or later editor who treats it as a fraction (0.0025) or as 25 % (0.25) changes position size by 100x with no error. The number is signed into the hash without its unit. `test_d1…`: `getattr(params,'per_trade_pct_unit') is None`. |
| Proposed fix | Rename to an unambiguous field (`risk.per_trade_pct_of_equity` with a documented range check) or add a hash-pinned `risk.per_trade_unit`; carry it in `ScreenParams` and every report. |
| Why FREEZE | The unit must be inside the thing the owner signs. |

## E. Follow-up fix PR plan (I3; for AFTER #755 merges; nothing here is executed)

| Step | Change | Files | Guard-adjacent | Review |
|---|---|---|---|---|
| 1 | Spec fields: `universe.category_map`, `data.adjustment`, risk unit; digests in the v2 declaration; `universe_params_from_draft` reads them; remove the free `common_stock_categories` argument | `spec/schema.py` **(guard-adjacent)**, `data/store_adapter.py`, `screen/params.py` | Yes (schema) | Full guard-adjacent review, walk-away, CI, Linux acceptance; resets any review in flight |
| 2 | Bar basis columns and verification | `data/fetch_adapter.py`, `data/bar_loader.py` | No | Standard |
| 3 | Issuer-keyed scheduler tie-break | `screen/scheduler.py`, `screen/types.py` | No | Standard; needs the owner's D14 ruling first |
| 4 | Flip the five xfails to ordinary passing tests (same change as each fix) | `tests/.../hazards/` | No | Standard |

Order: 1 first (it changes the hash), then 2-3 in either order. The blocking relation: A and D must close before any FREEZE; B and C before any RUN that loads real bars or reruns the portfolio basis.
