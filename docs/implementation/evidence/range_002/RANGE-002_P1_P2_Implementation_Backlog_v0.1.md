# RANGE-002 P1/P2 Technical Implementation Backlog v0.1 (architecture review and readiness)

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. Design and planning only.** Nothing here authorizes P1, a data pull, a vendor or broker call, a host, a credential, an engine or loader implementation, or any strategy computation. No signatures. |
| Date | 2026-10-10 |
| Base | `origin/main` at `d61f313a` (PR 3 Level 1 governance merged). Local-only branch `docs/range002-p1-p2-backlog`; not pushed. |
| Data accessed | None. Local file reading only (docs, repo code, the locally installed `alpaca-py` source for pagination behaviour). No network, no SDK call, no API key read or used, no historical data, no return computed. Two throwaway probes (below) ran only the repo's own offline lint/isolation scripts against a temporary module that was deleted; nothing was committed from them. |
| Sources read | Plan v0.5 (all of WP1-WP6, section 3, section 5, section 8, section 9, section 10, Appendix A); Addendum A1; `recon.md`; `governing_reconciliation.md` rulings; P0 decision sheets; governance and spec code under `apps/backend/app/research/range002/`; `tests/research/range002/governance/{conftest,test_import_lint}.py`; `scripts/check_research_plane_isolation.py`, `scripts/check_marketdata_feed_pinning.sh`, `scripts/ci_classify_changes.py`; reusable components named in `recon.md` section 2; earlier P1 readiness assessment (`git show d967925a:docs/implementation/evidence/range_002/RANGE-002_P1_Readiness_Assessment_v0.1.md`, local branch `docs/range002-p1-readiness`, NOT on main); Execution Boundary design (`git show d1406ec2:...Execution_Boundary_and_Registry_Anchoring_Design_v0.1.md`). |
| Convention | "Recommendation (not a decision)" marks every proposal. Vendor facts are UNKNOWN / TO VERIFY unless readable from this repository. Sizes are S/M/L, no dates. |

How this relates to the earlier P1 readiness assessment (`d967925a`, "RA" below): RA is reused, not duplicated. Its requirement IDs (L-FEED, L-CHUNK, L-IDEMP, L-MAN, L-DEL, V-COV), vendor questions V1-V13, owner questions Q-P1-1..8 and work packages P1-A..N stay authoritative for P1 loader requirements. This document adds what RA did not have: the P2 backlog, the governance-lint conformance analysis, the calendar finding, the spec-traceability table and the READY/BLOCKED classification. Where this document corrects RA, section 2.3 says so.

---

## 0. Summary

1. **Isolation-check answer.** `check_research_plane_isolation.py` forbids only `app.orders`, `app.risk`, `app.brokers`, `app.services.order_router` and the Alpaca *trading* SDK (`alpaca.trading`) for `app/research`, `app/factor_data`, `app/altdata`. The Alpaca *data* SDK (`alpaca.data`), pandas, pyarrow and duckdb are not restricted. Verified by reading and by a probe (a temporary `app/research/range002/data/` module importing all of them: script exit 0, "543 modules"). RA risk B12 is closed.
2. **The binding constraint on layout is not that check but the Level 1 import lint** (`tests/research/range002/governance/test_import_lint.py`). Every public callable in every module under `app/research/range002/` outside `governance/` (data/, engine/, controls/, stats/, audit/ included) must be `@requires_capability` or a reviewed pure entry. A probe confirmed it flags: a public function, a public method of a plain class, and public constants built by a call (`Decimal("0.01")`, `frozenset(...)`). This shapes every module in the backlog (section 1.4).
3. **The guard has no P1/data phase.** `Phase` is {P2, P3A, P3B, P4, P5}; P2 maps only to `REPLAY_RNG001`. The loader/universe/coverage code cannot obtain a capability. They need a reviewed exemption route, an owner/validator ruling (Q-B1).
4. **`eval_calendar` cannot be used as-is for 2016-2025.** It answers session dates only and clamps every query to `FORWARD_START = "2026-07-24"` (`eligible_sessions` returns `[]` for history; `is_eligible_session` is False). A new RANGE-002 calendar module is required, using `pandas_market_calendars` directly with the same fail-closed pattern (section 2.2). RA assumed reuse; this corrects it.
5. **`SpecView` exposes only partitions, exits, p3, exposure and genesis fields.** Signal, fill, costs, risk, execution, controls, stats and gates sections are in the schema but not reachable by engine code. A typed parameter extraction is needed (section 3.0), and many of those sections are `OpenValue` (shape not yet defined).
6. **Traceability found tasks with no owning spec field or decision** (section 5, table T2): control pass criteria for the WP4.0 stage-1 check, time-shuffle and no-information trigger definitions, starting equity, tick-size source, coverage thresholds, loader budget/chunk margin, tie-break inside one exit family, and others. They must get an owner (or be declared plan-fixed constants) before the affected code can be merged.
7. **READY (synthetic only) now:** 23 work packages B-00 to B-22 (section 4; some carry BLOCKED sub-items), most of the P2 engine, statistics, gates and audit-pack kernels, plus the P1 loader core against a fake client. **BLOCKED:** anything touching real data, the vendor, the research host (C12), holdout ingest (boundary B-1), S3 manifest publication, non-equivalence (C2), RNG-001 replay (host), and any real parameter value (D-values unset).
8. **Sequencing caveat for the owner:** plan section 8 places the engine PRs (8+) after the P0 gate and P1. Building them early on synthetic data deviates from that order. It is safe only if nothing merges as "approved engine" before the gate and the code carries no P0 values. Needs an explicit owner ruling (Q-B2).

---

## 1. Architecture review of the planned layout

### 1.1 Modules: exist vs new (against `origin/main` d61f313a)

| Package / module (under `apps/backend/app/research/range002/`) | State | Notes |
|---|---|---|
| `spec/` `schema.py, loader.py, hashing.py, manifest.py, genesis.py, immutable.py, limits.py` | EXISTS (PR 2) | Plan layout lists three; PR 2 added `manifest`, `genesis`, `immutable`, `limits`. Spec is JSON, not YAML (PyYAML undeclared). |
| `governance/` `results_guard, run_registry, exposure_ledger, holdout_token, hashchain, verdict, evidence, spec_adapter, spec_view, model, errors` | EXISTS (PR 3) | `nonequivalence.py` NOT present (blocked by C2). `evidence.audit_pack_header` fixes the first line of every audit pack. `run_registry.record_selection` takes the P3a SelectionRecord. |
| `data/` (`sip_loader, integrity, bar_store, pit_universe, calendar, corp_actions`) | NEW, absent | Proposed additions (Recommendation, not a decision): `fetch_plan.py`, `chunk_journal.py`, `minute_classes.py`, `coverage.py`, `identity_map.py`, `manifest.py`. |
| `engine/` (`or_signal, fill_model, risk_sizer, position_sim, trade_log`; WP2.8 names `portfolio_clock.py`) | NEW, absent | Proposed additions: `params.py` (typed parameter objects), `arming.py`, `exits.py`, `pipeline.py` (two-stage run), `_causality.py` (shared binding checks). |
| `controls/` (`random_entry, naive_orb, time_shuffle`) | NEW, absent | Add `no_information.py` (WP2.5 lists four controls), `rng001_replay.py` (WP2.6). |
| `stats/` (`bootstrap, multiplicity, walk_forward, splits, costs, redundancy, funnel`; `selection.py` in WP3) | NEW, absent | `gates.py` is named in plan section 5.1 but missing from the layout in section 3.2: place it in `stats/`. |
| `audit/` (`audit_pack`) | NEW, absent | Add `sealed_store.py` (WP4.0). |
| `apps/backend/app/strategies/range002/` | NEW, P5 only | Out of scope here. |
| `apps/backend/scripts/research/range002/` | EXISTS: `freeze_spec.py` only | Scripts are not linted by the import lint (known bypass). Keep them thin; no compute in scripts. |
| `apps/backend/tests/research/range002/{spec,governance}/` | EXISTS | New tests mirror: `tests/research/range002/{data,engine,controls,stats,audit}/`. Reuse `tests/research/range002/spec/_fixtures.py` and `governance/conftest.py` (`load_synthetic_view`, `new_registry`, `SIGNED_LEDGER`, `forge_guard_view`). |

Naming and path conventions: snake_case modules, one concern each, tests as `test_<module>.py`, evidence under `docs/implementation/evidence/range_002/`, ADR numbering untouched (next free was 0057 per recon). No new top-level package outside `app/research/range002/`.

### 1.2 Research-plane isolation checks: the questions asked

Read `scripts/check_research_plane_isolation.py` in full.

| Question | Answer |
|---|---|
| Does it allow the Alpaca data SDK under `app/research/range002`? | **Yes.** Forbidden for research roots: `app.orders`, `app.risk`, `app.brokers`, `app.services.order_router`, `alpaca.trading`. `alpaca.data.*` is explicitly permitted by design (docstring). `from alpaca import trading` is also caught (the `from` names are expanded to `alpaca.trading`). |
| pandas / pyarrow / duckdb? | **Not checked at all.** Allowed. All three are declared dependencies (pandas 2.3.3, pyarrow 19.0.1; duckdb in pyproject). |
| Transitivity | AST import graph, bounded to the plane's own packages (`app.research`, `app.factor_data`, `app.altdata`). Hops into other packages (e.g. `app.validation`, `app.market_data`, `app.strategies`) are leaves, not followed. So reusing `app.validation.security_lineage` is fine for this check. |
| What it does NOT prevent | (a) Importing `app.market_data.bar_cache` (the IEX-hardcoded cache): not forbidden by this script. Needs a RANGE-002-specific test (below). (b) Reading credentials from the environment: that is `check_no_env_credentials.sh`. (c) A SIP-labelled file written from an IEX call: `check_marketdata_feed_pinning.sh` only requires an explicit non-None `feed=` on request constructors under `apps/backend/app`, `apps/backend/scripts`, `scripts/research`. |
| Consequence for R7 | `app.risk` is unreachable, so the research risk sizer is necessarily new code (it cannot reuse `app.risk`). This is intended. |
| Property B (order path must not import MDQ archive) | Unaffected by range002. P5 executor importing `engine/` is not forbidden by this script; `check_strategy_isolation.sh` is the relevant check there. |

