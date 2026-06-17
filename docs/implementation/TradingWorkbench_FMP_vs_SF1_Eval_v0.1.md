# Fundamentals data: FMP vs Sharadar SF1 — evaluation (R2, P10)

Decision support for unlocking **Value + Quality factors** (the multi-factor book).
The factor research engine is built and plug-in (`(close, as_of) -> Series`); the
*only* blocker is fundamentals data. Our current Nasdaq Data Link / Sharadar key
returns just a 2-row SF1 sample (verified 2026-06-16) — so this is a **data
purchase decision, not code**. Owner leaned "evaluate the budget option (FMP)
first"; this is that evaluation, with the Sharadar SF1 comparison.

## What our pipeline actually needs

For honest, §5c/OOS-grade factor research the fundamentals source must give:
1. **Point-in-time / as-of correctness** — values as they were *knowable* on a
   past date (a filing/`datekey`), not today's restated numbers. Without this,
   value/quality backtests have look-ahead bias — the exact failure the §5c gate
   exists to catch.
2. **Survivorship-free coverage** — including delisted names, so the universe
   `as_of` a past date isn't biased toward today's winners.
3. **The fields**: revenue, EBITDA, net income, free cash flow, ROE, ROIC, total
   debt, shares outstanding, enterprise value → Value (EV/EBIT, FCF yield,
   earnings yield) + Quality (ROIC, ROE, gross profitability, debt/equity).
4. **History ≥ 2016** (to match the SEP backfill; ideally longer for IS/OOS).

## FMP (Financial Modeling Prep)

**Pricing (public, transparent):** Basic free · **Starter $22/mo** (5y, US, annual
only) · **Premium $59/mo** (≈30y history, US/UK/CA, *full* quarterly+annual
fundamentals, 750 calls/min) · Ultimate $149/mo (global, bulk delivery, 3000/min).
→ **Premium $59/mo** is the tier we'd need (full quarterly fundamentals + deep
history, US).

| Need | FMP verdict |
|---|---|
| Fields | ✅ income-statement / balance-sheet / cash-flow / ratios / key-metrics / enterprise-values endpoints cover all required fields |
| History | ✅ ~30y on Premium |
| PIT | ⚠ **Partial.** Statements carry a `fillingDate` (SEC filing date) and an "as-reported" endpoint exists — so PIT is *achievable*, but the standard endpoints return **restated** values (latest), so honest PIT requires using the as-reported endpoint + filing-date lag carefully. Not turnkey. |
| Survivorship | ✅ delisted-companies + historical-symbols endpoints (free) → can build a survivorship-free universe, with effort |
| Access shape | ⚠ **per-symbol REST** (`/income-statement/{sym}`, …), not one bulk table. ~200 names × ~4 statements is fine at 750/min; bulk delivery only on Ultimate |

## Sharadar SF1 (Nasdaq Data Link)

**Pricing:** not public — gated behind NDL login / sales contact (the acquisition
guide covers checking the entitlement). Historically personal-use SF1 / the
Equities bundle sits meaningfully above FMP Premium.

| Need | SF1 verdict |
|---|---|
| Fields | ✅ all required, plus pre-computed ratios |
| History | ✅ deep |
| PIT | ✅ **Gold standard.** `datekey` = date the data was first knowable, plus dimensions (ARQ/ART/MRQ/MRY/…) purpose-built for point-in-time quant research. Turnkey. |
| Survivorship | ✅ survivorship-bias-free by design, delisted names included |
| Access shape | ✅ one bulk SHARADAR datatable on the **same v3 API our `SharadarProvider` already speaks** (cursor pagination) |

## Engineering scope (the cost that isn't the sticker price)

**Common to both** (unavoidable, provider-independent): a fundamentals store table
(SF1-shaped: `ticker, datekey, period, dimension, <fields>`), ingestion job, and
the Value/Quality factor definitions reading it. The factor engine + IS/OOS
harness already exist.

**FMP-specific add-ons:**
- New `FMPProvider` (httpx REST, mirroring `SharadarProvider`: OS-trust-store TLS
  per ADR 0017, retry/backoff, key handling).
- Per-symbol ingestion across ~4 endpoints + **field-name mapping** (FMP → store
  schema).
- Survivorship handling: pull the delisted/historical-symbols lists to assemble a
  PIT universe.
- PIT care: use the as-reported endpoint + `fillingDate` to avoid restatement
  look-ahead.

**SF1-specific add-ons:**
- ~none for the provider: `SharadarProvider.fetch_table("SF1", …)` already works
  (SF1 is just another SHARADAR datatable). Ingestion = map SF1 columns → store +
  factor defs. PIT/survivorship are built in.

## Recommendation

- **If SF1's price is within ~2–3× FMP Premium ($59/mo):** buy **Sharadar SF1**.
  For *our* pipeline it is the lower-engineering, lower-risk path — the provider
  already exists (SF1 is a one-line addition), and its PIT/survivorship are
  turnkey, exactly what the §5c/OOS discipline depends on. FMP's lower monthly fee
  is largely a false economy once the new adapter + the restatement/PIT-fidelity
  risk are priced in.
- **If budget is the hard constraint or SF1 is far pricier:** **FMP Premium
  $59/mo** is a legitimate choice — full fields, deep history, and PIT *is*
  achievable via the as-reported endpoint + filing-date lag. Accept the adapter
  build and budget care for restatement/survivorship handling.
- **Either way, first** confirm the current Sharadar entitlement and SF1's actual
  price on the NDL account page (the cheap verification step in the acquisition
  guide) before paying — and validate PIT on a couple of names (e.g. a known
  restatement) before trusting either source for OOS research.

## Suggested next step (low-commitment)

Sign up for **FMP's free tier** and pull AAPL's `/income-statement` +
`/income-statement-as-reported` to (a) confirm field coverage and (b) eyeball the
restated-vs-as-reported gap. In parallel, get the SF1 price from the NDL account
page. That gives an apples-to-apples cost+quality picture for a final call —
without spending anything yet.
