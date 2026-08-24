# SEC-001 V3 — PIT Universe Liquidity Defect: Ruling and Amendment v1.0

**Status:** **SEALED 2026-08-24 (owner).** Amends the frozen §5.1 universe definition of `TradingWorkbench_SEC001_V3_Design_Implementation_v0_3.md`.
**Discovered:** during qualification Gate 5 of the governed store rebuild, **before** any union derivation, crawl, coverage measurement or economic run.
**Trial ledger:** **PRE-TRIAL CONSTRUCTION DEFECT — no trial consumed; no economic outcome observed.** V3-RC remains **trial #1**.
**Coverage rule:** `5b26ffa209a6…` (0.95 / 0.95 / 20 y) remains **UNSPENT**.

---

## 1. The defect

`FactorDataStore.dollar_volume_universe` ranks the PIT universe by `SUM(close * volume)`. In Sharadar SEP, **`close` is the split-adjusted series** and **`volume` is raw shares traded**. The product is therefore dimensionally invalid: an adjusted price multiplied by unadjusted volume. Reverse splits inflate the adjusted price without bound, so the error is unbounded and grows with distance into the past.

Evidence from the governed store (`89c4680f…`), 2015-11-02:

| ticker | `close` (adjusted) | `closeunadj` (traded) | `volume` |
|---|---:|---:|---:|
| **NUWE** | **3,124,661,463,902.45** | **2.41** | **1** |
| AAPL | 30.295 | 121.18 | 128,813,000 |

**752 tickers** across **1,336,142 rows** carry `close / closeunadj > 100`; 223 tickers exceed a `close` of 100,000. The consequence is that the historical "top-200 by liquidity" is partly reverse-split noise: at 2015-11-16 the frozen ranking's top three are **NUWE, JAGX, WHLR** — names trading on the order of one share per day — ahead of AAPL.

Membership error against a dimensionally valid ranking:

| as_of | frozen ∩ true (top-200) | names wrong |
|---|---:|---:|
| **2000-01-03** | **135/200 (68%)** | **65** |
| 2008-09-15 | 148/200 (74%) | 52 |
| 2015-11-16 | 171/200 (86%) | 29 |

**The error is worst in the deepest history** — exactly the region the 20-year floor (`θ_span_min`) forces V3 to occupy. Returns are unaffected: factors price off `closeadj`, which is correct. Only the liquidity *ranking* is wrong.

## 2. Ruling — the corrected universe

Frozen for SEC-001 V3 as **`PIT_LIQUID_TOP_N_V2` / `TRUE_TRADED_DOLLAR_V1`**:

> Daily traded dollar volume = **`SEP.closeunadj × SEP.volume`**.
> The historical PIT liquidity ranking retains the previously frozen trailing aggregation window, rebalance calendar, eligibility rules, minimum-observation rules, tie-breaking and **N = 200**. **Only the dimensional price input changes**, from adjusted `close` to contemporaneous `closeunadj`.

**No other universe change may be introduced while correcting this.**

The prior implementation is identified as **`LEGACY_ADJUSTED_CLOSE_X_RAW_VOLUME` — NONCONFORMING FOR LIQUIDITY RANKING**, and is retained **only** so existing V1/V2 evidence remains reproducible. It is never a V3 input.

## 3. Not a trial

V3-RC remains **trial #1**. At the moment of discovery the program had **not** derived the PIT-200 union, started the classification crawl, applied the frozen coverage rule, run V3-RC, or observed any return, Sharpe, drawdown, sector performance or promotion metric. The trial ledger counts **candidates evaluated against economic history**, not defects found while qualifying the frozen input construction. Recorded as **PRE-TRIAL CONSTRUCTION DEFECT**.

## 4. No in-place patch of the shared helper

Production and prior SEC-001 research share the legacy implementation. Replacing `dollar_volume_universe`'s behaviour globally would change **another strategy's universe** merely because SEC-001 found the bug. Therefore:

