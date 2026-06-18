# Factor Data Acquisition Guide — current architecture (FMP) and the SF1 upgrade path

| Field | Value |
|---|---|
| Document version | **v1.0 — frozen.** Supersedes the v0.1 premise that "SF1 is the blocker." |
| Date | 2026-06-18 |
| Purpose | Where factor data comes from **today** (prices + fundamentals), what that data has already told us, how it's refreshed/validated, and when — if ever — to buy the Sharadar SF1 fundamentals bundle. |
| Audience | The owner (a business + setup decision), and any future-self reconstructing the data architecture. |
| Related | ADR 0018 (PIT factor data: FMP + Sharadar); `TradingWorkbench_FMP_vs_SF1_Eval_v0.1.md`; `TradingWorkbench_Strategy_Research_Report_v1.0.md` §5.4 (Value/Quality result); `app/factor_data/store.py`, `app/factor_data/providers/fmp.py`, `scripts/ingest_fmp.py`, `app/factor_data/factors/fundamental.py` |

> **Change history.** v0.1 (2026-06-16) framed Sharadar **SF1** as the data blocker for Value/Quality research and recommended buying the "Core US Fundamentals" bundle. That premise was **obsolete**: the existing **FMP** key already supplies point-in-time fundamentals, the Value/Quality study has since **run to completion**, and the conclusion was *not* "we can't test" — it was "**those factors don't improve our current universe.**" v0.2 documented the real, shipped architecture and reframed SF1 as an **optional future upgrade**. **v1.0 (this version)** adds the dataset-confidence table, the full data-lineage, and an operational-notes section (refresh + validation), and is **frozen** — change it only when the architecture changes.

---

## 1. TL;DR

- **The data block is solved — nothing needs to be bought.** Prices come from Sharadar **SEP**; fundamentals come from **FMP** (Financial Modeling Prep) on its `/stable` API, using a key we **already own**. Both are read-only, point-in-time, and sanctioned by **ADR 0018**.
- **Value & Quality were already tested** (Research Report §5.4, v1.1). On the top-200-liquid universe, IS 2016–22 / OOS 2023–26, **every value/quality factor is negative or flat out-of-sample; only momentum survives.** This is a *universe + regime* result (mega-caps in a growth/momentum regime), **not** "value is dead." The multi-factor book is therefore **deferred, not built**.
- **Sharadar SF1 is sample-only on our current Nasdaq key** (2 annual rows for AAPL) and is **not used** — there is no `sf1` table in the store. We don't need it, because FMP covers the same Value/Quality inputs.
- **SF1 becomes worth buying only at a later stage** (broad multi-factor research, institutional deployment, external investors). See the decision table in §4.

---

## 2. Current data architecture

```
 PRICES                                  FUNDAMENTALS
 ──────                                  ────────────
 Sharadar SEP                            FMP  (/stable API, existing key)
   │  daily OHLCV (adj/unadj)              │  income / balance / cash-flow / ratios / key-metrics
   ▼  scripts/ingest_sharadar.py           ▼  scripts/ingest_fmp.py
 store: sep                              store: fundamentals  (PIT: accepted_date)
   │                                       │
   ▼                                       ▼
 momentum factor  (PRODUCTION)           value + quality factors  (TESTED → no OOS edge yet)
   app/factor_data/factors/momentum.py     app/factor_data/factors/fundamental.py

 UNIVERSE / METADATA
 ───────────────────
 Sharadar TICKERS + ACTIONS  →  store: tickers, actions  (PIT universe, sector/industry, splits)
```

**Full lineage — where it flows next** (the guide links into the research platform; ADR 0019):

```
 provider  →  store (DuckDB)  →  factors  →  research  →  portfolio construction
 (SEP/FMP)    (sep/fundamentals  (momentum,   (scripts/      (P10 §3 — weighting,
              /tickers/actions)   value, qual) factor_research benchmarks, gate)
                                                + research engine)
```

