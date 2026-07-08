# Session Report — 2026-07-07 · Operations, Factor-Store Fix & EAD Governance

**Author:** Claude (Opus 4.8) · **Owner review:** Jay Wang
**Scope:** The owner-directed 6-step sequence (below), plus the operational work it depended on
(account reset/rebuild, dashboard benchmark card, momentum recovery, risk-limit tuning).
**Status legend:** ✅ done · ⏳ in flight (auto-completing) · ○ not started

---

## Executive summary

All six steps of the directed sequence are **done or in flight**, with one net-new item deferred by
design (total-return pricing) and one deploy/schedule follow-up for the CEE. The headline result: a
**silently-broken factor refresh was found and fixed** — the live factor store had frozen at 07-06
because the daily refresh aborted every run on a tickers-ingest bug; it now advances correctly, so
the live factor books (momentum/sector/low-vol/combined) rank on fresh data again. Along the way the
flagship momentum book (which had halted on a benign rebuild-day breaker trip) was recovered, and the
daily-loss caps were tuned. Four EAD event-driven programs are now consolidated as **one finding** —
public corporate-disclosure events carry no residual alpha after matched controls — and that
conclusion is enforced in code as the **15th CI invariant**.

---

## The 6 steps

### Step 1 — Merge the walk-away PRs ✅
Merged, each after honoring the ≥1-hour walk-away and confirming green CI:
- **#378** — round non-fractionable orders to whole shares in OrderRouter (order-path fix)
- **#379** — CONGRESS-001 Phase 3 + LOBBY-001 (build + registered verdicts). *Caught + fixed a mypy
  CI failure before merge (`min()` over `date|None` in `congress_study`).*
- **#380** — dashboard benchmark comparison card
- **#381** — EAD Dataset Triage v0.2 + Research Program Registry v0.17
- **#382** — the factor-refresh fix (Step 2)
- **#383** (reference-only invariant) — merged. ⏳ **#384** (CEE report) — queued, auto-merging after
  its walk-away window.

### Step 2 — Fix live-store staleness ✅ (root cause was deeper than expected)
The memory framed this as "no automated refresh." In fact the automation existed (a daily systemd
timer) but was **silently failing every run**, so the store was frozen at 07-06.
- **Root cause:** the live `tickers` table predates a schema reorder (sector/industry were appended
  later), so a **positional `INSERT..SELECT`** landed the `sector` string ("Basic Materials") into
  the BOOLEAN `isdelisted` column → `ConversionException` → the whole refresh aborted before the swap.
- **Fix (#382):** name the target columns in the tickers INSERT (maps by name, immune to column
  order) + a regression test. **Hardened the swap into a safe swap:** verify the staging store
  *before* swapping (no sep_max regression, <10% ticker loss, `lastpricedate ≥ sep`) → abort
  untouched on failure; retain a one-deep rollback (`factor_data.prev.duckdb`).
- **Verified on the box:** the store advanced 07-06 → **07-07**, sep + tickers in lockstep.
- *Lesson recorded: positional `INSERT..SELECT` is a silent time-bomb across schema drift — always
  name target columns.*

### Step 3 — Verify factor books use fresh data ✅ (final proof = Monday's rebalance)
With the store fresh and sep/tickers in lockstep, the point-in-time universe resolves to **5,988
tickers** → the factor books will **RANK, not HOLD** at the next rebalance. The live confirmation is
the **Monday 10:00 ET** scheduled rebalance (nothing more to do until then).

### Step 4 — EAD Dataset Triage + summary ✅ (#381)
- **Triage v0.2** — four **hard** vetoes (PIT clarity · distinct mechanism · license path · ≥100
  sample); any one fails → no full study. The reference-use rule is a **codified invariant**, not a
  recommendation.
- **Registry v0.17** — folded the three EAD verdicts (GOVCONTRACT-001, CONGRESS-001, LOBBY-001, all
  Rejected) into the dashboard + counts (14 programs · Rejected 7 · Negative 10); framed the four
  rejections (with INSIDER-001) as **one finding**. Reserved: LOBBY-002 · OFX-001.

