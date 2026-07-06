# CAP-020 Regime-Overlay Validation — Result v1.2 (FINAL)

| Field | Value |
|---|---|
| Study | CAP-020 (FI-001 Phase 4 `regime_gross`): eqw combined book, gross → g when proxy < N-day SMA |
| Plan | `TradingWorkbench_FI001_CAP020_RegimeOverlayValidation_v0.2.md` (owner-approved 9.7/10) |
| Harness | `scripts/cap020_regime_validation.py` (+ 18 tests) |
| Data | Factor store deepened to 2017 — Option A (active names) then **Option B (survivorship-free, 10,492 tickers)** |
| Date | 2026-07-04 |
| **Verdict** | **🔴 REJECTED (Evidenced)** as a Calmar/Sharpe/return improver. Crash-insurance property spun out to **CAP-022**. |

## Bottom line

Tested as it was framed — *does the 200d-trend gross overlay improve the equal-weight combined book's
risk-adjusted return (Calmar-primary)* — **CAP-020 is rejected on the evidence, confirmed on a
survivorship-free universe.** The same mechanism, however, **reproducibly works as crash insurance**
(it cut the COVID and 2022 drawdowns ~13-15pp in both runs). That property is real and worth pursuing
under different criteria → carried forward as **[[CAP-022]] Crash-Insurance / Tail-Hedge Overlay** (Planned).

## The full validation arc

| Stage | Window | Verdict |
|---|---|---|
| v1.0 initial | 1.5y (store overlap 2024-2026, bull-only, 1 flip) | Inconclusive (**data-gated**) |
| Deepen Option A | 7.4y (SEP → 2017, active names, all 3 environments, 14 flips) | Conditionally Promising → escalate |
| **Deepen Option B** | 7.4y (**survivorship-free**, 10,492 tickers, 18 flips) | **confirms negative → Rejected** |

The data gate was an ingestion gap (SEP covered the universe only from 2024), fixed by deepening SEP to
2017 (see `CAP020_DataDeepening_Scope_v0.1.md`). The pre-committed escalation rule (Conditionally
Promising + primary CIs span zero) sent Option A → Option B; Option B **confirmed** the result.

## Both universes agree (OOS, headline SMA 200 / gross 0.5 / 10 bps)

| Metric | Option A (surv-biased) | **Option B (surv-free)** | Read |
|---|---|---|---|
| **ΔCalmar (primary)** | −0.22 | **−0.30** | negative in **all 9** grid cells both runs; CI spans 0 |
| ΔSharpe (guardrail) | −0.15 | **−0.23** | **fails** the ≥ −0.05 guardrail |
| ΔMaxDD (supporting) | +2.2 pp | +2.6 pp | CI spans 0 — not significant |
| ΔCAGR | −7.9 pp | −9.7 pp | ~10pp return given up |
| Robustness | 0/9 | 0/9 | — |
| Benchmark MaxDD | −24.9% | **−24.6%** | survivorship-free is **not** deeper |

**Why survivorship-free didn't rescue it:** the "deeper drawdowns will make the protection pay"
hypothesis failed — the equal-weight book of four *diversified* factor books has moderate drawdowns
(~−25%) regardless of the name pool, so there is no deeper tail for the overlay to protect. If anything
the overlay looks slightly worse survivorship-free.

## The retained finding — crash insurance works (→ CAP-022)

Per-environment (near-identical in both runs; Option B shown):

| Environment | ΔMaxDD | ΔCalmar | ΔSharpe |
|---|---|---|---|
| **covid_2020** | **+14.65 pp** | **+0.248** | +0.050 |
| **bear_2022** | **+12.33 pp** | −0.020 | −0.080 |
| bull_2023_24 | +1.32 pp | −0.086 | +0.034 |

The overlay does exactly what a tail hedge should — big, reproducible drawdown cuts in sharp bears, and
it even improves risk-adjusted return *during* the COVID crash. It fails the *portfolio-improver* test
only because the always-on cost-of-carry in calm/bull regimes outweighs the aggregate benefit. That is
the right question for a **tail hedge**, not a return enhancer → **CAP-022** re-scopes it with
tail-risk acceptance criteria (crash-regime MaxDD/CVaR/worst-month vs calm-regime carry).

## Disposition

- **CAP-020 → Rejected (Evidenced)** as a portfolio Calmar/Sharpe/return improver — robust across
  parameters, cost levels, and a survivorship-free universe. Do not deploy as a return enhancer.
- **CAP-022 (Planned · Promising)** — the crash-insurance / tail-hedge re-scope. Reuses the deepened
  survivorship-free store + the `cap020_regime_validation.py` primitives. Charter:
  `CAP022_CrashInsurance_Charter_v0.1.md`.

## Reproducibility

Python 3.12.13 · numpy 2.2.6 · pandas 2.3.3 · bootstrap seed 17 · store deepened to 2017 (survivorship-free
Option B: 10,492 tickers / 13.7M rows, 5,192 reaching 2017; 1,868 book-days 2019–2026). Artifacts:
`data/cap020/cap020_validation_results.json` (Option A) + `data/cap020/survfree/…json` (Option B) on the
box. All runs executed on the **staging** deepen copy — live store untouched.

_v1.2 — 2026-07-04. FINAL. Supersedes v1.0 (data-gated) / v1.1 (Option A). Feeds the FI-001 registry
CAP-020 (Rejected) + CAP-022 (Planned) lines._
