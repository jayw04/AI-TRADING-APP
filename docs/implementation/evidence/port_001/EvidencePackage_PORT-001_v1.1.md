# Evidence Package — PORT-001 **v1.1** (Capability Refresh: +KMLM, +correlation-aware tilt)

_Companion to `EvidencePackage_PORT-001_v1.0.md` (the initial 8-asset onboarding). This package documents the **refresh** that brought the platform's `combined-book` (strategy id=9) in line with the sibling `claude-trading-view` Combined Book after the origin evolved (sibling spec `Docs/Combined Book Strategy.md` §5.6 / §11 #1). Honest verdict unchanged: **crash-protected beta + diversification, NOT alpha.**_

## 1. What changed and why

| Change | Rationale (sibling spec) | Platform locus |
|---|---|---|
| **KMLM (managed futures) added — universe 8 → 9** | The #1 documented risk is **diversification decay** (§6.1): the cross-asset sleeve drifted to ~90% equity-correlated and the within-8 tilt is exhausted (only USD/commodities still hedge). Managed futures hedge the **rate/inflation crisis** (2022) where bonds fail *with* stocks — the book's weakest regime. KMLM-specific (§5.6: FMF marginal, DBMF hurt). | `app/research/factor_lab/cross_asset.py` `CROSS_ASSET_UNIVERSE` (8→9) |
| **Correlation-aware tilt (λ=0.5), ON** | Down-weight whatever is currently equity-correlated, lean into live hedges. Validated with KMLM *together* (§5.6 Step 4: +KMLM+tilt is the combined winner). | `cross_asset_tsmom(..., corr_aware=True)`; `combined_book.py` template params |

Deferred by decision: the look-through equity-beta-cap governor (sibling lever #2).

## 2. The exact ported logic

`d_a = clip(1 − 0.5·corr₆₀(asset, SPY), 0.0, 2.0)`, multiplied into the inverse-vol risk-parity weights, **after** the trend filter and **before** the de-risk-only vol-target (which is unchanged). SPY is the equity proxy (corr→1 → the proxy itself gets the 1−λ = 0.5 multiplier; faithful). Default OFF in the engine (existing callers byte-identical); ON in the `combined-book` template. Faithful port of the sibling `cross_asset_momentum._weights` (λ=0.5, window 60, floor 0.0, cap 2.0).

## 3. Gate A — delta-parity (construction-verification of the port, real sibling data)

`scripts/verify_tilt_parity.py` → `port001_delta_parity_tilt.json`. Feeds the **sibling's own Yahoo total-return data** (9 assets) into the **platform** `cross_asset_tsmom` and asserts the documented directional book (isolates the port from Alpaca-vs-Yahoo noise). **PASSED** (asof 2026-07-02):

| Metric | Platform engine | Sibling doc (§11 #1 / §5.6) |
|---|---|---|
| KMLM sleeve share | **10.66%** | ~7–11% ✓ |
| SPY sleeve share (base → tilt) | 8.78% → **4.92%** | "SPY 9→5%" ✓ |
| Sleeve equity-corr (base → tilt) | +0.213 → **+0.024** | tilt cuts sleeve-corr toward +0.07 ✓ |
| Gross | 1.000 (de-risk only) | ≤ 1 ✓ |

The platform's tilted weights match the sibling's regenerated `live_weights` (asof 2026-07-02) **exactly** — e.g. KMLM 0.1066, SPY 0.0492 — confirming the port is faithful, not merely directionally similar.

## 4. Gate B — full onboarding gate (9-asset construction-verification)

Regenerated the sibling's 9-asset tilted cross-asset series (`cross_asset_momentum_2026-07-03.json`, `ASSETS=…,KMLM CORR_AWARE=1 CORR_LAMBDA=0.5`), refreshed the `--from-sibling` tilted weights, and ran `scripts/run_port001_reproduction.py --from-sibling`. **PASSED — Lifecycle Fidelity 96.7%, 6/6** (`LifecycleFidelity_CONSTRUCTION_VERIFICATION_v1.1.md`, `port001_construction_verification_v1.1.json`; the v1.0 8-asset artifacts of the same base name are retained unchanged):

| Criterion | Value | Threshold | Pass |
|---|---|---|---|
| sharpe (|Δ|) | 0.0091 | ≤ 0.05 | ✓ |
| maxdd (|Δ|) | 0.0003 | ≤ 0.02 | ✓ |
| daily_return_corr | 0.99988 | ≥ 0.98 | ✓ |
| weight_corr | 0.99975 | ≥ 0.99 | ✓ |
| trade_count | n/a (return series) | ≤ 0.10 | ✓ |
| determinism | 1.0 | 1.0 | ✓ |

Candidate (platform ERC blend): Sharpe **1.03** · MaxDD **−9.25%**. Reference (sibling combined, fixed 0.40/0.60): Sharpe **1.02** · MaxDD **9.22%**. The platform's construction engine reproduces the sibling's refreshed 9-asset combined book within tolerance.

## 5. Honest window / gate scope

- **Window:** the 9-asset gate runs on the **KMLM-era window (2020-12 → 2026-07)** — KMLM's life (inception 2020-12). This is the correct window to validate KMLM on, and is a *different, shorter* sample than v1.0's 8-asset 2016–2026 gate. The 96.7% (vs v1.0's 98.8%) reflects the shorter window, not a regression.
- **Which gate:** the passing gate is **construction-verification** (`--from-sibling`). The **self-stack `--db`** reproduction (platform's own Alpaca+Sharadar data) remains the documented attributed companion (`SelfStackDataFidelity_PORT-001_v0.1.md`) — cross-vendor (Alpaca IEX 2018 start vs Yahoo), not a blocker.
- **Reference provenance:** the 9-asset reference is assembled inside `--from-sibling` from the sibling's regenerated `cross_asset_momentum_2026-07-03.json` (cross-asset leg) + the newest `factor_backtest_*.json` (equity leg, unchanged by KMLM) + the 2026-07-03 tilted `live_weights`. The committed `sibling_reference.json` remains the **8-asset** self-stack reference.

## 6. Live deployment

Strategy id=9 `combined-book` (user 7 / account 7 = ALPACA_PAPER_6) re-registered 2026-07-03 with **209 symbols** (200 momentum universe + 9 ETFs incl KMLM) and the tilt params (`ca_corr_aware=True`, `ca_corr_lambda=0.5`). Orders route through OrderRouter (ADR 0002) + the risk engine; no LLM (ADR 0006 v2). Template version bumped `1.0.0 → 1.1.0`.

_v1.1 — 2026-07-03._