Recommendations (not decisions) for the loader PR, tests only (no new CI script, so no `ci.yml` edit): `test_data_package_imports` asserting no import of `app.market_data.bar_cache`, `app.orders`, `app.risk`, `app.brokers`, no `os.environ` credential read, every `StockBarsRequest(...)` has a literal feed constant `"sip"` via a module constant (so the feed-pinning script passes and a static test can compare), and no token `iex` reachable (RA L-FEED-1/4).

### 1.3 CI classification impact

`ci_classify_changes.py`: `apps/backend/**` (source and tests), `scripts/**`, `deploy/**` are the `backend` project. Every PR adding or changing `app/research/range002/**` or its tests flags **backend FULL** (pytest and coverage) in addition to LIGHT (ruff, mypy, fast invariants including `check_research_plane_isolation.py` and `check_marketdata_feed_pinning.sh`). Docs-only PRs (including this one) are LIGHT only. Editing `.github/workflows/ci.yml`, root `pyproject.toml`, or `constraints/**` flags **every** project.

Implications:
1. Cost: batch per GITHUB-OPS-001. Section 4.4 groups the READY packages into 8 review-ready PRs (versus about 20 plan PRs); each is one FULL run, ideally 1-3 pushes. Recommendation (not a decision): the owner approves the regrouping since plan PR numbers are cited by the decision sheets.
2. New dependencies: `hypothesis` is NOT installed or declared (checked); `numpy` is only transitive (via pandas; 2.2.6 installed). Declaring either touches `constraints/**` (GLOBAL, all projects FULL). Recommendation: add no dependencies. Property tests use seeded `random.Random` loops; bootstrap uses stdlib `random` or numpy-as-transitive, with the choice flagged to the validator (section 3, bootstrap). Declaring numpy explicitly would be a separate owner/CI decision, batched with other manifest changes.
3. A coverage gate for range002 compute modules (like `check_risk_coverage.py`) would need a new script and a `ci.yml` edit. Recommendation: defer, batch with any other CI change; meanwhile require the coverage figure in the PR description.
4. FULL runtime: bootstrap and property tests must use small, seeded repetition counts in unit tests (for example 200 reps) and keep the 10,000-rep runs for governed runs only.

### 1.4 The guard-coverage proof: how every compute entry point uses the capability

What the code actually enforces (read from `results_guard.py` and the lint):

- `authorize(...)` is the only issuer. It needs a frozen, signed `GuardSpecView`, an owner-approved committed governance manifest, a registry, a signed exposure ledger, an OPEN registry row, and phase/partition authorization. `Phase.P2` is allowed only on `Partition.REPLAY_RNG001` (range inside the R2 window); no phase exists for P1. Governed integration tests with synthetic specs therefore go through the existing test seams (`load_synthetic_view`, `new_registry`, patched `_MANIFEST_PATH` in `governance/conftest.py`); they cannot run through the production manifest until the owner approves a real one.
- `@requires_capability` requires a parameter literally named `capability`; at call time `require_capability` verifies a genuine `ResultsCapability` (weak-table identity) whose run is still OPEN in the registry (a registry read on every call).
- The decorator does **not** check that the capability matches the inputs (spec hash of the parameters, partition, date range). A capability for spec A would run an engine fed spec B's parameters. Engine entry points must therefore also bind: `capability.spec_sha256 == params.spec_sha256`, `capability.date_range.contains(requested_range)`, and `capability.phase` in the entry point's allowed phases. Recommendation (not a decision): one private helper in `engine/_causality.py` reading the capability's public slots (`spec_sha256, phase, partition, date_range, citable`). The lint forbids naming the `ResultsCapability` type (R-C), so annotate the parameter `capability: object`.
- `bar_store` reads are the data-plane analogue: a read of bars for any date range must itself require a capability whose `date_range` contains the request, so a holdout month cannot be read by an ungated caller. (Holdout bytes additionally sit in broker-owned storage under boundary B-1; that is the stronger control.)

Import-lint rules that shape the design (verified by a probe):

| Rule | Consequence for module design |
|---|---|
| R-A: every public callable (functions, public methods of every class, lambdas, dunders beyond a safe set) is gated, or listed in `REVIEWED_PURE` (a reviewed edit to `test_import_lint.py`) AND in the module's literal `PURE_FUNCTIONS` tuple | Domain types are frozen dataclasses/enums with **no public methods**. Logic lives in module-level functions. Compute kernels are underscore-private (`_walk_bar`); a small number of coarse public entry points are gated. Private kernels are still unit-testable by importing the underscore name. |
| R-A2: no public constant bound by a call, lambda, comprehension | `TICK = Decimal("0.01")`, `frozenset(...)`, `dict(...)` are flagged. Use literals, tuples, `StrEnum`, or underscore names. |
| REVIEWED_PURE_IO: file I/O in a public pure function is accepted only if listed by exact name with its I/O described | Loader/manifest/coverage public functions need individually reviewed entries. Network I/O (SDK) is not detected by the lint but must be described in the same review entry. |
| R-B: no underscore-private name of a governance module | Use only public `results_guard` names. |
| R-C: no reference to `ResultsCapability` outside governance | Annotate `capability: object`. |
| R-E: no `__wrapped__`/`inspect.unwrap` | Tests must not unwrap the decorator to call raw entry points; they call private kernels instead. |
| Stale-entry test | Every REVIEWED entry must exist by exact qualified name; removing/renaming a function without editing the list fails CI. |

Performance consequence: each gated call reads the registry. Gate **coarse** entry points (one `run_*` per phase step; one `read_bars` per symbol-month or per run) and never gate per-bar or per-trade functions.

**Per-PR guard-coverage proof (required by plan section 4 for every PR adding code under `engine/ stats/ controls/ audit/`).** Concrete checklist, Recommendation (not a decision) as a shared test harness `tests/research/range002/_guard_harness.py` (package B-00):
1. Lint non-vacuous: the real-tree lint passes AND a test strips the decorator from a copy of the new module source (via `lint_source`) and asserts it is flagged; plus an `EXPECTED_GATED` list per module that must equal the set of attributes with `__requires_capability__` (deleting a decorator or adding an unlisted public function fails).
2. Negative tests per gated entry point, generated by the harness from `EXPECTED_GATED`: no capability; `None`; look-alike object; `copy`/`pickle` of a real capability (raises); a capability whose run is closed; a capability for a different spec hash; a capability for a different partition/date range; an entry point called with inputs outside `capability.date_range`.
3. Enumeration test: `inspect` plus AST list every public name of each compute module and fail if one is neither gated nor in the reviewed pure list.
4. Look-ahead/determinism tests for the new kernels (section 6).
Reviewers reject the PR without this evidence.

Open design question for the owner/validator (Q-B1): `data/` (loader, universe, coverage) is under the lint scope but has no phase. Options: (a) keep `data/` under `range002/` with a small number of reviewed pure(-IO) entries, each narrowly described, plus the holdout partition guard in `bar_store`; (b) a sibling package outside the lint scope (loses the guard-coverage proof for data code); (c) add a `P1`/data-acquisition phase to `governance` (a PR 3 change, with registry and attempt-budget semantics to decide). Recommendation (not a decision): (a), with data public surface kept to about six functions, because acquiring data produces no returns and the dangerous act (reading holdout data) is covered by `bar_store` gating and boundary B-1.

Probe evidence (not committed): lint output on a temporary `data/probe_tmp.py` flagged `TICK`, `NAMES`, `load_month`, `Bars.slice`; isolation script passed with `alpaca.data`, pandas, pyarrow, duckdb imports.

---

## 2. SIP one-minute loader and PIT universe: design review (design only)

RA section 4 holds the full loader requirement set. This section finalizes the architecture, adds what RA lacked, and defines work packages, fixtures and acceptance tests.

### 2.1 Architecture (finalized, design only)

```
fetch_plan  (spec + PIT universe -> ordered chunk list: (symbol batch, month, partition))
   |
chunk_journal (append-only chunk states: PENDING FETCHING FETCHED VERIFIED QUARANTINED FAILED NOT_FETCHED)
   |
sip_loader  (injected client; explicit feed constant; monthly chunks; pagination to exhaustion)
   |  raw response bytes -> atomic write -> sha256
integrity   (chunk checks L-CHUNK-6; truncation detectors L-CHUNK-3/4/5)
   |
bar_store   (normalized parquet, per symbol-month; basis tag; gated reads by capability.date_range)
   |
minute_classes (PRESENT NO_TRADE_MINUTE DATA_GAP HALT OUT_OF_LIFETIME NOT_FETCHED; pure function)
   |
coverage    (independent re-derivation from stored data + manifest + PIT population; return-blind schema)
manifest    (run-local data_manifest.json; canonical JSON; SHA-256; verifier)
```

