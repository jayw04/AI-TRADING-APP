# FI-001 Phase 3 — Allocation (Evidence)

_Survivorship-free books · weights trailing-estimated (126d window, monthly rebalance, no look-ahead) · n=150 · 2019-01-01..2026-06-13 · vol-target overlay 12% annual on the ERC book · H4 gate = paired Sharpe-diff bootstrap CI vs standalone momentum AND vs equal-weight._

> FI-001 Phase 3 per the pre-registered plan: does a **principled weighting** across the validated books
> beat naive equal-weight and standalone momentum? Phase 2 showed equal-weight banks the drawdown benefit
> but leaves the Sharpe gate uncleared; Phase 3 tests whether smarter allocation clears it.

## Allocation methods (books: Momentum, Low-Vol, Trend)

| Method | CAGR | Sharpe | MaxDD | Calmar | ΔSharpe vs mom [95% CI] | ΔSharpe vs eqw [95% CI] | ΔMaxDD vs mom (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Equal-weight | +23.3% | **1.13** | −30.7% | 0.76 | +0.081 [−0.153, 0.372] | 0.0 | +7.6 |
| Inverse-vol (risk-parity) | +20.0% | 1.10 | −30.5% | 0.66 | +0.059 [−0.286, 0.526] | −0.022 [−0.152, 0.165] | +7.8 |
| ERC (full covariance) | +19.5% | 1.10 | −30.5% | 0.64 | +0.053 [−0.309, 0.547] | −0.028 [−0.185, 0.192] | +7.8 |
| Min-variance (correlation-aware) | +15.2% | 0.99 | −30.2% | 0.50 | −0.052 [−0.611, 0.667] | −0.133 [−0.513, 0.35] | +8.1 |
| **ERC + vol-target (12%)** | +14.2% | **1.20** | **−14.2%** | **1.00** | +0.159 [−0.269, 0.559] | +0.080 [−0.28, 0.423] | **+24.1** |

*(standalone Momentum: CAGR +31.5%, Sharpe 1.04, MaxDD −38.3%, Calmar 0.82)*

## H4 verdict — two findings

**1. Cross-book allocation *sophistication* does not pay.** Inverse-vol, ERC, and min-variance all
**fail to beat naive equal-weight** — every ΔSharpe-vs-eqw CI spans zero and sits slightly *negative*
(−0.02 to −0.13). Equal-weight has the highest Sharpe of the static allocations (1.13). With only three
books of similar volatility, ERC ≈ inverse-vol ≈ equal-weight by construction, and the extra machinery
buys nothing. **The pre-registered "risk-based allocation beats equal-weight" half of H4 is not
supported** — a clean, useful negative: *use equal-weight; skip the optimizer.*

**2. The vol-target *overlay* is the real lever — for drawdown, not Sharpe.** `ERC + 12% vol-target`
posts the best Sharpe (1.20) and Calmar (1.00) of the entire program and **cuts max drawdown from −38%
to −14%** (a 24pp reduction) by scaling gross exposure down when realized vol is high. But even this does
**not clear the strict Sharpe gate** — ΔSharpe vs momentum +0.159 [−0.269, 0.559] still spans zero — and
it costs dearly in return (CAGR 31.5% → 14.2%, because the overlay runs under-invested much of the time).
It is a **drawdown/Calmar transformation at a large CAGR give-up**, not a free Sharpe edge.

**Neither half of H4 clears the paired-Sharpe gate** — consistent with Phase 2 and the platform's whole
track record: combining validated factors is a **risk-management** tool, not an alpha source.

## The FI-001 combined-book recommendation (cumulative, Phases 1–3)

- **Construct the combined book by equal-weighting** Momentum + Low-Vol + Trend. Do **not** reach for
  ERC/risk-parity/min-variance — they don't beat 1/N here.
- **Add a vol-target overlay for drawdown-sensitive capital only.** It roughly halves max drawdown and
  lifts Calmar to ~1.0, at a large CAGR give-up — a conservative-mandate trade, not a default.
- **Expect risk reduction, not alpha.** No construction produced a statistically decisive Sharpe edge
  over standalone momentum; the honest value proposition is a **6–24pp shallower drawdown** at
  comparable or slightly-better risk-adjusted return.

## Caveats & scope

- Three books only (Sector pending the box store — Phase 1b/3b); a fourth low-correlation book could
  change the ERC-vs-equal-weight calculus (more books → more room for covariance-aware weighting to help).
- The vol-target level (12%) is a single choice; a sweep would trace the drawdown/return frontier (a
  cheap follow-up). Weights are trailing-estimated (no look-ahead); bootstrap seed 17.

## Reproduce

```
cd apps/backend
.venv/Scripts/python.exe scripts/fi001_phase3_allocation.py \
    --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase3/
```

Artifacts: `apps/backend/research/fi001/phase3/`. Pure-helper tests in
`apps/backend/tests/scripts/test_fi001_phase3.py`.

## Phase 3 verdict (Allocation)

**No allocation clears the Sharpe gate.** Sophisticated cross-book weighting does **not** beat naive
equal-weight (skip the optimizer); the **vol-target overlay** roughly halves drawdown (Calmar 0.82→1.00)
at a large CAGR give-up but still yields no decisive Sharpe edge. FI-001's cumulative answer: a combined
book is a **drawdown-reduction** capability, built simply (equal-weight + optional vol-target), not an
alpha source. Remaining: **Sector arm on the box** (Phase 1b/3b) and **Phase 4 — Adaptive Portfolio**
(long-horizon).