**Store tables** (`app/factor_data/store.py`; DuckDB at `apps/backend/data/factor_data.duckdb`, plus the full-history `factor_data_full.duckdb`):

| Table | Source | Primary key | Holds | Feeds |
|---|---|---|---|---|
| `sep` | Sharadar SEP | `(ticker, date)` | daily OHLCV, `closeadj`/`closeunadj` | momentum (price factors) |
| `fundamentals` | **FMP** `/stable` | `(ticker, period, period_end)` | revenue, gross profit, EBITDA, net income, FCF, debt, equity, assets, shares, EV — with `filing_date` + **`accepted_date`** | value + quality factors |
| `tickers` | Sharadar TICKERS | `(ticker)` | universe metadata + `sector`/`industry` | PIT universe, sector caps |
| `actions` | Sharadar ACTIONS | — (replace-per-ticker) | splits / dividends / delistings | corporate-action handling |
| `ingest_runs` | — | — | ingest bookkeeping (status, rows) | operability |

**Point-in-time discipline (the correctness invariant).** Fundamental factors join on **`accepted_date <= as_of`** — the SEC acceptance timestamp, i.e. the date the statement was actually knowable — so no factor can read a filing before it existed. Prices use trading-day row offsets on or before `as_of`. This is what keeps the survivorship-free / no-look-ahead guarantee (ADR 0018).

### Dataset confidence

A reader's-eye view of how much weight to put on each source (subjective grades, not a vendor SLA):

| Dataset | Source | Confidence | In production? | Notes |
|---|---|---|---|---|
| Prices (`sep`) | Sharadar SEP | **A** | Yes | survivorship-free, split/div-adjusted, long history; the momentum edge rests on it |
| Fundamentals (`fundamentals`) | FMP `/stable` | **A−** | Yes | ~40y quarterly+annual with `acceptedDate`; coverage 197/200 of the liquid universe; restatement handling is the main caveat |
| Universe/metadata (`tickers`, `actions`) | Sharadar | **A** | Yes | sector/industry + corporate actions drive PIT eligibility |
| Fundamentals (`sf1`) | Sharadar SF1 | **A+** *(if owned)* | **No** | sample-only on our key; the institutional-grade upgrade (§4) |
| Options / alt-data | — | N/A | No | out of scope (factor-equities program) |

---

## 3. What the data has already told us

The Value/Quality factor code is **implemented** (`app/factor_data/factors/fundamental.py`): Value = `earnings_yield`, `fcf_yield`, `sales_yield`; Quality = `roe`, `gross_profitability`, `roic`, `debt_to_equity`. It was run against FMP fundamentals (197/200 names, 5,762 annual statements) via `scripts/factor_research.py --with-fundamentals`.

**Result (Research Report §5.4, v1.1 — top-200 liquid names, IS 2016–22 / OOS 2023–26):**

| Factor | OOS IC | OOS LS-Sharpe | Verdict |
|---|---|---|---|
| `mom_12` | +0.060 | **+1.33** | ✅ the edge |
| `debt_to_equity` | +0.001 | +0.87 | flat / noise |
| `gross_profitability` | −0.017 | −1.47 | ❌ IS t≈1.9 → collapses OOS |
| `roic` | −0.031 | −1.79 | ❌ negative |
| `roe` | −0.038 | −1.82 | ❌ negative |
| `earnings_yield` | −0.041 | −1.78 | ❌ negative |
| `fcf_yield` | −0.053 | −1.92 | ❌ negative |

**Why** (not "value is dead"): top-200-by-liquidity = mega-caps; 2023–26 was an extreme growth/momentum regime where cheap/defensive lost. The value/quality factors are highly inter-correlated (0.8–0.97), correlated with low-vol (also negative OOS), and **negatively correlated with momentum on this universe** — they are momentum's opposite here, not a diversifier. So: **do not blend them into the momentum book; the multi-factor book is deferred** until a broader universe / different regime justifies a re-test.

