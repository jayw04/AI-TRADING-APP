# RANGE-002 Data Feasibility and Research-Validation Design Report v0.1

| Field | Value |
|---|---|
| Status | **DRAFT ANALYSIS. Documentation only. Nothing in this report is a decision, a signature, an approval, a freeze or an authorization.** P0 is NO-GO and nothing in P0 is approved (Register v0.2 header, Status row and the "Recommended rulings versus formally approved decisions" table). |
| Date | 2026-10-10 |
| Base | `origin/main` at `80bdb200` (P0 Decision Register v0.2 and validator-independence requirements merged in #745; P1/P2 Implementation Backlog and Schema Change Batch Proposal merged in #746). The analysis was prepared against `a72dd119` and read the backlog and schema proposal before #746 merged; the merged versions differ from the versions read only in a few wording lines (section numbers unchanged). Cited here as "Backlog" (`RANGE-002_P1_P2_Implementation_Backlog_v0.1.md`) and "Schema Proposal" (`RANGE-002_Schema_Change_Batch_Proposal_v0.1.md`). The `apps/` tree is unchanged between `a72dd119` and `80bdb200` (checked with `git diff --stat`), so the code facts verified at `a72dd119` below hold on `80bdb200`. Register citations in this report are by section, not by line number. |
| Staging | Stage 1 of the local four-stage documentation sequence (feasibility, governance package, engineering readiness, register reconciliation); local branch `pub/1-feasibility`, not pushed. Stage 2 and later documents cite this report by path and therefore depend on it being published first. |
| Data accessed | **None.** No market data, no vendor/provider/broker/API call, no network, no credential file, no protected-period read, no backtest. Repository files only. The arithmetic in section 6 is synthetic (assumed distributions, fixed seed `20261010`); it uses no RANGE-002 or market observation. |
| Companion documents | Plan v0.5 ("Plan"), Addendum A1 ("A1", DRAFT, unsigned), Decision Sheets v0.1 ("Sheets"), Register v0.2 ("Register"), `governing_reconciliation.md`, `recon.md`, RNG-001 Rejection Summary ("RNG-001"), Governance Hardening Design v0.1 |

## 0. Reading conventions

Every statement about the strategy, a threshold or a method carries one of these labels. They are never merged.

| Label | Meaning |
|---|---|
| **IN FORCE (code)** | Enforced by merged code on `main` (spec schema, governance Level 1). Merged is not the same as approved. |
| **DESIGN v0.4** | The governing research design (Chinese DOCX, untracked, not read directly by this report; known only through Plan, A1 and the reconciliation). |
| **PROPOSED** | A recommendation in Plan, A1, Sheets or Register. Unsigned. |
| **UNSIGNED / UNSET** | A P0 decision with no value (blank signature row; spec field null). |
| **PREPARER'S ANALYSIS** | This report's own reasoning or arithmetic. Not a recommendation to the owner unless it says "Recommendation (not a decision)". |
| **UNKNOWN** | Not documented in the repository. The owner or a named party must verify with the vendor or by an authorized, return-blind measurement. |

Verdict vocabulary (section 8): FEASIBLE, FEASIBLE-WITH-CONDITIONS, BLOCKED, UNKNOWN. A verdict says whether the work can technically and statistically be done, not that it is authorized. No verdict here is a P0 approval.

---

## 1. Approved vs proposed vs unsigned: the state of the record

- **Formally approved decisions: zero.** Register header: "Formally approved decisions in this document: NONE (0)" (the "Recommended rulings versus formally approved decisions" table). The Register's "Owner provisional policy directions (Part IV)" (SoD-A plus SoD-C, limits 1/1, option B for `p5.account_binding`, return-blind feasibility amendment) are "PROVISIONAL POLICY DIRECTION -- NOT SIGNED".
- **A1 is DRAFT, not in force** (A1 status row). Until signed, design v0.4 governs, including fixed A/B exits. **The merged schema already assumes A1** (partition layout locked by equality validators; Register section 3.5 "C-SCHEMA" and section 23).
- **Owner rulings that exist** (recorded 2026-10-09, `governing_reconciliation.md` section 0, `recon.md` section 0): C5/D11 direction (new RANGE-002 SIP loader, `BarCache` untouched), C4 (dedicated intraday coverage validator), C6 (Holm, not BH-FDR), C11 (bootstrap parameters unset). These are owner rulings on direction. Each still needs its P0 value signed.
- **All 19 decisions D01-D19 are UNSIGNED**; 66 P0 fields are unset in the skeleton (Register section 4.5), rising to 86 if the Schema Proposal is accepted (Schema Proposal section 2).
- **Locked in code by equality validators, therefore not open without a code change and the v0.4 owner:** `gates.min_trades = 300`, `gates.pf_base = 1.30`, stress mean positive, `redundancy_corr_max = 0.85`, `p5.min_days = 60`, `p5.min_trades = 100`, `p5.max_cost_ratio = 1.5` (Register section 4.1).

---

# PART D1. DATA REQUIREMENTS

## 2. D1 findings

### 2.1 Point-in-time stock universe and survivorship avoidance

**Documented requirement (DESIGN v0.4 via Plan 2.1, lines 144-160):** US common stocks including later-delisted names; rebuilt monthly using only information visible on the prior trading day; top-N by 20-day average dollar volume; prior close above $10; `universe.n` proposed 100 (D03, UNSIGNED). Plan WP1.5 (Plan line 344) requires permaticker identity (not ticker strings), delisted names included, and a look-ahead test (shifting future data must not change any universe).

**What the platform has (recon.md section 2.3):**

| Asset | Path | Disposition | Limit |
|---|---|---|---|
| Survivorship-free daily store | `apps/backend/app/factor_data/store.py` (Sharadar SEP/TICKERS/ACTIONS in DuckDB) | REUSE | Daily layer only; used as the ADV/price source |
| Universe builder | `apps/backend/app/factor_data/universe.py` `universe_asof` | WRAP | Returns tickers not permatickers; not monthly; fail-closed `UniverseUnavailable` |
| Lineage resolver | `apps/backend/app/validation/security_lineage.py` | REUSE | See below |
| Identity resolver | `apps/backend/app/universe/security_identity.py` | REUSE | ticker + date to permanent id only |

**`security_lineage.py` (read in full header and signatures):**
- Identity contract `PERMATICKER_EFFECTIVE_INTERVAL_V1` (`security_lineage.py:55`): identity = vendor permanent id plus effective-date interval; ticker is an attribute.
- `resolve_lineage` (line 211) reads `tickers` for the symbol and requires an *active* lineage covering the session (`firstpricedate <= session <= lastpricedate`); it refuses on seven closed reasons (lines 73-83: `NO_ACTIVE_LINEAGE`, `MULTIPLE_ACTIVE_LINEAGES`, `MISSING_PERMANENT_ID`, `LOOKBACK_CROSSES_LINEAGE`, `METADATA_PRICE_DISAGREE`, `UNRESOLVED_REMAP_GAP`, `AMBIGUOUS_EFFECTIVE_INTERVAL`). `LINEAGE_GAP_SESSIONS = 20` (line 60).
- It queries `sep` (daily) for session lists (line 205-208). **It is a daily-layer, ticker-to-lineage resolver.** It says so itself: "SEP carries no permanent identifier -- it is keyed by ticker alone" and detection relies on TICKERS/ACTIONS (module docstring).
- Its governed constants live in the module, not in the RANGE-002 spec (Backlog 2.2 and T2 note). Owner decision O-7 / "OD-1" (lineage constants) has no spec field and no decision sheet; the Schema Proposal maps it to D03 as a sub-item.
- Stated limitation of the module itself: it "does not repair the corpus" and a store conflating two issuers stays defective (docstring). Refusals become exclusions, so *survivorship-free* is only as good as the daily corpus plus the refusal accounting (Backlog L9 requires exclusions to be counted with reason codes).

**Gaps (PREPARER'S ANALYSIS, supported by Backlog 2.2 and 7.2):**
1. The **reverse join** (permaticker + interval -> *vendor ticker used in the SIP request*) is NOT in the repo (Backlog 7.2). Without it the intraday fetch cannot be keyed to the PIT identity; a reused ticker would pull another issuer's minute bars. New `identity_map.py` is required.
2. Whether Sharadar TICKERS metadata is itself point-in-time (not retro-mapped) is UNKNOWN (Backlog 7.2).
3. Whether the SIP vendor returns minute history for delisted symbols is UNKNOWN (feasibility item F2, Sheets line 367). If it does not, the PIT universe contains names with no intraday bars; Plan WP1.8 requires explicit denominators and exclusion reasons "so 98% cannot be achieved by silently dropping unavailable symbols" (Plan line 347). The Schema Proposal adds `data.exclusion_bound` (UNSET) for this exact reason; a vendor that drops delisted names turns the universe into a survivor set in the *intraday* layer even though the daily layer is clean.
4. Survivorship bias direction (design reasoning): dropping delisted names removes losers, inflating a long-only breakout. This is a bias against honest rejection, so F2 failure must be treated as a stop (Plan 9.3), not an exclusion-bound tuning exercise.

**Verdict contribution:** FEASIBLE-WITH-CONDITIONS (daily PIT spine exists; the intraday join and delisted coverage are not demonstrated).

### 2.2 Opening-range intraday bars

**Requirement (Plan 2.1, WP1.2):** licensed SIP 1-minute regular-hours bars, `America/New_York`, 2016-2025 for the union of all monthly universes, feed asserted `sip`, monthly chunks, raw and normalized SHA-256s.

**Volume arithmetic (PREPARER'S ANALYSIS; schedule assumptions only, no vendor figure):**
- A full session has 390 regular-hours minutes. A calendar month has at most 23 sessions, so at most 23 x 390 = **8,970** one-minute rows per symbol-month; a typical month (21 sessions) has 8,190.
- That is just under the 10,000-row page cap observed in the ADR 0033 incident (RNG-001 section 5; Sheets F6). Any request spanning more than one symbol, or any extended-hours inclusion (04:00-20:00 would be 960 per session), exceeds one page. Pagination to exhaustion is therefore mandatory, not an edge case, and a response of exactly the cap must be treated as possibly truncated (Plan WP1.1; Backlog 2.1).
- Lower bound on stored rows if the union were only 100 names for 120 months: 100 x 120 x ~8,190 ≈ 9.8 x 10^7 rows (~10^8). The true union is larger because monthly top-N membership turns over. The union size is UNKNOWN until the PIT universe is built (Sheets D03 "union size estimate once built"). Order of magnitude is therefore ≥ 10^8 rows; byte size, request count, rate limit and cost are UNKNOWN (F5/F6).
- **About 40% of months (48 of 120) are the 2022-2025 holdout.** A research-principal loader must be unable to read them (Backlog 2.1 "Holdout partition split", boundary B-1 unresolved). Holdout ingest is BLOCKED on the execution-boundary design (Backlog 7.1 item 4).

**Opening-range specifics that need data semantics not yet known:**
- Bar timestamp convention (start- vs end-stamped) and vendor delivery delay for the 09:59 bar: UNKNOWN (F4; `execution.bar_timestamp_convention` and `vendor_delay_ms` UNSET under D14). Plan WP2.1 forbids signal code until this is verified. A one-bar misread shifts the OR window by one minute and leaks 10:00 data into the OR.
- `NO_TRADE_MINUTE` vs `DATA_GAP` classification needs an independent reference. The Schema Proposal proposes reconciling bar volume with Sharadar daily volume (`data.minute_reconciliation`, UNSET, D05 5a). Whether SEP daily volume reconciles with SIP minute volume is UNKNOWN (Backlog 7.2) and is itself return-blind and measurable only after an authorized pull.

### 2.3 Corporate actions and market calendars

- **Corporate actions:** Plan WP1.6 requires a single price basis for OR, stop and fills. Sharadar `open`/`close` are not spinoff-adjusted (only `closeadj` is; Plan line 345). **Vendor intraday adjustment semantics are UNKNOWN** (Backlog V9). A new `data.adjustment` field is proposed (UNSET, Schema Proposal row 1) with a closed vocabulary that deliberately omits spinoff-adjusted. Breakout triggers are price-level rules, so a split inside the lookback changes the trigger relative to a raw stop; mixing bases is a silent look-ahead/level error. Verdict: FEASIBLE-WITH-CONDITIONS (design is clear, vendor behavior unproven).
- **Calendars:** `validation/eval_calendar.py` is fail-closed XNYS but is clamped at `FORWARD_START = "2026-07-24"` (`forward_window.py:42`; `eval_calendar.py:67,78,98`), so it cannot enumerate 2016-2025 sessions. `app/market/session.py` falls back silently to curated lists (DO-NOT-USE). **A new `data/calendar.py` is required** (Backlog L1/B-01), with DST, half-day (13:00 ET close; 15:55 EOD offset is `exit.halfday_offset_min`, D05 5g UNSET), and market-closure-day fixtures. READY (synthetic only) but not yet built.

### 2.4 Missingness, halts and liquidity

- Plan 2.1 and WP1.7: a no-trade minute is not missing data; only vendor gaps count; any `DATA_GAP` minute in 09:30-09:59 makes the symbol-day ineligible (Sheets D05 5a, PROPOSED). P1 exit requires coverage >= 98% of symbol-days (design v0.4 threshold; Schema Proposal proposes `data.coverage_min` locked to 0.98).
- **Design interaction (PREPARER'S ANALYSIS):** the 98% threshold is computed over symbol-days. With a fail-closed "any gap in the 30-minute OR window voids the day" rule, the effective loss is concentrated in thinner names and in the first half hour, where the strategy lives. The report required by WP1.8 must therefore split coverage by the 09:30-10:00 window, not only the full day (Plan WP1.8 already says so). Thin stocks near the $10 floor and rank 100 are exactly where `NO_TRADE_MINUTE` is plausible, so the classification evidence matters.
- **Halts:** halt evidence source is UNKNOWN (Backlog O-16 / "OD-4"); the Backlog's own correction maps it to D05 5h not 5j. An `EXIT_UNAVAILABLE` state is required by Plan WP2.2 (halt rule is a P0 value `fill.halt_policy`, UNSET). Quote-level and halt history availability are UNKNOWN (F10).
- **Liquidity:** `risk.max_participation` and the participation model are UNSET (D05). Bar-volume-based participation is a coarse proxy; Plan WP2.2 requires the assumption to be disclosed. No documented source gives intraday spread or depth history; quote availability is UNKNOWN (F10).

### 2.5 SIP vs IEX feed suitability

- **IN FORCE (code):** the RANGE-002 spec requires `data.feed = "sip"` (Plan 2.1 key; skeleton fixes "SIP 1-minute RTH data"; Register 4.5 fixed list). Plan WP1.2: "The loader raises if the feed resolves to anything except `sip`."
- **Platform state:** `BarCache` hardcodes IEX (`bar_cache.py:428` `feed=DataFeed.IEX`; docstring at ~line 396 "IEX is the free real-time feed; bumping to SIP requires a paid Alpaca plan"). The existing exposed RNG-001 evidence is IEX 5-minute (recon.md 2.1; A1 section 6).
- **Suitability (PREPARER'S ANALYSIS, qualitative; no measurement made):** IEX bars summarize one venue's prints, so OR high/low (and any volume-based reconciliation) differ from a consolidated tape. A breakout trigger one tick above the OR high is acutely sensitive to which prints define the high. IEX results therefore cannot validate a rule specified on consolidated SIP bars. The size of the difference is UNKNOWN and must not be estimated from RANGE-002 data before authorization. The IEX archive is usable only for non-return plumbing replay (`REPLAY_RNG001`, never citable as RANGE-002 evidence; Plan WP0.4).
- **Entitlement (documented):** the platform's own SIP-CACHE-001 contract records one paid Algo Trader Plus subscription consumed as a shared Workbench data enabler, and a 403 body "subscription does not permit querying recent SIP data" for credentials without it (SIP-CACHE-001 contract v1.0.1, lines 84, 134, 162-168). That document concerns *recent/live* SIP quotes. **It does not document historical SIP minute-bar depth to 2016-01-01, delisted-symbol coverage, or rights to store bulk history.** Those are UNKNOWN (F1, F2, F5).
- `check_marketdata_feed_pinning.sh` enforces an explicit `feed=` but not sip-vs-iex and cannot stop a SIP-labelled file being written from an IEX call (recon.md 2.7). A runtime feed assertion in the new loader is required (Plan WP1.2; Backlog L-FEED-1).

### 2.6 Slippage and transaction costs

- **Fixed by design v0.4 and locked by the schema:** base 5 bps/side, stress 15 bps/side. `costs.accounting_mode` (all-in vs additive) is D15, UNSIGNED; PROPOSED all-in debit (Register D15 row). `costs.components`, `fill.slippage_model` are `OpenValue` fields with undefined shape (Schema Proposal 4.2).
- **Evidence status (PREPARER'S ANALYSIS):** nothing in the repository measures realized spread/slippage for this strategy class. RNG-001 used an optimistic fill model with no slippage at 5 bps per side (RNG-001 lines 136, 169). Calibrating a cost model needs quote or paper-fill data. Quote-level history availability is UNKNOWN (F10). The 15 bps stress is a design stress, not a measured one.
- **Why costs matter at the order of magnitude of the signal:** a 5 bps/side round trip is 10 bps of notional. If R_pre (entry minus OR low) is, say, 100 bps of price for a typical OR (illustrative, not measured), 10 bps is 0.10 R per trade. That is the same size as the effects the validation needs to detect (section 6). Narrow ORs make cost-in-R much larger. This makes `signal.min_or_width_ticks` (D05 5b, UNSET) a first-order economic parameter, not a hygiene filter; Plan 2.5 and 2.6 forbid choosing it after results.
- **Double-counting risk:** if 5/15 bps is all-in and a fill model also adds slippage, costs are counted twice and a real edge is hidden; if it is additive and the owner assumes all-in, they are under-counted. Plan WP2.2 requires an auditable cost bridge. D15 must be signed before any engine cost code is finalized.

### 2.7 Data lineage and reproducible snapshots

- **Documented requirement:** `data_manifest.json` with vendor, feed, adjustment rule, date range, row counts, per-file SHA-256 (Plan WP1.2); controlled S3 with Version ID and SHA-256 manifest for bulk evidence (CLAUDE.md, GITHUB-OPS-001; Plan C10).
- **Gap (verified by Backlog 2.3 item 4):** `manifests/s3/` does not exist and no S3 manifest tooling exists for this program; loader requirement L-MAN-5 (S3 publication) is untestable today. Backlog B-27: BLOCKED (tooling absent). Run-local manifests (Backlog L6) are feasible; governed publication is not.
- **Reproducibility design needs (PREPARER'S ANALYSIS):** (a) vendor restatement of a historical chunk must keep both snapshots and a `RESTATEMENT` event (Backlog L5); (b) the chunk journal must be append-only and hash-chained (reuse concept from `governance/hashchain.py`); (c) the universe snapshot hash, calendar version, library versions (`alpaca-py>=0.30,<1.0` is a wide range; pagination behavior was read only from local 0.44.0, Backlog 2.1) and the vendor's response metadata need to be bound into the manifest; (d) the spec records `data.fetch_mode` (D11, UNSET string).
- **Research host:** the approved isolated non-production environment is unnamed (C12, BLANK). Register C12: not `ec2-paper`, laptop is warm standby, Norton blocks the vendor endpoint. Until named, no real pull can occur. This is documented fact, not an assessment.

### 2.8 Licensing and permitted use (only what the repository documents)

| Item | Repository evidence | Status |
|---|---|---|
| Alpaca SIP: entitlement to *recent* SIP | SIP-CACHE-001 v1.0.1 §0 (one paid Algo Trader Plus subscription, shared data enabler); 403 text for non-entitled credentials | Documented for recent data only |
| Alpaca SIP: historical minute bars from 2016-01-01 | Not documented anywhere | **UNKNOWN. Owner must verify with the vendor (F1)** |
| Alpaca SIP: delisted-symbol minute history | Not documented | **UNKNOWN (F2)** |
| Alpaca SIP: bulk *storage* and research reuse of history | Not documented; Sheets F5 assigns to Owner | **UNKNOWN. Owner must verify the licence text (F5)** |
| Alpaca rate limits, page cap, truncation behavior beyond the 10,000-row incident | Page cap 10,000 observed in the ADR 0033 incident only | **UNKNOWN (F6)** |
| Cost / data budget | `data.budget` has no spec field; O-1 "budget cap" has no field (Schema Proposal 2) | UNSET (D03) |
| Sharadar / FMP | ADR 0018 item 6: "licensed for the operator's own use. The platform may compute and surface derived factors/signals, but must not redistribute raw vendor datasets" | Platform's own posture, **not vendor text. Owner to verify with the vendor** that holding 10 years of derived universe tables on a research host (C12) is within the licence |
| New vendor | CLAUDE.md: a new external dependency requires an ADR; D03 (b) says the same | Only if Alpaca fails F1/F2/F5 |
| Anthropic / agent exposure of vendor data | Not addressed | **UNKNOWN** whether licence terms restrict sending vendor data through an LLM session (AI sessions are part of the exposure audit D01) |

**Verdict contribution:** UNKNOWN. This is the longest external lead item (Sheets section 3 critical path).

---

# PART D2. CURRENT PLATFORM CAPABILITY REVIEW

## 3. D2 findings

### 3.1 The hardcoded IEX bar cache and the loader decision

Facts verified in `apps/backend/app/market_data/bar_cache.py` at `a72dd119`:

| Property | Evidence | Consequence |
|---|---|---|
| Feed hardcoded to IEX | line 428 `feed=DataFeed.IEX`; function `_alpaca_fetch_bars` at line 388 | Cannot return SIP. Nothing selects a feed |
| Page limit hardcoded | line 429 `limit=10000` | The SDK stops paging when `limit` is reached, so a cold multi-year request silently truncates (ADR 0033 incident) |
| Cache key excludes feed | `_bucket_file` line 197-198: `root/symbol/timeframe/bucket.parquet` | An IEX file is indistinguishable from SIP; a SIP-labelled path could hold IEX bytes |
| One call over the whole missing range | `_fetch_and_write` lines 272-285: `overall_start = min(...)`, `overall_end = max(...)`, a single fetch | No chunking (ADR 0033 point 3 unimplemented) |
| `.empty` markers for any bucket without rows | lines 297-315 (zero-byte `.empty` for every un-returned bucket) | A truncated response poisons un-returned days permanently (ADR 0033 point 1 unimplemented) |
| No exactly-page-limit check | result accepted without length test | ADR 0033 point 2 unimplemented |
| Shared with production | `BarCache` is also used by the live box (recon.md 2.7) | Modification is a production-code change needing its own review (ADR 0033) |

**Decision status:** the *direction* is an owner ruling: build a new RANGE-002 SIP loader and do not modify `BarCache` (recon.md §0 item 2; Addendum A1 §7; governing_reconciliation C5). The *P0 value* `data.fetch_mode` is UNSET (D11, UNSIGNED); no source defines its enumeration (Register D11 row). The Schema Proposal 4.3 proposes `monthly_chunked_sip` only; the field stays `string or null` in the proposal.

### 3.2 Required loader changes (new code, nothing in `BarCache` changes)

| # | Requirement | Source | Existing reuse | New |
|---|---|---|---|---|
| L-1 | Constant `FEED = "sip"` passed on every request; loader constructor takes no feed parameter; wrong-feed label raises, writes nothing | Plan WP1.2; Backlog 2.1 | `app/market_data/sip/*` feed-identity checks as reference | `data/sip_loader.py` |
| L-2 | Monthly chunking per symbol batch; planner proves `symbols x sessions x 390 <= page_cap x margin` or splits | Plan WP1.1; Backlog L3 | `research/capture/collector.py::fetch_session_bars` as request-shape reference (single session, 04:00-16:00, no pagination handling) | `data/fetch_plan.py` |
| L-3 | **No `limit` argument**; consume `next_page_token` to exhaustion; treat a page equal to the cap as suspect | Plan WP1.1; Backlog 2.1 | none | `data/sip_loader.py`, `data/integrity.py` |
| L-4 | **No `.empty` markers**; absence is a classified record (`NO_TRADE_MINUTE`, `DATA_GAP`, `HALT`, `OUT_OF_LIFETIME`, `NOT_FETCHED`) | ADR 0033 point 1; Backlog 2.1 | none | `data/minute_classes.py` |
| L-5 | Injected client; loader never reads credentials/env (keeps `check_no_env_credentials.sh` and plan R7 true) | Backlog 2.1 | | `data/` |
| L-6 | Append-only chunk journal, atomic writes, idempotent resume, finite retry budget, spend/request cap | Backlog L5 | `governance/hashchain.py` concept | `data/chunk_journal.py` |
| L-7 | Run-local SHA-256 manifest and verifier; denylist of return-like column names | Plan WP1.2/1.8; Backlog L6 | `spec/hashing.py::canonical_json, file_sha256` | `data/manifest.py` |
| L-8 | Dedicated intraday coverage validator, denominators from the PIT population, output schema denylist (no return/pnl/win/hit/profit), below-threshold gives `STOP_ESCALATE` | Plan WP1.8; ruling C4 | `dataset_health` is daily only | `data/coverage.py` |
| L-9 | PIT universe monthly rebuild with permaticker, exclusion reason codes; reverse join permaticker-to-vendor-ticker | Plan WP1.5; Backlog L9 | `factor_data/*`, `security_lineage.py` | `data/identity_map.py`, `data/pit_universe.py` |
| L-10 | Calendar 2016-2025 with DST/half-days, fail-closed if library missing | Plan WP1.4; Backlog L1 | pattern only from `eval_calendar.py` | `data/calendar.py` |
| L-11 | Price-basis tag on every table; refuse mixed raw/adjusted joins | Plan WP1.6; Backlog L10 | `factor_data/total_return.py` (WRAP) | `data/corp_actions.py` |
| L-12 | Partition-aware modes; research principal cannot read or ingest the 2022-2025 window | Backlog 2.1, L11 | | `data/sip_loader.py` mode; OS/process fence, not a guard control (Backlog 9.1 item 4) |
| L-13 | Gated read side: only `read_bars(handle, request, *, capability)` returns bars, bound to the capability's date range | Backlog 9.3 | `@requires_capability` | `data/bar_store.py` |

**CI/lint facts relevant to the loader:** `check_research_plane_isolation.py` already forbids `app/research/**` from importing `app.orders`, `app.risk`, `app.brokers` or the Alpaca trading SDK (recon.md 2.9), so the loader must receive an injected client rather than import trading code; the capability lint covers all of `range002/` outside `governance/` but does not see network calls (Backlog 9.1 item 3). Whether `data/` acquisition code is `REVIEWED_PURE_IO` or a new governance phase is open owner question Q-B1.

### 3.3 Missing infrastructure (all NOT-FOUND at `a72dd119` unless stated)

| Item | Evidence | Disposition |
|---|---|---|
| Any `range002/engine/`, `stats/`, `controls/`, `data/` code | `find app/research/range002`: only `governance/` and `spec/` exist | All to be built (Backlog sections 3, 16) |
| Day-clustered stationary bootstrap | recon.md 2.6 | New; closest references `factor_data/evidence.py::block_bootstrap_ci` (circular block, daily returns, Sharpe oriented) and `services/market_projection/validate.py` (`BLOCK_LEN=10`, geometric blocks; not importable from `app.services` by the isolation lint) |
| Holm function | recon.md 2.6 | New, small pure function |
| `select_exit`, `max_stat_bootstrap` | Plan WP3 `selection.py` | New; no reuse |
| Exit engine E1-E4 incl. trailing/scale-out on 1-minute bars | Plan WP2.2A | New |
| Portfolio scheduler with merged chronological event stream | Plan 3.3, WP2.8 | New |
| ADR 0037 non-equivalence check | recon.md 2.8 | Cannot exist until C2 specification is approved |
| S3 manifest tooling / `manifests/s3/` | Backlog 2.3 | Absent |
| Named research host (C12) | Register C12 | BLANK |
| Execution boundary B-1 for holdout ingest | Backlog 7.1 item 4 | Design unsigned |
| Registry genesis enrollment | Register section 2, 21 | PENDING; no operator, host or path |
| Enrollment CLI | Register 0.1 | Absent; Python API only |
| `permaticker -> vendor ticker` join | Backlog 7.2 | Absent |

### 3.4 Blockers per implementation item (decision IDs)

"T" = merged tooling mechanically refuses without it; "G" = governance requires it but no tool checks (Register convention). Status: **READY (synthetic only)** work can be built on synthetic fixtures but its *merge* is gated by Q-B2 (separate authorization to implement) and, for some, Q-B1/Q-B4/Q-B5 (Backlog 12.1, 19).

| Implementation item | Real-value / real-input blockers (P0 decisions) | Other blockers |
|---|---|---|
| Spec freeze (FRZ) | A1 (G+T indirect), D01, D02, D03, D04, D05, D06, D07, D08, D09, D10, D11, D12, D13, D14, D15, D16, D17, D18, D19 (66 fields; Register 4.5) plus the D08 distinct-human obligation R1-L1b | Schema batch (Q-B4) must land **before** any real freeze, else a re-freeze (Schema Proposal section 1); genesis (M-gen, M-loc, M-ops) |
| Genesis enrollment | M-loc (host/path), M-ops (operator + witness), approved manifest triple, limits (M-lim-p3a/p3b) | C-DR conflict decided first (Register 3.5) |
| WP1.3 vendor coverage check | D03 (N, vendor, licence, budget), F1, F2, F5, F6, C12 | Stop condition 9.3 |
| WP1.1 ADR 0033 finding / SIP loader (PR 5) | D11 (`data.fetch_mode`), D03, C12 | Q-B1 (adapter route), Q-B2 |
| WP1.2 real pull | P0 gate complete (FRZ), D03, D11, C12, B-24 vendor feasibility | Owner authorization per step |
| WP1.4 calendar | none for the code (synthetic) | `exit.halfday_offset_min` (D05 5g) for the half-day rule value |
| WP1.5 PIT universe | `universe.n` (D03); lineage constants O-7 (no field) | `permaticker -> vendor ticker` join |
| WP1.6 corporate actions | `data.adjustment` (proposed new field, D03/D05); V9 vendor semantics | |
| WP1.7/1.8 classification and coverage | `data.minute_reconciliation` (D05 5a), `data.coverage_min` (D03), `data.exclusion_bound` (D03) all proposed, UNSET; halt evidence (O-16, D05 5h) | |
| WP2.1/2.1A OR signal, arming | D05 5a, 5b; D14 (bar convention, delay, latencies, crossed-before-arm) | F3, F4 |
| WP2.2/2.2A fill and exit mechanics | D05 5c-5i, D14, D15, D19 (parameter vocabulary, within-family tie-break escalation E-1/E-2) | F3 |
| WP2.3 risk sizing | D05 5j, `risk.initial_equity`, `risk.equity_basis`, `risk.over_budget_rule` (proposed); O-17 units (no field) | |
| WP2.5 controls | D06 (random-entry reps/seed/invalid-draw policy), D13 (naive ORB), O-10/O-11/O-12 (stage-1 criteria, time-shuffle, no-information definitions: BLOCKED, definitions + validator review) | |
| WP2.8 scheduler | D14 tie-break and reservation shapes (`OpenValue`, undefined) | |
| WP3 bootstrap / multiplicity / selection | D06 (method, block_len, reps, ci_type, level, seed), D02 (family), D17/D19 (eligibility, delta, stop test level) | Validator review (O-8) |
| Gates G6, G7, G8, win rate | D04, D12, D10 (shapes undefined) | |
| G10 redundancy | OD-3 comparison set (unowned; Backlog Part IV item 4) | availability of approved strategies' daily series UNKNOWN |
| P3a run | A1 signed, D17, D18, D19, D06, D02, genesis, limits, WP4.0 sealed pipeline, P1 data | One attempt only (limit 1, proposed) |
| P3b run | all of the above plus successful P3a `EXIT_SELECTED` | Terminal if technical failure (C-DR) |
| P4 | D01 exposure audit signed (G0), D10, D12, holdout token, execution boundary B-1 | |
| Non-equivalence check (WP0.5) | C2 spec approval, D09, C2-overlap number, C2-reviewers, D09-hist | Cannot be met by a tool today |
| Governed evidence publication | S3 manifest tooling (absent) | |

**Sequencing note (PREPARER'S ANALYSIS):** the P0 exit gate requires the signed non-equivalence check, which needs signal history, while the licensed SIP history arrives only in P1 after the gate (Plan WP0.5; A1 section 6). The documents themselves flag this as unresolved (D09-hist options a/b/c). No data-feasibility conclusion here resolves it; any choice other than option (a) (exposed IEX archive, timestamps and direction only) needs an A1 amendment or an early return-blind SIP pull, which itself needs C12, D03 licence, F1 and F5 first.

---

# PART D3. RESEARCH-METHODOLOGY DESIGN EVALUATION

## 4. Design recap (labels per section 0)

| Element | Where | Label |
|---|---|---|
| P3a: all K candidates on 2016-2019, deterministic selection, selection-aware test, STOP | A1 §3; Plan WP4.1 | PROPOSED (A1 unsigned); schema partitions IN FORCE (code) |
| P3b: selected exit only, 2020-2021, D17 criteria | A1 §3; Plan WP4.1 | PROPOSED; D17 values UNSET (recommended 300/150, PF > 1.0) |
| P4: selected exit once, 2022-2025, gates G0-G10 | Plan 5.1 | Thresholds IN FORCE (G1 300, G2 1.30); rest UNSET |
| Exit set: <= 8 from four families; proposed K = 7 | A1 §2; Plan 2.2 | PROPOSED; cap of 8 IN FORCE (code, `MAX_EXIT_CANDIDATES`) |
| Selection: highest one-sided day-clustered bootstrap lower bound of mean net R; tie tolerance delta | Plan 2.2 | PROPOSED; delta placeholder 0.05 R is "illustrative only" (Register D19 row) |
| Holm; family size | A1 D02; Register 4.2 | PROPOSED option (a) {G4, G5}; UNSET |
| Bootstrap: stationary, day-clustered, >= 10,000 reps, one-sided 0.05 | Register D06 row | PROPOSED; UNSET by design (ruling C11) |
| Controls: random-entry, naive ORB, time-shuffle, no-information, SPY | Plan WP2.5 | Random-entry shape PROPOSED; time-shuffle and no-information definitions UNSET (O-11, O-12) |
| Attempts: P3a 1, P3b 1 | Register section 3 and Part IV P-2 | PROVISIONAL, NOT SIGNED; semantics IN FORCE (code): attempt consumed at `capability_issued` |

## 5. Structural assessment

### 5.1 P3a / P3b separation

**Strengths (PREPARER'S ANALYSIS):**
- Splitting selection from confirmation answers the RNG-001 lesson directly (PF 1.53 full sample vs 0.68 first half, RNG-001 §3.5). The selected exit is chosen on data that does not confirm it.
- The selection record is hashed and appended before unsealing (Plan WP4.1 step 3), so no human can pick after seeing candidate results. This is the correct place for the pre-registration.
- Counting the K-fold search in a selection-aware max-statistic test, rather than K attempts, is consistent with limit 1 (Register 3.3).

**Weaknesses and risks:**
1. **P3b is small and regime-specific.** 2020-2021 is ~505 sessions. At the recommended 150-trade minimum (D17) the MDE for a one-sided 5% test at 80% power is ~0.29 R under the section 6 ILLUSTRATIVE synthetic assumptions (SD 1.3 R, design effect 1.2; unvalidated). Whether that exceeds the true effect is UNKNOWN. Under those assumptions P3b has limited power as a confirmation, and a pass rate for a genuinely positive strategy would be correspondingly modest (section 6.5, illustrative). Because of limit 1, a P3b miss is terminal for the lineage (Register C-P3B-N).
2. **Regime mismatch between P3a and P3b.** P3a (2016-2019) and P3b (2020-2021) are different volatility regimes (the latter contains the March 2020 crash and the 2021 retail-participation period). An exit selected on 2016-2019 (e.g. a tight trail) may fail 2020-2021 for regime reasons unrelated to the null. A P3b failure then conflates "no edge" with "regime-specific edge", and the terminal STOP discards the candidate. This does not invalidate the design; it should be disclosed in the thesis and read with D12.
3. **P3a eligibility is "every candidate must reach the minimum trade count"** (D17 300), while trade counts differ by exit under D18's portfolio-constrained basis (holding time changes capital occupancy; Register C-N). If the minimum is not attainable by any candidate the lineage ends at P3a. The attainable count cannot be known return-blind because trigger frequency depends on future highs (Plan 2.4 item 5; Register 3.5). **Sample-size feasibility is UNKNOWN.**
4. **Both phases consume irreversible budget at authorization**, not at completion (Register 3.2). Any engine defect discovered after authorization is terminal; the Plan still describes defect-only reruns (C-DR conflict, Register 3.5 and section 20), and the owner's provisional direction is to correct the Plan, not the limit.
5. **Information leakage across stages is bounded by calendar, not by independence of ideas.** 2022-2025 holdout independence depends on the D01 exposure audit (including AI-session history and other programs' use of the daily layer). Data feasibility cannot assess that; it is a G0 blocker.

### 5.2 Bootstrap calculations

**Estimand ambiguity (PREPARER'S ANALYSIS; must be fixed in D06):** the Plan says "mean net R per trade" with "all trades on one day form one cluster". Two reasonable estimators differ: ratio-of-sums (sum of R over resampled days divided by trade count over resampled days; weights busy days more) and mean of per-day means (weights days equally). They have different variance and different bias when trade counts vary by day and correlate with outcome. The spec key set (`stats.bootstrap.method`, `block_len`, ...) does not name the estimand. Recommendation (not a decision): the D06 sheet should name the estimator, because a validator cannot calibrate size/power without it.

**Block length:** `block_len` must be fixed a priori and not estimated from RANGE-002 data (Register 4.3 table). The only precedent in the repo is `BLOCK_LEN = 10` on daily series. Day-aggregated R of an intraday strategy is likely weakly autocorrelated, so the choice is probably second-order, but this is an assumption and is what the validator's size calibration should check. A stationary bootstrap with geometric blocks has random block boundaries; the seed and RNG implementation (numpy stream vs stdlib) need to be frozen for reproducibility (Backlog Q-B6).

**Recentered-null percentile p-value** (the repo reference logic): `p = share of recentered resampled means >= observed`. Synthetic check (section 6.4): with a skewed zero-mean R distribution (60% at -1R, 40% at +1.5R) and Poisson trades per day, the one-sided nominal-5% test rejected 4.6%, 5.1% and 5.6% of null datasets at ~150, ~300 and ~600 expected trades (1,500 replications each, Monte Carlo SE about 0.6 percentage points). So size is acceptable at the planned sample sizes *for this synthetic shape*; heavier tails (a few +5R runners from trailing exits) and strong day-level dependence can degrade it, which only a validator calibration with the chosen estimator can bound. **No claim is made about real RANGE-002 returns.**

**Selection-aware max-statistic** (`max_stat_bootstrap`): resamples days jointly for all K candidates and takes the maximum studentized mean. Because all candidates share the identical entry stream (Plan WP2.2A), their statistics are highly correlated, so the effective number of independent tests is much smaller than K = 7. Synthetic critical values for the max of 7 equicorrelated standard normals (one-sided 95%): 2.40 (rho 0.3), 2.30 (0.6), 2.16 (0.8), 2.02 (0.9), 1.92 (0.95), versus 1.645 for a single test. The cost of selection among highly correlated candidates is therefore modest (~0.3-0.5 SE) relative to testing one prespecified exit; but note the test needs the *studentization* to be stable for small trade counts or high-variance exits (trailing, scale-out). The null hypothesis tested, "no candidate has positive mean net R" (Plan WP3 `selection.py`), is an intersection null and its rejection says only that at least one candidate is positive, not that the chosen one is.

### 5.3 Multiple-testing adjustment (Holm)

- Holm is the owner-ruled method for RANGE-002 (C6). It is valid under arbitrary dependence, hence conservative for the strongly correlated G4/G5 pair.
- With {G4, G5} both *required* (design §5.3/§6), the conjunction is what the owner cares about. Holm over m = 2 requires min(p) <= 0.025 and max(p) <= 0.05. Synthetic comparison of pass probability for both tests (section 6.3): Holm gave 0.08 / 0.19 / 0.36 / 0.57 vs separate-at-0.05 gave 0.09 / 0.21 / 0.38 / 0.58 for true mean net R of 0.05 / 0.10 / 0.15 / 0.20 at 300 trades. **The practical cost of Holm over the "G4 separate at 0.05, G5 at 0.05" intersection-union reading is about 1-2 percentage points of power**, consistent with the Register's remark that option (a) "costs little because both gates are required anyway" (Register D02 row). The decisive power constraint is not the correction but the sample size and the G5 variance (below).
- **The G5 test is the binding statistical constraint, not G4 (PREPARER'S ANALYSIS).** The paired difference vs random-entry has variance of roughly the sum of the two series' variances. Under independence the standard error is about sqrt(2) times G4's. Therefore G5 needs a larger true effect than G4 at the same n. The synthetic table already folds this in (se5 = sqrt(2) * se4); real pairing at the day level (Plan WP3.3) and a common-cause covariance (both series share market days) reduce the variance below sqrt(2) and could recover power. That reduction is a validator calibration item, not an assumption to bank.
- A mixed procedure (option b: G4 alone is the Holm family, G5 a separate gate) is not directly representable by the closed `stats.adjustment` set (`holm` / `fixed_sequence`) and needs the validator's confirmation of the representation (Register 4.2 representation note).
- The D02 family count is **not** the exit-configuration count (m = 1 in A1 text counts exit configurations). The owner value is UNSET.

### 5.4 Random-entry control and no-information baseline

**Random-entry (G5 comparator):**
- Defined causally at 10:00, randomized over predeclared feasible entry instants with R_pre > 0 under the same OR-low stop, portfolio constraints, costs and activation (Plan WP2.5). Invalid draws counted, denominator preserved (`NOT_EXECUTABLE`).
- **Design strength:** it is a baseline with the same stop geometry, so it neutralizes market drift, risk budgeting and cost drag. **Design risk (PREPARER'S ANALYSIS):** if random entries are drawn uniformly across the entry window and the strategy's trigger is conditioned on a price breakout, the two populations differ in *time-of-day* and *volatility conditioning* as well as in the signal. The G5 difference then mixes "breakout signal" with "different timing". The matching dimensions proposed (symbols, window, trade_count, capital, risk_budget; Schema Proposal row 9) do not include *time of day* or *volatility regime*. This is a D06 definition decision for the validator; it is not resolvable by data feasibility.
- Monte Carlo error: with R baseline repetitions per day, the baseline mean has MC variance that falls as 1/R; the paired bootstrap should resample days while holding or re-averaging the baseline draws per day (WP3.3 estimand). `controls.random_entry.repetitions`, `seed` and `invalid_draw_policy` are UNSET.
- The baseline mean net R is expected to be negative or near zero after costs (a stop at OR low plus EOD flat with costs); the synthetic arithmetic used -0.03 R for illustration only. This is an assumption.

**No-information trigger (WP2.5, O-12):** "random price level drawn independently of future bars, with comparable risk/cost distribution". The Schema Proposal's vocabulary draws a level uniformly between lo and hi OR-width multiples above the OR high. This control is only valid if the fill and exit logic cannot create an edge from drift; it is a *diagnostic of the simulator*, not a hypothesis test. Its definition is BLOCKED pending an owner/validator decision (Backlog B-16b).

### 5.5 Time-shuffle control

**Definition PROPOSED (Schema Proposal row 10):** `cyclic_day_shift` or `within_symbol_permutation`; `min_shift_days`; `reps`. All UNSET.

**Statistical-design issues (PREPARER'S ANALYSIS):**
1. A breakout rule's trigger is defined by the same day's OR; shifting entry *minutes* across days breaks the link between the OR and the subsequent path. That is the intended negative control, but a "positive result" has a legitimate, non-bug explanation: market drift (long-only in a rising market), the EOD-flat premium, and cost asymmetry. WP2.5 itself says "a positive control result is not by itself proof of a bug, nor is its absence proof of no leakage."
2. **If the control gates the run (stage-1 control check), its false-alarm rate becomes the probability the lineage is terminated by a correct engine.** Under attempt limit 1 and `on_fail = INCONCLUSIVE_ENGINE` (Plan WP4.0 step 2; Schema Proposal row 8, fixed), a negative-control test run at alpha = 0.05 would end the lineage with probability 0.05 even when the engine is perfect; two independent such controls: 0.0975. At alpha = 0.01: 0.0199; at 0.001: 0.002 (synthetic arithmetic, section 6.6). The Schema Proposal couples `negative_control_alpha` to the mode (`0.0` iff `invariants_only`), so the owner can choose. Recommendation (not a decision): gate the run on the deterministic invariants (no entry before 10:00, flat at close, ledger reconciles, no future-bar access), and treat statistical negative controls as *reported diagnostics* with a very small alpha if they must gate. The owner and validator decide O-10.
3. The invariant checks are exact; the statistical controls are not. They should not share an irreversible failure path.

### 5.6 Sample-size gates

| Gate | Value | Label | Feasibility (PREPARER'S ANALYSIS) |
|---|---|---|---|
| G1 | >= 300 trades in 2022-2025 | IN FORCE (code) | Implies ~0.30 trades per trading day over ~1,004 sessions. Whether the strategy (long only, first break, N = 100 names, portfolio limits) produces that is **UNKNOWN**; the trigger count is return-derived under the plan's own classification |
| P3a eligibility | >= 300 trades per candidate (PROPOSED) | UNSET | Same rate over ~1,006 sessions; if each candidate must reach it, the weakest candidate (e.g. a 3R target that fills rarely does not change entry count, but portfolio occupancy does) sets the bar |
| P3b | >= 150 (PROPOSED) | UNSET | ~0.30 per day over ~505 sessions; consistent with P4 rate. A miss is terminal |
| P5 | >= 100 trades, >= 60 days | IN FORCE (code) | 100 trades in 60 days is 1.67 per day, **5.6 times the historical-rate implied by G1 (0.30/day)** using the documented figures. Either the 60-day window cannot reach 100 trades at the P4 rate, or the P5 account trades materially more. This is an internal consistency question for the owner (PREPARER'S ANALYSIS from `p5.min_days`, `p5.min_trades` and G1; not verified against any data) |

**Power vs sample (section 6.1, 6.2; ILLUSTRATIVE, assumptions unvalidated):** under the assumed per-trade SD of 1.3 R and a day-clustering design effect of 1.2, the 80%-power minimum detectable mean net R for a one-sided 5% test is 0.29 R at 150 trades, 0.20 R at 300, 0.145 R at 600, 0.10 R at 1,200. Tightening to the Holm step (alpha 0.025) adds roughly 0.02-0.03 R. Under those assumptions a 300-trade test detects about 0.2 R with 80% probability. The strategy's true effect and SD are UNKNOWN, so no conclusion is drawn about how likely a real edge is to pass. The owner should be told that "REJECT" is read as "no demonstrated edge at this sample size", not "no edge" (Plan 2.7; RNG-001 §6 uses the same wording).

**PF 1.30 vs mean R (arithmetic):** with loss = 1 R, PF = p b / (1 - p). For PF = 1.30: win rate 35% needs b = 2.41 and gives mean R 0.195; 40%: b = 1.95, 0.18 R; 45%: 1.59, 0.165 R; 50%: 1.30, 0.15 R. So G2 (PF >= 1.30) implies a mean net R of about 0.15-0.20 R, which, under the ILLUSTRATIVE section 6 assumptions, is already near the 80%-power MDE at 300 trades. G2, G3, G4 and G5 are therefore not independent hurdles; under those assumptions a strategy that clears G2 at 300 trades would be borderline on G4/G5 (illustrative). This is useful: it shows no gate is redundant in the sense of being irrelevant, and that the real binding constraint is the combination.

### 5.7 Exit-candidate evaluation

- **Candidate structure:** E1 time exit, E2a/b fixed target 2R/3R, E3a/b breakeven-then-trail 1.0R/1.5R, E4a/b 50% scale-out at +1R with remainder EOD or trail. All share the OR-low stop and EOD flat; all share the identical entry stream (Plan 2.2).
- **Correlation structure:** same entries imply large positive correlation of candidate mean R. Different exits mainly reshape the payoff distribution (right-tail truncation for fixed targets, shorter holding for scale-out). Selection among them is closer to choosing a payoff shape than testing many distinct signals; that is a favorable property for the max-statistic.
- **Winner's curse (synthetic, section 6.5):** with K = 7, correlation 0.8 and SE 0.082 R at 300 trades, the expected maximum observed mean exceeds the common true mean by ~0.05 R even when all candidates are identical. Under these ILLUSTRATIVE assumptions the selected exit's P3a estimate is optimistic by about 0.05 R; the size of that relative to any true effect is UNKNOWN. P3b and P4 are the correction, so P3b's power matters.
- **Selection score is the lower bound of a one-sided bootstrap interval**, which favors lower-variance candidates. That is conservative but means a high-variance exit with a higher true mean can lose to a low-variance one; the complexity-order tie-break with tolerance delta applies only within delta. Delta units are R on a cost scale; the 0.05 R figure is explicitly an illustrative placeholder (Register D19 row) and the Schema Proposal notes the **within-family tie-break (E-1) is an unresolved escalation** (first listed vs smaller parameter vs inconclusive).
- **Path ambiguity:** with 1-minute bars the stop-vs-target order within a bar is unobservable. Plan WP2.2 applies the worst-case assumption (stop first) and flags `path_ambiguous`. This biases *against* target and scale-out exits relative to trailing/time exits in volatile minutes and could systematically favor E1 (time exit) in selection. The share of path-ambiguous trades per candidate is a mandatory report field; its effect on selection should be examined by a pre-registered sensitivity, not tuned.
- **Trailing exits on completed-bar closes** (Plan WP2.2A) introduce a one-bar lag, a deliberate conservative choice that also interacts with the 1-minute data-delay assumption (D14).
- **Verdict:** evaluation machinery is FEASIBLE-WITH-CONDITIONS on synthetic data now (Backlog B-08, B-12 READY synthetic only) and BLOCKED on real values (D19, D17, D06).

### 5.8 G10 redundancy

- **Design (Plan WP3 `redundancy.py`):** daily net-return correlation with each approved strategy; above 0.85 is flagged redundant. G10 is a **promotion constraint** (Plan 5.1), not a historical PASS/REJECT gate. Threshold 0.85 IN FORCE (code).
- **Assessment (PREPARER'S ANALYSIS):**
  1. A single intraday long-only strategy has many zero-return days (no entry). Pearson correlation of a sparse daily series against dense daily series is mechanically attenuated by the zeros, so 0.85 is a very high bar for a sparse strategy: nearly any ORB variant would pass G10 trivially, which may or may not be the intent. If the intent is "does this add a distinct return stream", correlation on active days or beta to market and sector factors would be more informative. This is a design observation for the owner, not a change to a locked threshold.
  2. **The comparison set is unowned.** "Approved strategies" is not defined for RANGE-002; the Schema Proposal lists it as O-13 / "OD-3" with no spec field and no decision sheet, and the independent review found the proposed D13 mapping does not preserve authority (Backlog Part IV item 4, E-5).
  3. **Data availability is UNKNOWN:** daily net-return series for the approved strategies over 2022-2025 (the holdout) must exist and be comparable (same days, same cost basis). Reading such series is itself a data access that touches the holdout calendar window with other programs' returns. The D01 contact audit should say whether that is acceptable.
  4. Because the constraint blocks *promotion* only, it can be computed late (P4/P6) and does not gate P0-P3. Verdict: UNKNOWN / BLOCKED on the unowned comparison set.

## 6. Synthetic arithmetic (no market data)

All numbers below are produced by `numpy`/`scipy` with fixed seed `20261010` from **assumed** distributions. They are illustrations of how the design behaves, not predictions about RANGE-002. Inputs that would need the validator's calibration: per-trade SD of net R (assumed 1.3), day-clustering design effect (assumed 1.2, as if ~3 trades per active day with intraclass correlation ~0.1), correlation of exit candidates (0.8), baseline mean (-0.03 R), shrinkage of the selected effect from P3a to P3b (0.7, arbitrary). Changing these changes the tables. **Reproducibility note:** the script that produced these numbers is committed as `docs/implementation/evidence/range_002/range002_synthetic_power_illustration.py` (synthetic only, no data, fixed seed `20261010`, numpy/scipy). It was written as scratch, has had no independent review, and reproduction by another party has not been done, so the numbers are not independently reproduced. Exact assumptions are those listed above and in section 6.5.

Formulas: SE = SD * sqrt(DEFF / n); MDE(80%) = (z_{1-alpha} + z_{0.8}) * SE; power(m) = 1 - Phi(z_{1-alpha} - m / SE).

### 6.1 Minimum detectable mean net R at 80% power (one-sided)

| Trades n | alpha 0.05 | alpha 0.025 (Holm step 1, m = 2) | alpha 0.0125 |
|---|---|---|---|
| 150 | 0.289 R | 0.326 R | 0.358 R |
| 300 | 0.204 R | 0.230 R | 0.253 R |
| 600 | 0.145 R | 0.163 R | 0.179 R |
| 1,200 | 0.102 R | 0.115 R | 0.127 R |

### 6.2 Power of a single test at true mean m

| n | m = 0.05 R | 0.10 R | 0.15 R | 0.20 R | (alpha) |
|---|---|---|---|---|---|
| 150 | 0.11 | 0.22 | 0.36 | 0.53 | 0.05 |
| 150 | 0.06 | 0.14 | 0.25 | 0.41 | 0.025 |
| 300 | 0.15 | 0.33 | 0.57 | 0.78 | 0.05 |
| 300 | 0.09 | 0.23 | 0.45 | 0.68 | 0.025 |
| 600 | 0.22 | 0.53 | 0.83 | 0.96 | 0.05 |
| 600 | 0.14 | 0.41 | 0.73 | 0.93 | 0.025 |

### 6.3 P4 requirement G4 AND G5, Holm over {G4, G5} vs separate tests at 0.05

G5 difference = m + 0.03 R (baseline -0.03 R), SE_5 = sqrt(2) * SE_4, correlation between the two z statistics 0.71. Probability both pass:

| n | m | Holm (m = 2) | Separate, each 0.05 |
|---|---|---|---|
| 300 | 0.05 | 0.08 | 0.09 |
| 300 | 0.10 | 0.19 | 0.21 |
| 300 | 0.15 | 0.36 | 0.38 |
| 300 | 0.20 | 0.57 | 0.58 |
| 600 | 0.05 | 0.12 | 0.14 |
| 600 | 0.10 | 0.35 | 0.37 |
| 600 | 0.15 | 0.65 | 0.66 |
| 600 | 0.20 | 0.86 | 0.87 |

### 6.4 Size of the recentered-null percentile day-clustered bootstrap under a skewed null

Null R: -1 with probability 0.6, +1.5 with probability 0.4 (mean 0); trades per day Poisson; resampling unit = trading day; estimator = ratio of sums; B = 1,000; 1,500 replications per cell.

| Days | Expected trades | Rejection rate at nominal 0.05 |
|---|---|---|
| 500 | ~150 | 0.046 |
| 1,000 | ~300 | 0.051 |
| 1,000 | ~600 | 0.056 |

Monte Carlo SE ~0.006. Acceptable for this shape. Real R distributions (trailing exits with occasional large winners, EOD forced exits) are heavier tailed; the validator must repeat this with the frozen estimator.

### 6.5 Chain pass probability, P3a selection test -> P3b -> P4 (G4 only at alpha 0.025)

P3a uses max-statistic critical value 2.0 (rho about 0.9); P3b tests the selected exit at alpha 0.05 with the true effect shrunk by 0.7; P4 at alpha 0.025 with the same shrinkage. Product assumes independent data windows.

| True mean m | P3a pass | P3b pass | P4 pass | All three (n = 300/150/300) | All three at double sample (600/300/600) |
|---|---|---|---|---|---|
| 0.05 R | 0.08 | 0.09 | 0.06 | 0.000 | 0.001 |
| 0.10 R | 0.22 | 0.15 | 0.13 | 0.004 | 0.019 |
| 0.15 R | 0.43 | 0.23 | 0.25 | 0.024 | 0.113 |
| 0.20 R | 0.67 | 0.33 | 0.40 | 0.088 | 0.326 |

Interpretation (PREPARER'S ANALYSIS, ILLUSTRATIVE ONLY, under these synthetic assumptions: per-trade SD 1.3 R; day-clustering design effect 1.2; candidate correlation 0.8 (P3a critical value 2.0 assumes about 0.9); trade counts 300/150/300 (or 600/300/600); P3a/P3b/P4 independent windows; P3b and P4 true effect shrunk to 0.7 of the P3a value (arbitrary); P3b one-sided alpha 0.05; P4 G4 alone at alpha 0.025; baseline -0.03 R. None is measured or validated. The stage probabilities are multiplied (independence assumed). The figures are illustrative arithmetic, not independently reproduced or reviewed by the validator. Not a general finding about RANGE-002.) Under those assumptions only, a true 0.15 R edge passed all three stages in about 2% of simulated sequences at the smaller counts and about 11% at the doubled counts. Other assumptions (lower SD, larger sample, higher edge, different window effects) can change this materially, so no statement about how likely real edges are to produce STOP/REJECT is made. The arithmetic does show that results depend strongly on sample size, which is what the owner may weigh when setting D17/D03.

**Winner's curse at selection:** K = 7 identical candidates (true mean m, correlation 0.8, n = 300, SE 0.082 R): E[max observed mean] = m + 0.050 R for m = 0 and for m = 0.05.

### 6.6 False-alarm probability of correct engines under limit 1

P(at least one of two independent negative-control tests fires on a correct engine): alpha 0.05 -> 0.0975; alpha 0.01 -> 0.0199; alpha 0.001 -> 0.0020. Each such event is `INCONCLUSIVE_ENGINE` and, with attempt limit 1 and no recovery path in code, ends the lineage (Register 3.2, 3.3).

### 6.7 Illustrative data-volume bound

Rows per symbol-month <= 23 x 390 = 8,970. Union of 100 names x 120 months x 8,190 typical = 9.8 x 10^7 rows lower bound; actual union size UNKNOWN until the PIT universe is built.

### 6.8 Provenance and reproducibility of the section 6 figures

- **Which script produced the figures:** all section 6 figures (MDE table, power tables, Holm vs separate, bootstrap size, K=7 critical values, chain probabilities, winner's curse, false-alarm arithmetic, PF vs mean R) came from ONE scratch script, `synth.py`, written by the preparer agent and run once before the report was drafted. It lived in the session scratch directory (not in the repo) until it was copied unchanged into `docs/implementation/evidence/range_002/range002_synthetic_power_illustration.py`.
- **Relationship of the committed script to the original:** it is a byte-for-byte copy, not a rewrite. SHA-256 of both files: `744F73264967D6814C1C5D46379C7096C0A8DD832D5CA8A8D5196E791A73173B`. (Hash as of commit 400d019f; later commits add a comment-only header and comment fix to the script, so the current hash differs; no executable line changed.) After the copy the preparer re-ran the file under `python -I` and the output reproduced the report values checked (0.36/0.25 and 0.57/0.45 power cells; Holm/separate 0.36/0.38 at n=300, m=0.15; type-I 0.046/0.051/0.056; chain 0.024 and 0.113 at m=0.15; winner's-curse bias 0.05, SE 0.082). The original and re-run outputs were compared by eye on those lines, not by a stored diff; the original output was not saved as a file.
- **Environment:** Python 3.12.10, numpy 2.2.6, scipy 1.18.1 (Windows 11). The script pins nothing itself; other versions may change random streams.
- **Command:** `python -I range002_synthetic_power_illustration.py` (no arguments, no input files, no network; seed `numpy.random.default_rng(20261010)` once at the top, so results depend on the order of the computations in the file). Runtime: about 40 s (as measured by Agent E; not timed by the author).
- **Reproducibility limitations:** (a) the script is published with this report and has no tests, no pinned dependency versions and no documented invocation beyond the above; (b) its outputs are not stored as an artifact; (c) the script has not been reviewed for correctness; it was independently regenerated on one environment by Agent E (byte-identical across two runs); original provenance is separate: the committed script is a byte-for-byte copy of the scratch script per the author, and comparison of the original output was by eye with no stored diff; (d) the validator's calibration (D06) and any selection-bias study have no scripts yet. The assumptions are illustrative, not measured.

## 7. Cross-cutting design risks

1. **Irreversibility vs multi-stage statistics.** Attempt consumption at authorization time (code) combined with stage-1 controls that can fail (plan) and a single P3a/P3b attempt (provisional) means nearly any non-research failure terminates a registered lineage. This is an owner-accepted design property (Register Part IV P-2) but it raises the importance of synthetic-fixture and `REPLAY_RNG001` engine validation before P3a authorization, and of keeping statistical controls out of the irreversible failure path (5.5).
2. **A1 not yet signed but already assumed by code.** Rejecting A1 now needs code changes to the partition equality validators, registry phases and verdict machine (Register C-SCHEMA). Independent methodology review of the exit-selection design is a stated precondition (Register Part IV P-3).
3. **Terminology drift.** "m = 1" counts exit configurations; the Holm family size is a separate owner value (D02). "Attempt" has a registry meaning and a looser plan meaning (C-LEDGER).
4. **Return-blindness boundary.** Trigger frequency, crossed-before-arm share, regime counts and capacity are sometimes treated as return-blind (counts relative to OR high) and sometimes as return-derived (frequency depends on future highs). The Plan says to ask the owner (WP2.1A) and to keep the unresolved ones behind `results_guard`. Section 5.6 sample-size feasibility is therefore UNKNOWN until that ruling.
5. **Costs comparable to the effect.** 10 bps round trip at an ILLUSTRATIVE OR width of 100 bps of price is ~0.1 R; the size of any real edge is UNKNOWN (2.6). Narrow-OR days dominate cost drag; `signal.min_or_width_ticks` (D05 5b) is a first-order parameter that must be set before results.

---

# 8. BLOCKERS AND VERDICTS

## 8.1 Blockers list (ordered by what unblocks the most)

| # | Blocker | Type | Blocks |
|---|---|---|---|
| B1 | **Every P0 decision unsigned; P0 is NO-GO** (D01-D19, A1). No spec value exists | Decision | Freeze, all real-value work |
| B2 | **D08 independent validator not named**; SoD option unsigned (SoD-A + SoD-C provisional); R1-L1b follow-up (`57dadd52`) unmerged | Decision / people | Any formal P0 approval or real freeze (owner ruling 5) |
| B3 | **Vendor feasibility F1 (SIP minute depth to 2016), F2 (delisted coverage), F5 (storage/research licence), F6 (page/rate limits)**: undocumented in repo | UNKNOWN / owner vendor verification | D03, WP1.3, P1; stop condition 9.3 |
| B4 | **Research host unnamed** (C12); Norton blocks laptop; laptop standby; `ec2-paper` excluded | Decision / infrastructure | P1, RNG-001 replay, D09-hist option (c) |
| B5 | **D11 `data.fetch_mode` enumeration undefined**; new SIP loader unbuilt; `BarCache` is IEX/limit-10000/feed-less-key and must remain untouched | Decision / build | P1 (PR 5) |
| B6 | **D06 bootstrap/baseline parameters and estimand unset**; D02 family count unset; D17 criteria, D18 basis, D19 candidate set/delta/tie-break unset | Decision | Selection rule, gates, freeze |
| B7 | **D05 / D14 / D15 execution and cost values unset**; F3 (broker stop semantics), F4 (bar timestamp convention/delay) unmeasured; any broker probe needs separate owner authorization (R14) | Decision / UNKNOWN | Engine real-value path, WP0.12 fixtures |
| B8 | **Control definitions (time-shuffle, no-information, stage-1 pass rule) undefined** and not reviewed; false-alarm path coupled to an irreversible attempt | Decision / validator review | Stage-1 gate, P3a |
| B9 | **D01 exposure audit unsigned** (AI-session contact, daily-layer use by other programs) | Evidence | G0 / holdout validity |
| B10 | **Non-equivalence check (C2) not specified/approved; D09-hist unresolved; overlap number and reviewers blank** | Decision | P0 exit gate |
| B11 | **Schema batch not approved/merged** (20 owner-valued leaves + `p5.account_binding`, 6 values with no field); must precede any real freeze | Decision / separate implementation authorization (Q-B2, Q-B4) | Freeze; avoids re-freeze |
| B12 | **Genesis enrollment pending** (host/path, operator, witness, manifest triple, limits) | Decision | Freeze, P3a |
| B13 | **C-DR conflict** (defect-only reruns vs limit 1) needs Plan wording correction; A1 vs v0.4 vs merged schema reconciliation memo unsigned | Decision | A1 signature, limits |
| B14 | **S3 manifest tooling absent**; governed evidence publication impossible | Tooling | Evidence custody (run-local manifests still possible) |
| B15 | **Execution boundary B-1 (holdout ingest) undesigned/unsigned** | Design | Any 2022-2025 ingest, P4 |
| B16 | **Sample-size feasibility unknown** (trade rate for G1/D17, P5 100-in-60-days consistency) pending return-blind-vs-return-derived ruling | UNKNOWN / ruling | D17 minimums, lineage-ending STOP risk |
| B17 | **G10 comparison set (OD-3) unowned**; approved-strategy daily series availability unknown | Decision / UNKNOWN | Promotion only |

## 8.2 Feasibility verdicts per area

Evidence cited as `file:line` where the repository gives a line; section references otherwise. Paths are relative to the repo root. Plan = `docs/implementation/evidence/range_002/RANGE-002_Implementation_Plan_v0.5.md`; Register = `.../RANGE-002_P0_Decision_Register_v0.2.md`.

### D1 Data

| Area | Verdict | Evidence and conditions |
|---|---|---|
| PIT stock universe / survivorship (daily layer) | **FEASIBLE-WITH-CONDITIONS** | Daily PIT spine and lineage refusal exist (`apps/backend/app/validation/security_lineage.py:55-83,211`; `recon.md` §2.3). Conditions: reverse join permaticker-to-vendor-ticker absent (Backlog 7.2); Sharadar TICKERS point-in-time-ness UNKNOWN; lineage constants unowned (O-7); exclusions must be counted and bounded (`data.exclusion_bound` UNSET) |
| Delisted-name intraday coverage | **UNKNOWN** | Not documented (Sheets F2, `RANGE-002_P0_Decision_Sheets_v0.1.md:367`); stop condition Plan §9 item 3 (Plan §9, from line 774) |
| Opening-range 1-minute SIP bars 2016-2025 | **UNKNOWN** | Historical depth, storage rights, rate limits not documented (Sheets F1, F5, F6 at :366,:370,:371); repo only documents recent-SIP entitlement (`docs/design/SIP-CACHE-001/...v1.0.1.md:84,134,162-168`) |
| Real pull execution | **BLOCKED** | C12 host BLANK (Register D-table row C12); D03, D11 unsigned; P0 gate (Plan WP1 header, WP0.4); holdout fence B-1 (Backlog 7.1) |
| Corporate actions / price basis | **FEASIBLE-WITH-CONDITIONS** | Design clear (Plan WP1.6); vendor intraday adjustment semantics UNKNOWN (Backlog V9); `data.adjustment` proposed, UNSET (Schema Proposal row 1) |
| Market calendar 2016-2025 | **FEASIBLE-WITH-CONDITIONS** | Existing XNYS helper clamped at `FORWARD_START` (`eval_calendar.py:67,78,98`; `forward_window.py:42`); new `data/calendar.py` required (Backlog L1); synthetic-buildable |
| Missingness / halts / liquidity | **FEASIBLE-WITH-CONDITIONS** | Classification design complete (Plan WP1.7; Backlog L7); halt evidence source and quote availability UNKNOWN (O-16, F10); reconciliation tolerance UNSET |
| SIP vs IEX suitability | **FEASIBLE-WITH-CONDITIONS** (SIP) / **not suitable** (IEX as evidence) | Spec requires SIP (Plan §2.1 "Data" row); `bar_cache.py:428` is IEX-only; IEX archive limited to plumbing replay (`REPLAY_RNG001`, Plan WP0.4). Magnitude of IEX-vs-SIP bar difference UNKNOWN; not measured |
| Slippage and transaction costs | **FEASIBLE-WITH-CONDITIONS** | 5/15 bps locked; accounting mode D15 UNSIGNED; no measured slippage evidence in repo (`RNG-001...md:136,169`); quote history UNKNOWN (F10) |
| Lineage / reproducible snapshots | **FEASIBLE-WITH-CONDITIONS** (run-local) / **BLOCKED** (governed S3 publication) | Run-local manifest design in Backlog L5-L6; `manifests/s3/` absent (Backlog 2.3 item 4) |
| Licensing and permitted use | **UNKNOWN** | Section 2.8: only ADR 0018 item 6 (`docs/adr/0018-point-in-time-factor-data-fmp-sharadar.md:82-86`) and SIP-CACHE entitlement documented; owner must verify with each vendor |

### D2 Platform

| Area | Verdict | Evidence and conditions |
|---|---|---|
| `BarCache` for SIP | **BLOCKED** (cannot be used) | `apps/backend/app/market_data/bar_cache.py:428-429` (IEX, limit 10000), `:197-198` (key without feed), `:278-285` (single call), `:297-315` (`.empty` markers); ADR 0033 points 1-3 unimplemented (`recon.md` §2.7) |
| New RANGE-002 SIP loader (design) | **FEASIBLE-WITH-CONDITIONS** | Direction ruled (recon §0 item 2; A1 §7); synthetic-buildable (Backlog L2-L11); real operation blocked by D03, D11, C12, F1/F2/F5/F6; adapter route Q-B1 |
| Intraday coverage validator | **FEASIBLE-WITH-CONDITIONS** | Ruled C4; synthetic-buildable (Backlog L8); thresholds `data.coverage_min`, `exclusion_bound` UNSET |
| Engine, exits, scheduler | **FEASIBLE-WITH-CONDITIONS** | READY synthetic only (Backlog 12.1 B-03..B-09); real values BLOCKED on D05, D14, D15, D19 |
| Governance infrastructure (registry, guard, ledger, holdout token) | **FEASIBLE** (exists) with conditions | Merged `app/research/range002/governance/*` (Register 0.1); infrastructure-only acceptance; genesis, limits and signers all BLANK |
| Spec freeze | **BLOCKED** | 66 unset fields (Register 4.5); D08 distinct-human obligation; schema batch before freeze (Schema Proposal §1) |
| Non-equivalence check | **BLOCKED** | C2 spec pending; no tool (`recon.md` §2.8; Plan WP0.5) |
| S3 evidence custody | **BLOCKED** | Tooling absent (Backlog 2.3) |

### D3 Methodology

| Area | Verdict | Evidence and conditions |
|---|---|---|
| P3a / P3b separation | **FEASIBLE-WITH-CONDITIONS** | Sound in principle (A1 §3; RNG-001 §3.5); P3b power is limited under the ILLUSTRATIVE section 6 assumptions (6.1/6.5) and there is regime mismatch; terminal-failure semantics (Register 3.2-3.5); A1 unsigned |
| Day-clustered bootstrap | **FEASIBLE-WITH-CONDITIONS** | Not existing (recon §2.6); size acceptable under a synthetic skewed null (6.4); estimand and all parameters UNSET (D06; Register 4.3) |
| Max-statistic selection-aware test | **FEASIBLE-WITH-CONDITIONS** | Highly correlated candidates give modest critical-value inflation (5.2); needs validator review (O-8) and D17 level |
| Holm / multiplicity | **FEASIBLE-WITH-CONDITIONS** | Power cost of Holm over {G4, G5} about 1-2 points (6.3); D02 family count UNSET; option (b) representation to confirm (Register 4.2) |
| Random-entry control | **FEASIBLE-WITH-CONDITIONS** | Design in Plan WP2.5; matching dimensions omit time-of-day/volatility conditioning (5.4); parameters UNSET (D06) |
| Time-shuffle control | **BLOCKED** (definition) | `controls.time_shuffle` not defined or reviewed (Schema Proposal row 10, §4.4); false-alarm coupling to irreversible attempt (5.5, 6.6) |
| No-information baseline | **BLOCKED** (definition) | `controls.no_information` vocabulary is a preparer proposal (Schema Proposal row 11); simulator diagnostic only |
| Sample-size gates (G1, P3a, P3b, P5) | **UNKNOWN** | Trade rate return-derived and unobservable return-blind (Plan 2.4 item 5; Register C-N); P5 100-in-60-days implies a 5.6x rate vs G1 (5.6) |
| Statistical power of the full chain | **UNKNOWN** (illustrative arithmetic only) | ILLUSTRATIVE, NOT validator-calibrated. Under these synthetic assumptions only: per-trade SD 1.3 R; day-clustering design effect 1.2; exit-candidate correlation 0.8 (P3a critical value 2.0 corresponds to about 0.9); trade counts 300/150/300 or 600/300/600; P3a, P3b and P4 treated as independent windows so stage probabilities multiply; P3b and P4 true effect shrunk to 0.7 of the P3a value (arbitrary); P3b one-sided alpha 0.05; P4 G4 alone at alpha 0.025; baseline -0.03 R; true edge 0.15 R. Under those assumptions a 0.15 R edge passed all three stages about 2% (smaller counts) and about 11% (doubled counts). Not a general finding about RANGE-002. Script: `range002_synthetic_power_illustration.py` (same directory; see 6.8 for provenance); not independently reviewed. |
| Exit-candidate evaluation | **FEASIBLE-WITH-CONDITIONS** | Mechanics in Plan WP2.2A; worst-case path rule penalizes target-type exits; winner's curse ~0.05 R at K = 7 under ILLUSTRATIVE synthetic assumptions (6.5); tie-break E-1 unresolved |
| G10 redundancy | **UNKNOWN** | Comparison set unowned (OD-3); sparse-series correlation attenuation (5.8); approved-strategy series availability unknown |

## 9. Unresolved questions for the owner

1. Is Alpaca SIP historical 1-minute coverage to 2016-01-01, including delisted names, available under the current subscription, and does the licence permit bulk storage for research (F1, F2, F5, F6)? Who verifies with the vendor and when?
2. Which host is the approved isolated research environment (C12), and who is accountable?
3. Is trigger frequency / crossed-before-arm share return-blind (countable pre-P3) or return-derived (sealed)? This decides whether D17 minimums can ever be checked before they can end the lineage.
4. Which estimator defines "mean net R per trade" for the day-clustered bootstrap (ratio of sums or mean of day means), and what block length (D06)?
5. Should statistical negative controls gate the irreversible run (O-10), or only the deterministic invariants?
6. Does the random-entry baseline match on time of day and volatility conditioning, or only on the dimensions in the Schema Proposal?
7. How is P5's 100-trades-in-60-days minimum reconciled with the 300-trades-in-four-years G1 rate?
8. What is the "approved strategies" comparison set for G10 (OD-3), and is reading their holdout-window daily returns acceptable under D01?
9. Does any vendor licence restrict passing vendor data through an LLM session (relevant to the AI-provenance record WP0.8 and the D01 contact audit)?
10. The power figures in section 6.5 are ILLUSTRATIVE and rest on the unvalidated synthetic assumptions listed there (SD 1.3 R, design effect 1.2, candidate correlation 0.8, independent stage windows, 0.7 shrink, baseline -0.03 R). How will the owner use an independent power calibration, with the validator's own SD and design-effect estimates and a reviewed, version-pinned simulation script, when setting D17/D03 (N, windows, limits)?

## 10. What this report did and did not do

Did: read repository files (Plan v0.5, A1, Sheets, Register v0.2, reconciliation, recon, RNG-001, Backlog and Schema Proposal via `git show`, `bar_cache.py`, `security_lineage.py`, `eval_calendar.py`, `spec/schema.py`, SIP-CACHE-001 contract, ADR 0018) and run synthetic numeric simulations in a scratch directory.

Did not: read the design v0.4 DOCX (untracked; known only through the repository's reconciliation), access any data or network, read credentials or `.env`, run the Docker stack, run governed code, compute any RANGE-002 return, choose or default any P0 value, or push.