### Step 5 — `rejected_reference_only` guardrail ✅ (#383, the 15th CI invariant)
The converse of the altdata-order-path-isolation invariant: a rejected EAD pattern may be **displayed
as context** but must **never enter ranking, sizing, or the order path.**
- `app/altdata/reference_only.py` — the guard + single source of truth.
- `scripts/check_reference_only_invariant.sh` — the 15th CI invariant (greps the order-path/ranking
  modules for any rejected-EAD label). Wired into CI, registered in CLAUDE.md.
- The registry-sync test also caught that **INSIDER-001 was missing from `programs.py`** — added it
  (rejected), so the doc and code now agree.

### Step 6 — Resume CEE / total-return ✅ CEE activated · ○ total-return not started
- **CEE (#384):** the Continuous Evidence Engine module was fully built + tested but had **no
  consumer** (dormant). Added `scripts/reports/cee_report.py` — runs the Research-Envelope check +
  Evidence Clock over the live books, exit 2 on INVESTIGATE. **Verified on the box:** classifies all
  5 live books, each mapped to its research envelope, clock at day 1 post-reset (all "Insufficient
  Evidence," accruing correctly).
- **Total-return pricing rollout:** ○ not started (see Remaining).

---

## Related operational work (this session)

| Item | Result |
|---|---|
| Account credential sync (.env → SSM → DB) + rebuild of 4 books | ✅ done (earlier this session) |
| Performance-baseline reset (equity curve + trade log start today) | ✅ done |
| Dashboard **benchmark card** (SPY/VOO/QQQ/IWM/DIA since inception) | ✅ built + **deployed to the box** (#380) |
| **momentum-portfolio recovered** — halted 19:18 on a *benign* transient rebuild-day breaker trip (−$2,066 vs $2k cap; account then recovered to **+1.70% / $101,699**). No liquidation, no missed rebalance → **zero financial impact.** Reset breaker + resumed to PAPER | ✅ done |
| **Daily-loss caps tuned** — all four $100k books (momentum/sector/low-vol/combined) widened 2% → **3% ($3,000)** via the audited API; range stays at its $500 profile | ✅ done |

---

## PR ledger

| PR | Title | State |
|---|---|---|
| #378 | Non-fractionable whole-share rounding | ✅ merged |
| #379 | CONGRESS-001 Phase 3 + LOBBY-001 verdicts | ✅ merged |
| #380 | Dashboard benchmark card | ✅ merged |
| #381 | EAD Triage v0.2 + Registry v0.17 | ✅ merged |
| #382 | Factor-refresh fix + safe swap | ✅ merged |
| #383 | EAD reference-only invariant (15th) | ✅ merged |
| #384 | CEE live-book report | ⏳ auto-merging |

---

## Tasks remaining

### Near-term / this program
1. **CEE deploy + schedule** — the report runs on the box on demand but isn't automated. Needs:
   `scripts/reports/` synced into the backend image, a systemd timer (like `daily-report`), and an
   **SNS alert on INVESTIGATE**. (The box source tree currently lacks `scripts/reports/`.)
2. **Total-return pricing rollout** — PORT-001 #3 (cross-asset total-return live pricing) is built and
   **default-OFF**; the rollout decision + enablement is not started.
3. **Confirm Monday's rebalance** — verify the four factor books actually rank on the fresh store at
   the 10:00 ET Monday rebalance (Step 3's live proof).
4. **Optional — momentum cap headroom** — momentum is at 3% ($3,000), which clears today's churn by
   only ~$900; consider $3,500–4,000 if it should comfortably survive a volatile down-day.

### Deferred / reserved (governed, do NOT start without a trigger)
5. **LOBBY-002** (New-Issue Lobbying Entry) — reserved; same mechanism class as the rejections.
6. **OFX-001** (Off-Exchange / Dark-Pool signal study) — reserved as a *cross-sectional signal*
   program (not an event study); **check the free FINRA feed before paying Quiver.**
7. **EAD event studies** — paused. Any new alt-data dataset must pass the Dataset Triage gate first.

### Watch-items (not action, just awareness)
- The **$3,000 (3%) daily-loss caps** are a loosened protection — monitor for real trips.
- The full **survivorship-free LOBBY-001 rerun** (Quiver rate-limited the v1 sweep) would only
  strengthen the rejection — a clean-up, not a blocker.

---

*Prepared for owner review. Nothing here is committed to `main` beyond the merged PRs above; this
report itself is uncommitted pending your review.*
