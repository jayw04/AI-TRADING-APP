# Trading Workbench — SEC-001 V3: Risk-Compatible Sector Baskets
## Design & Implementation Specification v0.3

| Field | Value |
|---|---|
| Program | **SEC-001 V3 — Risk-Compatible Sector Baskets** |
| Strategy family | Sector rotation / long-only equity |
| Status | **PROPOSED GOVERNING DESIGN — APPROVED WITH TWO BLOCKING CORRECTIONS (applied in this revision); V3-RC run BLOCKED on the §5.1a sector-classification DISPOSITION RULING — the Q1–Q5 provenance investigation is executed and recorded in §5.1b** |
| Date | 2026-08-23 |
| Supersedes | v0.2 (v0.1 + Review 1); this v0.3 applies Review 2's rulings. Does **not** rewrite SEC-001 V1/V2 evidence. |
| V2 runtime | Strategy 7 / Account 5 / `sector-rotation` v1.0.0 — **NONCONFORMING; RETIRE** |
| Proposed V3 runtime identity | New strategy record; recommended runtime version **2.0.0** (material economic/construction change) |
| Economic objective | Build a **deployable, net-profitable sector-rotation strategy** with bounded drawdown, bounded concentration, and a small number of positions; avoid a broad research program or factor zoo. |
| Core signal | **12-1 momentum = 252-session lookback / 21-session skip** |
| Sector count | **K = 3** |
| Position cap | **10% maximum per name** |
| Primary new mechanism | **Representability-first sector selection + concentrated risk-compatible sector baskets** |

> **Program stance.** SEC-001 V3 is not a repair of the failed V2 live implementation and does not inherit V2's paper track record. V3 is a new economic strategy candidate. The design intentionally limits research freedom: one primary candidate, one factor family, one construction, explicit profitability gates, and a short go/no-go path to paper.

**v0.3 changes (Review 2 rulings, 2026-08-23):** sector-classification provenance is now a **run blocker** — the current single-row `tickers.sector` lookup takes no as_of date and may never be labeled PIT; a five-question read-only investigation (§5.1a) must prove a historical source or the absence is explicitly adjudicated. Cost model corrected to Factor Lab's canonical one-way-portfolio-turnover convention and frozen at **10 bps base / 25 bps stress**. Evaluation period **2000-01-01 → 2026-06-12** and the five V2-helper walk-forward windows frozen. Breadth diagnostic upgraded to selected-vs-all-representable. Trial ledger notes pre-ledger V1/V2 exposure of the same history. Everything else freezes as written at v0.2. **Added after Review 2:** §5.1b records the executed §5.1a Q1–Q5 provenance investigation — findings only; it adjudicates nothing.

