# INSIDER-001 §2 — Data Validation Verdict (live EDGAR)

| Field | Value |
|---|---|
| Program | INSIDER-001 (Event-Driven Research Capability v1) |
| Gate | §2 data validation — the checkpoint **before** research (§3); a failing check blocks §3 |
| Source | SEC EDGAR Form 4 (`sec_edgar_form4`), live pull (read-only, ADR 0027) |
| Universe | 134-name sibling-system survivor set (`claude-trading-view/scripts/survivorship_check.py::SURVIVORS`) |
| Window | filings since 2026-01-01 |
| Run date | 2026-06-25 |
| Verdict | **GO ✅** — no blockers |

## Result

- **Events:** 100 (`insider_buy`: 100) across 33 issuers, 2026-01-12 → 2026-06-24.
- **Filing latency (txn→filed):** median **2.0d**, range [0, 44]d; **0 PIT violations**, 2 > 5d, 0 missing event date.
- **CIK resolution:** 119/134 (**89%**, above the 85% minimum); 4,336 Form 4 filings seen (62 amendments), 0 fetch failures.
- **Unresolved (15, ~11%):** BRY, CADE, CIVI, CMA, ESTE, FOLD, GES, HAYN, PPBI, SASR, SKX, SNV, TOWN, UCBI, VTLE.

## Reading

- The median 2.0-day txn→filed latency matches the Form 4 statutory deadline (two business days),
  and **zero negative latencies** confirms the PIT anchor (`filed_at` = SEC acceptance timestamp)
  never precedes the transaction — no look-ahead is structurally possible in the store.
- The ~11% CIK-resolution hole reproduces the gap the §2 plan anticipated. It clears the 85% gate
  but is **recorded**, not waved through: the unresolved names (delisted/renamed/merged tickers
  absent from `company_tickers.json`) must be reconciled before §3 treats the universe as complete,
  or the study scopes to the resolved 119 and says so.
- 62 `4/A` amendments were ingested and flagged (`payload.is_amendment`), not silently dropped, so
  §3 can decide how to treat corrections rather than inheriting a hidden bias.

## Reproduce

```
SEC_EDGAR_USER_AGENT="GlobalComplyAI TradingWorkbench <contact-email>"  # SEC fair-access UA
# truststore.inject_into_ssl() defeats Norton SSL inspection (ADR 0017)
ingest_form4(EdgarClient(...), EventStore(...), SURVIVORS, since="2026-01-01", cik_map=load_cik_map(...))
validate(store, ingest=report)  # -> ValidationReport(passed=True, blockers=[])
```

Gate logic + thresholds: `apps/backend/app/altdata/validate.py` (`MIN_CIK_RESOLUTION = 0.85`).