1. implement and **version** the corrected pure universe function;
2. bind **SEC-001 V3 explicitly** to that version;
3. add regression fixtures proving the dimensional correction;
4. **separately enumerate every consumer** of the legacy helper;
5. adjudicate their migration **independently**.

After that blast-radius review the platform may choose to make V2 the generic default — but SEC-001 must not silently change shared economics on its way through qualification.

## 5. Required tests — this exact failure class

The NUWE case becomes a permanent regression fixture. At minimum:

- reverse-split-adjusted `close` **cannot** inflate liquidity;
- `closeunadj × volume` produces contemporaneous traded-dollar ordering;
- AAPL-like high-volume trading ranks **ahead of** a one-share microcap in the demonstrated fixture;
- multiplying historical adjusted close by raw volume is **prohibited** in the V2 implementation;
- universe size is **exactly 200** whenever ≥200 eligible names exist;
- the corrected universe is **deterministic** across repeated runs against the same store SHA.

Cover **several corporate-action cases**, not just one extreme reverse split — the bug is a *class*, and a single fixture would prove only that one instance was handled.

## 6. The governed store is not defective

Store SHA **`89c4680f76a556d56ccd2e055605b3925375366fca41a40910edd1b844216d39`** does not become defective because a consumer queried it incorrectly. Gates 1–4 stand: historical breadth back to 1997 (8,553 names in 2000), `permaticker` 20,940/20,940, fail-closed `permaticker_asof`, zero duplicate tickers, zero SEP names missing a reference row. **The store is not rebuilt.**

After this amendment is sealed:

1. **rerun Gate 5** with the corrected, versioned universe;
2. test **the entire frozen weekly rebalance grid** from the start date through 2026-06-12 — count = 200 and identity resolution — not a seven-Monday sample;
3. then run the **pre-frozen laptop reconciliation**; unexplained differences affecting universe membership still **block** qualification;
4. only then promote this store from `build/` to the sealed custody tier.

**The union must never be derived from the defective ranking, even temporarily.**

## 7. Consequences for the V2 comparison

The V2 structural reference must be recomputed **again**. The authoritative reference for §9.3 / §10 uses: the corrected true-traded-dollar PIT universe; the adjudicated GICS-11 classification; the same final evaluation period and windows; the frozen 10 / 25 bps one-way-turnover cost convention; and **V2's intended economic construction — not its nonconforming live implementation**. It remains a *structural* comparison, never inheritable V3 evidence.

**§10.1 explanatory amendment:** the absolute **Net Sharpe ≥ 0.75 gate remains frozen and does not move**. The "V2 ~0.51" figure it cites is relabelled a **legacy defective-universe reference**, because the corrected V2 benchmark may differ. The relative gate stands unchanged: **V3 Sharpe > corrected V2 Sharpe AND V3 drawdown shallower than corrected V2 drawdown.**

## 8. The restatement limitation survives

This correction does **not** erase the approved SEP-restatement caveat. The corrected universe is still **historical membership reconstructed from the vendor's currently restated SEP history**. What changed is that its liquidity measure is now dimensionally valid. The evidence package must continue to state the limitation rather than describe the universe as a pristine contemporaneous snapshot.

## 9. Forensic retention

The **defective membership samples are retained as forensic evidence** — they are the proof of why this amendment was necessary. `build/store/2026-08-24/pit200_sample.json` holds the legacy-ranked PIT-200 for seven dates and is preserved, labelled nonconforming.

## 10. Authorized sequence

seal this ruling → implement the versioned `closeunadj × volume` universe → tests → rerun Gate 5 across the **full** weekly grid → qualification + reconciliation → seal the qualified store → derive and hash the corrected PIT-200 membership and union → **only then** the EDGAR crawl → the frozen coverage measurement → period/window seal → corrected V2 reference and V3-RC.

*The MDQ free-space obligation before Monday 2026-08-24 09:25 ET is separate, unchanged, and must use its own live wrapper measurement.*
