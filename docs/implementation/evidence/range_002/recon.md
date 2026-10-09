# RANGE-002 — WP0.1 Repository Reconnaissance

| Field | Value |
|---|---|
| Work package | WP0.1 (RANGE-002 Implementation Plan v0.4, §4) |
| Date | 2026-10-09 |
| Repo HEAD | `5b23707f` (branch `fix/time-bomb-tests`; working tree dirty, see "Untracked inputs") |
| Data accessed | None. Read-only code and document inspection. No returns computed, no broker or data-provider access. |
| Status | **Owner-reviewed 2026-10-09; direction approved with the decisions in §0.** Ready for review and merge. Nothing in this document is a P0 sign-off. |
| Companion | `governing_reconciliation.md` (design v0.4 / plan v0.4 / ADR 0014, 0033, 0037 reconciliation; conflicts C1–C12 awaiting owner rulings) |

## 0. Owner decisions on this recon (2026-10-09)

| # | Topic | Ruling | Effect on the work |
|---|---|---|---|
| 1 | Repository structure | **Approved.** `docs/implementation/evidence/range_002/` holds RANGE-002 governance docs, specs, manifests and evidence references. Large generated artifacts go to external storage with versioned manifests per repo policy | Plan v0.4 path mappings updated (§4). Code stays under `apps/backend/app/research/range002/`, tests under `apps/backend/tests/research/range002/` |
| 2 | D11, SIP loader | **Approved: build a new RANGE-002-specific SIP historical loader; do not modify `BarCache`; no change to production market-data behavior.** Required: explicit SIP feed with no IEX fallback; monthly chunking with pagination and truncation detection; historical completeness checks; idempotent retry and resume; data-source identification, timestamps and SHA-256 manifests; delisted coverage where the licensed source supports it | P1 work (PR 5). Open point C4: `dataset_health` is daily-only, so the loader needs its own intraday completeness check. Licensed SIP history depth and delisted coverage are still unverified (stop condition §9.3) |
| 3 | D06, bootstrap | **Proceed with the design of a day-clustered block-bootstrap module**, using existing utilities as references. **Do not claim it already exists in MR-002.** Method, block length, repetitions, confidence levels and hypothesis adjustments **remain open owner decisions** | Plan wording to be corrected (reconciliation C11). Design reference only: `factor_data/evidence.py`, `market_projection/validate.py` |
| 4 | D09, non-equivalence | Review ADR 0037 and the RNG-001 evidence **before** defining criteria. Implement a **deterministic check with explicit evidence and documented review outcomes**. A difference in strategy names or parameters is not proof of non-equivalence | Review done: ADR 0037 defines no test (C2). Proposed criteria basis and constraints are in `governing_reconciliation.md` C2, awaiting approval. No code until approved |
| 5 | Governing documents | Read the complete design v0.4 and reconcile it with the plan and ADR 0014, 0033, 0037 **before P0 sign-off**. Report conflicts for owner approval; **do not resolve governing conflicts by changing code** | Done: `governing_reconciliation.md`. 12 findings, none resolved in code |
| 6 | WP0.1 completion | Update this file; complete the documentation review; prepare WP0.1 for review and merge | This update |
| 7 | PR 2 | After WP0.1 is merged: spec schema, canonical hashing, freeze tool. For unresolved D01–D18: required fields and validation errors, **values unresolved**. **Do not freeze or sign the spec, authorize historical computations, or enter P1** until approvals and prerequisites are complete | Not started. Waiting for the WP0.1 merge |

**Standing conditions:** stop and escalate any unresolved governing conflict or material data-integrity issue. Primary objective: a reliable foundation for validating a genuinely profitable strategy, not for producing passing backtests.

SHA column = last commit touching the file (`git log -1 --format=%h -- <path>`) at HEAD `5b23707f`. Dispositions: **REUSE** (use as is), **WRAP** (use behind a RANGE-002 adapter), **REFERENCE** (copy the pattern, not the code), **DO-NOT-USE**, **NOT-FOUND**.

## 1. Headline findings

