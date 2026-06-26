> ⚠️ **INTERIM — NOT THE PRE-REGISTERED VERDICT.**
> Form 4 coverage is 50/134 target issuers (2016-01-08 → 2026-06-23, 837 events). The registered gate result must be computed once, on the complete pull (`--final`).
# INSIDER-001 §4 reproduction — B - Diversifier / factor tilt

**Action:** A real positive tilt but not a standalone edge — size as a disclosed diversifying sleeve, co-existing with the momentum book.

- **Window:** 2016-02-08 → 2026-06-25; universe 35 names; 179 conviction hits → 81 taken (96 de-overlap skips, 2 no-data).
- **Book vs equal-weight benchmark (H1):** Sharpe-diff -0.359 CI [-1.009, 0.261], bootstrap p 0.0795 → standalone edge: no.
- **Book:** Sharpe 0.395, total 89.8%, CAGR 6.4%, maxDD -67.4%.
- **Per-event (H3):** mean 7.56%, median 6.86%, hit-rate 68%, avg hold 87.1d.

_No parameter was re-tuned (plan §1 faithfulness rule); the verdict is declared, not coded (INSIDER_VERDICT)._

---
### Provenance
- **As-of (PIT):** 2026-06-25 — only Form 4 events filed on/before this date.
- **Event store:** `data/insider_events.duckdb` — 837 events, 50 distinct issuers, 2016-01-08 → 2026-06-23.
- **Price store:** `data/factor_data_full.duckdb` (survivorship-free SEP, split/div-adjusted).
- **Benchmark universe (H1):** 35 names (distinct event issuers).
- **Hold:** 90 trading days; bootstrap resamples 2000.