Momentum (the 12-month variant) is the production edge and the basis for the P10 portfolio-construction research.

---

## 4. The SF1 question — optional upgrade, not a blocker

Sharadar **SF1** (Core US Fundamentals) is **sample-only** on our current Nasdaq Data Link key — probing it returns ~2 annual rows for AAPL, not a subscription. We **do not ingest it** and there is **no `sf1` table**. That is fine, because FMP already provides everything Value/Quality needs (quarterly + annual, ~40y back to 1986, PIT timestamps). The `TradingWorkbench_FMP_vs_SF1_Eval_v0.1.md` evaluation reached the same conclusion: **no purchase needed today.**

SF1's advantages over FMP are about *institutional confidence*, not *capability*: a single survivorship-free vendor with rigorously reconciled point-in-time `datekey`s and uniform coverage. Those matter at a later maturity stage, not for current research.

### When should we upgrade to SF1?

| Situation | Buy SF1? | Why |
|---|---|---|
| Current momentum book | **No** | Price-only; SF1 irrelevant. |
| Current portfolio-construction research (P10 §3) | **No** | Uses prices + the existing FMP fundamentals; no gap. |
| Broader multi-factor research (more names, deeper history, higher PIT confidence) | **Maybe** | If FMP coverage/restatement handling becomes the limiting factor, SF1's uniform PIT history is worth pricing. |
| Institutional deployment | **Yes** | A single audited, survivorship-free vendor simplifies the data-lineage story. |
| External investors / audited track record | **Yes** | Reproducible PIT provenance from one reconciled source. |

---

## 5. If/when you upgrade — the (small) code work

The pipeline is already fundamentals-shaped (FMP), so adding SF1 later is **additive and bounded**, not a rewrite:

1. **Subscribe** to Sharadar "Core US Fundamentals" (SF1 + DAILY) on the same Nasdaq key — confirm current pricing and that the license matches research/paper use on the product page (`https://data.nasdaq.com/databases/SF1`).
2. **Store:** add an `sf1` table (PK `ticker, dimension, datekey`) and optionally `daily` — mirror the existing `sep`/`fundamentals` ingest pattern in `store.py`.
3. **Ingest:** extend `scripts/ingest_sharadar.py` to pull SF1 (dimensions ARQ + MRQ) and DAILY, bounded by `--from` for the rate cap.
4. **Accessor:** a PIT `get_fundamentals(ticker, as_of)` join on `datekey <= as_of` — the same discipline the FMP path already uses with `accepted_date`.
5. **Factors:** the value/quality factors in `fundamental.py` already exist; point them at the SF1-backed source and **re-run the IS/OOS study on the broader universe** the upgrade enables. The interesting question is whether value/quality earn their keep *off the mega-cap universe* — that is the actual reason to buy SF1, not "to test at all."

Estimate: ~1–2 days once the data is live (the factor engine and study harness are reusable).

---

## 6. Verify the current path (no purchase required)

**Fundamentals are already in the store** — confirm with a read-only query:

```bash
cd apps/backend
.venv/Scripts/python.exe -c "
import duckdb
con = duckdb.connect('data/factor_data.duckdb', read_only=True)
n, ntk = con.execute('SELECT count(*), count(DISTINCT ticker) FROM fundamentals').fetchone()
print(f'{n} fundamental rows across {ntk} tickers')
print('PIT column present:', 'accepted_date' in [c[0] for c in con.execute('DESCRIBE fundamentals').fetchall()])
"
```
Expected today: `5762 fundamental rows across 197 tickers` and `PIT column present: True`.

**Re-run the factor study with fundamentals** (regenerates `research/factor_report.md`):

```bash
cd apps/backend
.venv/Scripts/python.exe scripts/factor_research.py --with-fundamentals --n 200 --split 2023-01-01
```
Expected: momentum positive OOS; value/quality factors negative or flat OOS (the §5.4 result).