1. **There is no reusable ORB engine, run registry, results guard, exposure ledger, holdout token, Holm function, SIP 1-minute historical loader, or runnable non-equivalence check.** All must be built (NOT-FOUND).
2. **`BarCache` cannot be used for SIP research.** It hardcodes `DataFeed.IEX` (`bar_cache.py:428`), its cache keys do not include the feed, and ADR 0033 points 1–3 are still unimplemented there. Plan stop condition §9.4 applies unless the monthly-chunk path is approved (D11).
3. **`MarketSession` must not be used for governed research.** It falls back silently to curated holiday lists. `validation/eval_calendar.py` fails closed and is the right base.
4. **The plan's bootstrap premise is only partly true.** "Adopted from MR-002" is not verifiable from code, and no day-clustered stationary bootstrap exists. This is a D06 item for the owner.
5. **The plan's layout needs path adjustments** (§4 below). `docs/research/` does not exist.
6. **`scripts/research/rebuild_5min_cache.py`, cited by ADR 0033, is not tracked in the repo.** Its role is played by `apps/backend/scripts/research/range/backfill_intraday.py`.

## 2. Module map

### 2.1 RNG-001 engine, scripts and replay (WP2.6)

| Path | SHA | What it is | Disposition |
|---|---|---|---|
| `apps/backend/scripts/range_evidence.py` | `0fe8ad24` | Walk-forward plus i.i.d. trade-level bootstrap; writes `docs/implementation/evidence/range_rejection/range_evidence.{json,md}` | **REFERENCE / WRAP** for the old-engine reproduction (102 trades, PF 1.271) |
| `apps/backend/scripts/range_5c_gate.py` | `296f4f02` | Pre-registered GO/NO-GO gate. Pure `evaluate_gate(...)`, `GateThresholds`, `GateMetrics` | **REFERENCE** for the gate-function pattern |
| `apps/backend/app/strategies/backtester.py` (+ `backtest_models.py`, `backtest_context.py`) | `fe2d3abb` | Production `Backtester` used by the `backtest_range_trader_*.py` scripts | **WRAP**, RNG-001 reproduction only |
| `apps/backend/scripts/research/range/range_funnel.py` | `eee53a06` | Flat script: fade entry at OR low, 5 bps/side, IEX 5-min parquet | **DO-NOT-USE** as code (opposite logic); reference for replay |
| `apps/backend/scripts/research/range/range_variant_study.py` | `eee53a06` | Variants A/mid/vwap/vwap_gate with train/test split | **DO-NOT-USE** |
| `apps/backend/scripts/research/range/backfill_intraday.py` | `eee53a06` | Month-chunked IEX 5-min backfill, hardcoded 18 names; deletes `.empty` markers | **DO-NOT-USE** (hardcoded, IEX) |
| `apps/backend/strategies_user/templates/range_trader{,_vwap}.py`; `app/services/range_{execution,opening_levels,insight,auto_select}.py` | n/a | Live Range Trader (user 2) code | **DO-NOT-USE** (plan R5) |
| `scripts/research/rebuild_5min_cache.py` | n/a | Cited by ADR 0033 line 70 | **NOT-FOUND** |

### 2.2 CAP-025 funnel

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `docs/implementation/evidence/cap_025/CAP025_IntradayReplayFunnel_Charter_v0.1.md` | `f22a6448` | Charter only. No library module exists | **REUSE the design** (stop-first-within-bar, date-clustered inference); **code NOT-FOUND** |
| `apps/backend/app/research/gapper_stage0/funnel.py` | `74d569da` | `build_funnel_record`, `FunnelRecord`, `Exclusion` (reason-coded funnel) | **REFERENCE** for WP3.1 |

### 2.3 PIT universe, identity and daily data (WP1.5)

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `apps/backend/app/factor_data/store.py` | `956e932c` | DuckDB `FactorDataStore`: `permaticker_asof`, `trading_days`, `get_prices_many`, `price_date_bounds`, `dollar_volume_universe` | **REUSE** |
| `apps/backend/app/factor_data/universe.py` | `1a827e64` | `universe_asof(store, as_of, n, lookback_days)`; survivorship-free, raises `UniverseUnavailable`. Returns tickers, not permatickers; not monthly | **WRAP** for the monthly rebuild |
| `apps/backend/app/validation/security_lineage.py` | `5173b7c2` | `resolve_lineage`, `assess_universe`, `LineageRefusal`; refuses ticker-reuse boundaries | **REUSE** |
| `apps/backend/app/universe/security_identity.py` | `956e932c` | `FactorStoreSecurityIdentityResolver.resolve` | **REUSE** |
| `apps/backend/app/factor_data/evidence.py` | `1cee32f4` | `dataset_health` (ADR 0033 point 4), plus bootstrap functions (§2.6) | **REUSE** |
| `apps/backend/app/factor_data/total_return.py` | `f780b3a0` | Corporate-action adjustment | **WRAP** (plan WP1.6: do not mix raw and adjusted series) |