Design rules (Recommendation, not a decision):
- **Client injection.** The loader receives an already-constructed client object; it never reads credentials, environment variables or files for them. This keeps `check_no_env_credentials.sh` and R7 trivially true, and makes fakes the normal test path. A thin script on the approved host builds the real client (out of scope).
- **Explicit feed.** One module constant `FEED = "sip"` passed as `feed=` on every request constructor; loader constructor takes no feed parameter (RA L-FEED-1).
- **SDK pagination (read from the locally installed alpaca-py 0.44.0, `alpaca/common/rest.py::_get_marketdata`):** the SDK loops on `next_page_token` and stops early only when a caller-supplied `limit` is reached. `BarCache` sets `limit=10000`, which is the truncation mechanism of ADR 0033. The loader must pass **no `limit`** and still treat any response whose size equals a vendor page cap (V6) as suspect, because pagination behaviour under the pinned version range (`>=0.30,<1.0`) is a PR-time verification, not an assumption.
- **No `.empty` markers** (ADR 0033 point 1): absence is a classified record, never a marker file.
- **Look-ahead-safe fetch window:** fetch only months in which a name is a PIT universe member (RA 4.2).
- **Atomic writes and idempotent resume** exactly as RA L-IDEMP-1..6, including a finite retry budget and a spec-declared money/byte/request cap (no field exists; see T2 orphans).
- **Holdout partition split:** loader takes `partition` from the frozen spec's windows (never hardcoded 2022-01-01). A research-principal loader refuses any chunk whose end date falls in the holdout window; holdout ingest is a separate broker-principal mode, BLOCKED on boundary B-1 and Q-P1-3.

### 2.2 Reuse versus new code (with paths)

| Component | Path | Disposition | Reason |
|---|---|---|---|
| FactorDataStore (DuckDB; `permaticker_asof, trading_days, get_prices_many, price_date_bounds, dollar_volume_universe`) | `apps/backend/app/factor_data/store.py` | REUSE | Survivorship-free daily layer for ADV/price. Reads real data only after P0; tests use a tiny synthetic DuckDB file. |
| `universe_asof(store, as_of, n, lookback_days)` | `apps/backend/app/factor_data/universe.py` | WRAP | Returns tickers, not permatickers; not monthly; raises `UniverseUnavailable` (keep that fail-closed behaviour). Wrap into `pit_universe.build_month(...)` that also returns permaticker, ADV, price, rank. |
| `resolve_lineage`, `assess_universe`, `LineageRefusal`, `SessionLineageFilter` | `apps/backend/app/validation/security_lineage.py` | REUSE | Ticker-reuse refusal; refusals become exclusions with reason codes. Governed `LINEAGE_*` parameters live in that module, not the spec (see T2 note). |
| `FactorStoreSecurityIdentityResolver.resolve` | `apps/backend/app/universe/security_identity.py` | REUSE | Ticker/date to permanent id. The reverse join (permaticker + interval -> vendor ticker) is NOT in the repo: new `identity_map.py`. |
| `dataset_health` | `apps/backend/app/factor_data/evidence.py` | REUSE (daily layer only) | Intraday coverage is the new validator (ruling C4). |
| `canonical_json`, `file_sha256` | `apps/backend/app/validation/governed_corpus.py`; and `range002/spec/hashing.py` (`canonical_json, content_sha256, file_sha256, loads_strict`) | REUSE | Prefer the range002 spec hashing module already on main. |
| Hash-chained append-only file | `range002/governance/hashchain.py` | REUSE concept for chunk journal | Importing a governance module from data/ is allowed (public names only); RA left this as a recommendation. |
| `fetch_session_bars(client, universe, session, feed)` | `apps/backend/app/research/capture/collector.py` | REFERENCE | One session, 04:00-16:00 incl. premarket, no pagination/truncation handling of its own, return-bearing path for MDQ capture. Copy the request-construction shape only. |
| Funnel pattern `build_funnel_record`, `FunnelRecord`, `Exclusion` | `apps/backend/app/research/gapper_stage0/funnel.py` | REFERENCE | Reason-coded exclusions for `stats/funnel.py` and coverage denominators. |
| Session calendar date logic | `apps/backend/app/validation/eval_calendar.py` | **DO NOT USE for history** | Clamped to `FORWARD_START` (2026-07-24), dates only. Reuse the fail-closed pattern, not the functions. |
| `MarketSession`, `market_hours.py` | `app/market/session.py`, `app/services/market_hours.py` | DO-NOT-USE | Silent fallback / no holidays (recon). |
| `BarCache` | `app/market_data/bar_cache.py` | DO-NOT-USE | Hardcoded IEX at line 428, `limit=10000`, feed not in key. Not modified (ruling C5). |
| `app/market_data/sip/*` | | REFERENCE (feed identity checks) | Live quote plane only. |
| Block bootstrap functions `block_bootstrap_ci`, `cluster_bootstrap_ci`, `paired_sharpe_diff_ci` | `apps/backend/app/factor_data/evidence.py` | REFERENCE / WRAP of the recentered-null p-value logic | Circular fixed-block, daily returns, Sharpe-oriented; not day-clustered trade R. |
| `block_bootstrap_delta_ci` | `apps/backend/app/services/market_projection/validate.py` | REFERENCE | Geometric (stationary) blocks, `BLOCK_LEN=10`. Do not import from `app.services` (not a research module); copy the resampler shape. |
| Gate pattern | `apps/backend/scripts/range_5c_gate.py`, `app/research/promotion/gate.py` | REFERENCE / WRAP | Pure `evaluate` with thresholds object. |
| Sealed performance pattern | `apps/backend/app/validation/forward_window.py` (`preflight`, `seal_performance`) | REFERENCE | OPEN/SEALED split for WP4.0. |
| Registry / selection record / audit-pack header | `range002/governance/{run_registry,evidence}.py` | REUSE (already on main) | `record_selection`, `audit_pack_header`, `Verdict`. |
| Design latch | `apps/backend/app/research/gapper_stage0/design_latch.py` | REFERENCE | Not needed beyond what `spec/manifest.py` provides. |
| RNG-001 scripts | `apps/backend/scripts/range_evidence.py`, `range_5c_gate.py`, `app/strategies/backtester.py`, `scripts/research/range/*` | WRAP for replay only; DO-NOT-USE as code for RANGE-002 | Per recon. |
| Paper account provisioning | `apps/backend/scripts/provision_range_account.py` | WRAP (P5, WP5.1) | Out of scope here. |

### 2.3 Corrections to RA

1. B12 (isolation check behaviour for the data SDK): closed, see section 1.2.
2. RA assumed `eval_calendar` is the calendar base. It is a pattern only (FORWARD_START clamp, date-level). New `data/calendar.py` required (WP-L1 below).
3. RA did not note that the lint scope covers `data/`, nor the missing data phase (section 1.4).
4. RA's loader requirement L-MAN-5 (S3 publication) remains untestable: verified again that `manifests/s3/` does not exist and there is no S3 manifest script under `scripts/` or `apps/backend/scripts/` (found only `adr0042_make_manifest.py` and `adr0043_dbox_freeze_manifest.py`, both for other programs).

### 2.4 Work packages (each: scope, acceptance tests, fixtures)

Sizes S/M/L. "Fakes" means an in-memory client and synthetic DuckDB/parquet generated by test code. IDs map to RA requirements.

| ID | Package | Module(s) | Acceptance tests (synthetic) | Size |
|---|---|---|---|---|
| L1 | Calendar: session open/close in ET and UTC, early closes, DST, holidays; fail-closed if the calendar library is missing | `data/calendar.py` | DST start (second Sunday of March) and end (first Sunday of November) weeks for several years: 09:30 ET maps to 13:30 UTC vs 14:30 UTC correctly, 10:00 and 15:55 stay 10:00/15:55 ET; day after Thanksgiving and Christmas Eve early close at 13:00 ET; July 3 early close when applicable; a market-closure day (national mourning) is not a session; weekend month-ends; floor-free (2016-01-04 returns a session, unlike `eligible_sessions`); library import failure raises a named error, never a curated-list fallback. Expected values written independently (rule table in the test) and reviewed by a second person. | S |
| L2 | Fake vendor client + synthetic bar generator | `tests/research/range002/data/_fakes.py` | Deterministic 1-minute bars with controllable gaps, pages, continuation tokens, rate-limit and entitlement errors, restatements, wrong-feed label, start- and end-stamped conventions. | M |
| L3 | Fetch planner | `data/fetch_plan.py` | Property: for any batch and month, `symbols * sessions * 390 <= page_cap * margin` or the planner splits (RA L-CHUNK-1); same spec + universe gives identical plan hash; fetch only member months; holdout-end chunks refused for the research principal. | M |
| L4 | Loader core: pagination to exhaustion, exactly-page-limit suspicion, truncation detectors | `data/sip_loader.py`, `data/integrity.py` | Fixtures: **truncated page** (exactly 10,000 rows, 9,999, 10,001 over two pages, truncation ending mid-session -> later sessions `NOT_FETCHED`, no empty marker); hidden page 2 -> failure; non-monotonic timestamps; wrong-feed label -> raises and writes nothing; entitlement error -> `FAILED`, no fallback feed. | L |
| L5 | Chunk journal, atomic writes, resume | `data/chunk_journal.py` | Kill after each transition: resumed dataset bytes equal an uninterrupted run; second run makes zero vendor calls; restated chunk keeps both snapshots plus `RESTATEMENT` event; bounded backoff; tiny cap stops resumably. | L |
| L6 | Manifest writer/verifier (run-local) | `data/manifest.py` | Hash stability (key order/whitespace); tamper tests (flip byte, delete file, add file); no field matches credential patterns; no return-like columns. Publication to S3 is out of scope (tooling absent). | M |
| L7 | Minute classification | `data/minute_classes.py` | Thin minute with reconciling daily volume -> `NO_TRADE_MINUTE`; same minute in a truncated chunk -> `DATA_GAP`; daily volume exceeds bar sum -> `DATA_GAP`; halt only with positive evidence; insufficient evidence defaults to `DATA_GAP`; pure and deterministic; counts split by year, month and the 09:30-10:00 window. Tolerance injected (no value chosen). | M |
| L8 | Intraday coverage validator (ruling C4) | `data/coverage.py` | Removing a symbol's data lowers coverage and does not shrink the denominator; golden-file report on a synthetic dataset; exclusions listed by reason and bounded; output schema denylist (no return/pnl/win/hit/profit names); missing input or manifest mismatch aborts with no partial output; below-threshold -> `STOP_ESCALATE`. **Empty-month** fixture: a month with zero rows for a member symbol is `NOT_FETCHED` or `VENDOR_NO_HISTORY`, never silently covered. **Vendor-gap** fixture: a mid-month multi-day hole lowers coverage and is reported under `DATA_GAP`. | M |
| L9 | Identity map (permaticker, interval -> vendor ticker) and PIT universe monthly rebuild | `data/identity_map.py`, `data/pit_universe.py` | **Ticker reuse** (ticker T is security A until 2018 and security B from 2019: two intervals, two permatickers, never one series); rename (one permaticker, two tickers, stitched); **delisted symbol** (included before delisting, no requests beyond the last trading day, no `DATA_GAP` after, `OUT_OF_LIFETIME`); unmapped vendor ticker -> `IDENTITY_UNMAPPED` counted; `LineageRefusal` -> exclusion with reason; look-ahead test: perturbing daily data dated after the prior trading day never changes a month's universe; deterministic ordering (ADV ties broken by permaticker). Uses a synthetic DuckDB `FactorDataStore`. | L |
| L10 | Corporate-action basis handling | `data/corp_actions.py` | Basis tag on every table; join of raw intraday with `closeadj` refused; split-day and spinoff-day fixtures (Sharadar `open/close` not spinoff-adjusted); OR, stop and fill prices on one basis. Vendor adjustment semantics (V9) UNKNOWN: the tag type is built, the real mapping is BLOCKED. | M |
| L11 | Partition-aware ingest (broker mode) | `data/sip_loader.py` (mode) | Research principal cannot run HOLDOUT; spanning request split or refused; directory-permission tests on Linux runner only. | M |
| L12 | Real vendor metadata check, real pulls, real coverage report | scripts on approved host | n/a | see section 4 (BLOCKED) |

