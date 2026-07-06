# Capability Certificate — PORT-001 **v1.1**

_The versioned platform-status stamp for a capability onboarded under the Capability Onboarding lifecycle (ADR 0030 §4; plan §Certificate). v1.1 re-issues v1.0 after a **capability refresh**: the origin (sibling `claude-trading-view`) evolved its live Combined Book, and the platform book was brought in line. Supersedes `CapabilityCertificate_PORT-001_v1.0.md` (retained as the record of the initial 8-asset onboarding)._

| Field | Value |
|---|---|
| Capability | **PORT-001 — "Risk-Balanced Multi-Asset Portfolio"** (the Combined Book) |
| Capability class | Portfolio Construction (multi-sleeve ERC + crash/correlation overlays) |
| Certificate version | **v1.1 (Gate-Passed)** |
| Status | ✅ **Onboarding Gate PASSED** 2026-07-03 (construction-verification, Lifecycle Fidelity **96.7%**, 6/6) on the refreshed **9-asset + correlation-aware tilt** book |
| Date | 2026-07-03 |
| Supersedes | v1.0 (8-asset, λ=0; Gate-Passed 2026-06-27 at 98.8%) |
| Governing ADR | `docs/adr/0030-portfolio-construction-engine-and-capability-onboarding.md` — **no new ADR** (no architectural invariant changes; KMLM is a symbol on the existing Alpaca path, not a new external dependency) |
| Onboarding plan | `docs/implementation/TradingWorkbench_PORT001_ImplementationPlan_v1.0.md` (frozen) |

## What changed in v1.1 (the refresh — PORT-001 §5.6 / §11 #1 of the sibling spec)

1. **KMLM (managed futures) added — cross-asset universe 8 → 9.** The first *structural* response to the capability's #1 documented risk (diversification decay: the cross-asset sleeve had drifted to ~90% equity-correlated; the within-8 tilt is exhausted). Managed futures hedge the **rate/inflation crisis** (2022) where bonds fail *with* stocks — the book's weakest regime. KMLM-index-specific (FMF marginal, DBMF hurt). `app/research/factor_lab/cross_asset.py` `CROSS_ASSET_UNIVERSE`.
2. **Correlation-aware tilt (λ=0.5) — ON.** Down-weights whatever is currently equity-correlated, leans into the live hedges: `clip(1 − 0.5·corr₆₀(asset, SPY), 0, 2)` applied to the inverse-vol risk-parity weights, before the (unchanged) de-risk-only vol-target. `cross_asset_tsmom(..., corr_aware=True)`. Default OFF in the engine; ON in the `combined-book` template params.