### 2.4 Calendar (WP1.4)

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `apps/backend/app/validation/eval_calendar.py` | `a5729d4b` | Authoritative XNYS; raises `EvalCalendarError` if `pandas_market_calendars` is unavailable | **REUSE / WRAP** |
| `apps/backend/app/market/session.py` | `7bd35f1c` | `MarketSession`; silent fallback to curated lists, half-day close 13:00 | **DO-NOT-USE** for governed research |
| `apps/backend/app/services/market_hours.py` | n/a | No holiday handling | **DO-NOT-USE** |

There is no dedicated DST utility or test. WP1.4 must add them.

### 2.5 Ledger, registry and governance (WP0.2–0.7)

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `apps/backend/app/research/disc_mdq/ledger.py` | `50efc2fb` | Hash-chained append-only `DiscoveryLedger`, `LedgerRecord`, `CodeIdentity`, `LedgerIntegrityError` | **REFERENCE / WRAP** for run registry and exposure ledger |
| `apps/backend/app/research/registry/store.py` | `4864f40c` | DuckDB `ResearchStore` (strategy, dataset, experiment, artifact, transition log) | **REUSE** for WP0.7 registration |
| `apps/backend/app/research/gapper_stage0/design_latch.py` | `74d569da` | `latch_design(docx_path)` pins approved-design SHA-256 | **REFERENCE** for the frozen-spec latch |
| `apps/backend/app/validation/forward_window.py` | `7c2ca104` | `preflight`, `seal_performance` (OPEN/SEALED split) | **REFERENCE** for `results_guard` and the WP4.0 sealed run |
| `apps/backend/app/validation/governed_corpus.py` | `712c9cac` | `canonical_json`, `file_sha256` | **REUSE** for spec hashing |
| `apps/backend/app/research/promotion/gate.py` | `03227406` | `GateProfile`, `evaluate`, `gate_experiment` | **WRAP** for G0–G10 |
| `apps/backend/app/research/programs.py` | `9e5cf65f` | Program catalog (RNG-001 listed as rejected) | **REUSE**: RANGE-002 needs an entry |
| Trial ledger | n/a | Exists as documents and JSON, not code: `docs/review/momentum_daily/equal_weight_validation/TrialLedger_v1.0.{json,md}`; lifecycle doc §5.2 | Reference for format |
| `results_guard`, `run_registry`, `exposure_ledger`, `holdout_token` | n/a | | **NOT-FOUND**, build new |

### 2.6 Statistics (WP3)

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `apps/backend/app/factor_data/evidence.py` | `1cee32f4` | `block_bootstrap_ci` (circular fixed block, recentered-null one-sided p), `cluster_bootstrap_ci`, `paired_sharpe_diff_ci` | **WRAP** the one-sided p-value logic |
| `apps/backend/app/services/market_projection/validate.py` | `181edf7c` | `block_bootstrap_delta_ci`: true stationary block bootstrap (geometric blocks, `BLOCK_LEN=10`) | **REFERENCE** for the resampler |
| Day-clustered stationary bootstrap | n/a | | **NOT-FOUND**, build in `range002/stats/bootstrap.py` |
| Holm adjustment | n/a | Only doc-level mentions | **NOT-FOUND**, small pure function |

"MR-002" is the Mean-Reversion-002 validation program; no module of that name exists. Owner to confirm the convention under D06.

### 2.7 Market data, feed and bar cache (WP1.1–1.3)

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `apps/backend/app/market_data/bar_cache.py` | `ed597334` | Hardcoded `DataFeed.IEX` at line 428, `limit=10000` at line 429 | **DO-NOT-USE** for SIP |
| `apps/backend/app/research/capture/collector.py` | `86d8cbd5` | `fetch_session_bars(client, universe, session, feed)`: explicit feed, 1-min bars, no `limit` | **WRAP / REFERENCE** for a SIP loader (SDK page handling unverified) |
| `apps/backend/app/market_data/sip/*` | n/a | Governed SIP plane; latest quotes only, no 1-min history; fails closed, no fallback feed | **REFERENCE** (feed identity checks) |
| `apps/backend/scripts/check_marketdata_feed_pinning.sh` | `63c0c521` | AST check: explicit `feed=`; does not dictate sip vs iex, and cannot stop a SIP-labelled file being written from an IEX call | The plan's loader assertion is still needed |

