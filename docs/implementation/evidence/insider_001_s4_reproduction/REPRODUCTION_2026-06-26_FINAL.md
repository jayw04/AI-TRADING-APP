# INSIDER-001 §4 reproduction — C - Rejected

**Action:** No economic edge vs simply owning the small/mid-cap basket; do not promote.

- **Window:** 2016-01-27 → 2026-06-26; universe 134 names; 487 conviction hits → 212 taken (273 de-overlap skips, 2 no-data).
- **Book vs equal-weight benchmark (H1):** Sharpe-diff -0.298 CI [-0.627, -0.004], bootstrap p 0.0385 → standalone edge: no.
- **Book:** Sharpe 0.549, total 253.8%, CAGR 12.9%, maxDD -70.1%.
- **Per-event (H3):** mean 10.36%, median 7.67%, hit-rate 67%, avg hold 86.8d.

_No parameter was re-tuned (plan §1 faithfulness rule); the verdict is declared, not coded (INSIDER_VERDICT)._

---
### Provenance
- **As-of (PIT):** 2026-06-26 — only Form 4 events filed on/before this date.
- **Event store:** `data/insider_events.duckdb` — 2148 events, 113 distinct issuers, 2016-01-06 → 2026-06-24.
- **Price store:** `data/factor_data_full.duckdb` (survivorship-free SEP, split/div-adjusted).
- **Benchmark universe (H1):** 134 names (from --universe-file).
- **Hold:** 90 trading days; bootstrap resamples 2000.