# MR-002 — Pre-Freeze Data Verifications V1–V4 · Results v0.1

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Pre-reg:** `TradingWorkbench_MR002_PreRegistration_v0.3.md` §8
**Method:** live interrogation of the actual vendor holdings (Sharadar via Nasdaq Data Link + FMP probe)
via `apps/backend/scripts/mr002_verify_v1_v4.py` (truststore/ADR-0017 path). Raw output:
`V1_V4_raw_findings.json` (this directory).

| # | Verification | Verdict | Freeze impact |
|---|---|---|---|
| **V1** | PIT earnings schedule | 🔴 **FAIL as specified** — no forward calendar with known-at timestamps exists in our holdings | **Owner decision required** (three options below) |
| **V2** | PIT sector history | 🔴 **FAIL direct / 🟡 buildable via option 2** — TICKERS is a current snapshot; EDGAR-derived PIT SIC is feasible | **Owner decision required** (approve the SIC build) |
| **V3** | Consistent price series | ✅ **PASS** — SEP/ACTIONS deliver all four registered series, with one required §2 wording amendment | amend, no blocker |
| **V4** | Historical borrow / HTB | ✅ **RESOLVED BY REGISTERED FALLBACK** — confirmed no PIT source anywhere in our stack | none (disclosure stands) |

---

## V1 — PIT earnings schedule: FAIL as specified

**Findings.** Sharadar EVENTS has exactly three columns (`ticker, date, eventcodes`) — no timestamps, no
revision history, no BMO/AMC designation. It is a **historical 8-K event log**, not a calendar: zero
future-dated rows exist (query `date ≥ 2026-07-11` returned 0 across all tickers). AAPL's event codes
(22, 34, 52, 53, 57, 71, 81, 91) are consistent with 8-K item sections (code 22 ≈ Item 2.02, Results of
Operations). FMP's historical earnings calendar is **403 (gated)** on our Starter tier. **Depth floor:**
AAPL EVENTS starts **2016-01-25** — a ~10-year rolling window, the same floor as SF1.

**Consequence.** The v0.3 §4 earnings-clearance rule ("PIT-known earnings announcement … schedule
revisions recognized from revised timestamps") **cannot be implemented from current holdings.**

**Options for the owner (pick one before freeze):**

1. **PIT-estimated earnings window (RECOMMENDED).** Earnings announcements are strongly periodic. Derive
   each stock's announcement history PIT from EDGAR 8-K filings (CAP-015 client; filing acceptance
   timestamps give both the known-at property and an approximate BMO/AMC read) and/or EVENTS code-22
   dates, then register: *a stock is ineligible for entry, and must exit, when the current session falls
   inside the **expected earnings window** = [prior announcement + 80 sessions … + 100 sessions] (≈ one
   quarter ± buffer), or inside an actually-announced window once the 8-K is filed.* Fully known-at-`t`,
   reproducible, conservative (wider than a true calendar — costs some trading days, never leaks).
   Window constants frozen before development.
2. **Acquire a true PIT calendar** (e.g., FMP tier upgrade — forward dates + BMO/AMC but still no
   revision-timestamp history; or an institutional calendar vendor). Adds cost and an ADR-worthy new
   dependency; still only partially satisfies the revision-tracking requirement.
3. **Fallback per pre-reg:** restrict the exclusion to events already announced through `t` (no forward
   protection). The review flagged this as materially changing the design — requires explicit owner
   re-approval and would weaken the information-exclusion story.

**Note on the window:** whichever option is chosen, earnings-exclusion data bounds the realized backtest
window to **~2016 → present (~10 years)** unless EDGAR-native ingestion (option 1) is extended earlier —
EDGAR 8-K coverage reaches well before 2016. This sits exactly at the pre-reg's "materially shorter than
~10 years ⇒ stop and re-review" line; option 1 with EDGAR depth relieves it.

## V2 — PIT sector history: FAIL direct, buildable via option 2

**Findings.** Sharadar TICKERS is a **one-row-per-ticker current snapshot** (AAPL: 1 row per table
param; no `effectivedate`/`startdate`/`asof` fields anywhere in the 28-column schema). Sector fields
available: `sector`, `industry`, `sicsector`, `siccode`, `famaindustry` — all **current**. The
look-ahead is real and demonstrated: META reads "Communication Services" today, which would misclassify
its entire pre-2018 history (it was Technology before the GICS restructure).