**ADR 0033 status in `bar_cache.py`** (answer to WP1.1, to be re-verified at PR time):

| Point | State | Evidence |
|---|---|---|
| 1. `.empty` scoped to returned range | **Not implemented** | `_fetch_and_write` lines 297–316 mark any bucket without rows; no `[df.t.min, df.t.max]` comparison |
| 2. `len == limit` treated as possibly truncated | **Not implemented** | Result accepted at lines 431–434 with no limit check |
| 3. Cold fetches chunked | **Not implemented** | One `_alpaca_fetch_bars` call over `min(start)` to `max(end)` (lines 278–285) |

Changing the shared cache touches code the live box also uses, so ADR 0033 says it needs its own careful review. Recommended path for owner decision D11: a new RANGE-002 loader with monthly chunks and a hard feed assertion, leaving `BarCache` alone.

### 2.8 Non-equivalence check (WP0.5)

ADR 0037 decision 5 (`docs/adr/0037-…md:33`) requires rejected patterns to be auto-checked. Only the EAD event-label half is automated (`apps/backend/scripts/check_reference_only_invariant.sh`, `6500c6ad`), as a string check. **No runnable non-equivalence check against RNG-001 exists (NOT-FOUND).** Plan stop condition §9.1 cannot be evaluated by tool today; `governance/nonequivalence.py` would be new and its design needs owner approval.

### 2.9 Order path and P5 (WP5)

| Path | SHA | Notes | Disposition |
|---|---|---|---|
| `apps/backend/app/orders/router.py` | `d228a5bf` | `OrderRouter.submit` is the single entry point (ADR 0002) | **REUSE** |
| `apps/backend/app/risk/engine.py` | `07a92330` | Reference price from limit price, then `req.reference_price`, then latest cached bar close, else `None`; notional gate fails closed with `POSITION_CAP_UNPRICED` | **REUSE**; the executor must pass `reference_price` explicitly |
| `apps/backend/scripts/provision_range_account.py` | `68e9783f` | `provision_paper_account(...)`, idempotent | **WRAP** for WP5.1 (new account, not user 2) |

Isolation checks that will apply: `check_research_plane_isolation.py` (`3b9932b8`) already forbids `app/research/**` from importing `app.orders`, `app.risk`, `app.brokers` or the Alpaca trading SDK, which enforces plan R7 for `app/research/range002/`. The P5 executor under `app/strategies/range002/` falls outside it and under `check_strategy_isolation.sh` (no direct `app.brokers` import), so it must go through `StrategyContext`. Strategies have no `account_id`; they resolve to the owner user's account, which matters for WP5.1.

## 3. CI and conventions

- `ci_classify_changes.py` (`c76ed269`): `apps/backend/app/research/**` and `apps/backend/tests/research/**` match the `backend` pattern, so they trigger the **FULL** backend suite and the ADR 0043 gate. `docs/**` matches no project pattern, so docs-only PRs get LIGHT only.
- Any new `check_*.sh` must be added to `.github/workflows/ci.yml` by hand, which is a global path and forces FULL for every project. Batch it with other CI changes (GITHUB-OPS-001).
- Large artifacts (docx, data, evidence output) go to S3 with a manifest, not Git.
- ADRs: highest number is 0056. 0052 and 0053 are reserved, and 0054 is taken by an unmerged branch, so the next free number is **0057**, to be confirmed against open branches. ADR 0014 = `docs/adr/0014-backtests-primary-eval-ground-truth.md` (`933282c8`), ADR 0033 = `docs/adr/0033-historical-data-integrity.md` (`38ddf8b7`), ADR 0037 = `docs/adr/0037-daily-opportunity-and-event-discovery-governance.md` (`bba19373`). The ADR texts were not compared line by line against the plan's §0A matrix. That remains open under WP0.1.

## 4. Path mapping: plan §3.2 vs repository convention

The plan says to use the repo's convention and record the mapping.

