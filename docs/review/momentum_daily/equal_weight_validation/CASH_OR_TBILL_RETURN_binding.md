# CASH_OR_TBILL_RETURN — bound source & methodology — 2026-07-22

The absolute-return-hurdle benchmark for the equal-weight production-sizing validation (PREREG v1.0
§6.2, §7 B). All fields below are FROZEN per the owner rulings of 2026-07-22.

## Source binding (RATIFIED)

```
source_provider:     Federal Reserve Bank of St. Louis (FRED)
underlying_source:   Board of Governors of the Federal Reserve System
release:             H.15 Selected Interest Rates
series_id:           DGS3MO
series_title:        Market Yield on U.S. Treasury Securities at 3-Month Constant Maturity,
                     Quoted on an Investment Basis
frequency:           Daily
units:               Percent per annum
quotation_basis:     Investment basis        (⟹ NO discount→investment conversion)
seasonal_adjustment: Not seasonally adjusted
```

DTB3 was **rejected** for this program (discount basis → maturity-dependent conversion).

## Immutable snapshot

```
raw_file:            docs/review/momentum_daily/equal_weight_validation/data/DGS3MO.csv
raw_file_sha256:     87d8ba2fc5981add5ea48bb5d365f79371fd457488a598e0043758c21ff825d1
observation_start:   2004-01-02   (≥ 1 year of pre-2005 history → the first eligible session always
                                   has a strictly-prior value; no dynamic fetch at run time)
observation_cutoff:  2026-07-21   (the last observation available before the §0 countersign timestamp)
observations:        5,641 valid  (5,884 rows − header − FRED "." missing)
fetch provenance:    obtained on the Norton-free box ec2-paper via FRED H.15 CSV (the laptop's Norton
                     SSL inspection blocks fred.stlouisfed.org); transferred byte-exact (SHA verified
                     on both sides); committed with `-text` (no EOL conversion) so the bytes — and the
                     digest — are preserved.
```

The snapshot must **not auto-refresh** during the forward run. Any extension is **append-only**,
**separately hashed**, and tied to a **documented cutoff**. The loader (`load_dgs3mo`) is FAIL-CLOSED
on the digest: it refuses any file whose SHA-256 differs from the bound value.

## Frozen methodology

- **PIT rule (no same-day look-ahead):** the yield applied on trading session *t* is the latest valid
  observation dated **strictly before *t*** (one-session lag). No prior observation ⟹ `INVALID_DATA`,
  **never** zero.
- **Accrual (ACT/365 calendar-day, amended from 1/252):**
  `session_return = (1 + DGS3MO/100) ** (calendar_days_elapsed / 365) − 1`, where
  `calendar_days_elapsed` = calendar days since the previous valuation session (Fri→Mon = 3). Weekends,
  holidays, and missing observations accrue on the carried-forward strictly-prior yield. The 1/252 form
  is retained ONLY as a 252-session-equivalent **reporting** figure, never for the ledger.
- **Cash economics (single rule):** ALL uninvested strategy cash earns this identical PIT-lagged
  DGS3MO return — the 20%-cap residual, cash when < 5 names qualify, cash awaiting deployment, and
  post-settlement sale proceeds. Cash earns **nothing before it is economically available**
  (settlement). The cash benchmark and the production strategy therefore share identical cash economics.
- **Transaction costs:** 0.

## Verification

`test_cash_tbill_benchmark.py` (11) pins the frozen constants, ACT/365 accrual, zero/negative-yield,
strictly-before-t PIT, holiday/missing carry, first-date `INVALID_DATA` (never zero), the
strategy-residual-cash == benchmark-cash identity, digest fail-closed, and no-network-import.
`test_cash_tbill_snapshot_binding.py` (4) binds the real snapshot by digest and accrues over
contiguous real sessions (small per-session returns), Monday-after-weekend 3-day accrual, and the
pre-snapshot `INVALID_DATA` case.