Fixture list (all synthetic, generated in test code; none stored from a vendor): truncated page; empty month; DST day (March and November); half day; holiday (and national-mourning closure); delisted symbol; ticker reuse; rename; vendor gap; exact-page-limit page; hidden second page; wrong-feed label; start-stamped vs end-stamped bars; restated chunk; thin-minute with and without volume reconciliation; split day; spinoff day; unmapped vendor ticker; tampered manifest (byte flip, missing file, extra file); crash-at-each-journal-step.

---

## 3. Strategy implementation plan: module-level tasks

### 3.0 Cross-cutting design

- **Typed parameter objects, never hardcoded P0 values.** `engine/params.py` (frozen dataclasses: `OrParams, ArmingParams, FillParams, SizingParams, ExitParams, CostParams, PortfolioParams, ControlParams, StatsParams, GateParams`) and a single adapter `spec`-side function that builds them from a loaded frozen spec. Today `SpecView` does not expose `signal/fill/costs/risk/execution/controls/stats/gates` (see section 0 item 5). Recommendation (not a decision): extend `SpecView` (a small change to `spec/loader.py`; the content hash is unaffected) so the adapter can read those sections; until then tests construct the dataclasses from a synthetic values factory. Many fields are `OpenValue` (`signal.or_completeness_rule, fill.slippage_model, fill.halt_policy, costs.components, execution.stop_protection_policy/tie_break/order_reservation_policy, controls.random_entry.invalid_draw_policy, controls.naive_orb.definition, stats.hypothesis_family, stats.regime.*, p3.criteria, gates.trade_unit/yearly/win_rate/max_dd`). Their shapes are owner decisions; code defines the minimal shape it needs as a **proposal** and the owner confirms or replaces it. Until then the adapter cannot be written for real values (BLOCKED), but kernels and tests proceed (READY).
- **Capability binding** per section 1.4: each phase-level entry point is `@requires_capability`, binds spec hash/partition/date range, and delegates to private kernels.
- **Determinism:** no `set`/`dict` iteration-order dependence (sort by permaticker, then time); all randomness from one seeded generator per labelled stream, derived from `stats.bootstrap.seed`/`controls.random_entry.seed` plus a fixed label (derivation rule has no owning field: T2 orphan O-14); decimals or integer ticks for prices; no wall clock.
- **Causality:** every function that makes a decision takes `decision_at` and receives only data with `available_at <= decision_at` (types enforce it: a `VisibleBars` view built by one function).
- Public exposure per module: see section 1.4 (gated coarse entry, private kernels, no public methods).

For each component: path, API sketch, spec inputs, tests, P0 dependencies, reuse, size, risks.

**S1. OR signal** - `engine/or_signal.py`. API: `_compute_or(bars: VisibleBars, rule: CompletenessRule, min_width_ticks: int, tick: TickSizer) -> OpeningRange | Ineligible`; `_entry_trigger(or_: OpeningRange, tick_offset: int, tick: TickSizer) -> Decimal`. OR window 09:30:00-09:59:59 frozen at 10:00:00; immutable object with `window_end, finalized_at, available_at`; any bar with `bar_start >= 10:00` raises; completeness counts only `DATA_GAP` (NO_TRADE_MINUTE is not a gap); width > 0 and >= min. Spec: `signal.or_start/or_end` (fixed), `signal.or_completeness_rule` (D05), `signal.min_or_width_ticks` (D05), `signal.tick_offset` (fixed 1), `data.bar_timestamp`/`execution.bar_timestamp_convention` (D14), `execution.vendor_delay_ms` (D14). Tests: 09:59:59/10:00:00 boundary; start- vs end-stamped normalization; late 09:59 bar delays decision; zero-width; missing minute classes; shifting any bar at or after 10:00 never changes the OR (look-ahead). Reuse: new. Size M. Risk: timestamp convention unverified (F4); completeness rule shape open.

**S2. Entry and simulated arming** - `engine/arming.py`. API: `_arm(or_: OpeningRange, latency: Latency, policy: CrossedBeforeArmPolicy, bars: Iterator[VisibleBar]) -> ArmingOutcome` implementing plan WP2.1A (`decision_at = max(or_window_end, last_or_bar_available_at)`, `armed_at = decision_at + submit + ack`, `first_active_bar`, `crossed_before_arm` including the bar containing `armed_at`) and all three policies (SKIP, MARKET_AT_NEXT_ACTIVE_BAR_OPEN, REQUIRE_RETRACE) selected by the spec. First trigger only, one entry per symbol-day, window 10:00:00-14:59:59, no re-entry. Spec: `execution.submit_latency_ms, ack_latency_ms, vendor_delay_ms, crossed_before_arm_policy, order_type`; `signal.entry_window, max_entries_per_symbol_day`. Tests: breakout in the 10:00 bar with latency 0 vs 2 s; breakout before arming then retrace; gap above trigger at first active bar; duplicate trigger ignored; re-entry after stop ignored; no order timestamped before data availability (property). Reuse: new. Size M. Depends on D14. Risk: policy choice is outcome-relevant; implement all three, report sensitivity (plan WP2.1A).

**S3. Fill model** - `engine/fill_model.py`. API: `_fill_entry(bar, trigger, slippage: SlippageModel, same_bar: ...) -> Fill | NoFill`, `_fill_stop`, `_fill_target`, `_fill_eod(intent_time, bars, lead, latency)`. Rules exactly as plan WP2.2 (gap-through fills at bar open +/- slippage; stop-gap fills at open; target never credited in the entry bar; entry and stop in one bar = entry then stop with `path_ambiguous`; EOD fill = first bar starting at or after `intent + latency`; halt -> `EXIT_UNAVAILABLE`). Spec: `fill.slippage_model` (D05, shape open), `fill.same_bar_policy` (fixed `worst_case`), `fill.halt_policy` (D05), `costs.accounting_mode` (D15; under all-in no extra slippage), `exit.eod_flat`, `exit.halfday_offset_min`, `execution.eod_lead_s`. Tests: each table row; EOD fill cannot come from a bar that started before the intent; participation cap partial fill (unfilled remainder cancelled); `path_ambiguous` share reporting. Reuse: new. Size M. Risk: double-counting slippage versus all-in bps (D15 must be signed first); halt data availability unknown.

**S4. Risk sizer** - `engine/risk_sizer.py`. API: `_size(est_entry, stop, budget, caps: Caps, state: PortfolioState) -> Sized | Skipped(reason)`; `_post_fill(avg_fill, stop, qty, tol) -> PostFill` (R_fill <= 0 -> immediate exit and log). All limits rounded down to whole non-negative shares; zero -> skip (never force one share); logs R_pre, R_fill, budget, binding constraint. Spec: `risk.per_trade_pct, per_name_cap, gross_cap, max_concurrent, daily_loss_limit, max_participation, fill_risk_tolerance` (all D05 j), plus starting equity (NO FIELD, orphan O-3). Tests: each cap binding; participation cap; R_fill <= 0 after adverse fill; property: qty * R_pre <= budget; rounding at 1 share. Reuse: new (cannot import `app.risk`). Size M. Risk: units of `daily_loss_limit` and caps are undefined (percent vs currency).