**v0.2 changes (Review 1, 2026-08-23):** sector-classification pin added to the pre-registration (§5.1a — source, field, version, PIT semantics, unclassified handling, restatement; BLOCKING); validation-run freeze completed (§9.4 — evaluation period, walk-forward window boundaries, base cost model; BLOCKING before the run); SEC-001 trial ledger (§10.4 — the historical window is a consumable; V3-RC is trial #1); small-sector score-noise artifact recorded as accepted with a breadth-distribution diagnostic (§5.3, §10.2); mid-execution representability-break rule (§5.8). No change to the thesis, constraints, gates, architecture, or non-goals.

---

## 1. Executive decision

### 1.1 SEC-001 V2 — retire and contain

SEC-001 V2 is **retired as a deployable strategy**. The live Account-5 book never represented the governed V2 strategy: the deployed runtime used 252/0 instead of 252/21 and sized equal-weight per name instead of equal sector sleeves. The resulting book therefore measured a different strategy and is not admissible as SEC-001 economic evidence.

The owner ruling remains: **contain; do not repair V2 in place.** Strategy 7 stays stopped/IDLE, the forensic record remains immutable, and the current Account-5 positions are flattened through the authenticated OrderRouter/audit path. No direct DB status edits and no ad-hoc broker flatten are authorized.

### 1.2 SEC-001 V3 — start a new profitability-first program

V3 keeps only the parts of SEC-001 that remain economically useful:

- 12-1 momentum (`252/21`), not the deployed 252/0 drift;
- top **3** sectors;
- equal sector sleeves;
- long-only, weekly rotation;
- maximum **10%** per name;
- the same governed liquid-equity universe concept, reconstructed point-in-time.

V3 changes the construction deliberately. It first proves the target is representable under the 10% cap, skips sectors that cannot support a full sleeve, and concentrates each selected sector in its strongest **4–5** eligible names rather than holding every constituent. This is the new economic mechanism and therefore requires new prospective validation.

### 1.3 Primary goal

The goal is not to maximize research output. The goal is to answer one business question quickly and defensibly:

> **Can a risk-compatible, sector-neutral 12-1 momentum book produce attractive net returns with materially better drawdown and implementation quality than SEC-001 V2?**

If the answer is no, V3 stops. No K-grid, factor zoo, regime-filter ladder, optimizer, or post-hoc rescue variants are authorized inside this program.

---

## 2. SEC-001 V2 disposition and closure plan

### 2.1 Disposition

| Item | V2 ruling |
|---|---|
| Strategy 7 / `sector-rotation` v1.0.0 | **RETIRED / NONCONFORMING** |
| Account 5 scheduler | Remains disabled while contained |
| Existing V2 paper P&L | **Not SEC-001 evidence**; measured a different strategy |
| V2 research evidence | Preserve as historical scientific evidence only |
| V2 production code | Preserve for incident reconstruction; do not patch into V3 |
| V2 strategy record | Do not reactivate |
| V2 positions | Flatten through authenticated, audited path |
| V2 verdict inheritance | **None** — V3 changes selection/construction |
| Account 5 reuse | Allowed only after 0 positions, 0 open orders, containment closeout recorded |

### 2.2 C5b flatten gate

Before V3 uses Account 5:

1. Confirm strategy 7 is still `IDLE` and not scheduled.
2. Record position count, market value, cash/equity, and open-order count.
3. During RTH, execute the authenticated flatten workflow through OrderRouter and the audit path.
4. Verify `positions = 0` and `non_terminal_orders = 0`.
5. Seal a post-flatten evidence record linked to the 2026-08-22 incident.
6. Only then may Account 5 be reset/reused for V3.

### 2.3 V2 facts that must never leak into V3 defaults

The following deployed-V2 settings are specifically **not** V3 defaults:

- `sector_momentum_skip_days = 0`;
- equal-name weighting across the entire target;
- MOM-001 market-regime filter inherited by copy;
- MOM-001 vol-scaling inheritance;
- static symbol registration as a substitute for the governed PIT universe;
- any assumption that “registered = owned” or “account position = strategy position.”

---

## 3. V3 profitability thesis

V3 has one economic thesis and three implementation claims.

### 3.1 Economic thesis

Sector momentum has useful cross-sectional information, but V2 diluted that information by holding every name in the selected sectors and was not representable under the platform's 10% per-name cap when a selected sector was too narrow. V3 should improve the trade-off by:

1. selecting only sectors whose basket can be fully represented;
2. preserving equal sector sleeves;
3. concentrating each sleeve in the strongest names using the **same 12-1 momentum family**, rather than introducing another factor;
4. keeping the book compact enough that costs, reconciliation, and attribution remain controllable.

This is a plausible mechanism, not a performance claim. V3 earns deployment only by passing the prospective profitability gates in §10.

### 3.2 Why this is commercially preferable to a broad research program

- **One factor family:** 12-1 momentum only.
- **One sector count:** K=3.
- **One risk cap:** 10%.
- **One primary basket construction:** representable sector sleeves with 4–5 names per sector.
- **One cost model and one stress level.**
- **One promotion decision:** GO or STOP.

The program does not optimize dozens of thresholds to maximize historical Sharpe.

---

## 4. Non-negotiable strategy constraints

| Constraint | V3 rule |
|---|---|
| Signal window | `lookback_sessions = 252`, `skip_sessions = 21` |
| Sector count | `K = 3` |
| Direction | Long-only |
| Leverage | None; gross target ≤ 100% |
| Per-name cap | `max_position_pct = 0.10` |
| Sector sleeves | Equal, each approximately `(1 - cash_buffer) / 3` |
| Partial-sector fallback | **Prohibited** |
| K fallback | **Prohibited** — no K=2/K=4 rescue |
| Cap increase | **Prohibited** |
| Infeasible target | `SEC001_TARGET_INFEASIBLE`; **no orders** |
| Rebalance cadence | Weekly |
| Runtime slot | Proposed Monday **10:24 America/New_York**; operational, not research economics |
| Market regime filter | **OFF / absent** in V3 baseline |
| Vol scaling | **OFF / absent** in V3 baseline |
| News / MDQ / DISC signals | Out of scope |
| Short-term live tuning | Prohibited |

---

## 5. V3 strategy definition

### 5.1 Point-in-time universe

At each rebalance, V3 uses the governed point-in-time liquid-equity universe with target size `N=200`.

```text
rebalance session
    -> PIT universe_asof(session, n=200)
    -> permanent security identity / ticker lineage
    -> factor-valid names
    -> sector classification
```

The exact top-200 ranking definition and source fingerprint must be pinned in the V3 pre-registration. A static registration list may not silently replace the PIT universe.

**Universe version — AMENDED 2026-08-24, see `SEC001_V3_UniverseLiquidity_DefectRuling_v1_0.md`.** V3 binds to **`PIT_LIQUID_TOP_N_V2` / `TRUE_TRADED_DOLLAR_V1`**: daily traded dollar volume is **`SEP.closeunadj × SEP.volume`**. The trailing window, rebalance calendar, eligibility, minimum-observation rules, tie-breaking and `N = 200` are unchanged; only the dimensional price input moves from adjusted `close` to contemporaneous `closeunadj`. The prior behaviour — **`LEGACY_ADJUSTED_CLOSE_X_RAW_VOLUME`, NONCONFORMING FOR LIQUIDITY RANKING** — multiplied a split-adjusted price by raw volume and put one-share reverse-split microcaps above AAPL in the historical top-200 (68% membership agreement at 2000-01-03). It is retained only so V1/V2 evidence stays reproducible and is **never a V3 input**.

### 5.1a Sector classification pin *(added v0.2 — BLOCKING for pre-registration)*

Sector membership is this strategy's load-bearing input: it determines the score, the breadth, the representability gate, and therefore everything downstream — and v0.1 left it unpinned while carefully pinning the universe. The V3 pre-registration must freeze:

- **Source and field:** the exact provider and field supplying sector classification (e.g., the Sharadar sector field), by name;
- **Taxonomy version:** which classification scheme/version, since granularity directly moves `N_min` feasibility — a finer taxonomy makes fewer sectors representable and a coarser one changes what "sector" means economically;
- **PIT semantics:** a name's sector is its classification **as of the rebalance session**, resolved through permanent identity — never today's restated value applied backward;
- **Unclassified handling:** names with missing/unknown sector are **excluded from every sector's score and breadth** with reason `sector_unclassified`, never silently dropped and never pooled into a synthetic bucket — because their treatment changes which sectors clear `N_min`;
- **Restatement behavior:** whether the source restates historical classifications, and if so, the reconstruction rule that preserves PIT-ness (the same discipline as the universe fingerprint).

A classification-source change after freeze is a research decision requiring a new candidate/version, exactly like a signal change.

**Store-reality ruling *(v0.3 — RUN BLOCKER)*:** the current factor store cannot satisfy this pin as it stands. `tickers` is a one-row-per-ticker, latest-value reference table, and the sector metadata query reads today's `sector` with no `as_of` parameter. Therefore, frozen:

> **V3-RC may not run until a reproducible historical sector-classification source is proven, or the unavailability of historical PIT sector classification is explicitly adjudicated. The current single-row `tickers.sector` lookup may never be labeled PIT.**

**Read-only investigation (precedes any freeze of the classification fields):**

1. What exact Sharadar artifact populates `tickers.sector`?
2. Does that artifact contain historical / effective-dated sector membership?
3. If yes, can we reconstruct `permaticker + rebalance_date -> sector_asof(rebalance_date)`?
4. If no, is there another **already-held** source with historical classification? In particular: archived snapshots of `factor_data.duckdb` (or the `tickers` table) across the platform's backup history are **true PIT observations** — each snapshot's sector column is what was believed on that date — and a partial effective-dated spine may be assemblable from archived beliefs, bounded by backup cadence, without purchasing anything.
5. What fraction of historical PIT-200 names would be unresolved under the best available reconstruction?

**Disposition if historical classification is unavailable** — one of two explicit rulings, and the asymmetry between them is recorded here so a later schedule-pressured decision cannot treat them as equivalent:

- **Disposition 1 (strongly preferred):** acquire or build a genuine effective-dated sector-classification spine. For a strategy whose *signal is defined at the sector level*, this is the only construction whose grouping variable is clean.
- **Disposition 2 (accept restated/static classification with a recorded limitation):** permissible only by explicit owner adjudication that names the bias mechanism: **restated classification leaks outcomes into the grouping variable of a momentum signal.** Reclassification frequently *follows* the price and business behavior momentum measures — a company re-sectored after a pivot or run-up appears in its future sector throughout its history — so the leak is directional, not neutral noise. Any Disposition-2 validation result carries that caveat permanently in its evidence package.



**Execution implication:** V3 may reuse the neutral PIT-universe / dynamic-symbol infrastructure built at the platform level, but it must not import LOW-001 selection logic. If the generic dynamic-universe execution capability is not production-ready when V3 is implemented, V3 activation stays blocked rather than reverting to static registration drift.


### 5.1b Provenance investigation — FINDINGS *(v0.3; §5.1a Q1–Q5 executed read-only 2026-08-23)*

The §5.1a investigation has been run. **The five questions are answered; the disposition is NOT adjudicated here** — §5.1a reserves that ruling to the owner, and nothing below selects Disposition 1 or 2. The run blocker therefore narrows from "investigate" to "rule."

**Evidence basis.** Read-only inspection of `apps/backend/data/factor_data_full.refresh.duckdb` (SEP 1997-12-31 → 2026-07-24, 39,152,452 rows; laptop copy dated 2026-07-26) and `apps/backend/data/mr002_research.duckdb` (dated 2026-07-12), plus the recorded 2026-07-11 live vendor probe in `docs/implementation/evidence/mr_002/V1_V4_raw_findings.json`, plus one live SEC fetch. No writes; no MR-002 outcome or economic field was read. Coverage figures come from **laptop copies**, not the governed `ec2-paper` store — they are directional for the ruling and must be re-measured on the governed artifact before any pre-registration freeze. ⚠ Every *repository-state* claim below was subsequently re-verified against `origin/main` at `a992a9e`; the first draft was written from a working tree 27 commits behind, which produced one wrong finding, now corrected in place and marked.

**Q1 — What populates `tickers.sector`.** Sharadar **TICKERS (`table=SEP`)**, a single full-table bulk pull, via `scripts/ingest_sharadar.py:125` → `FactorDataStore.ingest_tickers`, projected to `_TICKERS_COLS` (`app/factor_data/store.py:41`) and upserted keyed by ticker. Read back by `get_sectors()` (`store.py:445`) as `SELECT ticker, sector FROM tickers WHERE ticker IN (…)` — no date parameter anywhere in the path, confirming §5.1a's store-reality ruling.

> **Taxonomy correction (material).** The field is **not GICS**. Live distinct values are the Morningstar-style set — Technology, Financial Services, Consumer Cyclical, Consumer Defensive, Basic Materials, Healthcare, Industrials, Communication Services, Real Estate, Energy, Utilities (11 values + 134 NULL over 21,853 rows). V2's measured book (70.5% Technology) is stated in *this* taxonomy.

**Q2 — Historical / effective-dated membership: NO.** Established by live probe on 2026-07-11 and recorded in `V1_V4_raw_findings.json` block V2: `tickers_rows_for_aapl: 1`; `aapl_rows_per_table_param {SEP: 1, SF1: 1}`; **`tickers_has_effective_date_fields: false`**. The 28 vendor columns include `permaticker`, `sector`, `siccode`, `sicsector`, `famaindustry`, `lastupdated` — and no `effectivedate` / `startdate` / `enddate` / `asof`. Restatement is demonstrated rather than inferred: **META resolves to "Communication Services" today** though it was Technology before the GICS-2018 restructure, i.e. the present label is applied backward across its whole history — precisely the leak mechanism §5.1a names.

**Q3 — Reconstruction from TICKERS: not possible. A genuine PIT spine already exists.** MR-002 built an effective-dated classification spine that survives that program's termination because it is code and reference data, not population:

- `app/altdata/mr002/sic_history.py` — extracts `STANDARD INDUSTRIAL CLASSIFICATION: NAME [CODE]` from each filing's EDGAR `…-index-headers.html` SGML block: the classification **assigned at filing time**, with acceptance timestamps, frozen precedence (10-K > 10-Q, then later acceptance), missing-SIC-never-overwrites, and conflicts **excluded, never defaulted** (CAP-024).
- Resolvers `app/research/mr002/spq1/sector_pit.py` and `.../spq1/phase2b/sic_sector.py` — latest record available by close t; same-timestamp conflict → `SECTOR_EFFECTIVE_DATE_CONFLICT`; absent record → `SECTOR_PIT_IDENTITY_MISSING`; no present-day backfill.
- `sic_mapping` (110 rows, owner-countersigned 2026-07-11) — SIC ranges → the **GICS 11** plus sector ETF, with `effective_from` / `effective_to` carrying the true taxonomy dates (2700–2749 → Communication Services effective 2018-10-01), per-row confidence, rationale, reviewer, and a `review_status` of `excluded_low` that already implements §5.1a's exclude-with-reason requirement.
- 33 `security_sector_overrides`, and a 1,068-row ticker→CIK `crosswalk` derived from the TICKERS `secfilings` field (so the identity join itself needs no crawl).

**Q4 — Other already-held sources.** The EDGAR spine above is the only viable one. **§5.1a's archived-snapshot idea is a dead end and should not be pursued:** the sole backup on disk is `apps/backend/data/backups/workbench-2026-06-01.sqlite` (the application DB, not the factor store), and the factor store itself was first created in June 2026 — so even a complete archive of past beliefs would cover roughly 2 months of a 26.5-year window. `siccode`, `sicsector` and `famaindustry` are latest-value on the same single row; SF1 carries no sector.

**Q5 — Unresolved fraction of the historical PIT-200.** Measured at the frozen §9.4 walk-forward boundary dates, resolving ticker → CIK through the effective-dated crosswalk and requiring a PIT SIC observation accepted on or before the date:

| as_of | in crosswalk | PIT-SIC resolved | unresolved |
|---|---:|---:|---:|
| 2000-01-03 | 111 | 0 | **200 (100%)** |
| 2005-04-15 | 147 | 0 | **200 (100%)** |
| 2010-07-29 | 175 | 141 | 59 (29.5%) |
| 2015-11-11 | 192 | 164 | 36 (18.0%) |
| 2021-02-23 | 174 | 161 | 39 (19.5%) |
| 2026-06-12 | 180 | 180 | 20 (10.0%) |

The held spine spans **2010-01-05 → 2026-07-10 only** (40,522 observations, 764 CIKs, zero NULL SIC). **The first 10.0 years — 38% of the frozen 2000-01-01 → 2026-06-12 evaluation period — have no coverage at all**, and frozen walk-forward windows 1 and 2 are essentially entirely uncovered. **As it stands, the spine cannot serve the §9.4 freeze.**

**Rebuild cost — modest, no purchase required.** 798 distinct names ever entered an annual-grid PIT-200 across 2000–2026 (a weekly rebalance grid will exceed this; treat 798 as a floor). MR-002 averaged ~53 header fetches per CIK over 16 years ⇒ ~106 over 26.5 ⇒ on the order of 85,000 header fetches plus one submissions JSON per CIK — about 2.4 hours of request time at SEC's 10 req/s ceiling, i.e. one unattended crawl.

**Residual gaps** — one real and closable by registered change, one withdrawn on re-verification; neither is a data-availability blocker:

1. **Foreign private issuers.** ADRs are **3.5–10.0% of the PIT-200** (10.0% at 2021-02-23) and file 20-F / 40-F, which `DEFAULT_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")` excludes ⇒ they would resolve to `SECTOR_PIT_IDENTITY_MISSING` for their whole history. Verified live 2026-08-23 that the data itself exists: TSM's 2026-04-16 **20-F header carries `SEMICONDUCTORS & RELATED DEVICES [3674]`**. Closing this is a registered extension of the form list, not an acquisition.
2. **Permanent identity — ⚠ CORRECTED 2026-08-23: this gap does not exist on `main`.** As first written this item claimed `_TICKERS_COLS` drops `permaticker`. That was measured against a working tree **27 commits behind `origin/main`** and is **wrong**. `permaticker` has been in the store projection, the DDL, the idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS` migration and the explicit ingest column list since **PR #542, 2026-07-29** (`5173b7c`), under owner ruling `PERMATICKER_EFFECTIVE_INTERVAL_V1`. `FactorDataStore.permaticker_asof(ticker, as_of)` already resolves identity point-in-time and **fails closed** — returning `None`, never a guess, when the ticker is unknown, the column is NULL, or `as_of` falls outside that row's `[firstpricedate, lastpricedate]` effective interval. **No registered change is required for identity.** What survives is not a gap but a *measurement*: the resolver answers only for the lineage holding a bare ticker **now**, so a historical PIT-200 name whose symbol was later reused by another issuer resolves to `None` and takes `sector_unclassified` semantics. The historical resolution rate is therefore a quantity to measure under rider item 2, not a capability to build.

**Finding A — how often classification actually moves (bears directly on the Disposition-2 asymmetry).** Within the held PIT SIC data, **93 of 764 CIKs (12.2%)** carry more than one distinct SIC across 2010–2026, and **≈64 (8.4%) cross a sector boundary** under the countersigned mapping (approximate: this count matches SIC ranges without applying `effective_from`). For a construction that selects 3 sectors from 11, roughly one name in twelve being misgrouped — in the directional manner §5.1a describes — is a material quantity, not tail noise.

**Finding B — the taxonomy mismatch is the substantive decision.** The two candidate sources are in different taxonomies: Sharadar `sector` is Morningstar-style; the countersigned `sic_mapping` targets GICS. Adopting the EDGAR spine therefore changes what "sector" means economically — which §5.1a already flags as moving `N_min` feasibility — and it also breaks comparability with the **§9.3 "SEC-001 V2 pure baskets" reference**, which was constructed in the Sharadar taxonomy. Recommendation for the ruling: if the spine is adopted, **recompute the V2 structural reference under the same taxonomy**, so all three §9.3 arms share one grouping variable.

**⚠ Code defect that must not be inherited.** `app/research/mr002/spq1/adapters/pit_sector_adapter.py::sic_to_sector` resolves `_SIC_DIVISION.get(str(sic).strip()[:1], "MATERIALS")` — silently defaulting an unrecognised SIC to Materials, contradicting the never-default rule asserted in its own module docstring and in `sic_history.py`. **V3 must reuse the Phase-2B path** (`phase2b/sic_sector.py`: hash-bound mapping, fail-closed refusals), never the Phase-2A adapter.

**What the ruling now requires.** Disposition 1 is achievable at overnight-crawl cost and needs **two** registered changes — not the three first recorded here, because identity is already shipped (see the correction above): extend the crawl form list to 20-F / 40-F; and extend the crawl back to 2000-01-01 across the ~800-name union. Disposition 2 remains available only under the §5.1a asymmetry, now with Finding A's measured 8.4% boundary-crossing rate attached to it.

### 5.2 Individual momentum

For each eligible security `i`:

```text
M_i(t) = total_return from t-252 sessions to t-21 sessions
```

No 252/0 fallback is allowed.

### 5.3 Sector score

For each sector `s`, using all factor-valid names in the PIT universe:

```text
SectorScore_s(t) = mean( M_i(t) for i in sector s )
```

Ties are resolved deterministically by sector name.

**Known accepted artifact *(recorded v0.2)*:** a small-breadth sector's mean momentum is substantially noisier than a large sector's, so minimum-breadth sectors are disproportionately likely to post extreme scores and be selected. V3 deliberately does **not** add shrinkage, a robustness estimator, or a breadth-weighted score — any of those is a new knob, and this program's discipline is one construction. The artifact is instead made *visible*: selected-sector breadth distribution is a mandatory secondary diagnostic (§10.2), and persistent minimum-breadth selection in validation or paper is a finding for the owner to see, not a threshold to quietly tune.

### 5.4 Representability gate

A selected sector must be capable of carrying its full equal sleeve without any name breaching the 10% cap.

General form:

```text
sector_sleeve = (1 - cash_buffer_pct) / K
N_min = ceil(sector_sleeve / max_position_pct)
```

With `K=3`, `max_position_pct=10%`, and a proposed 2% operational cash buffer:

```text
sector_sleeve = 0.98 / 3 = 32.67%
N_min = ceil(32.67% / 10%) = 4
```

So a sector with fewer than **4** eligible names is **not representable** and cannot be selected.

This gate is evaluated **before** sector selection. It is not a post-selection cap that truncates a sleeve.

### 5.5 Sector selection

```text
representable_sectors = sectors with eligible_count >= N_min
rank representable_sectors by SectorScore descending
take first K=3
```

If fewer than three representable sectors exist:

```text
emit SEC001_TARGET_INFEASIBLE
construct no new target
submit no orders
preserve current book for operator review
```

V3 does not invest in two sectors, increase the cap, or substitute a different K.

### 5.6 Within-sector name selection

V3 intentionally does **not** hold every name in a selected sector.

Define a target per-name weight below the 10% hard cap:

```text
target_name_weight_ceiling = 7.5%
N_target = ceil(sector_sleeve / 7.5%) = 5
```

For each selected sector:

- if eligible breadth is 4, hold all 4 names (~8.17% each with 2% cash buffer);
- if breadth is ≥5, rank names by the same individual 12-1 momentum and hold the top **5**;
- tie-break by permanent identity, then ticker.

This yields a compact **12–15 name** book while preserving equal sector sleeves.

### 5.7 Target weights

For selected sector `s` with `n_s` selected names:

```text
sector_weight = (1 - cash_buffer_pct) / 3
name_weight_i = sector_weight / n_s
```

Requirements:

- `name_weight_i <= 10%` for every name;
- sector weights equal within a small rounding tolerance;
- no hidden reweighting across sectors;
- no substitute names beyond the selected top 4–5;
- fractional shares may be used if the broker supports them; OrderRouter remains authoritative for whole-share flooring.

### 5.8 Rebalance semantics

Weekly rebalance only. At each governed slot:

1. resolve PIT universe and identity;
2. compute 252/21 momentum;
3. compute sector scores;
4. apply representability gate;
5. select three sectors;
6. select 4–5 names per sector;
7. validate broker asset + price eligibility;
8. prove final target remains representable after execution exclusions;
9. sell exits first;
10. buy toward target;
11. reconcile target vs broker state.

If execution exclusions make any sector sleeve unrepresentable, do **not** silently reweight a smaller set. Emit `SEC001_EXECUTION_TARGET_INFEASIBLE` and hold/abort the new rebalance.

**Mid-execution break *(added v0.2)*:** the step-8 precheck catches infeasibility before orders, but a broker rejection **during** the buy leg can break a sleeve after sells have already executed. That state ends the rebalance as a **recorded incomplete** (`SEC001_EXECUTION_TARGET_INFEASIBLE`, partial-book evidence preserved, operator review required) — never an auto-retry, never a substitute name, never a silent reweight of the surviving fills. The no-substitution rule applies mid-flight exactly as it applies at planning time.

---

## 6. Profitability-focused risk and execution controls

### 6.1 Controls that support profitability without adding alpha factors

| Control | Purpose |
|---|---|
| 10% per-name cap | Prevent single-name domination |
| 3 equal sector sleeves | Preserve the diversification premise |
| 4-name hard breadth floor | Guarantee target feasibility |
| 5-name target basket | Reduce sector-signal dilution while retaining diversification |
| PIT universe | Prevent stale static-universe construction drift |
| Permanent identity | Prevent ticker-change/reuse ownership errors |
| Weekly cadence | Keep turnover bounded and consistent with the signal horizon |
| Price/broker eligibility before target commit | Avoid dead legs and unintended cash drag |
| Full target representability check | Avoid partial books that violate the thesis |

### 6.2 No hidden overlays

V3 baseline contains **no** SPY 200-day regime filter, vol target, news filter, MDQ score, rank hysteresis, or post-hoc optimizer unless that behavior is explicitly represented in the V3 Factor Lab candidate and re-approved.

This clause is deliberately strict because the V2 incident was caused by implementation inheritance from another strategy.

---

## 7. Shared platform infrastructure from Dynamic PIT — allowed reuse

SEC-001 V3 should reuse neutral platform safety components where they exist. It should **not** reuse LOW-001's economic logic.

### 7.1 Reuse

- `PERMATICKER_EFFECTIVE_INTERVAL_V1` security identity;
- PIT universe snapshot/evidence model;
- dynamic symbol resolution and broker eligibility once generalized at platform level;
- strategy-owned holding provenance;
- broker position as current quantity authority;
- `StrategyPositionLiquidator` mechanics;
- explicit strategy-control `stop/deactivate(liquidate=True)` path;
- ownership/identity diagnostics;
- startup readiness checks for required providers.

### 7.2 Do not reuse

- LOW-001 realized-volatility ranking;
- LOW-001 lowest-quintile rule;
- LOW-001 executable-set 70% threshold;
- LOW-001 target builder;
- LOW-001 rebalance timing;
- any LOW-001 profitability conclusion.

### 7.3 V3-specific safety invariant

> **No SEC-001 V3 runtime may acquire a position unless the same strategy can later discover, price, reconcile, and liquidate that position after it leaves the current PIT universe or selected sector basket.**

---

## 8. Ownership, liquidation, and account isolation

### 8.1 Ownership

Use the same platform principle:

```text
order/acquisition provenance -> which strategy may claim the security
broker/current position      -> how much exists now
```

Never reconstruct strategy quantity from historical fills.

### 8.2 Account 5

V3 should begin on a **clean standalone PAPER account**. Account 5 may be reused after the V2 flatten and evidence closeout because a dedicated account gives clean attribution and simpler operational controls.

A new strategy record is required. Do not reactivate strategy ID 7 and do not append V3 paper results to the V2 track record.

### 8.3 Liquidation

V3 should opt into the platform's explicit PAPER liquidation capability only after a dedicated policy entry is reviewed. Authorization must remain default-deny; LOW-001's allowlist does not automatically authorize SEC-001.

---

## 9. Minimal research/validation program

V3 uses research only to answer deployability and profitability. It is not an open-ended discovery program.

### 9.1 One candidate only

Primary candidate:

```text
SEC-001 V3-RC
Universe: PIT top 200
Signal: 252/21 momentum
Sector score: mean constituent momentum
Representability: N_min from K=3 and 10% cap
Sector selection: top 3 representable sectors
Name selection: top 5 momentum names per sector, or all 4 if breadth=4
Weighting: equal sectors, equal names within sector
Cadence: weekly
Long-only, no leverage
```

No K={2,4} band, no lookback grid, no regime-filter variants, no optimizer.

### 9.2 Research implementation path

New work must use the Factor Lab path (`ProgramSpec` + `runner.run_program`), not extend the deprecated bespoke V2 script.

Recommended new artifacts:

- `app/research/factor_lab/configs.py` — `SEC_001_V3` program spec;
- a pure V3 selector/construction module reusable by research tests;
- `docs/design/SEC-001/` governing design and activation records;
- deterministic evidence package under `docs/implementation/evidence/sec_001_v3/`.

### 9.3 Comparison set

Only three comparisons are needed:

1. **V3 candidate** — decision book;
2. **SEC-001 V2 pure baskets** — historical structural reference, not inheritable evidence;
3. **equal-weight PIT universe** — broad market/control reference.

MOM-001 correlation may be reported as a secondary diversification diagnostic but is not a V3 promotion gate.

### 9.4 Validation-run freeze *(v0.3 — values frozen; cost convention corrected)*

Three inputs to the §10 gates freeze with the gates. At v0.3, two are frozen with values; the third (sector classification, §5.1a) awaits the owner's disposition ruling (the investigation itself is complete — §5.1b):

1. **Evaluation period — FROZEN:** 2000-01-01 → 2026-06-12.
2. **Walk-forward windows — FROZEN**, reproducing the existing SEC-001 V2 window-construction helper rather than inventing new periods (shared endpoint dates are intentional consequences of that helper; each window is evaluated independently):
   `[2000-01-01, 2005-04-15]` · `[2005-04-15, 2010-07-29]` · `[2010-07-29, 2015-11-11]` · `[2015-11-11, 2021-02-23]` · `[2021-02-23, 2026-06-12]`.
3. **Cost model — FROZEN, convention corrected:** v0.2's "base per-side cost in bps" did not match the research machinery. The canonical Factor Lab `_simulate` convention computes one-way portfolio turnover as `0.5 × Σ|w_new − w_old|` and charges `turnover_cost_bps × turnover`. The frozen model is: **`turnover_cost_bps` = bps charged per 100% one-way portfolio turnover under exactly that convention; base 10 bps, stress 25 bps**, applied identically to V3, the V2 reference, and the equal-weight control. Ten bps is the historical SEC-001 V2 harness default, so the V2 comparison changes the strategy, not the friction model.

---

## 10. Profitability gates — recommended owner freeze

These are **prospective deployment gates**, not observed results. V3 proceeds to PAPER only if all primary gates pass on the frozen validation run.

### 10.1 Primary gates

| Metric | Proposed gate | Reason |
|---|---:|---|
| Net CAGR | **>= 8%** | Must be economically worthwhile after modeled costs |
| Net Sharpe | **>= 0.75** | Absolute gate, **frozen and unmoved**. The "V2 ~0.51" it was originally set against is now a **legacy defective-universe reference** (2026-08-24 ruling); the corrected V2 benchmark may differ. |
| Max drawdown | **>= -35%** | V2's ~-65% drawdown is not commercially attractive |
| Calmar | **>= 0.30** | Requires return relative to drawdown, not Sharpe alone |
| Walk-forward windows | **>= 4 of 5 positive net-return windows** | Avoid one-regime dependence |
| Relative to V2 | Higher Sharpe **and** shallower drawdown, both against the **corrected** V2 reference (true-traded-dollar universe, GICS-11, same final period/windows, same cost convention, V2's *intended* construction) | New construction must solve an actual V2 weakness |
| Cost stress | At 25 bps turnover cost, CAGR > 0 and Sharpe >= 0.60 | Strategy must survive a materially harsher execution assumption |
| Representability | 100% of executed rebalances satisfy K=3 / 10% cap | No economic success from infeasible books |

### 10.2 Secondary diagnostics — not optimization targets

- annual turnover and estimated cost drag;
- number of holdings (expected 12–15);
- sector turnover frequency;
- worst rolling 12-month return;
- correlation with MOM-001;
- concentration by issuer and sector;
- frequency of `SEC001_TARGET_INFEASIBLE`;
- selected-sector breadth **versus all-representable-sector breadth** *(v0.3 — without the denominator, "we often selected breadth-4" cannot distinguish common from disproportionately selected; still a diagnostic, never a gate or knob)*.

### 10.3 Stop rule

If the single V3 candidate fails the primary profitability gates, the program returns **STOP / REDESIGN**. It does not automatically branch into parameter tuning.

A new candidate requires a new explicit economic mechanism and a new V3.x/V4 design decision.

### 10.4 SEC-001 trial ledger *(added v0.2)*

The historical evaluation window is a **consumable**. §10.3 correctly requires a new economic mechanism for any successor — but whoever designs that successor will have seen this candidate's diagnostics, and each candidate evaluated against overlapping history is a trial on the same data. Therefore:

- **V3-RC is trial #1** in the SEC-001 trial ledger (the same discipline as the platform's other N-trials ledgers);
- every subsequent SEC-001 candidate evaluated on a window overlapping this one increments the ledger, whatever its version label;
- every future GO/STOP decision record **discloses the ledger count** alongside the gate results, so a third or fifth candidate passing the same thresholds is read with the multiplicity it actually carries;
- the ledger records, per trial: candidate identity, mechanism summary, window used, disposition, and what the designer had seen of prior trials' diagnostics.

The ledger does not forbid successors; it prevents the window's consumption from being forgotten.

**Pre-ledger exposure *(v0.3)*:** this evaluation history was already viewed through SEC-001 V1 and V2. V3-RC is trial #1 of the *ledger*, not a pristine first look at the data — the ledger's opening entry records that inheritance explicitly.

---

## 11. Implementation architecture

### 11.1 Do not modify the V2 runtime in place

Recommended code layout:

```text
app/research/factor_lab/
    configs.py                    -> SEC_001_V3 ProgramSpec
    ...

strategies_user/templates/
    sector_rotation.py            -> RETAIN as V2 incident artifact
    sector_rotation_v3.py         -> NEW V3 runtime

app/universe/
    pit_universe_provider.py      -> shared
    security_identity.py          -> shared
    dynamic_symbol_resolver.py    -> shared when generalized
    strategy_ownership.py         -> shared
    owned_holdings.py             -> shared

app/services/
    strategy_position_liquidator  -> shared mechanics
    strategy_control              -> explicit stop/liquidate routing
```

### 11.2 Proposed V3 strategy class

```text
class SectorRotationV3(Strategy)
    name = "sector-rotation-v3"        # recommended clean identity
    version = "2.0.0"                 # material economics/construction change
    schedule = "24 10 * * mon"        # interpreted in America/New_York
```

If product naming requires retaining `sector-rotation`, use a **new strategy row + version 2.0.0** and preserve strategy 7 as retired. Do not overload the old row.

### 11.3 Core functions

```text
_rebalance()
    -> resolve PIT universe
    -> compute 252/21 momentum
    -> build sector states
    -> _representable_sectors()
    -> _select_three_sectors()
    -> _select_names_per_sector()
    -> _build_target_weights()
    -> _execution_precheck()
    -> _apply_targets()
    -> reconcile
```

Selection and target construction should be pure/deterministic where possible so the same logic is testable in Factor Lab and runtime conformance fixtures.

---

## 12. Evidence and observability

Each rebalance should durably answer:

```text
rebalance_id
strategy_id / version
pit_as_of
universe_hash
factor_as_of
sector -> breadth
sector -> score
sector -> representable yes/no + reason
selected sectors
selected names per sector
per-name target weight
risk-cap check
broker/price eligibility
final representability result
orders / fills / rejections
reconciliation
status
```

Suggested strategy-specific events:

```text
sec001_universe_resolved
sec001_sector_unrepresentable
SEC001_TARGET_INFEASIBLE
sec001_target_built
SEC001_EXECUTION_TARGET_INFEASIBLE
sec001_rebalance_completed
sec001_reconciliation_mismatch
```

Shared ownership/liquidation diagnostics should retain their platform event names rather than creating SEC-specific duplicates.

---

## 13. Required tests

### 13.1 Economic construction tests

| Test | Required outcome |
|---|---|
| 252/21 window | Exact; any 252/0 mutation fails |
| Sector score | Mean of valid constituent 12-1 scores |
| Sector breadth = 3 | Unrepresentable |
| Sector breadth = 4 | Representable; 4 names selected |
| Sector breadth >= 5 | Top 5 names selected |
| 3 representable sectors | Exactly 3 selected |
| <3 representable sectors | `SEC001_TARGET_INFEASIBLE`; zero orders |
| Strongest sector unrepresentable | Skip it; next representable sector may rank into top 3 |
| Equal sector sleeves | Each sector receives same target weight |
| 4-name sector | No name exceeds 10% |
| 5-name sector | Approx 6.5–6.7% per name before rounding |
| Deterministic ties | Permanent ID then ticker tie-break |

### 13.2 Conformance tests

- Research selector and runtime selector produce identical target sets/weights for frozen fixtures.
- Static registration cannot silently shrink the PIT universe.
- Market regime and vol-scaling code paths are absent/disabled unless explicitly added to the governed ProgramSpec.
- Schedule resolves to Monday 10:24 America/New_York across EST and EDT.
- No other strategy's defaults change.

### 13.3 Safety tests

- Held V3 name remains discoverable/exitable after leaving PIT universe or sector target.
- Ticker rename uses permanent identity and current broker ticker.
- Ticker reuse / unresolved identity fails closed.
- Manual/competing acquisition ambiguity fails closed.
- Explicit PAPER liquidation works only when SEC-001 V3 policy is enabled.
- Circuit-breaker trip does not imply full liquidation.

### 13.4 Profitability/research tests

- Factor Lab evidence package deterministic.
- Cost model applied consistently to V3, V2, and equal-weight control.
- All five walk-forward windows reported even when one fails.
- No automatic parameter search or best-of-many selection is present.

---

## 14. PR and implementation sequence

### PR 0 — V2 closeout / account cleanup

- Finish Account-5 flatten and evidence closeout.
- Mark strategy 7 retired/nonconforming in governed docs; do not reactivate.
- No V3 code.

### PR A — V3 research candidate

- `SEC_001_V3` Factor Lab ProgramSpec.
- Pure representability + selection + weighting functions.
- Deterministic tests.
- Run the one frozen candidate and issue **GO / STOP** against §10.

### PR B — V3 runtime scaffold

Only if PR A = GO:

- new strategy identity/runtime;
- shared PIT/identity plumbing;
- no account activation;
- static-strategy regression tests.

### PR C — execution + safety

- broker eligibility and price precheck;
- representability recheck after exclusions;
- ownership/readability/liquidation;
- reconciliation and evidence;
- schedule semantic tests.

### PR D — Account-5 PAPER activation

- new strategy record;
- runtime version 2.0.0;
- clean account proof;
- configuration freeze;
- first scheduled rebalance under observation.

---

## 15. Deployment gates

| Gate | Requirement |
|---|---|
| V3-G0 | V2 strategy 7 remains retired; Account 5 flat; incident evidence sealed |
| V3-G1 | Factor Lab V3 candidate passes all §10 primary profitability gates |
| V3-G2 | Research/runtime target conformance exact on historical fixtures |
| V3-G3 | PIT universe and security identity providers READY |
| V3-G4 | Target representability proven before any order |
| V3-G5 | Static strategies unchanged; no shared-default drift |
| V3-G6 | Normal exit + explicit PAPER liquidation + ticker-lineage tests pass |
| V3-G7 | Schedule resolves to Monday 10:24 New York wall-clock |
| V3-G8 | Account 5 is clean and dedicated to the new V3 strategy record |
| V3-G9 | First paper rebalance reconciles with zero unexplained differences |

Failure of any gate blocks activation. No partial activation.

---

## 16. PAPER phase — profitability monitoring, not a second research program

The paper phase is for execution validation and live economic monitoring. It does not retune the strategy.

### 16.1 Daily/weekly dashboard

Track:

- equity / cumulative return;
- realized and annualized volatility;
- rolling Sharpe as a descriptive metric;
- drawdown;
- sector exposures;
- position weights and cap headroom;
- turnover and modeled/realized trading cost;
- order rejection rate;
- target-vs-broker reconciliation;
- representability failures;
- correlation with MOM-001 as a secondary metric.

### 16.2 Paper promotion rule

Do not require four weeks of paper P&L to statistically prove the strategy. Research profitability is decided before activation. Paper promotion instead requires:

- clean execution/reconciliation;
- no hidden strategy drift;
- no cap or sector-weight violations;
- no recurring representability failure;
- observed costs consistent with the validation assumptions;
- no operational defect that invalidates the research construction.

A live loss does not automatically invalidate the historical profitability gate, and a short live gain does not upgrade the strategy. Paper data is operational evidence first.

---

## 17. Rollback and stop behavior

If V3 has an implementation defect:

1. stop new rebalance dispatch;
2. preserve all evidence;
3. use explicit audited PAPER liquidation if required;
4. do not reactivate V2;
5. return Account 5 to flat;
6. fix/re-validate against the same frozen V3 candidate;
7. resume only after conformance is re-proven.

If V3 fails the profitability gates before activation, no rollback is needed: the program stops with no paper deployment.

---

## 18. Explicit non-goals

V3 does **not** authorize:

- repairing SEC-001 V2 in place;
- inheriting the V2 paper track record;
- K=2/K=4 failover;
- cap >10%;
- partial investment because one selected sector is infeasible;
- 252/0 momentum;
- SPY regime filter;
- vol scaling;
- news/LLM/MDQ/DISC inputs;
- short selling;
- sector ETFs as a substitute for stock baskets;
- portfolio optimizer / risk-parity layer;
- live parameter tuning;
- multi-strategy blend optimization;
- using LOW-001's 70% executable-set floor as an SEC-001 rule.

Any of those is a separately governed strategy proposal.

---

## 19. Definition of Done

SEC-001 V3 is complete only when:

- [ ] V2 is retired and Account 5 is flat with a sealed closeout record.
- [ ] V3 design/profitability gates are owner-frozen before the validation run.
- [ ] Sector-classification provenance investigation (§5.1a Q1–Q5) is complete (✅ executed 2026-08-23, findings in §5.1b) **and its disposition adjudicated (⏳ owner ruling outstanding)**; the classification fields in Appendix A are frozen from a proven source — the single-row `tickers.sector` lookup is never labeled PIT.
- [ ] Evaluation period, walk-forward window dates, and cost model are frozen (§9.4 — DONE at v0.3: 2000-01-01→2026-06-12, five V2-helper windows, 10/25 bps one-way-turnover convention).
- [ ] The SEC-001 trial ledger opens with V3-RC as trial #1; the GO/STOP record discloses the ledger count (§10.4).
- [ ] One `SEC_001_V3` Factor Lab candidate is executed with no parameter search.
- [ ] All §10 primary profitability gates pass.
- [ ] Research and runtime selection/weighting are conformance-identical.
- [ ] PIT universe and permanent identity are used end-to-end.
- [ ] Every target is representable under K=3 and the 10% cap before orders.
- [ ] No hidden MOM-001 overlays exist.
- [ ] Normal exit and explicit PAPER liquidation work for owned names outside the current target/universe.
- [ ] Account 5 uses a new strategy record/version; V2 history remains separate.
- [ ] First paper rebalance reconciles with zero unexplained differences.
- [ ] The strategy remains long-only, fully invested subject only to the frozen cash buffer, and sector-neutral across three sleeves.

---

## 20. Immediate next actions

1. **Close V2 operationally:** read-only Sunday check, then authenticated Account-5 flatten during Monday RTH; seal the flat-state evidence.
2. **Freeze V3 v0.3:** approve the proposed profitability gates and construction in this document.
3. **Create `SEC_001_V3` ProgramSpec:** implement the one-candidate research book in Factor Lab.
4. **Run GO/STOP validation:** compare only V3 vs V2 reference vs equal-weight control, including 25-bps cost stress and five walk-forward windows.
5. **If GO:** implement a new V3 runtime/strategy record, reusing generic PIT/identity/ownership/liquidation infrastructure.
6. **If STOP:** do not paper trade and do not tune inside this program; return with a new economic mechanism or close SEC-001.

---

## Appendix A — proposed frozen V3 configuration

```yaml
program: SEC-001-V3
candidate: SEC-001-V3-RC
universe:
  type: PIT_LIQUID_TOP_N_V2          # amended 2026-08-24 (universe liquidity defect ruling)
  liquidity_measure: TRUE_TRADED_DOLLAR_V1   # SEP.closeunadj * SEP.volume
  legacy_rejected: LEGACY_ADJUSTED_CLOSE_X_RAW_VOLUME  # adjusted close * raw volume - NONCONFORMING
  n: 200
sector_classification:            # v0.2 — §5.1a; values set at pre-registration freeze
  source: <OWNER_FREEZE>          # provider + field, by name
  taxonomy_version: <OWNER_FREEZE>
  pit_semantics: as_of_rebalance_session
  unclassified: exclude_with_reason
signal:
  factor: momentum
  lookback_sessions: 252
  skip_sessions: 21
sector:
  score: mean_constituent_momentum
  top_k: 3
construction:
  cash_buffer_pct: 0.02
  max_position_pct: 0.10
  hard_min_names_per_sector: 4
  target_names_per_sector: 5
  within_sector_rank: individual_252_21_momentum
  sector_weighting: equal
  within_sector_weighting: equal
validation:                       # v0.3 — §9.4 values FROZEN; sector_classification above still awaits §5.1a
  evaluation_period:
    start: 2000-01-01
    end: 2026-06-12
  walk_forward_windows:
    - [2000-01-01, 2005-04-15]
    - [2005-04-15, 2010-07-29]
    - [2010-07-29, 2015-11-11]
    - [2015-11-11, 2021-02-23]
    - [2021-02-23, 2026-06-12]
  cost_model:
    convention: one_way_portfolio_turnover   # 0.5 * sum(|w_new - w_old|), canonical _simulate
    base_bps: 10
    stress_bps: 25
execution:
  rebalance: weekly
  schedule_local: "Monday 10:24 America/New_York"
  fractional_shares: true
  no_partial_sector_fallback: true
  abort_if_post_execution_target_infeasible: true
risk:
  long_only: true
  max_gross: 1.00
  leverage: false
excluded_features:
  market_regime_filter: false
  vol_scaling: false
  news: false
  mdq: false
  optimizer: false
```

## Appendix B — profitability gate card

```text
GO to PAPER only if all are true:
  Net CAGR >= 8%
  Net Sharpe >= 0.75
  Max DD >= -35%
  Calmar >= 0.30
  >= 4/5 walk-forward windows positive
  Sharpe > V2 reference
  Drawdown shallower than V2 reference
  25-bps stress: CAGR > 0 and Sharpe >= 0.60
  100% of executed targets representable under K=3 / 10% cap

Otherwise:
  STOP / REDESIGN
  no paper deployment
  no automatic parameter tuning
```

## Appendix C — source/evidence basis

This v0.3 is grounded in:

- owner incident status dated 2026-08-22 for Account 5 / strategy 7;
- `TradingWorkbench_P12_Session4_SEC001Production_v0.1.md` (original production-promotion design);
- `apps/backend/scripts/sector_rotation_v2_research.py` (historical V2 research; now deprecated for new work);
- `apps/backend/strategies_user/templates/sector_rotation.py` (deployed V2 runtime whose 252/0 and equal-name implementation drift triggered containment);
- the platform security/ownership/liquidation architecture established during LOW-001 PR-S work.

Where the owner incident record conflicts with older production-promotion documentation, the incident ruling controls.
