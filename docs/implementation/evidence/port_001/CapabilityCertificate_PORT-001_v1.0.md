# Capability Certificate — PORT-001 **v1.0**

_The versioned platform-status stamp for a capability onboarded under the Capability Onboarding lifecycle (ADR 0030 §4; plan §Certificate). Versioning lets a later improvement (`v2.0`) be compared against this. Stamped on the Capability Manifest below._

| Field | Value |
|---|---|
| Capability | **PORT-001 — "Risk-Balanced Multi-Asset Portfolio"** (the Combined Book) |
| Capability class | Portfolio Construction (multi-sleeve ERC + crash/correlation overlays) |
| Certificate version | **v1.0 (Gate-Passed)** |
| Status | ✅ **Onboarding Gate PASSED** 2026-06-27 (construction-verification, Lifecycle Fidelity 98.8%, 6/6) |
| Date | 2026-06-27 |
| Governing ADR | `docs/adr/0030-portfolio-construction-engine-and-capability-onboarding.md` (Proposed) |
| Onboarding plan | `docs/implementation/TradingWorkbench_PORT001_ImplementationPlan_v1.0.md` (frozen) |

## Capability Manifest (ADR 0030 §3 — the registry metadata layer)

| Manifest field | Value |
|---|---|
| **name** | Risk-Balanced Multi-Asset Portfolio |
| **owner** | Jay Wang (GlobalComplyAI, LLC) |
| **research-id** | PORT-001 (Research Program Registry; `programs.py`, status **`validated`**) |
| **evidence-package** | ✅ `docs/implementation/evidence/port_001/EvidencePackage_PORT-001_v1.0.md` (Onboarding Gate PASSED, construction-verification) |
| **dependencies** | DCAP-001 (Sharadar PIT equity) · DCAP-003 (Alpaca bars) · **DCAP-006 (Total-Return Adapter)** · CAP-002/003 (Evidence Package + Bootstrap) · **CAP-018 (Portfolio Construction Engine)** |
| **risk-profile** | Medium — crash-protected beta; look-through equity-beta concentration (~13% capital / majority of risk, spec §6.2) is the headline disclosure |
| **paper-account** | _to be provisioned at §4_ |
| **version** | 1.0 |
| **certificate** | this document |

## Capability Onboarding Maturity (L0–L5) — current state

| Level | Gate | Status |
|---|---|---|
| **L0** | Research complete | ✅ **Completed** — validated in the sibling system; honest verdict below |
| **L1** | Evidence reproduced (Workbench Evidence Package) | ✅ **Completed** 2026-06-27 — construction-verification: the platform PCE reproduces the origin combined book from its sleeve return series (daily-return corr 0.99994). `EvidencePackage_PORT-001_v1.0.md`. |
| **L2** | Onboarding Gate passed | ✅ **Completed** 2026-06-27 — **6/6 criteria, Lifecycle Fidelity 98.8%** (Sharpe Δ0.0014 · MaxDD Δ0.0009 · daily-return corr 0.99994 · weight corr 0.99981 · trade-count n/a · determinism). |
| **L3** | Paper operational | ⏳ Pending — §4 live `combined_book` template + dedicated paper account (owner-gated) |
| **L4** | Continuous Evidence | ⏳ Pending — §5 monitors → Evidence Dashboard |
| **L5** | Production-Qualified | ⏳ Pending |

**Highest level reached: L2 (Onboarding Gate passed — construction).** The platform's Portfolio Construction Engine reproduces the origin combined book within tolerance on every criterion. **Scope:** this validates the *construction engine*; the self-stack (Alpaca total-return + platform momentum) end-to-end data-fidelity port is a separate tracked study (the harness's `--db` real mode), expected to read against a looser, attributed tolerance (cross-vendor: Alpaca vs Yahoo).

## Honest verdict (carried on every artifact — spec §6)

**Crash-protected BETA + diversification, NOT alpha.** Combined-book residual alpha is statistically insignificant (t = 0.82), and the equity sleeve's stock-selection alpha was **refuted under point-in-time data** (spec §6.4). The product's value is drawdown reduction (sibling MaxDD −11.9% vs equity-only −23.5%) and diversification, not selection skill. The #1 operational risk is the **diversification thesis weakening** (sleeve correlation 0.68→0.77, spec §6.1).

## What advances this certificate

**L1 + L2 done** (construction-verification, 2026-06-27). Next: **§4** — build the live `combined_book` template + provision a dedicated paper account + activate (24h cooldown, ADR 0005) → advances **L3** (owner-gated). In parallel, the **self-stack data-fidelity study** (`--db` real mode over Sharadar + the §1 Total-Return Adapter) confirms the platform's own data path; **§5** Continuous Evidence advances **L4**.

_v1.0 — 2026-06-27. A capability certificate is re-issued (same or bumped version) as the capability advances the maturity ladder or is re-onboarded with improvements._