**S5. Exit engine E1-E4** - `engine/exits.py`. API: `_step_exit(state: ExitState, bar: VisibleBar, cfg: ExitConfig) -> ExitState` (pure state machine, one per candidate) for families `time` (E1), `fixed_r` (E2: limit at fill + k*R_fill active from the bar after entry), `trailing` (E3: activation on completed-bar close >= fill + 1R; new stop effective next bar; trail = max(previous stop, highest completed-bar close since entry - t*R_fill), never down; old stop governs the activation bar), `scale_out` (E4: 50% limit at +1R from the bar after entry; odd counts round the scaled quantity down; 1 share = remainder-only; partial fill of the scale order; remainder to EOD or trail). Same-bar stop-and-target: stop, `path_ambiguous`. One entry = one trade; net R = total net P&L of all exit fills / (entry qty * R_fill). Spec: `exits.candidates[*].{id,family,params}` (D19; param vocabulary open), `exits.complexity_order`, `exit.stop` (fixed `or_low`), `exit.eod_flat`. Runs all K candidates from one entry stream, portfolio constraints per candidate (S6). Tests (plan WP2.7): activation on a bar that also hits the old stop; trail never decreases; completed closes only; odd and 1-share scale-out; partial scale fill; two-fill net-R equals hand calculation; target not credited in entry bar; spec with more than 8 candidates or unknown family rejected (already enforced by `spec/schema.py`; engine re-asserts). Reuse: new. Size L. Risk: parameter vocabulary per family undefined (T2 O-9); complexity order is per family only.

**S6. Position sim and portfolio scheduler** - `engine/position_sim.py`, `engine/portfolio_clock.py`. API: `_run_day(events: Iterator[Event], params: PortfolioParams, cfg: ExitConfig) -> DayResult`; a single merged chronological event stream across symbols (OR freeze, eligibility, order submit/ack/arm, partial fills, protective stop, exits, risk state, intraday equity); same-timestamp priority by a frozen, return-independent rule; reserve cash/risk at submission, release on cancel/expiry/fill; end-of-day assertion that no position remains. Counters: `signal, submitted, filled, blocked, cancelled, exit, missed_due_to_capital`, reconciled with the funnel. Spec: `execution.tie_break, order_reservation_policy` (D14), `risk.*` (D05), `gates.trade_unit` (D18). Tests: two-symbol timestamp collision gives identical allocations on rerun; shifting future prices never changes an order scheduled before the shift (look-ahead); symbol-by-symbol-then-merge is impossible by API (single loop); concurrency, gross-exposure, daily-loss mid-day; determinism (byte-identical `trades.csv` hash). Reuse: new. Size L. Risk: the largest defect surface; independent hand-built fixtures required.

**S7. Costs** - `stats/costs.py`. API: `_apply_costs(trade, mode: CostMode, bps: float, components) -> NetTrade`; base 5 and stress 15 bps per side; all-in as P&L debit with a cost bridge labelling price adjustments vs debits (D15 recommendation) or itemized additive. Spec: `costs.base_bps_per_side, stress_bps_per_side` (fixed), `costs.accounting_mode, components` (D15). Tests: no double counting; stress is exactly 15; component sum equals all-in. Size S. Risk: mode unsigned.

**S8. Trade log** - `engine/trade_log.py`. Row schema as plan section 7 (`trades.csv`: symbol, permaticker, date, OR high/low, trigger, entry time/price, R_pre, R_fill, qty, all exit fills, costs by component, net P&L, net R, `path_ambiguous`, exit candidate id); stable column order, canonical number formatting, hashed. Size S.

**S9. Controls** - `controls/random_entry.py, naive_orb.py, time_shuffle.py, no_information.py`. Random entry: assignment population defined causally at 10:00, randomized among predeclared feasible instants with `R_pre > 0` under the identical OR-low stop, same portfolio constraints, costs and causal order activation; invalid draws counted as `NOT_EXECUTABLE`, denominator preserved, redraw procedure frozen; no use of a future cross of OR high. Naive ORB: OR high touch, no tick offset, same exits. Time-shuffle: entry minutes permuted across days by a frozen causal procedure. No-information trigger: random price level independent of future bars with comparable risk/cost distribution. Spec: `controls.random_entry.{repetitions,seed,invalid_draw_policy}` (D06), `controls.naive_orb.definition` (D13/D06). Time-shuffle and no-information definitions and the stage-1 pass criteria have NO owning field (orphans O-10..O-12). Tests (WP2.7A): synthetic uptrend, downtrend and non-breaking day; control never qualifies an observation by a future cross; infeasible draw accounting; reproducible seeds; paired unit at day level. Size L. Risk: biased controls manufacture alpha (R16).

**S10. Selection** - `stats/selection.py`. API: `select_exit(candidate_results, rule) -> SelectionRecord` (pure, deterministic): eligibility (min trades, PF > 1 at base cost, both from `exits.selection.eligibility`), score = one-sided lower bound of mean net R per trade from the day-clustered bootstrap, pick highest eligible, within `tie_tolerance_r` pick lower complexity rank, STOP if none eligible; raises on a candidate outside the frozen set. `max_stat_bootstrap(candidate_day_R, params)`: resample trading days jointly for all K candidates, take the maximum studentized mean net R per resample, compare the observed maximum to that distribution; output the selection-aware p-value. Record includes selected id or STOP, scores, eligibility, tie decision, p-value, input hashes, `run_id`, `spec_sha256` (required by `RunRegistry.record_selection`), written before unsealing. Spec: `exits.selection.{score,tie_tolerance_r,eligibility,stop_test}`, `exits.complexity_order`, `exits.candidates`, `stats.bootstrap.*`, `p3.criteria` (D17 alpha). Tests: determinism; tolerance and complexity order; STOP when none eligible; raises on unknown candidate; permutation invariance of candidate order; null calibration on synthetic iid zero-mean R (rejection rate near alpha, simulated data only, allowed by D06 sheet); max-stat is conservative relative to the best candidate's naive p-value. Size L. Risk: studentization details and the within-family tie rule are undefined (O-8, O-9); the validator must review.

**S11. Day-clustered block bootstrap** - `stats/bootstrap.py`. API: `_day_clusters(trades) -> list[DayCluster]`; `_resample(days, method, block, rng) -> list[int]` for the three D06 options (stationary geometric blocks, circular fixed blocks, iid days) behind one interface chosen by `stats.bootstrap.method`; outputs one-sided p-value and lower bound for mean net R per trade and for the paired G5 difference (mean net R of RANGE-002 trades minus mean net R of random-entry trades on the resampled days; days with RANGE-002 trades but no valid draw are counted and reported). Spec: `stats.bootstrap.{method,cluster,block_len,reps,ci_type,confidence_level,seed}` (D06; `cluster` fixed `trading_day`), `stats.alpha_one_sided`. The method is UNSET (ruling C11); implementing all three keeps the choice a spec value. Tests: each resampler is deterministic per seed; block-length semantics; all trades of a day move together; null calibration; Holm-compatible p-value definition (share of resampled means <= 0 under the recentered null). Reuse: REFERENCE only (section 2.2). Size L. Risk: randomness stream (stdlib `random` is stable across Python versions for the used calls; numpy Generator streams are not guaranteed across versions: record versions in the audit pack).

**S12. Multiplicity** - `stats/multiplicity.py`: `_holm(pvals, alpha)` and `_fixed_sequence(pvals, alpha)` selected by `stats.adjustment`, reporting unadjusted values clearly labelled; family from `stats.hypothesis_family` (D02, open shape). Tests: textbook Holm cases, ties, monotonicity, m=1 and m=2. Size S.

**S13. Gates evaluator** - `stats/gates.py`. API: `evaluate_gates(audit_inputs, gate_params, basis) -> GateReport` (closed result per gate: value, threshold, operator, units, denominator, pass/fail/UNDEFINED, adjustment). G0 independence (exposure audit signed), G1 >= 300 trades (fixed), G2 PF >= 1.30 (fixed; zero-loss denominator -> UNDEFINED, never +inf PASS), G3 stress mean > 0 at 15 bps (fixed), G4 and G5 per D02/D06, G6 yearly (D04; undefined year does not pass), G7 regime (D12), G8 max drawdown vs comparator (D10), G9 data/engine reliability (coverage, no look-ahead, stage-1 controls passed), G10 redundancy <= 0.85 (fixed). Win rate displayed under both evaluations (ruling C3). Verdict strings only via `governance.verdict.Verdict`. Spec: `gates.*` (D18, D04, D10), `p3.criteria` (D17). Tests: UNDEFINED handling; each gate boundary (299/300 trades, 1.2999/1.30); basis switch (portfolio-constrained vs signal-level); P3b scaled G1. Size L (M for the fixed gates; G6/G7/G8 parameter shapes BLOCKED). Risk: gates must not be edited to change a threshold (fixed values live in the schema).

**S14. Sealed store and two-stage pipeline** - `audit/sealed_store.py`, `engine/pipeline.py`. Stage 1: compute all strategy and control outputs into a sealed store, expose only control outputs and engine sanity checks; control failure -> verdict `INCONCLUSIVE_ENGINE`, seal never opened; stage 2: after controls pass, (P3a) call `select_exit` and `max_stat_bootstrap`, append the `SelectionRecord` via `record_selection` BEFORE unsealing, then verify the seal hash, unseal and log operator/time. Spec: none directly; control pass criteria have NO owning field (O-10). Level 1 seal = content hash commit plus access control by file mode; real sealing depends on the execution boundary (B-1/B-2), not built here. Tests: unseal-before-selection impossible by API order; control fail never exposes strategy outputs; hash mismatch aborts; crash between steps leaves an `ABORTED` row. Size M. Risk: false assurance; state the Level 1 limit in the docstring.

**S15. Audit-pack writer** - `audit/audit_pack.py`. First line from `governance.evidence.audit_pack_header(run_id, spec_sha256)`; files per plan section 7 (research manifest, data manifest, spec copy, trades, selection record, orders, risk events, controls, test summary, diagnostics, validation report generated from JSON with no hand-edited numbers, candidate events, order event log, funnel, attribution); immutable and hashed; a separate return-blind variant for P1 coverage reports with the denylist test. Spec: `governance.economic_thesis_sha` (D13), plus manifests. Tests: header canonical form accepted by `parse_audit_pack_header`; rewrite attempt detected; report numbers equal JSON; no return fields in the P1 variant. Size M.

