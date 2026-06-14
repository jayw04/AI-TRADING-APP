# P9 Session Zero v0.1 — Factor-Data Access Verification (FMP + Sharadar)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-13 |
| Phase | **P9** — Point-in-time data backbone + multi-factor equity model |
| Session | **§0 (Session Zero)** of P9 — pre-flight go/no-go, ships no product code |
| Predecessor | P8 closed (tag `p8-q4-scan-apply-template-complete`); P9 Direction v0.2 + ADR 0018 (PR #97) |
| Successor | P9 §1 — Sharadar price/universe spine in DuckDB |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Governing ADRs | 0018 (FMP + Sharadar PIT factor data), 0017 (OS trust store for outbound TLS), 0003 (credential encryption — credential-storage posture) |
| Scope | Empirically verify that both vendor keys authenticate, return the datasets P9 needs at the expected **survivorship-free / point-in-time** quality and depth, under the ADR-0017 TLS path; produce a **go/no-go** for §1. |
| Estimated wall time | 2–4 hours |
| Tag on completion | none — Session Zero is a go/no-go gate; findings recorded in §6 + a verification script committed |
| Out of scope | Any ingestion, the DuckDB store, factor math, product code (see §8) |

---

## 1. Why this session exists

P9's entire value rests on a single unverified assumption: that the two subscriptions
actually deliver **survivorship-free, point-in-time** data at usable depth and rate limits.
ADR 0018 was written against the owner's coverage analysis (`data/Data available {1,2}.jpg`),
not against live API responses. Before §1 builds a DuckDB ingestion layer and a
`universe_asof()` against these vendors, Session Zero proves the assumptions empirically —
exactly the "verify infrastructure before building on it" discipline that has repeatedly
caught fabricated capability in this project (Retrospective; the `# VERIFY-CAPABILITY-EXISTS`
habit).

The load-bearing thing to confirm is **survivorship-freeness**: that delisted names are
present with history, and that S&P 500 membership can be reconstructed *as of* a past date.
If that fails, the factor backtests cannot be honest and §1 should not start as planned.

## 2. What this session ships

1. **`apps/backend/scripts/verify_factor_data_access.py`** — a host-venv verification script
   (no Docker, no stack) that hits both vendors over REST, prints per-dataset shapes, and
   runs a PASS/FAIL battery ending in a `RESULT: GO|NO-GO` line with a non-zero exit on any
   hard failure. Mirrors the existing `validate_range_insight_live.py` / `verify_tls_trust.py`
   precedent.
2. **A filled findings section (§6)** in this doc: per-dataset schema, date depth, row
   counts, rate limits, the S&P-500-membership construction approach, and the
   REST-vs-SDK dependency decision.
3. **A go/no-go signal** for P9 §1, with any gap stated explicitly.

No product code, no new runtime dependency is committed in §0 (the script uses `httpx` /
`pandas`, already backend deps — see §7 note 1).

## 3. Prerequisites

- `FMP_API_KEY` and `NASDAQ_DATA_LINK_API_KEY` present in `.env` (confirmed 2026-06-13).
- ADR-0017 OS-trust-store path **merged to `main` (`d5a9596`)** — genuinely available, so calls
  succeed under Norton inspection from the host venv (proven 2026-06-13 by the AAPL fixture gen).
- P9 Direction v0.2 + ADR 0018 **Accepted 2026-06-13 (merged in PR #97)** — §0 verifies the
  data that direction assumes; its filled §6 is the evidence of record behind that acceptance.
- Host backend venv (`apps/backend/.venv`) — the script runs there, not in Docker.

## 4. Detailed verification work

All calls are **read-only REST** with the key as a query param, each wrapped so a vendor
outage degrades to a recorded FAIL rather than a crash. Inject the OS trust store first
(`truststore.inject_into_ssl()`, ADR 0017) before any HTTPS, exactly as the fixture-gen path
does.

### 4.1 Nasdaq Data Link → Sharadar (the v1 spine)

Datatables REST base: `https://data.nasdaq.com/api/v3/datatables/SHARADAR/<TABLE>.json?...&api_key=$NASDAQ_DATA_LINK_API_KEY`
(tables paginate via `qopts.cursor_id`; record that).

- **SEP — survivorship-free adjusted prices.** Pull a liquid name and an *old* range:
  `SHARADAR/SEP.json?ticker=AAPL&date.gte=1998-01-01&date.lte=1998-03-31`. Confirm:
  columns (`ticker,date,open,high,low,close,volume,closeadj,closeunadj,lastupdated`),
  history reaches **1998**, and `closeadj` (the split/div-adjusted close P9 prices from)
  is present.
- **★ Survivorship-free proof (load-bearing).** Pull a **known delisted** name (e.g. a
  Lehman/`LEH`-class delisting, or any `isdelisted='Y'` ticker found via TICKERS) from SEP
  and confirm price history **exists and ends at the delisting**, not "no such ticker." This
  is the single check that decides whether honest backtests are possible.
- **TICKERS — as-of universe.** `SHARADAR/TICKERS.json?table=SEP`. Confirm ~62k rows and the
  fields P9 needs: `ticker,name,exchange,category,isdelisted,firstpricedate,lastpricedate`.
- **ACTIONS — corporate actions.** `SHARADAR/ACTIONS.json?ticker=AAPL`. Confirm split / div /
  delisting events with dates.
- **★ S&P 500 point-in-time membership.** The chosen universe is S&P 500, so we must be able
  to reconstruct membership **as of a past date**. The owner's analysis flagged
  `SP500 constituents: historical change-log FULL, current membership sampled — use TICKERS
  instead`. Verify the actual mechanism: query `SHARADAR/SP500.json` and confirm the
  **historical add/remove change-log is full** (so `sp500_universe_asof(date)` is
  reconstructable), and cross-check coverage against TICKERS. **Record the exact construction
  recipe** §1 will implement. If the change-log is *not* full, record the fallback (e.g. a
  maintained membership list) — this is a §1-blocking finding.
  - **★ Earliest change-log date vs the backtest window (data-quality trap).** "Full" is not
    enough — record the **earliest date the SP500 change-log reaches**. If the change-log
    floor (say ~2008) post-dates the SEP price history (1998), the pre-floor universe is
    **unreconstructable**, and a momentum backtest to 1998 would silently fall back to a wrong
    (likely survivorship-biased) universe. If the floor post-dates the intended window, that is
    a scope finding: either **start the momentum backtest at the change-log floor**, or
    document the universe-construction limitation explicitly. Record floor date + decision.
- **Full-vs-sample confirmation.** Empirically confirm SEP / TICKERS / ACTIONS return **full**
  (not 10-row sample) data; note that SF1 / DAILY / METRICS are sample-only (not used in v1).
- Record: per-table row counts, date ranges, pagination behavior, and the **rate limit**
  (premium concurrency/throughput) — needed to size the §1 S&P 500 batch ingest.

### 4.2 FMP (deferred layer — token verification only)

v1 is price-only, so §0 verifies FMP is *reachable and shaped as expected* but does **not**
build anything on it. REST base: `https://financialmodelingprep.com/api/v3/<endpoint>?...&apikey=$FMP_API_KEY`.

- **Fundamentals depth:** `income-statement/AAPL?period=annual&limit=20` — confirm auth (200),
  schema, and **record how many years actually return** (expected ~5 on Starter — this
  pins the deferred fundamental-backtest window).
- **Ratios:** `ratios/AAPL?limit=20` — confirm presence.
- **Earnings surprises:** `earnings-surprises/AAPL` — confirm presence (PEAD factor input).
- **Macro:** confirm a treasury/economic endpoint is accessible on the tier (record which).
- Record: the **rate limit** and any endpoints that 401/403 on the Starter tier. Capture this
  as a **structured §6 finding** — the *specific* gated endpoint names, not prose — so that
  when §5+ plans the fundamental layer it knows exactly which endpoints need a tier bump
  rather than discovering gated endpoints mid-build.

### 4.3 TLS + credential posture

- Confirm both vendors are reached through the **OS-trust-store** path (ADR 0017) with Norton
  active — i.e. no `CERTIFICATE_VERIFY_FAILED`. Same mechanism as the fixture gen.
- Confirm the keys load as `Settings` env-aliases (ADR 0018 §5) and are **never logged** —
  the script prints key *lengths*, never values.

### 4.4 Licensing (hard §0 finding)

Licensing is a **recorded §0 finding**, not a deferred "tracked" note. Sharadar / Nasdaq Data
Link and FMP both carry redistribution + derived-data clauses that can constrain even local
computation depending on tier. For the single-user local deployment this is almost certainly
fine — but record the answer now, cheaply, before the ADR-0018 multi-user trigger ever fires.
Record explicitly **both**:
- whether **raw vendor tables** may be re-exposed (API / MCP) — expected **no** (ADR 0018 §6);
- whether **derived factor scores** (surfaced in Discovery filters, or a strategy others could
  see) may be exposed — the subtler question a hosted deployment would hit.

### 4.5 Verification script shape

```text
apps/backend/scripts/verify_factor_data_access.py   (host venv; no stack)
  truststore.inject_into_ssl()                       # ADR 0017, before any HTTPS
  settings = get_settings()                          # FMP_API_KEY / NASDAQ_DATA_LINK_API_KEY
  checks = []                                         # (name, ok: bool, detail: str)
  # --- Sharadar ---
  checks += sep_recent(), sep_history_1998(), sep_delisted_name()   # ★ survivorship
  checks += tickers_universe(), actions(), sp500_membership_asof()  # ★ PIT membership
  # --- FMP (token) ---
  checks += fmp_fundamentals_depth(), fmp_ratios(), fmp_earnings(), fmp_macro()
  print_table(checks); print(f"RESULT: {'GO' if all_ok else 'NO-GO'}")
  sys.exit(0 if all_ok else 1)
```

Run: `PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/verify_factor_data_access.py`

## 5. Go / No-Go criteria

**GO** (all must hold):
1. Both keys authenticate (200) over the OS-trust-store path under Norton.
2. SEP returns survivorship-free history to ~1998 **including a delisted name**, with
   `closeadj`.
3. TICKERS returns the full universe with `isdelisted` / `firstpricedate` / `lastpricedate`.
4. **S&P 500 PIT membership is reconstructable** (SP500 change-log full, or a documented
   fallback).
5. ACTIONS returns corporate actions.
6. FMP authenticates and returns fundamentals (depth recorded), even though unused in v1.
7. Rate limits are not just "adequate" but **quantified**: record the **estimated total time
   to ingest the full S&P 500 SEP history (1998+) at the observed rate**. This number decides
   whether §1 is a 5-minute job or a 5-hour job — i.e. whether §1 must build
   checkpointing / resumability from the start.

**NO-GO** triggers (any one) → stop, record the gap, revise the Direction doc before §1:
- SEP/TICKERS are sample-only (not full) → no survivorship-free spine.
- Delisted names are absent from SEP → backtests cannot be honest.
- S&P 500 PIT membership cannot be reconstructed → `universe_asof` is unbuildable as planned
  (fallback: widen to a TICKERS-derived universe, or maintain a membership list — a Direction
  revision).

## 6. Results (filled on execution)

> Session Zero produces a record. Fill this in when the script runs; do not fabricate.

- Sharadar SEP: ______ (rows, date range, delisted-name check) — PASS/FAIL
- Sharadar TICKERS: ______ — PASS/FAIL
- Sharadar ACTIONS: ______ — PASS/FAIL
- S&P 500 PIT membership recipe: ______ — PASS/FAIL
- **S&P 500 change-log earliest date: ______ ; covers backtest window (1998+)? ______ ;
  decision if not: ______**
- FMP fundamentals depth: ______ years — PASS/FAIL
- FMP macro/earnings reachable: ______ — PASS/FAIL
- **FMP Starter gated endpoints (specific names): ______**
- Rate limits (Sharadar / FMP): ______ / ______
- **Estimated full S&P 500 SEP ingest time at observed rate: ______ → §1 checkpointing needed? ______**
- **Licensing — raw-table re-export permitted? ______ ; derived-score exposure permitted? ______**
- TLS under Norton (OS trust store): ______ — PASS/FAIL
- Dependency decision (REST vs SDK): ______
- **RESULT: GO / NO-GO** — ______

## 7. Walk-away discipline

≥ 1 hour (routine; ships only a verification script + findings, no runtime/order-path
surface). The PR is the script + this doc's filled Results.

## 8. What this session does NOT do

- **No ingestion / no DuckDB store** — that is §1.
- **No factor computation, no backtest, no strategy** — §2+.
- **No FMP integration beyond a token reachability check** — the fundamental layer is §5+.
- **No new runtime dependency** — REST via existing `httpx`/`pandas`; the `nasdaq-data-link`
  / `fmpsdk` SDK decision is *recorded* here, adopted (if at all) in §1.
- **No credential-store change** — keys stay `Settings` env-aliases (ADR 0018 §5).
- **No raw vendor data committed** to the repo (licensing posture, ADR 0018 §6) — only
  schema/shape findings.

## 9. Notes & gotchas

1. **Use existing deps.** `httpx` + `pandas` are already backend deps; raw REST avoids a new
   package install (and the Norton/pip friction). The Nasdaq Data Link datatables endpoint
   returns JSON/CSV that `pandas` reads directly. Adopt a vendor SDK only if §0 finds REST
   pagination/auth genuinely painful — record the call.
2. **Inject truststore first.** Any HTTPS before `truststore.inject_into_ssl()` will
   `CERTIFICATE_VERIFY_FAILED` under Norton. The app does this at startup (ADR 0017); a
   standalone script must do it explicitly (as the fixture-gen one-liner did).
3. **Survivorship-free is the honesty hinge.** The delisted-name SEP check (§4.1 ★) is the
   single most important assertion in P9 — it is the difference between an honest factor
   backtest and a misleading one. Do not hand-wave it.
4. **S&P 500 membership is a real subtlety.** "Current membership sampled, historical
   change-log full" means *today's* snapshot is unreliable but *as-of* membership is
   reconstructable from the change-log. §1's `universe_asof` depends on §0 nailing the exact
   recipe — record it precisely.
5. **Keys are operator-level, not per-user.** Print lengths, never values; do not write them
   to logs or the audit log (ADR 0018 §5; `structlog` redaction already exists for the named
   secrets — these are not on that list, so be deliberate).
6. **Depth split is expected, not a failure.** FMP returning ~5y is the documented Starter
   behavior, not a NO-GO — record it; price factors backtest from Sharadar to 1998.
7. **§6 Results is a permanent artifact, not a throwaway.** This is the first phase whose
   correctness — not just availability — cannot be unit-tested: survivorship-freeness is an
   empirical property of the *vendor's data*, not of our code. When the first momentum
   backtest prints a suspiciously good Sharpe, the first question will be "is the universe
   actually survivorship-free / PIT" — and the filled §6 is the answer of record. Keep it.