**Re-ingest / extend FMP fundamentals** (if adding names or refreshing):

```bash
cd apps/backend
.venv/Scripts/python.exe scripts/ingest_fmp.py --tickers AAPL,MSFT --period annual
```

---

## 7. Operational notes — refresh & validation

> **Honesty note:** refresh is **manual today** (run the ingest scripts); there is no scheduler/cron wired for factor data. The cadence below is the **recommended policy**, not an automated guarantee. The "enforced today" items, by contrast, are real (DuckDB constraints + ingest logic in `store.py`).

**Refresh — recommended cadence (run manually for now):**

| Dataset | Recommended cadence | Command | Rationale |
|---|---|---|---|
| Prices (`sep`) | per trading day (or before a study) | `scripts/ingest_sharadar.py` | momentum reads the latest close |
| Fundamentals (`fundamentals`) | weekly (statements only arrive quarterly) | `scripts/ingest_fmp.py` | weekly polling far exceeds the quarterly filing rate |
| Universe/metadata (`tickers`, `actions`) | monthly | `scripts/ingest_sharadar.py` | listings/sector/corporate-actions drift slowly |

Each run is recorded in `ingest_runs` (`dataset, started_at, finished_at, rows, status`) for auditability.

**Validation — what's enforced today (real):**

- **No duplicate keys.** `sep`, `tickers`, `fundamentals` are written with `INSERT OR REPLACE` keyed by their PRIMARY KEY, so re-ingesting **converges** (idempotent upsert) rather than duplicating; `actions` is replace-per-ticker.
- **Key fields non-null.** PKs are `NOT NULL` (`sep.ticker/date`, `fundamentals.ticker/period_end`), so a row with no ticker or period can't land.
- **PIT integrity.** Fundamental factors only read rows with `accepted_date <= as_of`; rows lacking `accepted_date` are excluded from as-of joins (no silent look-ahead).
- **Run accounting.** `ingest_runs` row count + `status` ('running'|'ok'|'failed') per dataset.

**Validation — recommended (not yet automated):** coverage thresholds (e.g. alert if < N% of the universe has fundamentals), stale-provider detection (alert if `lastupdated` falls behind), and a post-ingest sanity report. These are worth building if/when ingestion becomes scheduled rather than operator-driven.

---

## 8. References

- **ADR 0018** — `docs/adr/0018-point-in-time-factor-data-fmp-sharadar.md` — sanctions FMP + Sharadar as read-only external data dependencies with PIT discipline; never touch the order path.
- **FMP vs SF1 evaluation** — `docs/implementation/TradingWorkbench_FMP_vs_SF1_Eval_v0.1.md` — "the data block is effectively already solved; no purchase needed"; FMP `/stable` returns ~40y quarterly+annual with `acceptedDate`.
- **Value/Quality result** — `docs/implementation/TradingWorkbench_Strategy_Research_Report_v1.0.md` §5.4 (v1.1) — no robust OOS edge on the current universe; multi-factor book deferred.
- **Code** — provider `app/factor_data/providers/fmp.py`; ingest `scripts/ingest_fmp.py`; factors `app/factor_data/factors/fundamental.py`; store schema `app/factor_data/store.py`; study `scripts/factor_research.py`.

---

## 9. Out of scope for this guide

- **Building the multi-factor book** — deferred per §3; it is a research decision gated on a broader universe / regime, not a data-acquisition task.
- **Adding a new external data vendor** (Polygon, etc.) — would require its own ADR (ADR 0018 governs the current two: FMP + Sharadar).
- **Options / alternative-data acquisition** — out of the factor-research scope; the program direction is factor equities, not options.
- **The momentum upgrade and risk overlays** — those are price-only research items tracked in the Research Report, independent of fundamentals.
- **Automated ingestion scheduling** — the refresh cadence in §7 is recommended policy; wiring a scheduler is future operational work, not part of this guide.