**Deferred (separate later work):** the look-through equity-beta-cap governor (sibling lever #2).

## Capability Manifest (ADR 0030 §3)

| Manifest field | Value |
|---|---|
| **name** | Risk-Balanced Multi-Asset Portfolio |
| **owner** | Jay Wang (GlobalComplyAI, LLC) |
| **research-id** | PORT-001 (Research Program Registry; `programs.py`, status **`validated`**) |
| **evidence-package** | ✅ `docs/implementation/evidence/port_001/EvidencePackage_PORT-001_v1.1.md` (refresh; both gates passed) |
| **dependencies** | DCAP-001 (Sharadar PIT equity) · DCAP-003 (Alpaca bars) · DCAP-006 (Total-Return Adapter) · CAP-002/003 (Evidence Package + Bootstrap) · CAP-018 (Portfolio Construction Engine) |
| **risk-profile** | Medium — crash-protected beta; look-through equity-beta concentration remains the headline disclosure (the beta-cap governor is deferred) |
| **paper-account** | ✅ account 7 (user 7 `combined-book@globalcomplyai.com`, ALPACA_PAPER_6, $100k) — strategy id=9 live on PAPER; re-registered with the 9-asset + tilt config 2026-07-03 |
| **version** | 1.1 |
| **certificate** | this document |

## Capability Onboarding Maturity (L0–L5) — current state

| Level | Gate | Status |
|---|---|---|
| **L0** | Research complete | ✅ **Completed** — refresh validated in the sibling (spec §5.6: KMLM PURSUE→DEPLOYED; combined book 0.87→1.00 Sharpe with the tilt). |
| **L1** | Evidence reproduced | ✅ **Completed (refreshed 2026-07-03)** — the platform's ported `cross_asset_tsmom` reproduces the sibling's 9-asset tilted sleeve weights **exactly** on the sibling's own Yahoo total-return data (KMLM 0.1066, SPY 0.0492 — identical to `live_weights`). Delta-parity gate `port001_delta_parity_tilt.json`. |
| **L2** | Onboarding Gate passed | ✅ **Completed (refreshed 2026-07-03)** — **6/6 criteria, Lifecycle Fidelity 96.7%** on the 9-asset construction-verification (Sharpe Δ0.0091 · MaxDD Δ0.0003 · daily-return corr 0.99988 · weight corr 0.99975 · trade-count n/a · determinism). `LifecycleFidelity_CONSTRUCTION_VERIFICATION_v1.1.md` / `port001_construction_verification_v1.1.json` (the v1.0 8-asset artifacts are retained unchanged). |
| **L3** | Paper operational | ✅ **Completed** — live on PAPER: strategy id=9 `combined-book` (user 7 / account 7 = ALPACA_PAPER_6), re-registered 2026-07-03 with 209 symbols (200 momentum + 9 ETFs incl KMLM) + the tilt params, schedule `0 14 * * mon`. |
| **L4** | Continuous Evidence | 🔄 **Accruing** — account-7 equity snapshots + the weekly live-evidence pipeline; L4 confirms once a clean multi-week track record accrues (ADR 0014). The refresh resets nothing — the maturity clock continues. |
| **L5** | Production-Qualified | ⏳ Pending |

**Highest level reached: L3 (Paper operational).**

**Window/gate notes (honest scope):**
- The 9-asset gate runs on the **KMLM-era window (2020-12 → 2026-07)** — KMLM's life. This is the correct window to validate KMLM on, and is a *different* window than v1.0's 8-asset 2016–2026 gate (hence 96.7% vs 98.8% — not a regression, a different, shorter sample).
- The **passing** gate is the **construction-verification** path (`--from-sibling`: the sibling's own return series through the platform PCE/ERC). The **self-stack `--db`** reproduction (platform's own Alpaca+Sharadar data) remains the documented, attributed companion (`SelfStackDataFidelity_PORT-001_v0.1.md`), not a blocker.
- The committed `sibling_reference.json` remains the **8-asset** self-stack reference; the 9-asset reference is assembled inside the `--from-sibling` construction-verification path from the sibling's regenerated `cross_asset_momentum_2026-07-03.json` + the 2026-07-03 tilted `live_weights`.

## Honest verdict (unchanged — spec §6)

**Crash-protected BETA + diversification, NOT alpha.** The refresh **strengthens the diversification** (sleeve equity-correlation falls under the tilt+KMLM: +0.213 → +0.024 on the delta-parity as-of; sibling reports sleeve-corr +0.55 → +0.07), directly addressing the #1 risk (§6.1) — but it does not manufacture alpha. Combined-book residual alpha remains statistically insignificant; the equity sleeve's selection alpha was refuted under PIT (§6.4).

## What advances this certificate

L1+L2+L3 done for the refresh. **L4** confirms once account-7 accrues a clean multi-week Continuous-Evidence track record on the 9-asset+tilt config; then **§6** retire the sibling (L5) — still deferred until the platform book proves out. Deferred capability work: the look-through equity-beta-cap governor (sibling lever #2) and a total-return live-pricing path for the sleeve.

_v1.1 — 2026-07-03. Re-issued on capability refresh (origin evolved; platform brought in line)._
