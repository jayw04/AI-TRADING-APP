# FI-001 Phase 4 — Adaptive Portfolio v1 (Evidence)

_Survivorship-free books · regime = equal-weight-universe proxy vs its 200d SMA (no look-ahead) · risk-off gross 0.5 · corr de-risk threshold 0.6 (trailing 63d) · n=150 · 2019-01-01..2026-06-13 · gate = paired Sharpe-diff bootstrap CI vs static equal-weight AND vs standalone momentum._

> FI-001 Phase 4, gated by Phases 1–3. Those found: combining reduces drawdown but never clears the
> Sharpe gate; naive equal-weight beats sophisticated *static* allocation; the vol-target overlay is the
> drawdown lever; and correlation is regime-dependent. Phase 4 asks whether allocation that **adapts to
> the market regime / correlation state** beats the static equal-weight book.

## Adaptive strategies (books: Momentum, Low-Vol, Trend)

| Strategy | CAGR | Sharpe | MaxDD | Calmar | ΔSharpe vs eqw [95% CI] | ΔSharpe vs mom [95% CI] | ΔMaxDD vs eqw (pp) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Static equal-weight (control) | +23.3% | 1.13 | −30.7% | 0.76 | 0.0 | +0.081 [−0.153, 0.372] | 0.0 |
| **Regime gross (de-risk in downtrend)** | +19.5% | **1.17** | **−24.2%** | **0.81** | +0.041 [−0.189, 0.228] | +0.122 [−0.116, 0.358] | **+6.4** |
| Regime tilt (defense in risk-off) | +23.4% | 1.07 | −31.9% | 0.73 | −0.054 [−0.178, 0.044] | +0.027 [−0.151, 0.241] | −1.3 |
| Correlation-adaptive (de-risk on high corr) | +15.6% | 1.07 | −24.5% | 0.64 | −0.058 [−0.347, 0.202] | +0.023 [−0.225, 0.277] | +6.2 |

*(standalone Momentum: Sharpe 1.04, MaxDD −38.3%)*

## Findings

**Regime-gross de-risking is the best adaptive rule — and the best combined book in the whole program.**
Cutting gross exposure to half when the market is below its 200d SMA lifts Sharpe to **1.17** (the only
FI-001 construction whose *point estimate* beats **both** static equal-weight *and* standalone momentum)
and cuts drawdown 6.4pp — while keeping far more return than the Phase 3 vol-target overlay (CAGR 19.5%
vs 14.2%, because it de-risks only in confirmed downtrends rather than on every vol spike). It is a
**better, more return-preserving cousin of vol-targeting.** But — consistent with every FI-001 phase —
its ΔSharpe CIs **still span zero** vs both benchmarks: a better *tradeoff*, not a *decisive* edge.

**Regime-tilting HURTS.** Over-weighting the defensive books in risk-off (and momentum in risk-on)
slightly *lowered* Sharpe (−0.054 vs eqw) and *deepened* drawdown (−31.9%): the risk-off tilt to defense
gave up momentum's recovery. Changing *which* books you hold by regime is worse than simply de-risking
*how much* you hold.

**Correlation-adaptive de-risking reduces drawdown but costs Sharpe.** De-risking when trailing
cross-book correlation exceeds 0.6 shaves 6.2pp of drawdown but drops Sharpe to 1.07 — it de-risks at the
wrong times often enough to erode the risk-adjusted return. The Phase 1 "correlation is unstable"
finding is real, but a naive correlation trigger does not monetize it.

## Phase 4 verdict (Adaptive Portfolio v1)

**No adaptive rule clears the Sharpe gate** — the same disciplined result as Phases 1–3. But Phase 4
identifies the **best drawdown-managed combined book in the program: equal-weight + a simple market-regime
gross de-risk** (Sharpe 1.17, MaxDD −24% vs momentum's −38%, keeping ~19.5% CAGR). Regime-*tilting* and
correlation-*triggering* do not help. This refines the FI-001 recipe:

> **For a Sharpe-maximizer:** standalone momentum — nothing decisively beats it.
> **For a drawdown-sensitive allocator:** equal-weight the diversified books + a **market-regime gross
> overlay** (de-risk below the 200d SMA) — the best return-for-drawdown book, better than static
> vol-targeting, though still not a statistically decisive Sharpe edge.

## Caveats & scope

- v1 uses one regime signal (200d SMA of the equal-weight universe), one risk-off gross (0.5), one corr
  threshold (0.6); sweeps of these trace the frontier (cheap follow-ups). Sector book pending the box.
- Weights/regime are trailing/shifted (no look-ahead); bootstrap seed 17. A regime overlay adds turnover
  the return-level model does not fully cost — a live implementation must account for it.

## Reproduce

```
cd apps/backend
.venv/Scripts/python.exe scripts/fi001_phase4_adaptive.py \
    --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase4/
```

Artifacts: `apps/backend/research/fi001/phase4/`. Pure-helper tests in
`apps/backend/tests/scripts/test_fi001_phase4.py`.

## FI-001 program close (Phases 1–4)

All four phases agree: **combining validated factors is a risk-management capability, not an alpha
source.** The best construction is deliberately simple — **equal-weight + a market-regime gross overlay**
for drawdown-sensitive capital — and no sophistication (ERC, min-variance, regime-tilt, correlation
triggers) earns a decisive Sharpe edge. Verdict stands: **Diversifier (B), portfolio-level.** Remaining
open items are refinements, not the thesis: a full-history+sector store, and parameter sweeps of the
regime overlay.
