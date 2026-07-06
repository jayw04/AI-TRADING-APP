| Field | Value |
|---|---|
| Document version | v0.3 (final — owner approved for implementation 2026-07-04, 9.8/10; v0.3 folds the pre-merge refinements) |
| Date | 2026-07-04 |
| Phase | PORT-001 (Capability Onboarding) — deferred follow-up to the live `combined-book` (§4) |
| Session | PORT-001 · Total-Return Live Pricing (owner priority #3) |
| Predecessor | PR #342 (beta-cap governor, `f33805d`) — PORT-001 v1.2; combined-book id=9 live paper acct 7 |
| Successor | (owner priority #4) CAP-020 regime-overlay validation |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Add a live Alpaca-backed `DistributionsProvider` and route the combined-book **cross-asset ETF sleeve** (and the beta-cap governor's price panel) onto **total-return** closes instead of raw closes. **Default OFF**; fail-open to raw closes. Includes data-quality validation, bounded retry, performance thresholds, Prometheus metrics, and per-rebalance evidence logging (owner review). |
| Estimated wall time | 6–8 hours (provider + validation + retry + metrics + evidence + wiring + tests + live read-only smoke + PR) |
| Tag on completion | `port001-total-return-pricing-complete` |
| Out of scope | Equity momentum sleeve (already prices from Sharadar `closeadj`); enabling the flag on the live book; a Sharadar/Yahoo/Polygon distributions provider *implementation* (abstraction documented, not built); backfilling historical reproduction with TR; frontend surfacing; total-return in the offline reproduction harness; persistent cross-restart corp-actions cache. |

---

## 0. Executive summary

- **Objective** — deliver total-return pricing for the combined-book cross-asset ETF sleeve using Alpaca corporate actions, removing a known raw-price approximation before the next allocation/regime-overlay validation work.
- **Behavior** — **default OFF.** Byte-identical to today's book until an explicit param flip; a `report_only` dry-run logs the live TR-vs-raw divergence first.
- **Risk to live trading** — **none.** Additive, gated behind a default-false flag, fail-open to raw closes on any provider error, no order-path/audit-subsystem/new-dependency change.
- **Deployment** — read-only preview → report-only rebalance → owner review of the divergence → enable → production (mirrors the beta-cap governor rollout).
- **Expected benefit** — more accurate momentum/vol signals for income-producing ETFs (TLT, IEF, DBC, GLD) where distributions are a material part of total return; the governor also assesses risk on TR series once enabled.

## Review response (v0.2 — how `comments.md` was folded)

| # | Owner suggestion | Priority | Where addressed |
|---|---|---|---|
| 1 | Performance thresholds (latency/timeout) | High | §4.1 "Performance thresholds" |
| 2 | Data-quality validation before adjusting | Very High | §4.1 "Data-quality validation" |
| 3 | Prometheus observability metrics | — | §4.4 (six `workbench_*` metrics) |
| 4 | Cache lifecycle rules | — | §4.1 "Cache lifecycle" |
| 5 | Bounded retry before fail-open | — | §4.1 "Retry" (mirrors `sharadar._get_with_retry`) |
| 6 | Per-rebalance evidence logging | — | §4.4 (structured `total_return_pricing` signal) |
| 7 | Feature-state (RAW/TOTAL_RETURN) in evidence | — | §4.4 (`pricing_method` in payload) |
| 8 | Future multi-provider abstraction | — | §4.5 (documented, not built) |
| 9 | Corporate-action versioning metadata | — | §4.4 (`provider`/`fetched_at`/`record_count`) |
| ed | Executive summary | Editorial | §0 above |

**v0.3 pre-merge refinements (final review):**

| # | Owner suggestion | Where addressed |
|---|---|---|
| v3-1 | Explicit success criteria | §5.1 "Success criteria" |
| v3-2 | Risk classification matrix | §3.1 "Risk matrix" |
| v3-3 | Rollback plan | §6.1 "Rollback" |
| v3-4 | Functional vs non-functional requirements | §1.1 "Requirements" |
| v3-5 | Ownership table | §1.2 "Ownership" |
| v3-6 | Assumptions | §1.3 "Assumptions" |
| v3-7 | Future considerations roadmap | §4.5 (extended) |
| v3-tech | Layered decomposition of the provider | §8 note 11 — **deliberately deferred** (owner: over-engineering for a 9-symbol weekly fetch) |

## 1. Why this session exists

PORT-001's cross-asset sleeve (TSMOM over SPY/EFA/EEM/TLT/IEF/GLD/DBC/UUP/KMLM) prices from the platform's Alpaca daily bars, which are **raw / unadjusted** (DCAP-003). For bond and commodity ETFs, cash distributions are a **material** share of total return: TLT/IEF pay monthly coupons, DBC and the equity ETFs pay quarterly. Pricing momentum and vol on raw closes systematically understates the return of the high-distribution legs and injects a spurious ~ex-date "gap down" into the signal. The Total-Return Adapter (`app/factor_data/total_return.py`, DCAP-006) was built in PORT-001 §1 precisely for this, with the pure math shipped and tested — but its live `DistributionsProvider` seam was **deferred**, because the only wired corporate-actions path (`data.alpaca.markets`) was blocked by Norton SSL inspection on the developer laptop.

Two facts have since changed and make this the right time to close the seam:

1. **The runtime is AWS, not the laptop.** The live book runs on `ec2-paper`; Norton does not apply there. A live Alpaca corporate-actions fetch from the box **works** (verified 2026-07-04 — see §7).
2. **Sharadar cannot supply this data.** The Sharadar `actions` table has **zero** rows for every cross-asset ETF (SPY/EFA/EEM/TLT/IEF/GLD/DBC/UUP/KMLM are absent from both `actions` and `sep`; its 349 action rows are US single-stock dividends). Sharadar is therefore not a candidate source for the ETF sleeve — Alpaca corporate-actions is.

This session ships the live provider and wires it in **default-OFF**, exactly mirroring how lever #2 (the beta-cap governor) shipped: additive, dry-runnable, flipped later by param after review. It leaves the live book's behavior unchanged until the owner enables it.

### §1.1 — Requirements (functional vs non-functional)

**Functional**
- Fetch cash distributions + splits for the 9 cross-asset ETFs from Alpaca corporate actions.
- Compute the total-return index (raw closes + distributions) via the existing adapter.
- Wire TR closes into `combined_book._close_panel` (cross-asset sleeve + governor panel).
- Report the raw-vs-TR divergence (report-only dry-run) and emit a per-rebalance evidence signal.

**Non-functional**
- **Default OFF** — byte-identical target book until an explicit flip.
- **Fail-open** — any provider error ⇒ raw closes; a rebalance never breaks.
- **Timeout ≤ 10 s**, **retry ≤ 2** (transient only), latency SLOs (§4.1).
- **Data-quality validation** — drop-and-continue on any malformed record.
- **Observability** — six Prometheus metrics + structured evidence payload.
- **No order-path / audit-subsystem / new-dependency impact.**

### §1.2 — Ownership

| Component | Owning area |
|---|---|
| `AlpacaDistributionsProvider` (fetch/validate/cache/retry) | Market Data (`app/market_data/`) |
| Prometheus metrics | Observability (`app/observability/`) |
| Evidence signal / divergence reporting | Portfolio / strategy (`combined_book`) |
| `use_total_return_pricing` / `tr_pricing_report_only` params | Strategy (`strategies_user/templates/combined_book.py`) |
| Total-return math (`total_return_index`) | Factor-data (existing, `app/factor_data/total_return.py`) |

### §1.3 — Assumptions

1. Corporate actions remain available via the Alpaca data API (`data.alpaca.markets`) from the box.
2. Alpaca ETF distributions are authoritative for these 9 symbols (Sharadar has none).
3. The corporate-actions API stays backward compatible within `alpaca-py <1.0` (`CorporateActionsClient` surface).
4. One weekly batched fetch (9 symbols) remains operationally inexpensive.
5. The combined-book rebalance remains single-threaded (justifies the non-thread-safe in-memory cache).

*If any assumption breaks, revisit: (1)/(3) → the provider fetch; (2) → the source decision (§8 note 1); (4) → the cache/persistence decision; (5) → cache thread-safety.*

## 2. What this session ships

- `app/market_data/alpaca_distributions.py` — `AlpacaDistributionsProvider`, a live `DistributionsProvider` backed by the Alpaca corporate-actions API (batch fetch grouped by symbol, **data-quality validation**, **bounded retry**, **performance thresholds**, documented **cache lifecycle**).
- Six Prometheus metrics in `app/observability/metrics.py` (`workbench_distribution_*`, `workbench_total_return_fail_open_total`).
- Total-return wiring in `strategies_user/templates/combined_book.py::_close_panel`, behind a new param `use_total_return_pricing` (**default `False`**), fail-open to raw closes, emitting a structured **evidence signal** each rebalance (records, splits, fallback, elapsed_ms, pricing_method, provider metadata).
- Two new params in `default_params` + `params_schema`: `use_total_return_pricing` (bool) and `tr_pricing_report_only` (bool — log the TR-vs-raw divergence without changing the panel, the dry-run analogue).
- Unit tests: `tests/market_data/test_alpaca_distributions.py` (parsing + validation + retry + fail-open, offline with a fake client) and an extension to `tests/strategies/test_combined_book_template.py` (the `_close_panel` TR branch with a fake provider).
- `scripts/preview_total_return_pricing.py` — a read-only box preview: fetch live distributions, build TR vs raw panels for the 9 ETFs, and print the per-symbol return divergence (the evidence the owner reviews before flipping).
- Doc updates: remove the "deferred / Norton-gated" note in `total_return.py`; a short entry in the PORT-001 capability certificate/evidence; update `SelfStackDataFidelity_PORT-001_v0.1.md` (ETF distribution source resolved → Alpaca).

## 3. Prerequisites

- PORT-001 v1.2 live on the box (id=9, done — PR #342).
- Alpaca creds resolvable in the backend container via `load_credentials()` (confirmed — the sleeve already fetches bars).
- `alpaca-py` ≥ 0.30 (box runs **0.43.5**; exposes `CorporateActionsClient`, `CorporateActionsRequest`, `CorporateActionsType`).
- Box network reachability to `data.alpaca.markets` (confirmed 2026-07-04).

### §3.1 — Risk matrix

| Risk | Impact | Mitigation |
|---|---|---|
| Alpaca corporate-actions API unavailable | Low | Fail-open to raw closes; `workbench_total_return_fail_open_total` |
| Invalid / anomalous corporate-action record | Low | Data-quality validation (drop-and-continue), reject metric |
| Slow API | Low | 10 s timeout + bounded retry (≤2), latency histogram + SLO log |
| Missing / incomplete dividends | Medium | Evidence logging (record counts) surfaces gaps; report-only divergence review |
| Wrong pricing applied to the live book | Medium | Default OFF + report-only rollout + owner review before enabling |
| Double-adjusting the equity sleeve | Low | Scoped to cross-asset sleeve only; equity uses Sharadar `closeadj` (§7) |

## 4. Detailed work

### §4.1 — `AlpacaDistributionsProvider` (`app/market_data/alpaca_distributions.py`)

Implements the existing Protocol (`app/factor_data/total_return.py:93`):

```python
def distributions(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
                  ) -> tuple[pd.Series, pd.Series]:  # (dividends, splits), keyed by ex-date
```

Design choices (inline rationale):

- **Batch, then group.** The corporate-actions endpoint accepts a list of symbols and returns one flat list per category, each item carrying `.symbol`. So the provider exposes a `prefetch(symbols, start, end)` that makes **one** HTTP call for all 9 ETFs and caches the grouped result; `distributions(symbol, …)` then reads from the cache. One weekly rebalance ⇒ one API call. (Per-symbol calls would be 9×; unnecessary.)
- **Field mapping (verified against live objects):**
  - `cash_dividends[i]` → dividend `d`: `rate` (cash per share) keyed by `ex_date`. Ignore `special`/`foreign` distinctions for pricing (they still pay the holder).
  - `forward_splits[i]` / `reverse_splits[i]` → split multiplier `s = new_rate / old_rate` keyed by `ex_date` (NVDA 10:1 → `new_rate=10, old_rate=1` → `s=10.0`; a 1:2 reverse → `s=0.5`). This is exactly the `total_return_index` convention (`s_t` = share multiplier).
- **Credential + TLS idiom** mirrors `bar_cache._alpaca_fetch_bars`: `enable_os_trust_store()` (ADR 0017) then `load_credentials()` then construct `CorporateActionsClient(api_key, secret_key)`. Truststore keeps it working behind any MITM and is a no-op on the box.
- **Sync SDK call, async surface.** The SDK client is synchronous; the strategy context is async. Wrap the blocking call in `run_in_executor` (as `BarCache.get_bars` does) so the one weekly HTTP call never blocks the event loop.
- **Read-only / no side effects.** No DB writes, no order path (satisfies the MCP/broker-isolation spirit — this is pure market-data read). Returns empty series on any error so the adapter degrades to raw closes.

**Data-quality validation (owner review #2 — Very High).** Vendor feeds occasionally carry anomalies; validate every record *before* it can affect a price, and drop-and-log bad ones rather than fail the whole fetch:

| Check | Action on failure |
|---|---|
| dividend `rate` present, finite, `>= 0` | drop record, `warning` log, increment reject metric |
| split `new_rate > 0` and `old_rate > 0` (⇒ `s = new_rate/old_rate > 0`) | drop record |
| `ex_date` non-null and within `[start, end]` | drop record |
| no NaN in the produced series | coerce/drop |
| de-duplicate on `ex_date` (keep last by `process_date`) | collapse duplicates |
| series sorted ascending by `ex_date` | sort (not a reject) |

A single bad record never poisons the symbol; a symbol that ends up empty simply yields raw pricing for that leg. All rejects are counted (§4.4) so anomalies are visible without log-diving.

- **Performance thresholds (owner review #1 — High).** The batched fetch is wrapped with an explicit HTTP **timeout of 10 s**. Operational thresholds: typical **< 500 ms**, target **< 2 s**, max tolerated **5 s** (a `warning` log + latency metric fire above target). On timeout → retry path (below) → fail-open. These are documented so slowness is an alert, not a judgment call.

- **Retry (owner review #5).** Transient network failures retry with bounded exponential backoff **before** falling back to raw — mirroring the proven `SharadarProvider._get_with_retry` (`app/factor_data/providers/sharadar.py:24`): up to 2 retries on transport errors / HTTP 429 / 5xx, `backoff_base · 2**attempt`; non-transient errors (auth 4xx) fail open immediately. Exhausting retries → fail-open (raw closes) + `total_return_fail_open_total` increment.

- **Cache lifecycle (owner review #4).** The cache is **per-provider-instance, in-memory only**, populated by one `prefetch()` and read by `distributions()` within a **single rebalance**. Explicitly:
  - *Scope:* one rebalance. `combined_book` constructs (or is handed) a fresh provider per `_rebalance`, so the cache does not span runs.
  - *Reuse across runs:* none — a new rebalance re-fetches (corp-actions data is authoritative and cheap weekly).
  - *Midnight / staleness:* irrelevant — the window is recomputed each rebalance from `start/end`; nothing ages in-cache.
  - *Thread-safety:* not required — a rebalance is single-tasked; no concurrent writers.
  - *Process restart:* does not survive (in-memory by design). No persistent corp-actions table this session (see Out of scope).

Skeleton:

```python
class AlpacaDistributionsProvider:  # implements factor_data.total_return.DistributionsProvider
    def __init__(self, client: object | None = None, *, timeout_s: float = 10.0) -> None: ...
    async def prefetch(self, symbols: list[str], start, end) -> "FetchSummary": ...  # 1 batched call, executor-wrapped, retried, validated; returns metadata for evidence
    def distributions(self, symbol, start, end) -> tuple[pd.Series, pd.Series]: ...   # read cache; ([], []) if absent/invalid
```

Tests (offline, no network): a fake client returning canned `cash_dividends` + `forward_splits` objects → dividends keyed by `ex_date` with the right `rate`; forward + reverse split → `s = new_rate/old_rate`; **validation** — negative dividend / zero split / out-of-window ex-date / duplicate ex-date / NaN each dropped, good records kept; **retry** — transient error then success returns data; **fail-open** — persistent error → empty series + fail-open metric; unknown symbol → empty series.

### §4.2 — Wire into `combined_book._close_panel` (default OFF)

`_close_panel` (`combined_book.py:383`) currently builds each symbol's series from raw `bars["c"]`. Add a total-return branch:

```python
use_tr = bool(self.params.get("use_total_return_pricing", False))
report_only = bool(self.params.get("tr_pricing_report_only", False))
# when use_tr or report_only: prefetch distributions once, then per symbol:
#   tri = total_return_index(raw_close, dividends, splits)   # app.factor_data.total_return
#   series[sym] = tri if use_tr else raw_close                # report_only logs divergence, keeps raw
```

- **Default OFF** (`use_total_return_pricing=False`) ⇒ byte-identical to today's behavior (conservative-defaults convention). The engine default stays raw; only an explicit param flip changes pricing.
- **`tr_pricing_report_only=True`** computes the TR panel and **logs** the per-symbol raw-vs-TR trailing-return divergence to a `PORTFOLIO` info signal (`reason="total_return_pricing"`) **without** changing the panel — the live dry-run, so the owner sees the effect on the actual book before enabling. (Same pattern as `beta_cap_report_only`.)
- **Fail-open:** any provider/adapter error ⇒ log `reason="total_return_failopen"` and use raw closes. The rebalance never breaks on a data hiccup.
- **Governor coupling:** `_maybe_beta_cap` calls `_close_panel` for its covariance panel, so enabling TR also feeds the governor TR returns — correct and desirable (the governor should assess risk on total-return series).

New params (added to `default_params` and `params_schema` so the form stays in sync — the drift-avoidance invariant):

```python
"use_total_return_pricing": False,   # price the cross-asset sleeve on total-return closes (Alpaca corp-actions)
"tr_pricing_report_only": False,     # log the TR-vs-raw divergence without changing the panel (dry-run)
```

### §4.3 — Preview script (`scripts/preview_total_return_pricing.py`)

Read-only, box-run. Fetch live distributions for the 9 ETFs, build raw and TR close panels over ~2y, and print per-symbol: number of distributions, trailing 12m raw return vs TR return, and the delta. This is the **evidence artifact** the owner reviews to decide the flip — the analogue of `preview_beta_cap_live.py`. Writes a JSON to `data/` (mounted; `docs/` is not).

### §4.4 — Evidence & observability

**Prometheus metrics (owner review #3).** Added to `app/observability/metrics.py` following the existing `workbench_*` naming (cf. `orders_submitted_total`, `broker_api_errors_total`):

```python
workbench_distribution_requests_total   = Counter(...)     # corp-actions fetches attempted
workbench_distribution_failures_total   = Counter(...)     # fetches that fell through to fail-open
workbench_distribution_records_total    = Counter(..., ["kind"])  # kind=dividend|split|rejected
workbench_total_return_fail_open_total  = Counter(...)     # rebalances that used raw due to error
workbench_distribution_fetch_seconds    = Histogram(...)   # fetch latency (buckets to 10s)
workbench_pricing_mode                  = Gauge(..., ["strategy_id"])  # 0=raw, 1=total_return
```

These make provider health and the active pricing mode visible on the existing Grafana without log-diving.

**Per-rebalance evidence signal (owner review #6, #7, #9).** Each rebalance that touches TR pricing writes one `PORTFOLIO` info signal (`reason="total_return_pricing"`) — the audit trail of exactly how pricing was constructed:

```json
{
  "reason": "total_return_pricing",
  "pricing_method": "TOTAL_RETURN",         // or "RAW" — feature-state (#7)
  "report_only": false,
  "provider": "alpaca",                      // versioning metadata (#9)
  "provider_sdk": "alpaca-py 0.43.5",
  "fetched_at": "2026-07-06T14:40:12Z",
  "window": ["2024-01-01", "2026-07-06"],
  "symbols": 9,
  "dividends": 27,
  "splits": 1,
  "rejected": 0,
  "fallback": false,
  "elapsed_ms": 410,
  "divergence_bps": { "TLT": 38.2, "IEF": 21.7, "...": 0.0 }   // report-only: raw-vs-TR trailing-return delta
}
```

`pricing_method` in every report removes the "which pricing produced this book?" ambiguity months later. `provider`/`provider_sdk`/`fetched_at`/record counts give reproducibility if a vendor later revises historical actions (#9). In `report_only` mode `fallback` stays the effective state and `divergence_bps` is populated; when enabled, `divergence_bps` may be omitted (the panel *is* TR).

### §4.5 — Future multi-provider abstraction (documented, not built — owner review #8)

The `DistributionsProvider` Protocol (`total_return.py:93`) is already the seam; this session implements exactly one concrete provider. The intended future shape (no code this session):

```
DistributionsProvider  (Protocol, exists)
  ├─ AlpacaDistributionsProvider   (this session)
  ├─ SharadarDistributionsProvider (future — once ETF coverage exists; today it's empty)
  ├─ PolygonDistributionsProvider  (future)
  └─ YahooDistributionsProvider    (future — needs a vendor ADR)
```

A future selector could pick per-symbol-class (equities → Sharadar `closeadj` already; ETFs → Alpaca) or cross-check providers for the versioning use case (#9). Building any second provider is out of scope and, for Yahoo, gated on a new-dependency ADR.

**Future considerations roadmap (signalled, not scoped this session):**
- Persistent corporate-action cache / table (survives restarts; enables historical replay).
- Cross-provider reconciliation & multi-source validation (Alpaca vs Sharadar/Polygon).
- Historical replay of TR pricing into the offline reproduction harness.
- Provider failover (auto-switch on sustained `fail_open` rate).
- Automatic stale-data detection (alert when the newest distribution is older than expected for a coupon-payer).

## 5. Manual smoke (end-of-session)

Run **on the box** (read-only; no order path, no live-book change):

```bash
ssh workbench && cd /opt/workbench/app
# 1) provider + preview: real distributions, TR-vs-raw divergence for the 9 ETFs
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T backend python scripts/preview_total_return_pricing.py
# expect: nonzero dividends for TLT/IEF/DBC/GLD/SPY/EFA/EEM; TR return > raw return for the coupon-payers
# 2) offline unit tests (parsing, validation, retry, fail-open, wiring)
uv run pytest tests/market_data/test_alpaca_distributions.py tests/strategies/test_combined_book_template.py -q
# 3) metrics registered (no scrape needed — import + registry presence)
uv run python -c "from app.observability import metrics as m; print(m.workbench_distribution_requests_total)"
```

Load-bearing assertion: with `use_total_return_pricing` still **False**, a rebalance dry-run (or `preview_beta_cap_live.py`) produces the **same** target book as before this session (default-OFF ⇒ no behavior change). The TR effect appears only in the preview/report-only output, and the `total_return_pricing` evidence signal records `pricing_method` + provider metadata.

### §5.1 — Success criteria (checklist before merge)

- ☐ All new + existing unit tests pass (`test_alpaca_distributions.py`, `test_combined_book_template.py`); ruff + mypy clean.
- ☐ Preview script (`preview_total_return_pricing.py`) completes on the box and shows nonzero dividends for TLT/IEF/DBC/GLD.
- ☐ The six metrics import and register (`workbench_distribution_*`, `workbench_pricing_mode`).
- ☐ Report-only divergence is generated (a `total_return_pricing` signal with `divergence_bps`).
- ☐ **Default OFF produces a byte-identical target book** vs pre-session (the load-bearing assertion).
- ☐ Enabling TR changes **only** the pricing panel (weights differ solely via the TR inputs, not the algorithm).
- ☐ **No regression in the beta-cap governor** (it runs on the same `_close_panel`; its report still fires).
- ☐ No additional failed rebalances attributable to the provider (fail-open holds).
- ☐ Evidence artifact (JSON preview + signal) generated and inspectable.

## 6. Walk-away discipline

≥ **1 hour** (routine session — additive, default-OFF, no order-path or audit-subsystem change, no new external dependency). Not a §5/§7/§8-class change. The subsequent *enablement* (flipping `use_total_return_pricing=True` on the live book) is a separate owner decision with its own review of the report-only divergence — not part of this session.

### §6.1 — Rollback

Rollback is a **param flip, no data migration** — the cheapest possible reversal:

1. Set `use_total_return_pricing=False` (and `tr_pricing_report_only=False` if desired) on id=9.
2. `restart backend` (resume-on-boot re-registers) — or, if enabled via the audited API PUT, stop→PUT→start.
3. The next rebalance prices on raw closes again.

No migration, no data conversion, no cleanup — the provider is read-only and stateless across runs, and TR pricing never wrote anything persistent. Nothing to unwind intra-week (the panel only matters at rebalance time). Same mechanics and caveats as the beta-cap governor flip (`docs/runbook/beta-cap-governor.md`); a companion runbook section will be added when the feature is first enabled.

## 7. What this session does NOT do

- Does **not** enable TR pricing on the live book — ships default-OFF, flipped later by param after reviewing the report-only divergence.
- Does **not** touch the equity momentum sleeve — it already prices from Sharadar `closeadj` (split/div-adjusted); adding TR there would double-adjust.
- Does **not** add a Sharadar- or Yahoo-backed distributions provider — Sharadar has zero ETF coverage; Yahoo is a separate vendor decision (would need an ADR).
- Does **not** retrofit the offline PORT-001 reproduction harness with TR (the sibling-fidelity gate used its own panel; out of scope here).
- Does **not** add persistent caching / a corporate-actions table — one batched weekly fetch is cheap; a cache is a later optimization.
- Does **not** surface TR pricing in the frontend.
- Does **not** add a new ADR — Alpaca is already a sanctioned dependency and this is the deferred live wiring of an already-accepted capability (ADR 0030 #2).

## 8. Notes & gotchas

1. **Source decision is data-driven, not preference.** Sharadar `actions`/`sep` return **zero** rows for all 9 ETFs (verified on the box 2026-07-04). Do not "reuse the already-ingested Sharadar path" — it has nothing for these symbols. Alpaca corporate-actions is the only viable live source.
2. **Norton gate is laptop-only.** The `total_return.py` deferral note ("Norton blocks `data.alpaca.markets`") applies to the dev laptop, not the AWS box. Live fetch from the box is confirmed working (returned e.g. `DBC 2025-12-22 rate=0.744`, `IEF 2025-06-02 rate=0.310`, and `NVDA` forward-split `new_rate=10/old_rate=1`).
3. **Split multiplier direction:** `s = new_rate / old_rate` (forward > 1, reverse < 1). The `total_return_index` formula (`r_t = s_t·(c_t + d_t)/c_{t-1} − 1`) expects exactly this — a forward split drops raw `c_t`, and `s_t` restores continuity.
4. **Batch, don't loop.** One `CorporateActionsRequest(symbols=[…9 ETFs…])` returns everything; group by `.symbol`. Per-symbol calls waste 8 round-trips per rebalance.
5. **alpaca-py version drift:** the box runs 0.43.5; `pyproject.toml` only pins `>=0.30,<1.0`. `CorporateActionsClient` exists across that range, but keep the import defensive.
6. **Enablement mirrors the governor.** When the owner later flips `use_total_return_pricing=True`, the box user-7 API login currently 401s, so the flip will likely use the DB-params-edit + `restart backend` fallback (see `docs/runbook/beta-cap-governor.md`) — and that path is **not** audit-logged. Consider fixing the box login so pricing/risk-relevant param flips go through the audited API PUT.
7. **Report-only first.** Prefer landing this with `tr_pricing_report_only` enabled for one rebalance to capture the live divergence, then flip `use_total_return_pricing=True` — same review discipline as lever #2.
8. **Validation is drop-and-continue, never raise.** A malformed vendor record must reduce a symbol to raw pricing at worst, never abort the rebalance. Every reject is counted (`workbench_distribution_records_total{kind="rejected"}`) so silent data loss is visible.
9. **Metric cardinality.** `workbench_pricing_mode` is labelled by `strategy_id` only (low cardinality). Do **not** add per-symbol labels to the counters — 200+ equity symbols would blow up the series count; per-symbol divergence lives in the evidence signal payload, not in Prometheus.
10. **Rollout order for the added surface.** Metrics + evidence signal are always-on (cheap, no behavior change); the *pricing* change stays behind `use_total_return_pricing`. So even before enabling TR, you get provider-health metrics and a report-only divergence trail — the observability lands ahead of the behavior.
11. **Provider decomposition deliberately deferred (owner review, final).** The provider concentrates fetch + validate + group + cache + retry + metrics in one class. The owner explicitly flagged a future layered split (`Client → Retry → Validation → Cache → Provider`) but judged it **over-engineering for a 9-symbol weekly fetch** — do NOT build it now. Revisit only if this grows to hundreds of symbols, multiple providers, or higher-frequency rebalancing. Keeping the concerns as clearly-named private methods within the one class preserves an easy future extraction.