**S16. Funnel and attribution** - `stats/funnel.py`. `build_funnel(...)`: stages PIT symbol-days, complete OR, width eligible, signal-eligible, first trigger, order admissible, submitted, filled, protected, exited, net result; reason-coded exclusions (pattern of `gapper_stage0/funnel.py`); reconciles exactly with the portfolio counters and the trial ledger. The "fell back inside the OR within N minutes" statistic needs N (no owning field: O-15). Size M.

**S17. Diagnostics** - `stats/{walk_forward,splits,redundancy}.py`: yearly windows (from `partitions.*`), halves, regime split (D12 label supplied by a caller; label function BLOCKED), cost stress, path-ambiguity sensitivity, concentration, MFE/MAE per candidate (diagnostic only, never feeds selection), redundancy correlation (which approved strategies: O-13). Size M.

**S18. RNG-001 replay** - `controls/rng001_replay.py`: BLOCKED (host C12, IEX archive access, partition `REPLAY_RNG001` capability). The independent hand-built edge-case fixtures for chain 2 (expected outputs from a spreadsheet or separate reference implementation) are READY as an authoring task.

**S19. Params adapter** - see section 3.0. Real-value path BLOCKED on D-values and `OpenValue` shapes.

---

## 4. Prioritized backlog

### 4.1 Classification key

- **READY (synthetic only):** can be designed, built and tested with synthetic data and test-spec parameters; needs no market data and no P0 value. Merge status still needs the owner ruling in Q-B2 (plan order).
- **BLOCKED: <decision>:** cannot proceed (or cannot be completed) until the named D/C item is signed.
- **BLOCKED: host/vendor:** needs the unnamed research host (C12), a vendor/licence answer (V1-V13), or boundary B-1.

### 4.2 Ordered work packages

| # | Package | Contents | Status | Size | Depends on |
|---|---|---|---|---|---|
| B-00 | Guard harness and conventions | `_guard_harness.py` (negative tests, `EXPECTED_GATED`, enumeration), `engine/_causality.py` binding helper, look-ahead test utility (section 6), synthetic spec/param factory | READY (synthetic only) | M | - |
| B-01 | Calendar (L1) | `data/calendar.py` + DST/half-day/holiday fixtures | READY (synthetic only) | S | - |
| B-02 | Parameter objects (S19 types) | `engine/params.py` + synthetic factory | READY (synthetic only); adapter BLOCKED: D05, D06, D14, D15, D17, D18, D19 shapes | S | B-00 |
| B-03 | OR signal, tick sizer, trigger (S1) | | READY (synthetic only) | M | B-01, B-02 |
| B-04 | Arming and crossed-before-arm (S2) | | READY (synthetic only) | M | B-03 |
| B-05 | Fill model (S3) | | READY (synthetic only) | M | B-03 |
| B-06 | Risk sizer (S4) | | READY (synthetic only) | M | B-02 |
| B-07 | Costs and trade log (S7, S8) | | READY (synthetic only) | S | B-02 |
| B-08 | Exit engine E1-E4 (S5) | | READY (synthetic only) | L | B-05, B-06 |
| B-09 | Position sim and portfolio scheduler (S6) | | READY (synthetic only) | L | B-04..B-08 |
| B-10 | Bootstrap, three methods (S11) | | READY (synthetic only) | L | B-02 |
| B-11 | Multiplicity (S12) | | READY (synthetic only) | S | B-10 |
| B-12 | Selection: `select_exit`, `max_stat_bootstrap` (S10) | | READY (synthetic only) | L | B-08, B-10 |
| B-13 | Gates evaluator (S13) | G0-G5, G9, G10 structure READY; G6 (D04), G7 (D12), G8/win-rate (D10) parameter shapes BLOCKED | READY (synthetic only) for the fixed gates; BLOCKED: D04, D10, D12 for those gates | L | B-10, B-11 |
| B-14 | Audit-pack writer, return-blind report schema (S15) | | READY (synthetic only) | M | B-07 |
| B-15 | Sealed store and two-stage pipeline (S14) | Level 1 only | READY (synthetic only); real sealing BLOCKED: boundary B-1/B-2, owner EB-1 | M | B-12, B-14 |
| B-16 | Controls (S9) | random-entry mechanics READY; naive-ORB definition BLOCKED: D13/D06; time-shuffle and no-information definitions BLOCKED: no owning field (O-11, O-12) | READY (synthetic only) for random entry; otherwise BLOCKED | L | B-09 |
| B-17 | Funnel, attribution, diagnostics (S16, S17) | regime label function BLOCKED: D12; redundancy list BLOCKED: O-13 | READY (synthetic only) for the rest | M | B-09 |
| B-18 | Independent hand-built engine fixtures (RNG-001 chain 2 authoring) | Expected outputs by an independent method | READY (synthetic only); needs a second person | M | B-03..B-08 |
| B-19 | Loader fakes and fixtures (L2) | | READY (synthetic only) | M | B-01 |
| B-20 | Planner, loader core, truncation detection, chunk journal (L3-L5) | Against fakes | READY (synthetic only); the data-package lint route needs Q-B1 | L | B-19 |
| B-21 | Manifest writer/verifier, minute classifier, coverage validator (L6-L8) | | READY (synthetic only); classifier tolerance BLOCKED: D05 (injected in tests) | M | B-20 |
| B-22 | Identity map, PIT universe, corporate-action basis (L9, L10) | Synthetic DuckDB store | READY (synthetic only); real vendor mapping BLOCKED: host/vendor (V3, V9) | L | B-01 |
| B-23 | Params adapter for real spec values | | BLOCKED: D05/D06/D14/D15/D17/D18/D19 shapes and values | S | B-02 |
| B-24 | Vendor feasibility (V1-V13), earliest-bar and delisted coverage | | BLOCKED: host/vendor (C12, D03, F1, F2, F5, F6); owner authorization per step | M | - |
| B-25 | Partition-aware (holdout) ingest, broker mode (L11) | | BLOCKED: host/vendor (boundary B-1, Q-P1-3, V12) | M | B-20 |
| B-26 | Real dev-partition pull, real PIT universe, real coverage report | | BLOCKED: host/vendor and P0 sign-off, D03, D11 `data.fetch_mode` | M | B-20..B-22, B-24 |
| B-27 | S3 publication of manifests | | BLOCKED: host/vendor (S3 manifest tooling absent) | S | B-21 |
| B-28 | RNG-001 replay chain 1 | | BLOCKED: host/vendor (C12, archive, partition capability) | M | B-09 |
| B-29 | Non-equivalence check | | BLOCKED: C2/D09 (no code until specification approved) | M | - |
| B-30 | P3a/P3b/P4 runs, P5 executor | | BLOCKED: P0 gate, A1, D17/D18/D19, P4 PASS; out of scope | - | all |

### 4.3 Dependency graph

```
B-00 --+--> B-02 --> B-03 --> B-04 -----------+
B-01 --+              +--> B-05 --+            |
                      B-06 -------+--> B-08 --> B-09 --> B-16, B-17
                      B-07 (costs, trade log) -> B-14 -> B-15
B-02 --> B-10 --> B-11 --> B-13
B-08 + B-10 --> B-12 --> B-15
B-19 --> B-20 --> B-21 ;  B-01 --> B-22
B-23, B-24..B-30: blocked branch (approvals, host, vendor)
```

### 4.4 Suggested PR grouping (Recommendation, not a decision; each is one backend FULL run)

PR-A: B-00, B-01, B-02, B-19. PR-B: B-03..B-07. PR-C: B-08, B-09. PR-D: B-10..B-12. PR-E: B-13..B-15. PR-F: B-16..B-18. PR-G: B-20, B-21 (after the Q-B1 ruling). PR-H: B-22. Mapping to plan numbering: PR-B/C ~ plan PR 8, PR-F ~ 9/12B, PR-D ~ 11, PR-E ~ 12, PR-G ~ 5/7, PR-H ~ 6.

---

## 5. Traceability: task -> frozen-spec field -> owner decision -> status

Field paths are the dotted paths in Appendix A / `spec/schema.py`. Status vocabulary: **FIELD+VALUE UNSET** (field exists, P0 value null, required by the freeze); **FIELD, SHAPE OPEN** (`OpenValue`; schema accepts anything, so the owner must define the structure); **FIXED** (constant enforced by the schema); **PLAN-FIXED (code)** (rule fixed in the plan/A1, not a spec field; changing it is a new hypothesis); **NO OWNING FIELD** (flagged: behaviour depends on a value nobody owns).

### T1. Traceability table

