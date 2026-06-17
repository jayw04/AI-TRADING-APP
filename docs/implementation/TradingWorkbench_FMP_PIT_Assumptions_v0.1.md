# FMP fundamentals — point-in-time assumptions & data-risk control (R2)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-17 |
| Phase | P10 — factor research (R2 data layer) |
| Scope | Exactly how the FMP fundamentals feed is used, and the look-ahead / survivorship assumptions a factor study built on it depends on. |
| Related | ADR 0018 (FMP/Sharadar factor data); `..._FMP_vs_SF1_Eval_v0.1.md`; code: `app/factor_data/providers/fmp.py`, `scripts/ingest_fmp.py`, `app/factor_data/store.py` (`fundamentals`, `get_fundamentals`) |
| Purpose | The reviewer's **"main data-risk control"**: document the endpoint, the filing/accepted-date field, restated-vs-as-reported handling, survivorship universe construction, and delisted coverage — so anyone trusting a Value/Quality result knows what it rests on. |

This is the data-risk control for every fundamentals-based study (the Value/Quality
study, any future multi-factor work). A factor result is only as honest as these
assumptions; record them here and check a study against them before trusting it.

## 1. Endpoints used (FMP `/stable`)

The legacy `/api/v3` + `/api/v4` endpoints are retired for our key (403); we use
the current `/stable` API (`FMPProvider`, base
`https://financialmodelingprep.com/stable`).

| Purpose | Endpoint | Used by |
|---|---|---|
| Income statement | `income-statement` | `ingest_fmp` → `fundamentals` |
| Balance sheet | `balance-sheet-statement` | `ingest_fmp` |
| Cash flow | `cash-flow-statement` | `ingest_fmp` |
| Enterprise value / metrics | `key-metrics` | `ingest_fmp` |
| Sector (crash study) | `profile` | `momentum_crash_study` |
| Benchmarks SPY/QQQ | `historical-price-eod/full` | `momentum_crash_study` |

Period: **annual (`FY`)** for the ingested fundamentals to date. Quarterly is
available (`period=quarter`) and tier-permitted, but the current `fundamentals`
store + study use FY rows.

## 2. Point-in-time field — `acceptedDate`

Every statement carries `date` (fiscal period end), `filingDate` (SEC filing
date), and `acceptedDate` (SEC acceptance timestamp). We store all three and treat
**`acceptedDate` as the "knowable-on" instant**.

`FactorDataStore.get_fundamentals(ticker, as_of)` returns only rows with
`COALESCE(accepted_date, filing_date) <= as_of`. So on a rebalance date the factor
layer sees only statements **accepted on or before that date** — a statement filed
later is invisible. The Value/Quality factor build (`factors/fundamental.py`)
applies this via `merge_asof` on `accepted_date`. **This is the core no-look-ahead
guarantee.**

## 3. Restated vs as-reported — the known residual risk ⚠

