# Factor Data Acquisition Guide — unlocking Value & Quality (SF1)

| Field | Value |
|---|---|
| Document version | v0.1 — for the owner (a business + setup decision) |
| Date | 2026-06-16 |
| Purpose | Exactly what data to acquire (and how) to unlock the Value/Quality + multi-factor research the report recommends, with verification and code implications. |
| Related | `TradingWorkbench_Strategy_Research_Report_v1.0.md` (§4 data blocker); `factor_research.py` |

---

## 1. What's missing, and the proof

The factor engine works; the **data subscription** is the gate. We use **Nasdaq Data Link** with the **Sharadar** publisher. Today's entitlement covers **SEP (daily prices)** — that's why momentum (price-based) studied fine — but **NOT the fundamentals table SF1**.

Evidence (probed 2026-06-16, current key):

```
AAPL SF1 (no filter)  -> 2 rows, dimension=MRY, datekeys 2022-09-24 .. 2023-09-30
AAPL SF1 dimension=ARQ -> 0 rows
```

Two annual rows ending 2023 is a **sample**, not a subscription. A point-in-time Value/Quality study needs years of quarterly fundamentals across the universe → **blocked by data, not code.**

## 2. What to acquire (recommended: stay on Sharadar)

Sharadar splits its catalog into bundles. We have the **prices** bundle; we need the **fundamentals** bundle:

| Sharadar table | Bundle | Have? | Gives |
|---|---|---|---|
| **SEP** | Equity Prices | ✅ | daily OHLCV (prices → momentum) |
| **SF1** | **Core US Fundamentals** | ❌ | financial statements + derived: revenue, EBITDA, net income, FCF, **ROIC, ROE**, gross profit, debt, shares, **enterprise value** → **Quality** + raw Value |
| **DAILY** | **Core US Fundamentals** | ❌ | daily-updated valuation ratios: marketcap, ev, **pe, pb, ps, evebit, evebitda**, divyield → **Value** (ready-made, no computation) |
| TICKERS / ACTIONS | both | ✅ | metadata, corporate actions |

**Target product: "Sharadar Core US Fundamentals"** (provides SF1 **and** DAILY). SF1 covers Quality; DAILY gives clean daily valuation ratios for Value with minimal computation and built-in point-in-time correctness.

**Why stay on Sharadar:** our provider **already fetches SF1** (the probe returned the full SF1 schema — `assets, bvps, roic, ev, …`). So no fetch-layer rewrite; just the subscription + a small ingest/accessor build (§5). Sharadar is also **survivorship-free** and **point-in-time** via the `datekey` field (the as-of date the data was knowable) — exactly what we need to avoid look-ahead.

## 3. How to subscribe (Nasdaq Data Link)

1. **Sign in** with the account tied to the current API key: `https://data.nasdaq.com/`  → Account.
2. **Check current entitlements:** `https://data.nasdaq.com/account/subscriptions` (a.k.a. "My Data Products"). You'll likely see a Sharadar **prices/SEP** product but **not** Core US Fundamentals — that matches our probe.
3. **Open the product page:** Sharadar Core US Fundamentals — `https://data.nasdaq.com/databases/SF1`. (Catalog: `https://data.nasdaq.com/publishers/SHARADAR`.)
4. **Subscribe.** Sharadar offers a lower-cost **personal/non-commercial** tier and a higher **commercial** tier — *confirm current pricing on the product page* (it changes; I'm not quoting a number to avoid staleness). For our research use, personal/non-commercial is typically the right tier — verify the license matches paper/research use.
5. Same API key is used; no new key needed.

## 4. Verify (before paying, and after)

**Before (sanity — should still show the 2-row sample):**
```bash
cd apps/backend
PYTHONPATH=. .venv/Scripts/python.exe -c "
import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv('../../.env')
from app.factor_data.providers.sharadar import SharadarProvider
with SharadarProvider() as p:
    df = p.fetch_table('SF1', ticker='AAPL')
    print(len(df), 'rows; dims', sorted(df['dimension'].unique()) if len(df) else [])
"
```
Today this prints `2 rows; dims ['MRY']`.

**After upgrade — expect hundreds of rows across dimensions (ARQ/MRQ quarterly back many years):**
```python
import nasdaqdatalink  # pip name: nasdaq-data-link
nasdaqdatalink.ApiConfig.api_key = "<key>"
df = nasdaqdatalink.get_table("SHARADAR/SF1", ticker="AAPL", paginate=True)
print(len(df), df["datekey"].min(), df["datekey"].max())   # want hundreds, back to ~2016+
```
Success = many rows with quarterly `datekey`s spanning years; failure = still ~2 rows.

## 5. What it unlocks + the (small) code work

Once SF1/DAILY data flows, the build is bounded (the fetch already works):

1. **Store:** add an `sf1` table (PK `ticker, dimension, datekey`) + a `daily` table — mirror the existing `sep` ingest pattern in `store.py`.
2. **Ingest:** extend `scripts/ingest_sharadar.py` to pull `SF1` (dimensions ARQ + MRQ) and `DAILY`, bounded by `--from` for the rate cap, per-ticker for the universe.
3. **Accessor:** `get_fundamentals(ticker, as_of)` doing a **point-in-time** join (`datekey <= as_of` — never read a statement before it was filed). This is the key correctness step.
4. **Factors:** add to `factor_research.py` — Value (EV/EBIT, FCF yield, earnings yield from DAILY/SF1), Quality (ROIC, ROE, gross profitability, D/E from SF1). They plug into the existing engine as `(panel, as_of) → Series`.
5. **Re-run** the IS/OOS study → answer "does Quality + Value improve Momentum on our universe?" → if yes, build the composite multi-factor book.

Estimate: ~1–2 days once the data is live.

## 6. Alternatives (if not Sharadar)

| Source | Pros | Cons |
|---|---|---|
| **FMP** (Financial Modeling Prep) | cheap; income/balance/cashflow + ratios (ROE, ROIC); also has options chains | **new provider needed** (our pipeline is Sharadar-shaped); PIT/restatement handling is on us; coverage/quality varies |
| **Polygon.io** | API-first, good docs, solid US coverage | new provider; reworks the ingestion layer |

Both require building a **new provider + PIT layer** (more code than the Sharadar upgrade, which reuses everything). FMP is the budget option and you already have an FMP key — worth pricing against Sharadar, but I'd stay on Sharadar for minimal code + survivorship-free PIT, unless cost is decisive.

## 7. Recommendation

1. **Verify** current SF1 entitlement (the probe above — already confirms it's a sample).
2. **Price** the Sharadar **Core US Fundamentals** subscription (personal tier) on the product page.
3. If the cost is acceptable, **subscribe**, then run the after-upgrade verification and start Value/Quality research (the engine + ~1–2 day ingest build is ready).
4. **In parallel — no data needed:** the report's Priority 1 (**Momentum 6-1 → 12-month upgrade**) and Priority 2 (**risk overlays**). These don't depend on SF1 and are the highest-confidence near-term wins.