| Task | Spec field(s) | Owner decision(s) | Status |
|---|---|---|---|
| L1 calendar sessions, early close | `data.tz` (fixed), `exit.halfday_offset_min` | D05 5g | tz FIXED; half-day offset FIELD+VALUE UNSET |
| L3 planner chunk composition | `universe.n`, `data.vendor`, `data.fetch_mode`, `partitions.*` | D03, D11 | UNSET; page-cap margin and symbols-per-request limits: NO OWNING FIELD (O-1) |
| L4 loader feed | `data.feed` (fixed `sip`), `data.bar` (fixed) | R6 | FIXED |
| L4/L5 retry budget, backoff, budget cap | none | D03 (budget cap named in sheet) | NO OWNING FIELD (O-1) |
| L6 manifest contents | `data.vendor`, `data.feed`; adjustment rule | D03, V9 | adjustment basis: NO OWNING FIELD (`data.adjustment` named in RA, absent from schema) (O-2) |
| L7 NO_TRADE_MINUTE vs DATA_GAP evidence rule and tolerance | `signal.missing_minute_classes` (fixed), `signal.or_completeness_rule` | D05 5a | rule SHAPE OPEN; volume-reconciliation tolerance: NO OWNING FIELD (O-4) |
| L8 coverage threshold 98%, exclusion bound | none | design v0.4; Q-P1-4 | threshold is design text, not a spec field; exclusion bound: NO OWNING FIELD (O-5) |
| L9 universe N, price floor, ADV window, rebuild cadence | `universe.n`, `universe.min_price` (fixed 10.0), `universe.adv_window_days` (fixed 20), `universe.rebuild` (fixed monthly), `universe.include_delisted` (fixed) | D03 | n FIELD+VALUE UNSET; rest FIXED |
| L9 PIT timing of the rebuild; ADV tie-break; instrument metadata PIT | none | D03 ("PIT timing" in `universe.*`/`data.*`) | NO OWNING FIELD (O-6) |
| L9 lineage refusal thresholds (`LINEAGE_*`, 20 sessions) | none (constants in `app/validation/security_lineage.py`) | D09? (RA open question) | PLAN-FIXED in another module; whether RANGE-002 adopts them is unowned (O-7) |
| L10 price basis | none | D05 (WP1.6), V9 | NO OWNING FIELD (O-2) |
| L11 holdout ingest authorization | `partitions.holdout` | EB-1/EB-3, Q-P1-3 | boundary design unsigned; ingest authorization has no design |
| S1 OR completeness, min width | `signal.or_completeness_rule`, `signal.min_or_width_ticks` | D05 5a, 5b | SHAPE OPEN / UNSET |
| S1 tick size source (price bands) | `signal.tick_offset` (fixed 1) | D05 5f | tick-size table: NO OWNING FIELD (O-3a) |
| S1/S2 bar timestamp convention, vendor delay | `execution.bar_timestamp_convention`, `execution.vendor_delay_ms` | D14, F4 | FIELD+VALUE UNSET |
| S2 latency, crossed-before-arm, order type, protection | `execution.submit_latency_ms`, `ack_latency_ms`, `crossed_before_arm_policy`, `order_type`, `stop_protection_policy` | D14, F3 | UNSET; `stop_protection_policy` SHAPE OPEN |
| S2 entry window, one entry per day | `signal.entry_window`, `signal.max_entries_per_symbol_day` | - | FIXED |
| S3 slippage, halt, same-bar | `fill.slippage_model`, `fill.halt_policy`, `fill.same_bar_policy` | D05 5d, 5e, 5h, 5i; D15 | slippage/halt SHAPE OPEN; same-bar FIXED `worst_case`; halt detection data availability unknown: NO OWNING FIELD (O-16) |
| S3 EOD flat, lead | `exit.eod_flat` (fixed 15:55:00), `exit.halfday_offset_min`, `execution.eod_lead_s` | D05 5g, D14 | eod FIXED; others UNSET |
| S3 bar-volume basis for participation | `risk.max_participation` | D05 5j | unit/definition of "participation" not stated: partial (O-17) |
| S4 per-trade risk, caps, concurrency, daily loss, tolerance | `risk.per_trade_pct, per_name_cap, gross_cap, max_concurrent, daily_loss_limit, max_participation, fill_risk_tolerance` | D05 5j, 5c | FIELD+VALUE UNSET; units undefined (percent vs currency) (O-17) |
| S4 starting equity / buying power in the simulation | none | none | **NO OWNING FIELD (O-3)** |
| S4 action when actual risk exceeds budget (reduce vs protective exit) | `risk.fill_risk_tolerance` covers tolerance only | D05 5c | rule choice has NO OWNING FIELD (O-18) |
| S5 exit candidates, params, order | `exits.candidates`, `exits.complexity_order` | D19, A1 | UNSET; per-family param vocabulary OPEN (O-9) |
| S5 initial stop | `exit.stop` | - | FIXED `or_low` |
| S5 trail/breakeven/scale-out semantics (completed-bar close, next-bar effect, rounding down, 50%) | none | A1, plan WP2.2A | PLAN-FIXED (code) |
| S6 same-time priority, reservation policy | `execution.tie_break`, `execution.order_reservation_policy` | D14 | SHAPE OPEN / UNSET |
| S6 trade unit, basis | `gates.basis`, `gates.trade_unit` | D18 | UNSET / SHAPE OPEN |
| S7 cost bps, mode, components | `costs.base_bps_per_side` (fixed 5), `costs.stress_bps_per_side` (fixed 15), `costs.accounting_mode`, `costs.components` | D15 | mode UNSET; components SHAPE OPEN |
| S9 random-entry reps, seed, invalid-draw policy | `controls.random_entry.{repetitions,seed,invalid_draw_policy}` | D06, WP2.7A | UNSET; policy SHAPE OPEN |
| S9 random-entry feasible-instant set and matching rule | none | D06 (design 5.3: matched on symbols, window, trade count, capital, risk) | **NO OWNING FIELD (O-10a)** |
| S9 naive ORB definition | `controls.naive_orb.definition` | D13/D06 | SHAPE OPEN |
| S9 time-shuffle procedure | none | none | **NO OWNING FIELD (O-11)** |
| S9 no-information trigger distribution | none | none | **NO OWNING FIELD (O-12)** |
| S14 stage-1 control pass criteria (what makes a control "fail") | none | none | **NO OWNING FIELD (O-10)**: G9 and `INCONCLUSIVE_ENGINE` depend on it |
| S14 seal mechanism | none | EB-1 (boundary) | design unsigned |
| S10 selection score, tolerance, eligibility, stop test | `exits.selection.{score,tie_tolerance_r,eligibility.min_trades,eligibility.min_pf,stop_test}` | D19, D17, D06 | UNSET; `score`/`stop_test` are free strings: allowed vocabulary not defined |
| S10 tie rule inside one family (E3a vs E3b), studentization | none | none | **NO OWNING FIELD (O-8, O-9)** |
| S11 bootstrap method, block, reps, CI type, level, seed | `stats.bootstrap.{method,block_len,reps,ci_type,confidence_level,seed}`; `stats.bootstrap.cluster` fixed | D06, C11 | UNSET (method deliberately unset) |
| S11 per-stream seed derivation, per-candidate substreams | none | D06 | NO OWNING FIELD (O-14) (engineering rule; propose in code, validator reviews) |
| S11 alpha | `stats.alpha_one_sided` | D06, D17 | UNSET |
| S12 family and adjustment | `stats.hypothesis_family`, `stats.adjustment` | D02, C6 | SHAPE OPEN / UNSET |
| S13 G1, G2, G3, G10 | `gates.min_trades` (300), `gates.pf_base` (1.30), `gates.stress_mean_positive`, `gates.redundancy_corr_max` (0.85) | design 6 | FIXED |
| S13 G6 yearly | `gates.yearly` | D04 | SHAPE OPEN |
| S13 G7 regime | `stats.regime.{definition,criterion}` | D12 | SHAPE OPEN |
| S13 G8, win rate | `gates.max_dd`, `gates.win_rate` | D10, C3 | SHAPE OPEN |
| S13 P3a/P3b criteria | `p3.criteria`, `p3.max_p3a_attempts`, `p3.max_p3b_attempts` | D17 | UNSET (guard refuses while null) |
| S13 G0 | `governance.exposure_signed` | D01 | UNSET |
| S13 G9 coverage threshold | none (98% in design text) | design 6 | NO OWNING FIELD for the 98% value (O-5) |
| S15 audit pack header and files | none | plan section 7 | PLAN-FIXED (header format in `governance/evidence.py`) |
| S15 thesis reference | `governance.economic_thesis_sha` | D13 | UNSET |
| S16 funnel fell-back-inside-OR window N | none | none | NO OWNING FIELD (O-15) |
| S17 walk-forward windows | `partitions.*` | - | FIXED (derived) |
| S17 redundancy comparison set | `gates.redundancy_corr_max` only | none | which approved strategies: NO OWNING FIELD (O-13) |
| Guard binding (spec hash, partitions, exposure) | `governance.registry_genesis_id`, `governance.exposure_signed`, `partitions.*`, `p3.*` | D01, D17 | UNSET; genesis manifest unsigned |

### T2. Tasks whose behaviour depends on a value with no owning field or decision (flag list)

Each needs either a new spec field (plus a decision), an explicit "plan-fixed constant" ruling, or removal. Until then the affected module cannot be merged as final.