**We ingest the STANDARD statement endpoints, which return RESTATED values** (the
company's latest figures for each historical period), tagged with that period's
**original** `filingDate`/`acceptedDate`.

The subtlety: if a company **restates** a past period (e.g. a 2019 figure revised
in a 2021 filing), our store shows the *revised* value carrying the *2019*
accepted date — so a backtest at a 2020 rebalance could "see" a number that, in
reality, was only known after the 2021 restatement. That is a **mild look-ahead**
on restated lines (and on `key-metrics` derived from them).

- **Magnitude:** small for most large-cap names (restatements are the exception,
  and material restatements rarer still), but it is a real, directional bias —
  it makes historical fundamentals look slightly "more knowable/accurate" than
  they were. It does **not** affect price/return or momentum factors.
- **Mitigation / upgrade path (available, not yet used):** FMP `/stable` exposes
  **as-reported** endpoints — `income-statement-as-reported` and
  `financial-statement-full-as-reported` (verified live; they return the
  as-filed line items under a `data` field). A higher-fidelity ingest would pull
  these and key on `acceptedDate`, eliminating the restatement look-ahead. We have
  **not** done this yet because (a) the current Value/Quality result was *negative*
  on our universe (§5.4 of the capstone) — restatement bias would only have
  *flattered* it, so removing it cannot rescue the thesis; and (b) it adds a
  different response shape (nested `data`) to parse. **Before trusting any
  *positive* Value/Quality result (e.g. on a broadened universe), switch to the
  as-reported endpoints** — that is the condition under which this residual risk
  becomes load-bearing.

## 4. Survivorship universe construction

**Survivorship-freeness comes from the Sharadar SEP store, not from FMP.** The
study universe is the top-N by trailing dollar volume drawn from `sep` (which
includes delisted names that were liquid as of a past date — see
`universe.py` / ADR 0018). FMP fundamentals are then fetched **per ticker** for
that universe (`ingest_fmp --tickers-file`).

- The current ingested universe is **today's top-200 liquid names** → it is
  dominated by *survivors*. So while the *price/universe* spine is survivorship-
  free, the *fundamentals* coverage has so far been exercised mostly on survivors.
- The FMP **`delisted-companies`** endpoint exists in the provider
  (`FMPProvider.delisted_companies`) for assembling a survivorship-free name list,
  but **is not yet wired into fundamentals ingestion**. A broadened-universe study
  must include delisted names and pull their fundamentals to stay honest.

## 5. Delisted ticker coverage ⚠

FMP fundamentals coverage for **since-delisted** names is **not yet verified** in
our pipeline (the top-200-liquid universe is almost all survivors). FMP does serve
delisted symbols' history via the delisted endpoints, but completeness/depth of
their *fundamentals* is untested here. **This is the second condition that gates a
broadened-universe Value/Quality re-test:** confirm delisted-name fundamental
coverage (spot-check a handful of known delistings) before drawing OOS conclusions
on a small/mid-cap universe — otherwise survivorship bias re-enters through the
fundamentals side even though the price spine is clean.

## 6. What a study built on this can and cannot claim

- **Can** claim PIT-honest *relative* factor rankings on the ingested universe, to
  the precision of the restated-values caveat (§3).
- **Cannot** yet claim survivorship-free *fundamentals* across delisted names
  (§4–§5), nor strict as-originally-reported PIT (§3), without the two upgrades.
- The current Value/Quality result (negative OOS on top-200 liquid) is **robust to
  both caveats** — they would only have helped value/quality, which still failed.
  The caveats become binding only for a **positive** result on a broadened
  universe; address §3 (as-reported) and §5 (delisted coverage) before trusting one.

## 6b. Data confidence levels

A quick-read confidence grade per source, so a research report's reliability is
legible at a glance (A = trust as-is; B = usable, known minor caveat; C = use with
care, a material residual bias until the §3/§5 upgrades land).

| Source | Confidence | Why |
|---|---|---|
| Prices (Sharadar SEP) | **A** | survivorship-free, adjusted, deep history; the spine |
| Momentum / price factors | **A** | derived from SEP only; no fundamentals dependency |
| Annual fundamentals (FMP FY) | **B** | full coverage + `acceptedDate` PIT lag; restated-values caveat (§3) |
| Quarterly fundamentals (FMP) | **B** | available, same restated caveat; not yet used in studies |
| Restated metrics (key-metrics / ratios) | **C** | standard endpoints = restated; mild look-ahead until as-reported (§3) |
| Delisted-name fundamentals | **C** | coverage unverified; universe ≈ survivors (§5) |
| Benchmarks SPY/QQQ (FMP EOD) | **A** | index ETFs, well-covered; correlation/beta only |
| Sector (FMP profile) | **B** | current sector classification, not point-in-time (sectors rarely change, but it's today's label) |

Rule of thumb: an **A/B**-only study is trustworthy as-is; any result leaning on a
**C** source needs the §3 (as-reported) and/or §5 (delisted coverage) upgrade
before it is acted on.

## 7. Checklist before trusting a new fundamentals study

1. Confirm `acceptedDate` PIT lag is in force (`get_fundamentals(..., as_of=)`).
2. If the result is **positive**, switch ingestion to the **as-reported**
   endpoints (§3) and re-run.
3. If the universe includes small/mid-caps, **include delisted names** (§4) and
   spot-check their fundamental coverage (§5).
4. Re-state the universe, period (FY vs quarter), and date window in the report.
