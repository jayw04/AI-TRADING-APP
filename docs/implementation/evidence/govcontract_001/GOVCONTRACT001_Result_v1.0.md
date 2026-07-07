# GOVCONTRACT-001 — Result (Registered Verdict) v1.0

| Field | Value |
|---|---|
| Date | 2026-07-06 |
| Program | GOVCONTRACT-001 (EAD; ADR-0037) |
| Status | **Complete — REGISTERED VERDICT** (supersedes `GOVCONTRACT001_InterimResult_v0.1.md`) |
| Verdict | **🔴 Rejected (Evidenced)** — no residual alpha over matched controls |
| Robust | **False** (fragile — sign/significance wobble across reasonable alternatives) |
| Live impact | **None** (no book; research verdict only) |

## Question

Do new federal government-contract awards predict drift in the awarded small/mid-cap contractor,
*over and above* sector + size + liquidity + momentum (the beta-not-alpha trap that rejected
INSIDER-001)? Pre-registered matched-control design (plan v0.2): each event benchmarked against
same-sector, same-market-cap/ADV/6-month-momentum-decile (±1) controls; net-of-cost bootstrap 95%
CI must exclude zero; **≥100-benchmarked-event decision gate**.

## What changed since the interim (why we now have a verdict)

The first run (`InterimResult_v0.1`) terminated **Insufficient Evidence — only 10/123 benchmarked**,
because materiality (0.25% of market cap) selects small-caps but the factor universe (1,254 SEP
tickers) was small-cap-sparse, so most events couldn't find ≥10 same-decile peers. Two fixes, **no
threshold change**:

1. **DCAP-008 — small-cap SF1 ingest.** The CAP-020 deepen already gave broad small-cap **SEP**
   (10,492 tickers) but zero SF1; ingested **SF1 fundamentals** → **9,040 tickers** (9,003 with
   market-cap), so small-cap peers can be *matched* (sector + market-cap decile), not just priced.
2. **Small-cap-inclusive universe + separate compute.** The runner's default pool was
   top-2,000-by-dollar-volume — which structurally excludes low-volume small-cap peers — so a
   `--n-universe 10000` knob was added. That pool + the deepen store's 13.7M SEP rows exceeds the
   live box's 3.7 GB (and running it there risked the live app), so the study was run on a
   **temporary 32 GB AWS r7g.xlarge**, terminated after. A batched `compute_momentum_batch`
   (per-ticker full-history loop → one window-bounded query, ~1000× faster) made the large universe
   tractable.

## Result — the gate is cleared

```
eligible 890,229  →  material 490  →  de-overlapped 324  →  benchmarked 289   (≥100 gate PASSED)
```

**PRIMARY** (disclosure lag 21, hold 20 trading days, cost 10 bps/side), n=289:

| Metric | Value |
|---|---|
| Net mean excess vs matched controls | **+1.15%** |
| 95% bootstrap CI | **[−0.24%, +2.66%] — spans zero** |
| Gross mean excess | +1.55% |

**SENSITIVITY** (one-factor-at-a-time; confirmation, not the verdict):

| Variant | n | net excess | 95% CI | sig |
|---|---|---|---|---|
| disclosure_lag=14 | 287 | +1.18% | [−0.21%, +2.75%] | — |
| disclosure_lag=46 | 285 | +0.57% | [−0.91%, +2.06%] | — |
| cost_bps=20 | 289 | +0.75% | [−0.64%, +2.26%] | — |
| holding_days=5 | 290 | +0.05% | [−0.69%, +0.81%] | — |
| holding_days=10 | 290 | +0.44% | [−0.51%, +1.55%] | — |
| holding_days=60 | 278 | +2.78% | [+0.43%, +5.14%] | **sig+** |

BH-FDR (q=0.10) across the holding-window family: **1/4 survive.**

## Verdict

**Rejected.** The primary net-excess CI spans zero — no residual alpha over matched controls.
The only nominally significant cell (60-day hold, +2.78%) does not survive as a robust finding
(BH-FDR 1/4; the point estimate and significance wobble across reasonable disclosure lags and
holding windows), so `robust=False`. This is the **beta-not-alpha** outcome the matched-control
design exists to surface: contract-award "signals" are explained by the awarded firm's sector,
size, liquidity, and momentum, not by the award itself. **No book; no live change.** (A separate
*Diversifier* re-check would require the correlation-to-live-books analysis — data-gated, plan §8 —
but the standalone-alpha question is answered: no.)

## Reproduction / reusable assets

- Runner: `scripts/run_govcontract001.py --factor-db <deepen store> --n-universe 10000` (the
  `--n-universe` knob is new; small-cap peers need a large pool or they're excluded).
- **Batched `compute_momentum_batch`** (`app/factor_data/factors/momentum.py`) — one window-bounded
  query over all pool tickers; a durable ~1000× speed-up that benefits *all* factor research.
- **Throwaway-compute recipe** (for any research too big for the live box): launch a large EC2 in
  the box's VPC/SG/key with its IAM profile → stage data + code via presigned S3 URLs → `venv`
  editable-install → run → **terminate**. Keeps heavy batch research off the live-trading box.