| ID | Orphan value | Affects | Recommendation (not a decision) |
|---|---|---|---|
| O-1 | Loader budget cap (money/bytes/requests), page-cap safety margin, retry budget, backoff | L3-L5 | Add `data.budget` and `data.chunk_margin` to D03 (RA Q-P1-7 already asks); retry/backoff as code constants recorded in the manifest. |
| O-2 | Price adjustment basis (`data.adjustment`) | L6, L10 | Add field; D03/V9. RA used this key but `schema.py` `Data` has no such field. |
| O-3 | Starting equity for the simulation; O-3a tick-size source | S4, S6; S1 | Add `risk.initial_equity` under D05 5j; tick-size band table as a PLAN-FIXED constant with a source citation. |
| O-4 | Daily-volume reconciliation tolerance | L7 | Put inside the D05 `or_completeness_rule` structure or a new `data.minute_reconciliation`. |
| O-5 | 98% coverage threshold and bound on `VENDOR_NO_HISTORY`/`IDENTITY_UNMAPPED` exclusions | L8, G9 | Add `data.coverage_min` and `data.exclusion_bound` (Q-P1-4). |
| O-6 | PIT timing of the rebuild; ADV tie-break; instrument-type metadata as-of | L9 | D03 states "PIT timing" but no key; add `universe.pit_rule` or declare plan-fixed. |
| O-7 | Whether lineage refusal constants apply | L9 | Owner states adoption of `LINEAGE_*` as-is (RA recommendation). |
| O-8 | Studentization method in max-statistic | S10 | Validator specifies in D06/D19; pure code constant otherwise. |
| O-9 | Tie rule within one family; per-family candidate parameter vocabulary | S5, S10 | D19 sheet to list parameter names (`k_r`, `trail_r`, `scale_fraction`, `scale_at_r`) and a within-family complexity order. |
| O-10 | Stage-1 control pass criteria; random-entry feasible-instant set and matching (O-10a) | S14, S9, G9 | New `controls.stage1_criteria` under D06; without it `INCONCLUSIVE_ENGINE` cannot be decided. |
| O-11 | Time-shuffle procedure | S9 | New `controls.time_shuffle` under D06. |
| O-12 | No-information trigger distribution | S9 | New `controls.no_information` under D06. |
| O-13 | Approved strategies for the redundancy correlation | S17, G10 | Owner list under D10/D08, pinned by hash. |
| O-14 | RNG stream/seed derivation | S9, S11 | Engineering rule documented in the module; validator reviews. |
| O-15 | Window N for the "fell back inside OR" statistic | S16 | Diagnostic-only constant, labelled non-binding. |
| O-16 | Halt data source and detection | S3, L7 | Depends on V (halt data availability UNKNOWN); `fill.halt_policy` cannot be implemented beyond labelling. |
| O-17 | Units for `risk.*` limits and meaning of participation | S3, S4 | Owner states units with D05 5j (percent of equity vs currency; fraction of bar volume). |
| O-18 | Rule when actual risk exceeds budget | S4 | Add enumerated `risk.over_budget_rule` (reduce / protective exit) under D05 5c. |

---

## 6. Test plan (layered)

Principle: all tests use synthetic data. No test reads a vendor response, an IEX archive or a Sharadar file. A CI-safe check in the PR proves test modules import no real-data path.

1. **Unit.** Every kernel, one behaviour per test, expected values computed by hand in the test (not by the code under test). Table-driven for the fill model rows, exit-engine transitions and gate boundaries.
2. **Property** (seeded `random.Random` loops, no new dependency). No entry precedes both bar availability and order acknowledgement; `qty * R_pre <= budget`; trail stop never decreases; net R across exit fills equals hand sum; daily end-of-day position is zero when the market is executable; Holm monotonicity; bootstrap resamples keep each trading day's trades together; planner never exceeds page cap; universe ordering is stable under input permutation.
3. **Fixtures** (section 2.4 list plus engine fixtures: gap-through, gap-down, same-bar entry+stop, stop+target, target-in-entry-bar, odd/1-share scale-out, partial fill, participation binding, daily-loss mid-day, split/spinoff/delisting, halt/resume, duplicate trigger). The independent expected-output set (B-18) is authored and reviewed by someone other than the implementer.
4. **Governed integration with synthetic specs.** Build the synthetic frozen spec via `load_synthetic_view` + `to_guard_view`, enroll `new_registry`, patch the manifest seam as `governance/conftest.py` does, call `authorize(phase=P2, partition=REPLAY_RNG001, ...)` and run the phase-level entry point end to end: success path; every refusal path (unsigned spec, wrong genesis, closed run, capability of another run/spec/partition, date range outside `capability.date_range`). P3A/P3B-style runs are exercised only against synthetic partitions with synthetic D17/D19 blocks; the P4 holdout token path is already covered by governance tests.
5. **Guard-coverage proof** per PR (section 1.4): non-vacuous lint, negative tests per entry point, enumeration.
6. **Determinism.** Same inputs, spec and seed give byte-identical `trades.csv`, selection record, audit pack (hash equal across two runs and across `PYTHONHASHSEED` values); input row order permutation does not change results; Python/pandas/numpy versions recorded in the pack.
7. **Look-ahead tests** (the central property). Generic helper `assert_causal(run_fn, bars, cut)`: run once with the true bars, once with every bar whose `available_at > cut` replaced by adversarial garbage (huge spikes, NaN-free but extreme, reordered), and assert that every decision, order, reservation, size and state with `decision_at <= cut` is identical. Applications: OR frozen at 10:00 (garbage from 10:00 on leaves the OR unchanged); trigger and arming; R_pre and sizing at submission; the whole portfolio scheduler (shifting future prices never changes an order scheduled before the shift; the two-symbol collision case); exits (completed-bar-close updates never use the current bar); PIT universe (garbage in daily data dated after the prior trading day never changes the month's universe); controls (random entry never qualifies by a future cross of OR high); minute classifier (a classification of minute t uses only data stored for the chunk, not later chunks). Mutation check: a deliberately look-ahead variant of each kernel in the test file must FAIL `assert_causal`, proving the helper is not vacuous.
8. **Statistical calibration (simulated data only).** Zero-mean iid and autocorrelated synthetic R series: one-sided rejection rate near alpha for each bootstrap method; max-statistic more conservative than best-of-K naive; power sanity on a planted positive effect. Allowed by the D06 sheet; no RANGE-002 data involved.
9. **Failure-behaviour tests (loader).** Truncation, empty month, vendor gap, delisted, ticker reuse, wrong feed, entitlement error, crash/resume, restatement, tampered manifest, below-threshold coverage (all section 2.4).
10. **Return-blind schema tests.** P1 coverage and manifest schemas contain no field matching return/pnl/win/hit/profit patterns.

Coverage target (Recommendation, not a decision): >= 95% line coverage for new range002 compute modules, reported in the PR description until a coverage script is justified (CI batching, section 1.3).

---

## 7. Readiness report

### 7.1 Top blockers

1. **P0 sign-off chain** (A1, D08, D06, D19, D17, D05, D14, D15, D02, D18, D01, D09/C2, remaining). No real parameter value exists; the adapter cannot be completed.
2. **Vendor/licence/history** (RA V1-V13; D03, F1, F2, F5, F6): bulk stored research use of 10 years of 1-minute SIP bars including delisted names is unconfirmed (stop condition 3 if not).
3. **Research host unnamed** (C12) and its custody procedure; Norton blocks the laptop; `ec2-paper` and the laptop are excluded.
4. **Execution boundary B-1** (EB-1..3, Q-B3) before any holdout-month ingest; holdout ingest authorization is not designed.
5. **S3 manifest tooling absent** (checked: no `manifests/s3`, no S3 manifest scripts): loader evidence has no governed home; do not invent a format.
6. **Guard route for `data/`** (Q-B1): no P1 phase; lint requires reviewed entries.
7. **Orphan values** (section 5, T2): O-3, O-5, O-10..O-12, O-18 are most consequential.
8. **Sequencing ruling** (Q-B2) for building P2 kernels before the P0 gate.

### 7.2 Unknowns

Vendor SIP minute depth to 2016 and delisted coverage; whether the account's entitlement allows storage; vendor rate limits and page cap; bar timestamp convention and delay (F4); whether SEP daily volume reconciles with SIP minute volume (affects `NO_TRADE_MINUTE`); whether Sharadar TICKERS metadata is point-in-time; vendor halt data; vendor restatement behaviour; quote-level history; the permaticker-to-vendor-ticker join (absent from the repo: only ticker-to-permaticker resolution exists); SDK pagination behaviour across the allowed `alpaca-py` range (verified only on the local 0.44.0 source); whether numpy streams or stdlib `random` is preferred by the validator; broker stop-order semantics (F3).

### 7.3 What is NOT authorized by this document

- Any P1 execution, vendor/provider/broker call, SDK call, or network access; reading or using any API key or credential file.
- Retrieving, copying, sampling or reading any historical market data (including "small samples"); building the real PIT universe or any real ADV/price ranking.
- Computing or looking at any RANGE-002 return, P&L, profit factor, win rate, or any real-data strategy statistic; any protected evaluation; backtesting any real strategy.
- Implementing or merging the loader, the engine, or any compute module (this document is a backlog and design; sections 3 and 4 are plans).
- Choosing, defaulting or hardcoding any `P0:` value, or freezing/signing the spec; fabricating a signature.
- Running the loader, replay or any workbench stack on the laptop or `ec2-paper`; opening any holdout data; touching `BarCache`, RNG-001 code, user 2, or the order path.
- Publishing to S3 or inventing a manifest format; pushing, opening PRs or merging.

### 7.4 Owner questions

| # | Question |
|---|---|
| Q-B1 | How should `data/` code satisfy the capability lint given there is no P1 phase: reviewed pure(-IO) entries (recommended), a package outside the lint scope, or a new data-acquisition phase in governance? |
| Q-B2 | May P2 kernels and the P1 loader core be built and reviewed on synthetic data before the P0 gate (plan section 8 order), with nothing treated as the approved engine until the gate? |
| Q-B3 | Approve the regrouping of 20 plan PRs into the 8 PR groups in section 4.4? |
| Q-B4 | Add the missing spec fields listed in T2 (`risk.initial_equity`, `risk.over_budget_rule`, `controls.stage1_criteria`, `controls.time_shuffle`, `controls.no_information`, `data.adjustment`, `data.budget`, `data.coverage_min`, `data.exclusion_bound`, `universe.pit_rule`) or rule each a plan-fixed constant? This is a schema change touching the frozen-spec contract (hash unaffected until a spec is frozen). |
| Q-B5 | Extend `SpecView` so engine code can read the sections it does not expose today? |
| Q-B6 | Accept no new dependencies (no `hypothesis`; numpy only as the existing transitive dependency), or approve declaring them as part of a batched manifest change? |
| Q-B7 | Is it acceptable that unit tests call underscore-private kernels on synthetic data without a capability (no real data involved)? |
| Q-B8 | Plus the RA questions Q-P1-1..8, unchanged. |