**Consequence.** The v0.3 rule "accept only a genuinely PIT sector history, or historically effective
SIC/NAICS through a frozen mapping table" fails on the first branch across our holdings.

**Recommended resolution (option 2 of the registered rule):** build the PIT SIC history from **EDGAR
filing headers** — every 10-K/10-Q/8-K carries the company's SIC code as assigned at filing time, and
CAP-015 (the native EDGAR client from INSIDER-001) already handles fair-access fetching. Deliverables:
per-security effective-dated SIC series (from filing dates) + a **frozen SIC→sector-ETF mapping table
whose SHA-256 ships in the evidence package** (per the registered rule). `permaticker` (present in
TICKERS) serves as the stable identifier joining SEP ↔ the SIC series. This is a real but bounded
build — reusable as a platform capability (a CAP candidate: PIT Classification History) and a natural
extension of CAP-024's no-silent-bad-mapping principle.

## V3 — Price-series consistency: PASS (one amendment required)

Empirical checks on AAPL across the 2020-08-31 4:1 split and the 2020-08-07 ex-dividend:

| Registered series (§4) | SEP/ACTIONS delivery | Evidence |
|---|---|---|
| Signal = total-return adjusted | **`closeadj`** ✓ | `closeadj/close` ratio steps at the ex-div date (0.96827 → 0.97007) — dividends are in `closeadj` only |
| Execution = split-adjusted, non-div-adjusted open/close | **`open`/`close`** ✓ | `closeunadj/close` = 4.0 pre-split, 1.0 post → `close` (and `open`) are split-adjusted only |
| Gap = split-adjusted + cash-distribution-adjusted | `open`/`close` + ACTIONS `dividend` rows ✓ | ACTIONS carries per-share dividend `value` on every dividend row |
| Dollar-volume ranking = consistent pair | **⚠ AMENDMENT:** use **SEP `close` × SEP `volume`** | SEP `volume` is **split-adjusted** (median-volume ratio across the split = 1.02, no 4× shift). Therefore v0.3 §2's registered "raw close × raw volume" is **not available and would be inconsistent** (`closeunadj` × adjusted volume mixes bases). `close × volume` is the "equivalent consistently split-adjusted pair" the review explicitly allowed — and it equals raw dollar volume by split-invariance. |
| Delisting valuation | priority order intact ✓ | ACTIONS marks `delisted` / `acquisitionby`; SEP carries prices to the delist date (TWTR last bar 2022-10-27). **No vendor delisting-return field exists** → priority 1 is unavailable; priorities 2–4 (transaction consideration → final market price → conservative fallback) are operative. |

**Implementation-Freeze checklist item added:** verify the adjustment basis of ACTIONS dividend `value`
(pre- vs post-split per-share) against the `closeadj` step on a sample of split+dividend names before
validation runs.

## V4 — Historical borrow / HTB: no source, registered fallback applies

Confirmed across the stack: Sharadar Core US Equities Bundle has **no** borrow/short-availability table
(and we hold no SF2); FMP short-interest is **403 (gated)** — and short interest ≠ borrow availability
regardless; Alpaca's `easy_to_borrow` is a **current snapshot only**, not historical. The §9 registered
no-data fallback therefore applies verbatim: primary backtest assumes availability in the top-150 short
universe; mandatory diagnostics deny the most extreme 10% / 25% of short signals (by |z|) and apply
300 / 1,000 bps annual borrow costs. Per review 2, this does not block freeze — the disclosure ships in
every result artifact.

---

## Required pre-registration amendments (→ v0.4, pre-OOS corrections per Q1 rules)

1. **§2 dollar-volume definition:** "raw close × raw volume" → "**SEP `close` × SEP `volume`** (a
   mutually consistent split-adjusted pair; equals raw dollar volume by split-invariance)". (V3)
2. **§4 earnings-clearance rule:** replace with the owner's chosen V1 option (recommended: the
   PIT-estimated expected-earnings window, constants frozen).
3. **§8 V2 row:** record the chosen resolution — EDGAR-derived effective-dated SIC + frozen hashed
   SIC→SPDR mapping table.
4. **§7 Implementation-Freeze checklist:** add the ACTIONS dividend-value basis check. (V3)
5. **§8 data plan:** realized-window note — earnings data bounds the window to ~2016+ unless EDGAR
   ingestion extends it (V1); the Data Availability Gate re-checks after the V1 build.

**Owner decisions needed to unblock freeze: the V1 option (1/2/3) and V2 build approval.** V3 and V4
are closed by this report.
