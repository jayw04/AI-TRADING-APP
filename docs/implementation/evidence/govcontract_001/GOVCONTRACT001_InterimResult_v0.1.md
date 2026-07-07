# GOVCONTRACT-001 — Interim Result (coverage-limited)

> **⚠️ SUPERSEDED (2026-07-06)** by the REGISTERED VERDICT in `GOVCONTRACT001_Result_v1.0.md`
> (**Rejected**, 289 benchmarked). This interim doc is kept as the record of the coverage-limited
> first run and the path (DCAP-008 small-cap SF1 + a small-cap-inclusive universe) that unblocked it.

| Field | Value |
|---|---|
| Program | **GOVCONTRACT-001** (EAD's first event-driven research program; DCAP-007 / Quiver Government Contracts) |
| Date | 2026-07-06 |
| Plan | `TradingWorkbench_GOVCONTRACT001_Plan_v0.1.md` (pre-registration **v0.2** — locked calibration + decision gates) |
| Status | **INTERIM — Insufficient Evidence (coverage-limited). NOT a registered verdict.** |
| Governing ADR | 0037 |

---

## Outcome

The study ran **end-to-end on the box** against the real event store (890,114 eligible `gov_contract_award` events, 2018–2026) + the factor spine (research copy with SEP + SF1). The pre-registered pipeline executed correctly. It terminated **Insufficient Evidence** at the pre-registered ≥100-benchmarked-event gate — **honestly, not by failure**.

```
eligible: 890,114  →  material: 163  →  de-overlapped: 123  →  benchmarked: 10   (< 100 gate)

PRIMARY (lag 21, hold 20, cost 10 bps):
  net mean excess = −2.16%   95% CI [−11.10%, +5.35%]   (spans zero)
  gross mean excess = −1.76%

SENSITIVITY (one-factor-at-a-time; confirmation only):
  disclosure_lag=14   n=8    net +6.39%   CI [−9.29%, +31.84%]   .
  disclosure_lag=46   n=7    net −10.85%  CI [−27.44%, +1.03%]   .
  cost_bps=20         n=10   net −2.56%   CI [−11.50%, +4.95%]   .
  holding_days=5      n=11   net +1.76%   CI [+0.19%, +3.38%]    sig+
  holding_days=10     n=11   net −0.25%   CI [−6.10%, +5.51%]    .
  holding_days=60     n=10   net +17.89%  CI [−8.02%, +58.61%]   .
  BH-FDR (q=0.10) across the holding-window family: 1/4 survive

DECISION:
  verdict = Insufficient Evidence
  robust  = False (fragile — the sign flips across reasonable disclosure lags: +6.4% at 14d, −10.9% at 46d)
```

## Why only 10 of 123 material events benchmarked (the honest, structural reason)

This is **not** a tuning problem — it is a **data-breadth limitation**, and the gates are working as designed:

- The **materiality filter is relative to market cap** (award ≥ 0.25% of market cap AND ≥ $250k). A $250k award is only 0.25%-material to a company ≤ ~$100M, so **materiality inherently selects small-cap contractors** — which is exactly the hypothesis's target.
- The **factor-data universe on the box is liquidity-skewed and small-cap-sparse** (1,254 SEP tickers, mostly mid/large-cap). So most small-cap events cannot find **10 same-sector, same-market-cap-decile matched controls** (the pre-registered ≥10-controls-or-exclude rule), and are correctly excluded rather than benchmarked against dissimilar names.

The 10-event sample that *did* benchmark is **fragile** (the excess-return sign flips across reasonable disclosure-lag assumptions; only the 5-day window is nominally significant, and BH-FDR passes just 1 of 4 windows) — so forcing a verdict on it would be exactly the beta-not-alpha, small-sample overfit the pre-registration exists to prevent.

## What this records (evidence-engineering, not a failure)

Per ADR-0037, **the verdict matters less than the system proving it honestly**. The platform:
- ingested 890k real government-contract events (98.5% mapped, USAspending-validated, 0 §2.6a kill signals),
- applied a fully pre-registered materiality / matched-control / cost / bootstrap methodology,
- and **refused to manufacture a verdict from 10 noisy, fragile observations** — terminating Insufficient Evidence at the pre-registered gate.

That refusal is the result.

## Path to a genuine testable verdict (no gate-relaxing)

The limit is **universe breadth**, not the thresholds. To benchmark enough small-cap contractor events, the factor-data universe needs far more **small-cap SEP + SF1 coverage** (a broad survivorship-free small-cap set), so each small-cap event has ≥10 same-decile peers. That is a scoped **data-provisioning** task — **not** a threshold to lower. Materiality and the ≥100-event gate stay exactly as pre-registered (plan §0.2 / §5).

## Reproducibility

- Runner: `apps/backend/scripts/run_govcontract001.py --factor-db data/factor_data.research.duckdb` (read-only).
- Engine: `app/altdata/matched_control.py` (matched-control excess study) + `app/altdata/quiver/govcontract_study.py` (locked calibration, verdict tree, sensitivity).
- Data: event store `data/event_store.duckdb` (Quiver gov contracts, DCAP-007); factor research copy `data/factor_data.research.duckdb` (SEP + SF1 for ~1,251 tickers).
