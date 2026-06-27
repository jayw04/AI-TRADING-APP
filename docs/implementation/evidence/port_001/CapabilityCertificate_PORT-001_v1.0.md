# Capability Certificate — PORT-001 **v1.0**

_The versioned platform-status stamp for a capability onboarded under the Capability Onboarding lifecycle (ADR 0030 §4; plan §Certificate). Versioning lets a later improvement (`v2.0`) be compared against this. Stamped on the Capability Manifest below._

| Field | Value |
|---|---|
| Capability | **PORT-001 — "Risk-Balanced Multi-Asset Portfolio"** (the Combined Book) |
| Capability class | Portfolio Construction (multi-sleeve ERC + crash/correlation overlays) |
| Certificate version | **v1.0** |
| Date | 2026-06-27 |
| Governing ADR | `docs/adr/0030-portfolio-construction-engine-and-capability-onboarding.md` (Proposed) |
| Onboarding plan | `docs/implementation/TradingWorkbench_PORT001_ImplementationPlan_v1.0.md` (frozen) |

## Capability Manifest (ADR 0030 §3 — the registry metadata layer)

| Manifest field | Value |
|---|---|
| **name** | Risk-Balanced Multi-Asset Portfolio |
| **owner** | Jay Wang (GlobalComplyAI, LLC) |
| **research-id** | PORT-001 (Research Program Registry; `programs.py`, status `planned`) |
| **evidence-package** | _pending_ — produced by the §2 reproduction run (data-gated) |
| **dependencies** | DCAP-001 (Sharadar PIT equity) · DCAP-003 (Alpaca bars) · **DCAP-006 (Total-Return Adapter)** · CAP-002/003 (Evidence Package + Bootstrap) · **CAP-018 (Portfolio Construction Engine)** |
| **risk-profile** | Medium — crash-protected beta; look-through equity-beta concentration (~13% capital / majority of risk, spec §6.2) is the headline disclosure |
| **paper-account** | _to be provisioned at §4_ |
| **version** | 1.0 |
| **certificate** | this document |

## Capability Onboarding Maturity (L0–L5) — current state

| Level | Gate | Status |
|---|---|---|
| **L0** | Research complete | ✅ **Completed** — validated in the sibling system; honest verdict below |
| **L1** | Evidence reproduced (Workbench Evidence Package) | ⏳ **Pending** — the §2 reproduction backtest is data-gated (real Sharadar + total-return ETF bars; `data.alpaca.markets` Norton-blocked here) |
| **L2** | Onboarding Gate passed | ⏳ Pending — runs after L1 (Sharpe ±0.05 · MaxDD ±2pp · daily-return corr ≥0.98 · weight corr >0.99 · trade-count · determinism) |
| **L3** | Paper operational | ⏳ Pending — §4 live `combined_book` template + dedicated paper account |
| **L4** | Continuous Evidence | ⏳ Pending — §5 monitors → Evidence Dashboard |
| **L5** | Production-Qualified | ⏳ Pending |

**Highest level reached: L0 (Research complete).** The platform machinery for L1–L2 is built and unit-tested (the Portfolio Construction Engine, the Onboarding Gate); only the data-gated reproduction *run* remains to advance the certificate.

## Honest verdict (carried on every artifact — spec §6)

**Crash-protected BETA + diversification, NOT alpha.** Combined-book residual alpha is statistically insignificant (t = 0.82), and the equity sleeve's stock-selection alpha was **refuted under point-in-time data** (spec §6.4). The product's value is drawdown reduction (sibling MaxDD −11.9% vs equity-only −23.5%) and diversification, not selection skill. The #1 operational risk is the **diversification thesis weakening** (sleeve correlation 0.68→0.77, spec §6.1).

## What advances this certificate

Run the **§2 reproduction** in a non-Norton environment with the data → if the **Onboarding Gate** passes within tolerance (drift attributed, not waived), set **L1 + L2 = ✅**, attach the Evidence Package + the Lifecycle Fidelity dashboard, promote the `programs.py` status `planned → validated`, and issue the certificate as **v1.0 (Gate-Passed)**. Then §4 (paper) advances L3, §5 advances L4.

_v1.0 — 2026-06-27. A capability certificate is re-issued (same or bumped version) as the capability advances the maturity ladder or is re-onboarded with improvements._