| Plan path | Repo convention / proposed path | Note |
|---|---|---|
| `apps/backend/app/research/range002/` | same | `app/research/<program>/` is established (`gapper_stage0`, `disc_mdq`); does not exist yet |
| `apps/backend/app/strategies/range002/` | same | P5 only |
| `apps/backend/scripts/research/range002/` | same | Directory `scripts/research/range/` exists |
| `tests/research/range002/` | `apps/backend/tests/research/range002/` | Plan omits the `apps/backend/` prefix |
| `docs/research/range002/` | `docs/implementation/evidence/range_002/` for evidence and governance artifacts; frozen spec and design docs alongside | **Approved by owner 2026-10-09** (§0 item 1). `docs/research/` does not exist. Plan v0.4 updated: the five references to `docs/research/range002/` now read `docs/implementation/evidence/range_002/`, and the tests path now reads `apps/backend/tests/research/range002/` |

## 5. Untracked inputs (not in Git)

- `docs/implementation/RANGE-002_Implementation_Plan_v0.4.md` (the plan; file is named `.MD` in the request)
- `Teams/Strategies/RANGE-002_Implementation_Plan_v0.3_Developer_Agent_Enhanced.md`
- `Teams/Strategies/RANGE-002_开盘区间突破延续策略_验证与实施方案_v0.4.docx` (research design v0.4, which **wins on conflicts**)
- `Teams/Strategies/RANGE-001 Failure Analysis & RANGE-002 Proposal.docx`
- `docs/reports/RNG-001_Rejection_Summary_Report_2026-10-09.md`

The research design v0.4 docx has since been **read in full** (text extracted to the session scratchpad only; the docx was not copied or modified) and reconciled; see `governing_reconciliation.md`. Plan action 11.3.2 says to commit the docx; repo policy sends Office binaries to S3 with a manifest, so custody is an open owner item (§6 item 10).

## 6. Open items surfaced by this reconnaissance

| # | Item | Status | Related decision / stop condition |
|---|---|---|---|
| 1 | Path mapping in §4 | **Closed**: approved | WP0.1 |
| 2 | How to meet ADR 0033 for SIP | **Closed**: new RANGE-002 loader (§0 item 2). Variance from design decision 11 wording recorded as C5 | D11, §9.4 |
| 3 | Bootstrap convention | **Open, by design**: module design may proceed; every parameter is an owner decision. Plan wording fix (C11) pending | D06 |
| 4 | Non-equivalence check | **Open**: ADR 0037 review done; criteria proposal awaiting approval (C2). No code yet | D09, WP0.5 |
| 5 | SIP 1-minute historical rights and depth to 2016, delisted coverage | **Open**: not checkable from code; needs vendor and licence confirmation. Blocks P1, not PR 2 | D03, WP1.3, §9.3 |
| 6 | Compare ADR 0014/0033/0037 to the plan's §0A matrix; read the design docx | **Done**, with findings C1–C12 in `governing_reconciliation.md`, all awaiting owner rulings | WP0.1, §9.10 |
| 7 | RANGE-002 entry in `app/research/programs.py` | **Open**: at registration | WP0.7 |
| 8 | Intraday coverage check (`dataset_health` is daily-only) | **New, open** (C4) | WP1.1, WP1.8 |
| 9 | Host for SIP pulls and the RNG-001 replay (Norton blocks the laptop; the laptop is standby-only) | **New, open** (C12) | WP1.2, WP2.6 |
| 10 | Design `.docx` custody (S3 + manifest vs Git) | **New, open** (C10) | github-ops policy |

## 7. Handoff (plan §11.3A)

```
Work package: WP0.1 (no PR opened; nothing committed)
Code and files changed: docs/implementation/evidence/range_002/recon.md and governing_reconciliation.md (new);
  docs/implementation/RANGE-002_Implementation_Plan_v0.4.md (path references only, untracked file); all uncommitted
Source-spec references: research design v0.4 (read in full), Implementation Plan v0.4, ADR 0014 v1.1, ADR 0033, ADR 0037
Data accessed: none
Governance authorization: owner decisions of 2026-10-09 (section 0)
Tests executed: none (documentation only)
Evidence artifacts: this file and governing_reconciliation.md
Risk/safety assessment: no broker credentials touched, no account used, no order capability added
Open decisions or blockers: D01-D18 unresolved; reconciliation findings C1-C12; section 6 items 3-5 and 7-10
Owner rulings on C1-C12: recorded in governing_reconciliation.md section 0 (2026-10-09); WP0.1 approved for documentation-only review and merge
Recommended next action: open the documentation PR, observe the 1-hour walk-away, merge when the required check is green on the exact head; then PR 2 (spec schema, hashing, freeze tool) using synthetic fixtures only, with D01-D18 values unset
```
